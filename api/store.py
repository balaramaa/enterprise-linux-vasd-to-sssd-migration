"""Node and wave state for the control plane.

This reference implementation uses SQLite from the Python standard library so it
runs with no extra services. A production deployment can swap this module for a
PostgreSQL-backed store with the same functions.
"""
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

DB_PATH = os.environ.get("MIGRATION_DB", "migration_state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS waves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    limit_pattern TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS nodes (
    host TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    wave_id TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    wave_id TEXT,
    role TEXT,
    task TEXT,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA)


def create_wave(name, limit_pattern, dry_run, db_path=None):
    wave = {
        "id": str(uuid.uuid4()),
        "name": name,
        "limit_pattern": limit_pattern,
        "dry_run": bool(dry_run),
        "status": "DEFINED",
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
    }
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO waves VALUES (:id, :name, :limit_pattern, :dry_run, :status,"
            " :created_at, :started_at, :finished_at)",
            wave,
        )
    return wave


def get_wave(wave_id, db_path=None):
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM waves WHERE id = ?", (wave_id,)).fetchone()
    if row is None:
        return None
    wave = dict(row)
    wave["dry_run"] = bool(wave["dry_run"])
    return wave


def set_wave_status(wave_id, status, db_path=None):
    column = {"RUNNING": "started_at"}.get(status, "finished_at")
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "UPDATE waves SET status = ?, %s = ? WHERE id = ?" % column,
            (status, _now(), wave_id),
        )


def claim_wave(wave_id, db_path=None):
    """Move a wave from DEFINED to RUNNING. Returns False if it was not DEFINED."""
    with closing(_connect(db_path)) as conn, conn:
        cur = conn.execute(
            "UPDATE waves SET status = 'RUNNING', started_at = ?"
            " WHERE id = ? AND status = 'DEFINED'",
            (_now(), wave_id),
        )
        return cur.rowcount == 1


def record(host, state, role=None, task=None, status="ok", wave_id=None, db_path=None):
    """Set a node's state and attach one piece of evidence."""
    now = _now()
    with closing(_connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO nodes (host, state, wave_id, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(host) DO UPDATE SET state = excluded.state,"
            " wave_id = COALESCE(excluded.wave_id, nodes.wave_id),"
            " updated_at = excluded.updated_at",
            (host, state, wave_id, now),
        )
        conn.execute(
            "INSERT INTO evidence (host, wave_id, role, task, status, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (host, wave_id, role, task, status, now),
        )


def get_node(host, evidence_limit=50, db_path=None):
    with closing(_connect(db_path)) as conn:
        node = conn.execute("SELECT * FROM nodes WHERE host = ?", (host,)).fetchone()
        if node is None:
            return None
        rows = conn.execute(
            "SELECT role, task, status, wave_id, recorded_at FROM evidence"
            " WHERE host = ? ORDER BY id DESC LIMIT ?",
            (host, evidence_limit),
        ).fetchall()
    result = dict(node)
    result["evidence"] = [dict(r) for r in rows]
    return result
