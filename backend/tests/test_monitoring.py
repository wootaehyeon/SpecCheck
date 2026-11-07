"""기기 권한 분리, 영구 이력, 수집 동의, 키 폐기 경로를 실제 DB로 검증한다."""
import io
import json
import os
import time
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.main import create_app
from app.services import monitoring_service as service
from app.api.routes import monitoring

DATABASES = ["sqlite"] + (["postgres"] if os.environ.get("MONITOR_TEST_DATABASE_URL") else [])


@pytest.fixture(params=DATABASES)
def client(request, tmp_path, monkeypatch):
    cfg = get_settings()
    url = os.environ["MONITOR_TEST_DATABASE_URL"] if request.param == "postgres" else "sqlite:///" + (tmp_path / "monitor.db").as_posix()
    monkeypatch.setattr(cfg, "monitoring_enabled", True)
    monkeypatch.setattr(cfg, "monitoring_database_url", url)
    monkeypatch.setattr(cfg, "telemetry_api_enabled", False)
    monkeypatch.setattr(cfg, "serve_frontend", True)
    monitoring._pair_attempts.clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    service.database(url).dispose()
    service.database.cache_clear()


def connect(client, *, security=False):
    response = client.post("/api/monitor/pair", json={"name": "테스트 PC", "accepted": True, "security_accepted": security})
    assert response.status_code == 201
    connection = response.json()
    owner = {"Authorization": "Bearer " + connection["reader_token"]}
    writer = client.post("/api/monitor/agent-config", headers=owner)
    assert writer.status_code == 200
    return connection, owner, {"Authorization": "Bearer " + writer.json()["writer_token"]}


def payload(device, snapshot_id="same-snapshot-id", *, security=False):
    stamp = datetime.now(timezone.utc).isoformat()
    result = {"schema_version": "1.2.0", "snapshot_id": snapshot_id, "device_id": device,
              "collected_at": stamp, "scan_mode": "actual", "agent": {"version": "0.1.0", "os": "Windows"},
              "sections": {"hardware": {"status": "ok", "data": {"cpu": [{"name": "Synthetic CPU"}],
                    "gpu": [], "memory": {"total_gb": 32}, "storage": [], "motherboard": {}}},
                  "performance": {"status": "ok", "data": {"cpu": {"usage_percent": {"avg": 48}},
                    "memory": {"available_mb": {"avg": 8192}, "committed_percent": {"avg": 51}},
                    "disk": {"queue_length": {"avg": 0.2}}, "thermal": {"max_c": None}}}}}
    if security:
        result["sections"]["security"] = {"status": "ok", "data": {
            "consent": {"version": "sysmon-minimal-v1", "granted_at": stamp},
            "window_start": stamp, "window_end": stamp,
            "truncated": False, "log_gap": False, "log_reset": False, "log_oldest_at": stamp,
            "events": [{"event_id": 1, "record_id": 10, "occurred_at": stamp,
                        "process_guid": "guid-1", "process_id": 42, "image": "synthetic.exe"}]}}
    return result


def test_read_and_upload_keys_have_different_permissions(client):
    connection, owner, sender = connect(client)
    assert client.get("/api/monitor/latest").status_code == 401
    assert client.get("/api/monitor/latest", headers=sender).status_code == 401
    assert client.post("/api/monitor/agent-config", headers=sender).status_code == 401
    assert client.post("/api/monitor/snapshots", json=payload(connection["device_id"]), headers=owner).status_code == 401
    assert client.get("/api/monitor/latest", headers=owner).json()["snapshot"] is None
    assert client.get("/api/scan/snapshots", headers=owner).status_code == 404
    assert client.get("/api/diagnosis/rules", headers=owner).status_code == 404


def test_two_owners_are_isolated_even_with_same_snapshot_id(client):
    a, owner_a, sender_a = connect(client)
    b, owner_b, sender_b = connect(client)
    for device, sender in [(a, sender_a), (b, sender_b)]:
        assert client.post("/api/monitor/snapshots", json=payload(device["device_id"]), headers=sender).status_code == 201
    attack = client.post("/api/monitor/snapshots", json=payload(b["device_id"]), headers=sender_a)
    assert attack.status_code == 403
    for device, owner, other in [(a, owner_a, b), (b, owner_b, a)]:
        response = client.get("/api/monitor/latest?device_id=" + other["device_id"], headers=owner)
        assert response.json()["snapshot"]["device_id"] == device["device_id"]
        assert len(client.get("/api/monitor/history", headers=owner).json()) == 1
        assert response.headers["cache-control"] == "no-store"


def test_history_and_connection_survive_recreated_engine(client):
    device, owner, sender = connect(client)
    body = payload(device["device_id"])
    assert client.post("/api/monitor/snapshots", json=body, headers=sender).status_code == 201
    first = client.get("/api/monitor/latest", headers=owner).json()
    assert first["metrics"]["cpu_percent"] == 48
    assert first["metrics"]["temperature_c"] is None
    assert "decision" in first["diagnosis"]
    service.engine().dispose()
    service.database.cache_clear()
    with TestClient(create_app()) as restarted:
        after = restarted.get("/api/monitor/latest", headers=owner).json()
        assert after["snapshot"] == first["snapshot"]
        assert after["received_at"] == first["received_at"]
        assert restarted.post("/api/monitor/snapshots", json=body, headers=sender).status_code == 201
        assert len(restarted.get("/api/monitor/history", headers=owner).json()) == 1


def test_process_consent_and_event_deduplication(client):
    device, owner, sender = connect(client)
    assert client.post("/api/monitor/snapshots", json=payload(device["device_id"], security=True), headers=sender).status_code == 403
    other, owner2, sender2 = connect(client, security=True)
    body = payload(other["device_id"], security=True)
    assert client.post("/api/monitor/snapshots", json=body, headers=sender2).status_code == 201
    body["snapshot_id"] = "next-frame"
    assert client.post("/api/monitor/snapshots", json=body, headers=sender2).status_code == 201
    assert len(client.get("/api/monitor/process-events", headers=owner2).json()) == 1
    assert client.get("/api/monitor/process-events", headers=owner).json() == []
    body["sections"]["security"]["data"]["events"][0]["command_line"] = "private command"
    assert client.post("/api/monitor/snapshots", json=body, headers=sender2).status_code == 422


def test_rotated_writer_and_disconnect_revoke_access(client):
    device, owner, old_writer = connect(client)
    response = client.post("/api/monitor/agent-config", headers=owner)
    new_writer = {"Authorization": "Bearer " + response.json()["writer_token"]}
    assert client.post("/api/monitor/snapshots", json=payload(device["device_id"]), headers=old_writer).status_code == 401
    assert client.post("/api/monitor/snapshots", json=payload(device["device_id"]), headers=new_writer).status_code == 201
    assert client.delete("/api/monitor/connection", headers=owner).status_code == 204
    assert client.get("/api/monitor/latest", headers=owner).status_code == 401
    assert client.post("/api/monitor/snapshots", json=payload(device["device_id"]), headers=new_writer).status_code == 401
    with service.engine().connect() as conn:
        assert conn.execute(select(service.samples).where(service.samples.c.device_id == device["device_id"])).first() is None
        assert conn.execute(select(service.events).where(service.events.c.device_id == device["device_id"])).first() is None


def test_existing_owner_can_enable_and_disable_sysmon_without_losing_history(client):
    device, owner, sender = connect(client)
    basic = payload(device["device_id"], 'before-sysmon')
    assert client.post('/api/monitor/snapshots', json=basic, headers=sender).status_code == 201
    assert client.put('/api/monitor/security-consent', json={'accepted': True}).status_code == 401
    assert client.put('/api/monitor/security-consent', json={'accepted': True}, headers=sender).status_code == 401
    assert client.put('/api/monitor/security-consent', json={'accepted': 'false'}, headers=owner).status_code == 422
    enabled = client.put('/api/monitor/security-consent', json={'accepted': True}, headers=owner)
    assert enabled.status_code == 200
    assert enabled.json()['security_allowed'] is True
    assert client.get('/api/monitor/latest', headers=owner).json()['security_allowed'] is True
    config = client.post('/api/monitor/agent-config', headers=owner).json()
    assert config['device_id'] == device['device_id'] and config['security_consent'] is True
    new_sender = {'Authorization': 'Bearer ' + config['writer_token']}
    secure = payload(device['device_id'], 'with-sysmon', security=True)
    assert client.post('/api/monitor/snapshots', json=secure, headers=new_sender).status_code == 201
    assert len(client.get('/api/monitor/history', headers=owner).json()) == 2
    assert client.put('/api/monitor/security-consent', json={'accepted': False}, headers=owner).status_code == 200
    assert client.post('/api/monitor/snapshots', json=secure, headers=new_sender).status_code == 403
    assert len(client.get('/api/monitor/process-events', headers=owner).json()) == 1
    assert client.post('/api/monitor/snapshots', json=basic, headers=new_sender).status_code == 201


def test_expired_records_are_hidden_and_cleaned(client):
    device, owner, sender = connect(client)
    client.post("/api/monitor/snapshots", json=payload(device["device_id"], "old"), headers=sender)
    with service.engine().begin() as conn:
        conn.execute(update(service.samples).where(service.samples.c.device_id == device["device_id"])
                     .values(received_at=time.time() - 8 * 86400))
    assert client.get("/api/monitor/latest", headers=owner).json()["snapshot"] is None
    assert client.get("/api/monitor/history", headers=owner).json() == []
    client.post("/api/monitor/snapshots", json=payload(device["device_id"], "new"), headers=sender)
    assert len(client.get("/api/monitor/history", headers=owner).json()) == 1
    with service.engine().begin() as conn:
        conn.execute(update(service.devices).where(service.devices.c.id == device["device_id"]).values(expires_at=0))
    assert client.get("/api/monitor/latest", headers=owner).status_code == 401


def test_bad_input_limits_and_keys_are_not_stored_as_plaintext(client):
    device, owner, sender = connect(client)
    assert client.post("/api/monitor/pair", json={"accepted": False}).status_code == 422
    assert client.post("/api/monitor/snapshots", headers=sender, content=b"x" * (1024 * 1024 + 1)).status_code == 413
    assert client.post("/api/monitor/snapshots", headers=sender, content=b'{"bad": NaN}').status_code == 422
    assert client.get("/api/monitor/history?limit=99999", headers=owner).status_code == 422
    with service.engine().connect() as conn:
        row = conn.execute(select(service.devices).where(service.devices.c.id == device["device_id"])).mappings().one()
    assert row["read_hash"] != device["reader_token"]
    assert len(row["read_hash"]) == 64 and len(row["write_hash"]) == 64


def test_agent_download_contains_only_distributable_source(client):
    response = client.get("/api/monitor/agent.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert "SpecCheck-Agent/Start-SpecCheck.cmd" in names
    assert "SpecCheck-Agent/speccheck_agent/watch.py" in names
    assert not any(name.endswith((".db", ".env", ".json")) for name in names)
    page = client.get("/monitor.html")
    assert page.status_code == 200
    assert "script-src 'self'" in page.headers["content-security-policy"]


def test_missing_database_fails_closed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "monitoring_database_url", "")
    assert client.get("/api/monitor/status").json()["enabled"] is False
    assert client.post("/api/monitor/pair", json={"accepted": True}).status_code == 503
    assert client.get("/api/monitor/latest").status_code == 503
