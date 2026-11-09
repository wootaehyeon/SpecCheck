"""Shopping fallback must remain usable after the provider's retirement."""

import requests
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.config import get_settings
from app.services import purchase_catalog


@pytest.mark.parametrize("query", ["NVMe SSD 1TB", "DDR5 메모리", " SSD "])
def test_missing_ebay_credentials_has_no_fake_products_or_network_calls(monkeypatch, query):
    for key in ["ebay_client_id", "ebay_client_secret", "ebay_oauth_token"]:
        monkeypatch.setattr(get_settings(), key, "")
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("no network without credentials"))
    result = purchase_catalog.search_products(query)
    assert result["query"] == query.strip()
    assert result["status"] == "unconfigured"
    assert result["products"] == []
    assert "eBay" in result["message"]


def test_empty_product_query_needs_no_provider():
    assert purchase_catalog.search_products(" ")["status"] == "empty"


def test_purchase_search_is_public_and_validates_queries(monkeypatch):
    monkeypatch.setattr('app.api.routes.purchase.search_products', lambda query: {'query': query, 'status': 'empty', 'products': []})
    with TestClient(create_app()) as client:
        response = client.get('/api/purchase/products', params={'query': ' SSD '})
        assert response.status_code == 200
        assert response.json()['query'] == 'SSD'
        assert client.get('/api/purchase/products').status_code == 422
        assert client.get('/api/purchase/products', params={'query': 'x' * 121}).status_code == 422
