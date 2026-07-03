"""Authentication endpoints: login and token validation."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import authenticate, get_current_user, make_token, resolve_token_user
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

    return {"token": make_token(user["id"], user["username"]), "user": user}


@router.post("/validate")
def validate(req: TokenRequest):
    """Validate a stored token (used for auto-redirect on the login page)."""
    conn = get_connection()
    try:
        user = resolve_token_user(conn, req.token)
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldedaten nicht mehr gültig.")
    return {"user": user}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user (used by the app on load)."""
    return {"user": user}
