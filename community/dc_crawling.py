"""DC인사이드 PC견적 갤러리 크롤러 (standalone).

backend/app/services/crawl_service.py 의 크롤링 로직과 동일하다.
디버깅은 같은 폴더의 debug_dc_crawl.py 를 사용한다:

    python debug_dc_crawl.py "RTX 4070"
"""
import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin, parse_qs, urlparse
from datetime import datetime
from typing import List, Dict, Optional

# PC견적 갤러리 (정식 갤러리 → gall.dcinside.com/board/lists)
GALLERY_ID = "pridepc_new4"
GALLERY_BASE = "https://gall.dcinside.com"
GALLERY_SEARCH_URL = f"{GALLERY_BASE}/board/lists/"
INTEGRATED_SEARCH_URL = "https://search.dcinside.com/post/p/{page}/q/{keyword}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": f"{GALLERY_BASE}/board/lists?id={GALLERY_ID}",
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


def _get(url: str, params: Optional[dict] = None, session: Optional[requests.Session] = None) -> Optional[requests.Response]:
    """공통 GET 요청. DC는 charset 헤더가 누락될 수 있어 UTF-8을 명시한다."""
    try:
        client = session or requests
        resp = client.get(url, params=params, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        resp.encoding = "utf-8"
        return resp
    except requests.RequestException as e:
        print(f"DC 요청 오류 ({url}): {e}")
        return None


def crawl_gallery_search(keyword: str, gallery_id: str = GALLERY_ID, max_blocks: int = 1,
                         per_block_limit: int = 10, session: Optional[requests.Session] = None) -> List[Dict]:
    """갤러리 내부 검색 (제목+내용 검색).

    https://gall.dcinside.com/board/lists/?id={gallery_id}&s_type=search_subject_memo&s_keyword={kw}
    지정한 갤러리(PC견적 갤러리)의 게시물만 수집하므로 목적에 맞는 결과를 얻는다.
    설문/광고/공지 행은 글 번호가 숫자가 아니므로 걸러낸다.
    DC 검색은 search_pos 단위 블록으로 페이지네이션되며, a.search_next 링크로 다음 블록을 따라간다.
    """
    results = []
    params = {
        "id": gallery_id,
        "s_type": "search_subject_memo",
        "s_keyword": keyword,
    }
    url = GALLERY_SEARCH_URL

    for block in range(max_blocks):
        resp = _get(url, params=params, session=session)
        if resp is None:
            break

        # 마이너 갤러리 잘못 접근 시 location.replace 스크립트만 내려온다
        if len(resp.text) < 500 and "location.replace" in resp.text:
            print(f"DC 갤러리 검색: {gallery_id} 는 이 경로의 갤러리가 아님 (리다이렉트 응답)")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("tr.ub-content")
        count_in_block = 0

        for tr in rows:
            num_el = tr.select_one(".gall_num")
            tit_el = tr.select_one(".gall_tit a")
            date_el = tr.select_one(".gall_date")

            # 설문/AD/공지 행 제외: 글 번호가 숫자인 일반 게시물만 수집
            if not (num_el and tit_el and date_el):
                continue
            post_no = num_el.get_text(strip=True)
            href = tit_el.get("href", "")
            if not post_no.isdigit() or "/board/view/" not in href:
                continue

            results.append({
                "post_id": f"{gallery_id}-{post_no}",
                "keyword": keyword,
                "title": tit_el.get_text(" ", strip=True),
                "date": date_el.get("title") or date_el.get_text(strip=True),
                "url": urljoin(GALLERY_BASE, href),
                "source": "DC인사이드 PC견적 갤러리",
                "content": tit_el.get_text(" ", strip=True),
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            })
            count_in_block += 1
            if count_in_block >= per_block_limit:
                break

        # 다음 검색 블록 (search_pos) 추적
        next_link = soup.select_one("a.search_next")
        if not next_link or block + 1 >= max_blocks:
            break
        next_qs = parse_qs(urlparse(next_link.get("href", "")).query)
        search_pos = next_qs.get("search_pos", [None])[0]
        if not search_pos:
            break
        params["search_pos"] = search_pos
        time.sleep(random.uniform(0.3, 0.6))

    return results


def crawl_integrated_search(keyword: str, max_pages: int = 1, per_page_limit: int = 5,
                            session: Optional[requests.Session] = None) -> List[Dict]:
    """DC인사이드 통합검색 (전체 갤러리 대상).

    갤러리 내부 검색에서 결과가 부족할 때 보조로 사용한다.
    본문 미리보기(p.link_dsc_txt)를 content 로 수집해 감정분석 정확도를 높인다.
    셀렉터: a.tit_txt(제목/링크), span.date_time(날짜), a.sub_txt(갤러리명)
    """
    results = []

    for page in range(1, max_pages + 1):
        url = INTEGRATED_SEARCH_URL.format(page=page, keyword=quote(keyword))
        resp = _get(url, session=session)
        if resp is None:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        posts = soup.select(".sch_result_list li")
        count_in_page = 0

        for post in posts:
            title_el = post.select_one("a.tit_txt")
            date_el = post.select_one(".date_time")
            desc_el = post.select_one("p.link_dsc_txt")
            gallery_el = post.select_one("a.sub_txt")

            if not (title_el and date_el):
                continue

            post_url = title_el.get("href", "")
            if "/board/view/" not in post_url:
                continue

            qs = parse_qs(urlparse(post_url).query)
            gall_id = qs.get("id", ["?"])[0]
            post_no = qs.get("no", [""])[0]
            gallery_name = gallery_el.get_text(strip=True) if gallery_el else gall_id

            results.append({
                "post_id": f"{gall_id}-{post_no}" if post_no else post_url,
                "keyword": keyword,
                "title": title_el.get_text(" ", strip=True),
                "date": date_el.get_text(strip=True),
                "url": post_url,
                "source": f"DC인사이드 ({gallery_name})",
                "content": desc_el.get_text(" ", strip=True) if desc_el else title_el.get_text(" ", strip=True),
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            })
            count_in_page += 1
            if count_in_page >= per_page_limit:
                break

        if page < max_pages:
            time.sleep(random.uniform(0.3, 0.6))

    return results


# 통합검색 보충 시 PC 부품 시장 반응과 관련 있는 갤러리를 우선한다
PC_RELATED_GALLERY_TERMS = ("컴퓨터", "PC", "pc", "견적", "노트북", "그래픽", "하드웨어", "조립", "오버클럭", "중고")


def _is_pc_related(item: Dict) -> bool:
    source = item.get("source", "")
    return any(term in source for term in PC_RELATED_GALLERY_TERMS)


def crawl_dcinside_search(keyword: str, gallery_id: str = GALLERY_ID, max_pages: int = 1,
                          min_results: int = 3, session: Optional[requests.Session] = None) -> List[Dict]:
    """키워드에 대한 DC인사이드 시장 반응 수집.

    1차: PC견적 갤러리 내부 검색 (목적에 정확히 맞는 결과)
    2차: 결과가 부족하면 통합검색으로 보충하되, PC 관련 갤러리 글을 우선 채택
         (본문 미리보기가 있어 감정분석에 유리)
    """
    results = crawl_gallery_search(keyword, gallery_id=gallery_id, max_blocks=max_pages, session=session)

    if len(results) < min_results:
        seen_urls = {r["url"] for r in results}
        extra = crawl_integrated_search(keyword, max_pages=1, session=session)
        extra = [item for item in extra if item["url"] not in seen_urls]
        # PC 관련 갤러리 글을 먼저, 그래도 부족하면 나머지로 채움
        ranked = [item for item in extra if _is_pc_related(item)] + \
                 [item for item in extra if not _is_pc_related(item)]
        for item in ranked:
            if len(results) >= min_results + 2:
                break
            results.append(item)

    return results
