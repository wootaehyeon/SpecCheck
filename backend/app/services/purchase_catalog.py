"""네이버쇼핑 실상품만 반환하며 API 미설정/실패 시 예시 상품을 만들지 않는다."""

import html
import re
from urllib.parse import urlsplit

import requests

from app.services import naver_api


def search_products(query: str) -> dict:
    result = {'query': query, 'source': 'naver', 'status': 'empty', 'products': []}
    if not query:
        return result
    if not naver_api.NAVER_CLIENT_ID or not naver_api.NAVER_CLIENT_SECRET:
        return {**result, 'status': 'unconfigured'}
    try:
        response = requests.get(
            naver_api.NAVER_SHOP_API_URL,
            headers={
                'X-Naver-Client-Id': naver_api.NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': naver_api.NAVER_CLIENT_SECRET,
            },
            params={'query': query, 'display': 12, 'sort': 'sim'},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get('items', []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return {**result, 'status': 'unavailable'}
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = html.unescape(re.sub(r'<[^>]*>', '', str(item.get('title') or ''))).strip()
            link = str(item.get('link') or '')
            try:
                price = int(item.get('lprice') or 0)
                url = urlsplit(link)
                if url.scheme != 'https' or not url.hostname or url.username or url.password:
                    continue
            except (TypeError, ValueError):
                continue
            if not title or price <= 0 or link in seen:
                continue
            seen.add(link)
            result['products'].append({
                'title': title, 'price': price, 'url': link,
                'mall': str(item.get('mallName') or '네이버쇼핑'),
            })
        result['status'] = 'ok' if result['products'] else 'empty'
        return result
    except (requests.RequestException, ValueError, TypeError):
        # 공급자 오류에 포함될 수 있는 자격 증명이나 내부 응답을 노출하지 않는다.
        return {**result, 'status': 'unavailable'}
