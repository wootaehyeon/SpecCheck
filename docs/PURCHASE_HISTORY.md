# 구매이력 저장과 공유

React 개발 화면은 `http://localhost:3000/purchases`, Docker/정적 웹 화면은
`http://localhost:8000/purchases.html`에서 연다. 각 메인 화면과 부품 구매 화면에서도 이동할 수 있다.

## 사용 방법

1. 실제 구매한 부품의 상품명, 종류, 원화 단가, 수량, 구매일, 판매처를 입력한다.
2. 기본값은 비공개다. 공유 동의에 체크하면 익명 구매자 표시와 함께 공개 목록에 나타난다.
3. 여러 사용자 구매이력에서 상품명·종류로 검색한다. 구매자 표시를 누르면 그 구매자가 공유한 기록만 보인다.
4. 내 구매이력에서 공유를 중단하거나 기록을 삭제할 수 있다.

구매이력은 사용자가 직접 입력한 기록이며 결제나 영수증을 검증한 내역이 아니다.
판매처 이동이나 상품 검색을 구매 완료로 간주하지 않는다. 실제 구매 자료가 없는 상태에서
예시 데이터를 운영 저장소에 넣지 않는다. 구매자 수는 브라우저 저장키 기준으로 집계하며 실제 인원과 다를 수 있다.
총액은 검색 조건에 맞는 내역 전체의 단가 × 수량 합계이고, 가격 범위는 개당 가격이다.
서로 다른 제품의 합계/범위가 시장 시세를 뜻하지 않는다.

## 저장과 권한

- 저장소: `DATA_DIR/purchase-history.db`. 기본값은 `backend/data/purchase-history.db`다.
- Docker Compose에서는 `DATA_DIR=/app/backend/data`를 지정하고 기존 데이터 볼륨에 저장한다.
  컨테이너를 다시 만들어도 볼륨이 유지되면 이력이 보존된다.
- 로컬 서버 프로세스를 다시 실행해도 파일이 남아 있으면 기록이 유지된다.
- 임시 파일 시스템을 사용하는 호스팅에서는 재배포 시 파일이 사라질 수 있다.
  공개 운영 전에 `DATA_DIR`를 영구 디스크로 연결해야 한다. 이 기능은 기존 모니터링 PostgreSQL과 별도 저장소다.
- 브라우저에서 생성한 256비트 관리키를 localStorage에 보관하고 인증 헤더로만 전송한다.
  서버는 키의 SHA-256 해시를 저장한다. 공개 API에 관리키나 해시를 반환하지 않는다.
- 로그인 계정 연동은 없다. 같은 브라우저·웹 출처·API 주소에서만 기존 관리키를 사용한다.
  다른 브라우저/기기에서 접속하거나 브라우저 데이터를 삭제하면 기존 비공개 기록을 관리할 수 없다.
- 공개 조회는 동의한 기록만 반환한다. 공유 철회 즉시 이후 조회에서 제외한다.
  본인 기록 조회·공유 변경·삭제는 관리키로 소유권을 검사한다.
- 저장 요청 ID를 사용하므로 통신 실패 후 같은 요청을 재전송해도 중복 저장하지 않는다.
- 구매이력 응답은 브라우저/공유 캐시에 저장하지 않는다. 원본 DB 파일은 Git에서 제외된다.

## API

| 메서드 | 경로 | 기능 |
| --- | --- | --- |
| GET | `/api/purchase/history` | 공유 기록 검색, 구매자별 필터, 집계, 페이지 조회 |
| GET | `/api/purchase/history/me` | 관리키 소유자의 비공개·공개 기록 조회 |
| POST | `/api/purchase/history` | 구매이력 저장 |
| PATCH | `/api/purchase/history/{id}` | 본인 기록의 공개 여부 변경 |
| DELETE | `/api/purchase/history/{id}` | 본인 기록 삭제 |

조회 파라미터는 `query`, `category`, `page`, `page_size`다. 공개 조회는 `buyer`도 지원한다.
쓰기와 본인 조회는 `Authorization: Bearer sc_purchase_<64자리 소문자 16진수>`가 필요하다.
저장에는 UUID 형식 `request_id`, `product_name`, `category`, `unit_price`, `quantity`,
`purchased_on`, `merchant`, `shared`를 사용한다. 날짜 검증은 한국 시간을 기준으로 한다.

## 검증

```powershell
node scripts/run-python.mjs backend -m pytest -q tests/test_purchase_history.py
$env:SPECCHECK_TEST_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
node frontend/tests/node_modules/@playwright/test/cli.js test --config frontend/tests/playwright.config.cjs purchase-history.spec.cjs
```

테스트는 임시 저장소에서 진행하며 실제 구매 기록과 섞이지 않는다.
