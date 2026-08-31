# 아키텍처

## 계층

```
 [사용자 PC]                          [서버]                        [브라우저]

  Local Agent                        Backend                        Frontend
  ───────────                        ───────                        ────────
  collectors/       스냅샷 JSON      api/routes/scan     진단 결과   web/
    hardware   ──┐  ─────────────▶     └ 저장(SQLite)   ──────────▶
    performance  │   (계약: shared/     │
    storage      ├──▶ contracts/)       ▼
    reliability  │                    diagnosis/
    security   ──┘                      engine.py  ── rules/ ──▶ Findings
       │                                   │
       ▼                                   ▼
  pipeline/ (SQLite)                  Action Decision ──▶ explainer (Gemma)
       │                                   │
       └── 로컬 보관 (기본)                 ▼
                                      services/ (가격·호환성·벤치마크)
```

## 세 가지 설계 원칙

### 1. 계약이 먼저다

Agent와 Backend는 `shared/contracts/telemetry_snapshot.schema.json` 하나로만
대화한다. 어느 쪽을 먼저 고치든 계약 파일을 함께 갱신하지 않으면
Backend가 `415`로 거절한다 (`SUPPORTED_SCHEMA_MAJOR`).

Agent가 서버보다 앞서 나가는 상황은 정상이다 — 사용자가 Agent를 언제
업데이트할지 통제할 수 없기 때문이다. 그래서 버전 불일치는 예외가 아니라
설계된 응답 경로다.

### 2. 없는 데이터로는 판정하지 않는다

collector 하나가 실패해도 스캔 전체는 계속된다. 실패한 섹션은
`status="error"` 로 기록되고, 그 섹션을 `requires` 로 선언한 규칙은
**조용히 실행되지 않는다.**

```python
class Rule:
    requires = ("hardware",)     # 이 섹션이 ok/partial 일 때만 evaluate() 호출
```

진단 결과의 `coverage` 와 `confidence` 는 "무엇을 못 봤는지"를 사용자에게
그대로 드러낸다. 데이터가 없는데 있는 척하는 것이 이 시스템에서 가장 큰 실패다.

### 3. LLM은 판정하지 않는다

규칙 엔진이 Finding을 확정하고, LLM은 그것을 읽기 쉬운 문장으로 옮기기만
한다. 프롬프트에 telemetry 원본을 넣지 않고 확정된 Finding만 넣는 이유가
이것이다 (`explainer.build_prompt`). 모델이 없거나 실패하면 템플릿으로
자동 대체되므로, 설명 기능 때문에 진단이 실패하는 일은 없다.

## 데이터 흐름

### Actual Scan

```
speccheck-agent scan --upload
  → collectors 실행 (실패는 섹션 단위로 격리)
  → build_snapshot()  ... 계약 형식의 JSON
  → 로컬 SQLite 저장 (기본)
  → POST /api/scan/snapshots  (사용자가 --upload 를 줬을 때만)
  → POST /api/diagnosis/{snapshot_id}
      → Rule 실행 → Findings → Action Decision → 설명
```

### Estimated Scan

Agent 없이 사용자가 사양을 직접 입력하는 경로. 같은 계약 형식에
`scan_mode="estimated"` 로 담아 `POST /api/diagnosis/analyze` 로 보낸다.
진단 파이프라인은 두 모드를 구분하지 않으며, 신뢰도만 낮춰 잡는다
(`engine._coverage_confidence`).

`agent/.../pipeline/normalize.py` 의 `to_spec_profile()` 이 두 경로를 잇는다 —
Actual Scan의 스냅샷을 Estimated Scan과 동일한 사양 프로필로 바꿔주므로,
호환성·가격·벤치마크 로직은 어느 쪽에서 왔는지 알 필요가 없다.

## 로컬 우선

- Agent는 **런타임 의존성이 없다.** WMI 조회는 pywin32 대신 PowerShell
  `Get-CimInstance` 서브프로세스로 처리한다. 설치 실패 지점을 줄이기 위한
  의도적 선택이다.
- 스캔 결과는 기본적으로 로컬 SQLite에만 쌓인다. 업로드는 `--upload` 를
  명시했을 때만 일어난다.
- 시리얼 번호, MAC 주소, 사용자명은 수집하지 않는다. 기기 식별은 호스트명
  해시(`device_id`)로만 한다.
- LLM 기본값은 로컬 Gemma(Ollama)다.

## 성능 메모

PowerShell 프로세스 기동 비용이 조회당 약 2초다. 하드웨어 인벤토리는 9개
CIM 클래스를 조회하므로, 순차 실행하면 18초가 걸린다. `cim.query_batch()` 로
한 번의 기동에 모두 묶어 4.6초로 줄였다. **collector를 추가할 때도 개별
`query()` 를 반복 호출하지 말고 배치를 쓴다.**
