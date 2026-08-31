"""API 라우터 집합.

도메인별로 파일을 나눈다. 새 도메인을 추가할 때는 모듈을 만들고
아래 ``include_router`` 한 줄만 더한다.

| prefix | 담당 | 상태 |
| --- | --- | --- |
| (없음) | 가격/시세/견적 최적화 | 구현됨 |
| /scan | Agent 스냅샷 수집·조회 | M3 |
| /diagnosis | 진단 및 Root Cause | M4-M5 |
"""

from fastapi import APIRouter

from . import diagnosis, price, scan

router = APIRouter()
router.include_router(price.router, tags=["price"])
router.include_router(scan.router, prefix="/scan", tags=["scan"])
router.include_router(diagnosis.router, prefix="/diagnosis", tags=["diagnosis"])

__all__ = ["router"]
