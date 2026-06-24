"""Role endpoints: list and create roles (SYS_ROLES)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import get_current_user, require_admin
from ..db import get_connection

router = APIRouter(prefix="/api/roles", tags=["roles"])


class RoleRequest(BaseModel):
    bezeichnung: str


@router.get("")
def list_roles(user: dict = Depends(get_current_user)):
    """All roles defined in SYS_ROLES."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, bezeichnung FROM SYS_ROLES ORDER BY bezeichnung"
        ).fetchall()
        return {"roles": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def create_role(req: RoleRequest, user: dict = Depends(get_current_user)):
    """Create a role if it does not already exist (admin only)."""
    require_admin(user)
    name = req.bezeichnung.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Die Bezeichnung darf nicht leer sein.")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, bezeichnung FROM SYS_ROLES WHERE bezeichnung = ?", (name,)
        ).fetchone()
        if existing:
            return {"created": False, "role": dict(existing)}
        cur = conn.execute("INSERT INTO SYS_ROLES (bezeichnung) VALUES (?)", (name,))
        conn.commit()
        return {"created": True, "role": {"id": cur.lastrowid, "bezeichnung": name}}
    finally:
        conn.close()
