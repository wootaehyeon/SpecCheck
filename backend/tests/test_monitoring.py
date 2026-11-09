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
    monitoring._redeem_attempts.clear()
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


def test_agent_assistance_is_writer_scoped_and_does_not_expose_raw_telemetry(client):
    device, owner, sender = connect(client)
    assert client.get("/api/monitor/assistance").status_code == 401
    assert client.get("/api/monitor/assistance", headers=owner).status_code == 401
    assert client.get("/api/monitor/assistance", headers=sender).status_code == 404
    body = payload(device["device_id"], "agent-scan")
    body["sections"]["hardware"]["data"]["motherboard"] = {"product": "B550"}
    body["sections"]["performance"]["data"]["memory"] = {
        "available_mb": {"avg": 780}, "committed_percent": {"avg": 96}}
    assert client.post("/api/monitor/snapshots", headers=sender, json=body).status_code == 201
    response = client.get("/api/monitor/assistance?snapshot_id=agent-scan", headers=sender)
    result = response.json()
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert result["device_id"] == device["device_id"] and result["snapshot_id"] == "agent-scan"
    assert result["decision"]["action"] == "purchase" and result["recommendations"]
    assert "snapshot" not in result and "sections" not in result
    assert "reader_token" not in response.text and "writer_token" not in response.text
    assert "evidence" not in result["findings"][0]
    # The Agent receives only its bounded diagnosis, never the browser's full read scope.
    assert client.get("/api/monitor/latest", headers=sender).status_code == 401
    other, _, other_sender = connect(client)
    assert client.get("/api/monitor/assistance?snapshot_id=agent-scan", headers=other_sender).status_code == 404
    assert client.get("/api/monitor/assistance?snapshot_id=wrong", headers=sender).status_code == 404
    assert client.delete("/api/monitor/connection", headers=owner).status_code == 204
    assert client.get("/api/monitor/assistance", headers=sender).status_code == 401


def test_agent_assistance_excludes_expired_measurements_and_preserves_diagnosis_failure(client):
    device, _, sender = connect(client)
    assert client.post("/api/monitor/snapshots", headers=sender, json=payload(device["device_id"])).status_code == 201
    with service.engine().begin() as conn:
        conn.execute(update(service.samples).where(service.samples.c.device_id == device["device_id"])
                     .values(diagnosis=json.dumps({"unavailable": True, "findings": []})))
    result = client.get("/api/monitor/assistance", headers=sender).json()
    assert result["unavailable"] is True and result["decision"] is None
    with service.engine().begin() as conn:
        conn.execute(update(service.samples).where(service.samples.c.device_id == device["device_id"])
                     .values(received_at=time.time() - 8 * 86400))
    assert client.get("/api/monitor/assistance", headers=sender).status_code == 404


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


def test_monitor_diagnosis_includes_matching_purchase_candidates_and_clears_after_recovery(client):
    device, owner, sender = connect(client)
    body = payload(device["device_id"], "memory-pressure")
    body["sections"]["hardware"]["data"]["memory"] = {
        "total_gb": 8, "modules": [{"rated_speed_mhz": 3200}], "empty_slot_count": 2,
    }
    body["sections"]["performance"]["data"]["memory"] = {
        "available_mb": {"avg": 500}, "committed_percent": {"avg": 96},
    }
    assert client.post("/api/monitor/snapshots", json=body, headers=sender).status_code == 201
    latest = client.get("/api/monitor/latest", headers=owner).json()
    recommendations = latest["diagnosis"]["recommendations"]
    assert recommendations
    assert "PF-MEM-001" in recommendations[0]["findingIds"]
    preferred = next(item for item in recommendations[0]["candidates"] if item["recommended"])
    assert preferred["parts"][0]["searchQuery"]
    assert "DDR4" in preferred["parts"][0]["specifications"]
    assert all(part["category"] == "memory" for part in preferred["parts"])
    service.engine().dispose()
    service.database.cache_clear()
    assert client.get("/api/monitor/latest", headers=owner).json()["diagnosis"]["recommendations"] == recommendations
    recovered = payload(device["device_id"], "recovered")
    assert client.post("/api/monitor/snapshots", json=recovered, headers=sender).status_code == 201
    assert client.get("/api/monitor/latest", headers=owner).json()["diagnosis"]["recommendations"] == []


def test_catalog_failure_keeps_monitor_diagnosis(client, monkeypatch):
    from app.diagnosis import recommendations

    def unavailable(*args):
        raise ValueError("catalog unavailable")

    monkeypatch.setattr(recommendations, "build_recommendations", unavailable)
    device, owner, sender = connect(client)
    body = payload(device["device_id"])
    body["sections"]["hardware"]["data"]["memory"]["total_gb"] = 4
    assert client.post("/api/monitor/snapshots", json=body, headers=sender).status_code == 201
    diagnosis = client.get("/api/monitor/latest", headers=owner).json()["diagnosis"]
    assert diagnosis["findings"]
    assert diagnosis["recommendations"] == []
    assert diagnosis["recommendations_unavailable"] is True


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


def test_code_is_authenticated_single_use_and_only_grants_upload_access(client):
    device, owner, old_writer = connect(client)
    assert client.post('/api/monitor/pairing-code').status_code == 401
    assert client.post('/api/monitor/pairing-code', headers=old_writer).status_code == 401
    issued = client.post('/api/monitor/pairing-code', headers=owner).json()
    assert len(issued['code']) == 9 and issued['code'][4] == '-'
    assert 590 < issued['expires_at'] - time.time() <= 600
    with service.engine().connect() as conn:
        stored = conn.execute(select(service.pairing_codes)).mappings().one()
    assert stored['code_hash'] == service.token_hash(issued['code'].replace('-', ''))
    assert issued['code'] not in str(stored)
    assert client.get('/api/monitor/latest', headers=owner).json()['pairing_state'] == 'pending'
    # Showing/reissuing a code must not stop an Agent that is already running.
    assert client.post('/api/monitor/snapshots', json=payload(device['device_id']), headers=old_writer).status_code == 201
    assert client.post('/api/monitor/redeem', json={'code': issued['code'], 'accepted': False}).status_code == 422
    result = client.post('/api/monitor/redeem', json={'code': issued['code'].lower(), 'accepted': True})
    assert result.status_code == 200
    config = result.json()
    assert config['device_id'] == device['device_id']
    assert 'reader_token' not in config and 'read_hash' not in config
    new_writer = {'Authorization': 'Bearer ' + config['writer_token']}
    assert client.get('/api/monitor/latest', headers=new_writer).status_code == 401
    assert client.post('/api/monitor/redeem', json={'code': issued['code'], 'accepted': True}).status_code == 400
    assert client.post('/api/monitor/snapshots', json=payload(device['device_id']), headers=old_writer).status_code == 401
    assert client.post('/api/monitor/snapshots', json=payload(device['device_id']), headers=new_writer).status_code == 201
    assert client.get('/api/monitor/latest', headers=owner).json()['pairing_state'] == 'connected'


def test_reissued_expired_and_disconnected_codes_cannot_connect(client):
    device, owner, sender = connect(client)
    first = client.post('/api/monitor/pairing-code', headers=owner).json()['code']
    second = client.post('/api/monitor/pairing-code', headers=owner).json()['code']
    assert client.post('/api/monitor/redeem', json={'code': first, 'accepted': True}).status_code == 400
    service.engine().dispose()
    service.database.cache_clear()
    # Codes survive restarts and remain scoped to their owning device.
    config = client.post('/api/monitor/redeem', json={'code': second, 'accepted': True}).json()
    assert config['device_id'] == device['device_id']
    expired = client.post('/api/monitor/pairing-code', headers=owner).json()['code']
    with service.engine().begin() as conn:
        conn.execute(update(service.pairing_codes).where(service.pairing_codes.c.device_id == device['device_id']).values(expires_at=0))
    assert client.get('/api/monitor/latest', headers=owner).json()['pairing_state'] == 'expired'
    assert client.post('/api/monitor/redeem', json={'code': expired, 'accepted': True}).status_code == 400
    removed = client.post('/api/monitor/pairing-code', headers=owner).json()['code']
    assert client.delete('/api/monitor/connection', headers=owner).status_code == 204
    assert client.post('/api/monitor/redeem', json={'code': removed, 'accepted': True}).status_code == 400


def test_parallel_redemption_has_exactly_one_winner(client):
    from concurrent.futures import ThreadPoolExecutor
    _, owner, _ = connect(client)
    code = client.post('/api/monitor/pairing-code', headers=owner).json()['code']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.redeem_pairing_code, [code, code]))
    assert sum(result is not None for result in results) == 1


def test_invalid_codes_are_rate_limited(client):
    for _ in range(10):
        assert client.post('/api/monitor/redeem', json={'code': 'AAAA-BBBB', 'accepted': True}).status_code == 400
    assert client.post('/api/monitor/redeem', json={'code': 'AAAA-BBBB', 'accepted': True}).status_code == 429


def test_windows_download_serves_binary_or_explicit_unavailable(client, monkeypatch, tmp_path):
    cfg = get_settings()
    binary = tmp_path / 'SpecCheck-Agent.exe'
    monkeypatch.setattr(cfg, 'monitoring_agent_exe', binary)
    monkeypatch.setattr(cfg, 'monitoring_agent_download_url', '')
    assert client.get('/api/monitor/status').json()['agent_download_available'] is False
    assert client.get('/api/monitor/agent.exe').status_code == 503
    binary.write_bytes(b'MZ-synthetic-test-binary')
    response = client.get('/api/monitor/agent.exe')
    assert response.status_code == 200 and response.content == binary.read_bytes()
    assert 'SpecCheck-Agent.exe' in response.headers['content-disposition']
    assert client.get('/api/monitor/status').json()['agent_download_available'] is True
    monkeypatch.setattr(cfg, 'monitoring_agent_exe', tmp_path / 'not-present.exe')
    monkeypatch.setattr(cfg, 'monitoring_agent_download_url', 'https://downloads.example.com/SpecCheck-Agent.exe')
    response = client.get('/api/monitor/agent.exe', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == cfg.monitoring_agent_download_url
    monkeypatch.setattr(cfg, 'monitoring_agent_download_url', 'http://downloads.example.com/Agent.exe')
    assert client.get('/api/monitor/agent.exe', follow_redirects=False).status_code == 503
