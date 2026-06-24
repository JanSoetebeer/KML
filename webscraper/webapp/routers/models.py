"""
AI model endpoints (admin only).

- Upload model files into the project's ``SYS_AI_MODELS`` folder and register
  them in SYS_AI_MODEL.
- Maintain the model<->role matrix in SYS_MODEL_ROLES.
- Delete a model: removes the file, its SYS_MODEL_ROLES rows, then the
  SYS_AI_MODEL row.
"""

import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import get_current_user, require_admin
from ..db import get_connection

router = APIRouter(prefix="/api/models", tags=["models"])

# <project>/SYS_AI_MODELS  (models.py -> routers -> webapp -> project root)
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "SYS_AI_MODELS"


def _ensure_dir() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


class MatrixToggleRequest(BaseModel):
    model_id: int
    role_id: int
    assigned: bool


@router.get("")
def list_models(user: dict = Depends(get_current_user)):
    """All uploaded AI models (SYS_AI_MODEL)."""
    require_admin(user)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, bezeichnung FROM SYS_AI_MODEL ORDER BY bezeichnung"
        ).fetchall()
        return {"models": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("")
def upload_model(
    file: UploadFile = File(...), user: dict = Depends(get_current_user)
):
    """Save an uploaded model file and register it in SYS_AI_MODEL."""
    require_admin(user)

    filename = Path(file.filename or "").name  # strip any path components
    if not filename:
        raise HTTPException(status_code=400, detail="Kein gültiger Dateiname.")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM SYS_AI_MODEL WHERE bezeichnung = ?", (filename,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409, detail=f'Ein Modell "{filename}" existiert bereits.'
            )

        _ensure_dir()
        target = MODELS_DIR / filename
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        try:
            cur = conn.execute(
                "INSERT INTO SYS_AI_MODEL (bezeichnung) VALUES (?)", (filename,)
            )
        except sqlite3.IntegrityError:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail="Modell existiert bereits.")
        conn.commit()
        return {"id": cur.lastrowid, "bezeichnung": filename}
    finally:
        file.file.close()
        conn.close()


@router.get("/matrix")
def get_matrix(user: dict = Depends(get_current_user)):
    """Return models, roles and current assignments for the matrix view."""
    require_admin(user)
    conn = get_connection()
    try:
        models = conn.execute(
            "SELECT id, bezeichnung FROM SYS_AI_MODEL ORDER BY bezeichnung"
        ).fetchall()
        roles = conn.execute(
            "SELECT id, bezeichnung FROM SYS_ROLES ORDER BY bezeichnung"
        ).fetchall()
        links = conn.execute(
            "SELECT model_id, role_id FROM SYS_MODEL_ROLES"
        ).fetchall()
        return {
            "models": [dict(m) for m in models],
            "roles": [dict(r) for r in roles],
            "assignments": [[l["model_id"], l["role_id"]] for l in links],
        }
    finally:
        conn.close()


@router.post("/matrix")
def toggle_matrix(req: MatrixToggleRequest, user: dict = Depends(get_current_user)):
    """Assign or unassign a role to/from a model in SYS_MODEL_ROLES."""
    require_admin(user)
    conn = get_connection()
    try:
        if req.assigned:
            if not conn.execute(
                "SELECT 1 FROM SYS_AI_MODEL WHERE id = ?", (req.model_id,)
            ).fetchone():
                raise HTTPException(status_code=404, detail="Modell nicht gefunden.")
            if not conn.execute(
                "SELECT 1 FROM SYS_ROLES WHERE id = ?", (req.role_id,)
            ).fetchone():
                raise HTTPException(status_code=404, detail="Rolle nicht gefunden.")
            conn.execute(
                "INSERT OR IGNORE INTO SYS_MODEL_ROLES (model_id, role_id) "
                "VALUES (?, ?)",
                (req.model_id, req.role_id),
            )
        else:
            conn.execute(
                "DELETE FROM SYS_MODEL_ROLES WHERE model_id = ? AND role_id = ?",
                (req.model_id, req.role_id),
            )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.delete("/{model_id}")
def delete_model(model_id: int, user: dict = Depends(get_current_user)):
    """Delete a model file and its DB rows (SYS_MODEL_ROLES then SYS_AI_MODEL)."""
    require_admin(user)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT bezeichnung FROM SYS_AI_MODEL WHERE id = ?", (model_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Modell nicht gefunden.")

        # 1) remove the file
        file_path = MODELS_DIR / Path(row["bezeichnung"]).name
        file_path.unlink(missing_ok=True)

        # 2) remove matrix links, then 3) the model row
        conn.execute("DELETE FROM SYS_MODEL_ROLES WHERE model_id = ?", (model_id,))
        conn.execute("DELETE FROM SYS_AI_MODEL WHERE id = ?", (model_id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()
