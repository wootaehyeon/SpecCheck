import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from app.services.naver_api import search_lowest_price

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PRICE_CACHE_FILE = DATA_DIR / "price_cache.json"

CACHE_EXPIRY_HOURS = 24

def _load_cache() -> dict:
    if os.path.exists(PRICE_CACHE_FILE):
        try:
            with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PRICE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4, ensure_ascii=False)

def get_price(component_name: str) -> dict:
    """
    주어진 부품명의 가격 정보를 반환합니다.
    캐시가 유효하면 캐시된 가격을 반환하고,
    그렇지 않으면 네이버 API를 통해 새로 조회한 후 캐시를 업데이트합니다.
    """
    if not component_name:
        return {"price_krw": None, "source": "None"}

    cache = _load_cache()
    now = datetime.now()

    if component_name in cache:
        cached_data = cache[component_name]
        try:
            updated_at = datetime.fromisoformat(cached_data.get("updated_at", ""))
            # 캐시가 만료되지 않았고 가격 정보가 있는 경우
            if now - updated_at < timedelta(hours=CACHE_EXPIRY_HOURS):
                return {
                    "price_krw": cached_data.get("price_krw"),
                    "title": cached_data.get("title"),
                    "link": cached_data.get("link"),
                    "source": "cache",
                    "updated_at": cached_data.get("updated_at")
                }
        except ValueError:
            pass # 날짜 파싱 오류가 나면 새로 조회

    # 캐시에 없거나 만료된 경우 API 조회
    api_result = search_lowest_price(component_name)
    
    if api_result.get("price_krw"):
        # 캐시 업데이트
        cache[component_name] = {
            "price_krw": api_result["price_krw"],
            "title": api_result.get("title"),
            "link": api_result.get("link"),
            "updated_at": now.isoformat()
        }
        _save_cache(cache)
        
        return {
            "price_krw": api_result["price_krw"],
            "title": api_result.get("title"),
            "link": api_result.get("link"),
            "source": "api",
            "updated_at": now.isoformat()
        }
    
    # API에서 가격을 못 찾은 경우
    return {
        "price_krw": None,
        "error": api_result.get("error", "Not found"),
        "source": "api"
    }
