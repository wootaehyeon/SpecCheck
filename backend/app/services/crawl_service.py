import time
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin, parse_qs, urlparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .integrated_crawl import integrate_market_data, get_naver_shopping_price, get_youtube_reviews, get_namu_wiki_info

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

# 실제 후기 기반 샘플 데이터 - 크롤링 실패 시 폴백용
REAL_MARKET_DATA = {
    "i9-13900K": [
        {
            "title": "i9-13900K 구입 1개월 후기 - 최고다!",
            "content": "정말 좋은 CPU입니다. 게임 성능이 탁월하고 멀티태스킹도 완벽합니다. 가성비 최고!",
            "sentiment": "positive"
        },
        {
            "title": "i9-13900K 너무 비싸지만 성능은 우수함",
            "content": "가격이 높지만 성능이 뛰어납니다. 발열이 조금 높지만 우수한 선택입니다.",
            "sentiment": "positive"
        },
        {
            "title": "i9-13900K 가격 비교 - 최저가는?",
            "content": "최신 고성능 CPU입니다. 가격을 비교해서 구입하면 합리적인 거래입니다.",
            "sentiment": "neutral"
        },
        {
            "title": "i9-13900K 구입하지 말 것 - 발열 문제 심각",
            "content": "발열 문제가 심각합니다. 쿨러 비용까지 들어서 비쌉니다. 아쉬워요.",
            "sentiment": "negative"
        }
    ],
    "RTX 4070": [
        {
            "title": "RTX 4070 구입 후 만족도 95점",
            "content": "훌륭한 그래픽카드입니다. 1440p 고주사율 게임도 완벽합니다. 최고의 선택!",
            "sentiment": "positive"
        },
        {
            "title": "RTX 4070 중고 구입 정보 - 성능 우수",
            "content": "중고로 구입했는데 성능이 좋습니다. 가격도 합리적이고 배치도 뛰어납니다.",
            "sentiment": "positive"
        },
        {
            "title": "RTX 4070 vs RTX 4060 성능 비교",
            "content": "RTX 4070은 무난한 선택입니다. 가격 대비 성능이 적절합니다.",
            "sentiment": "neutral"
        },
        {
            "title": "RTX 4070 너무 비싸다 - 추천 안 함",
            "content": "가격이 너무 비쌉니다. 성능이 괜찮지만 가성비는 형편없습니다.",
            "sentiment": "negative"
        }
    ],
    "DDR5 32GB": [
        {
            "title": "DDR5 32GB 램 최종 구입 후기 - 최고다",
            "content": "속도가 빠르고 안정적입니다. 게임과 작업 모두 우수합니다. 추천!",
            "sentiment": "positive"
        },
        {
            "title": "DDR5 32GB 가격 인하 - 지금이 기회",
            "content": "요즘 DDR5 가격이 저렴해졌습니다. 좋은 성능이고 안정적입니다.",
            "sentiment": "positive"
        },
        {
            "title": "DDR5 램 구입 고민 중",
            "content": "DDR5 램은 보통 정도의 성능입니다. 가격이 적절하면 무난한 선택입니다.",
            "sentiment": "neutral"
        }
    ],
    "라이젠 7 5700X": [
        {
            "title": "라이젠 7 5700X 2년 사용 후기 - 역시 좋다",
            "content": "안정적이고 성능이 좋습니다. 2년 동안 문제 없이 사용했습니다. 추천합니다!",
            "sentiment": "positive"
        },
        {
            "title": "라이젠 7 5700X는 여전히 가치 있는가?",
            "content": "최신 게임도 무난하게 처리합니다. 가격도 저렴해서 좋은 선택입니다.",
            "sentiment": "positive"
        },
        {
            "title": "라이젠 7 5700X 가격 비교",
            "content": "적절한 가격에 무난한 성능을 제공합니다. 시장 추천 제품입니다.",
            "sentiment": "neutral"
        }
    ],
    "RTX 4090": [
        {
            "title": "RTX 4090 최고급 그래픽카드 구입 후기",
            "content": "완벽합니다! 모든 게임이 초고주사율로 돌아갑니다. 최고의 선택입니다!",
            "sentiment": "positive"
        },
        {
            "title": "RTX 4090 가격 대비 성능 - 최고급 선택",
            "content": "비싸지만 성능이 최고입니다. 4K 게이밍에 최적입니다.",
            "sentiment": "positive"
        },
        {
            "title": "RTX 4090 구입 고민 - 과하지 않을까?",
            "content": "매우 고가입니다. 1440p 게이밍이면 과하지만 4K는 필요합니다.",
            "sentiment": "neutral"
        },
        {
            "title": "RTX 4090 너무 비싸고 소비전력 높음",
            "content": "가격이 매우 비싸고 전기료가 많이 나옵니다. 아쉽습니다.",
            "sentiment": "negative"
        }
    ]
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


def get_sample_market_reactions(part_name: str) -> List[Dict]:
    """부품명 기반 실제 후기 샘플 데이터 반환 (크롤링 실패 시 폴백)"""
    results = []

    # 정확한 매칭
    if part_name in REAL_MARKET_DATA:
        reviews = REAL_MARKET_DATA[part_name]
    else:
        # 부분 매칭 (예: "Intel i9-13900K" -> "i9-13900K")
        reviews = None
        for key in REAL_MARKET_DATA.keys():
            if key.lower() in part_name.lower() or part_name.lower() in key.lower():
                reviews = REAL_MARKET_DATA[key]
                break

        if not reviews:
            reviews = REAL_MARKET_DATA.get("i9-13900K", [])

    # 날짜 생성 (최근 1개월)
    sources = ["DC인사이드", "네이버 카페", "당근마켓", "오늘의집"]
    post_id = 1

    for idx, review in enumerate(reviews):
        days_ago = random.randint(1, 30)
        post_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        results.append({
            "post_id": f"sample-{part_name}-{post_id}",
            "keyword": part_name,
            "title": review["title"],
            "date": post_date,
            "url": f"https://gall.dcinside.com/board/lists?id={GALLERY_ID}",
            "source": sources[idx % len(sources)] + " (샘플)",
            "content": review["content"],
            "collected_at": datetime.now().isoformat(timespec="seconds")
        })
        post_id += 1

    return results


def crawl_related_parts(parts: List[dict], max_results: int = 20, per_part_limit: int = 5) -> List[dict]:
    """부품별 시장 반응 수집.

    실제 DC 크롤링을 우선 시도하고, 한 건도 수집하지 못한 부품만 샘플 데이터로 채운다.
    부품당 per_part_limit 건으로 제한해 전체 응답 시간을 관리한다.
    """
    search_terms = []
    for part in parts:
        name = getattr(part, 'name', None) if not isinstance(part, dict) else part.get('name')
        if name:
            search_terms.append(name)

    results = []
    seen = set()
    session = requests.Session()

    for part_name in search_terms:
        if len(results) >= max_results:
            break

        part_items = []
        try:
            part_items = crawl_dcinside_search(part_name, max_pages=1, session=session)
        except Exception as e:
            print(f"DC 크롤링 오류 ({part_name}): {e}")

        # 실제 크롤링 실패 시에만 샘플 데이터 사용
        if not part_items:
            part_items = get_sample_market_reactions(part_name)

        added = 0
        for item in part_items:
            if item["post_id"] in seen:
                continue
            seen.add(item["post_id"])
            results.append(item)
            added += 1
            if added >= per_part_limit or len(results) >= max_results:
                break

    return results[:max_results] if results else get_sample_market_reactions("i9-13900K")
