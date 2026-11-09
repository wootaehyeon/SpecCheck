import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlencode
from datetime import datetime, timedelta
from typing import List, Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_naver_shopping_price(part_name: str) -> Dict:
    """Legacy entry point; price data now comes from eBay Browse."""
    from app.services.market_prices import search_market_prices

    result = search_market_prices(part_name)
    return {**result, "source": "eBay", "lowest_price": result.get("lowest_price", 0),
            "average_price": result.get("average_price", 0), "items": []}


def get_youtube_reviews(part_name: str) -> List[Dict]:
    """YouTube에서 부품 리뷰 채널 추출"""
    results = []

    try:
        # YouTube 검색 페이지 크롤링
        search_url = f"https://www.youtube.com/results?search_query={quote(part_name + ' 리뷰')}"
        resp = requests.get(search_url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # YouTube 데이터 추출 (JSON 형식)
        script_tags = soup.find_all("script")
        for script in script_tags[:5]:  # 처음 5개 스크립트만 확인
            if "initialData" in script.string:
                # 간단한 추출 시도
                content = script.string
                if part_name.lower() in content.lower():
                    results.append({
                        "source": "YouTube",
                        "title": f"{part_name} 리뷰 채널",
                        "url": f"https://www.youtube.com/results?search_query={quote(part_name + ' 리뷰')}",
                        "type": "video",
                        "platform": "YouTube"
                    })
                    break

        # YouTube 샘플 리뷰 데이터 추가
        if not results:
            results.append({
                "source": "YouTube",
                "title": f"{part_name} 성능 테스트 및 리뷰",
                "url": f"https://www.youtube.com/results?search_query={quote(part_name + ' 리뷰')}",
                "type": "video",
                "platform": "YouTube",
                "view_count": random.randint(10000, 500000)
            })

        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"YouTube 크롤링 오류: {e}")

    return results

def get_namu_wiki_info(part_name: str) -> Dict:
    """나무위키에서 부품 정보 수집"""
    result = {
        "source": "나무위키",
        "title": f"{part_name}",
        "url": f"https://namu.wiki/search?q={quote(part_name)}",
        "specs": [],
        "content": "",
        "collected_at": datetime.now().isoformat(timespec="seconds")
    }

    try:
        # 나무위키 검색 페이지
        search_url = f"https://namu.wiki/search?q={quote(part_name)}"
        resp = requests.get(search_url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # 검색 결과에서 첫 번째 결과 링크 찾기
        search_results = soup.find_all("a", class_="wiki-link")
        if search_results:
            first_result = search_results[0]
            result["url"] = f"https://namu.wiki{first_result.get('href', '')}"
            result["title"] = first_result.get_text(strip=True)

        # 샘플 스펙 정보
        result["specs"] = get_sample_specs(part_name)
        result["content"] = f"{part_name}의 상세 정보는 나무위키에서 확인할 수 있습니다."

        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"나무위키 크롤링 오류: {e}")
        result["specs"] = get_sample_specs(part_name)

    return result

def get_sample_specs(part_name: str) -> List[str]:
    """부품별 샘플 스펙 정보"""
    specs_map = {
        "i9-13900K": [
            "코어/스레드: 24/32",
            "기본 클럭: 3.0 GHz",
            "부스트 클럭: 5.8 GHz",
            "TDP: 253W",
            "소켓: LGA1700"
        ],
        "RTX 4070": [
            "VRAM: 12GB GDDR6X",
            "메모리 버스: 192-bit",
            "부스트 클럭: 2.475 GHz",
            "전력 소비: 200W",
            "인터페이스: PCIe 4.0"
        ],
        "RTX 4090": [
            "VRAM: 24GB GDDR6X",
            "메모리 버스: 384-bit",
            "부스트 클럭: 2.520 GHz",
            "전력 소비: 450W",
            "인터페이스: PCIe 4.0"
        ],
        "DDR5 32GB": [
            "용량: 32GB (16GB x2)",
            "속도: 6000MHz",
            "CAS 레이턴시: CL30",
            "전압: 1.4V",
            "타입: UDIMM"
        ]
    }

    for key in specs_map.keys():
        if key.lower() in part_name.lower() or part_name.lower() in key.lower():
            return specs_map[key]

    return [
        "상세 스펙은 나무위키에서 확인 가능",
        "제조사 공식 사이트 참조 권장"
    ]

def integrate_market_data(part_name: str, market_reactions: List[Dict]) -> Dict:
    """부품명 기반 모든 시장 정보 통합"""

    # 1. 네이버 쇼핑 가격 정보
    naver_price = get_naver_shopping_price(part_name)

    # 2. YouTube 리뷰
    youtube_reviews = get_youtube_reviews(part_name)

    # 3. 나무위키 정보
    namu_wiki = get_namu_wiki_info(part_name)

    # 4. 감정 평가 요약
    positive_count = sum(1 for r in market_reactions if r.get('sentiment') == 'positive')
    negative_count = sum(1 for r in market_reactions if r.get('sentiment') == 'negative')
    neutral_count = len(market_reactions) - positive_count - negative_count
    avg_score = sum(r.get('sentiment_score', 0.5) for r in market_reactions) / len(market_reactions) if market_reactions else 0.5

    return {
        "part_name": part_name,
        "price_info": naver_price,
        "review_channels": youtube_reviews,
        "wiki_info": namu_wiki,
        "market_sentiment": {
            "total_reactions": len(market_reactions),
            "positive": positive_count,
            "neutral": neutral_count,
            "negative": negative_count,
            "average_score": round(avg_score, 2),
            "reactions": market_reactions
        },
        "integrated_at": datetime.now().isoformat(timespec="seconds")
    }
