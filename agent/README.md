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
python -m speccheck_agent profile       # 부품 사양 프로필 (견적 시스템 입력 형식)
```

### 자주 쓰는 옵션

```powershell
python -m speccheck_agent scan --collectors hardware   # 특정 수집기만
python -m speccheck_agent scan --out snapshot.json     # 파일로 저장
python -m speccheck_agent scan --no-save               # 로컬 DB에 남기지 않음
python -m speccheck_agent scan --note "RAM 교체 전"     # 시점 메모 (예측 검증용)
```

## 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SPECCHECK_AGENT_HOME` | `~/.speccheck` | 스냅샷 DB 위치 |
| `SPECCHECK_BACKEND_URL` | `http://127.0.0.1:8000` | 업로드 대상 |
| `SPECCHECK_DEVICE_ID` | 호스트명 해시 | 기기 식별자 직접 지정 |

## 수집 항목 (M1)

| 항목 | WMI 클래스 |
| --- | --- |
| 시스템 / OS | `Win32_ComputerSystem`, `Win32_OperatingSystem` |
| CPU | `Win32_Processor` |
| 메모리 | `Win32_PhysicalMemory` |
| GPU | `Win32_VideoController` |
| 저장장치 | `Win32_DiskDrive` + `MSFT_PhysicalDisk` |
| 메인보드 / BIOS | `Win32_BaseBoard`, `Win32_BIOS` |

수집하지 **않는** 것: 시리얼 번호, MAC 주소, 사용자명. 기기 식별은
호스트명 해시로만 한다.

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

주의할 점 두 가지.

- 조회가 여러 개면 `cim.query()` 를 반복하지 말고 **`cim.query_batch()`** 를
  쓴다. PowerShell 기동 비용이 조회당 약 2초다.
- 부분 실패는 반환 dict에 `"_partial": True` 를 넣어 알린다. 그러면 섹션
  상태가 `ok` 대신 `partial` 로 기록된다.

## 테스트

```powershell
python -m pytest
```

CIM(Windows)에 의존하지 않는 순수 로직만 검증하므로 어느 환경에서도 돈다.
