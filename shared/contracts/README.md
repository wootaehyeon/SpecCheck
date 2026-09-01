# shared/contracts

Agent(생산자)와 Backend(소비자)가 공유하는 데이터 계약.
**이 디렉토리의 스키마가 단일 진실 공급원(single source of truth)이다.**

| 파일 | 버전 | 설명 | 대응 구현 |
| --- | --- | --- | --- |
| `telemetry_snapshot.schema.json` | 1.1.0 | 스캔 1회 결과 표준 형식 | `agent/speccheck_agent/snapshot.py`, `backend/app/schemas/telemetry.py` |

## 변경 이력

| 버전 | 변경 |
| --- | --- |
| 1.1.0 | M2 섹션 추가 — `storage_health`(수명·여유 공간), `reliability`(이벤트 집계), `performance`(샘플링 통계). 각 섹션 `data` 의 키를 `$defs` 에 문서화했다. 1.0.0에 있던 `storage` 를 실제 collector 이름인 `storage_health` 로 맞췄다. |
| 1.0.0 | 최초 정의 (M0). |

`sections` 는 `additionalProperties` 라 이름 목록은 문서일 뿐 강제되지 않는다.
그래도 1.1.0은 MINOR로 올린다 — 필드 추가이고 Backend가 그대로 수용한다.

**`data` 안의 키는 스키마가 강제하지 않지만 진단 규칙이 경로로 참조한다.**
키 이름을 바꾸면 규칙이 오류를 내는 대신 **조용히 침묵한다.** `$defs` 의
`storage_health_data` / `reliability_data` / `performance_data` 를 함께 고쳐야
하는 이유다.

## 버전 규칙 (SemVer)

| 변경 | 버전 | Backend 처리 |
| --- | --- | --- |
| 필드 추가 (optional) | MINOR | 그대로 수용 |
| 설명/제약 완화 | PATCH | 그대로 수용 |
| 필드 삭제·의미 변경·필수화 | **MAJOR** | **거절** (`415 Unsupported schema_version`) |

스키마를 수정하면 반드시 아래 두 곳을 함께 갱신한다.

1. `agent/speccheck_agent/snapshot.py` → `SCHEMA_VERSION`
2. `backend/app/schemas/telemetry.py` → `SUPPORTED_SCHEMA_MAJOR`
