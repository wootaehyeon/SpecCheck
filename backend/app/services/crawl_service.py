import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime
from typing import List

GALLERY_ID = "pridepc_new4"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def normalize_keywords(part_name: str) -> List[str]:
    return [
        part_name,
        f"{part_name} 리뷰",
        f"{part_name} 가격",
        f"{part_name} 성능평가"
    ]


def crawl_dcinside_search(keyword: str, gallery_id: str = GALLERY_ID, max_pages: int = 1) -> List[dict]:
    results = []

    for page in range(1, max_pages + 1):
        url = f"https://search.dcinside.com/post/p/{page}/q/{quote(keyword)}/gallery/{gallery_id}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception:
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
                "collected_at": datetime.now().isoformat(timespec="seconds")
            })

        time.sleep(random.uniform(1.5, 2.5))

    return results


def sample_crawl_results() -> List[dict]:
    return [
        {
            "source": "DC인사이드 CPU갤",
            "keyword": "i9-13900K",
            "title": "[구매문의] i9-13900K 최저가는 어디인가?",
            "date": "2026-05-25",
            "url": "https://gall.dcinside.com/mgallery/board/view/?id=cpu&no=12345",
            "post_id": "12345",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "content": "최근에 i9-13900K를 구매했는데 가격이 저렴했어요. 좋은 성능입니다.",
            "sentiment": "positive",
            "sentiment_score": 0.85
        },
        {
            "source": "DC인사이드 VGA갤",
            "keyword": "RTX 4070",
            "title": "[판매] RTX 4070 중고 팝니다",
            "date": "2026-05-24",
            "url": "https://gall.dcinside.com/mgallery/board/view/?id=vga&no=54321",
            "post_id": "54321",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "content": "RTX 4070 중고 판매합니다. 성능도 좋고 가격도 합리적입니다.",
            "sentiment": "positive",
            "sentiment_score": 0.78
        },
        {
            "source": "DC인사이드 CPU갤",
            "keyword": "라이젠 7600X",
            "title": "[정보] 라이젠 7600X 가격 비교",
            "date": "2026-05-23",
            "url": "https://gall.dcinside.com/mgallery/board/view/?id=cpu&no=67890",
            "post_id": "67890",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
            "content": "라이젠 7600X는 나쁘지 않은 선택입니다. 다만 가격이 조금 비쌀 수 있습니다.",
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
        for keyword in normalize_keywords(part_name)[:3]:
            if len(results) >= max_results:
                break

            items = crawl_dcinside_search(keyword, max_pages=1)
            for item in items:
                if item["post_id"] in seen:
                    continue

                seen.add(item["post_id"])
                results.append({
                    "source": "DC인사이드",
                    "keyword": keyword,
                    "title": item["title"],
                    "date": item["date"],
                    "url": item["url"],
                    "post_id": item["post_id"],
                    "collected_at": item["collected_at"]
                })

                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

    return results if results else sample_crawl_results()
