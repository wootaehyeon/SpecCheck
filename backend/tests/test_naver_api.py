import pytest
import requests

from app.services import naver_api


@pytest.mark.parametrize("query", ["WD_BLACK SN850X 1TB", "삼성 SSD 1TB"])
def test_retired_service_never_calls_provider_or_fabricates_prices(monkeypatch, query):
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("retired API must not be called"))
    result = naver_api.search_market_prices(query)
    assert result["error_code"] == "service_retired"
    assert "2026년 7월 31일" in result["error"]
    assert "lowest_price" not in result
    assert naver_api.search_lowest_price(query)["price_krw"] is None


def test_empty_query_retains_validation_error():
    assert naver_api.search_market_prices("   ")["error_code"] == "invalid_query"
