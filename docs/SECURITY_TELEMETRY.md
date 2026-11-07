# Sysmon 프로세스 이력과 보안 진단

## 적용 범위

기존 Basic Scan, 성능·수명 규칙, 견적/가격 기능을 유지한다. Advanced 영역에
사용자가 선택하는 Sysmon 프로세스 이벤트 수집을 추가한다. 이번 구현은 CLI와
Backend 개발 기반이며, 배포용 동의 UI·Windows 서비스·인증 서버를 완성한 상태는 아니다.

Sysmon Event ID 1(생성), 5(종료)를 `(device_id, ProcessGuid)`로 연결한다.
PID는 재사용되므로 단독 연결 키로 쓰지 않는다. 시작과 종료가 모두 관측된 경우에만
그 차이를 실행 지속 시간으로 계산할 수 있다. 한쪽이 없으면 미상으로 표시한다.
실행 지속 시간은 전경 앱 사용 시간이나 CPU 사용 시간이 아니다.
시계열 API는 원시 이벤트를 반환하며 실행 시간 집계·차트는 아직 제공하지 않는다.

## 수집과 동의

Sysmon은 미리 설치·설정되어 있어야 한다. 설치/설정에 필요한 관리자 권한과
사용자의 수집 동의는 별개다. `monitor`는 일반 권한에서 실행하면 수집 전에 Windows
UAC 승인을 요청한다. 승인하면 현재 Python과 설정으로 관리자 권한의 새 창을 열고,
취소하면 DB 저장·수집·업로드 없이 종료한다. 이미 관리자라면 현재 창에서 실행한다.
Agent는 Sysmon 설치나 로그 ACL 변경을 수행하지 않는다.
이벤트 로그 읽기가 거부되거나 로그가 비활성화되면 security 섹션에 오류를 기록한다.

`monitor`는 권한 거부·로그 정보 접근 실패·로그 비활성화를 발견하면 안내 후 종료 코드 2로
중단한다. 이 경우 실패 스냅샷을 반복 저장하거나 업로드하지 않는다. `--security-consent`는
수집 동의이며 Windows 관리자 권한을 부여하는 옵션이 아니다.
권한 오류가 나면 PowerShell을 **관리자 권한으로 실행**하고 Agent 폴더에서 다시 실행한다.
관리자 실행 후에도 실패하면 다음 명령으로 Sysmon 로그 접근/설치 상태를 확인한다.

```powershell
Get-WinEvent -ListLog 'Microsoft-Windows-Sysmon/Operational' -ErrorAction Stop |
    Select-Object LogName, IsEnabled, RecordCount
```

전용 서비스 계정을 사용하는 배포에서는 해당 로그의 읽기 권한을 별도로 설정해야 한다.
Agent는 계정 권한이나 로그 ACL을 자동 변경하지 않는다.

`SpecCheck/agent` 디렉터리에서:

```powershell
# 기존 Basic Scan: Sysmon을 읽지 않음
python -m speccheck_agent scan

# 최근 1시간의 로그를 수집하는 데 동의하고 1회 저장
python -m speccheck_agent scan --security-consent

# 명령 실행 이후의 이벤트를 30초마다 조회·저장
python -m speccheck_agent monitor --security-consent --interval 30

# Backend 전송에도 동의: 이전 미전송 security 단독 스캔도 재전송
python -m speccheck_agent monitor --security-consent --upload
```

`Ctrl+C`는 SpecCheck 수집을 중단한다. 이미 저장된 이력과 별도로 설치된 Sysmon
서비스의 Windows 로그 기록은 유지된다. 사용자에게 수집 중지, 이력 삭제,
Sysmon 제거/관리의 차이를 설명해야 한다. 명령줄 플래그는 개발용 동의 수단이다.
배포 UI에서는 수집 항목·목적·보관 기간·서버 전송을 보여주고 동의를 별도로 기록한다.

기본 전송 목적지는 `http://127.0.0.1:8000`이며 `--upload` 없이는 전송하지 않는다.
Gemma는 기존과 동일하게 진단 결과 설명용이며 이번 구현은 모델을 실행하거나 설치하지 않는다.

## 보관되는 필드

- `event_id`, `record_id`, `occurred_at`(UTC)
- `process_guid`, `process_id`, `image`(파일명만)
- `parent_process_guid`, `parent_image`(파일명만)
- 수집 동의 버전/시각, 관측 시작/끝, 로그 누락 가능성, 미처리 여부

명령줄 인자, 사용자 이름, 실행 파일 전체 경로, 접속 IP, DNS 이름은 수집 결과에서
제외한다. PowerShell 단계부터 최소 필드만 반환하며 Backend도 허용하지 않은 필드를
거절한다. Sysmon 자체 Windows 로그에는 설정에 따라 전체 명령줄 등이 남을 수 있다.
파일명만으로 실행 파일의 동일성이나 신뢰성을 보장할 수는 없다.

## DB와 API

| 위치 | 테이블 | 내용 |
| --- | --- | --- |
| `~/.speccheck/agent.db` | `snapshots`, `collector_runs` | 로컬 수집 원본 JSON·수집 상태·업로드 여부 |
| `backend/data/snapshots.db` | `snapshots` | 업로드된 원본 JSON |
| 같은 Backend DB | `process_events` | 장치·시각·ProcessGuid로 조회할 이벤트 인덱스 |
| 같은 Backend DB | `diagnoses` | 진단 ID, 시각, 원본 입력 JSON, 결과 JSON, 규칙 코드 SHA-256 |

기존 DB에 테이블을 추가하며 기존 스냅샷을 삭제하지 않는다. 기존에 저장된 security
스냅샷의 이벤트 인덱스는 자동 역변환하지 않는다. 새 업로드부터 인덱스를 작성한다.

```text
POST /api/scan/snapshots
GET  /api/scan/process-events?device_id=...&start=2026-09-14T00:00:00Z&end=2026-09-15T00:00:00Z
POST /api/diagnosis/{snapshot_id}
GET  /api/diagnosis/{snapshot_id}/history
```

시계열 조회는 `[start, end)` 범위이며 시간대가 필수다. `process_guid` 필터와
`limit`(최대 2000), `offset`을 지원한다. 여러 스캔에 겹쳐 들어온 동일한 이벤트는
조회 시 중복을 제거한다. 실시간 추가/삭제 중 offset 페이지는 일관된 DB 스냅샷을
보장하지 않으므로, UI는 닫힌 과거 시간 구간을 조회하는 것이 좋다.

저장된 스냅샷을 진단할 때마다 진단 이력을 추가한다. 과거 결과를 덮어쓰지 않는다.
`POST /api/diagnosis/analyze`는 기존처럼 저장하지 않는다. 업로드 자체가 진단을
자동 실행하지는 않는다. 클라이언트가 반환된 snapshot_id로 진단 API를 호출한다.
규칙 해시는 변경 추적용이며 과거 코드를 복원하지는 않으므로 릴리스 소스도 보관한다.
Gemma 설명 재생성은 비결정적일 수 있지만, 저장된 결과 JSON 조회는 당시 설명을 그대로 반환한다.

## 관측 한계와 복구

- 실행 중에는 오래된 이벤트부터 최대 2000개씩 처리하고 DB 저장 후 RecordId를 전진시킨다.
- backlog가 있으면 `partial`, `truncated=true`로 표시하고 1초 후 다음 페이지를 읽는다.
- 로그 초기화/보관 범위 부족/수집 오류를 정상으로 해석하지 않는다. Event ID 255도 보관한다.
- cursor는 현재 프로세스 메모리에 있다. 재시작은 새 동의 시점부터 시작하며 중단 기간을
  자동 복구하지 않는다. 서비스 배포 전에는 동의 세션과 durable bookmark 복구가 필요하다.
- 장시간 로그가 순환되거나 초기화되면 데이터 유실이 가능하다. 로그가 없다고 프로세스가
  실행되지 않았다고 판단하지 않는다. Sysmon 필터로 제외된 이벤트도 복구할 수 없다.
- 업로드 실패 시 로컬 데이터는 남고 다음 회차에 재시도한다. 기존 `prune` 명령으로
  지운 미전송 스냅샷은 재전송할 수 없으므로 정리 전 업로드 상태를 확인한다.
- 자동 보관 만료/삭제 UI는 아직 없다. 배포 시 권장 초안은 이벤트 원본 7일,
  요약/진단 30일이며 사용 목적에 맞춰 사용자에게 명시한다. `process_events`만 지우면
  `snapshots.payload`와 `diagnoses.input_payload`에 원본이 남으므로 함께 정리해야 한다.

## 이번에 추가한 규칙

| 규칙 | 동작 |
| --- | --- |
| `SEC-SYSMON-025` | Event ID 25(프로세스 변조)가 관측되면 보안 검사와 프로그램 출처 확인 권고. 악성코드로 확정하지 않음 |
| `SEC-SYSMON-COVERAGE` | 로그 누락 가능성·미처리 이벤트·Sysmon 오류를 관측 한계로 표시 |

일반 프로세스가 실행됐다는 이유로 악성 판정이나 부품 구매 권고를 만들지 않는다.
security 단독 스캔의 `confidence`는 수집 섹션 확보 비율이지 PC 전체가 안전할 확률이 아니다.

## 기존 프로젝트에 맞는 추가 보안 기능

1. Defender 실시간 보호/서명 업데이트 상태와 방화벽 프로필 상태: 구현 비용이 낮고
   사용자에게 구체적 설정 점검을 권고할 수 있다. 다른 백신 사용/조직 정책도 고려한다.
2. 자동 실행 항목 변경: 시작 프로그램 변화와 부팅 후 CPU/메모리 부하를 연결해
   부품 구매 전에 프로그램 설정 점검을 제안한다. 승인된 설치와 악성 지속성을 구분해야 한다.
3. 프로세스별 자원 사용 시계열: 기존 performance 수집을 PID+생성 시각 등으로
   안전하게 연결하고 반복되는 고부하를 보여준다. Sysmon만으로 CPU 사용량을 추정하지 않는다.
4. Secure Boot/TPM 상태: 지원 여부와 권한 부족을 구분해 참고 정보로 제공한다.
5. 제한적인 네트워크/DNS 집계: 별도 동의 후 프로세스별 연결 횟수 중심으로 확장한다.
   접속 도메인 전체 수집이나 단일 연결을 근거로 한 악성 판정은 초기 범위에서 제외한다.

M5는 프로세스 이력·Advanced UI, M6는 기본 보안 상태, M7은 성능/이벤트 상관분석에
집중하는 구성이 적합하다. 기존 하드웨어 규칙과 견적 기능의 책임을 그대로 유지한다.

## 배포 전 남은 통합

기존 `/api/scan/*`, `/api/diagnosis/*` 개발 API에는 사용자 인증/장치 소유권 검증이 없다.
device_id 필터는 접근 통제가 아니므로 공개 서버에서는 계속 비활성화한다.
공개 웹에서는 [모니터링 연결](MONITORING.md)의 별도 `/api/monitor/*` API를 사용한다.
기기별 조회키·전송키, PostgreSQL 이력, 원본·이벤트·진단 삭제와 키 폐기를 지원한다.
연결 설정에서 Sysmon에 별도 동의하고 실제 Windows Agent를 실행해야 수집·전송이 시작된다.
Sysmon 설치 동의 및 UAC, 지속 동의/철회 UI, 서비스 재시작 bookmark, 이력 차트도
배포 통합 단계의 작업이다. 현재 구현은 로컬 개발 Backend에서 검증한다.

## 공식 자료

- [Sysmon 이벤트 및 설정](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon)
- [Defender 상태 조회](https://learn.microsoft.com/en-us/powershell/module/defender/get-mpcomputerstatus)
- [방화벽 프로필 조회](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallprofile)
- [Secure Boot 확인](https://learn.microsoft.com/en-us/powershell/module/secureboot/confirm-securebootuefi)
