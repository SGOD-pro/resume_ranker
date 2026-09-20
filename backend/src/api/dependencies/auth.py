"""
dependencies/auth.py — Authentication and Authorization dependencies
===================================================================
Extracts session from httpOnly cookie or Authorization Bearer header,
verifies tenant ownership, and enforces role boundaries.
"""

import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from src.api.auth import (
    SESSION_COOKIE_NAME,
    AuthContext,
    get_default_auth_context,
    verify_session_token,
)

logger = logging.getLogger(__name__)

# If STRICT_AUTH=true or ENVIRONMENT=prod, reject unauthenticated requests without fallback
STRICT_AUTH = os.environ.get("STRICT_AUTH", "false").lower() in ("true", "1", "yes")


async def get_auth_context(request: Request) -> AuthContext:
    """Extract and verify user authentication context.

    Inspects:
    1. Cookie `sortlist_session`
    2. Header `Authorization: Bearer <token>`
    3. Fallback to default developer context if non-production and unauthenticated
    """
    token: Optional[str] = None

    # 1. Authorization header (explicit credential takes precedence)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Cookie (ambient session)
    if not token and SESSION_COOKIE_NAME in request.cookies:
        token = request.cookies[SESSION_COOKIE_NAME]


    if token:
        ctx = verify_session_token(token)
        if ctx:
            return ctx
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session. Please log in again.",
            )

    # If strict auth is enabled, require valid token
    env = os.environ.get("ENVIRONMENT", "dev").lower()
    if STRICT_AUTH or env in ("prod", "production"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    # In local development mode without token, provide default authenticated recruiter context
    return get_default_auth_context()


def require_recruiter(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Ensure user has at least recruiter-level privileges."""
    if ctx.role not in ("admin", "recruiter"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required.",
        )
    return ctx


def require_admin(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Ensure user has admin privileges."""
    if ctx.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return ctx


def enforce_tenant_ownership(resource_org_id: str, ctx: AuthContext) -> None:
    """Verify that resource belongs to the user's organization."""
    if not resource_org_id:
        return  # Legacy un-tenanted resource
    if ctx.org_id != resource_org_id and ctx.role != "superadmin":
        logger.warning(
            "Tenant access violation: user org %s attempted access to resource org %s",
            ctx.org_id,
            resource_org_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: resource belongs to another organization.",
        )

