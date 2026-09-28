"""Catalog-bound eBay Browse quotes. Secrets and OAuth stay on the backend."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlsplit

import requests

from app.core.config import get_settings
from app.services.component_catalog import load_catalog
from app.services.purchase_offers import HOSTS, matches

API = "https://api.ebay.com"
_lock = threading.RLock()
_cache = {}
_tokens = {}
MESSAGES = {
    "not_configured": "가격 미확인 · 판매처 연결 대기",
    "auth_failed": "가격 미확인 · 판매처 인증 오류",
    "rate_limited": "가격 미확인 · 판매처 조회 한도 도달",
    "unavailable": "가격 미확인 · 판매처 응답 오류",
    "no_match": "가격 미확인 · 동일 모델의 판매 상품을 찾지 못함",
}


class MarketError(Exception):
    def __init__(self, code):
        self.code = code


def configured():
    settings = get_settings()
    return bool(settings.ebay_oauth_token or (settings.ebay_client_id and settings.ebay_client_secret))


def _fingerprint():
    settings = get_settings()
    return hashlib.sha256((settings.ebay_client_id + "\0" + settings.ebay_client_secret + "\0" + settings.ebay_oauth_token).encode()).hexdigest()


def _payload(response):
    if response.status_code in {401, 403}:
        raise MarketError("auth_failed")
    if response.status_code == 429:
        raise MarketError("rate_limited")
    if response.status_code >= 300:
        raise MarketError("unavailable")
    try:
        data = response.json()
        if not isinstance(data, dict) or data.get("errors"):
            raise MarketError("unavailable")
        return data
    except ValueError as error:
        raise MarketError("unavailable") from error


def _token():
    settings = get_settings()
    if settings.ebay_oauth_token:
        return settings.ebay_oauth_token
    key = _fingerprint()
    stored = _tokens.get(key)
    if stored and stored[1] > time.monotonic():
        return stored[0]
    data = _payload(requests.post(API + "/identity/v1/oauth2/token",
        auth=(settings.ebay_client_id, settings.ebay_client_secret),
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=4, allow_redirects=False))
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise MarketError("auth_failed")
    try:
        expiry = max(0, min(float(data.get("expires_in", 0)), 7200) - 60)
    except (ValueError, TypeError):
        expiry = 0
    _tokens.clear()
    _tokens[key] = (token, time.monotonic() + expiry)
    return token


def _get(path, token, deadline, params=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MarketError("unavailable")
    return _payload(requests.get(API + "/buy/browse/v1/" + path,
        params=params, headers={"Authorization": "Bearer " + token,
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DKR"},
        timeout=min(4, remaining), allow_redirects=False))


def _money(value):
    try:
        if not isinstance(value, dict) or len(str(value.get("value", ""))) > 40:
            return None
        amount = Decimal(value["value"])
        currency = value["currency"]
        if not amount.is_finite() or amount < 0 or amount > 100000000 or currency not in {"USD", "EUR", "GBP", "AUD", "CAD", "KRW"}:
            return None
        return amount, currency
    except (KeyError, TypeError, InvalidOperation):
        return None


def _offer(product, item):
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", ""))[:300]
    mpn = str(item.get("mpn", ""))[:100]
    if not matches(product, title + " " + mpn):
        return None
    if str(item.get("conditionId")) != "1000" or "FIXED_PRICE" not in item.get("buyingOptions", []):
        return None
    url = str(item.get("itemWebUrl", ""))
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in {None, 443} or not parsed.path.startswith("/itm/"):
            return None
        end = item.get("itemEndDate")
        if end and datetime.fromisoformat(end.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            return None
    except (ValueError, TypeError):
        return None
    price = _money(item.get("price"))
    if not price or price[0] == 0:
        return None
    shipping = []
    for option in item.get("shippingOptions", []):
        if not isinstance(option, dict) or not isinstance(option.get("shipToLocationUsedForEstimate"), dict):
            continue
        if (option.get("shipToLocationUsedForEstimate") or {}).get("country") != "KR" or option.get("quantityUsedForEstimate", 1) != 1:
            continue
        money = _money(option.get("shippingCost"))
        if money and money[1] == price[1]:
            shipping.append(money[0])
    statuses = {value.get("estimatedAvailabilityStatus") for value in item.get("estimatedAvailabilities", []) if isinstance(value, dict) and (not value.get("deliveryOptions") or "SHIP_TO_HOME" in value["deliveryOptions"])}
    availability = "out_of_stock" if "OUT_OF_STOCK" in statuses else "in_stock" if "IN_STOCK" in statuses else "unknown"
    cost = min(shipping) if shipping else None
    return {"id": str(item.get("itemId", "")), "product_id": product["id"], "title": title, "url": url,
            "amount": str(price[0]), "currency": price[1], "shipping": str(cost) if cost is not None else None,
            "total": str(price[0] + cost) if cost is not None else None, "availability": availability,
            "observed_at": datetime.now(timezone.utc).isoformat(), "source": "ebay_browse",
            "delivery_country": "KR", "tax_included": False, "stock_estimated": True}


def _quote_product(product, token, deadline):
    try:
        data = _get("item_summary/search", token, deadline, {"q": product["search_query"][:200], "limit": "10",
                    "sort": "price", "filter": "buyingOptions:{FIXED_PRICE},conditionIds:{1000},deliveryCountry:KR"})
        offers = []
        for summary in data.get("itemSummaries", [])[:3]:
            if not isinstance(summary, dict):
                continue
            item_id = summary.get("itemId")
            if not isinstance(item_id, str) or len(item_id) > 100:
                continue
            item = _get("item/" + quote(item_id, safe=""), token, deadline)
            offer = _offer(product, item)
            if offer and offer["availability"] != "out_of_stock":
                offers.append(offer)
        return {"product_id": product["id"], "code": "ok" if offers else "no_match", "offers": offers}
    except (MarketError, requests.RequestException, ValueError, TypeError, KeyError) as error:
        return {"product_id": product["id"], "code": error.code if isinstance(error, MarketError) else "unavailable", "offers": []}


def offers_state(products=None):
    if products is None:
        products = load_catalog()[0]
    products = sorted(products, key=lambda p: p["id"])[:32]
    codes = []
    offers = []
    if not configured():
        codes = [{"product_id": p["id"], "code": "not_configured", "offers": []} for p in products]
    elif products:
        # Coalesce quote requests and never reuse results under another credential/catalog.
        with _lock:
            deadline = time.monotonic() + 16
            key_prefix = _fingerprint()
            pending = []
            for product in products:
                key = key_prefix + hashlib.sha256(json.dumps(product, sort_keys=True).encode()).hexdigest()
                cached = _cache.get(key)
                if cached and cached[1] > time.monotonic():
                    codes.append(cached[0])
                else:
                    pending.append((product, key))
            if pending:
                try:
                    token = _token()
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        futures = [(pool.submit(_quote_product, p, token, deadline), k) for p, k in pending]
                        for future, key in futures:
                            result = future.result()
                            ttl = max(30, min(get_settings().ebay_quote_ttl_seconds, 600)) if result["code"] in {"ok", "no_match"} else 30
                            _cache[key] = (result, time.monotonic() + ttl)
                            codes.append(result)
                except (MarketError, requests.RequestException) as error:
                    code = error.code if isinstance(error, MarketError) else "unavailable"
                    for product, key in pending:
                        result = {"product_id": product["id"], "code": code, "offers": []}
                        _cache[key] = (result, time.monotonic() + 30)
                        codes.append(result)
            if not get_settings().ebay_oauth_token and any(c["code"] == "auth_failed" for c in codes):
                _tokens.clear()
            if len(_cache) > 512:
                _cache.clear()
    for status in codes:
        offers.extend(status.get("offers", []))
    best = {}
    for offer in offers:
        if offer["availability"] != "in_stock" or offer["total"] is None:
            continue
        key = offer["product_id"] + ":" + offer["currency"]
        if key not in best or Decimal(offer["total"]) < Decimal(best[key]["total"]):
            best[key] = offer
    state = {"mode": "automatic" if configured() else "technical_only", "offers": sorted(offers, key=lambda o: (o["product_id"], o["id"])),
             "best": sorted(best.values(), key=lambda o: (o["product_id"], o["currency"])),
             "products": sorted([{"product_id": c["product_id"], "code": c["code"], "message": MESSAGES.get(c["code"], "판매 정보 확인됨")} for c in codes], key=lambda c: c["product_id"])}
    return state, hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def enrich(recommendations, state):
    for recommendation in recommendations:
        for candidate in recommendation.candidates:
            for part in candidate.parts:
                quotes = [o for o in state["offers"] if o["product_id"] == part.key]
                candidate.tradeoffs.extend(f"{part.name}: eBay {o['currency']} {o['amount']}, 한국 배송비 {o['shipping'] if o['shipping'] is not None else '미확인'}, 합계 {o['total'] or '미확인'}; 재고={o['availability']} (API 추정); 세금 제외; 조회={o['observed_at']}" for o in quotes[:3])
                if not quotes:
                    candidate.tradeoffs.append(f"{part.name}: 가격·재고 미확인. 기술적 후보이며 구매 가격을 추정하지 않습니다.")
    return recommendations
