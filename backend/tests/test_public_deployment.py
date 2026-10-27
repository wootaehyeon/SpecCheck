"""공개 배포에서 웹/API 연결과 개인 PC 이력 차단을 검증한다."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def public_client(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "serve_frontend", True)
    monkeypatch.setattr(settings, "telemetry_api_enabled", False)
    monkeypatch.setattr(settings, "cors_origins", "")
    monkeypatch.setattr(settings, "snapshot_db", tmp_path / "snapshots.db")
    with TestClient(create_app()) as client:
        yield client
    assert not (tmp_path / "snapshots.db").exists()


@pytest.mark.parametrize("path", [
    "/", "/index.html", "/input.html", "/analyzing.html", "/result.html",
    "/detail.html", "/recommend.html", "/crawl.html", "/css/style.css", "/js/script.js",
])
def test_public_web_assets(public_client, path):
    response = public_client.get(path)
    assert response.status_code == 200
    if path.endswith(".html") or path == "/":
        assert "text/html" in response.headers["content-type"]


def test_health_and_public_api_remain_available(public_client, monkeypatch):
    monkeypatch.setattr("app.api.routes.price.search_market_prices", lambda name: {
        "lowest_price": 100000, "highest_price": 150000, "average_price": 125000,
    })
    assert public_client.get("/health").json()["status"] == "ok"
    response = public_client.post("/api/market-prices", json={"parts": [
        {"key": "cpu", "category": "CPU", "name": "test CPU", "userPrice": 120000},
    ]})
    assert response.status_code == 200
    assert response.json()["prices"][0]["lowestPrice"] == 100000
    paths = public_client.get("/openapi.json").json()["paths"]
    assert "/api/evaluate-build" in paths
    assert not any(path.startswith(("/api/scan", "/api/diagnosis")) for path in paths)


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/scan/snapshots"),
    ("POST", "/api/scan/snapshots"),
    ("GET", "/api/scan/snapshots/test-id"),
    ("GET", "/api/scan/process-events"),
    ("GET", "/api/diagnosis/rules"),
    ("POST", "/api/diagnosis/analyze"),
    ("POST", "/api/diagnosis/test-id"),
    ("GET", "/api/diagnosis/test-id/history"),
])
def test_public_server_excludes_telemetry_routes(public_client, method, path):
    # StaticFiles는 POST를 405로 거절할 수 있다. 저장/진단 라우터에는 도달하지 않는다.
    assert public_client.request(method, path).status_code in (404, 405)


@pytest.mark.parametrize("path", [
    "/.env", "/.git/config", "/backend/.env", "/backend/data/snapshots.db",
    "/%2e%2e/%2e%2e/backend/.env",
])
def test_only_frontend_directory_is_public(public_client, path):
    assert public_client.get(path).status_code == 404


def test_local_backend_retains_existing_routes(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "serve_frontend", False)
    monkeypatch.setattr(settings, "telemetry_api_enabled", True)
    with TestClient(create_app()) as client:
        assert "Backend is running" in client.get("/").json()["message"]
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/scan/snapshots" in paths
        assert "/api/diagnosis/{snapshot_id}" in paths
