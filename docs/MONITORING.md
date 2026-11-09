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
- 전송키는 조회키와 분리된다. 전송키로 원시 스냅샷·성능 이력·이벤트를 읽거나 다른 PC에
  업로드할 수 없다. Agent의 구매 지원을 위한 `/api/monitor/assistance`는 자신의 기기에서
  최근 7일 내 수신한 진단과 교체 후보만 제한적으로 반환한다. 선택적 `snapshot_id`도
  같은 기기 범위에서 검사하며 조회키나 원시 telemetry를 포함하지 않는다.
- DB에는 키 원문을 저장하지 않고 SHA-256 해시만 저장한다. 키는 URL에 넣지 않는다.
- 연결키는 90일 동안 유효하다. 조회키 백업 파일은 다른 브라우저에서 가져올 수 있다.
  파일을 가진 사람이 이력을 볼 수 있으므로 공유하지 않는다.
- 웹에서 8자리 일회용 코드를 발급하고 프로그램이 코드를 교환할 때 전송키를 발급한다.
  코드는 10분간 유효하며 DB에는 해시만 저장한다. 발급과 교환은 서버 재시작 후에도 유지된다.
  새 코드 발급만으로 기존 프로그램을 끊지 않으며, 코드를 교환한 시점에 이전 전송키를 폐기한다.
  연결 해제는 미사용 코드와 해당 기기의
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

Render에서 환경변수를 **Save only**로 저장했다면 **Save and deploy**로 반영한다.
**Restart service**는 이전 배포의 설정을 재사용하므로 새 환경변수를 적용하지 않는다.

`/api/monitor/status`의 `enabled: true`, `persistent: true`와 실제 PC 연결 성공을 확인한다.
Neon Free에도 저장 공간과 연산량 한도가 있다. 지속적인 24시간 수집은 무료 연산량을
초과할 수 있으므로 실제 사용량을 확인한다. 서버가 재시작되어도 외부 DB의 이력과 키는 유지된다.

## 사용자 연결

1. 웹의 **내 PC 모니터링**을 연다.
2. **Windows용 다운로드**를 누르고 `SpecCheck-Agent.exe`를 실행한다. Python 설치는 필요 없다.
3. 웹에서 수집 항목·서버 전송에 동의하고 **연결 코드 받기**를 누른다.
4. 표시된 `ABCD-2345` 형식의 코드를 프로그램에 입력하고 **연결하고 시작**을 누른다.
   서버 주소는 빌드 시 포함되며, 다른 개발 서버에 연결할 때만 **서버 주소 확인·변경**을 사용한다.
5. 웹은 프로그램 연결 대기 → 첫 데이터 수집 중 → 대시보드 순서로 전환한다.
   연결 대기 중에는 3초, 데이터 표시 후에는 10초마다 확인한다. Agent 수집 간격은 기본 30초다.

코드는 한 번만 사용할 수 있다. 만료되거나 잘못 입력한 경우 **새 코드 발급**으로 재시도한다.
같은 브라우저 탭을 새로고침해도 유효한 코드를 다시 표시하며, 프로그램은 연결 정보를
Windows 사용자 계정에 묶인 DPAPI로 암호화해 `~/.speccheck/desktop-connection.dat`에 저장한다.
다음 실행부터 코드를 다시 입력하지 않는다. 웹의 **프로그램 다시 연결**은 기존 기기와 이력을
유지하면서 새 코드를 발급한다. 코드를 아는 사람은 해당 PC의 전송 권한을 받을 수 있으므로 공유하지 않는다.

Agent는 하드웨어 사양을 5분마다 읽고 CPU·메모리·디스크 부하·온도·상위 점유 프로세스
이름을 주기적으로 수집한다. 지원하지 않는 온도 등은 `확인 못함`으로 표시한다.
프로세스 CPU 카운터는 코어별 합계여서 100%를 넘을 수 있다.

개발 중 GUI를 직접 실행하려면 `cd agent` 후 `python -m speccheck_agent.desktop`을 사용한다.
기존 CLI 자동화가 필요한 경우에는 연결 설정을 `agent/speccheck-monitor.json`에 넣고
다음 명령으로 기본 모니터링을 백그라운드에서 시작·확인·중지할 수 있다.
Python 3.12를 사용하며 Sysmon 이력은 수집하지 않는다. PC 부팅 시 자동 시작은 등록하지 않는다.

```powershell
.\scripts\monitor.ps1 -Consent
.\scripts\monitor.ps1 -Action Status
.\scripts\monitor.ps1 -Action Stop
```

로그와 로컬 DB는 저장소의 `.speccheck` 폴더에 저장된다. 연결 설정·조회키 백업·로컬 자료는
Git에서 제외된다. 중지해도 이미 저장된 이력은 유지된다.

프로세스 시작·종료 이력을 원하면 연결할 때 별도 체크박스에 동의한다. Sysmon이 미리
설치되어 있어야 하며, 프로그램이 관리자 권한으로 다시 시작할지 안내한다.
Agent는 Sysmon을 설치하거나 로그 접근 권한을 변경하지 않는다. 수집 권한이 없으면
이유를 알리고 중단한다. 일반 성능 모니터링에는 Sysmon이나 관리자 권한이 필수가 아니다.

이미 연결된 PC는 **프로세스 이벤트 이력 → Sysmon 수집 켜기**에서 동의·설정을 변경할 수 있다.
기존 기기와 이력은 유지되고 새 연결 코드가 표시된다. 프로그램에서 **수집 중지**를 누른 후
새 코드를 입력하고 시작한다. CLI를 유지하는 개발 환경에서는 기존 설정 발급 API를 사용할 수 있다.

```powershell
.\scripts\monitor.ps1 -Action Stop
.\scripts\monitor.ps1 -Consent -SecurityConsent
.\scripts\monitor.ps1 -Action Status
```

Sysmon 수집과 해당 관리자 Agent의 중지에는 Windows UAC 승인이 필요하다. 승인 창은
사용자가 직접 확인한다. 백그라운드 Agent는 숨긴 창으로 실행하며 로그 접근 권한을 바꾸지 않는다.
끄기는 이후 이벤트 전송을 차단하며, 이미 저장된 이력은 보관 기간까지 남는다.

보안 이벤트는 실행 파일명, 이벤트 시각, 프로세스 관계만 보낸다. 명령줄, 전체 경로,
사용자 이름, 네트워크 주소는 보내지 않는다. 프로세스 실행 지속 시간과 전경 앱 사용
시간은 같지 않으며, 이 화면은 전경 앱 사용 시간을 계산하지 않는다.

## 중단·삭제·보관

- 프로그램에서 **수집 중지**를 누르거나 창을 닫으면 수집과 전송이 중단된다. CLI에서는
  `Ctrl+C`를 사용한다. Windows 서비스나 자동 시작을
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
브라우저 테스트는 합성 데이터로 EXE 다운로드 경로·코드 연결·수집 대기·모니터링·다른 브라우저 복원·연결 해제를
검증한다. 테스트가 사용자의 실제 PC 자료를 수집하거나 외부 서버로 전송하지 않는다.

## Windows 프로그램 빌드와 배포

Windows에서 Python과 Tk가 설치된 개발 환경으로 실행한다. 사용자는 Python을 설치하지 않는다.

```powershell
python -m pip install -r agent/requirements-build.txt
# 실제 배포할 서버의 공개 origin을 지정한다. 아래 도메인은 예시다.
python scripts/build-windows-agent.py --backend-url https://your-speccheck.example.com
# 로컬 개발용:
python scripts/build-windows-agent.py --backend-url http://127.0.0.1:8000
```

출력은 `agent/releases/SpecCheck-Agent.exe`, SHA-256 체크섬, `build-info.json`이다.
서버 URL만 내장하며 연결키·로컬 DB·설정 파일은 포함하지 않는다. 기본 다운로드 API는 이 EXE를
제공하고, 파일이 없으면 웹에 준비 중 상태를 표시한다. Docker는 빌드 컨텍스트에 있는 EXE를 포함한다.
Linux 서버에서 Windows EXE를 직접 빌드하지 않는다. GitHub Actions의 **Windows Agent**를
수동 실행하면 입력한 서버 주소로 Windows 빌드와 GUI 시작 검사를 수행하고 아티팩트를 보관한다.
Agent 변경이 main에 반영되면 기존 공개 서버 주소로 빌드하고, GUI 시작 검사 통과 후 해당 커밋의
`windows-agent-<sha>` GitHub Release에 EXE와 체크섬을 게시한다. PR에서는 검사와 아티팩트 생성만 수행한다.
공개 origin은 저장소 변수 `SPECCHECK_PUBLIC_ORIGIN` 또는 수동 실행 입력으로 변경할 수 있다.

Render처럼 EXE를 저장소에 넣지 않는 환경에서는 빌드 결과를 공개 릴리스 자산으로 올리고
`MONITORING_AGENT_DOWNLOAD_URL=https://github.com/wootaehyeon/SpecCheck/releases/latest/download/SpecCheck-Agent.exe`를 설정한다.
`render.yaml`에도 같은 값을 지정했다. 비공개 Actions
아티팩트 링크는 일반 사용자가 다운로드할 수 없으므로 사용하지 않는다.
서버의 다른 경로에 EXE를 두면 `MONITORING_AGENT_EXE`에 절대 경로를 지정한다.
`/api/monitor/status`의 `agent_download_available`과 `/api/monitor/agent.exe`를 확인한다.
서버 주소가 바뀌면 해당 주소로 EXE를 다시 빌드하거나 프로그램의 서버 주소를 변경한다.

공개 배포 전에는 배포자가 소유한 코드 서명 인증서로 서명한다. 인증서가 Windows 사용자
인증서 저장소에 있고 Windows SDK의 SignTool을 설치했다면 다음 옵션을 사용할 수 있다.

```powershell
python scripts/build-windows-agent.py --backend-url https://your-speccheck.example.com --sign-thumbprint YOUR_CERTIFICATE_THUMBPRINT
```

서명 후 검증과 체크섬 생성을 수행한다. CI의 기본 아티팩트는 서명되지 않는다.
앱 제어 정책이 서명되지 않은 파일을 차단하면 정책을 우회하지 않고, 서명된 빌드를 조직 정책에
맞게 배포한다. 서명만으로 모든 기기의 허용이나 SmartScreen 평판을 보장하지 않는다.
기본 모니터링은 일반 사용자 권한으로 실행한다. Sysmon을 선택하면 UAC 승인과 사전 설치가 필요하다.

## 공식 자료

- [Neon 요금과 Free 범위](https://neon.com/pricing)
- [Render 환경변수](https://render.com/docs/configure-environment-variables)
- [PostgreSQL 연결 드라이버](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#psycopg)
- [PyInstaller 번들링](https://pyinstaller.org/en/stable/usage.html)
- [Windows 사용자별 DPAPI 암호화](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
