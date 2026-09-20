"""
auth.py — Authentication and Session Management for Sortlist v2
================================================================
Implements secure HMAC-SHA256 session tokens, user/tenant entities,
and authentication helpers with zero external crypto dependencies.
Supports both httpOnly secure cookies and Authorization: Bearer tokens.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default secret key from env or fallback for local development
SECRET_KEY = os.environ.get(
    "SESSION_SECRET_KEY",
    "swyra-sortlist-v2-dev-secret-key-32-chars-long-minimum!"
).encode("utf-8")

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "sortlist_session")
SESSION_MAX_AGE_SECONDS = int(os.environ.get("SESSION_MAX_AGE_SECONDS", "86400"))  # 24 hours


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("utf-8"))


@dataclass
class User:
    user_id: str
    org_id: str
    email: str
    name: str
    role: str  # "admin" | "recruiter" | "viewer"
    password_hash: str
    created_at: float


@dataclass
class Organization:
    org_id: str
    name: str
    created_at: float


@dataclass
class AuthContext:
    user_id: str
    org_id: str
    email: str
    role: str
    is_authenticated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── In-memory user and org registry ──────────────────────────────────────────
# Default demo organization and user for development & out-of-the-box operation
DEFAULT_ORG_ID = "org_default"
DEFAULT_USER_ID = "user_recruiter"

_ORGANIZATIONS: Dict[str, Organization] = {
    DEFAULT_ORG_ID: Organization(
        org_id=DEFAULT_ORG_ID,
        name="Default Workspace",
        created_at=time.time(),
    )
}

def _hash_password(password: str) -> str:
    salt = b"sortlist_v2_salt"
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()

_USERS: Dict[str, User] = {
    "recruiter@sortlist.local": User(
        user_id=DEFAULT_USER_ID,
        org_id=DEFAULT_ORG_ID,
        email="recruiter@sortlist.local",
        name="Lead Recruiter",
        role="recruiter",
        password_hash=_hash_password("recruiter123"),
        created_at=time.time(),
    )
}


# ── Token Generation & Verification ──────────────────────────────────────────

def create_session_token(user: User, max_age: int = SESSION_MAX_AGE_SECONDS) -> str:
    """Create a tamper-evident HMAC-SHA256 session token."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.user_id,
        "org_id": user.org_id,
        "email": user.email,
        "role": user.role,
        "name": user.name,
        "exp": int(time.time()) + max_age,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
    }

    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    message = f"{header_b64}.{payload_b64}".encode("utf-8")

    signature = hmac.new(SECRET_KEY, message, hashlib.sha256).digest()
    sig_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> Optional[AuthContext]:
    """Verify HMAC token signature and expiration."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, sig_b64 = parts
        message = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(SECRET_KEY, message, hashlib.sha256).digest()

        actual_sig = _b64decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            logger.warning("Session token HMAC signature verification failed")
            return None

        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp", 0)
        if time.time() > exp:
            logger.info("Session token expired for user: %s", payload.get("email"))
            return None

        return AuthContext(
            user_id=payload.get("sub", ""),
            org_id=payload.get("org_id", DEFAULT_ORG_ID),
            email=payload.get("email", ""),
            role=payload.get("role", "viewer"),
            is_authenticated=True,
        )
    except Exception as exc:
        logger.warning("Error verifying session token: %s", exc)
        return None


# ── User and Org Management Helpers ──────────────────────────────────────────

def register_user(org_name: str, email: str, name: str, password: str, role: str = "recruiter") -> User:
    """Register a new organization and initial user."""
    norm_email = email.strip().lower()
    if norm_email in _USERS:
        raise ValueError("User with this email already exists")

    org_id = f"org_{uuid.uuid4().hex[:10]}"
    _ORGANIZATIONS[org_id] = Organization(
        org_id=org_id,
        name=org_name.strip(),
        created_at=time.time(),
    )

    user = User(
        user_id=f"user_{uuid.uuid4().hex[:10]}",
        org_id=org_id,
        email=norm_email,
        name=name.strip(),
        role=role,
        password_hash=_hash_password(password),
        created_at=time.time(),
    )
    _USERS[norm_email] = user
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password."""
    norm_email = email.strip().lower()
    user = _USERS.get(norm_email)
    if not user:
        return None

    if hmac.compare_digest(user.password_hash, _hash_password(password)):
        return user
    return None


def get_user_by_id(user_id: str) -> Optional[User]:
    for user in _USERS.values():
        if user.user_id == user_id:
            return user
    return None


def get_default_auth_context() -> AuthContext:
    """Return default authenticated recruiter context for local dev."""
    return AuthContext(
        user_id=DEFAULT_USER_ID,
        org_id=DEFAULT_ORG_ID,
        email="recruiter@sortlist.local",
        role="recruiter",
        is_authenticated=True,
    )
