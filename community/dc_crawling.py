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

def normalize_keyword(part_name: str) -> List[str]:
    return [
        part_name,
        f"{part_name} 리뷰",
        f"{part_name} 가격",
        f"{part_name} 성능평가",
        f"{part_name} 중고",
        f"{part_name} 추천",
    ]

def crawl_dcinside_search(keyword, gallery_id=GALLERY_ID, max_pages=2):
    results = []

    for page in range(1, max_pages + 1):
        url = f"https://search.dcinside.com/post/p/{page}/q/{quote(keyword)}/gallery/{gallery_id}"
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
                "collected_at": datetime.now().isoformat(timespec="seconds")
            })

        time.sleep(random.uniform(1.5, 3.0))

    return results