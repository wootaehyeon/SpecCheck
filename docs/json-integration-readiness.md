# 진단 JSON 통합 작업 기록

동료가 전달한 Telemetry/Rule Detection 구현과 Basic Scan UI를 하나의 실행
경로로 연결한 내용을 기록합니다.

## 반영 내용

- 최신 `integration` 브랜치를 기준으로 Python Agent, FastAPI Backend,
  Rule Detection 17개, 기존 가격·견적 기능을 유지했습니다.
- 현재 Basic Scan UI와 `diagnosis.schema.json`을 다시 포함했습니다.
- `TelemetrySnapshot → DiagnosisResult → Diagnosis 1.1` Adapter를 추가했습니다.
- Finding 심각도, 확신도, 개수를 사용해 0–100 Risk Score를 계산합니다.
- 각 Finding의 `recommendedAction`과 최상위 `decision`을 출력 계약에 추가했습니다.
- UI가 사용하는 `/api/health`, `/api/scans`, `/api/scans/latest` 별칭을 FastAPI에 추가했습니다.
- Gemma endpoint를 loopback으로 제한하고 모델 설치 상태를 구분합니다.
- UI에서 수집 실패, 권한 필요, 범위 밖을 정상 상태와 구분합니다.
- 저장된 Snapshot이 없을 때 하드코딩된 장치 정보를 대신 표시하지 않고 빈 상태를 표시합니다.

## Demo 데이터 정책

- 기본값에서는 Local Agent가 수집해 Backend에 저장한 실제 Diagnosis만 표시합니다.
- Backend가 실행 중이지만 Snapshot이 없으면 `진단 데이터가 없습니다` 상태를 표시합니다.
- Backend에 연결할 수 없으면 연결 오류 상태를 별도로 표시합니다.
- 화면 개발용 고정 데이터가 필요할 때만
  `NEXT_PUBLIC_SPECCHECK_DEMO_MODE=true`로 명시하여 Demo mode를 사용합니다.

## Risk Score

가장 높은 Finding의 심각도가 Risk Level의 기본 구간을 결정합니다.

| 최고 심각도 | 점수 구간 |
| --- | --- |
| `info` | 0–14 |
| `low` | 15–39 |
| `medium` | 40–69 |
| `high` | 70–84 |
| `critical` | 85–100 |

같은 구간 안에서 확신도가 높을수록 점수가 올라가며, 추가 Finding은 빈도
가산점으로 반영됩니다. 낮은 심각도 여러 건이 임의로 상위 Risk Level로
승격되지는 않습니다.

## UI 진단 규약

1. 수집하지 못한 영역은 정상으로 표시하지 않습니다.
2. `fix` 항목이 있으면 구매 전에 실행할 조치로 함께 보여줍니다.
3. 결론과 함께 Evidence를 표시합니다.
4. 모든 Finding에 Confidence를 표시합니다.
5. `decision.action=fix`이면 구매 권고를 표시하지 않습니다.

## 다음 연결 지점

Recommendation 연동에서는 `decision.drivenBy`의 Rule ID와
`recommendedAction=purchase`인 Finding을 부품 추천 근거로 사용합니다.
Advanced Scan에서는 기존 `security` 섹션과 `sysmon` Source 상태를
확장하되 Diagnosis 1.1 소비 구조는 유지합니다.
