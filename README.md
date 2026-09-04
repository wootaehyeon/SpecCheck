# 🖥️ SpecCheck — AI 기반 PC Lifecycle Platform

> 현재 PC의 **Hardware / Performance / System·Security telemetry**를 분석하여 문제의 원인을 진단하고,
> **현재 상태 유지**와 **Hardware/Software 변경**에 따른 예상 결과를 비교하여
> 최적의 **PC 관리 및 구매 의사결정**을 지원하는 AI 기반 PC Lifecycle Platform.

---

## 통합 진단 실행

현재 Basic Scan UI는 Python Local Agent가 생성한 `telemetry 1.1.0`을 FastAPI의
17개 규칙으로 분석하고 `diagnosis 1.1.0`으로 변환해 표시합니다.

```powershell
# Backend + UI
pnpm dev:all
```

`http://localhost:3000`에서 `기본 진단 시작`을 누르고 Windows UAC를 승인하면
Agent 수집, Backend 업로드, Diagnosis 생성, UI 갱신이 자동으로 이어집니다.
8000 포트가 사용 중이면 `$env:SPECCHECK_BACKEND_PORT=8001`처럼 포트를 지정한
뒤 `pnpm dev:all`을 실행할 수 있으며 UI와 Agent 업로드 대상도 함께 변경됩니다.

전체 연결 구조와 결정 사항은 [Collector JSON 통합](docs/collector-integration.md),
구현 기록은 [진단 JSON 통합 작업 기록](docs/json-integration-readiness.md)을 참고하세요.

---

## 📌 Project Overview

| 항목 | 내용 |
| --- | --- |
| **목적** | 추천 중심의 기존 서비스와 달리, 사용자의 실제 PC 상태를 진단하고 견적의 품질을 객관적으로 검증 |
| **핵심 가치** | 정량적 telemetry 분석 + LLM 추론을 결합해, 초보자도 이해할 수 있는 진단·의사결정 환경 제공 |
| **차별점** | "무엇을 사라"가 아니라 **"왜 사야 하는가 / 안 사도 되는가"** 를 데이터로 답한다 |
| **개발기간** | 2026년 4월 29일 ~ |

---

## 🧭 전체 아키텍처 흐름

```
                     SpecCheck
                         │
                 현재 PC 등록
                         │
          ┌──────────────┴──────────────┐
          │                             │
    Agent 설치 사용자              Agent 미설치 사용자
          │                             │
          ▼                             ▼
     Actual Scan                 Estimated Scan
     실제 시스템 진단               예상 시스템 진단
          │                             │
          └──────────────┬──────────────┘
                         ▼
                   AI Diagnosis
                         │
           ┌─────────────┼─────────────┐
           │             │             │
        Hardware      Software      Security
         Issue          Issue         Issue
           │             │             │
           └─────────────┼─────────────┘
                         ▼
                Root Cause Analysis
                         │
                         ▼
                  Action Decision
                         │
         ┌───────────────┼───────────────┐
         │               │               │
      유지한다          수정한다          구매한다
         │               │               │
         ▼               ▼               ▼
  No-Purchase       Software Fix     SpecCheck
   Scenario                         제품 추천/가격
         │                               │
         └───────────────┬───────────────┘
                         ▼
                   What-if Scan
                         │
            ┌────────────┴────────────┐
            │                         │
      현재 상태 유지              제품 교체
            │                         │
     예상 미래 상태              예상 개선 상태
            │                         │
            └────────────┬────────────┘
                         ▼
                  사용자 의사결정
                         │
                         ▼
                   구매 후 Scan
                         │
                         ▼
              실제 개선 여부 검증
```

### 🔁 예측 → 검증 → 학습 루프

Scan은 일회성 진단으로 끝나지 않는다. 예측한 결과와 실제 결과를 비교해 모델을 개선하는 폐루프 구조를 갖는다.

```
              Current PC
                  ↓
             Actual Scan
                  ↓
             AI Diagnosis
                  ↓
             Root Cause
                  ↓
         ┌────────┴─────────┐
         │                  │
      구매 안 함            구매
         │                  │
         ▼                  ▼
   No-Purchase          Upgrade
     Scenario           Scenario
         │                  │
         ▼                  ▼
   Estimated Scan      Estimated Scan
         │                  │
         └────────┬─────────┘
                  ▼
              Decision
                  │
                  ▼
            시간 경과 / 구매
                  │
                  ▼
             Actual Scan
                  │
                  ▼
         Prediction 비교
                  │
                  └────→ AI 개선
```

---

## 🔍 두 가지 Scan 모드

| 구분 | Actual Scan | Estimated Scan |
| --- | --- | --- |
| 대상 | Local Agent 설치 사용자 | Agent 미설치 사용자 |
| 데이터 | WMI/CIM, 성능 카운터, WHEA, Sysmon 등 실측 telemetry | 사용자가 입력한 사양 기반 추정치 |
| 정확도 | 높음 (실제 시스템 상태) | 보통 (통계·벤치마크 기반 예측) |
| 용도 | 원인 진단, 개선 검증 | 진입 장벽 없는 사전 진단, What-if 시뮬레이션 |

---

## ✨ Key Features

* **AI Diagnosis** — Hardware / Software / Security 3축으로 이상 징후 분류
* **Root Cause Analysis** — 증상이 아닌 근본 원인 추적 (예: 프레임 드랍 → 발열 스로틀링 → 쿨러 노후)
* **Action Decision** — 유지한다 / 수정한다 / 구매한다 중 데이터 기반 선택지 제시
* **What-if Scan** — "그대로 두면 6개월 뒤" vs "이 부품을 바꾸면" 시나리오 비교
* **No-Purchase Scenario** — 구매하지 않는 선택지를 1급 결과로 제시 (과소비 방지)
* **가격 시세 및 오버페이 판단** — 시장 평균가 대비 부품별 가격 적정성 평가
* **성능 밸런스 분석** — CPU–GPU 병목(Bottleneck) 및 비효율 조합 탐지
* **부품 호환성 검증** — CPU–메인보드, RAM, 파워 등 실제 조립 가능 여부 확인
* **구매 위험도 점수** — 종합 분석을 수치화한 점수와 개선 방향 제시
* **LLM 기반 도슨트** — Local Gemma로 진단 결과를 자연어 설명으로 변환
* **구매 후 검증** — 예측 대비 실제 개선폭을 측정해 모델에 피드백

---

## 🛠 구현 Phase

| 단계 | 구현 |
| --- | --- |
| **Phase 1** | WMI/CIM Hardware Inventory |
| **Phase 2** | Performance + Storage + WHEA |
| **Phase 3** | Rule-based Diagnosis |
| **Phase 4** | Local Gemma 설명 |
| **Phase 5** | SpecCheck 기존 호환성/가격 시스템 연결 |
| **Phase 6** | Local Agent 설치 프로그램 |
| **Phase 7** | Sysmon Advanced Scan |
| **Phase 8** | Process trajectory |
| **Phase 9** | ML Anomaly Detection |
| **Phase 10** | Graph/Temporal AI 연구 확장 |

---

## 🎯 전체 Milestone

| Milestone | 핵심 목표 | 결과물 |
| --- | --- | --- |
| M0 | Agent 기반 구축 | Local Agent 실행 |
| M1 | Hardware Inventory | WMI/CIM 수집 |
| M2 | Basic Health Scan | WHEA + Storage + Resource |
| M3 | Data Pipeline | Normalization + SQLite |
| M4 | Rule Detection | 기본 이상 탐지 |
| M5 | Local AI Diagnosis | Gemma 기반 설명 |
| **MVP** | **Basic Scan 완성** | **실제 사용자 진단 가능** |
| M6 | Sysmon 기반 구축 | Advanced Scan |
| M7 | Security Event Correlation | Process/Network/File 연결 |
| M8 | ML Anomaly Detection | 비정상 패턴 탐지 |
| M9 | Trajectory Analysis | 행동 sequence 분석 |
| M10 | SpecCheck 통합/배포 | 실제 서비스 완성 |

> **MVP 기준선**: M0–M5 완료 시점. 이때부터 실제 사용자 대상 Basic Scan 진단이 가능하다.
> 현재 진행 상황: Agent 축(우태현)은 **M0–M4 완료** — 자세한 내용은 [docs/AGENT_ROADMAP.md](docs/AGENT_ROADMAP.md).
> 전체 로드맵은 [docs/ROADMAP.md](docs/ROADMAP.md) 참조.

---

## 🚀 Differentiation

* **진단 중심** — 단순 추천이 아닌, 실제 시스템 telemetry에 근거한 원인 규명
* **구매하지 않을 자유** — No-Purchase Scenario를 동등한 결과로 제시
* **이유 있는 제안** — 대체 부품 제안 시 구체적 교체 이유와 근거 동반
* **검증되는 예측** — 구매 후 Actual Scan으로 예측 정확도를 되먹임
* **로컬 우선** — Local Agent + Local LLM(Gemma)로 telemetry를 외부로 내보내지 않음

---

## 📂 Repository Structure

```
SpecCheck/
├── agent/            # Local Agent — 사용자 PC telemetry 수집 (의존성 없음)
├── backend/          # API 서버 · 진단 엔진 / 가격 / 호환성 로직
├── shared/contracts/ # Agent ↔ Backend 데이터 계약 (단일 진실 공급원)
├── frontend/         # 웹 UI · PC 3D 조립 시각화
├── datasets/         # CPU/GPU 사양 · 벤치마크 데이터셋
├── tools/            # 커뮤니티 크롤링 등 보조 스크립트
├── scripts/          # 개발용 실행 스크립트
└── docs/             # 문서 · 발표자료
```

자세한 지도와 "무엇을 어디에 추가하는가"는 [docs/DIRECTORY.md](docs/DIRECTORY.md) 참조.

---

## 🚀 Quick Start

### 1. Backend

```powershell
pip install -r backend/requirements.txt
copy backend\.env.example backend\.env    # API 키 입력 (없어도 진단은 동작)
.\scripts\dev-backend.ps1                 # http://127.0.0.1:8000/docs
```

### 2. Local Agent (Windows)

```powershell
.\scripts\scan.ps1 doctor      # 실행 환경 점검
.\scripts\scan.ps1             # 스캔 (약 5초, 로컬 저장)
.\scripts\scan.ps1 --upload    # 스캔 후 Backend 전송
```

### 3. Frontend

```powershell
.\scripts\dev-frontend.ps1     # http://127.0.0.1:5599
```

### 4. 테스트

```powershell
.\scripts	est.ps1             # agent + backend 전체
```

### Local LLM (선택)

```powershell
ollama pull gemma2:2b
# backend/.env 에서 LLM_ENABLED=true
```

꺼져 있어도 진단은 동작하며, 설명만 템플릿으로 대체된다.

---

## 🔌 주요 API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/scan/snapshots` | Agent telemetry 스냅샷 업로드 |
| `GET` | `/api/scan/snapshots` | 스냅샷 목록 (기기별 시계열) |
| `POST` | `/api/diagnosis/analyze` | 스냅샷 즉시 진단 (저장 없이) |
| `POST` | `/api/diagnosis/{snapshot_id}` | 저장된 스냅샷 재진단 |
| `GET` | `/api/diagnosis/rules` | 진단 규칙 목록 (판정 기준 공개) |
| `POST` | `/api/price-check` | 부품 가격 오버페이 평가 |
| `POST` | `/api/optimize-estimate` | 중고 시세 기반 견적 최적화 |

---

## 📖 문서

| 문서 | 내용 |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 계층 구조 · 데이터 흐름 · 설계 원칙 |
| [docs/DIRECTORY.md](docs/DIRECTORY.md) | 디렉토리 지도 · 확장 지점 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Milestone 진행 상황 · 다음 작업 |
| [shared/contracts/README.md](shared/contracts/README.md) | 스냅샷 계약 · 버전 규칙 |

---

## 👥 Team Info

* **개발기간**: 2026년 4월 29일 ~
