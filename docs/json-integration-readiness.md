# JSON 연동 전 준비 작업

이 문서는 외부에서 전달될 Collector JSON을 SpecCheck에 연결하기 전에 정리한 기반 작업과 다음 연결 절차를 설명합니다. 아직 합의되지 않은 JSON 필드, Diagnosis Schema, SQLite 세부 구조는 변경하지 않았습니다.

## 완료한 작업

### 설정 중앙화

- Local Agent의 버전, 포트, CORS Origin, DB 경로, 데모 Snapshot 경로와 요청 크기 제한을 `agent/config.mjs`에서 관리합니다.
- Gemma endpoint, 모델명, 응답 제한 시간과 생성 옵션도 같은 설정 모듈에서 관리합니다.
- Agent 버전은 `package.json`에서 읽으므로 API 응답과 패키지 버전이 어긋나지 않습니다.
- UI는 `app/config.ts`를 통해 Agent 주소와 요청 제한 시간을 읽습니다.

### API Client 분리

`app/diagnostics-client.ts`가 다음 Local Agent 호출을 전담합니다.

- Agent 상태 조회
- 최신 Diagnosis 조회
- Basic Scan 실행
- 요청 제한 시간 처리
- HTTP 오류를 `DiagnosticsApiError`로 변환

UI는 URL이나 HTTP 응답 형식을 직접 다루지 않습니다. Collector JSON 연동 시에도 화면 코드를 수정하지 않고 API Client 또는 Agent 입력 Adapter에서 변환할 수 있습니다.

### UI 상태 구분

진단 화면은 다음 상태를 구분합니다.

| 상태 | 의미 |
| --- | --- |
| `checking` | Local Agent 연결 확인 중 |
| `live` | Agent API 응답을 받은 상태 |
| `demo` | Agent가 없어 데모 데이터를 표시하는 상태 |
| `error` | 사용자가 Scan을 실행했지만 Agent 요청이 실패한 상태 |

표시 중인 결과가 Agent 응답인지 브라우저 데모 데이터인지 `AGENT DATA`와 `DEMO DATA` 배지로 확인할 수 있습니다.

### Fixture 분리

- UI 전용 결과 예시: `app/fixtures/demo-diagnosis.ts`
- Agent 전용 입력 예시: `agent/fixtures/demo-snapshot.json`

데모 데이터는 실제 Collector 입력과 혼동되지 않도록 명시적인 fixture 경로에 둡니다. 빈 Scan 요청은 개발 편의를 위해 Agent fixture를 사용하며, 실제 연동에서는 `POST /api/scans`의 `snapshot` 값이 우선합니다.

### Snapshot 입력 경계

`agent/snapshot.mjs`가 Agent에 들어오는 Snapshot의 최소 구조를 검사합니다. 현재 검사는 JSON 계약 확정 전 단계이므로 다음 필수 컨테이너만 확인합니다.

- `machine`
- `resources`
- `findings`
- `inventory`
- `sources`
- Source의 `name`과 유효한 `status`

동료 JSON이 확정되면 이 경계에 Adapter와 전체 Schema 검증을 추가합니다.

## 환경 설정

| 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `NEXT_PUBLIC_SPECCHECK_AGENT_URL` | `http://127.0.0.1:4318` | UI가 호출할 Agent 주소 |
| `NEXT_PUBLIC_SPECCHECK_REQUEST_TIMEOUT_MS` | `5000` | UI API 제한 시간 |
| `SPECCHECK_AGENT_PORT` | `4318` | Agent 포트 |
| `SPECCHECK_ALLOWED_ORIGINS` | localhost Origin 목록 | 허용 UI Origin |
| `SPECCHECK_BODY_LIMIT_BYTES` | `1000000` | Agent 요청 본문 제한 |
| `SPECCHECK_DB_PATH` | `./data/speccheck.db` | SQLite 파일 경로 |
| `SPECCHECK_SNAPSHOT_PATH` | `./agent/fixtures/demo-snapshot.json` | 개발용 Snapshot |
| `SPECCHECK_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `SPECCHECK_GEMMA_MODEL` | `gemma3:4b` | 로컬 모델 |
| `SPECCHECK_GEMMA_TIMEOUT_MS` | `12000` | Gemma 진단 제한 시간 |

나머지 Gemma 상태 확인 시간과 생성 옵션은 `.env.example`에서 확인할 수 있습니다.

## Collector JSON 수신 후 연결 순서

1. 전달받은 원본 JSON과 정상/누락/오류 예시를 fixture로 추가합니다.
2. 원본 JSON을 현재 Snapshot 구조로 바꾸는 Adapter를 만듭니다.
3. Adapter 결과를 `validateSnapshot`에서 검증합니다.
4. Diagnosis JSON 생성 결과를 Schema와 테스트로 확인합니다.
5. `runBasicScan(snapshot)` 경로로 UI까지 연결합니다.
6. 데모, 부분 수집, 권한 부족, Collector 실패 상태를 각각 확인합니다.

## 의도적으로 보류한 작업

- `diagnosis.schema.json` 필드 변경
- Collector별 원본 필드 매핑
- Finding과 Recommendation 구조 변경
- SQLite 정규화 및 Migration
- Advanced Scan 입력 구조

이 항목은 동료 JSON 계약을 확인한 뒤 결정해야 중복 수정과 호환성 문제를 줄일 수 있습니다.
