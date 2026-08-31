"""로컬 SQLite 저장소 (M3).

telemetry는 기본적으로 로컬에 머무른다. 서버 업로드는 사용자가 명시적으로
선택했을 때만 일어나며, 저장소는 그 이전/이후 모두의 단일 기록처다.

시계열로 쌓이는 스냅샷은 나중에 예측 검증(구매 후 Scan vs 예측)의 재료가 된다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    device_id      TEXT,
    collected_at   TEXT NOT NULL,
    scan_mode      TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    agent_version  TEXT,
    uploaded_at    TEXT,
    payload        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_collected_at
    ON snapshots (collected_at DESC);

CREATE TABLE IF NOT EXISTS collector_runs (
    snapshot_id TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL,
    milestone   TEXT,
    duration_ms REAL,
    error       TEXT,
    PRIMARY KEY (snapshot_id, name),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots (snapshot_id) ON DELETE CASCADE
);
"""


class SnapshotStore:
    """스냅샷 영속화. 컨텍스트 매니저로 사용한다."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> SnapshotStore:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- 쓰기 ------------------------------------------------------------

    def save(self, snapshot: dict[str, Any]) -> str:
        conn = self.connect()
        agent = snapshot.get("agent") or {}
        conn.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, device_id, collected_at, scan_mode, schema_version, agent_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot["snapshot_id"],
                snapshot.get("device_id"),
                snapshot["collected_at"],
                snapshot["scan_mode"],
                snapshot["schema_version"],
                agent.get("version"),
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        rows = [
            (
                snapshot["snapshot_id"],
                name,
                section.get("status"),
                section.get("milestone"),
                section.get("duration_ms"),
                section.get("error"),
            )
            for name, section in (snapshot.get("sections") or {}).items()
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO collector_runs "
            "(snapshot_id, name, status, milestone, duration_ms, error) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return snapshot["snapshot_id"]

    def mark_uploaded(self, snapshot_id: str) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE snapshots SET uploaded_at = ? WHERE snapshot_id = ?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), snapshot_id),
        )
        conn.commit()

    # --- 읽기 ------------------------------------------------------------

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self.connect()
        cursor = conn.execute(
            "SELECT snapshot_id, collected_at, scan_mode, agent_version, uploaded_at "
            "FROM snapshots ORDER BY collected_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        cursor = conn.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id LIKE ? ORDER BY collected_at DESC LIMIT 1",
            (snapshot_id + "%",),
        )
        row = cursor.fetchone()
        return json.loads(row["payload"]) if row else None

    def latest(self) -> dict[str, Any] | None:
        conn = self.connect()
        cursor = conn.execute(
            "SELECT payload FROM snapshots ORDER BY collected_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return json.loads(row["payload"]) if row else None
