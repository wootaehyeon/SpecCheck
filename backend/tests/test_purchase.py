"""상품 실데이터·공급자 장애·안전한 구매 URL 처리 검증."""

import requests
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import naver_api, purchase_catalog


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(naver_api, 'NAVER_CLIENT_ID', 'test-id')
    monkeypatch.setattr(naver_api, 'NAVER_CLIENT_SECRET', 'test-secret')
    return monkeypatch


def test_live_products_are_cleaned_and_invalid_offers_are_omitted(catalog):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'items': [
                {'title': '<b>SSD</b> &amp; 1TB', 'lprice': '99000', 'link': 'https://shop.example/ssd', 'mallName': '판매처'},
                {'title': 'duplicate', 'lprice': '99000', 'link': 'https://shop.example/ssd'},
                {'title': 'unsafe', 'lprice': '100', 'link': 'javascript:alert(1)'},
                {'title': 'no price', 'lprice': '0', 'link': 'https://shop.example/zero'},
                {'title': 'invalid', 'lprice': 'bad', 'link': 'https://shop.example/bad'},
                None,
            ]}

    def search(url, **kwargs):
        assert kwargs['params'] == {'query': 'NVMe SSD 1TB', 'display': 12, 'sort': 'sim'}
        assert kwargs['timeout'] == 5
        return Response()

    catalog.setattr(purchase_catalog.requests, 'get', search)
    result = purchase_catalog.search_products('NVMe SSD 1TB')
    assert result['status'] == 'ok'
    assert result['products'] == [{
        'title': 'SSD & 1TB', 'price': 99000, 'url': 'https://shop.example/ssd', 'mall': '판매처',
    }]


def test_missing_keys_do_not_fabricate_products_or_call_provider(catalog):
    catalog.setattr(naver_api, 'NAVER_CLIENT_ID', '')
    catalog.setattr(purchase_catalog.requests, 'get', lambda *a, **k: pytest.fail('must not call provider'))
    assert purchase_catalog.search_products('SSD')['status'] == 'unconfigured'
    assert purchase_catalog.search_products('SSD')['products'] == []


@pytest.mark.parametrize('failure', [requests.Timeout('private provider detail'), ValueError('invalid JSON')])
def test_provider_failure_is_safe_and_has_no_fake_prices(catalog, failure):
    def fail(*args, **kwargs):
        raise failure
    catalog.setattr(purchase_catalog.requests, 'get', fail)
    result = purchase_catalog.search_products('SSD')
    assert result['status'] == 'unavailable'
    assert result['products'] == []
    assert 'private' not in str(result)


def test_purchase_search_is_public_and_validates_queries(catalog):
    catalog.setattr('app.api.routes.purchase.search_products', lambda query: {'query': query, 'status': 'empty', 'products': []})
    with TestClient(create_app()) as client:
        response = client.get('/api/purchase/products', params={'query': ' SSD '})
        assert response.status_code == 200
        assert response.json()['query'] == 'SSD'
        assert client.get('/api/purchase/products').status_code == 422
        assert client.get('/api/purchase/products', params={'query': 'x' * 121}).status_code == 422
