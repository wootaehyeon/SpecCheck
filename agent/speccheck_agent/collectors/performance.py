"""Performance collector (Phase 2 / M2).

데이터 소스

- CPU/메모리/디스크 사용률
  ``Win32_PerfFormattedData_PerfOS_Processor`` (PercentProcessorTime)
  ``Win32_PerfFormattedData_PerfOS_Memory`` (AvailableMBytes, PagesPerSec)
  ``Win32_PerfFormattedData_PerfDisk_PhysicalDisk`` (AvgDiskQueueLength)
  ``Win32_PerfFormattedData_PerfProc_Process`` (상위 점유 프로세스)
- 온도 / 스로틀링
  ``MSAcpi_ThermalZoneTemperature`` (root/wmi) - 미지원 메인보드 다수
  ``Win32_Processor.CurrentClockSpeed`` 와 MaxClockSpeed 비율로 간접 추정
- 전원 계획
  ``Win32_PowerPlan`` (root/cimv2/power) - 절전 모드로 인한 성능 저하 판별

설계 노트: 단발성 값은 진단 근거로 약하다. 짧은 샘플링 구간(기본 3회 x 1초)의
평균/최대를 함께 담아 스파이크와 상시 부하를 구분할 수 있게 한다. 평균만 높으면
상시 부하(원인 규명 대상), 최대만 높으면 순간 스파이크(정상)다.

성능 카운터 이름은 ``Get-Counter`` 의 경로와 달리 CIM 클래스 속성이라 로케일과
무관하다. 한국어 Windows에서도 같은 키로 읽힌다.

전원 계획은 이름이 로케일마다 다르므로(균형 조정 / Balanced) 판정에는 GUID를 쓴다.

프라이버시: 프로세스는 **이미지 이름만** 남긴다. 명령줄 인자와 실행 경로는
수집하지 않는다. 규칙이 필요로 하는 것은 "무엇이 CPU를 먹고 있는가"이지
"그것이 어디에 설치되어 있는가"가 아니다.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ..win import cim
from .base import Collector, register

DEFAULT_SAMPLE_COUNT = 3
DEFAULT_INTERVAL_MS = 1000
TOP_PROCESS_COUNT = 5

#: 전원 계획 GUID -> (식별자, 표시 이름).
#: ``Win32_PowerPlan`` 은 root/cimv2/power 네임스페이스 접근이 막힌 환경이 있고
#: ElementName은 로케일마다 다르다. GUID는 두 문제에서 모두 자유롭다.
POWER_SCHEME_GUIDS = {
    "a1841308-3541-4fab-bc81-f71556f20b4a": ("power_saver", "절전"),
    "381b4222-f694-41f0-9685-ff5bb260df2e": ("balanced", "균형 조정"),
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": ("high_performance", "고성능"),
    "e9a42b02-d5df-448d-aa00-03f14749eb61": ("ultimate_performance", "최고의 성능"),
}

#: ``powercfg /getactivescheme`` 은 관리자 권한 없이도 활성 계획 GUID를 낸다.
#: 출력의 한글 부분은 콘솔 코드페이지 영향을 받지만 GUID는 ASCII라 안전하다.
_POWER_PLAN_SCRIPT = "[pscustomobject]@{ Active = ((powercfg /getactivescheme) -join ' ') }"

#: 한 샘플에서 읽는 카운터. 세 클래스를 한 번씩 읽고 필요한 값만 뽑는다.
#: 스크립트에는 작은따옴표만 쓴다 - 큰따옴표는 subprocess -> Windows 명령행 ->
#: PowerShell 파서를 거치며 이스케이프가 한 겹 더 필요해져 깨지기 쉽다.
_SAMPLE_STATEMENTS = (
    "$cpu = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_Processor"
    " | Where-Object { $_.Name -eq '_Total' }",
    "$mem = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_Memory",
    "$disk = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfDisk_PhysicalDisk"
    " | Where-Object { $_.Name -eq '_Total' }",
    "$samples += [pscustomobject]@{"
    " CpuPercent = [double]$cpu.PercentProcessorTime;"
    " CpuPrivilegedPercent = [double]$cpu.PercentPrivilegedTime;"
    " AvailableMBytes = [double]$mem.AvailableMBytes;"
    " CommittedPercent = [double]$mem.PercentCommittedBytesInUse;"
    " PagesPerSec = [double]$mem.PagesPerSec;"
    " DiskQueueLength = [double]$disk.AvgDiskQueueLength;"
    " DiskIdlePercent = [double]$disk.PercentIdleTime }",
)

#: 이미지 이름만 남긴다. Win32_PerfFormattedData_PerfProc_Process.Name 은 경로를 포함하지 않는다.
_TOP_PROCESS_SCRIPT = (
    "Get-CimInstance -ClassName Win32_PerfFormattedData_PerfProc_Process"
    " | Where-Object { $_.Name -ne '_Total' -and $_.Name -ne 'Idle' }"
    " | Sort-Object PercentProcessorTime -Descending"
    " | Select-Object -First " + str(TOP_PROCESS_COUNT) + " Name, PercentProcessorTime, WorkingSetPrivate"
)


def sample_count() -> int:
    return _env_int("SPECCHECK_PERF_SAMPLES", DEFAULT_SAMPLE_COUNT, 1, 10)


def interval_ms() -> int:
    return _env_int("SPECCHECK_PERF_INTERVAL_MS", DEFAULT_INTERVAL_MS, 100, 10000)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def build_sampling_script(count: int, interval: int) -> str:
    """샘플링 루프를 배치에 넣을 수 있는 한 줄 스크립트로 만든다.

    ``cim.query_batch`` 의 script 항목은 개행을 허용하지 않으므로 ``;`` 로 잇는다.
    마지막에 ``$samples`` 를 평가해 배열을 출력값으로 내보낸다.
    """
    body = "; ".join(_SAMPLE_STATEMENTS)
    return (
        "$samples = @(); "
        "for ($i = 0; $i -lt {count}; $i++) {{ "
        "if ($i -gt 0) {{ Start-Sleep -Milliseconds {interval} }}; {body} }}; "
        "$samples"
    ).format(count=count, interval=interval, body=body)


def build_queries(count: int, interval: int) -> dict[str, dict[str, Any]]:
    return {
        "samples": {"script": build_sampling_script(count, interval)},
        "processor": {
            "class_name": "Win32_Processor",
            "properties": ["CurrentClockSpeed", "MaxClockSpeed", "LoadPercentage"],
        },
        "top_processes": {"script": _TOP_PROCESS_SCRIPT},
        "power_plan": {"script": _POWER_PLAN_SCRIPT},
        # 다수의 메인보드가 지원하지 않는다. 실패해도 다른 항목은 살아남는다.
        "thermal": {
            "class_name": "MSAcpi_ThermalZoneTemperature",
            "namespace": "root/wmi",
            "properties": ["InstanceName", "CurrentTemperature"],
        },
    }


@register
class PerformanceCollector(Collector):
    name = "performance"
    milestone = "M2"
    description = "성능 카운터 샘플링 (CPU/메모리/디스크/온도)"

    def collect(self) -> dict[str, Any]:
        count, interval = sample_count(), interval_ms()
        # 샘플링 대기 시간만큼 타임아웃 여유를 준다.
        timeout = cim.BATCH_TIMEOUT + count * interval / 1000
        rows, errors = cim.query_batch(build_queries(count, interval), timeout=timeout)

        samples = rows.get("samples", [])
        data: dict[str, Any] = {
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sampling": {"count": len(samples), "interval_ms": interval},
            "cpu": shape_cpu_usage(samples, rows.get("processor", [])),
            "memory": shape_memory_usage(samples),
            "disk": shape_disk_usage(samples),
            "top_processes": shape_top_processes(rows.get("top_processes", [])),
            "power_plan": shape_power_plan(rows.get("power_plan", [])),
            "thermal": shape_thermal(rows.get("thermal", [])),
        }

        # 온도 미지원은 흔한 일이라 partial 사유로 치지 않는다. 샘플이 하나도
        # 없거나 온도 외 조회가 깨진 경우만 신뢰도를 낮춘다.
        blocking = {key: message for key, message in errors.items() if key != "thermal"}
        if blocking or not samples:
            data["_partial"] = True
        if errors:
            data["collect_errors"] = _explain_errors(errors)
        return data


def _explain_errors(errors: dict[str, str]) -> list[str]:
    """수집 실패 사유를 조치 가능한 문장으로 바꾼다.

    온도는 지원하지 않는 메인보드가 많고, 지원하더라도 관리자 권한을 요구한다.
    둘 중 무엇인지는 구분되지 않으므로 양쪽을 함께 안내한다.
    """
    explained = []
    for key, message in errors.items():
        if key == "thermal":
            explained.append(
                "thermal: 온도 센서(MSAcpi_ThermalZoneTemperature)를 읽지 못했습니다. "
                "지원하지 않는 메인보드이거나 관리자 권한이 필요합니다. "
                "온도 결측은 다른 진단에 영향을 주지 않습니다."
            )
        else:
            explained.append("{0}: {1}".format(key, message))
    return explained


# --- 정규화 함수 -------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def stats(samples: list[dict[str, Any]], key: str, digits: int = 1) -> dict[str, Any]:
    """샘플 구간의 평균/최대/최소.

    평균이 높으면 상시 부하, 최대만 높으면 순간 스파이크다. 이 구분이 없으면
    "지금 CPU 90%"라는 단발값으로 부품 교체를 권하는 오진이 나온다.
    """
    values = [value for value in (_to_float(row.get(key)) for row in samples) if value is not None]
    if not values:
        return {"avg": None, "max": None, "min": None, "samples": []}
    return {
        "avg": round(sum(values) / len(values), digits),
        "max": round(max(values), digits),
        "min": round(min(values), digits),
        "samples": [round(value, digits) for value in values],
    }


def shape_cpu_usage(
    samples: list[dict[str, Any]], processors: list[dict[str, Any]]
) -> dict[str, Any]:
    processor = processors[0] if processors else {}
    current = _to_int(processor.get("CurrentClockSpeed"))
    maximum = _to_int(processor.get("MaxClockSpeed"))

    return {
        "usage_percent": stats(samples, "CpuPercent"),
        # 커널 시간 비중이 높으면 드라이버/IO 문제를 의심한다 (M7 상관 분석 입력).
        "privileged_percent": stats(samples, "CpuPrivilegedPercent"),
        "clock": {
            "current_mhz": current,
            "max_mhz": maximum,
            # 부하가 없을 때도 낮은 것은 정상(절전)이므로, 이 비율만으로 판정하지
            # 않고 usage_percent와 함께 봐야 스로틀링을 구분할 수 있다.
            "ratio": round(current / maximum, 2) if current and maximum else None,
        },
    }


def shape_memory_usage(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "available_mb": stats(samples, "AvailableMBytes"),
        "committed_percent": stats(samples, "CommittedPercent"),
        # 페이징이 잦다는 것은 물리 메모리가 모자라 디스크로 밀려나고 있다는 뜻이다.
        "pages_per_sec": stats(samples, "PagesPerSec"),
    }


def shape_disk_usage(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "queue_length": stats(samples, "DiskQueueLength", digits=2),
        "idle_percent": stats(samples, "DiskIdlePercent"),
    }


def shape_top_processes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processes = []
    for row in rows:
        name = _clean(row.get("Name"))
        if not name:
            continue
        working_set = _to_float(row.get("WorkingSetPrivate"))
        processes.append(
            {
                "name": name,
                "cpu_percent": _to_float(row.get("PercentProcessorTime")),
                "memory_mb": round(working_set / (1024 ** 2), 1) if working_set else None,
            }
        )
    return processes


def shape_power_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """``powercfg /getactivescheme`` 출력에서 활성 전원 계획을 읽는다."""
    raw = (_clean((rows[0] if rows else {}).get("Active")) or "").lower()

    scheme = name = None
    for guid, (key, label) in POWER_SCHEME_GUIDS.items():
        if guid in raw:
            scheme, name = key, label
            break

    return {
        "name": name,
        "scheme": scheme,
        # 데스크톱에서 절전 계획이 걸려 있으면 부품이 아니라 설정이 원인이다.
        "is_power_saver": scheme == "power_saver",
    }


def shape_thermal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """ACPI 열 영역 온도. 지원하지 않는 메인보드가 많아 결측이 정상이다."""
    temperatures = []
    for row in rows:
        # CurrentTemperature 단위는 0.1 켈빈이다.
        raw = _to_float(row.get("CurrentTemperature"))
        if raw is None or raw <= 0:
            continue
        celsius = round(raw / 10 - 273.15, 1)
        if -50 <= celsius <= 150:  # 명백한 오보고 제외
            temperatures.append(celsius)

    return {
        "available": bool(temperatures),
        "max_c": max(temperatures) if temperatures else None,
        "zones_c": temperatures,
    }
