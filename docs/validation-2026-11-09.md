# 2026-11-09 추가 검증 기록

기존 D07/D08의 2026-11-05 기준 미해결 항목을 재확인했다. 이 기록은 아래에
명시한 환경과 실행에만 적용한다. 전체 운영 서비스의 최종 인수 판정은 아니다.

| 항목 | 실행 결과와 근거 |
| --- | --- |
| OBS-01 / STC-REAL-012 | 실제 FastAPI에 견적을 UI로 입력했다. AM5/B650/DDR5와 AM5/B550/DDR5의 판정이 다르고 서버 호환성 메시지가 상세 화면에 일치했다. 등록된 Ryzen 7 5700X / RTX 3060의 점수는 Backend JSON과 화면값이 일치했다. 미등록 모델은 점수를 표시하지 않는다. |
| OBS-02 | 결과 화면의 데모 가격 재계산, 카탈로그 및 RAM 용량 기반 예시 가격, 시장 조사 실패 시 예시 게시글·평판·가격을 제거했다. API 성공값 유지, 실패, 이전 저장 결과 무효화, 교체 후 이전 부품 가격 폐기, 후보 가격 미입력 차단, 적용·되돌리기를 시험했다. |
| STC-REAL-007 | Windows 11 / Python 3.14.3에서 실제 Basic Scan을 실행하고 로컬 HTTP Backend에 업로드했다(201). 하드웨어 원본과 저장 후 조회값이 일치했다. hardware/reliability/performance는 ok, storage_health/security 및 일부 분석은 partial이었다. 보호된 카운터를 수집했다고 판정하지 않았다. |
| OBS-04 / STC-REAL-009 부분 | 실제 스캔의 hardware/performance를 Agent의 `watch.upload()`로 로컬 HTTPS 서버에 전송했다. 인증서와 IP SAN을 검증했다. PostgreSQL 17 Docker 인스턴스에 저장하고 Edge에서 실제 CPU 4.0%, RAM 32GB 및 하드웨어 모델 표시를 확인했다. Backend와 PostgreSQL 컨테이너를 모두 재시작한 뒤 snapshot/received_at 유지, 연결 삭제 204 및 이전 조회키 401을 확인했다. 공개 인터넷/운영 도메인 TLS는 미검증이다. |
| PostgreSQL 회귀 | `tests/test_monitoring.py -k postgres`: 15 passed, 15 deselected. 기기·권한 격리, 이력 유지, 동의·철회·삭제 등을 실제 PostgreSQL 연결로 확인했다. 이 회귀 시험의 입력은 합성 데이터다. |
| STC-REAL-013 | Edge의 실제 Canvas UI에서 쿨러 선장착 차단, 보드→CPU→쿨러 장착 및 쿨러→CPU→보드 해제를 확인했다. 장착된 하위 부품을 둔 채 메인보드를 해제할 수 있던 오류를 수정했다. |
| UI 회귀 | `npm run test:ui`: 53 passed. `estimate.spec.cjs` 4건과 `assembly.spec.cjs` 1건: 5 passed. `npm run lint`: 통과. |

실행 환경은 저장소의 Python `.venv`, Node 24.14.0, 설치된 Microsoft Edge,
실제 Uvicorn 서버, Docker PostgreSQL 17이다. 테스트용 DB·연결키는 운영 설정과
분리했다. 로컬 HTTPS는 테스트 인증서를 명시적으로 신뢰하여 검증했으며 운영
인증서를 발급받거나 시스템 인증서 저장소를 변경하지 않았다. 브라우저의 해당
로컬 HTTPS 화면 확인은 `ignoreHTTPSErrors`를 사용했고, Agent 전송에서 별도로
인증서 검증을 수행했다.

실측 스냅샷, 진단 원문, 화면 캡처, 임시 연결키·인증서는 개인정보를 포함할 수
있으므로 Git 제외 경로 `.deployment-tmp/real-validation*`,
`.deployment-tmp/real-monitor*`에만 남겼다. 자동 UI 시험 캡처는
`frontend/tests/test-results/`에 있다. 임시 서버와 검증 컨테이너는 종료한다.

## 남은 실환경 제한

- STC-REAL-008: `doctor`는 Sysmon 로그 접근 거부를 반환했다. 현재 계정은 비관리자다.
  관리자 실행 또는 승인된 로그 읽기 권한을 갖춘 뒤 실제 이벤트 수집·전송·철회를
  재시험해야 한다. 이번 작업에서 권한·Sysmon 설치 설정을 변경하지 않았다.
- STC-REAL-009의 공개 배포 부분: 실제 외부 PostgreSQL, Render 운영 주소, 외부
  네트워크 및 공개 TLS 인증서 검증은 남아 있다. 로컬 PostgreSQL/HTTPS 통과로
  공개 배포 통과를 대신하지 않는다. 애플리케이션 Docker 이미지 실행도 별도다.
- STC-REAL-010: 현재 상품 API는 실제 호출에서 `status=unconfigured`, 상품 0건을
  반환했다. eBay 키가 준비되지 않았다. 네이버 설정 존재만으로 현재 eBay 경로가
  준비됐다고 판단하지 않았다. 원화 성공값 시험은 명시적 모의 제공자 응답이었다.
  실제 eBay 상품·중고 시세·커뮤니티 제공자 원본과 화면값 비교는 남아 있다.
- STC-REAL-011: Ollama 서버/실행 모델이 준비되지 않았고 LLM은 비활성 상태다.
  실제 생성·모델 중단 시험은 남아 있다. 이번 진단 설명은 템플릿 경로다.
- STC-REAL-014: 장시간·다기기 목표 부하와 허용 기준이 정해지지 않았다. 짧은
  회귀 및 기기 격리 시험으로 장시간 운영 성능을 보증하지 않는다.

## 재현 명령

프로젝트 루트에서 `npm run test:ui`, `npm run lint`를 실행한다.
`frontend/tests`에서는 아래 환경변수로 브라우저 회귀를 실행한다.

```powershell
$env:SPECCHECK_TEST_PYTHON = (Resolve-Path '../../.venv/Scripts/python.exe').Path
$env:MONITOR_TEST_BROWSER = 'msedge'
$env:SPECCHECK_TEST_PORT = '8041'
npx playwright test estimate.spec.cjs assembly.spec.cjs
```

PostgreSQL 시험은 전용 시험 DB의 연결 URL을 `MONITOR_TEST_DATABASE_URL`에 설정한
뒤 `backend`에서 `../.venv/Scripts/python.exe -m pytest tests/test_monitoring.py -q -k postgres`로 실행한다.
운영 DB를 지정하지 않는다. Basic Scan은 `agent`에서 `python -m speccheck_agent scan --out <로컬 저장 경로>`로 재실행한다.
