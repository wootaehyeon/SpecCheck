# 로드맵 및 진행 상황

기준일: 2026-09-20

> Agent M5–M9 구현 업데이트: [ADVANCED_SCAN.md](ADVANCED_SCAN.md).
> 아래 표는 전체 서비스의 기존 번호다. 이전 M2 계획은 범위가 더 넓으며,
> 이번에 추가한 분석 입력 수집과 상세 제한 사항은 링크에서 확인한다.

## Milestone

| M | 핵심 목표 | 결과물 | 상태 |
| --- | --- | --- | --- |
| M0 | Agent 기반 구축 | Local Agent 실행 | ✅ 완료 |
| M1 | Hardware Inventory | WMI/CIM 수집 | ✅ 완료 |
| M2 | Basic Health Scan | WHEA + Storage + Resource | 🔲 스텁 준비됨 |
| M3 | Data Pipeline | Normalization + SQLite | ✅ 완료 |
| M4 | Rule Detection | 기본 이상 탐지 | 🟡 엔진 완료 · 규칙 5개 |
| M5 | Local AI Diagnosis | Gemma 기반 설명 | 🟡 연동 완료 · 모델 검증 필요 |
| **MVP** | **Basic Scan 완성** | **실제 사용자 진단 가능** | **M2 완료 시 도달** |
| M6 | Sysmon 기반 구축 | Advanced Scan | 구현 · Sysmon 설치 기기 검증 필요 |
| M7 | Security Event Correlation | 시간 창/프로세스 연결 | 구현 · 합성 시나리오 검증 |
| M8 | ML Anomaly Detection | z-score 이상 신호 | 구현 · 로컬 baseline |
| M9 | Trajectory Analysis | 저장장치/오류 추세 | 구현 · 선형 baseline |
| M10 | SpecCheck 통합/배포 | 실제 서비스 완성 | 🔲 |

## Phase 대응

| Phase | 구현 | 위치 |
| --- | --- | --- |
| 1 | WMI/CIM Hardware Inventory | `agent/.../collectors/hardware.py` ✅ |
| 2 | Performance + Storage + WHEA | `collectors/{performance,storage_health,reliability}.py` (스텁) |
| 3 | Rule-based Diagnosis | `backend/app/diagnosis/` ✅ |
| 4 | Local Gemma 설명 | `backend/app/diagnosis/explainer.py` ✅ |
| 5 | 기존 호환성/가격 시스템 연결 | `pipeline/normalize.py` → `backend/app/services/` 🟡 |
| 6 | Local Agent 설치 프로그램 | 미착수 |
| 7 | Sysmon Advanced Scan | `collectors/security.py` (스텁) |
| 8 | Process trajectory | 미착수 |
| 9 | ML Anomaly Detection | 미착수 |
| 10 | Graph/Temporal AI 연구 확장 | 미착수 |

## 다음 작업 (M2)

MVP까지 남은 것은 M2 하나다. 세 collector 모두 스텁 파일에 수집 대상 WMI
클래스와 이벤트 ID가 이미 적혀 있으므로, `implemented = False` 를 지우고
`collect()` 를 채우면 된다.

### 우선순위

1. **`storage_health`** — 시스템 드라이브 여유 공간 부족은 체감 성능 저하의
   가장 흔한 원인이면서 구매가 필요 없는 사례다. No-Purchase Scenario의
   핵심 근거이므로 먼저 만든다.
2. **`reliability`** — WHEA 오류는 증상이 아니라 하드웨어 결함의 직접
   증거다. 아직 체감 증상이 없어도 교체 필요성을 예측할 수 있는 유일한 신호다.
3. **`performance`** — 온도/스로틀링. 단발 측정값은 근거가 약하므로 짧은
   샘플링 구간의 평균·최대를 함께 담는다.

각 collector가 붙을 때마다 대응 규칙을 `backend/app/diagnosis/rules/` 에
추가한다. 규칙은 `requires` 로 필요한 섹션을 선언하므로, collector가 없는
동안에도 코드가 깨지지 않고 그냥 실행되지 않는다.

### 그 다음

- **Phase 5 연결** — `to_spec_profile()` 결과를 `services/price_evaluation.py`,
  `logic/evaluator.py` 에 물려 진단과 견적을 하나로 잇는다.
- **What-if Scan** — 현재 상태 유지 시 예상 미래 vs 부품 교체 시 예상 개선.
  진단 결과와 벤치마크 데이터셋을 함께 쓴다.
- **예측 검증 루프** — `device_id` 기준으로 스냅샷이 시계열로 쌓이므로,
  구매 후 Actual Scan과 예측을 비교하는 데 필요한 데이터는 이미 모이고 있다.
