# Collector JSON 통합

SpecCheck 진단 파이프라인은 입력과 출력 계약을 분리합니다.

| 경계 | 계약 | 네이밍 | 역할 |
| --- | --- | --- | --- |
| Agent → Backend | `telemetry 1.1.0` | snake_case | 원본 측정값과 섹션별 수집 상태 |
| Backend → UI | `diagnosis 1.2.0` | camelCase | 규칙 결과, 위험도, 권고와 화면용 요약 |

원본 계약은 `shared/contracts/telemetry_snapshot.schema.json`, 출력 계약은
`schemas/diagnosis.schema.json`입니다. 두 계약 사이의 변환은
`backend/app/diagnosis/adapter.py` 한 곳에서 담당합니다.

## 데이터 흐름

```text
Python Local Agent
  → TelemetrySnapshot 1.1
  → FastAPI SQLite 저장
  → 17개 Rule Detection
  → DiagnosisResult
  → UI Adapter + Risk Score
  → Diagnosis 1.2
  → Basic Scan UI
```

규칙이 필요로 하는 섹션이 수집되지 않았으면 해당 규칙은 실행되지 않습니다.
결측값을 정상값으로 바꾸지 않으며, UI도 수집 상태를 별도로 표시합니다.

## UI 호환 API

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/health` | Backend, Agent, Gemma 상태 |
| `POST` | `/api/scans` | 전달된 Snapshot 또는 최신 Snapshot 진단 |
| `GET` | `/api/scans/latest` | 최신 Snapshot 재진단 |
| `GET` | `/api/schema/diagnosis` | Diagnosis JSON Schema |

기존 Agent 및 내부 진단 API도 유지합니다.

- `POST /api/scan/snapshots`
- `GET /api/scan/snapshots`
- `POST /api/diagnosis/{snapshot_id}`
- `POST /api/diagnosis/analyze`
- `GET /api/diagnosis/rules`

## Snapshot 직접 진단

```json
{
  "snapshot": {
    "schema_version": "1.1.0",
    "snapshot_id": "UUID",
    "collected_at": "2026-09-04T00:00:00Z",
    "scan_mode": "actual",
    "device_id": "anonymous-device-hash",
    "agent": {
      "version": "0.1.0",
      "os": "Windows",
      "os_version": "10.0.26200"
    },
    "sections": {}
  }
}
```

빈 객체를 `POST /api/scans`에 보내면 SQLite에 저장된 최신 Snapshot을
진단합니다. 저장된 Snapshot이 없으면 `404`와 Agent 실행 안내를 반환합니다.

## Source 상태 변환

| Telemetry 상태 | Diagnosis 상태 |
| --- | --- |
| `ok` | `collected` |
| `partial` | `collected` |
| 권한 오류가 포함된 `partial` | `permission_required` |
| `skipped`, `error` | `unavailable` |
| `planned` | `not_in_scope` |

`hardware`는 WMI와 CIM, `reliability`는 WHEA, `storage_health`는 Storage,
`performance`는 Performance Counter, `security`는 Sysmon으로 표시합니다.

## 결정 사항

- `machine.name`: 호스트명 대신 익명 `device_id` 앞 12자리
- `evidence[]`: UI 호환을 위해 사람이 읽는 문자열 유지
- `recommendedAction`: 각 Finding에 `keep | fix | purchase` 보존
- `decision`: 최상위 권고와 이를 유발한 Rule ID 보존
- FastAPI 포트: 기존 Backend와 합쳐 `8000`
- Gemma 기본 모델: `gemma3:4b`, loopback endpoint만 허용
