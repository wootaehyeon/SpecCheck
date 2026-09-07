from types import SimpleNamespace

from app.services import naver_api


def test_market_price_reports_missing_credentials(monkeypatch):
    monkeypatch.setattr(
        naver_api,
        "get_settings",
        lambda: SimpleNamespace(naver_client_id="", naver_client_secret="", naver_price_cache_ttl_seconds=900),
    )
    naver_api._CACHE.clear()

    result = naver_api.search_market_prices("WD_BLACK SN850X 1TB")

    assert result["error_code"] == "credentials_missing"


def test_market_price_uses_lowest_verified_new_listing(monkeypatch):
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [
                {"title": "WD_BLACK SN850X 1TB 방열판", "lprice": "12000", "productType": "1", "link": "https://bad.example", "mallName": "액세서리몰"},
                {"title": "WD_BLACK SN850X 1TB NVMe SSD", "lprice": "145000", "productType": "1", "link": "https://low.example", "mallName": "최저가몰"},
                {"title": "WD_BLACK SN850X 1TB NVMe SSD 정품", "lprice": "152000", "productType": "1", "link": "https://high.example", "mallName": "다른몰"},
            ]}

    monkeypatch.setattr(
        naver_api,
        "get_settings",
        lambda: SimpleNamespace(naver_client_id="id", naver_client_secret="secret", naver_price_cache_ttl_seconds=900),
    )
    captured = {}

    def fake_get(*_args, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(naver_api.requests, "get", fake_get)
    naver_api._CACHE.clear()

    result = naver_api.search_market_prices("WD_BLACK SN850X 1TB")

    assert result["lowest_price"] == 145000
    assert result["purchase_link"] == "https://low.example"
    assert result["listing_count"] == 2
    assert captured["params"]["sort"] == "asc"
    assert captured["params"]["exclude"] == "used:cbshop"
