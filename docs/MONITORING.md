# 내 PC 모니터링

공개 웹의 `/monitor.html`에서 본인 Windows PC를 연결한다. 웹 서버 자체의 사용률이나
예시 데이터가 아닌, 로컬 Agent가 보내는 실측값을 보여준다.

## 구조와 인증

```text
Windows Agent → HTTPS + 기기 전송키 → Render API → PostgreSQL
브라우저      → HTTPS + 기기 조회키 → Render API → 내 기기 이력
```

- 연결 시 무작위 조회키를 발급하고 브라우저에 저장한다. 로그인 계정 방식이 아닌
  기기 연결키 방식이며, 조회키를 가진 사람이 해당 기기를 조회할 수 있다.
- 전송키는 조회키와 분리된다. 전송키로 이력을 읽거나 다른 PC에 업로드할 수 없다.
- DB에는 키 원문을 저장하지 않고 SHA-256 해시만 저장한다. 키는 URL에 넣지 않는다.
- 연결키는 90일 동안 유효하다. 조회키 백업 파일은 다른 브라우저에서 가져올 수 있다.
  파일을 가진 사람이 이력을 볼 수 있으므로 공유하지 않는다.
- 새 Agent 설정을 내려받으면 이전 전송키를 폐기한다. 연결 해제는 해당 기기의
  원본·진단·성능 추이·이벤트와 연결키를 삭제하고 이후 업로드를 거절한다.
- 인증 없는 기존 `/api/scan/*`, `/api/diagnosis/*`는 공개 서버에서 계속 비활성화한다.

## PostgreSQL 연결

무료 Render의 로컬 디스크에 저장하지 않는다. Neon 또는 별도 PostgreSQL을 만들고
Render **Environment**에 다음 값을 추가한다. 기존 PostgreSQL을 사용한다면 반드시
SpecCheck 전용 DB나 전용 스키마 권한을 제공한다.

```dotenv
MONITORING_ENABLED=true
MONITORING_DATABASE_URL=postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

Neon에서는 Free 프로젝트를 만들고 연결 문자열을 복사한다. Render 설정에만 입력하고
채팅·GitHub·프론트엔드에 연결 문자열을 올리지 않는다. 외부 PostgreSQL에는 TLS가 필요하다.
PostgreSQL 스키마와 인덱스는 최초 연결 시 `monitor_*` 이름으로 생성한다.

코드 업로드 후 Render에서 **Manual Deploy → Deploy latest commit**을 실행한다.
Blueprint 변경을 동기화할 경우 `MONITORING_ENABLED=true`도 반영된다.
`MONITORING_DATABASE_URL`이 없으면 모니터링 API는 503으로 닫히고 설정 안내를 표시한다.
새 유료 Render 리소스는 Blueprint에 추가하지 않는다.

`/api/monitor/status`의 `enabled: true`, `persistent: true`와 실제 PC 연결 성공을 확인한다.
Neon Free에도 저장 공간과 연산량 한도가 있다. 지속적인 24시간 수집은 무료 연산량을
초과할 수 있으므로 실제 사용량을 확인한다. 서버가 재시작되어도 외부 DB의 이력과 키는 유지된다.

## 사용자 연결

1. 웹의 **내 PC 모니터링**을 연다.
2. 수집 항목·서버 전송에 동의하고 **내 PC 연결하고 설정 저장**을 누른다.
3. **Agent ZIP 다운로드**를 눌러 압축을 푼다.
4. 내려받은 `speccheck-monitor.json`을 압축을 푼 `SpecCheck-Agent` 폴더에 넣는다.
5. Windows PC에 Python 3.10 이상이 설치되어 있어야 한다. `Start-SpecCheck.cmd`를 실행하고
   안내된 수집·전송에 동의하면 Y를 누른다.
6. 웹에서 수신 상태와 실측값을 확인한다. 웹은 10초마다, Agent는 기본 30초마다 갱신한다.

Agent는 하드웨어 사양을 5분마다 읽고 CPU·메모리·디스크 부하·온도·상위 점유 프로세스
이름을 주기적으로 수집한다. 지원하지 않는 온도 등은 `확인 못함`으로 표시한다.
프로세스 CPU 카운터는 코어별 합계여서 100%를 넘을 수 있다.

프로세스 시작·종료 이력을 원하면 연결할 때 별도 체크박스에 동의한다. Sysmon이 미리
설치되어 있어야 하며, `Start-SpecCheck.cmd`를 우클릭하여 관리자 권한으로 실행한다.
Agent는 Sysmon을 설치하거나 로그 접근 권한을 변경하지 않는다. 수집 권한이 없으면
이유를 알리고 중단한다. 일반 성능 모니터링에는 Sysmon이나 관리자 권한이 필수가 아니다.

보안 이벤트는 실행 파일명, 이벤트 시각, 프로세스 관계만 보낸다. 명령줄, 전체 경로,
사용자 이름, 네트워크 주소는 보내지 않는다. 프로세스 실행 지속 시간과 전경 앱 사용
시간은 같지 않으며, 이 화면은 전경 앱 사용 시간을 계산하지 않는다.

## 중단·삭제·보관

- Agent 창에서 `Ctrl+C`를 누르면 수집과 전송이 중단된다. Windows 서비스나 자동 시작을
  등록하지 않는다. 실행되지 않는 동안에는 새 자료가 수집되지 않는다.
- 원본은 로컬 `~/.speccheck/monitor/<device_id>/agent.db`에도 저장한다. 전송에 실패하면
  다음 회차에 같은 기기의 미전송 자료부터 재시도한다. 로컬 이력은 자동 삭제하지 않는다.
- 서버는 최근 7일 이력을 조회한다. 7일이 지난 원본·진단·이벤트는 업로드 처리 시 정리한다.
  서버가 유휴 중이고 업로드가 없으면 물리 삭제는 다음 처리 시점까지 지연될 수 있다.
- 웹의 **연결 해제·서버 이력 삭제**는 기기 키를 폐기하고 해당 기기의 서버 이력을
  삭제한다. 로컬 DB와 Sysmon 자체의 Windows 로그는 남으므로 별도로 관리한다.
- 수집을 선택한 시점 이전의 Sysmon 이력을 자동 복구하지 않는다. Agent 재시작 시
  새로운 관측 세션을 시작하므로 중단 구간은 누락될 수 있다.

## 개발 검증

로컬 개발에서는 별도 SQLite 파일 URL을 명시할 수 있다. 공개 운영에는 PostgreSQL을 사용한다.

```powershell
$env:MONITORING_ENABLED = 'true'
$env:MONITORING_DATABASE_URL = 'sqlite:///C:/path/to/dev-monitor.db'
$env:SERVE_FRONTEND = 'true'
$env:TELEMETRY_API_ENABLED = 'false'
python -m uvicorn app.main:app --app-dir backend --port 8000
```

CLI 직접 실행:

```powershell
cd agent
python -m speccheck_agent watch --config C:/path/to/speccheck-monitor.json --consent
# Sysmon에 별도 동의한 설정에서만:
python -m speccheck_agent watch --config C:/path/to/speccheck-monitor.json --consent --security-consent
```

Backend 테스트는 SQLite와 `MONITOR_TEST_DATABASE_URL`로 지정한 PostgreSQL 양쪽에서
접근 분리·재시작·키 폐기·이벤트 중복 제거를 확인한다. CI는 PostgreSQL 16을 사용한다.
브라우저 테스트는 합성 데이터로 연결·설정 다운로드·모니터링·다른 브라우저 복원·연결 해제를
검증한다. 테스트가 사용자의 실제 PC 자료를 수집하거나 외부 서버로 전송하지 않는다.

## 공식 자료

- [Neon 요금과 Free 범위](https://neon.com/pricing)
- [Render 환경변수](https://render.com/docs/configure-environment-variables)
- [PostgreSQL 연결 드라이버](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)
