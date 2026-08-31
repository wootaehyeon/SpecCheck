"""DC인사이드 크롤링 디버그 도구.

크롤링이 안 될 때 어느 단계(요청/인코딩/셀렉터/필터)에서 실패하는지 단계별로 진단한다.

사용법:
    python debug_dc_crawl.py                          # 기본 키워드(RTX 4070)로 전체 진단
    python debug_dc_crawl.py "i5-14600K"              # 키워드 지정
    python debug_dc_crawl.py "RTX 4070" --gallery-only    # 갤러리 검색만
    python debug_dc_crawl.py "RTX 4070" --integrated-only # 통합검색만
    python debug_dc_crawl.py "RTX 4070" --save-html       # 응답 HTML 을 파일로 저장
    python debug_dc_crawl.py "RTX 4070" --pages 3         # 검색 블록(페이지) 수

진단 항목:
    1. HTTP 응답 (상태코드, 인코딩, 본문 크기, 리다이렉트 여부)
    2. 셀렉터 매칭 수 (전체 행 / 일반 게시물 / 제외된 행)
    3. 파싱된 결과 샘플
    4. 페이지네이션 (search_next / search_pos)
"""
import sys
import io
import argparse
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949)에서 한글/특수문자 출력 깨짐 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, parse_qs, urlparse

from dc_crawling import (
    GALLERY_ID,
    GALLERY_SEARCH_URL,
    INTEGRATED_SEARCH_URL,
    HEADERS,
    crawl_gallery_search,
    crawl_integrated_search,
    crawl_dcinside_search,
)

DUMP_DIR = Path(__file__).parent / "debug_html"


def hr(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def save_html(name: str, text: str):
    DUMP_DIR.mkdir(exist_ok=True)
    path = DUMP_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.html"
    path.write_text(text, encoding="utf-8")
    print(f"  [저장] {path}")


def debug_request(url: str, params: dict = None, save: bool = False, name: str = "resp"):
    """요청 단계 진단: 상태코드/인코딩/크기/리다이렉트."""
    print(f"  URL: {url}")
    if params:
        print(f"  파라미터: {params}")
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
    except requests.RequestException as e:
        print(f"  [실패] 요청 예외: {e}")
        return None

    print(f"  상태코드: {resp.status_code}")
    print(f"  최종 URL: {resp.url}")
    print(f"  인코딩(헤더): {resp.encoding} / 추정: {resp.apparent_encoding}")
    print(f"  본문 크기: {len(resp.text):,} bytes")

    resp.encoding = "utf-8"

    if resp.status_code != 200:
        print("  [실패] 200 이 아님 — 차단되었거나 URL 이 잘못됨")
        if save:
            save_html(f"{name}_error", resp.text)
        return None

    if len(resp.text) < 500 and "location.replace" in resp.text:
        print(f"  [실패] 리다이렉트 스크립트만 수신 — 갤러리 종류(정식/마이너) 또는 ID 확인 필요")
        print(f"  응답 내용: {resp.text[:200]}")
        return None

    if save:
        save_html(name, resp.text)

    return resp


def debug_gallery_search(keyword: str, gallery_id: str, save: bool, pages: int):
    hr(f"1단계: 갤러리 내부 검색 진단 (갤러리: {gallery_id})")
    params = {"id": gallery_id, "s_type": "search_subject_memo", "s_keyword": keyword}
    resp = debug_request(GALLERY_SEARCH_URL, params=params, save=save, name="gallery_search")
    if resp is None:
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    rows = soup.select("tr.ub-content")
    print(f"\n  셀렉터 'tr.ub-content' 매칭: {len(rows)} 행")
    if not rows:
        print("  [실패] 게시물 행이 없음 — DC 페이지 구조가 바뀌었을 가능성")
        print("  페이지에 존재하는 table/tr 관련 클래스:")
        classes = set()
        for el in soup.find_all(["table", "tr", "tbody"], class_=True):
            classes.update(el.get("class"))
        print(f"    {sorted(classes)}")
        return

    real, skipped = [], []
    for tr in rows:
        num_el = tr.select_one(".gall_num")
        tit_el = tr.select_one(".gall_tit a")
        date_el = tr.select_one(".gall_date")
        num = num_el.get_text(strip=True) if num_el else "?"
        if num_el and tit_el and date_el and num.isdigit() and "/board/view/" in tit_el.get("href", ""):
            real.append(tr)
        else:
            skipped.append(num)

    print(f"  일반 게시물: {len(real)} 건 / 제외(설문·광고·공지 등): {len(skipped)} 건 {skipped[:5]}")

    if not real:
        print("  [경고] 일반 게시물이 0건 — 검색 결과가 없거나 필터 조건 확인 필요")

    print("\n  파싱 샘플 (최대 3건):")
    for tr in real[:3]:
        tit = tr.select_one(".gall_tit a")
        date = tr.select_one(".gall_date")
        print(f"    - 번호: {tr.select_one('.gall_num').get_text(strip=True)}")
        print(f"      제목: {tit.get_text(' ', strip=True)[:60]}")
        print(f"      날짜: {date.get('title') or date.get_text(strip=True)}")
        print(f"      링크: {tit.get('href', '')[:80]}")

    next_link = soup.select_one("a.search_next")
    if next_link:
        qs = parse_qs(urlparse(next_link.get("href", "")).query)
        print(f"\n  페이지네이션: search_next 있음 (search_pos={qs.get('search_pos', ['?'])[0]})")
    else:
        print("\n  페이지네이션: search_next 없음 (마지막 블록)")

    hr(f"1단계 결과: crawl_gallery_search('{keyword}', max_blocks={pages})")
    items = crawl_gallery_search(keyword, gallery_id=gallery_id, max_blocks=pages)
    print(f"  수집: {len(items)} 건")
    for it in items[:5]:
        print(f"    - [{it['date']}] {it['title'][:50]}")


def debug_integrated_search(keyword: str, save: bool):
    hr("2단계: 통합검색 진단 (전체 갤러리)")
    url = INTEGRATED_SEARCH_URL.format(page=1, keyword=quote(keyword))
    resp = debug_request(url, save=save, name="integrated_search")
    if resp is None:
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    posts = soup.select(".sch_result_list li")
    print(f"\n  셀렉터 '.sch_result_list li' 매칭: {len(posts)} 건")
    if not posts:
        print("  [실패] 결과 목록 없음 — DC 통합검색 구조가 바뀌었을 가능성")
        classes = set()
        for el in soup.find_all(["ul", "div"], class_=True):
            classes.update(el.get("class"))
        related = sorted(c for c in classes if "sch" in c or "result" in c or "list" in c)
        print(f"  관련 클래스 후보: {related}")
        return

    ok = sum(1 for p in posts if p.select_one("a.tit_txt") and p.select_one(".date_time"))
    print(f"  제목(a.tit_txt)+날짜(.date_time) 모두 있는 항목: {ok} / {len(posts)}")
    if ok == 0:
        print("  [실패] 셀렉터 불일치 — 첫 항목 구조:")
        print(posts[0].prettify()[:800])
        return

    hr(f"2단계 결과: crawl_integrated_search('{keyword}')")
    items = crawl_integrated_search(keyword, max_pages=1)
    print(f"  수집: {len(items)} 건")
    for it in items[:5]:
        print(f"    - [{it['date']}] ({it['source']}) {it['title'][:40]}")
        print(f"      내용: {it['content'][:60]}")


def debug_combined(keyword: str, gallery_id: str, pages: int):
    hr(f"3단계: 통합 동작 확인 crawl_dcinside_search('{keyword}')")
    items = crawl_dcinside_search(keyword, gallery_id=gallery_id, max_pages=pages)
    print(f"  최종 수집: {len(items)} 건")
    by_source = {}
    for it in items:
        by_source[it["source"]] = by_source.get(it["source"], 0) + 1
    for src, cnt in by_source.items():
        print(f"    {src}: {cnt} 건")
    print()
    for it in items[:10]:
        print(f"    - [{it['date']}] {it['title'][:50]}")
        print(f"      {it['url'][:90]}")

    if not items:
        print("  [실패] 수집 결과 0건 — 위 1·2단계 출력에서 실패 지점을 확인하세요")


def main():
    parser = argparse.ArgumentParser(description="DC인사이드 크롤링 디버그")
    parser.add_argument("keyword", nargs="?", default="RTX 4070", help="검색 키워드 (기본: RTX 4070)")
    parser.add_argument("--gallery", default=GALLERY_ID, help=f"갤러리 ID (기본: {GALLERY_ID})")
    parser.add_argument("--pages", type=int, default=1, help="검색 블록 수 (기본: 1)")
    parser.add_argument("--gallery-only", action="store_true", help="갤러리 검색만 진단")
    parser.add_argument("--integrated-only", action="store_true", help="통합검색만 진단")
    parser.add_argument("--save-html", action="store_true", help="응답 HTML 을 debug_html/ 에 저장")
    args = parser.parse_args()

    print(f"키워드: {args.keyword} / 갤러리: {args.gallery} / 블록: {args.pages}")
    print(f"실행 시각: {datetime.now().isoformat(timespec='seconds')}")

    if not args.integrated_only:
        debug_gallery_search(args.keyword, args.gallery, args.save_html, args.pages)
    if not args.gallery_only:
        debug_integrated_search(args.keyword, args.save_html)
    if not args.gallery_only and not args.integrated_only:
        debug_combined(args.keyword, args.gallery, args.pages)

    print("\n진단 완료.")


if __name__ == "__main__":
    main()
