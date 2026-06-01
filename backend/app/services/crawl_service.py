import time
import random
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime
from typing import List

GALLERY_ID = "pridepc_new4"
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

WORD_REGEX = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def tokenize_part_name(part_name: str) -> List[str]:
    tokens = []
    for token in WORD_REGEX.findall(part_name or ""):
        normalized = token.strip()
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return tokens


def normalize_keywords(part_name: str) -> List[str]:
    part_name = (part_name or "").strip()
    keywords = [part_name] if part_name else []

    if part_name:
        keywords.extend([
            f"{part_name} 가격",
            f"{part_name} 중고",
            f"{part_name} 시세",
            f"{part_name} 구매",
            f"{part_name} 판매",
            f"{part_name} 정보"
        ])

        no_space = part_name.replace(' ', '')
        if no_space and no_space not in keywords:
            keywords.append(no_space)

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


def crawl_dcinside_search(keyword: str, gallery_id: str | None = GALLERY_ID, max_pages: int = 1) -> List[dict]:
    results = []

    for page in range(1, max_pages + 1):
        if gallery_id:
            url = f"https://search.dcinside.com/post/p/{page}/q/{quote(keyword)}/gallery/{gallery_id}"
        else:
            url = f"https://search.dcinside.com/post/p/{page}/q/{quote(keyword)}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception:
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

        time.sleep(random.uniform(1.5, 2.5))

    return results


def crawl_related_parts(parts: List[dict], max_results: int = 15) -> List[dict]:
    search_terms = []
    for part in parts:
        name = getattr(part, 'name', None) if not isinstance(part, dict) else part.get('name')
        if name:
            search_terms.append(name)

    results = []
    seen = set()

    for part_name in search_terms:
        for keyword in normalize_keywords(part_name):
            if len(results) >= max_results:
                break

            items = crawl_dcinside_search(keyword, max_pages=2)
            if not items:
                items = crawl_dcinside_search(keyword, gallery_id=None, max_pages=1)

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

    return results
