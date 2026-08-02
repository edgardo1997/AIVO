"""Authentication endpoints for JWT-based login."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.jwt_auth import authenticate_user, rotate_refresh_token

log = logging.getLogger("sentinel.auth_jwt")

router = APIRouter()


class LoginRequest(BaseModel):
    user_id: str
    password: str = ""


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    access, refresh = authenticate_user(body.user_id, body.password)
    if not access:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(access_token=access, refresh_token=refresh)


@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest):
    new_access, new_refresh = rotate_refresh_token(body.refresh_token)
    if not new_access or not new_refresh:
        raise HTTPException(status_code=401, detail="Invalid, expired, or already-rotated refresh token")
    # Rotation invalidates the submitted refresh token server-side, so it can
    # never be exchanged again (prevents replay).
    return RefreshResponse(access_token=new_access, refresh_token=new_refresh)
