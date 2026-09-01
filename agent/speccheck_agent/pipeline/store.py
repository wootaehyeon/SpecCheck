"""로컬 SQLite 저장소 (M3).

telemetry는 기본적으로 로컬에 머무른다. 서버 업로드는 사용자가 명시적으로
선택했을 때만 일어나며, 저장소는 그 이전/이후 모두의 단일 기록처다.

시계열로 쌓이는 스냅샷은 나중에 예측 검증(구매 후 Scan vs 예측)의 재료가 된다.
그래서 스키마가 바뀌어도 **기존 DB를 지우지 않는다** - 과거 스냅샷이 사라지면
추세 분석(M9)의 근거가 통째로 사라지기 때문이다. 대신 ``schema_meta`` 에
버전을 기록하고 마이그레이션으로 올린다.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: 로컬 DB 스키마 버전. 스냅샷 계약(snapshot.SCHEMA_VERSION)과는 별개다.
DB_SCHEMA_VERSION = 2

_BASE_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS schema_meta (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    version    INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
"""

#: 버전 N -> N+1 로 올리는 문장들. 이미 데이터가 있는 DB에서도 안전해야 한다.
_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        # 시점 메모(--note). 예측 검증에서 "무엇을 바꾼 뒤의 스냅샷인가"의 기준선이 된다.
        "ALTER TABLE snapshots ADD COLUMN notes TEXT",
        # 같은 기기의 시계열 조회(M9 추세 분석의 전제).
        "CREATE INDEX IF NOT EXISTS idx_snapshots_device"
        " ON snapshots (device_id, collected_at DESC)",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            existing = _detect_version(conn)
            conn.executescript(_BASE_SCHEMA)
            _migrate(conn, existing)
            conn.commit()
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def schema_version(self) -> int:
        row = self.connect().execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
        return int(row["version"]) if row else 0

    # --- 쓰기 ------------------------------------------------------------

    def save(self, snapshot: dict[str, Any]) -> str:
        conn = self.connect()
        agent = snapshot.get("agent") or {}
        conn.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, device_id, collected_at, scan_mode, schema_version, agent_version, notes, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot["snapshot_id"],
                snapshot.get("device_id"),
                snapshot["collected_at"],
                snapshot["scan_mode"],
                snapshot["schema_version"],
                agent.get("version"),
                snapshot.get("notes"),
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
            (_now(), snapshot_id),
        )
        conn.commit()

    def prune(self, keep_last: int | None = None, older_than_days: int | None = None) -> int:
        """보관 정책 적용. 삭제된 스냅샷 수를 반환한다.

        두 조건은 **함께 만족해야** 삭제한다. 오래됐어도 최근 N개 안에 들면
        남긴다 - 몇 달 만에 켠 PC에서 시계열이 통째로 사라지는 것을 막기 위해서다.
        """
        conn = self.connect()
        conditions: list[str] = []
        params: list[Any] = []

        if older_than_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
            conditions.append("collected_at < ?")
            params.append(cutoff.isoformat(timespec="seconds"))

        if keep_last is not None:
            conditions.append(
                "snapshot_id NOT IN ("
                "SELECT snapshot_id FROM snapshots ORDER BY collected_at DESC LIMIT ?)"
            )
            params.append(keep_last)

        if not conditions:
            return 0

        cursor = conn.execute(
            "DELETE FROM snapshots WHERE " + " AND ".join(conditions), tuple(params)
        )
        conn.commit()
        return cursor.rowcount or 0

    # --- 읽기 ------------------------------------------------------------

    def list_recent(self, limit: int = 20, device_id: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        sql = (
            "SELECT snapshot_id, device_id, collected_at, scan_mode, agent_version, uploaded_at, notes "
            "FROM snapshots "
        )
        params: list[Any] = []
        if device_id:
            sql += "WHERE device_id = ? "
            params.append(device_id)
        sql += "ORDER BY collected_at DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def history(self, device_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """같은 기기의 스냅샷을 오래된 것부터 반환한다 (추세 분석용, M9의 전제)."""
        conn = self.connect()
        cursor = conn.execute(
            "SELECT payload FROM snapshots WHERE device_id = ? "
            "ORDER BY collected_at ASC LIMIT ?",
            (device_id, limit),
        )
        return [json.loads(row["payload"]) for row in cursor.fetchall()]

    def device_ids(self) -> list[str]:
        conn = self.connect()
        cursor = conn.execute(
            "SELECT device_id, COUNT(*) AS count FROM snapshots "
            "WHERE device_id IS NOT NULL GROUP BY device_id ORDER BY count DESC"
        )
        return [row["device_id"] for row in cursor.fetchall()]

    def count(self) -> int:
        return int(self.connect().execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"])

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        cursor = conn.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id LIKE ? ORDER BY collected_at DESC LIMIT 1",
            (snapshot_id + "%",),
        )
        row = cursor.fetchone()
        return json.loads(row["payload"]) if row else None

    def latest(self, device_id: str | None = None) -> dict[str, Any] | None:
        conn = self.connect()
        sql = "SELECT payload FROM snapshots "
        params: list[Any] = []
        if device_id:
            sql += "WHERE device_id = ? "
            params.append(device_id)
        sql += "ORDER BY collected_at DESC LIMIT 1"
        row = conn.execute(sql, tuple(params)).fetchone()
        return json.loads(row["payload"]) if row else None


# --- 마이그레이션 -------------------------------------------------------------


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    )
    return cursor.fetchone() is not None


def _detect_version(conn: sqlite3.Connection) -> int:
    """연결 시점의 DB 버전.

    ``schema_meta`` 가 없고 ``snapshots`` 만 있으면 버전 기록 이전에 만들어진
    DB(=1)다. 둘 다 없으면 새 DB(=0)이고 마이그레이션이 필요 없다.
    """
    if _table_exists(conn, "schema_meta"):
        row = conn.execute("SELECT version FROM schema_meta WHERE id = 1").fetchone()
        if row is not None:
            return int(row[0])
    return 1 if _table_exists(conn, "snapshots") else 0


def _migrate(conn: sqlite3.Connection, from_version: int) -> None:
    """기존 데이터를 유지한 채 스키마를 현재 버전까지 올린다."""
    if from_version == 0:
        # 새 DB는 _BASE_SCHEMA가 이미 최신 형태를 만들지만, 마이그레이션으로
        # 추가되는 컬럼/인덱스는 거기 없으므로 같은 경로를 태운다.
        from_version = 1

    version = from_version
    while version < DB_SCHEMA_VERSION:
        for statement in _MIGRATIONS.get(version, ()):
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                # 같은 컬럼을 두 번 추가하는 경우(중단된 마이그레이션 재시도)는 넘어간다.
                if "duplicate column" not in str(exc).lower():
                    raise
        version += 1

    conn.execute(
        "INSERT INTO schema_meta (id, version, applied_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET version = excluded.version, applied_at = excluded.applied_at",
        (DB_SCHEMA_VERSION, _now()),
    )
