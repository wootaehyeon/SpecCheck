# shared/contracts

Agent(생산자)와 Backend(소비자)가 공유하는 데이터 계약.
**이 디렉토리의 스키마가 단일 진실 공급원(single source of truth)이다.**

| 파일 | 설명 | 대응 구현 |
| --- | --- | --- |
| `telemetry_snapshot.schema.json` | 스캔 1회 결과 표준 형식 | `agent/speccheck_agent/snapshot.py`, `backend/app/schemas/telemetry.py` |

## 버전 규칙 (SemVer)

| 변경 | 버전 | Backend 처리 |
| --- | --- | --- |
| 필드 추가 (optional) | MINOR | 그대로 수용 |
| 설명/제약 완화 | PATCH | 그대로 수용 |
| 필드 삭제·의미 변경·필수화 | **MAJOR** | **거절** (`415 Unsupported schema_version`) |

스키마를 수정하면 반드시 아래 두 곳을 함께 갱신한다.

1. `agent/speccheck_agent/snapshot.py` → `SCHEMA_VERSION`
2. `backend/app/schemas/telemetry.py` → `SUPPORTED_SCHEMA_MAJOR`

## 1.1.0

optional 섹션 `storage_health`, `correlation`, `anomaly`, `trajectory`와 Sysmon
집계 데이터가 추가됐다. 기존 섹션 envelope는 동일하므로 지원 major는 1이다.
Agent와 Backend의 저장·조회 테스트로 새 섹션의 보존을 확인한다.
필드 의미와 결측/프라이버시 정책은 [Advanced Scan 계약 설명](../../docs/ADVANCED_SCAN.md)을 따른다.
