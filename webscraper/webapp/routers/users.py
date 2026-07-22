"""
User management endpoints (SYS_USER_DATA + SYS_USER_ROLES).

- Admin-only: list users, create users, assign/remove roles.
- Any authenticated user: change own password.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import (
    get_current_user,
    hash_password,
    make_token,
    require_admin,
    verify_password,
)
from ..db import get_connection

router = APIRouter(prefix="/api/users", tags=["users"])

MIN_USERNAME_LEN = 4
MIN_PASSWORD_LEN = 8


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    role_id: int | None = None


class RoleAssignRequest(BaseModel):
    role_id: int


class PasswordChangeRequest(BaseModel):
    current: str
    new: str
    confirm: str


@router.get("")
def list_users(user: dict = Depends(get_current_user)):
    """List all users with their position (admin only)."""
    require_admin(user)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT u.id, u.username, p.bezeichnung AS position "
            "FROM SYS_USER_DATA u JOIN SYS_POSITION p ON p.id = u.position_id "
            "ORDER BY u.username"
        ).fetchall()
        return {
            "users": [
                {
                    "id": r["id"],
                    "username": r["username"],
                    "position": r["position"],
                    "is_admin": r["position"] == "Administrator",
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@router.post("")
def create_user(req: CreateUserRequest, user: dict = Depends(get_current_user)):
    """Create a new user (admin only) with length validation."""
    require_admin(user)

    errors = []
    if len(req.username.strip()) < MIN_USERNAME_LEN:
        errors.append(f"Der Benutzername muss mindestens {MIN_USERNAME_LEN} Zeichen lang sein.")
    if len(req.password) < MIN_PASSWORD_LEN:
        errors.append(f"Das Passwort muss mindestens {MIN_PASSWORD_LEN} Zeichen lang sein.")
    if errors:
        raise HTTPException(status_code=400, detail=" ".join(errors))

    username = req.username.strip()
    position_name = "Administrator" if req.is_admin else "User"

    conn = get_connection()
    try:
        pos = conn.execute(
            "SELECT id FROM SYS_POSITION WHERE bezeichnung = ?", (position_name,)
        ).fetchone()
        if pos is None:
            raise HTTPException(status_code=500, detail="Position nicht gefunden.")

        try:
            cur = conn.execute(
                "INSERT INTO SYS_USER_DATA (username, password, position_id) "
                "VALUES (?, ?, ?)",
                (username, hash_password(req.password), pos["id"]),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Benutzername existiert bereits.")

        new_id = cur.lastrowid
        if req.role_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO SYS_USER_ROLES (user_id, role_id) VALUES (?, ?)",
                (new_id, req.role_id),
            )
        conn.commit()
        return {
            "id": new_id,
            "username": username,
            "position": position_name,
            "is_admin": req.is_admin,
        }
    finally:
        conn.close()


@router.get("/{user_id}/roles")
def get_user_roles(user_id: int, user: dict = Depends(get_current_user)):
    """Roles assigned to a specific user (admin only)."""
    require_admin(user)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT r.id, r.bezeichnung FROM SYS_ROLES r "
            "JOIN SYS_USER_ROLES ur ON ur.role_id = r.id "
            "WHERE ur.user_id = ? ORDER BY r.bezeichnung",
            (user_id,),
        ).fetchall()
        return {"roles": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/{user_id}/roles")
def add_user_role(
    user_id: int, req: RoleAssignRequest, user: dict = Depends(get_current_user)
):
    """Assign a role to a user (admin only)."""
    require_admin(user)
    conn = get_connection()
    try:
        if not conn.execute(
            "SELECT 1 FROM SYS_USER_DATA WHERE id = ?", (user_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden.")
        if not conn.execute(
            "SELECT 1 FROM SYS_ROLES WHERE id = ?", (req.role_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Rolle nicht gefunden.")
        conn.execute(
            "INSERT OR IGNORE INTO SYS_USER_ROLES (user_id, role_id) VALUES (?, ?)",
            (user_id, req.role_id),
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.delete("/{user_id}/roles/{role_id}")
def remove_user_role(
    user_id: int, role_id: int, user: dict = Depends(get_current_user)
):
    """Remove a role from a user (admin only)."""
    require_admin(user)
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM SYS_USER_ROLES WHERE user_id = ? AND role_id = ?",
            (user_id, role_id),
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.post("/me/password")
def change_password(
    req: PasswordChangeRequest, user: dict = Depends(get_current_user)
):
    """
    Change the current user's own password.

    The new password must match in both fields (case-sensitive). On success a
    fresh token is returned (the old token embedded the previous password).
    """
    if req.new != req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Das neue Passwort stimmt in beiden Feldern nicht überein.",
        )

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT password FROM SYS_USER_DATA WHERE id = ?", (user["id"],)
        ).fetchone()
        if row is None or not verify_password(req.current, row["password"]):
            raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist falsch.")
        conn.execute(
            "UPDATE SYS_USER_DATA SET password = ? WHERE id = ?",
            (hash_password(req.new), user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "ok", "token": make_token(user["id"], user["username"])}
