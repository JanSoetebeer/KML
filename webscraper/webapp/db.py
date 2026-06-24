"""
SQLite database layer for the admin web application.

Holds the relational schema (positions, roles, users, the N:M user-roles join
table, AI models and the model-roles matrix), connection helpers, and the
initial seed data (admin / 0000 with the Administrator position and the
Modulhandbuch role).

The database file lives at ``<project>/app.db`` and is created automatically on
first start via :func:`init_db`.
"""

import os
import sqlite3
from pathlib import Path

# app.db sits at the project root (next to run.py).
_DB_PATH = Path(os.getenv("APP_DB_PATH", str(Path(__file__).resolve().parent.parent / "app.db")))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS SYS_POSITION (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS SYS_ROLES (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS SYS_USER_DATA (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,
    password     TEXT NOT NULL,
    position_id  INTEGER NOT NULL,
    FOREIGN KEY (position_id) REFERENCES SYS_POSITION (id)
);

CREATE TABLE IF NOT EXISTS SYS_USER_ROLES (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    role_id   INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES SYS_USER_DATA (id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES SYS_ROLES (id) ON DELETE CASCADE,
    UNIQUE (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS SYS_AI_MODEL (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bezeichnung  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS SYS_MODEL_ROLES (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id  INTEGER NOT NULL,
    role_id   INTEGER NOT NULL,
    FOREIGN KEY (model_id) REFERENCES SYS_AI_MODEL (id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES SYS_ROLES (id) ON DELETE CASCADE,
    UNIQUE (model_id, role_id)
);
"""


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with row access by name and FK enforcement."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the schema (if missing) and insert the seed data (idempotent)."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Positions: Administrator + User
    for bez in ("Administrator", "User"):
        cur.execute(
            "INSERT OR IGNORE INTO SYS_POSITION (bezeichnung) VALUES (?)", (bez,)
        )

    # Role: Modulhandbuch
    cur.execute(
        "INSERT OR IGNORE INTO SYS_ROLES (bezeichnung) VALUES (?)", ("Modulhandbuch",)
    )

    # Default admin user (admin / 0000) with the Administrator position
    admin_pos_id = cur.execute(
        "SELECT id FROM SYS_POSITION WHERE bezeichnung = 'Administrator'"
    ).fetchone()["id"]
    cur.execute(
        "INSERT OR IGNORE INTO SYS_USER_DATA (username, password, position_id) "
        "VALUES (?, ?, ?)",
        ("admin", "0000", admin_pos_id),
    )

    # admin -> Modulhandbuch role
    admin_id = cur.execute(
        "SELECT id FROM SYS_USER_DATA WHERE username = 'admin'"
    ).fetchone()["id"]
    mh_id = cur.execute(
        "SELECT id FROM SYS_ROLES WHERE bezeichnung = 'Modulhandbuch'"
    ).fetchone()["id"]
    cur.execute(
        "INSERT OR IGNORE INTO SYS_USER_ROLES (user_id, role_id) VALUES (?, ?)",
        (admin_id, mh_id),
    )
