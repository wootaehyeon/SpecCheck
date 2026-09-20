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
CREATE INDEX IF NOT EXISTS idx_snapshots_device_time
    ON snapshots (device_id, collected_at DESC);

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
        with self.connect():
            return self._save(snapshot)

    def _save(self, snapshot: dict[str, Any]) -> str:
        conn = self.connect()
        agent = snapshot.get("agent") or {}
        conn.execute(
            "INSERT INTO snapshots "
            "(snapshot_id, device_id, collected_at, scan_mode, schema_version, agent_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(snapshot_id) DO UPDATE SET "
            "device_id=excluded.device_id, collected_at=excluded.collected_at, "
            "scan_mode=excluded.scan_mode, schema_version=excluded.schema_version, "
            "agent_version=excluded.agent_version, payload=excluded.payload",
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
        conn.execute('DELETE FROM collector_runs WHERE snapshot_id = ?', (snapshot['snapshot_id'],))
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

    def history(self, device_id: str, before: str, limit: int = 200) -> list[dict[str, Any]]:
        """Bounded, device-scoped actual measurements, returned oldest first."""
        if not 1 <= limit <= 1000:
            raise ValueError('history limit must be between 1 and 1000')
        rows = self.connect().execute(
            "SELECT payload FROM snapshots WHERE device_id = ? AND scan_mode = 'actual' "
            "AND julianday(collected_at) < julianday(?) ORDER BY julianday(collected_at) DESC LIMIT ?",
            (device_id, before, limit),
        ).fetchall()
        return [json.loads(row['payload']) for row in reversed(rows)]

    def prune(self, keep: int = 200) -> int:
        """Keep the newest N snapshots per device, cascading collector runs."""
        if keep < 1:
            raise ValueError('keep must be positive')
        conn = self.connect()
        with conn:
            cursor = conn.execute(
                'DELETE FROM snapshots WHERE snapshot_id IN ('
                'SELECT snapshot_id FROM (SELECT snapshot_id, ROW_NUMBER() OVER ('
                'PARTITION BY device_id ORDER BY julianday(collected_at) DESC, snapshot_id DESC) AS n '
                'FROM snapshots) WHERE n > ?)', (keep,))
        return cursor.rowcount
