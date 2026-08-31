# 디렉토리 구조

> 무엇을 어디에 추가해야 하는지에 대한 지도.

```
SpecCheck/
├── agent/                      # Local Agent — 사용자 PC에서 telemetry 수집
│   ├── speccheck_agent/
│   │   ├── cli.py              #   CLI 진입점 (scan / list / show / profile / doctor)
│   │   ├── config.py           #   실행 설정 (SPECCHECK_* 환경변수)
│   │   ├── snapshot.py         #   표준 스냅샷 생성 · SCHEMA_VERSION
│   │   ├── collectors/         #   ★ telemetry 수집기 (여기에 추가)
│   │   ├── pipeline/           #   정규화 + SQLite 저장
│   │   ├── transport/          #   Backend 업로드
│   │   └── win/                #   WMI/CIM 어댑터 (PowerShell 호출)
│   └── tests/
│
├── backend/                    # API 서버
│   ├── app/
│   │   ├── main.py             #   FastAPI 앱
│   │   ├── api/routes/         #   ★ HTTP 엔드포인트 (도메인별 파일)
│   │   ├── core/               #   설정 · LLM 프롬프트
│   │   ├── diagnosis/          #   ★ 진단 엔진
│   │   │   ├── engine.py       #     규칙 실행 · Action Decision
│   │   │   ├── rules/          #     ★ 진단 규칙 (여기에 추가)
│   │   │   └── explainer.py    #     LLM 자연어 설명 (Gemma)
│   │   ├── schemas/            #   Pydantic 모델 (telemetry / diagnosis / price)
│   │   ├── services/           #   외부 연동 · 저장소
│   │   └── logic/              #   견적 평가 로직
│   ├── data/                   #   벤치마크 JSON · 캐시 (DB는 커밋 안 함)
│   └── tests/
│
├── shared/contracts/           # ★ Agent ↔ Backend 데이터 계약 (단일 진실 공급원)
│
├── frontend/
│   ├── web/                    # 메인 웹 UI (정적 HTML/CSS/JS)
│   └── pc_3d_assembly/         # PC 3D 조립 시각화
│
├── datasets/                   # 원본 데이터셋 (CSV)
│   ├── cpu_spec/  cpu_benchmark/
│   └── gpu_spec/  gpu_benchmark/
│
├── tools/community/            # 커뮤니티 크롤링 스크립트
├── scripts/                    # 개발용 실행 스크립트 (PowerShell)
└── docs/                       # 문서 · 발표자료
```

## 무엇을 어디에 추가하는가

| 하고 싶은 일 | 손댈 곳 |
| --- | --- |
| 새 telemetry 수집 (온도, WHEA, SMART …) | `agent/speccheck_agent/collectors/` + `collectors/__init__.py` |
| 새 진단 규칙 | `backend/app/diagnosis/rules/` + `rules/__init__.py` |
| 새 API 엔드포인트 | `backend/app/api/routes/` + `routes/__init__.py` |
| 스냅샷에 필드 추가 | `shared/contracts/` → Agent `snapshot.py` → Backend `schemas/telemetry.py` |
| 외부 서비스 연동 (가격, 크롤링) | `backend/app/services/` |
| 화면 추가 | `frontend/web/` |

## 두 개의 레지스트리

Collector와 Rule은 같은 패턴을 쓴다. 클래스를 만들고 `@register` 를 붙인 뒤
패키지 `__init__.py` 에 import 한 줄을 더하면 끝이다. 등록 목록을 따로
관리하는 파일은 없다.

```python
# agent/speccheck_agent/collectors/thermal.py
@register
class ThermalCollector(Collector):
    name = "thermal"
    milestone = "M2"
    def collect(self): ...

# backend/app/diagnosis/rules/hardware_rules.py
@register
class ThermalThrottling(Rule):
    rule_id = "HW-TEMP-001"
    requires = ("thermal",)      # 이 섹션이 없으면 규칙은 실행되지 않는다
    def evaluate(self, snapshot): ...
```

## 커밋하지 않는 것

telemetry는 개인 하드웨어 정보다. 다음은 `.gitignore` 로 막혀 있다.

- `*.db` — Agent 로컬 DB, Backend 스냅샷 DB
- `~/.speccheck/` — Agent 홈 디렉토리
- `backend/.env` — API 키
