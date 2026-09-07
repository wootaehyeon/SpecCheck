"""Naver Shopping Search API adapter for verified catalog products.

The API returns a product's advertised lowest price. We only expose a
purchase link after filtering out used/import listings and weak title matches,
so a cheap accessory cannot become the recommended purchase.
"""

from __future__ import annotations

import re
import statistics
import time
from typing import Any

import requests

from app.core.config import get_settings

NAVER_SHOP_API_URL = "https://openapi.naver.com/v1/search/shop.json"
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _plain_title(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return {token for token in normalized.split() if len(token) > 1}


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"error": message, "error_code": code}


def _cached(query: str) -> dict[str, Any] | None:
    ttl = max(0, get_settings().naver_price_cache_ttl_seconds)
    item = _CACHE.get(query)
    if not item or time.monotonic() - item[0] > ttl:
        return None
    return {**item[1], "cached": True}


def _save_cache(query: str, result: dict[str, Any]) -> dict[str, Any]:
    _CACHE[query] = (time.monotonic(), result)
    return {**result, "cached": False}


def _relevance(query: str, item: dict[str, Any]) -> float:
    wanted = _tokens(query)
    title = _tokens(_plain_title(item.get("title", "")))
    if not wanted:
        return 0.0
    overlap = len(wanted & title) / len(wanted)
    # ProductType 1 is Naver's price-comparison product. It is a useful tie
    # breaker, but exact model-token matching remains the primary guardrail.
    if str(item.get("productType", "")) in {"1", "3"}:
        overlap += 0.1
    return overlap


def _looks_like_accessory(item: dict[str, Any]) -> bool:
    title = _plain_title(item.get("title", "")).lower()
    accessory_words = ("방열판", "히트싱크", "케이스", "커버", "나사", "enclosure", "adapter")
    has_storage_identity = "ssd" in title or "nvme" in title
    return any(word in title for word in accessory_words) and not has_storage_identity


def _priced_matches(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in items:
        price_text = str(item.get("lprice") or "")
        if not price_text.isdigit() or int(price_text) <= 0:
            continue
        if _looks_like_accessory(item):
            continue
        if _relevance(query, item) < 0.6:
            continue
        matches.append({
            "price": int(price_text),
            "title": _plain_title(item.get("title", "")),
            "link": item.get("link", ""),
            "mall": item.get("mallName", "") or "네이버 쇼핑",
        })
    return matches


def search_market_prices(query: str) -> dict[str, Any]:
    """Return the lowest verified listing and a representative market range."""
    query = query.strip()
    if not query:
        return _failure("invalid_query", "가격을 조회할 제품명이 비어 있습니다.")

    cached = _cached(query)
    if cached is not None:
        return cached

    settings = get_settings()
    if not settings.naver_client_id or not settings.naver_client_secret:
        return _failure(
            "credentials_missing",
            "네이버 쇼핑 API 키가 설정되지 않았습니다. backend/.env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 설정하세요.",
        )

    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {
        "query": query,
        "display": 100,
        "sort": "asc",
        "exclude": "used:cbshop",
    }
    try:
        response = requests.get(NAVER_SHOP_API_URL, headers=headers, params=params, timeout=8)
        if response.status_code == 403:
            return _failure(
                "permission_denied",
                "네이버 API 권한이 없습니다. 개발자 센터에서 이 애플리케이션의 검색 API 사용 설정을 확인하세요.",
            )
        if response.status_code in {401, 429}:
            return _failure(
                "authentication_or_limit",
                "네이버 API 인증 또는 호출 한도 오류입니다. 키와 일일 호출 한도를 확인하세요.",
            )
        response.raise_for_status()
        items = _priced_matches(query, response.json().get("items", []))
    except requests.Timeout:
        return _failure("timeout", "네이버 쇼핑 가격 조회 시간이 초과됐습니다. 잠시 후 다시 시도하세요.")
    except requests.RequestException:
        return _failure("network_error", "네이버 쇼핑 API에 연결하지 못했습니다. 네트워크 연결을 확인하세요.")
    except ValueError:
        return _failure("invalid_response", "네이버 쇼핑 API 응답을 읽지 못했습니다.")

    if not items:
        return _failure("no_verified_match", "동일 모델로 확인할 수 있는 새 상품 가격을 찾지 못했습니다.")

    # The API is already sorted by price, but use min explicitly so a provider
    # order change cannot alter which checkout link the UI presents.
    lowest = min(items, key=lambda item: item["price"])
    prices = [item["price"] for item in items]
    return _save_cache(query, {
        "lowest_price": lowest["price"],
        "highest_price": max(prices),
        "average_price": int(round(statistics.mean(prices))),
        "purchase_link": lowest["link"],
        "product_title": lowest["title"],
        "mall": lowest["mall"],
        "listing_count": len(items),
    })


def search_lowest_price(query: str) -> dict[str, Any]:
    """Legacy single-price adapter used by older estimate routes."""
    result = search_market_prices(query)
    if "error" in result:
        return {"error": result["error"], "price_krw": None}
    return {
        "price_krw": result["lowest_price"],
        "title": result["product_title"],
        "link": result["purchase_link"],
    }
