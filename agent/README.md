# SpecCheck Local Agent

사용자 PC에서 telemetry를 수집해 표준 스냅샷으로 만드는 로컬 실행 프로그램.

**런타임 의존성이 없다.** WMI 조회는 pywin32 대신 PowerShell
`Get-CimInstance` 서브프로세스로 처리하므로 Python 3.10+ 만 있으면 동작한다.

## 실행

```powershell
cd agent

python -m speccheck_agent doctor        # 실행 환경 점검
python -m speccheck_agent collectors    # 등록된 수집기 목록
python -m speccheck_agent scan          # 스캔 (로컬 저장)
python -m speccheck_agent scan --upload # 스캔 후 Backend 전송
python -m speccheck_agent list          # 최근 스냅샷
python -m speccheck_agent show          # 최신 스냅샷 원문
python -m speccheck_agent health        # 수명/이벤트/성능 상태 요약
python -m speccheck_agent profile       # 부품 사양 프로필 (견적 시스템 입력 형식)
python -m speccheck_agent history       # 같은 기기의 스냅샷 추이
python -m speccheck_agent prune         # 오래된 스냅샷 정리
```

전체 스캔은 약 **10초** 걸린다 (i7-12700 / NVMe 기준 9.4~10.4초). 대부분은
성능 샘플링 대기 시간이며, `--collectors` 로 항목을 줄이면 그만큼 짧아진다.

### 자주 쓰는 옵션

```powershell
python -m speccheck_agent scan --collectors hardware   # 특정 수집기만
python -m speccheck_agent scan --out snapshot.json     # 파일로 저장
python -m speccheck_agent scan --no-save               # 로컬 DB에 남기지 않음
python -m speccheck_agent scan --note "RAM 교체 전"     # 시점 메모 (예측 검증용)

python -m speccheck_agent show --sections              # 원문 대신 섹션별 상태만
python -m speccheck_agent health --json                # 상태 요약을 JSON으로
python -m speccheck_agent prune --keep 30 --older-than 90
```

### 관리자 권한

권한 없이도 대부분 수집된다. **SMART(불량 섹터·수명)와 CPU 온도만** 관리자
권한을 요구하며, 없으면 해당 항목이 빠진 채 섹션이 `partial` 로 기록된다.
스캔이 실패하지는 않는다. `doctor` 가 현재 권한 상태를 알려준다.

## 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SPECCHECK_AGENT_HOME` | `~/.speccheck` | 스냅샷 DB 위치 |
| `SPECCHECK_BACKEND_URL` | `http://127.0.0.1:8000` | 업로드 대상 |
| `SPECCHECK_DEVICE_ID` | 호스트명 해시 | 기기 식별자 직접 지정 |
| `SPECCHECK_RELIABILITY_DAYS` | `30` | 이벤트 로그 관측 구간(일) |
| `SPECCHECK_PERF_SAMPLES` | `3` | 성능 카운터 샘플 횟수 |
| `SPECCHECK_PERF_INTERVAL_MS` | `1000` | 샘플 간격(ms) |

## 수집 항목

### 하드웨어 인벤토리 — `hardware` (M1)

무엇이 달려 있는가.

| 항목 | WMI 클래스 |
| --- | --- |
| 시스템 / OS | `Win32_ComputerSystem`, `Win32_OperatingSystem` |
| CPU | `Win32_Processor` |
| 메모리 | `Win32_PhysicalMemory` |
| GPU | `Win32_VideoController` |
| 저장장치 | `Win32_DiskDrive` + `MSFT_PhysicalDisk` |
| 메인보드 / BIOS | `Win32_BaseBoard`, `Win32_BIOS` |

### 저장장치 상태 — `storage_health` (M2)

얼마나 닳았는가.

| 항목 | 자료원 | 권한 |
| --- | --- | --- |
| 볼륨 용량·여유 공간 | `Win32_LogicalDisk` (DriveType=3) | 일반 |
| 시스템 볼륨의 물리 디스크 | `Get-Partition` | 일반 |
| SMART 속성 (재할당·대기 섹터, 통전 시간, 총 쓰기량) | `MSStorageDriver_FailurePredictData` | **관리자** |
| 실패 예측 플래그 | `MSStorageDriver_FailurePredictStatus` | **관리자** |
| NVMe/SSD 수명·온도 | `Get-StorageReliabilityCounter` | **관리자** |

### 신뢰성 이벤트 — `reliability` (M2)

결함의 직접 증거가 남았는가. 기본 관측 구간은 최근 30일이며, **이벤트 원문이
아니라 EventID별 건수와 최초/최종 발생 시각만** 담는다.

| 분류 | Provider / EventID |
| --- | --- |
| WHEA 정정된 오류 | `Microsoft-Windows-WHEA-Logger` 17 / 19 / 47 |
| WHEA 치명적 오류 | `Microsoft-Windows-WHEA-Logger` 18 |
| 비정상 종료 | `Kernel-Power` 41, `EventLog` 6008 |
| 블루스크린 | `WER-SystemErrorReporting` 1001 |
| 디스크 오류 | `disk` 7 / 11 / 51 / 153, `volmgr` 161 |
| 파일 시스템 손상 | `Ntfs` 55 |

로그 보관 기간이 관측 구간보다 짧으면 `log_covers_window: false` 로 표시한다.
0건이 곧 "이상 없음"은 아니기 때문이다.

### 성능 — `performance` (M2)

지금 어떤 상태인가. 단발값이 아니라 **샘플링 구간(기본 3회 × 1초)의 평균/최대/최소**를
담는다. 평균이 높으면 상시 부하, 최대만 높으면 순간 스파이크다.

| 항목 | 자료원 |
| --- | --- |
| CPU 사용률 / 커널 시간 | `Win32_PerfFormattedData_PerfOS_Processor` |
| 가용 메모리 / 커밋 비율 / 페이징 | `Win32_PerfFormattedData_PerfOS_Memory` |
| 디스크 큐 길이 / 유휴 비율 | `Win32_PerfFormattedData_PerfDisk_PhysicalDisk` |
| 상위 점유 프로세스 | `Win32_PerfFormattedData_PerfProc_Process` |
| 동작 클럭 / 정격 클럭 | `Win32_Processor` |
| 전원 계획 | `powercfg /getactivescheme` (GUID로 판정) |
| CPU 온도 | `MSAcpi_ThermalZoneTemperature` (미지원 보드 다수) |

## 수집하지 않는 것

시리얼 번호, MAC 주소, 사용자명, 파일 경로, 프로세스 명령줄 인자.
프로세스는 **이미지 이름만** 남기고, 이벤트 로그는 집계만 남긴다.
기기 식별은 호스트명 해시로만 한다.

## 로컬 저장소

스냅샷은 `~/.speccheck/agent.db` (SQLite)에 쌓인다. 서버 업로드는 `--upload`
를 줬을 때만 일어난다.

스키마가 바뀌어도 **기존 DB를 지우지 않는다.** `schema_meta` 테이블에 버전을
기록하고 마이그레이션으로 올린다 — 과거 스냅샷이 사라지면 추세 분석(M9)의
근거가 통째로 사라지기 때문이다.

`prune` 은 `--keep` 과 `--older-than` 을 **모두** 만족하는 스냅샷만 지운다.
오래됐어도 최근 N개 안에 들면 남으므로, 몇 달 만에 켠 PC에서 시계열이
통째로 사라지지 않는다.

## 수집기 추가하기

```python
# speccheck_agent/collectors/thermal.py
from .base import Collector, register

@register
class ThermalCollector(Collector):
    name = "thermal"       # 스냅샷 sections의 키
    milestone = "M2"
    description = "온도 및 스로틀링"

    def collect(self) -> dict:
        rows, errors = cim.query_batch({...})
        return {...}
```

`collectors/__init__.py` 에 `from . import thermal` 한 줄을 추가하면 등록된다.

주의할 점.

- 조회가 여러 개면 `cim.query()` 를 반복하지 말고 **`cim.query_batch()`** 를
  쓴다. PowerShell 기동 비용이 조회당 약 2초다.
- CIM이 아닌 자료원(`Get-WinEvent`, `powercfg`, 샘플링 루프)도 배치에 넣을 수
  있다. `{"script": "..."}` 로 주면 된다. 단 **한 줄**이어야 한다 — 배치 전체가
  `;` 로 이어 붙기 때문이다.
- PowerShell 스크립트에는 **작은따옴표만** 쓴다. 큰따옴표는 subprocess →
  Windows 명령행 → PowerShell 파서를 거치며 이스케이프가 한 겹 더 필요해진다.
- 부분 실패는 반환 dict에 `"_partial": True` 를 넣어 알린다. 그러면 섹션
  상태가 `ok` 대신 `partial` 로 기록된다.
- 결측은 `None` 으로 둔다. **0으로 채우지 않는다.** "값이 0이다"와 "확인하지
  못했다"를 섞으면 진단 규칙이 없는 근거로 판정하게 된다.

## 테스트

```powershell
python -m pytest
```

CIM(Windows)에 의존하지 않는 순수 로직만 검증하므로 어느 환경에서도 돈다.
collector 테스트는 CIM이 돌려준 행(dict)을 계약 형식으로 바꾸는 과정만 본다.
PowerShell 호출 자체는 실기기 스캔으로 확인한다.
