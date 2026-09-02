# SpecCheck Diagnostics

Windows의 정규화된 Hardware / Performance / Storage / WHEA 데이터를 받아 Basic Scan 진단으로 보여 주는 로컬 우선 프로토타입입니다.

## 주요 기능

- Vinext/React 진단 UI와 Node.js Local Agent
- Ollama 기반 로컬 Gemma 진단 및 deterministic fallback
- `diagnosis.schema.json` 기반 Diagnosis JSON v1.0.0
- SQLite 진단 이력 저장
- Risk, Finding, Hardware Inventory, 수집 출처, AI 설명 표시

Rule Detection과 Windows collector 자체는 담당 파트가 연결할 수 있도록 입력 adapter로 분리했습니다. 현재 빈 요청으로 스캔하면 재현 가능한 fixture를 사용하며, 실제 정규화 snapshot은 `POST /api/scans`의 `snapshot` 필드로 전달합니다.

## 빠른 실행

필수 조건은 Node.js 22.13 이상과 pnpm입니다.

```powershell
pnpm install
pnpm dev:all
```

- UI: `http://localhost:3000`
- Local Agent: `http://127.0.0.1:4318`
- Ollama: `http://127.0.0.1:11434` (선택)

UI만 실행하면 Demo mode로 결과 구조를 확인할 수 있습니다. `dev:all`은 UI와 Agent를 함께 시작하며 실행한 Basic Scan 결과를 `data/speccheck.db`에 저장합니다.

## Local Gemma

기본 모델 식별자는 `gemma3:4b`입니다. Ollama와 사용할 모델을 로컬에 준비한 뒤 Agent를 실행하면 자동으로 연결합니다. 다른 Gemma tag를 사용할 때는 환경 변수를 설정합니다.

```powershell
$env:SPECCHECK_GEMMA_MODEL='gemma3:4b'
$env:SPECCHECK_OLLAMA_URL='http://127.0.0.1:11434'
pnpm dev:all
```

Ollama가 없거나 모델 호출이 실패해도 스캔은 실패하지 않습니다. 동일 Finding에서 생성하는 한국어 template 설명으로 전환되고 UI에 `SAFE FALLBACK`으로 표시됩니다. Gemma URL은 SSRF와 원격 데이터 전송을 막기 위해 loopback 주소만 허용합니다.

## API

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/health` | Agent와 Gemma 상태 |
| `POST` | `/api/scans` | fixture 또는 전달된 snapshot으로 Basic Scan 실행 |
| `GET` | `/api/scans/latest` | SQLite에 저장된 최신 Diagnosis |
| `GET` | `/api/schema/diagnosis` | Diagnosis JSON Schema |

실제 collector 연결 예시는 [collector-integration.md](docs/collector-integration.md)를 참고하세요. 진단 결과 계약의 원본은 [diagnosis.schema.json](schemas/diagnosis.schema.json)입니다.

## 검증

```powershell
pnpm test
pnpm build
```

테스트는 Risk 경계값, Diagnosis 조립, SQLite round-trip, Gemma endpoint의 loopback 제한을 확인합니다.

## 보안 기본값

- Agent는 `127.0.0.1`에만 bind합니다.
- UI origin은 기본적으로 `localhost:3000`과 `127.0.0.1:3000`만 허용합니다.
- 요청 body는 1 MB로 제한합니다.
- Gemma endpoint는 loopback만 허용하고 진단 데이터가 외부로 나가지 않습니다.
- Sysmon은 Basic Scan에서 수집하지 않습니다.
