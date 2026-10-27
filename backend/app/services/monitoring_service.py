"""기기별 읽기/전송 권한과 PostgreSQL 모니터링 이력. SQLite는 개발 테스트용."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import zlib
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import (Boolean, Column, Float, ForeignKey, Index, LargeBinary, MetaData,
                        String, Table, Text, create_engine, delete, select, update)
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import get_settings
from app.schemas.telemetry import TelemetrySnapshot

RETENTION_SECONDS = 7 * 24 * 3600
ACCESS_SECONDS = 90 * 24 * 3600
metadata = MetaData()
devices = Table("monitor_devices", metadata,
    Column("id", String(36), primary_key=True), Column("name", String(64), nullable=False),
    Column("read_hash", String(64), unique=True, nullable=False),
    Column("write_hash", String(64), unique=True), Column("security_allowed", Boolean, nullable=False),
    Column("consent_at", Float, nullable=False), Column("expires_at", Float, nullable=False))
samples = Table("monitor_samples", metadata,
    Column("device_id", String(36), ForeignKey("monitor_devices.id", ondelete="CASCADE"), primary_key=True),
    Column("snapshot_id", String(64), primary_key=True), Column("received_at", Float, nullable=False),
    Column("payload", LargeBinary, nullable=False), Column("metrics", Text, nullable=False),
    Column("diagnosis", Text, nullable=False))
Index("ix_monitor_samples_device_time", samples.c.device_id, samples.c.received_at)
events = Table("monitor_events", metadata,
    Column("device_id", String(36), ForeignKey("monitor_devices.id", ondelete="CASCADE"), primary_key=True),
    Column("event_key", String(64), primary_key=True), Column("received_at", Float, nullable=False),
    Column("occurred_at", String(40), nullable=False), Column("payload", Text, nullable=False))
Index("ix_monitor_events_device_time", events.c.device_id, events.c.occurred_at)


def configured() -> bool:
    cfg = get_settings()
    return cfg.monitoring_enabled and bool(cfg.monitoring_database_url)


@lru_cache(maxsize=4)
def database(raw_url: str):
    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url[len("postgres://"):]
    url = make_url(raw_url)
    if url.drivername in ("postgresql", "postgresql+psycopg"):
        url = url.set(drivername="postgresql+psycopg")
        if url.host not in ("localhost", "127.0.0.1", "::1"):
            if url.query.get("sslmode") in ("disable", "allow", "prefer"):
                raise ValueError("외부 PostgreSQL은 TLS 연결이 필요합니다.")
            if "sslmode" not in url.query:
                url = url.update_query_dict({"sslmode": "require"})
        engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2,
                               connect_args={"connect_timeout": 10}, hide_parameters=True)
    elif url.drivername == "sqlite":
        engine = create_engine(url, connect_args={"check_same_thread": False}, hide_parameters=True)
    else:
        raise ValueError("PostgreSQL 또는 개발용 SQLite URL이 필요합니다.")
    metadata.create_all(engine)
    return engine


def engine():
    return database(get_settings().monitoring_database_url)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pair(name: str, security_allowed: bool) -> dict:
    now = time.time()
    read_token = "sc_read_" + secrets.token_urlsafe(32)
    device = {"id": str(uuid4()), "name": name, "read_hash": token_hash(read_token),
              "security_allowed": security_allowed, "consent_at": now, "expires_at": now + ACCESS_SECONDS}
    with engine().begin() as conn:
        # 기한이 끝난 연결의 원본·이벤트·인증키를 함께 정리한다.
        expired = select(devices.c.id).where(devices.c.expires_at < now)
        conn.execute(delete(events).where(events.c.device_id.in_(expired)))
        conn.execute(delete(samples).where(samples.c.device_id.in_(expired)))
        conn.execute(delete(devices).where(devices.c.expires_at < now))
        conn.execute(devices.insert().values(**device))
    return {"device_id": device["id"], "name": name, "reader_token": read_token,
            "security_allowed": security_allowed, "expires_at": device["expires_at"]}


def authenticate(token: str, scope: str) -> dict | None:
    if len(token) > 256:
        return None
    column = devices.c.read_hash if scope == "read" else devices.c.write_hash
    with engine().connect() as conn:
        row = conn.execute(select(devices).where(column == token_hash(token),
                                                 devices.c.expires_at > time.time())).mappings().first()
    return dict(row) if row else None


def issue_writer(device: dict) -> str:
    token = "sc_write_" + secrets.token_urlsafe(32)
    with engine().begin() as conn:
        conn.execute(update(devices).where(devices.c.id == device["id"]).values(write_hash=token_hash(token)))
    return token


def _average(data: dict, *keys):
    value = data
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def metrics(snapshot: TelemetrySnapshot) -> dict:
    perf = snapshot.data("performance")
    return {"collected_at": snapshot.collected_at.isoformat(),
            "cpu_percent": _average(perf, "cpu", "usage_percent", "avg"),
            "memory_available_mb": _average(perf, "memory", "available_mb", "avg"),
            "memory_committed_percent": _average(perf, "memory", "committed_percent", "avg"),
            "disk_queue": _average(perf, "disk", "queue_length", "avg"),
            "temperature_c": _average(perf, "thermal", "max_c")}


def _insert(table):
    return pg_insert(table) if engine().dialect.name == "postgresql" else sqlite_insert(table)


def save(device: dict, snapshot: TelemetrySnapshot) -> float:
    from app.diagnosis import diagnose

    try:
        diagnosis = diagnose(snapshot).model_dump_json()
    except (TypeError, ValueError, KeyError, AttributeError, IndexError):
        diagnosis = json.dumps({"findings": [], "unavailable": True, "coverage": snapshot.coverage()})
    now = time.time()
    values = {"device_id": device["id"], "snapshot_id": snapshot.snapshot_id, "received_at": now,
              "payload": zlib.compress(snapshot.model_dump_json().encode("utf-8")),
              "metrics": json.dumps(metrics(snapshot)), "diagnosis": diagnosis}
    with engine().begin() as conn:
        # 동일 스냅샷 재전송은 원본의 수신 시각까지 보존한다. 다른 기기 ID와는 충돌하지 않는다.
        conn.execute(_insert(samples).values(**values).on_conflict_do_nothing())
        event_rows = []
        for event in snapshot.data("security").get("events", []):
            key = "|".join(str(event.get(k, "")) for k in ("record_id", "occurred_at", "event_id", "process_guid"))
            event_rows.append(dict(device_id=device["id"],
                event_key=hashlib.sha256(key.encode()).hexdigest(), received_at=now,
                occurred_at=event["occurred_at"], payload=json.dumps(event, ensure_ascii=False)))
        for start in range(0, len(event_rows), 200):
            conn.execute(_insert(events).values(event_rows[start:start + 200]).on_conflict_do_nothing())
        # 7일 보관. 조회도 동일 기한을 적용해 만료된 자료를 반환하지 않는다.
        conn.execute(delete(samples).where(samples.c.received_at < now - RETENTION_SECONDS))
        conn.execute(delete(events).where(events.c.received_at < now - RETENTION_SECONDS))
    return now


def latest(device: dict) -> dict:
    with engine().connect() as conn:
        row = conn.execute(select(samples).where(samples.c.device_id == device["id"],
            samples.c.received_at >= time.time() - RETENTION_SECONDS)
            .order_by(samples.c.received_at.desc()).limit(1)).mappings().first()
    result = {"device_id": device["id"], "name": device["name"],
              "security_allowed": device["security_allowed"], "snapshot": None}
    if row:
        result.update(snapshot=json.loads(zlib.decompress(row["payload"])), received_at=row["received_at"],
                      diagnosis=json.loads(row["diagnosis"]), metrics=json.loads(row["metrics"]))
    return result


def history(device: dict, limit: int) -> list[dict]:
    with engine().connect() as conn:
        rows = conn.execute(select(samples.c.received_at, samples.c.metrics)
            .where(samples.c.device_id == device["id"], samples.c.received_at >= time.time() - RETENTION_SECONDS)
            .order_by(samples.c.received_at.desc()).limit(limit)).all()
    return [{**json.loads(row.metrics), "received_at": row.received_at} for row in reversed(rows)]


def process_events(device: dict, limit: int) -> list[dict]:
    with engine().connect() as conn:
        rows = conn.execute(select(events.c.payload).where(events.c.device_id == device["id"],
            events.c.received_at >= time.time() - RETENTION_SECONDS)
            .order_by(events.c.occurred_at.desc()).limit(limit)).scalars().all()
    return [json.loads(row) for row in rows]


def disconnect(device: dict) -> None:
    with engine().begin() as conn:
        conn.execute(delete(events).where(events.c.device_id == device["id"]))
        conn.execute(delete(samples).where(samples.c.device_id == device["id"]))
        conn.execute(delete(devices).where(devices.c.id == device["id"]))
