# Local Agent 로드맵

담당: 우태현 · 브랜치: `agent-telemetry` · 기준일 2026-08-25

이 문서는 `agent/` (Local Agent) 한 축의 마일스톤 계획이다. 설계 원칙과
계약은 [ARCHITECTURE.md](ARCHITECTURE.md) 를 따르며, 이 문서는 **무엇을
언제까지 어떤 상태로 끝내는가**만 정의한다.

---

## 전체 지도

| # | 마일스톤 | 기간 | 상태 | 한 줄 정의 |
| --- | --- | --- | --- | --- |
| M0 | Agent skeleton | ~08/24 | ✅ 완료 | CLI·collector 레지스트리·스냅샷 계약의 뼈대 |
| M1 | WMI/CIM | ~08/24 | ✅ 완료 | PowerShell CIM 배치 조회 + 하드웨어 인벤토리 |
| M2 | WHEA / Storage / Performance | 08/25 ~ 09/07 | 🔜 진행 예정 | "얼마나 닳았고 지금 어떤 상태인가"를 실측 |
| M3 | Normalization / SQLite | 09/08 ~ 09/14 | 🟡 부분 구현 | 로컬 시계열 저장 + spec profile 정규화 완성 |
| M4 | Rule Detection | 09/15 ~ 09/28 | ⬜ | 규칙 엔진과 Finding 확정 |
| M5 | Basic Scan Risk 생성 | 09/29 ~ 10/05 | ⬜ | Finding → Risk 점수/등급, Basic Scan 산출물 |
| M6 | Sysmon | 10/06 ~ 10/19 | ⬜ | Advanced Scan용 보안 이벤트 수집 |
| M7 | Event Correlation | 10/20 ~ 11/02 | ⬜ | 이벤트 간 인과 연결 → Root Cause 후보 |
| M8 | ML Anomaly | 11/03 ~ 11/16 | ⬜ | 규칙이 못 잡는 이상치 탐지 (stretch) |
| M9 | Trajectory | 11/17 ~ 11/30 | ⬜ | 시계열 추세 → 열화 예측 (stretch) |
| M10 | Agent 안정화 | 12/01 ~ 12/07 | ⬜ | 성능·예외·권한·프라이버시 정리 |
| M11 | Installer / Test | 12/08 ~ 12/14 | ⬜ | 배포 패키지와 전체 회귀 테스트 |

날짜는 발표 일정에 맞춰 조정한다. **M8·M9는 stretch**로 둔다 — 일정이 밀리면
이 둘을 규칙 기반 baseline으로 축소하고 M10·M11을 반드시 확보한다.
Agent가 설치되지 않으면 프로젝트 전체가 시연되지 않기 때문이다.

---

## 공통 완료 기준 (모든 마일스톤에 적용)

한 마일스톤은 아래를 전부 만족해야 닫는다.

1. **계약 반영** — 스냅샷 형식이 바뀌면 `shared/contracts/telemetry_snapshot.schema.json`
   과 `snapshot.SCHEMA_VERSION`, Backend의 `SUPPORTED_SCHEMA_MAJOR`를 같은 PR에서 갱신한다.
2. **실패 격리** — 새 collector는 예외를 던져도 스캔 전체를 멈추지 않는다
   (`Collector.run()` 의 계약). 미지원 환경은 `skipped`, 미구현은 `planned`.
3. **배치 조회** — CIM 조회는 `cim.query()` 반복 호출 대신 `cim.query_batch()` 를 쓴다.
   PowerShell 기동 비용이 조회당 약 2초다.
4. **테스트** — `agent/tests/` 에 최소 1개. Windows 전용 호출은 CIM 계층을
   모킹해 비Windows에서도 돌게 한다.
5. **실측 1회** — 실제 Windows 기기에서 `speccheck-agent scan` 을 돌린 결과와
   소요 시간을 PR 본문에 붙인다.
6. **문서** — 새 collector는 모듈 docstring에 데이터 소스와 설계 의도를 남긴다
   (기존 스텁 파일들의 형식을 따른다).

---

## M2 — WHEA / Storage / Performance

**왜 먼저인가.** 지금 Agent는 "무엇이 달렸는가"만 안다. 진단이 성립하려면
"얼마나 닳았고 지금 어떤 상태인가"가 필요하다. M4 규칙 엔진이 먹을 재료를
만드는 단계이므로, 여기가 비면 뒤 전부가 비어 돈다.

**대상 파일**
- `agent/speccheck_agent/collectors/reliability.py` (WHEA / 비정상 종료 / 디스크 오류)
- `agent/speccheck_agent/collectors/storage_health.py` (SMART / NVMe 수명 / 볼륨 여유)
- `agent/speccheck_agent/collectors/performance.py` (CPU·메모리·디스크 샘플링, 전원 계획)

**구현 순서** — `storage_health` → `reliability` → `performance`.
여유 공간 부족은 No-Purchase Scenario의 대표 근거라 가장 값이 싸고 효과가 크다.

**완료 기준**
- 세 collector 모두 `implemented = True`, 스냅샷 `sections` 에 `status="ok"`.
- `performance` 는 단발값이 아니라 **샘플링 구간의 평균/최대**를 함께 담는다
  (스파이크와 상시 부하를 구분해야 M7이 성립한다).
- `reliability` 는 이벤트 원문이 아니라 **집계**(EventID별 건수 + 최근 발생 시각 +
  관측 구간)를 담는다. 원문 로그는 용량과 프라이버시 양쪽에서 비용이다.
- SMART 미지원 디스크(USB·일부 NVMe)에서 전체 실패가 아니라 `partial` 로 떨어진다.
- 전체 스캔 소요 시간 목표 **10초 이내**.

**리스크** — `MSAcpi_ThermalZoneTemperature` 를 지원하지 않는 메인보드가 많다.
온도는 "없으면 없는 대로" 두고 `CurrentClockSpeed / MaxClockSpeed` 비율로 스로틀링을
간접 추정한다. 온도 결측이 collector 실패가 되어서는 안 된다.

---

## M3 — Normalization / SQLite

**현재 상태.** `pipeline/store.py`(스냅샷·collector_runs 테이블)와
`pipeline/normalize.py`(`to_spec_profile`)의 1차 구현은 있다. M2에서 세 섹션이
늘어난 만큼 정규화 대상과 보관 정책을 이번에 확정한다.

**완료 기준**
- `to_spec_profile()` 이 M2의 새 섹션까지 포함해 Estimated Scan과 **완전히 동일한**
  키 집합을 만든다 (Backend가 두 경로를 구분할 필요가 없어야 한다).
- DB 스키마 버전 테이블과 마이그레이션 경로. 기존 DB를 지우지 않고 올라간다.
- 보관 정책: 스냅샷 N개/N일 초과분 정리 (`speccheck-agent prune`).
- `speccheck-agent list` / `show` / `profile` 이 M2 섹션을 사람이 읽는 형태로 출력.
- 같은 기기의 스냅샷을 `device_id` 로 시간순 조회하는 쿼리 (M9의 전제).

---

## M4 — Rule Detection

규칙 엔진이 Finding을 확정한다. LLM은 이 단계에 관여하지 않는다.

**완료 기준**
- `Rule` 인터페이스: `requires` 로 필요한 섹션을 선언하고, 해당 섹션이
  `ok`/`partial` 이 아니면 **조용히 실행되지 않는다**.
- 초기 규칙 8~12개. 최소한 다음을 덮는다:
  시스템 드라이브 여유 공간 부족 / SMART 재할당·대기 섹터 증가 / NVMe 수명 임계 /
  WHEA Corrected 누적 / 비정상 종료 반복 / 메모리 부족(페이징 과다) /
  전원 계획 절전 고정 / 상시 CPU 점유 과다.
- Finding 형식: `id`, `severity`, `category`(hardware|software|security),
  `evidence`(어느 섹션의 어떤 값에서 나왔는지), `suggested_action`.
- 규칙별 단위 테스트를 **합성 스냅샷 fixture**로 작성 (실기기 없이 검증 가능해야 한다).
- 결측 데이터에서 규칙이 침묵하는지 검증하는 테스트 1개 이상.

---

## M5 — Basic Scan Risk 생성

Finding들을 사용자가 보는 하나의 결과로 합친다. Basic Scan의 최종 산출물.

**완료 기준**
- 카테고리별 Risk 점수와 종합 등급.
- `coverage`(무엇을 봤는가) / `confidence`(얼마나 믿을 수 있는가)를 함께 낸다.
  섹션이 `skipped`/`error`면 점수가 아니라 **신뢰도**가 떨어져야 한다.
- Estimated Scan(Agent 미설치)도 같은 형식으로 나오고 confidence만 낮다.
- **없는 데이터로 판정하지 않는다** — 근거 섹션이 없으면 "이상 없음"이 아니라
  "확인하지 못함"으로 표시된다. 이 구분이 M5의 핵심 수용 기준이다.
- 데모 가능 지점: 여기까지가 발표에서 반드시 돌아가야 하는 최소 제품.

---

## M6 — Sysmon

Advanced Scan 영역. `collectors/security.py` 를 구현한다.

**완료 기준**
- Sysmon 미설치 기기에서 `skipped` + 안내 사유. 설치를 강요하지 않는다.
- 수집 대상: EventID 1(Process Create), 3(Network Connect), 11(File Create),
  13(Registry Set), 22(DNS Query) — 원문이 아니라 집계/상위 N.
- 기본 보안 상태: Defender(`MSFT_MpComputerStatus`), TPM, Secure Boot.
- 프라이버시 경계 문서화: 명령줄 인자·사용자명·경로 중 무엇을 버리는지 명시.
  기본은 **수집하지 않는다**이고, 예외만 근거와 함께 남긴다.
- Sysmon 설정 XML 샘플을 저장소에 포함.

---

## M7 — Event Correlation

이벤트를 서로 잇는다. "게임이 느려졌다"의 원인이 부품인지 소프트웨어인지를
가르는 단계이고, Action Decision이 **구매**로 갈지 **Software Fix**로 갈지가
여기서 갈린다.

**완료 기준**
- 시간 창(window) 기반 상관 규칙: 성능 저하 구간 ↔ 프로세스/네트워크 이벤트 ↔
  디스크 오류 이벤트를 같은 구간에서 묶는다.
- Root Cause 후보를 **순위와 근거**를 붙여 최대 3개까지 제시한다.
- 최소 2개 시나리오를 합성 데이터로 재현·검증:
  (1) 크립토마이너/백그라운드 과부하 → Software Fix,
  (2) WHEA 누적 + 디스크 재시도 → 부품 교체.
- 상관이 약할 때 "원인 불명"을 반환하는 경로가 있다.

---

## M8 — ML Anomaly *(stretch)*

규칙이 못 잡는 이상치를 잡는다. **규칙 엔진을 대체하지 않는다** — 판정은 여전히
규칙이 하고, ML은 "평소와 다르다"는 신호만 낸다.

**완료 기준**
- 기기별 baseline을 로컬 스냅샷 시계열에서 학습 (서버 전송 없음).
- 경량 모델 우선: IsolationForest 또는 통계적 z-score. 무거우면 후자로 내린다.
- 스냅샷 3개 미만이면 동작하지 않고 `partial` 로 표시.
- 오탐 시 사용자 결과를 오염시키지 않도록, 출력은 Finding이 아니라
  **신호(signal)** 등급으로 분리한다.
- 축소 대안: 이상치 판정을 이동평균 ± 2σ 규칙으로 대체하고 M9로 넘어간다.

---

## M9 — Trajectory *(stretch)*

시계열에서 열화 추세를 뽑아 "언제쯤 문제가 되는가"를 답한다. What-if Scan과
예측 검증(구매 후 Scan vs 예측)의 재료.

**완료 기준**
- 추세 대상: SSD 수명·재할당 섹터·WHEA 누적 건수·여유 공간 감소율.
- 선형 추세 + 임계 도달 예상 시점, 불확실성 구간과 함께 제시.
- 데이터 포인트 부족 시 예측을 내지 않고 필요한 관측 수를 안내한다.
- `--note` 로 남긴 이벤트(예: "RAM 교체 전/후")를 기준선으로 구간을 나눈다.

---

## M10 — Agent 안정화

**완료 기준**
- 전체 스캔 소요 시간 목표 **15초 이내** (M6까지 전부 켠 상태).
- 관리자 권한 없이 실행했을 때: 실패가 아니라 해당 섹션만 `skipped` + 사유.
- PowerShell 타임아웃·비정상 종료·인코딩(한글 로케일) 예외 처리.
- `speccheck-agent doctor` 가 환경 문제(PowerShell 정책, Sysmon 유무, 권한)를
  진단하고 조치를 안내한다.
- 프라이버시 최종 점검: 시리얼·MAC·사용자명·경로가 스냅샷에 새지 않는지
  **자동 테스트**로 고정한다 (금지 패턴 검사).
- 로그 파일과 `--verbose` 레벨 정리.

---

## M11 — Installer / Test

**완료 기준**
- PyInstaller 단일 실행 파일 (Python 미설치 기기에서 동작 확인).
- 설치 스크립트: 실행 파일 배치 + 선택적 Sysmon 설치 + 스케줄 등록(선택).
- 깨끗한 Windows 기기 1대에서 **설치 → 스캔 → 업로드 → 진단 결과 확인**
  전 경로 1회 검증.
- 전체 회귀 테스트 통과, `pytest` 커버리지 확인.
- 제거 절차(파일·스케줄·로컬 DB) 문서화.
- README에 설치·사용법 추가.

---

## 브랜치 전략

```
main
 └─ agent-telemetry            ← 이 축의 통합 브랜치 (담당: 우태현)
     ├─ agent/m2-reliability
     ├─ agent/m2-storage-health
     ├─ agent/m3-normalize
     └─ ...
```

- 마일스톤 단위 작업은 `agent-telemetry` 에서 `agent/m<N>-<주제>` 브랜치를 파고,
  끝나면 `agent-telemetry` 로 PR을 올린다.
- `agent-telemetry` → `main` 병합은 **M5(데모 가능 지점)** 와 **M11(배포)** 두 번을
  기본으로 한다. 계약 파일(`shared/contracts/`)을 건드리는 변경은 Backend 담당자와
  같은 PR에서 합의한 뒤 즉시 `main` 으로 올린다.
- 커밋 메시지: `agent(M2): reliability collector - WHEA 이벤트 집계` 형식.
