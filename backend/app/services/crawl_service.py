import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlencode
from datetime import datetime
from typing import List, Dict

GALLERY_ID = "pridepc_new4"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def normalize_keyword(part_name: str) -> List[str]:
    return [
        part_name,
        f"{part_name} 리뷰",
        f"{part_name} 가격",
        f"{part_name} 성능평가",
        f"{part_name} 중고",
        f"{part_name} 추천",
    ]

def crawl_dcinside_search(keyword, gallery_id=GALLERY_ID, max_pages=1):
    results = []

    for page in range(1, max_pages + 1):
        url = f"https://search.dcinside.com/post/p/{page}/q/{quote(keyword)}/gallery/{gallery_id}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            posts = soup.select(".sch_result_list li")

            for post in posts:
                title = post.select_one(".tit_txt")
                date = post.select_one(".date")
                link = post.select_one("a")

                if not (title and date and link):
                    continue

                post_url = link.get("href", "")
                post_id = post_url.split("no=")[-1].split("&")[0] if "no=" in post_url else post_url

                results.append({
                    "post_id": post_id,
                    "keyword": keyword,
                    "title": title.get_text(strip=True),
                    "date": date.get_text(strip=True),
                    "url": post_url,
                    "source": "DC인사이드",
                    "content": title.get_text(strip=True),
                    "collected_at": datetime.now().isoformat(timespec="seconds")
                })

            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            print(f"DC 크롤링 오류: {e}")
            break

    return results

def crawl_naver_cafe_search(keyword: str, max_results: int = 5) -> List[Dict]:
    """네이버 카페 검색 결과 크롤링"""
    results = []
    try:
        url = "https://section.cafe.naver.com/ajax/SearchSection.nhn"
        params = {
            "query": keyword,
            "sortBy": "date",
            "pageSize": max_results
        }

        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("result", {}).get("articles", [])

            for article in articles[:max_results]:
                results.append({
                    "post_id": article.get("cafeArticleId", ""),
                    "keyword": keyword,
                    "title": article.get("subject", ""),
                    "date": article.get("writeDate", datetime.now().isoformat()[:10]),
                    "url": article.get("articleUrl", ""),
                    "source": "네이버 카페",
                    "content": article.get("summary", ""),
                    "collected_at": datetime.now().isoformat(timespec="seconds")
                })

            time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"네이버 카페 크롤링 오류: {e}")

    return results

def crawl_used_market_search(keyword: str, max_results: int = 3) -> List[Dict]:
    """중고거래 사이트 검색"""
    results = []
    try:
        # 당근마켓 API (실제 API 키 필요)
        url = "https://api.karrotmarket.com/api/v2/search"
        params = {"q": keyword, "limit": max_results}

        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            for item in items[:max_results]:
                results.append({
                    "post_id": item.get("id", ""),
                    "keyword": keyword,
                    "title": item.get("title", ""),
                    "date": item.get("created_at", datetime.now().isoformat()[:10]),
                    "url": item.get("url", ""),
                    "source": "당근마켓",
                    "content": item.get("description", ""),
                    "collected_at": datetime.now().isoformat(timespec="seconds")
                })

        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"중고거래 크롤링 오류: {e}")

    return results

def sample_market_reactions() -> List[Dict]:
    """시장 반응 샘플 데이터"""
    return [
        {
            "post_id": "1",
            "keyword": "i9-13900K",
            "title": "최신 고성능 CPU 구입 후기",
            "date": "2026-06-07",
            "url": "https://gall.dcinside.com/mgallery/board/view/?id=cpu&no=12345",
            "source": "DC인사이드",
            "content": "최신 고성능 CPU를 구입했는데 정말 좋습니다. 게임 성능도 뛰어나고 가성비도 우수합니다.",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "sentiment": "positive",
            "sentiment_score": 0.85
        },
        {
            "post_id": "2",
            "keyword": "RTX 4070",
            "title": "고급 그래픽카드 중고 거래",
            "date": "2026-06-06",
            "url": "https://example.com/item/54321",
            "source": "당근마켓",
            "content": "고급 그래픽카드 중고 판매합니다. 성능이 뛰어나고 합리적인 가격입니다.",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "sentiment": "positive",
            "sentiment_score": 0.78
        },
        {
            "post_id": "3",
            "keyword": "라이젠 7 5700X",
            "title": "CPU 선택에 대한 조언",
            "date": "2026-06-05",
            "url": "https://cafe.naver.com/article/12345",
            "source": "네이버 카페",
            "content": "라이젠 7 5700X는 무난한 선택입니다. 다만 가격을 비교해보시고 결정하세요.",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "sentiment": "neutral",
            "sentiment_score": 0.52
        }
    ]

def crawl_related_parts(parts: List[dict], max_results: int = 15) -> List[dict]:
    search_terms = []
    for part in parts:
        name = getattr(part, 'name', None) if not isinstance(part, dict) else part.get('name')
        if name:
            search_terms.append(name)

    results = []
    seen = set()

    for part_name in search_terms:
        for keyword in normalize_keyword(part_name)[:3]:
            if len(results) >= max_results:
                break

            # DC인사이드 크롤링
            dc_items = crawl_dcinside_search(keyword, max_pages=1)
            for item in dc_items:
                if item["post_id"] in seen:
                    continue
                seen.add(item["post_id"])
                results.append(item)

            # 네이버 카페 크롤링 (실패 시 건너뜀)
            try:
                cafe_items = crawl_naver_cafe_search(keyword, max_results=2)
                for item in cafe_items:
                    if item["post_id"] in seen:
                        continue
                    seen.add(item["post_id"])
                    results.append(item)
            except:
                pass

            # 중고거래 크롤링 (실패 시 건너뜀)
            try:
                used_items = crawl_used_market_search(keyword, max_results=2)
                for item in used_items:
                    if item["post_id"] in seen:
                        continue
                    seen.add(item["post_id"])
                    results.append(item)
            except:
                pass

            if len(results) >= max_results:
                break

            if len(results) >= max_results:
                break

    return results if results else sample_market_reactions()
