import os
import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/shop.json"


def search_product(query: str) -> dict:
    """네이버 쇼핑 API로 최저가 검색. API 키 없으면 Mock 반환."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return _mock_price(query)

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 5, "sort": "asc"}

    try:
        res = requests.get(NAVER_SEARCH_URL, headers=headers, params=params, timeout=5)
        res.raise_for_status()
        items = res.json().get("items", [])
        if not items:
            return {"found": False, "query": query}

        top = items[0]
        return {
            "found": True,
            "query": query,
            "title": top.get("title", "").replace("<b>", "").replace("</b>", ""),
            "lowest_price": int(top.get("lprice", 0)),
            "link": top.get("link", ""),
            "image": top.get("image", ""),
            "mall_name": top.get("mallName", ""),
            "is_mock": False,
        }
    except Exception as e:
        return {"found": False, "query": query, "error": str(e)}


def _mock_price(query: str) -> dict:
    """API 키 없을 때 반환하는 Mock 데이터"""
    import random
    import hashlib

    # 쿼리 기반 시드로 일관된 Mock 가격 생성
    seed = int(hashlib.md5(query.encode()).hexdigest(), 16) % 10000
    random.seed(seed)
    price = random.randint(50000, 800000)
    encoded = requests.utils.quote(query)

    return {
        "found": True,
        "query": query,
        "title": query,
        "lowest_price": price,
        "link": f"https://search.shopping.naver.com/search/all?query={encoded}",
        "image": "",
        "mall_name": "Mock (API 키 미설정)",
        "is_mock": True,
    }
