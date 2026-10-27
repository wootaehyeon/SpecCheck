# SpecCheck 공개 배포

웹 화면과 API를 하나의 Render Web Service에서 제공한다. 도메인을 사기 전에도
Render가 발급하는 HTTPS 기본 주소를 공유할 수 있다. 프론트엔드의 API 요청은
같은 주소의 `/api/...`로 전송하므로 도메인을 연결할 때 코드를 다시 바꿀 필요가 없다.

## 공개 범위

- 견적 입력·분석·가격 조회·시장 조사 웹과 해당 API를 제공한다.
- 현재 웹의 성능·호환성 점수와 교체 추천은 예시 결과다. 공개 화면에 시범 서비스
  안내가 표시된다. 완성된 진단·구매 판단 서비스로 안내하지 않는다.
- `TELEMETRY_API_ENABLED=false`로 `/api/scan/*`, `/api/diagnosis/*`를 등록하지 않는다.
  업로드, 기기 목록, 프로세스 이력, 저장된 진단 결과도 공개되지 않는다.
- 공개하는 파일은 `frontend/web` 안의 파일뿐이다. 저장소 전체를 정적 서버로 열지 않는다.
- Agent 배포·PC 정보 업로드는 포함하지 않는다. 사용자 인증과 장치 소유권 검증을
  구현하기 전까지 공개 서버에서 telemetry API를 활성화하지 않는다.

## Render 배포

1. 이 변경 사항이 포함된 GitHub 브랜치를 준비한다.
2. Render 계정을 만들고 로그인한다. GitHub 저장소 접근을 연결한다.
3. **New → Blueprint**에서 `wootaehyeon/SpecCheck` 저장소와 배포할 브랜치를 선택한다.
4. 저장소 최상위 `render.yaml`을 사용한다. `speccheck` 서비스가 **Free**인지 확인한다.
5. 배포가 끝나면 서비스에 표시되는 실제 `https://...onrender.com` 주소로 접속한다.
   이 문서의 이름 예시는 예약된 주소가 아니며, 실제 주소는 Render가 발급한다.
6. 자동 배포는 꺼져 있다. 이후 변경은 Render에서 **Manual Deploy**로 반영한다.

Blueprint 대신 Web Service를 직접 만들 때의 설정:

| 항목 | 값 |
| --- | --- |
| Root Directory | 비워 두기: 저장소 최상위 |
| Runtime | Python |
| Python 버전 | `.python-version`의 Python 3.12 |
| Build Command | `pip install -r backend/requirements-web.txt` |
| Start Command | `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Plan | Free: 최초 공유·검증용 |
| Region | Singapore |

`backend`를 Root Directory로 지정하면 같은 서비스에서 제공할 `frontend/web`과
벤치마크 데이터 경로가 달라지므로 저장소 최상위를 사용한다.

## 환경변수

`render.yaml`에 다음 공개 배포 설정이 들어 있다.

| 변수 | 값 | 용도 |
| --- | --- | --- |
| `SERVE_FRONTEND` | `true` | 웹과 API를 같은 서버에서 제공 |
| `TELEMETRY_API_ENABLED` | `false` | 인증 없는 PC 스캔·진단 API 제외 |
| `CORS_ORIGINS` | 빈 문자열 | 같은 주소의 웹에서 API 사용 |
| `LLM_ENABLED` | `false` | 서버에 설치되지 않은 로컬 Ollama 호출 안 함 |
| `QUALITY_EVAL_ENABLED` | `false` | 선택적 게시글 품질 모델 비활성화 |

네이버 실시간 가격을 사용하려면 Render의 **Environment**에 `NAVER_CLIENT_ID`,
`NAVER_CLIENT_SECRET`을 입력하고 재배포한다. 없으면 가격 조회 API가 오류 정보를
반환하며, 기존 웹은 샘플 가격으로 대체할 수 있다. 샘플 결과를 실제 시세 검증에
사용하지 않는다. 필요하면 `EBAY_OAUTH_TOKEN`도 서버 환경변수로 추가한다.

`.env` 파일이나 API 키를 GitHub·프론트엔드에 올리지 않는다.
공개 웹 런타임은 `requirements-web.txt`를 사용하므로 torch/transformers를
다운로드하지 않는다. 로컬 개발용 `requirements.txt`는 선택적 ML 및 테스트도 포함한다.

## 접속 확인

- `/`: 웹 메인 화면이 표시되는지 확인한다.
- `/input.html`: 견적 입력 후 분석 결과까지 이동하는지 확인한다.
- `/health`: `status: ok`가 반환되는지 확인한다.
- `/api/scan/snapshots`, `/api/diagnosis/rules`: GET 요청이 404인지 확인한다.
- 휴대전화의 모바일 데이터 등 다른 네트워크에서도 접속해 본다.
- API 키를 입력했다면 가격 응답이 `source: naver`이고 샘플 대체가 아닌지 확인한다.

무료 Web Service는 15분간 요청이 없으면 중지되고 다음 접속 때 다시 시작하므로
첫 응답이 늦을 수 있다. 무료 인스턴스는 상시 운영용이 아니다. 이번 구성은
개인 PC 데이터를 저장하지 않으므로 영구 디스크를 요구하지 않는다.
가격 캐시는 재시작 시 초기화될 수 있다.

## 로컬에서 배포 모드 확인

기존 개발 명령은 그대로 사용할 수 있다. 공개 설정을 직접 확인할 때는:

```powershell
$env:SERVE_FRONTEND = 'true'
$env:TELEMETRY_API_ENABLED = 'false'
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 연다. 종료한 뒤 같은 PowerShell에서
로컬 Agent 개발을 재개하려면 `Remove-Item Env:SERVE_FRONTEND`와
`Remove-Item Env:TELEMETRY_API_ENABLED`로 위 임시 설정을 해제한다.
기존 `dev-frontend.ps1`의 5599 포트는 로컬 8000 포트 Backend를 사용한다.

## 나중에 도메인 연결

1. 도메인을 구매한다.
2. Render 서비스의 **Settings → Custom Domains**에 도메인을 추가한다.
3. 도메인의 DNS 관리 화면에 Render가 안내하는 레코드를 입력한다.
4. Render에서 검증 완료와 HTTPS 인증서 발급을 확인한다.

웹/API가 같은 서비스에 있어 별도 `api` 서브도메인은 필요 없다.

## 공식 문서

- [FastAPI 배포](https://render.com/docs/deploy-fastapi)
- [Blueprint 설정](https://render.com/docs/blueprint-spec)
- [Python 버전 지정](https://render.com/docs/python-version)
- [무료 서비스 제한](https://render.com/docs/free)
- [도메인 연결](https://render.com/docs/custom-domains)
