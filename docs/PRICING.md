# eBay 판매가 연동

상품 검색, 견적 입력의 판매가 조회, 카탈로그 교체 후보의 견적은 eBay Browse API를 사용한다.
기존 OAuth 발급·갱신과 한국 배송 목적지 처리를 공유한다.

`backend/.env`에 다음 항목을 설정한다. 실제 키는 저장소나 채팅에 공개하지 않는다.

```dotenv
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
# 위 두 항목 대신 이미 발급한 Application token을 사용할 수도 있다.
EBAY_OAUTH_TOKEN=
EBAY_QUOTE_TTL_SECONDS=300
```

설정을 바꾸면 로컬 백엔드를 다시 실행하거나 `docker compose up -d`로 컨테이너를 갱신한다.
인증 정보가 없으면 외부 API를 호출하지 않고 `unconfigured` 상태와 쇼핑몰 검색 링크를 제공한다.
인증 오류·호출 제한·공급자 장애는 각각 구분하며 공급자의 원본 오류나 키는 응답에 포함하지 않는다.

`GET /api/purchase/products?query=모델명`은 새 상품·고정가·한국 배송 조건으로 검색한다.
상품 상세를 확인해 모델·용량·변형·링크·금액·판매 상태를 검증한다. 상세 조회는 요청당 최대 3개다.
확인한 결과는 자격 증명과 검색어별로 짧게 캐시한다. 표시되는 가격은 조회한 상품의 상품가이며 시장 전체 최저가를 의미하지 않는다.

`POST /api/market-prices`는 기존 원화 비교 필드와 `nativePrices`를 구분한다.
외화 견적만 있으면 `errorCode: currency_mismatch`와 원래 통화의 상품가를 반환하며,
원화의 최저가·평균가를 임의로 환산하거나 과지불 여부를 계산하지 않는다.
배송비와 합계가 확인되지 않으면 미확인으로 표시하고 관세·부가세는 별도 확인한다.

`GET /api/purchase/quotes`의 카탈로그 견적은 모델·SKU를 기준으로 검증하고,
한국 배송비·재고·통화 조건을 확인한 견적끼리 비교하는 기존 동작을 유지한다.

네이버 쇼핑 검색 API는 [공식 공지](https://developers.naver.com/notice/article/32564)에 따라
2026년 7월 31일 종료됐다. 이전 호출 함수는 `service_retired` 상태로 응답하며 종료된 API를 호출하지 않는다.
eBay의 API 동작은 [공식 Browse API 문서](https://developer.ebay.com/develop/api/buy/browse_api)를 참고한다.
