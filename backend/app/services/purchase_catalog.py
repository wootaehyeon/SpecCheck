"""eBay product search using the existing Browse OAuth and quote validation."""

import hashlib
import re
import threading
import time
from decimal import Decimal
from urllib.parse import quote

import requests

from app.core.config import get_settings
from app.services import purchase_market as market

_cache = {}
_locks = [threading.RLock() for _ in range(32)]
MESSAGES = {
    "unconfigured": "eBay 실시간 가격 연결이 아직 준비되지 않았습니다. 아래 쇼핑몰에서 판매 가격을 확인해주세요.",
    "auth_failed": "eBay 판매 정보 연결을 확인하지 못했습니다. 아래 쇼핑몰 검색을 이용해주세요.",
    "rate_limited": "eBay 조회가 잠시 제한되었습니다. 잠시 후 다시 시도하거나 쇼핑몰 검색을 이용해주세요.",
    "unavailable": "eBay 판매 정보를 불러오지 못했습니다. 아래 쇼핑몰 검색을 이용해주세요.",
}


def _tokens(text):
    text = re.sub(r"(\d+(?:\.\d+)?)\s+(TB|GB)\b", r"\1\2", text, flags=re.I)
    for original, translated in {"삼성": "samsung", "메모리": "memory", "하이닉스": "hynix", "엔비디아": "nvidia", "지포스": "geforce"}.items():
        text = text.replace(original, translated)
    return set(re.findall(r"[a-z0-9가-힣]+", text.casefold()))


def _query_matches(product, title):
    query = product["name"]
    if re.search(r"\b(enclosure|adapter|heatsink|empty|defective|broken|parts only|not working)\b", title, re.I):
        return False
    ignored = {"nvidia", "geforce", "amd", "intel", "정품"}
    wanted = _tokens(query) - ignored
    actual = _tokens(title) - ignored
    variants = {"ti", "super", "xt", "xtx", "laptop", "mobile"}
    # Model suffixes and capacities cannot silently select a different variant.
    capacities = lambda value: {Decimal(n) * (1000 if unit.lower() == "tb" else 1)
                                for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(TB|GB)\b", value, re.I)}
    size = capacities(query)
    return bool(wanted) and wanted <= actual and wanted & variants == actual & variants and (not size or size == capacities(title))


def search_products(query: str) -> dict:
    query = query.strip()
    result = {"query": query, "source": "ebay_browse", "status": "empty", "products": []}
    if not query:
        return result
    if not market.configured():
        return {**result, "status": "unconfigured", "message": MESSAGES["unconfigured"]}
    key = market._fingerprint() + hashlib.sha256(query.casefold().encode()).hexdigest()
    with _locks[int(key[-2:], 16) % len(_locks)]:
        cached = _cache.get(key)
        if cached and cached[1] > time.monotonic():
            return {**cached[0], "cached": True}
        try:
            deadline = time.monotonic() + 12
            with market._lock:
                token = market._token()
            data = market._get("item_summary/search", token, deadline, {
                "q": query[:120], "limit": "12", "sort": "price",
                "filter": "buyingOptions:{FIXED_PRICE},conditionIds:{1000},deliveryCountry:KR",
            })
            summaries = data.get("itemSummaries", [])
            if not isinstance(summaries, list):
                raise market.MarketError("unavailable")
            seen = set()
            for summary in summaries[:3]:
                identifier = summary.get("itemId") if isinstance(summary, dict) else None
                if not isinstance(identifier, str) or not identifier or len(identifier) > 100 or identifier in seen:
                    continue
                seen.add(identifier)
                item = market._get("item/" + quote(identifier, safe=""), token, deadline)
                offer = market._offer({"id": "search-" + hashlib.sha256(query.encode()).hexdigest()[:16], "name": query}, item, verify=_query_matches)
                if offer and offer["availability"] != "out_of_stock":
                    result["products"].append({
                        **offer, "price": float(offer["amount"]), "mall": "eBay",
                    })
            result["status"] = "ok" if result["products"] else "empty"
        except (market.MarketError, requests.RequestException, ValueError, TypeError, KeyError) as error:
            # Never expose supplier error bodies, credentials, or partial prices.
            code = error.code if isinstance(error, market.MarketError) else "unavailable"
            result = {**result, "status": code, "products": [], "message": MESSAGES.get(code, MESSAGES["unavailable"])}
            if code == "auth_failed" and not get_settings().ebay_oauth_token:
                market._tokens.clear()
        ttl = max(30, min(get_settings().ebay_quote_ttl_seconds, 600)) if result["status"] in {"ok", "empty"} else 30
        if len(_cache) >= 256:
            _cache.clear()
        _cache[key] = (result, time.monotonic() + ttl)
        return {**result, "cached": False}
