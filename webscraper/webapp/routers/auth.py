"""Authentication endpoints: login and token validation."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import authenticate, decode_token, get_current_user, make_token
from ..db import get_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenRequest(BaseModel):
    token: str


@router.post("/login")
def login(req: LoginRequest):
    """Validate credentials. On success return a token + user info."""
    conn = get_connection()
    try:
        user = authenticate(conn, req.username, req.password)
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Ungültige Anmeldedaten.")

    return {"token": make_token(req.username, req.password), "user": user}


@router.post("/validate")
def validate(req: TokenRequest):
    """Validate a stored token (used for auto-redirect on the login page)."""
    try:
        username, password = decode_token(req.token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Ungültiger Token.")

    conn = get_connection()
    try:
        user = authenticate(conn, username, password)
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldedaten nicht mehr gültig.")
    return {"user": user}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user (used by the app on load)."""
    return {"user": user}
