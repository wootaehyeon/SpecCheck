import io
import json
import urllib.error
from copy import deepcopy
from uuid import uuid4

import pytest

from speccheck_agent import purchase


@pytest.fixture
def connection():
    return {"version": 1, "device_id": str(uuid4()), "backend_url": "https://example.com",
            "writer_token": "sc_write_" + "a" * 40, "interval": 30,
            "security_consent": False, "consent_version": "monitor-v1"}


def diagnosis(connection, action="purchase"):
    return {"device_id": connection["device_id"], "snapshot_id": "scan-one",
            "decision": {"action": action, "reason": "측정값에 따른 판단"},
            "findings": [{"title": "메모리 부족", "summary": "780MB", "action_detail": "상주 프로그램도 확인"}],
            "recommendations": [{"title": "메모리 후보", "candidates": [
                {"title": "DDR4 32GB", "recommended": True, "summary": "용량을 늘리는 후보", "compatibilityStatus": "conditional",
                 "checks": [{"status": "conditional", "label": "슬롯", "detail": "실제 슬롯 확인 필요"}],
                 "parts": [{"key": "memory-32", "name": "DDR4 32GB", "searchQuery": "DDR4 & 32GB",
                            "specifications": ["DIMM", "32GB"]}]}]}]}


def test_agent_orchestrates_own_diagnosis_and_catalog_only_quotes(connection, monkeypatch):
    calls = []
    def get(config, path, **kwargs):
        calls.append((path, kwargs))
        if path.startswith("/api/monitor/"):
            return diagnosis(connection)
        return {"offers": [], "products": [{"product_id": "memory-32", "message": "가격 미확인"}]}
    monkeypatch.setattr(purchase, "_get", get)
    report = purchase.run_assistance(connection, snapshot_id="scan-one")
    assert calls == [("/api/monitor/assistance?snapshot_id=scan-one", {"private": True}),
                     ("/api/purchase/quotes?product_id=memory-32", {})]
    assert report["action"] == "purchase"
    assert "가격 미확인" in report["text"] and "실제 슬롯 확인 필요" in report["text"]
    assert len(report["links"]) == 3
    for link in report["links"]:
        assert purchase.safe_shop_url(link["url"])
        assert "device_id" not in link["url"] and connection["writer_token"] not in link["url"]
        assert "%26" in link["url"]


@pytest.mark.parametrize("action", ["keep", "fix"])
def test_no_purchase_action_never_requests_quotes_or_generates_shopping_links(connection, monkeypatch, action):
    calls = []
    def get(config, path, **kwargs):
        calls.append(path)
        return diagnosis(connection, action)
    monkeypatch.setattr(purchase, "_get", get)
    report = purchase.run_assistance(connection)
    assert len(calls) == 1 and report["links"] == []


def test_price_failure_keeps_technical_candidate_without_fabricating_prices(connection, monkeypatch):
    def get(config, path, **kwargs):
        if path.startswith("/api/monitor/"):
            return diagnosis(connection)
        raise purchase.AssistanceError("unavailable")
    monkeypatch.setattr(purchase, "_get", get)
    report = purchase.run_assistance(connection)
    assert "DDR4 32GB" in report["text"] and "가격 조회에 실패" in report["text"]
    assert len(report["links"]) == 3


def test_automatic_refresh_does_not_request_market_prices(connection, monkeypatch):
    def get(config, path, **kwargs):
        assert path == "/api/monitor/assistance"
        return diagnosis(connection)
    monkeypatch.setattr(purchase, "_get", get)
    assert "가격·재고 미확인" in purchase.run_assistance(connection, fetch_quotes=False)["text"]


def test_malformed_quote_response_preserves_technical_recommendation(connection, monkeypatch):
    monkeypatch.setattr(purchase, "_get", lambda config, path, **kw:
                        diagnosis(connection) if path.startswith("/api/monitor/") else {"offers": None})
    report = purchase.run_assistance(connection)
    assert "DDR4 32GB" in report["text"] and "가격 조회에 실패" in report["text"]


@pytest.mark.parametrize("change", [{"device_id": "other"}, {"snapshot_id": "old"},
                                  {"unavailable": True}, {"decision": None}])
def test_wrong_device_stale_or_unavailable_diagnosis_is_not_recommended(connection, monkeypatch, change):
    context = diagnosis(connection)
    context.update(change)
    monkeypatch.setattr(purchase, "_get", lambda *a, **kw: context)
    with pytest.raises(purchase.AssistanceError):
        purchase.run_assistance(connection, snapshot_id="scan-one")


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/Windows/a", "https://evil.example/product",
                                "https://www.ebay.com.evil.example/item", "https://user:pass@www.ebay.com/item",
                                "https://www.ebay.com:444/item", "https://www.ebay.com/\nitem"])
def test_untrusted_shopping_urls_are_filtered(connection, url):
    assert not purchase.safe_shop_url(url)
    report = purchase.build_report(diagnosis(connection), {"offers": [{"product_id": "memory-32", "url": url}]}, "")
    assert all(link["url"] != url for link in report["links"])


def test_transport_keeps_device_credentials_out_of_public_quote_requests(connection, monkeypatch):
    sent = []
    class Opener:
        def open(self, request, **kwargs):
            sent.append(request)
            return io.BytesIO(b'{}')
    monkeypatch.setattr(purchase.urllib.request, "build_opener", lambda handler: Opener())
    purchase._get(connection, "/api/monitor/assistance", private=True)
    purchase._get(connection, "/api/purchase/quotes?product_id=memory-32")
    assert sent[0].get_header("Authorization") == "Bearer " + connection["writer_token"]
    assert sent[1].get_header("Authorization") is None
    assert all(connection["writer_token"] not in r.full_url for r in sent)


def test_authentication_errors_do_not_expose_server_body_or_credentials(connection, monkeypatch):
    class Opener:
        def open(self, request, **kwargs):
            raise urllib.error.HTTPError(request.full_url, 401, connection["writer_token"], {}, None)
    monkeypatch.setattr(purchase.urllib.request, "build_opener", lambda handler: Opener())
    with pytest.raises(purchase.AssistanceError) as error:
        purchase._get(connection, "/api/monitor/assistance", private=True)
    assert connection["writer_token"] not in str(error.value)


def test_matching_offer_preserves_unknown_shipping_and_rejects_other_products(connection):
    offer = {"product_id": "memory-32", "url": "https://www.ebay.com/itm/123", "title": "DDR4",
             "currency": "USD", "amount": "40", "shipping": None, "total": None, "observed_at": "2026-11-10"}
    other = deepcopy(offer)
    other.update(product_id="unrelated", url="https://www.ebay.com/itm/456")
    report = purchase.build_report(diagnosis(connection), {"offers": [offer, other]}, "")
    assert "한국 배송 미확인 / 합계 미확인" in report["text"]
    assert any(link["url"] == offer["url"] for link in report["links"])
    assert not any(link["url"] == other["url"] for link in report["links"])


def test_failed_compatibility_never_generates_purchase_links_or_quotes(connection, monkeypatch):
    context = diagnosis(connection)
    context["recommendations"][0]["candidates"][0]["checks"][0]["status"] = "failed"
    def get(config, path, **kwargs):
        assert path == "/api/monitor/assistance"
        return context
    monkeypatch.setattr(purchase, "_get", get)
    report = purchase.run_assistance(connection)
    assert report["links"] == [] and "구매 연결에서 제외" in report["text"]
