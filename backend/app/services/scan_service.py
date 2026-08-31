"""스냅샷 저장소 (M3).

Agent가 업로드한 telemetry 스냅샷을 서버 측에 보관한다. 저장 단위는
원문 JSON이다 — 진단 규칙이 나중에 바뀌어도 과거 스냅샷을 다시 진단할 수
있어야 예측 검증 루프(구매 후 Scan vs 예측)가 성립하기 때문이다.

SQLite는 MVP 단계의 선택이다. 배포 시 PostgreSQL로 옮기더라도 이 모듈의
함수 시그니처는 그대로 두어 호출부가 흔들리지 않게 한다.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from app.core.config import get_settings
from app.schemas.telemetry import SnapshotSummary, TelemetrySnapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    device_id      TEXT,
    collected_at   TEXT NOT NULL,
    received_at    TEXT NOT NULL,
    scan_mode      TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    agent_version  TEXT,
    payload        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_device
    ON snapshots (device_id, collected_at DESC);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = get_settings().snapshot_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_snapshot(snapshot: TelemetrySnapshot) -> datetime:
    received_at = datetime.now(timezone.utc)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, device_id, collected_at, received_at, scan_mode, schema_version, agent_version, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot.snapshot_id,
                snapshot.device_id,
                snapshot.collected_at.isoformat(),
                received_at.isoformat(),
                snapshot.scan_mode,
                snapshot.schema_version,
                snapshot.agent.version,
                snapshot.model_dump_json(),
            ),
        )
    return received_at


def get_snapshot(snapshot_id: str) -> TelemetrySnapshot | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
    if row is None:
        return None
    return TelemetrySnapshot.model_validate_json(row["payload"])


def latest_snapshot(device_id: str) -> TelemetrySnapshot | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM snapshots WHERE device_id = ? ORDER BY collected_at DESC LIMIT 1",
            (device_id,),
        ).fetchone()
    if row is None:
        return None
    return TelemetrySnapshot.model_validate_json(row["payload"])


def list_snapshots(device_id: str | None = None, limit: int = 20) -> list[SnapshotSummary]:
    query = "SELECT payload FROM snapshots"
    params: tuple = ()
    if device_id:
        query += " WHERE device_id = ?"
        params = (device_id,)
    query += " ORDER BY collected_at DESC LIMIT ?"
    params += (limit,)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    summaries = []
    for row in rows:
        snapshot = TelemetrySnapshot.model_validate_json(row["payload"])
        summaries.append(
            SnapshotSummary(
                snapshot_id=snapshot.snapshot_id,
                device_id=snapshot.device_id,
                collected_at=snapshot.collected_at,
                scan_mode=snapshot.scan_mode,
                agent_version=snapshot.agent.version,
                coverage=snapshot.coverage(),
            )
        )
    return summaries
