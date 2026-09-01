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
| M2 | WHEA / Storage / Performance | 08/25 ~ 09/07 | ✅ 완료 | "얼마나 닳았고 지금 어떤 상태인가"를 실측 |
| M3 | Normalization / SQLite | 09/08 ~ 09/14 | ✅ 완료 | 로컬 시계열 저장 + spec profile 정규화 완성 |
| M4 | Rule Detection | 09/15 ~ 09/28 | ✅ 완료 | 규칙 엔진과 Finding 확정 |
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

**완료 기록 (2026-09-01)**

세 collector 모두 구현했다. i7-12700 / RAM 32GB / NVMe + HDD 구성에서 실측:

```
wall 9.4s | hardware=1608ms  storage_health=1004ms  reliability=344ms  performance=6207ms
```

전체 스캔 9.4~10.4초로 목표(10초)를 만족한다. `performance` 가 6초를 쓰는데
그중 2초는 샘플링 대기이고, 나머지는 collector마다 PowerShell을 새로 띄우는
고정 비용(약 1.5초 x 4)이다. 이 고정 비용을 줄이려면 collector를 한 프로세스에
합쳐야 하는데, 그러면 실패 격리가 깨지므로 M2에서는 하지 않았다.

계획에서 바뀐 것 세 가지.

- **전원 계획을 `Win32_PowerPlan` 대신 `powercfg /getactivescheme` 으로 읽는다.**
  실측 기기에서 `root/cimv2/power` 네임스페이스 접근이 정책으로 막혀 있었다.
  `powercfg` 는 권한 없이 동작하고 GUID를 주므로 로케일 문제도 함께 사라진다.
- **`cim.query_batch` 에 script 통로를 추가했다.** `Get-WinEvent`, `powercfg`,
  샘플링 루프처럼 CIM 조회로 표현할 수 없는 자료원도 같은 PowerShell 기동
  안에서 처리하기 위해서다.
- **시스템 볼륨이 올라간 물리 디스크 번호(`system_disk_index`)를 함께 수집한다.**
  M4 규칙 작업 중 `HW-DISK-001`(시스템 드라이브가 HDD)이 실측에서 오진하는 것을
  발견했다. 데이터용 HDD가 0번, OS가 설치된 NVMe가 1번인 구성에서 `Index 0` 을
  시스템 디스크로 가정하고 있었다. `Get-Partition` 으로 실제 연결을 확인한다.

**권한 관련.** SMART(`root/wmi`)과 온도는 관리자 권한을 요구한다. 권한이 없으면
해당 항목만 빠지고 섹션이 `partial` 이 된다. 오류 메시지는 로케일마다 다르므로
문자열이 아니라 `cim.is_elevated()` 로 권한을 직접 확인해 조치 가능한 안내로
바꿔 넣는다.

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

**완료 기록 (2026-09-01)**

- `to_spec_profile()` 이 인벤토리와 수명 정보를 합친 `storage` 목록과 `health`
  블록을 낸다. **키 집합은 수집 결과와 무관하게 항상 같다** — 섹션이 없으면
  키가 사라지는 것이 아니라 값이 `None` 이 된다. Backend가 Actual/Estimated
  경로를 구분하지 않아도 되게 하기 위한 조건이다.
- `schema_meta` 테이블과 마이그레이션 경로. 버전 기록 이전에 만들어진 DB는
  `snapshots` 테이블 존재 여부로 v1로 판별해 올린다. 기존 스냅샷은 보존된다.
- `prune --keep N --older-than D` 는 두 조건을 **모두** 만족할 때만 지운다.
  오래됐어도 최근 N개 안에 들면 남는다.
- `health`(상태 요약), `history`(기기별 추이), `show --sections`, `list --device`
  추가. 상태가 `ok` 가 아닌 섹션도 반드시 함께 출력한다.
- 부수 수정: stdout이 파이프로 연결되면 한국어 Windows에서 cp949로 인코딩돼
  `scan --json > file` 결과를 Backend가 읽지 못했다. UTF-8로 고정했다.

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

**완료 기록 (2026-09-01)**

규칙 12개를 추가해 총 17개가 됐다 (M1 기반 5개 + M2 기반 12개).

| 모듈 | 규칙 |
| --- | --- |
| `storage_rules` | `ST-SPACE-001` 시스템 볼륨 여유 공간 / `ST-SMART-001` 불량 섹터 / `ST-SMART-002` 실패 예측 / `ST-WEAR-001` 수명 소모 |
| `reliability_rules` | `RL-WHEA-001` 정정 오류 누적 / `RL-WHEA-002` 치명적 오류 / `RL-CRASH-001` 비정상 종료 반복 / `RL-DISK-001` IO 오류 |
| `performance_rules` | `PF-MEM-001` 메모리 압박 / `PF-POWER-001` 절전 계획 / `PF-CPU-001` 상시 CPU 점유 / `PF-THROTTLE-001` 클럭 저하 |

임계값 설계에서 지킨 규칙 세 가지.

- **두 신호가 겹칠 때만 판정한다.** 여유 공간은 비율과 절대량을 모두 넘어야
  하고(2TB의 8%는 부족하지 않다), 메모리 압박은 커밋 비율과 가용량을 함께 본다.
- **평균과 최소를 함께 본다.** CPU 점유는 최대만 높으면 스파이크다. 최소까지
  높아야 상시 부하로 인정한다. 이 구분이 없으면 성능 축에서 오진이 쏟아진다.
- **낮은 구간에서는 더 싼 조치를 권한다.** WHEA 정정 오류 5~19건은 XMP 해제와
  재장착(FIX), 20건 이상부터 교체(PURCHASE). 수명 소모 70~89%는 백업과 계획(KEEP),
  90% 이상부터 교체. 비정상 종료 반복은 원인 부품을 특정할 수 없으므로 구매가
  아니라 원인 규명을 권한다.

확신도(confidence)에는 관측의 한계를 반영한다. 성능 축은 관측 구간이 수 초에
불과하므로 0.6~0.75, 이벤트 로그가 관측 구간을 덮지 못하면(`log_covers_window`
가 false) 0.8배로 낮춘다.

M2 데이터로 M1 규칙 하나를 고쳤다. `HW-DISK-001` 은 `Index 0` 을 시스템 디스크로
가정했으나 이제 `storage_health.disks[].is_system` 을 본다. 그 정보가 없으면
기존 추정으로 떨어지되 확신도를 0.85에서 0.5로 낮춘다.

테스트는 `backend/tests/test_m2_rules.py` 38개 + `agent/tests/test_m2_m3.py` 43개.
모두 합성 스냅샷만 쓰므로 Windows 없이 돈다.

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
