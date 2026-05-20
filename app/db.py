from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.models import Shipment

_DB_PATH = Path(__file__).parent.parent / "data" / "shipments.db"
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shipments (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    return conn


def save(shipment: Shipment) -> None:
    payload = shipment.model_dump_json()
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO shipments (id, created_at, updated_at, status, data)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                status = excluded.status,
                data = excluded.data
            """,
            (
                shipment.id,
                shipment.created_at.isoformat(),
                shipment.updated_at.isoformat(),
                shipment.status.value,
                payload,
            ),
        )


def get(shipment_id: str) -> Optional[Shipment]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT data FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    if not row:
        return None
    return Shipment.model_validate(json.loads(row["data"]))


def list_all(limit: int = 100) -> list[Shipment]:
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT data FROM shipments ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [Shipment.model_validate(json.loads(r["data"])) for r in rows]


def delete(shipment_id: str) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
        return cur.rowcount > 0
