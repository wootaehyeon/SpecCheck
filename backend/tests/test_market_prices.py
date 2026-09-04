from fastapi.testclient import TestClient

from app.api.routes import price
from app.main import app


def test_market_prices_exposes_representative_product(monkeypatch):
    monkeypatch.setattr(
        price,
        "search_market_prices",
        lambda _query: {
            "lowest_price": 59000,
            "highest_price": 79000,
            "average_price": 68000,
            "purchase_link": "https://shopping.example/item",
            "product_title": "테스트 DDR 메모리 16GB",
            "mall": "테스트몰",
            "listing_count": 12,
        },
    )

    response = TestClient(app).post(
        "/api/market-prices",
        json={"parts": [{"key": "memory-upgrade", "category": "memory", "name": "16GB PC 메모리"}]},
    )

    assert response.status_code == 200
    item = response.json()["prices"][0]
    assert item["lowestPrice"] == 59000
    assert item["productTitle"] == "테스트 DDR 메모리 16GB"
    assert item["mall"] == "테스트몰"
    assert item["listingCount"] == 12


def test_market_prices_keeps_api_failure_in_item(monkeypatch):
    monkeypatch.setattr(price, "search_market_prices", lambda _query: {"error": "Naver API keys are missing."})

    response = TestClient(app).post(
        "/api/market-prices",
        json={"parts": [{"key": "storage-replacement", "category": "storage", "name": "NVMe SSD 1TB"}]},
    )

    assert response.status_code == 200
    item = response.json()["prices"][0]
    assert item["source"] == "error"
    assert item["lowestPrice"] == 0
    assert item["error"] == "Naver API keys are missing."
