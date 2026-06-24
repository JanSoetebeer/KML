"""
Authentication helpers.

Per the project decision, this uses a deliberately simple, *plaintext* scheme:
- Passwords are stored in plaintext in SYS_USER_DATA.
- The login token is a base64-encoded JSON of the credentials, stored in the
  browser's localStorage. On revisiting the login page the token is validated
  and the user is redirected straight to the application.

NOTE: This is insecure (credentials are recoverable from the token) and is only
acceptable for a prototype / learning project. Swap `make_token`/`decode_token`
for signed JWTs + bcrypt hashing to harden later.
"""

import base64
import binascii
import json
import sqlite3

from fastapi import Header, HTTPException


def make_token(username: str, password: str) -> str:
    """Encode credentials into an opaque (base64) token string."""
    raw = json.dumps({"u": username, "p": password}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_token(token: str) -> tuple[str, str]:
    """Decode a token back into ``(username, password)``; raises on bad input."""
    try:
        data = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        return data["u"], data["p"]
    except (binascii.Error, ValueError, KeyError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed token") from exc


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict | None:
    """Return the full user info dict if credentials match, else ``None``."""
    row = conn.execute(
        "SELECT id, username, password, position_id FROM SYS_USER_DATA "
        "WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or row["password"] != password:
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
    try:
        username, password = decode_token(x_auth_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Ungültiger Token.")

    conn = get_connection()
    try:
        user = authenticate(conn, username, password)
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldedaten nicht mehr gültig.")
    return user


def require_admin(user: dict) -> None:
    """Raise 403 if the given user is not an Administrator."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Nur für Administratoren.")
