# M5–M9 구현 및 검증

요청한 Agent 번호를 기준으로 정리한다. 기존 전체 서비스 로드맵의 M5(Gemma)와
구분하며, 과거 Agent 문서의 M6–M10이 여기서는 M5–M9에 해당한다.

| 단계 | 구현 | 검증 |
| --- | --- | --- |
| M5 Sysmon | Event 1/3/11/13/22, 24시간·최신 2,000건 제한, 분/프로세스 집계, Defender/TPM/Secure Boot | 합성 로그·권한 없음·빈 로그·개인정보 제거 테스트 |
| M6 Event Correlation | ±120초 창, CPU 과부하와 동일 프로세스의 생성/통신 연결, WHEA/디스크 오류 연결, 상위 3개 후보 | 소프트웨어/하드웨어 시나리오, 창 밖·다른 프로세스·결측 배제 |
| M7 ML Anomaly | 표준 라이브러리 z-score baseline, 기기별 이전 스냅샷 최대 200개 | 콜드 스타트·일정한 baseline·급증·기기 분리 |
| M8 Trajectory | 선형 추세, 기울기/임계 도달 시각과 근사 구간, 메모 기준 구간 분리 | 여유 공간 감소·정체·카운터 초기화·관측 부족 |
| M9 Agent 안정화 | 수집 병렬 실행, PowerShell 제한 시간·UTF-8·숨김 실행, 분석 실패 격리, 로그 회전, doctor, prune | Agent/Backend 회귀 테스트 및 로컬 Windows 스캔 |

## 실행

저장소 루트에서 `cd agent` 후 실행한다. 추가 ML 패키지는 필요하지 않다.

```powershell
python -m speccheck_agent doctor
python -m speccheck_agent scan
python -m speccheck_agent scan --collectors security --json
python -m speccheck_agent analyze
python -m speccheck_agent analyze <snapshot-id>
python -m speccheck_agent scan --note "SSD 교체 후"
python -m speccheck_agent --verbose --log-file scan
python -m speccheck_agent prune --keep 200
```

`scan`은 수집 후 세 분석 섹션을 붙여 로컬 SQLite에 저장한다. `analyze`는 저장된
스냅샷을 재분석해 출력하며 원본을 수정하지 않는다. `--json` 출력은 JSON 하나다.
`--no-save`는 DB를 만들거나 기록하지 않으며, 기존 DB가 있으면 과거 측정만 읽는다.
업로드는 기존처럼 `--upload`를 명시해야 한다. baseline 학습을 위해 서버에
접속하지 않으며, 업로드를 선택하면 현재 스냅샷의 분석 결과도 전송된다.

## 결과 해석

### doctor에서 Sysmon을 사용할 수 없다고 나올 때

`doctor`는 Sysmon 서비스·로그 활성화·읽기 접근을 별도로 확인한다. 준비되지
않은 선택 항목은 `[WARN]`으로 표시하며 Basic Scan의 종료 코드는 실패로 만들지
않는다. `not_installed`, `log_missing`, `log_disabled`, `access_denied`,
`service_stopped`, `query_failed`를 구분해 조치 방법을 표시한다.

미설치라면 **관리자 PowerShell을 열어 저장소 루트에서** 다음 명령을 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-sysmon.ps1
cd agent
python -m speccheck_agent doctor
python -m speccheck_agent scan --collectors security --no-save
```

설치 스크립트는 Microsoft 공식 Sysinternals 배포본을 다운로드하고 Microsoft
Authenticode 서명을 검증한 뒤 `agent/sysmon-config.xml`을 적용한다. 다운로드와
설치 로그는 Git에서 제외되는 `agent/var/`에 저장한다. 기존 Sysmon 서비스나
Windows 내장 Sysmon 바이너리가 있으면 덮어쓰지 않고 종료한다. 설치에는 관리자
권한이 필요하지만 설치 후에는 일반 사용자 터미널에서 `doctor`를 다시 실행해
읽기 권한을 확인할 수 있다. 로그 접근 실패를 숨기거나 전체 사용자에게 권한을
추가하는 처리는 하지 않는다.

Windows 내장 버전은 [Microsoft의 내장 Sysmon 활성화 절차](https://learn.microsoft.com/en-us/windows/security/operating-system-security/sysmon/how-to-enable-sysmon)를 따른다.
이미 설치된 서비스의 중지·로그 비활성·접근 거부는 재설치보다 해당 항목 점검이 먼저다.
Sysmon OS 로그에는 원문이 기록된다. 제거는 관리자 PowerShell에서 설치에 사용한
`& "$env:ProgramData\SpecCheck\Sysmon\Sysmon64.exe" -u`로 서비스/드라이버를 제거한다
(ARM64는 Sysmon64a.exe). 한글 경로에서 Sysmon XML 로더가 실패할 수 있으므로,
설치 스크립트는 검증한 실행 파일과 설정을 `%ProgramData%\SpecCheck\Sysmon`에
복사한 뒤 실행한다. 프로젝트를 영문 경로로 옮길 필요는 없다.

설치 후 `access_denied`라면 **일반 사용자 터미널**에서 `whoami /user`로 해당
사용자의 SID를 확인한다. 관리자 PowerShell을 저장소 루트에서 열어 다음 명령의
SID를 확인한 값으로 바꿔 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\grant-sysmon-read.ps1 -UserSid S-1-5-21-111-222-333-1001
```

이 명령은 지정한 사용자에게 **Sysmon 채널 읽기(0x1)**만 추가한다. 기존 채널
권한은 보존하며 전체 이벤트 로그 그룹 가입이나 쓰기·삭제 권한을 부여하지 않는다.
변경 전 권한은 `%ProgramData%\SpecCheck\Sysmon\channel-access-before.sddl`에
백업된다. 이후 일반 사용자 터미널에서 `doctor`와 보안 스캔을 다시 실행한다.
Sysmon 읽기 권한에는 OS 로그의 원문 열람이 포함된다.

### 수집·분석 결과

- `security.data.sysmon.status=skipped`: Sysmon 미설치, 로그 비활성 또는 읽기 권한
  부족. 다른 보안 상태를 살리기 위해 전체 security 섹션은 `partial`이다.
- 잘린 이벤트 목록은 `truncated=true`. 건수는 전체가 아닌 관측한 건수의 하한이다.
- 상관 후보는 인과관계나 악성코드 확정이 아니다. CPU 과부하 후보는 작업 관리자에서
  추가 확인하고, WHEA/디스크 후보는 점검 후 교체 여부를 판단한다. 근거가 없으면
  `conclusion=unknown`이며, 최대 세 후보에 순위와 근거가 붙는다.
- 이상 탐지는 각 지표에 **이전 측정 3개 + 현재 측정 1개**가 필요하다. 학습 표준편차에
  `max(평균 절댓값의 5%, 1)`을 최소 변동폭으로 적용하고 |z|≥3이면 `signal`을 낸다.
  Finding이나 구매 판정으로 자동 승격하지 않는다.
- 추세는 3개 이상 측정과 1일 이상 관측 범위가 필요하다. 지표별 결측은 제외한다.
  디스크별 wear/재할당 섹터, 시스템 볼륨 여유 공간, 24시간 WHEA 건수를 다룬다.
  현 Windows 어댑터는 vendor SMART 재할당 섹터를 제공하지 않으므로 이 지표는
  `null`이며 예측하지 않는다. WHEA는 누적 수명이 아닌 고정 24시간 관측 건수다.
- 임계값은 여유 공간 10%, wear 90%, 재할당 섹터 1이다. WHEA에는 임계 도달
  시각을 만들지 않는다. 도달 예측은 악화 방향이며 0~3,650일 범위일 때만 제공한다.
  기울기 ±2 표준오차와 이를 이용한 시간 범위는 탐색용 근사이며, 보정된 95% 구간이나
  물리적인 고장 시점이 아니다. 예측 불가는 `null`이다.
- `--note`가 있는 스냅샷부터 새 구간이다. 디스크 번호가 재사용될 수 있으므로
  부품 교체 후 메모를 남긴다. wear/재할당 카운터가 감소한 구간은 예측에서 제외한다.
- 기존 M2 수집 스텁 중 필요한 CPU/메모리/디스크 샘플, 볼륨 여유 공간·wear,
  WHEA/디스크 오류를 구현했다. 온도·전원 계획·vendor SMART 전체 지원은 포함하지 않는다.

## 프라이버시와 로그

Windows 이벤트 원문·명령줄·사용자명·파일/레지스트리 경로·DNS 이름·IP/MAC·시리얼은
새 보안 수집 결과에 포함하지 않는다. 이벤트 데이터는 PowerShell 내부에서 허용된
시간·ID·SHA-256 ProcessGuid로 축소하고 Python에서 분 단위로 집계한다.
프로세스 경로와 이름도 저장하지 않는다. 로그에는 collector 이름·상태·시간만 남긴다.
`--log-file`은 `SPECCHECK_AGENT_HOME/agent.log`에 1MiB, 백업 2개로 회전한다.
사용자가 직접 입력하는 `--note`는 원문 그대로 보관하므로 개인정보를 적지 않는다.

선택적 설정 예시는 [sysmon-config.xml](../agent/sysmon-config.xml)이다.
이 파일을 자동 설치하거나 시스템에 적용하지 않는다. **Sysmon 자체의 Windows
로그에는 민감한 원문 필드가 기록될 수 있으며**, Agent의 출력 축소는 OS 로그를
삭제하거나 익명화하지 않는다. 설정 의미는 [Microsoft Sysmon 문서](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon)를 따른다.

## 검증

2026-09-21 Sysmon 미설치 문제를 실제 기기에서 해결했다. Microsoft 서명을 확인한
Sysmon 15.22 설치와 현재 사용자의 Sysmon 채널 읽기 권한 추가 후, **일반 사용자**
`doctor`에서 Sysmon `[OK]`를 확인했다. 한글 경로의 XML 로더 문제는 ProgramData
경로로 스테이징해 해결했다. 시간 조건은 UTC XPath로 명시하며 EventLogReader로
스트리밍한다. 실측에서 Event 1/3/11/13/22 합계 **2,000건을 2.78초**에 수집했다.
상한 초과는 `truncated=true`로 표시한다. 최신 Agent 회귀 테스트는 **57개 통과**.
일반 사용자에게는 TPM/Secure Boot 등의 추가 제한이 있어 전체 security 섹션이
`partial`일 수 있으나, `security.data.sysmon.status=ok`와 구분한다.

2026-09-20 Windows 11 / Python 3.13.12에서 Agent **41개**, Backend **28개**
테스트 통과. Backend에는 기존 Starlette/httpx 사용 중단 예정 경고 1개가 있다.
일반 사용자 권한의 실제 스캔은 **11.36초**에 완료되었고 hardware/performance/
reliability는 `ok`, storage_health/security는 `partial`, 분석 세 섹션은 관측 부족으로
`partial`이었다. 수집 `error`는 없었다. `doctor`에서 Sysmon 로그를 읽을 수 없음을
확인했다. 실제 스냅샷은 Git에서 제외된 `agent/var/live.snapshot.json`에만 보관했다.

```powershell
cd agent
python -m pytest -q
cd ../backend
python -m pytest -q
```

새 섹션은 optional인 계약 1.1.0이며 Backend major 지원은 1을 유지한다.
Sysmon 설치 기기의 이벤트→집계 경로는 위 실측으로 확인했다. 장기 실제 시계열의
예측 품질 평가는 별개의 운영 검증으로 남는다. `scan`과 `doctor` 자체는 Sysmon
설치나 로그 접근 권한을 변경하지 않으며, 명시적으로 실행한 관리자 스크립트만 변경한다.
