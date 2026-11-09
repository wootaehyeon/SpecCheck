"""Exercise the replacement supplier, variant identity and currency boundary."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import purchase_catalog as catalog
from app.services import purchase_market as market
from app.services import market_prices
from tests.test_purchase_market import item, Response


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key in ["ebay_client_id", "ebay_client_secret", "ebay_oauth_token"]:
        monkeypatch.setattr(get_settings(), key, "")
    catalog._cache.clear()
    market._tokens.clear()


def install(monkeypatch, product=None, status=200):
    monkeypatch.setattr(get_settings(), "ebay_oauth_token", "test-only-token")
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if status != 200:
            return Response({"errors": [{"message": "private credential detail"}]}, status)
        if url.endswith("/search"):
            return Response({"itemSummaries": [{"itemId": "v1|123456789012|0"}]})
        return Response(product or item())

    monkeypatch.setattr(market.requests, "get", get)
    return calls


def test_browse_search_reuses_oauth_validation_cache_and_native_shipping(monkeypatch):
    calls = install(monkeypatch)
    result = catalog.search_products("Fixture FIX-1000 1TB")
    assert result["status"] == "ok" and result["source"] == "ebay_browse"
    product = result["products"][0]
    assert product["currency"] == "USD" and product["amount"] == "100.00"
    assert product["shipping"] == "10.00" and product["total"] == "110.00"
    assert len(calls) == 2
    assert "deliveryCountry:KR" in calls[0][1]["params"]["filter"]
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-only-token"
    assert calls[0][1]["allow_redirects"] is False
    assert catalog.search_products("Fixture FIX-1000 1TB")["cached"]
    assert len(calls) == 2 and "test-only-token" not in str(result)


@pytest.mark.parametrize("changes", [
    {"title": "Fixture FIX-1000X 1TB"}, {"title": "Fixture FIX-1000 2TB"},
    {"title": "Fixture FIX-1000 1TB 2TB"}, {"title": "Fixture FIX-1000 1TB enclosure"},
    {"title": "Fixture FIX-1000 Ti 1TB"}, {"conditionId": "3000"}, {"buyingOptions": ["AUCTION"]},
    {"itemWebUrl": "javascript:bad()"}, {"price": {"value": "NaN", "currency": "USD"}},
    {"estimatedAvailabilities": [{"estimatedAvailabilityStatus": "OUT_OF_STOCK"}]},
])
def test_search_does_not_offer_other_variants_unsafe_links_or_invalid_prices(monkeypatch, changes):
    install(monkeypatch, item(**changes))
    result = catalog.search_products("Fixture FIX-1000 1TB")
    assert result["status"] == "empty" and result["products"] == []


@pytest.mark.parametrize("status,code", [(401, "auth_failed"), (403, "auth_failed"), (429, "rate_limited"), (503, "unavailable")])
def test_supplier_failures_are_cached_and_do_not_leak_details(monkeypatch, status, code):
    calls = install(monkeypatch, status=status)
    first = catalog.search_products("Fixture FIX-1000 1TB")
    assert first["status"] == code and not first["products"]
    catalog.search_products("Fixture FIX-1000 1TB")
    assert len(calls) == 1 and "private" not in str(first)


def test_unknown_shipping_is_not_reported_as_free(monkeypatch):
    install(monkeypatch, item(shippingOptions=[]))
    product = catalog.search_products("Fixture FIX-1000 1TB")["products"][0]
    assert product["shipping"] is None and product["total"] is None


def test_currency_stays_native_and_does_not_enter_won_comparisons(monkeypatch):
    install(monkeypatch)
    response = TestClient(app).post("/api/market-prices", json={"parts": [
        {"key": "ssd", "category": "SSD", "name": "Fixture FIX-1000 1TB", "userPrice": 99000},
    ]})
    assert response.status_code == 200
    row = response.json()["prices"][0]
    assert row["lowestPrice"] == row["highestPrice"] == row["averagePrice"] == 0
    assert row["errorCode"] == "currency_mismatch" and row["source"] == "ebay_browse"
    assert row["nativePrices"][0] == {"currency": "USD", "lowest": "100.00", "highest": "100.00", "average": "100.00", "listingCount": 1}
    assert row["purchaseLink"].startswith("https://www.ebay.com/itm/")
    assert market_prices.search_lowest_price("Fixture FIX-1000 1TB")["price_krw"] is None


def test_won_quotes_can_be_used_without_assuming_exchange_rates(monkeypatch):
    install(monkeypatch, item(price={"value": "99000", "currency": "KRW"}))
    result = market_prices.search_market_prices("Fixture FIX-1000 1TB")
    assert "error" not in result and result["lowest_price"] == 99000


def test_search_cache_does_not_survive_credential_change(monkeypatch):
    calls = install(monkeypatch)
    catalog.search_products("Fixture FIX-1000 1TB")
    monkeypatch.setattr(get_settings(), "ebay_oauth_token", "new-test-token")
    catalog.search_products("Fixture FIX-1000 1TB")
    assert len(calls) == 4
