# Docker Desktop으로 실행하기

Docker Desktop을 실행하고 **Linux containers** 모드를 사용한다.
Docker Compose 2.24 이상이 필요하다. Python을 PC에 설치하지 않아도 웹과 API를 실행할 수 있다.

## 실행

프로젝트 최상위 폴더에서 실행한다.

```powershell
docker compose up --build -d
docker compose ps
```

| 주소 | 내용 |
| --- | --- |
| http://localhost:8000 | 웹 화면 |
| http://localhost:8000/docs | API 문서 |
| http://localhost:8000/health | 서버 상태 |
| http://localhost:8000/monitor.html | 내 PC 모니터링 |

Docker Desktop의 **Containers → speccheck → app**에서도 상태와 로그를 확인하고
중지·시작할 수 있다. 프론트엔드는 API와 같은 서버에서 제공한다.

```powershell
docker compose logs -f app       # 로그 보기 (Ctrl+C로 로그 보기 종료)
docker compose stop             # 중지
docker compose start            # 다시 시작
docker compose down             # 컨테이너 제거, 저장 데이터 유지
docker compose up --build -d    # 코드를 수정한 뒤 다시 빌드하고 실행
```

8000 포트를 다른 프로그램이 사용한다면:

```powershell
$env:SPECCHECK_PORT = '8080'
docker compose up --build -d
# http://localhost:8080
```

변경한 포트는 다음 Compose 명령에도 적용되도록 같은 PowerShell에서 작업한다.
계속 사용할 값은 프로젝트 최상위 `.env`에 `SPECCHECK_PORT=8080`으로 저장할 수 있다.

## 설정과 저장 데이터

- `backend/.env`가 없어도 실행된다. 있으면 컨테이너 환경변수로 읽는다.
  API 키가 필요할 때 `backend/.env.example`을 `backend/.env`로 복사한 뒤 입력한다.
- Docker에서는 웹 제공, 스냅샷 저장 경로, Windows Ollama 주소를 Compose 설정으로 지정한다.
  나머지 설정은 `backend/.env`가 이미지 기본값보다 우선한다.
- 별도 설정이 없으면 로컬 모니터링을 활성화하고 SQLite를 사용한다.
  예제 `.env`를 복사하면 모니터링이 꺼지므로, 로컬 모니터링을 사용하려면 다음 값을 넣는다.

```dotenv
MONITORING_ENABLED=true
MONITORING_DATABASE_URL=sqlite:////app/backend/data/monitoring.db
```

환경변수를 바꾼 뒤에는 `docker compose up -d`로 컨테이너에 반영한다.
기본 구성은 localhost에서 사용하는 개발 환경이다. 공개 운영의 PostgreSQL 및 인증 설정은
[MONITORING.md](MONITORING.md)와 [DEPLOYMENT.md](DEPLOYMENT.md)를 따른다.

스냅샷, 진단 이력, 모니터링 DB, 가격 캐시는 `speccheck_speccheck-data` Docker 볼륨에 저장된다.
기존 PC의 `backend/data/snapshots.db`는 자동으로 가져오지 않는다.
`docker compose down`이나 컨테이너 재생성 후에도 볼륨 데이터는 유지된다.
`docker compose down -v`는 볼륨 데이터까지 삭제하므로 초기화할 때만 사용한다.
이미지에는 API 키, 로컬 DB, 스캔 결과, 가상환경, 작업 산출물을 포함하지 않는다.

## Windows Agent 연결

Agent는 Windows의 WMI/CIM·이벤트 로그를 사용하므로 Windows PC에서 실행한다.
웹과 API만 Linux 컨테이너에서 실행하며, Agent를 사용할 PC에는 Python 3.10 이상이 필요하다.

한 번 스캔해서 Docker의 API로 업로드하려면:

```powershell
# 기본 8000 포트를 쓸 때
.\scripts\scan.ps1 --upload

# Docker 포트를 8080으로 바꿨을 때
$env:SPECCHECK_BACKEND_URL = 'http://127.0.0.1:8080'
.\scripts\scan.ps1 --upload
```

지속적인 모니터링은 웹의 **내 PC 모니터링**에서 연결 설정과 Agent ZIP을 내려받고
[MONITORING.md의 사용자 연결 절차](MONITORING.md#사용자-연결)를 따른다.
Docker를 실행하는 것만으로 PC 수집이 시작되지는 않는다.

## 선택 기능

Windows에 설치한 Ollama를 사용하려면 `ollama pull gemma2:2b`를 실행하고
`backend/.env`에 `LLM_ENABLED=true`를 설정한 뒤 `docker compose up -d`로 반영한다.
컨테이너는 `http://host.docker.internal:11434`로 접속한다. Ollama가 컨테이너에서
접근 가능한 주소로 수신하도록 설정되어 있어야 한다. 연결 실패 시 기존 템플릿 설명을 사용한다.

기본 이미지는 `requirements-web.txt`를 사용하며 torch/transformers와 선택적 품질 평가 모델은
포함하지 않는다. 가격 API를 사용하려면 `backend/.env`에 해당 API 키를 입력한다.

## 공식 문서

- [Compose의 선택적 환경변수 파일](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)
- [Docker 빌드 컨텍스트와 .dockerignore](https://docs.docker.com/build/concepts/context/)
