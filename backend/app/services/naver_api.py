import os
import re
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_SHOP_API_URL = "https://openapi.naver.com/v1/search/shop.json"


def _plain_title(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()

def search_lowest_price(query: str) -> dict:
    """
    네이버 쇼핑 API를 검색하여 최저가를 반환합니다.
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "Naver API keys are missing.", "price_krw": None}

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    
    # 검색 정확도를 높이기 위해 불필요한 단어 제거 (옵션)
    # query_str = query.replace("Laptop GPU", "").strip()

    params = {
        "query": query,
        "display": 5,      # 5개 결과만
        "sort": "sim"      # 정확도순. "asc"로 하면 엉뚱한 부품/케이스가 최저가로 나올 수 있음.
    }

    try:
        response = requests.get(NAVER_SHOP_API_URL, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            return {"error": "No items found", "price_krw": None}

        # 검색 결과 중 가격이 있는 가장 첫 번째(정확도가 높은) 항목의 최저가 사용
        # (sim 정렬이라도 lprice가 있는 것을 찾음)
        for item in items:
            lprice = item.get("lprice")
            if lprice and lprice.isdigit():
                return {
                    "price_krw": int(lprice),
                    "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                    "link": item.get("link", "")
                }
                
        return {"error": "No valid price found", "price_krw": None}

    except Exception as e:
        return {"error": str(e), "price_krw": None}

def search_market_prices(query: str) -> dict:
    """
    네이버 쇼핑 API를 검색하여 최저가, 최고가, 평균가 및 구매 링크를 반환합니다.
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "Naver API keys are missing."}

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    params = {
        "query": query,
        "display": 20,     # 20개 결과 수집하여 평균 도출
        "sort": "sim"
    }

    try:
        response = requests.get(NAVER_SHOP_API_URL, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            return {"error": "No items found"}

        priced_items = []

        for item in items:
            lprice_str = item.get("lprice")
            if lprice_str and lprice_str.isdigit():
                price = int(lprice_str)
                # 너무 터무니없이 낮은 가격(예: 부품 케이스, 쿨러 등)을 필터링하는 로직이 필요할 수 있음
                # 여기서는 단순 수집
                priced_items.append({
                    "price": price,
                    "title": _plain_title(item.get("title", "")),
                    "link": item.get("link", ""),
                    "mall": item.get("mallName", ""),
                })

        if not priced_items:
            return {"error": "No valid prices found"}

        # Keep the representative price range stable when one search result is
        # an accessory or a marketplace data error. This is intentionally a
        # conservative trim, not a product-ranking algorithm.
        raw_prices = sorted(item["price"] for item in priced_items)
        median = raw_prices[len(raw_prices) // 2]
        filtered = [
            item for item in priced_items
            if median * 0.35 <= item["price"] <= median * 3
        ] or priced_items
        lowest_item = min(filtered, key=lambda item: item["price"])
        prices = [item["price"] for item in filtered]
        lowest_price = min(prices)
        highest_price = max(prices)
        average_price = sum(prices) // len(prices)

        return {
            "lowest_price": lowest_price,
            "highest_price": highest_price,
            "average_price": average_price,
            "purchase_link": lowest_item["link"],
            "product_title": lowest_item["title"],
            "mall": lowest_item["mall"],
            "listing_count": len(filtered),
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Test
    print("Lowest Price API:")
    print(search_lowest_price("AMD Ryzen 5 5600X"))
    print("\nMarket Prices API:")
    print(search_market_prices("AMD Ryzen 5 5600X"))
