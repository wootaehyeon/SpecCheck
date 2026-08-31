"""Scan / Diagnosis API 통합 테스트.

Agent -> Backend -> 진단으로 이어지는 경로 전체를 한 번에 확인한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """테스트가 실제 스냅샷 DB를 건드리지 않게 격리한다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "snapshot_db", tmp_path / "snapshots.db")
    monkeypatch.setattr(settings, "llm_enabled", False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def make_payload(snapshot_id: str = "11111111-2222-3333-4444-555555555555", **overrides):
    payload = {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scan_mode": "actual",
        "device_id": "device-abc",
        "agent": {"version": "0.1.0", "os": "Windows", "os_version": "10.0.26200"},
        "sections": {
            "hardware": {
                "status": "ok",
                "milestone": "M1",
                "data": {
                    "memory": {"total_gb": 4.0, "module_count": 1, "modules": []},
                    "storage": [{"model": "WDC HDD", "media_type": "HDD", "size_gb": 1000}],
                    "gpu": [],
                    "motherboard": {},
                },
            },
            "security": {"status": "planned", "milestone": "M6"},
        },
    }
    payload.update(overrides)
    return payload


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_and_fetch_snapshot(client):
    response = client.post("/api/scan/snapshots", json=make_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["usable_sections"] == ["hardware"]  # planned 섹션은 제외된다

    fetched = client.get("/api/scan/snapshots/{0}".format(body["snapshot_id"]))
    assert fetched.status_code == 200
    assert fetched.json()["device_id"] == "device-abc"


def test_incompatible_schema_major_is_rejected(client):
    """Agent가 앞서 나가면 해석하지 않고 명시적으로 거절한다."""
    response = client.post("/api/scan/snapshots", json=make_payload(schema_version="2.0.0"))
    assert response.status_code == 415


def test_list_snapshots_by_device(client):
    client.post("/api/scan/snapshots", json=make_payload("aaaaaaaa-0000-0000-0000-000000000001"))
    client.post("/api/scan/snapshots", json=make_payload("aaaaaaaa-0000-0000-0000-000000000002"))

    response = client.get("/api/scan/snapshots", params={"device_id": "device-abc"})
    assert response.status_code == 200
    assert len(response.json()) == 2

    empty = client.get("/api/scan/snapshots", params={"device_id": "unknown"})
    assert empty.json() == []


def test_missing_snapshot_returns_404(client):
    assert client.get("/api/scan/snapshots/nope").status_code == 404
    assert client.post("/api/diagnosis/nope").status_code == 404


def test_analyze_without_storing(client):
    response = client.post("/api/diagnosis/analyze", json=make_payload())
    assert response.status_code == 200
    result = response.json()
    assert result["decision"]["action"] == "purchase"
    assert result["explanation"]
    # 저장하지 않는 경로이므로 조회되면 안 된다
    assert client.get("/api/scan/snapshots/{0}".format(result["snapshot_id"])).status_code == 404


def test_diagnose_stored_snapshot(client):
    upload = client.post("/api/scan/snapshots", json=make_payload())
    snapshot_id = upload.json()["snapshot_id"]

    response = client.post("/api/diagnosis/{0}".format(snapshot_id))
    assert response.status_code == 200
    result = response.json()
    assert {f["rule_id"] for f in result["findings"]} >= {"HW-RAM-002", "HW-DISK-001"}
    assert result["coverage"]["security"] == "planned"


def test_rules_endpoint_exposes_criteria(client):
    response = client.get("/api/diagnosis/rules")
    assert response.status_code == 200
    rules = response.json()
    assert rules and all({"rule_id", "title", "requires"} <= set(rule) for rule in rules)


def test_price_routes_still_mounted(client):
    """구조 개편 후에도 기존 가격 API 경로가 유지되는지 확인한다."""
    paths = {route.path for route in app.routes}
    assert "/api/price-check" in paths
    assert "/api/optimize-estimate" in paths
