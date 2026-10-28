# 진단 JSON 통합 작업 기록

동료가 전달한 Telemetry/Rule Detection 구현과 Basic Scan UI를 하나의 실행
경로로 연결한 내용을 기록합니다.

## 반영 내용

- 최신 `integration` 브랜치를 기준으로 Python Agent, FastAPI Backend,
  Rule Detection 17개, 기존 가격·견적 기능을 유지했습니다.
- 현재 Basic Scan UI와 `diagnosis.schema.json`을 다시 포함했습니다.
- `TelemetrySnapshot → DiagnosisResult → Diagnosis 1.2` Adapter를 추가했습니다.
- Finding 심각도, 확신도, 개수를 사용해 0–100 Risk Score를 계산합니다.
- 각 Finding의 `recommendedAction`과 최상위 `decision`을 출력 계약에 추가했습니다.
- UI가 사용하는 `/api/health`, `/api/scans`, `/api/scans/latest` 별칭을 FastAPI에 추가했습니다.
- Gemma endpoint를 loopback으로 제한하고 모델 설치 상태를 구분합니다.
- UI에서 수집 실패, 권한 필요, 범위 밖을 정상 상태와 구분합니다.
- 저장된 Snapshot이 없을 때 하드코딩된 장치 정보를 대신 표시하지 않고 빈 상태를 표시합니다.
- UI의 Basic Scan 버튼이 Local Agent를 관리자 권한으로 실행하고 완료 후 최신 Diagnosis를 자동으로 표시합니다.

## 원클릭 Basic Scan

1. `POST /api/scans/start`가 단일 백그라운드 스캔을 시작합니다.
2. Windows UAC 승인 후 Agent가 collector별 진행 상태를 로컬 파일에 기록합니다.
3. UI는 `GET /api/scans/status`를 폴링해 단계와 진행률을 표시합니다.
4. Agent가 Snapshot을 Backend에 업로드하면 UI가 최신 Diagnosis를 다시 불러옵니다.

동시에 두 개의 스캔을 실행하지 않으며, 허용된 Local UI Origin이 아닌 웹 페이지의
스캔 시작 요청은 `403`으로 거부합니다. 배포 단계에서는 관리자 Agent를 Windows
서비스로 설치해 UAC와 프로세스 수명 관리를 Installer가 담당하도록 전환합니다.

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

## Recommendation 연동

`decision.drivenBy`의 Rule ID와 `recommendedAction=purchase`인 Finding을
부품 추천 근거로 사용합니다. Basic Scan 응답의 `recommendations[]`는 현재
수집한 사양과 확정된 Rule만으로 생성됩니다.

- `fix`와 `keep` Finding은 구매 추천으로 변환하지 않습니다.
- 시스템 디스크·SMART·수명·디스크 I/O 근거는 NVMe SSD 교체 후보로, 메모리
  부족 근거는 RAM 증설 후보로 변환합니다.
- 특정 부품으로 안전하게 연결할 수 없는 Hardware Finding은 기존 진단 조치에
  남기며, 억지로 상품을 추천하지 않습니다.
- 각 추천은 `candidates[]`에 최소 교체안과 플랫폼 교체안을 함께 제공합니다.
  오류가 발생한 후보는 제외하고, 통과 후보만 `compatibilityStatus`, 점수,
  검사 근거, 추가 교체 부품, 장단점과 함께 반환합니다.
- 플랫폼 묶음은 코드에 고정하지 않고 `backend/data/replacement_platforms.json`
  카탈로그에서 현재 CPU 제조사와 소켓을 기준으로 선택합니다.
- WMI에서 메모리 전체 슬롯 수까지 수집해 최소 교체안이 빈 슬롯 증설인지 기존
  모듈 교체인지 구분합니다. PSU·케이스처럼 WMI로 확인할 수 없는 항목은
  `conditional`로 남겨 호환 통과로 오인하지 않게 합니다.
- 외부 시세 API 키가 없어도 추천 목록은 생성됩니다. 키가 설정된 환경에서는
  `/api/market-prices`가 대표 상품, 최저가, 평균가, 판매처, 비교 상품 수를 조회해
  추천 카드 안에 표시합니다. 조회 실패 시 가격을 임의로 채우지 않습니다.

Advanced Scan에서는 기존 `security` 섹션과 `sysmon` Source 상태를
확장하되 Diagnosis 1.2 소비 구조는 유지합니다.
