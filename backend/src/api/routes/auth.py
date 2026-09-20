"""
routes/auth.py — Authentication routes (API version: v2)
==========================================================
Provides session management, registration, and user identity endpoints.
Sets secure httpOnly cookies and returns bearer tokens.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.api.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthContext,
    authenticate_user,
    create_session_token,
    register_user,
)
from src.api.dependencies.auth import get_auth_context

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    org_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=120)
    name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)
    password: str


class AuthResponse(BaseModel):
    user_id: str
    org_id: str
    email: str
    name: str
    role: str
    token: str


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response):
    """Register a new organization and initial administrator user."""
    try:
        user = register_user(
            org_name=body.org_name,
            email=body.email,
            name=body.name,
            password=body.password,
            role="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    token = create_session_token(user)

    # Set httpOnly secure session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True behind TLS in production
    )

    return AuthResponse(
        user_id=user.user_id,
        org_id=user.org_id,
        email=user.email,
        name=user.name,
        role=user.role,
        token=token,
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response):
    """Authenticate with email and password to receive session cookie and token."""
    user = authenticate_user(email=body.email, password=body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_session_token(user)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
    )

    return AuthResponse(
        user_id=user.user_id,
        org_id=user.org_id,
        email=user.email,
        name=user.name,
        role=user.role,
        token=token,
    )


@router.post("/logout")
def logout(response: Response):
    """Clear session cookie and terminate user session."""
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"status": "logged_out", "message": "Session terminated successfully."}


@router.get("/me")
def get_me(ctx: AuthContext = Depends(get_auth_context)):
    """Return currently authenticated user and organization identity."""
    return {
        "user_id": ctx.user_id,
        "org_id": ctx.org_id,
        "email": ctx.email,
        "role": ctx.role,
        "is_authenticated": ctx.is_authenticated,
    }
