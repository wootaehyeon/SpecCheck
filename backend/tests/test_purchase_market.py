from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import purchase_market as market

PRODUCT = {"id": "fixture-ssd", "name": "Fixture X900 1TB", "manufacturer": "Fixture", "model_number": "FIX-1000", "capacity_gb": 1000, "search_query": "Fixture X900 FIX-1000 1TB"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    settings = get_settings()
    for key in ["ebay_client_id", "ebay_client_secret", "ebay_oauth_token"]:
        monkeypatch.setattr(settings, key, "")
    market._cache.clear()
    market._tokens.clear()


def item(**updates):
    return {"itemId": "v1|123456789012|0", "title": "Fixture FIX-1000 1TB", "conditionId": "1000", "buyingOptions": ["FIXED_PRICE"],
            "itemWebUrl": "https://www.ebay.com/itm/123456789012", "price": {"value": "100.00", "currency": "USD"},
            "shippingOptions": [{"shipToLocationUsedForEstimate": {"country": "KR"}, "quantityUsedForEstimate": 1,
                                 "shippingCost": {"value": "10.00", "currency": "USD"}}],
            "estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK", "deliveryOptions": ["SHIP_TO_HOME"]}], **updates}


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        return self.data


def test_no_credentials_no_network_and_stable_technical_state(monkeypatch):
    monkeypatch.setattr(market.requests, "get", lambda *a, **k: pytest.fail("No network without credentials"))
    monkeypatch.setattr(market.requests, "post", lambda *a, **k: pytest.fail("No OAuth without credentials"))
    state, revision = market.offers_state([PRODUCT])
    assert state["mode"] == "technical_only" and state["offers"] == []
    assert state["products"][0]["code"] == "not_configured"
    assert market.offers_state([PRODUCT])[1] == revision


def test_exact_variant_normalized_with_destination_shipping():
    offer = market._offer(PRODUCT, item())
    assert offer["total"] == "110.00" and offer["source"] == "ebay_browse"
    assert offer["stock_estimated"] and not offer["tax_included"]


@pytest.mark.parametrize("changes", [
    {"title": "Fixture FIX-2000 1TB"}, {"title": "Fixture FIX-1000X 1TB"},
    {"title": "Fixture FIX-1000 2TB"}, {"title": "Fixture FIX-1000 1TB 2TB"},
    {"title": "Fixture FIX-1000 1TB enclosure"}, {"conditionId": "3000"},
    {"buyingOptions": ["AUCTION"]}, {"itemWebUrl": "https://evil.test/itm/123456789012"},
    {"price": {"value": "NaN", "currency": "USD"}},
    {"price": {"value": "-1", "currency": "USD"}},
    {"itemEndDate": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
])
def test_reject_wrong_variant_accessory_used_auction_bad_price_expired(changes):
    assert market._offer(PRODUCT, item(**changes)) is None


@pytest.mark.parametrize("changes", [
    {"shippingOptions": []},
    {"shippingOptions": [{"shipToLocationUsedForEstimate": {"country": "US"}, "shippingCost": {"value": "0", "currency": "USD"}}]},
    {"shippingOptions": [{"shipToLocationUsedForEstimate": {"country": "KR"}, "shippingCost": {"value": "0", "currency": "EUR"}}]},
])
def test_unknown_or_wrong_destination_shipping_not_free(changes):
    offer = market._offer(PRODUCT, item(**changes))
    assert offer["shipping"] is None and offer["total"] is None


def install_mock(monkeypatch, value=None, status=200):
    monkeypatch.setattr(get_settings(), "ebay_oauth_token", "test-only-token")
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if status != 200:
            return Response({"errors": [{"message": "never expose remote error containing a secret"}]}, status)
        if url.endswith("/search"):
            return Response({"itemSummaries": [{"itemId": "v1|123456789012|0"}]})
        return Response(value or item())
    monkeypatch.setattr(market.requests, "get", get)
    return calls


def test_search_details_cache_and_headers(monkeypatch):
    calls = install_mock(monkeypatch)
    state, revision = market.offers_state([PRODUCT])
    assert state["mode"] == "automatic" and state["best"][0]["total"] == "110.00"
    assert len(calls) == 2
    search = calls[0][1]
    assert search["params"]["q"] == PRODUCT["search_query"]
    assert "deliveryCountry:KR" in search["params"]["filter"]
    assert search["headers"]["X-EBAY-C-ENDUSERCTX"] == "contextualLocation=country%3DKR"
    assert search["allow_redirects"] is False
    assert market.offers_state([PRODUCT])[1] == revision and len(calls) == 2
    assert "test-only-token" not in str(state)


@pytest.mark.parametrize("status,code", [(401, "auth_failed"), (403, "auth_failed"), (429, "rate_limited"), (503, "unavailable"), (302, "unavailable")])
def test_errors_fail_soft_without_price_or_secrets(monkeypatch, status, code):
    install_mock(monkeypatch, status=status)
    state, _ = market.offers_state([PRODUCT])
    assert state["offers"] == [] and state["products"][0]["code"] == code
    assert "secret" not in str(state)


@pytest.mark.parametrize("availability", ["OUT_OF_STOCK", "UNKNOWN"])
def test_stock_not_assumed(monkeypatch, availability):
    install_mock(monkeypatch, value=item(estimatedAvailabilities=[{"estimatedAvailabilityStatus": availability}]))
    state, _ = market.offers_state([PRODUCT])
    assert not state["best"]


def test_oauth_client_credentials_and_expiry(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ebay_client_id", "fixture-id")
    monkeypatch.setattr(settings, "ebay_client_secret", "fixture-secret")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return Response({"access_token": "fixture-token", "expires_in": 3600})
    monkeypatch.setattr(market.requests, "post", post)
    assert market._token() == market._token() == "fixture-token"
    assert len(calls) == 1 and calls[0]["auth"] == ("fixture-id", "fixture-secret")
    key = market._fingerprint()
    market._tokens[key] = ("expired", 0)
    assert market._token() == "fixture-token" and len(calls) == 2


def test_failed_oauth_is_cached_briefly_and_does_not_repeat(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ebay_client_id", "fixture-id")
    monkeypatch.setattr(settings, "ebay_client_secret", "wrong-fixture-secret")
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return Response({}, 401)
    monkeypatch.setattr(market.requests, "post", post)
    first = market.offers_state([PRODUCT])
    assert first == market.offers_state([PRODUCT])
    assert first[0]["products"][0]["code"] == "auth_failed" and len(calls) == 1


def test_cache_expires_and_credential_change_not_reused(monkeypatch):
    calls = install_mock(monkeypatch)
    market.offers_state([PRODUCT])
    key = next(iter(market._cache))
    market._cache[key] = (market._cache[key][0], 0)
    market.offers_state([PRODUCT])
    assert len(calls) == 4
    monkeypatch.setattr(get_settings(), "ebay_oauth_token", "changed-test-token")
    market.offers_state([PRODUCT])
    assert len(calls) == 6


def test_catalog_only_read_api(monkeypatch):
    import app.api.routes.purchase as route
    monkeypatch.setattr(route, "load_catalog", lambda: ([PRODUCT], "test"))
    with TestClient(app) as client:
        assert client.get("/api/purchase/quotes?product_id=not-in-catalog").status_code == 422
        response = client.get("/api/purchase/quotes?product_id=fixture-ssd")
        assert response.status_code == 200 and response.json()["mode"] == "technical_only"
        assert client.post("/api/purchase/quotes", json={}).status_code == 405


def test_diagnosis_only_queries_actual_candidates(monkeypatch, tmp_path):
    from app.services import diagnosis_service
    from tests.test_ui_diagnosis import make_snapshot
    monkeypatch.setattr(get_settings(), "snapshot_db", tmp_path / "snapshot.db")
    monkeypatch.setattr(get_settings(), "llm_enabled", False)
    seen = []
    def quotes(products):
        seen.extend(p["id"] for p in products)
        return {"offers": []}, "test-revision"
    monkeypatch.setattr(diagnosis_service, "offers_state", quotes)
    diagnosis = diagnosis_service.diagnose_for_ui(make_snapshot())
    assert seen and all("ddr4" in identifier for identifier in seen)
    assert len(diagnosis.recommendations[0].candidates) >= 2
    assert sum(c.recommended for c in diagnosis.recommendations[0].candidates) == 1
