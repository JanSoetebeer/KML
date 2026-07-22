"""
Authentication helpers.

Security model (hardened for public/multi-user deployment):
- Passwords are stored as **bcrypt hashes** in SYS_USER_DATA (never plaintext).
- The login token is an **opaque, signed session token** (itsdangerous) that
  carries only the user id + username and an issue timestamp. It does NOT
  contain the password and cannot be forged without the server ``SECRET_KEY``.
  Tokens expire after ``SESSION_MAX_AGE_SECONDS`` (default 12h).

The token is stored in the browser's localStorage; on revisiting the login page
it is validated and the user is redirected straight to the application.
"""

import os
import sqlite3

import bcrypt
from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SECRET_KEY = os.getenv("SECRET_KEY", "")
_TOKEN_SALT = "webapp-session-v1"
_TOKEN_MAX_AGE = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(12 * 3600)))


def _serializer() -> URLSafeTimedSerializer:
    """Return the signing serializer; fails loudly if SECRET_KEY is unset."""
    if not _SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. Refusing to issue "
            "session tokens with an empty signing key."
        )
    return URLSafeTimedSerializer(_SECRET_KEY, salt=_TOKEN_SALT)


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password* (safe to store)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches the stored bcrypt *hashed* value."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def make_token(user_id: int, username: str) -> str:
    """Create a signed, timestamped session token (no password inside)."""
    return _serializer().dumps({"uid": int(user_id), "u": username})


def decode_token(token: str) -> dict:
    """Verify + decode a session token into ``{'uid', 'u'}``; raises on failure."""
    try:
        data = _serializer().loads(token, max_age=_TOKEN_MAX_AGE)
        return {"uid": int(data["uid"]), "u": data["u"]}
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError) as exc:
        raise ValueError("Malformed or expired token") from exc


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict | None:
    """Return the full user info dict if credentials match, else ``None``."""
    row = conn.execute(
        "SELECT id, username, password, position_id FROM SYS_USER_DATA "
        "WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not verify_password(password, row["password"]):
        return None
    return build_user_info(conn, row)


def resolve_token_user(conn: sqlite3.Connection, token: str) -> dict | None:
    """Resolve a session token to a user info dict, or ``None`` if invalid.

    The token's embedded username must still match the stored one, so renaming
    (or deleting) a user invalidates their existing tokens.
    """
    try:
        data = decode_token(token)
    except ValueError:
        return None
    row = conn.execute(
        "SELECT id, username, position_id FROM SYS_USER_DATA WHERE id = ?",
        (data["uid"],),
    ).fetchone()
    if row is None or row["username"] != data["u"]:
        return None
    return build_user_info(conn, row)


def build_user_info(conn: sqlite3.Connection, user_row: sqlite3.Row) -> dict:
    """Assemble a user dict: id, username, position, is_admin and roles."""
    position = conn.execute(
        "SELECT bezeichnung FROM SYS_POSITION WHERE id = ?", (user_row["position_id"],)
    ).fetchone()
    position_name = position["bezeichnung"] if position else None

    roles = conn.execute(
        "SELECT r.id, r.bezeichnung FROM SYS_ROLES r "
        "JOIN SYS_USER_ROLES ur ON ur.role_id = r.id "
        "WHERE ur.user_id = ? ORDER BY r.bezeichnung",
        (user_row["id"],),
    ).fetchall()

    return {
        "id": user_row["id"],
        "username": user_row["username"],
        "position": position_name,
        "is_admin": position_name == "Administrator",
        "roles": [{"id": r["id"], "bezeichnung": r["bezeichnung"]} for r in roles],
    }


def get_current_user(x_auth_token: str | None = Header(default=None)) -> dict:
    """
    FastAPI dependency: resolve the current user from the X-Auth-Token header.

    Raises 401 if the token is missing/invalid or the credentials no longer
    match a user (e.g. password changed).
    """
    from .db import get_connection

    if not x_auth_token:
        raise HTTPException(status_code=401, detail="Kein Token übergeben.")

    conn = get_connection()
    try:
        user = resolve_token_user(conn, x_auth_token)
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldedaten nicht mehr gültig.")
    return user


def require_admin(user: dict) -> None:
    """Raise 403 if the given user is not an Administrator."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Nur für Administratoren.")
