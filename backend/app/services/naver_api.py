import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_SHOP_API_URL = "https://openapi.naver.com/v1/search/shop.json"

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

if __name__ == "__main__":
    # Test
    print(search_lowest_price("AMD Ryzen 5 5600X"))
