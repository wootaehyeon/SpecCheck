"""실제 DB로 구매자 격리, 공유 철회, 검색/집계, 재시작 후 보존을 검증한다."""
from datetime import datetime, timedelta, timezone
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

URL = "/api/purchase/history"
OWNER = {"Authorization": "Bearer sc_purchase_" + "a" * 64}
OTHER = {"Authorization": "Bearer sc_purchase_" + "b" * 64}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    monkeypatch.setattr(get_settings(), "telemetry_api_enabled", False)
    with TestClient(create_app()) as client:
        yield client


def record(**changes):
    return {"request_id": str(uuid4()), "product_name": "테스트 SSD 1TB", "category": "storage",
            "unit_price": 99000, "quantity": 2, "purchased_on": "2026-01-01", **changes}


def save(client, owner=OWNER, **changes):
    response = client.post(URL, headers=owner, json=record(**changes))
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_private_by_default_and_survives_new_application(client):
    saved = save(client)
    assert saved["shared"] is False
    assert saved["total_price"] == 198000
    assert saved["source"] == "self_reported"
    assert client.get(URL).json()["items"] == []
    assert client.get(URL + "/me", headers=OTHER).json()["items"] == []
    with TestClient(create_app()) as restarted:
        assert restarted.get(URL + "/me", headers=OWNER).json()["items"] == [saved]
    connection = sqlite3.connect(get_settings().data_dir / "purchase-history.db")
    try:
        raw = str(connection.execute("SELECT * FROM purchase_history").fetchall())
        assert "sc_purchase_" not in raw
    finally:
        connection.close()


def test_multiple_buyers_public_summary_and_filtering(client):
    first = save(client, shared=True)
    second = save(client, OTHER, shared=True, product_name="테스트 DDR5", category="memory", unit_price=50000, quantity=1)
    save(client, OTHER, product_name="비공개 부품", unit_price=1000000)
    data = client.get(URL, params={"page_size": 1}).json()
    assert len(data["items"]) == 1
    assert data["summary"] == {"records": 2, "buyers": 2, "total_spent": 248000, "min_unit_price": 50000, "max_unit_price": 99000}
    assert client.get(URL, params={"page_size": 1, "page": 2}).json()["items"][0]["id"] != data["items"][0]["id"]
    assert client.get(URL, params={"query": " sSd ", "category": "storage"}).json()["items"] == [first]
    assert client.get(URL, params={"buyer": second["buyer_label"]}).json()["items"] == [second]
    assert client.get(URL, params={"query": "%' OR 1=1 --"}).json()["summary"]["records"] == 0
    public = client.get(URL)
    assert public.headers["cache-control"] == "no-store"
    assert not any(field in public.text for field in ("owner_hash", "request_id", "sc_purchase_", "비공개 부품"))


def test_only_owner_can_share_revoke_or_delete(client):
    first = save(client)
    path = URL + "/" + first["id"]
    assert client.patch(path, headers=OTHER, json={"shared": True}).status_code == 404
    assert client.delete(path, headers=OTHER).status_code == 404
    assert client.patch(path, headers=OWNER, json={"shared": True}).json()["shared"]
    assert len(client.get(URL).json()["items"]) == 1
    assert client.patch(path, headers=OWNER, json={"shared": False}).status_code == 200
    assert client.get(URL).json()["items"] == []
    assert client.delete(path, headers=OWNER).status_code == 204
    assert client.get(URL + "/me", headers=OWNER).json()["summary"]["records"] == 0


def test_request_retry_does_not_duplicate_a_purchase(client):
    payload = record(shared=True)
    first = client.post(URL, headers=OWNER, json=payload).json()
    assert client.post(URL, headers=OWNER, json=payload).json() == first
    assert client.get(URL).json()["summary"]["records"] == 1
    payload["unit_price"] += 1
    assert client.post(URL, headers=OWNER, json=payload).status_code == 409


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad"}, {"Authorization": "Basic " + "a" * 64}])
def test_private_operations_need_valid_bearer_key(client, headers):
    assert client.get(URL + "/me", headers=headers).status_code == 401
    assert client.post(URL, headers=headers, json=record()).status_code == 401
    assert client.patch(URL + "/" + str(uuid4()), headers=headers, json={"shared": True}).status_code == 401
    assert client.delete(URL + "/" + str(uuid4()), headers=headers).status_code == 401


@pytest.mark.parametrize("changes", [
    {"product_name": "   "}, {"unit_price": 0}, {"unit_price": True}, {"unit_price": 1.5},
    {"quantity": 0}, {"quantity": 101}, {"category": "unknown"}, {"shared": "true"},
    {"merchant": "x" * 81}, {"purchased_on": "2099-01-01"}, {"extra": "forbidden"},
])
def test_invalid_purchase_is_not_saved(client, changes):
    assert client.post(URL, headers=OWNER, json=record(**changes)).status_code == 422
    assert client.get(URL + "/me", headers=OWNER).json()["items"] == []


def test_korean_today_and_list_bounds(client):
    korean_today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    save(client, purchased_on=korean_today)
    for query in ("page=0", "page_size=101", "category=unknown", "query=" + "a" * 121):
        assert client.get(URL + "?" + query).status_code == 422


def test_storage_failure_does_not_report_a_success_or_leak_details(client, monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("private path and credentials")
    monkeypatch.setattr("app.services.purchase_history.sqlite3.connect", fail)
    response = client.post(URL, headers=OWNER, json=record())
    assert response.status_code == 503
    assert "private" not in response.text
