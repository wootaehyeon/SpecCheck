import time
import random
import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime

GALLERY_ID = "pridepc_new4"  # 일반 PC 갤러리
#https://gall.dcinside.com/board/lists/?id=pridepc_new4
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

WORD_REGEX = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def tokenize_part_name(part_name: str) -> list[str]:
    tokens: list[str] = []
    for token in WORD_REGEX.findall(part_name or ""):
        normalized = token.strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return tokens


def normalize_keyword(part_name: str) -> list[str]:
    part_name = (part_name or "").strip()
    keywords: list[str] = [part_name] if part_name else []

    if part_name:
        keywords.extend([
            f"{part_name} 가격",
            f"{part_name} 중고",
            f"{part_name} 시세"
        ])

        tokens = tokenize_part_name(part_name)
        for token in tokens:
            if token not in keywords:
                keywords.append(token)
            if len(token) > 1:
                price_token = f"{token} 가격"
                if price_token not in keywords:
                    keywords.append(price_token)

        for n in range(2, min(3, len(tokens) + 1)):
            for i in range(len(tokens) - n + 1):
                phrase = " ".join(tokens[i:i + n])
                if phrase not in keywords:
                    keywords.append(phrase)

    return keywords

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
            date = post.select_one(".date_time")
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