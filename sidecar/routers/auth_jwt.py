"""Authentication endpoints for JWT-based login."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.jwt_auth import authenticate_user, create_access_token, verify_token

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
    token_type: str = "bearer"


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    access, refresh = authenticate_user(body.user_id, body.password)
    if not access:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(access_token=access, refresh_token=refresh)


@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest):
    payload = verify_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = payload["sub"]
    new_access = create_access_token(user_id)
    return RefreshResponse(access_token=new_access)
