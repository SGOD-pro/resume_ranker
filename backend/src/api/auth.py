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

def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()
    return f"{salt.hex()}${pw_hash}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if "$" in stored_hash:
        salt_hex, hash_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        candidate_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()
        return hmac.compare_digest(hash_hex, candidate_hash)
    # Backward compatibility with legacy static salt
    legacy_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"sortlist_v2_salt", 100_000).hex()
    return hmac.compare_digest(stored_hash, legacy_hash)


_USERS: Dict[str, User] = {
    "recruiter@sortlist.local": User(
        user_id=DEFAULT_USER_ID,
        org_id=DEFAULT_ORG_ID,
        email="recruiter@sortlist.local",
        name="Lead Recruiter",
        role="recruiter",
        password_hash=_hash_password("recruiter123", salt=b"sortlist_v2_salt"),
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
            logger.info("Session token expired for user_id: %s", payload.get("sub", "unknown"))
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

def _persist_user_dynamo(user: User) -> None:
    try:
        from src.infrastructure.repositories.base import _get_table
        table = _get_table()
        table.put_item(
            Item={
                "PK": f"USER#{user.email}",
                "SK": "METADATA",
                "entity_type": "USER",
                "user_id": user.user_id,
                "org_id": user.org_id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "password_hash": user.password_hash,
                "created_at": str(user.created_at),
            }
        )
    except Exception as exc:
        logger.debug("DynamoDB user persistence fallback: %s", exc)


def _persist_org_dynamo(org: Organization) -> None:
    try:
        from src.infrastructure.repositories.base import _get_table
        table = _get_table()
        table.put_item(
            Item={
                "PK": f"ORG#{org.org_id}",
                "SK": "METADATA",
                "entity_type": "ORG",
                "org_id": org.org_id,
                "name": org.name,
                "created_at": str(org.created_at),
            }
        )
    except Exception as exc:
        logger.debug("DynamoDB org persistence fallback: %s", exc)


def _fetch_user_dynamo(email: str) -> Optional[User]:
    try:
        from src.infrastructure.repositories.base import _get_table
        table = _get_table()
        resp = table.get_item(Key={"PK": f"USER#{email}", "SK": "METADATA"})
        it = resp.get("Item")
        if it:
            u = User(
                user_id=it["user_id"],
                org_id=it["org_id"],
                email=it["email"],
                name=it["name"],
                role=it["role"],
                password_hash=it["password_hash"],
                created_at=float(it.get("created_at", 0.0) or 0.0),
            )
            _USERS[email] = u
            return u
    except Exception as exc:
        logger.debug("DynamoDB user fetch fallback: %s", exc)
    return None


def register_user(org_name: str, email: str, name: str, password: str, role: str = "recruiter") -> User:
    """Register a new organization and initial user."""
    norm_email = email.strip().lower()
    if norm_email in _USERS or _fetch_user_dynamo(norm_email):
        raise ValueError("User with this email already exists")

    org_id = f"org_{uuid.uuid4().hex[:10]}"
    org = Organization(
        org_id=org_id,
        name=org_name.strip(),
        created_at=time.time(),
    )
    _ORGANIZATIONS[org_id] = org
    _persist_org_dynamo(org)

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
    _persist_user_dynamo(user)
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password."""
    norm_email = email.strip().lower()
    user = _USERS.get(norm_email) or _fetch_user_dynamo(norm_email)
    if not user:
        return None

    if _verify_password(password, user.password_hash):
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
