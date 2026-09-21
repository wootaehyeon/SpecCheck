# M5–M9 구현 및 검증

Agent 로드맵 기준으로 정리한다. M5는 선택적 Sysmon 수집이며, Sysmon을 자동 설치하거나
Windows 이벤트 로그 원문을 외부로 전송하지 않는다.

| 단계 | 구현 | 검증 |
| --- | --- | --- |
| M5 Sysmon | Event 1/3/11/13/22, 24시간·최신 2,000건 제한, 분/프로세스 집계, Defender/TPM/Secure Boot | 합성 로그·권한 없음·빈 로그·개인정보 제거 테스트 |
| M6 Event Correlation | ±120초 창, CPU 과부하와 동일 프로세스의 생성/통신 연결, WHEA/디스크 오류 연결, 상위 3개 후보. UI에는 순위·신뢰도·근거·조치만 표시 | 소프트웨어/하드웨어 시나리오, 창 밖·다른 프로세스·결측 배제, 프로세스 해시 비노출 |
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

- `security.data.sysmon.status=skipped`: Sysmon 미설치, 로그 비활성 또는 읽기 권한
  부족. 다른 보안 상태를 살리기 위해 전체 security 섹션은 `partial`이다.
- 잘린 이벤트 목록은 `truncated=true`. 건수는 전체가 아닌 관측한 건수의 하한이다.
- 상관 후보는 인과관계나 악성코드 확정이 아니다. CPU 과부하 후보는 작업 관리자에서
  추가 확인하고, WHEA/디스크 후보는 점검 후 교체 여부를 판단한다. 근거가 없으면
  `conclusion=unknown`이며, 최대 세 후보에 순위와 근거가 붙는다.
- UI의 `rootCauseCandidates`는 M6 상관 후보를 표시하는 선택 필드다. `ProcessGuid`
  해시, 이벤트 원문, 사용자명, 경로, IP와 DNS 이름은 API 응답과 화면에 포함하지 않는다.
  후보의 권장 조치는 우선 `fix`이며, 하드웨어 교체는 별도 규칙의 근거가 있을 때만 제안한다.
- 이상 탐지는 각 지표에 **이전 측정 3개 + 현재 측정 1개**가 필요하다. 학습 표준편차에
  `max(평균 절댓값의 5%, 1)`을 최소 변동폭으로 적용하고 |z|≥3이면 `signal`을 낸다.
  `anomalyAnalysis`는 지표·현재값·기준선 평균·z-score·표본 수를 UI에 표시한다.
  Finding이나 구매 판정으로 자동 승격하지 않는다.
- 추세는 3개 이상 측정과 1일 이상 관측 범위가 필요하다. 지표별 결측은 제외한다.
  디스크별 wear/재할당 섹터, 시스템 볼륨 여유 공간, 24시간 WHEA 건수를 다룬다.
  `trajectoryAnalysis`는 추세 방향, 일별 변화량, 관측 수와 임계 도달 추정일을 UI에
  표시한다. 이 날짜는 선형 회귀의 탐색용 근사이며 고장 시점이나 구매 시점이 아니다.
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
`scripts/enable-sysmon.ps1`은 관리자 권한으로 내장 Sysmon 기능을 우선 활성화하고,
지원되지 않을 때만 Microsoft Sysinternals 공식 패키지를 내려받아 이 설정을 적용한다.
UI의 Basic Scan은 관리자 Agent를 시작할 때 이 절차를 자동 수행하고, 준비가 끝나면
같은 스캔에서 Sysmon 이벤트 조회를 다시 시도한다. 일반 CLI 스캔은 자동 설치하지 않는다.
**Sysmon 자체의 Windows 로그에는 민감한 원문 필드가 기록될 수 있으며**, Agent의
출력 축소는 OS 로그를 삭제하거나 익명화하지 않는다. 설정 의미는
[Microsoft Sysmon 문서](https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon)를 따른다.

## 검증

2026-09-22 Windows 11 / Python 3.13에서 Agent **73개**, Backend **89개** 테스트와
프론트엔드 production build를 통과했다. Backend에는 기존 Starlette/httpx 사용 중단 예정
경고 2개가 있다. 실제 관리자 Basic Scan에서 Sysmon Event 1/3/11/13/22가 집계되었고,
Gemma 4 진단도 생성됐다. 정상 상태에서는 CPU 과부하나 WHEA/디스크 오류가 없어 M6 후보가
비어 있는 것이 정상이다. M7은 실제 이력의 5개 지표를 분석해 신호 0건을 확인했고,
M8은 실제 23~24회 이력에서 수명 소모 안정·여유 공간 개선을 확인했다. 합성 CPU 급증과
여유 공간 감소 시나리오로 UI 변환과 프로세스 해시 비노출을 검증했다.

```powershell
cd agent
python -m pytest -q
cd ../backend
python -m pytest -q
```

새 섹션은 optional인 계약 1.1.0이며 Backend major 지원은 1을 유지한다.
Sysmon 이벤트 수집은 UI Basic Scan에서 관리자 Agent를 통해 자동 준비된다. 장기 실제
시계열의 예측 품질 평가는 합성 테스트와 별개의 운영 검증이다.
