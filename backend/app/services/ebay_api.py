"""
해외(eBay) 중고 부품 시세 수집 서비스.

우선순위:
  1) EBAY_OAUTH_TOKEN 이 설정되어 있으면 eBay 공식 Browse API 사용 (중고 condition 필터)
  2) 토큰이 없으면 eBay 검색 페이지를 직접 스크래핑 (LH_ItemCondition=3000, 중고)
  3) 둘 다 실패하면 빈 결과 반환 (호출 측에서 폴백 처리)

가격은 USD로 수집한 뒤 KRW로 환산해서 함께 반환합니다.
"""

import os
import re
import time
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

EBAY_OAUTH_TOKEN = os.getenv("EBAY_OAUTH_TOKEN")  # Browse API용 OAuth Application token
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_SCRAPE_URL = "https://www.ebay.com/sch/i.html"

# eBay condition ID: 3000=Used, 2500=Seller refurbished, 2000=Certified refurbished
USED_CONDITION_IDS = "3000|2500|2000"

# 환율: 명시적 환경변수 > 실시간 API > 기본값
DEFAULT_USD_KRW = 1380.0
_FX_CACHE: Dict[str, object] = {"table": None, "fetched_at": None}
_FX_TTL = timedelta(hours=6)
# USD 기준 기본 환율 테이블 (실시간 조회 실패 시 폴백)
_DEFAULT_RATE_TABLE = {"USD": 1.0, "KRW": DEFAULT_USD_KRW, "EUR": 0.92,
                       "GBP": 0.79, "JPY": 157.0, "CAD": 1.36, "AUD": 1.50}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# eBay는 쿠키 없는 첫 요청을 자주 403 처리한다. 세션으로 홈을 한 번 방문해
# 쿠키를 확보한 뒤 검색하면 차단 확률이 줄어든다.
_SESSION: Optional[requests.Session] = None


_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _new_session(ua: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    headers = dict(HEADERS)
    if ua:
        headers["User-Agent"] = ua
    session.headers.update(headers)
    try:
        session.get("https://www.ebay.com/", timeout=8)
    except Exception:
        pass
    return session


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = _new_session()
    return _SESSION


def _reset_session(ua: Optional[str] = None) -> requests.Session:
    global _SESSION
    _SESSION = _new_session(ua)
    return _SESSION


def _looks_blocked(html: str) -> bool:
    """eBay 봇 차단/캡차 인터럽션 페이지 여부."""
    head = html[:4000].lower()
    return (
        "pardon our interruption" in head
        or "captcha" in head
        or "are you a human" in head
    )

# 중고 시세 캐시 (24시간)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
USED_CACHE_FILE = DATA_DIR / "used_price_cache.json"
CACHE_EXPIRY_HOURS = 24


# ---------------------------------------------------------------------------
# 환율
# ---------------------------------------------------------------------------
def _get_rate_table() -> Dict[str, float]:
    """USD 기준 환율 테이블을 반환 (캐시 6시간). 실패 시 기본 테이블."""
    now = datetime.now()
    cached = _FX_CACHE.get("table")
    fetched_at = _FX_CACHE.get("fetched_at")
    if cached and fetched_at and now - fetched_at < _FX_TTL:
        return cached  # type: ignore[return-value]

    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        resp.raise_for_status()
        rates = resp.json().get("rates", {})
        if rates.get("KRW"):
            table = {k: float(v) for k, v in rates.items()}
            _FX_CACHE["table"] = table
            _FX_CACHE["fetched_at"] = now
            return table
    except Exception:
        pass

    return dict(_DEFAULT_RATE_TABLE)


def get_usd_krw_rate() -> float:
    """USD→KRW 환율을 반환. 환경변수 > 실시간 API > 기본값 순."""
    env_rate = os.getenv("USD_KRW_RATE")
    if env_rate:
        try:
            return float(env_rate)
        except ValueError:
            pass
    return _get_rate_table().get("KRW", DEFAULT_USD_KRW)


def convert_to_krw(amount: float, currency: str) -> int:
    """임의 통화 금액을 KRW로 변환."""
    currency = (currency or "USD").upper()
    if currency == "KRW":
        return int(round(amount))
    table = _get_rate_table()
    krw = table.get("KRW", DEFAULT_USD_KRW)
    cur_rate = table.get(currency)  # USD 1단위당 해당 통화 금액
    if not cur_rate:
        # 알 수 없는 통화는 USD로 가정
        cur_rate = 1.0
    usd = amount / cur_rate
    return int(round(usd * krw))


def usd_to_krw(usd: float, rate: Optional[float] = None) -> int:
    rate = rate if rate is not None else get_usd_krw_rate()
    return int(round(usd * rate))


# ---------------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------------
def _load_cache() -> dict:
    if USED_CACHE_FILE.exists():
        try:
            with open(USED_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(USED_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 가격 파싱 유틸
# ---------------------------------------------------------------------------
_PRICE_RE = re.compile(r"[\d,]+\.?\d*")

# eBay는 접속 지역에 따라 통화를 다르게 표기한다(예: 한국 IP는 'KRW...').
# 가격 텍스트 앞부분의 기호/코드로 통화를 판별한다.
def _detect_currency(text: str) -> str:
    t = text.upper()
    if "KRW" in t or "₩" in text or "원" in text:
        return "KRW"
    if "£" in text or "GBP" in t:
        return "GBP"
    if "€" in text or "EUR" in t:
        return "EUR"
    if "¥" in text or "JPY" in t:
        return "JPY"
    if t.lstrip().startswith("C $") or "CAD" in t:
        return "CAD"
    if t.lstrip().startswith("AU $") or t.lstrip().startswith("A $") or "AUD" in t:
        return "AUD"
    return "USD"  # 'US $' / '$' 기본


def _parse_price_text(text: str) -> Optional[float]:
    """'$123.45' 또는 'KRW 100,000 to 200,000' 형태에서 최저 금액(원 통화) 추출."""
    if not text:
        return None
    matches = _PRICE_RE.findall(text.replace(",", ""))
    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue
    if not values:
        return None
    # 'X to Y' 범위면 보수적으로 최저값 사용
    return min(values)


def _robust_low(values: List[float], pct: float = 0.20) -> float:
    """하위 백분위(기본 20%) 가격. 단일 쓰레기/오매칭 매물로 인한
    비현실적 최저가 왜곡을 줄인 '현실적 저가'."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) < 5:
        return s[0]
    idx = max(1, int(len(s) * pct))
    return s[idx]


def _parse_price_with_currency(text: str):
    """가격 텍스트에서 (금액, 통화코드) 반환."""
    amount = _parse_price_text(text)
    if amount is None:
        return None
    return amount, _detect_currency(text)


def _summarize(priced: List[tuple], source: str,
               sample_link: Optional[str], sample_title: Optional[str]) -> Dict:
    """priced: [(amount, currency), ...] → KRW 기준 요약."""
    if not priced:
        return {"found": False, "source": source, "error": "no used listings"}

    # 대표 통화(가장 많이 등장한 통화)
    currencies = [c for _, c in priced]
    currency = max(set(currencies), key=currencies.count)

    prices_krw = [convert_to_krw(amt, cur) for amt, cur in priced]
    rate = get_usd_krw_rate()

    lowest = min(prices_krw)
    highest = max(prices_krw)
    average = statistics.mean(prices_krw)
    median = statistics.median(prices_krw)
    robust_low = _robust_low(prices_krw)

    result = {
        "found": True,
        "source": source,
        "currency": currency,
        "usd_krw_rate": round(rate, 2),
        "listing_count": len(prices_krw),
        "lowest_price_krw": int(round(lowest)),
        "robust_low_krw": int(round(robust_low)),
        "highest_price_krw": int(round(highest)),
        "average_price_krw": int(round(average)),
        "median_price_krw": int(round(median)),
        "sample_link": sample_link,
        "sample_title": sample_title,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 원 통화가 USD면 USD 금액도 함께 제공 (참고용)
    if currency == "USD":
        usd_vals = [amt for amt, cur in priced if cur == "USD"]
        result["lowest_price_usd"] = round(min(usd_vals), 2)
        result["average_price_usd"] = round(statistics.mean(usd_vals), 2)
        result["highest_price_usd"] = round(max(usd_vals), 2)

    return result


# ---------------------------------------------------------------------------
# 1) eBay Browse API
# ---------------------------------------------------------------------------
def _search_browse_api(query: str, limit: int = 25) -> Optional[Dict]:
    if not EBAY_OAUTH_TOKEN:
        return None

    headers = {
        "Authorization": f"Bearer {EBAY_OAUTH_TOKEN}",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    params = {
        "q": query,
        "limit": limit,
        "filter": f"conditionIds:{{{USED_CONDITION_IDS}}},buyingOptions:{{FIXED_PRICE}}",
        "sort": "price",
    }

    try:
        resp = requests.get(EBAY_BROWSE_URL, headers=headers, params=params, timeout=8)
        if resp.status_code != 200:
            return None
        items = resp.json().get("itemSummaries", []) or []

        priced: List[tuple] = []
        sample_link = None
        sample_title = None
        for item in items:
            price = item.get("price", {})
            currency = price.get("currency") or "USD"
            try:
                value = float(price.get("value"))
            except (TypeError, ValueError):
                continue
            priced.append((value, currency))
            if sample_link is None:
                sample_link = item.get("itemWebUrl")
                sample_title = item.get("title")

        return _summarize(priced, "ebay_api", sample_link, sample_title)
    except Exception as exc:
        print(f"[ebay] Browse API 오류: {exc}")
        return None


# ---------------------------------------------------------------------------
# 2) eBay 검색 페이지 스크래핑
# ---------------------------------------------------------------------------
def _search_scrape(query: str, limit: int = 25) -> Dict:
    params = {
        "_nkw": query,
        "LH_ItemCondition": "3000|2500|2000",  # Used / Refurbished
        "LH_BIN": "1",                          # Buy It Now (고정가)
        "_sop": "15",                           # Price + shipping: lowest first
        "_ipg": "60",
    }

    # 봇 차단(Pardon Our Interruption) 감지 시 세션/UA 교체 후 백오프 재시도
    html = None
    for attempt in range(3):
        try:
            session = _get_session() if attempt == 0 else _reset_session(_USER_AGENTS[attempt % len(_USER_AGENTS)])
            resp = session.get(
                EBAY_SCRAPE_URL,
                params=params,
                timeout=10,
                headers={"Referer": "https://www.ebay.com/", "Sec-Fetch-Site": "same-origin"},
            )
            resp.raise_for_status()
            if not _looks_blocked(resp.text):
                html = resp.text
                break
        except Exception as exc:
            if attempt == 2:
                print(f"[ebay] 스크래핑 요청 오류: {exc}")
        time.sleep(1.5 * (attempt + 1))  # 1.5s, 3s 백오프

    if html is None:
        return {"found": False, "source": "ebay_scrape", "error": "blocked or unavailable"}

    try:
        soup = BeautifulSoup(html, "html.parser")

        items = soup.select("li.s-item, li.s-card")
        priced: List[tuple] = []
        sample_link = None
        sample_title = None

        for li in items:
            title_el = li.select_one(".s-item__title, .s-card__title")
            title = title_el.get_text(strip=True) if title_el else ""
            # eBay 첫 결과는 보통 'Shop on eBay' 플레이스홀더
            if not title or title.lower().startswith("shop on ebay"):
                continue

            price_el = li.select_one(".s-item__price, .s-card__price")
            parsed = _parse_price_with_currency(price_el.get_text(strip=True)) if price_el else None
            if not parsed or parsed[0] <= 0:
                continue

            priced.append(parsed)
            if sample_link is None:
                link_el = li.select_one("a.s-item__link, a.s-card__link, a[href*='/itm/']")
                sample_link = link_el.get("href") if link_el else None
                sample_title = title

            if len(priced) >= limit:
                break

        # 명백한 이상치(액세서리/케이블 등 극단 저가) 1차 필터링
        priced = _filter_outliers(priced)

        time.sleep(0.4)  # 매너 딜레이
        return _summarize(priced, "ebay_scrape", sample_link, sample_title)
    except Exception as exc:
        print(f"[ebay] 스크래핑 오류: {exc}")
        return {"found": False, "source": "ebay_scrape", "error": str(exc)}


def _filter_outliers(priced: List[tuple]) -> List[tuple]:
    """중앙값의 25% 미만인 항목은 액세서리로 간주하고 제거. priced=[(amount,currency)]."""
    if len(priced) < 4:
        return priced
    amounts = [a for a, _ in priced]
    med = statistics.median(amounts)
    floor = med * 0.25
    filtered = [(a, c) for a, c in priced if a >= floor]
    return filtered or priced


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
def search_used_price(query: str, use_cache: bool = True) -> Dict:
    """
    주어진 부품명의 해외(eBay) 중고 시세를 반환합니다.
    반환 구조는 _summarize 참조. found=False면 시세 미수집.
    """
    if not query:
        return {"found": False, "error": "empty query"}

    cache = _load_cache() if use_cache else {}
    now = datetime.now()

    if use_cache and query in cache:
        entry = cache[query]
        try:
            collected = datetime.fromisoformat(entry.get("collected_at", ""))
            if now - collected < timedelta(hours=CACHE_EXPIRY_HOURS) and entry.get("found"):
                entry = {**entry, "source": entry.get("source", "cache") + "+cache"}
                return entry
        except ValueError:
            pass

    # 1) 공식 API → 2) 스크래핑
    result = _search_browse_api(query)
    if not result or not result.get("found"):
        result = _search_scrape(query)

    if use_cache and result.get("found"):
        cache[query] = result
        try:
            _save_cache(cache)
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "RTX 4070"
    print(f"환율 USD→KRW: {get_usd_krw_rate():,.2f}")
    print(json.dumps(search_used_price(q, use_cache=False), indent=2, ensure_ascii=False))
