"""Hardware Inventory collector (Phase 1 / M1).

WMI(CIM)로 CPU, 메모리, GPU, 저장장치, 메인보드, OS 정보를 수집한다.
모든 조회는 ``cim.query_batch`` 로 한 번에 처리한다 (PowerShell 기동 1회).

개인정보 원칙: 시리얼 번호, MAC 주소, 사용자명 등 재식별 가능한 값은
수집 대상에서 제외한다. 진단에 필요한 것은 "무엇이 달렸는가"이지
"누구의 것인가"가 아니다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..win import cim
from .base import Collector, register

_BYTES_PER_GB = 1024 ** 3

_MEDIA_TYPES = {0: "Unspecified", 3: "HDD", 4: "SSD", 5: "SCM"}
_BUS_TYPES = {7: "USB", 8: "RAID", 11: "SATA", 17: "NVMe"}
_HEALTH = {0: "Healthy", 1: "Warning", 2: "Unhealthy"}

_INTEGRATED_GPU_HINTS = ("uhd graphics", "hd graphics", "iris", "radeon graphics", "vega")

#: 한 번의 PowerShell 실행으로 처리할 CIM 조회 목록.
QUERIES: dict[str, dict[str, Any]] = {
    "system": {
        "class_name": "Win32_ComputerSystem",
        "properties": [
            "Manufacturer",
            "Model",
            "SystemType",
            "TotalPhysicalMemory",
            "NumberOfProcessors",
        ],
    },
    "os": {
        "class_name": "Win32_OperatingSystem",
        "properties": [
            "Caption",
            "Version",
            "BuildNumber",
            "OSArchitecture",
            "InstallDate",
            "LastBootUpTime",
        ],
    },
    "cpu": {
        "class_name": "Win32_Processor",
        "properties": [
            "Name",
            "Manufacturer",
            "NumberOfCores",
            "NumberOfLogicalProcessors",
            "MaxClockSpeed",
            "L3CacheSize",
            "SocketDesignation",
        ],
    },
    "memory": {
        "class_name": "Win32_PhysicalMemory",
        "properties": [
            "Capacity",
            "Speed",
            "ConfiguredClockSpeed",
            "Manufacturer",
            "PartNumber",
            "DeviceLocator",
        ],
    },
    "gpu": {
        "class_name": "Win32_VideoController",
        "properties": [
            "Name",
            "AdapterRAM",
            "DriverVersion",
            "DriverDate",
            "VideoProcessor",
            "CurrentHorizontalResolution",
            "CurrentVerticalResolution",
            "CurrentRefreshRate",
        ],
    },
    "nvidia_gpu_memory": {
        "script": "$cmd = Get-Command nvidia-smi -ErrorAction SilentlyContinue; if ($cmd) { & $cmd.Source --query-gpu=name,memory.total --format=csv,noheader,nounits | ForEach-Object { $parts = $_ -split ',\\s*'; [pscustomobject]@{ Name = $parts[0]; MemoryTotalMiB = [int]$parts[1] } } }",
    },
    "disk_drive": {
        "class_name": "Win32_DiskDrive",
        "properties": ["Model", "InterfaceType", "Size", "Partitions", "Index"],
    },
    # MediaType(SSD/HDD)과 BusType(NVMe/SATA)은 storage 네임스페이스에만 있다.
    # 구버전 Windows에는 없을 수 있으나, 배치 조회라 실패해도 나머지는 살아남는다.
    "physical_disk": {
        "class_name": "MSFT_PhysicalDisk",
        "namespace": "root/microsoft/windows/storage",
        "properties": ["DeviceId", "MediaType", "BusType", "HealthStatus"],
    },
    "baseboard": {
        "class_name": "Win32_BaseBoard",
        "properties": ["Manufacturer", "Product", "Version"],
    },
    "bios": {
        "class_name": "Win32_BIOS",
        "properties": ["Manufacturer", "SMBIOSBIOSVersion", "ReleaseDate"],
    },
}


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bytes_to_gb(value: Any, digits: int = 2) -> float | None:
    number = _to_int(value)
    if number is None:
        return None
    return round(number / _BYTES_PER_GB, digits)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _cim_date(value: Any) -> str | None:
    """CIM DateTime을 ISO 문자열로 정규화.

    PowerShell의 ConvertTo-Json은 날짜를 ``/Date(1712345678000)/`` 형태로 낸다.
    """
    if not value:
        return None
    text = str(value)
    if text.startswith("/Date("):
        digits = text[6:].split(")")[0]
        for separator in ("+", "-"):
            digits = digits.split(separator)[0]
        milliseconds = _to_int(digits)
        if milliseconds is not None:
            moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
            return moment.isoformat(timespec="seconds")
    return text


def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


@register
class HardwareCollector(Collector):
    name = "hardware"
    milestone = "M1"
    description = "WMI/CIM 기반 하드웨어 인벤토리"

    def collect(self) -> dict[str, Any]:
        rows, errors = cim.query_batch(QUERIES)

        data: dict[str, Any] = {
            "system": shape_system(_first(rows.get("system", []))),
            "os": shape_os(_first(rows.get("os", []))),
            "cpu": shape_cpu(rows.get("cpu", [])),
            "memory": shape_memory(rows.get("memory", [])),
            "gpu": shape_gpu(rows.get("gpu", []), rows.get("nvidia_gpu_memory", [])),
            "storage": shape_storage(rows.get("disk_drive", []), rows.get("physical_disk", [])),
            "motherboard": shape_motherboard(
                _first(rows.get("baseboard", [])), _first(rows.get("bios", []))
            ),
        }

        if errors:
            # base.Collector.run()이 이 플래그를 보고 status를 partial로 낮춘다.
            data["_partial"] = True
            data["collect_errors"] = ["{0}: {1}".format(key, msg) for key, msg in errors.items()]
        return data


# --- 정규화 함수 (CIM 행 -> 계약 형식) --------------------------------------
# 순수 함수로 분리해 CIM 없이도 단위 테스트할 수 있게 한다.


def shape_system(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "manufacturer": _clean(row.get("Manufacturer")),
        "model": _clean(row.get("Model")),
        "system_type": _clean(row.get("SystemType")),
        "total_memory_gb": _bytes_to_gb(row.get("TotalPhysicalMemory")),
        "cpu_socket_count": _to_int(row.get("NumberOfProcessors")),
    }


def shape_os(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "caption": _clean(row.get("Caption")),
        "version": _clean(row.get("Version")),
        "build": _clean(row.get("BuildNumber")),
        "architecture": _clean(row.get("OSArchitecture")),
        # 설치일은 PC 노후도 추정(What-if Scan)의 기준점이 된다.
        "installed_at": _cim_date(row.get("InstallDate")),
        "last_boot_at": _cim_date(row.get("LastBootUpTime")),
    }


def shape_cpu(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": _clean(row.get("Name")),
            "manufacturer": _clean(row.get("Manufacturer")),
            "cores": _to_int(row.get("NumberOfCores")),
            "threads": _to_int(row.get("NumberOfLogicalProcessors")),
            "max_clock_mhz": _to_int(row.get("MaxClockSpeed")),
            "l3_cache_kb": _to_int(row.get("L3CacheSize")),
            "socket": _clean(row.get("SocketDesignation")),
        }
        for row in rows
    ]


def shape_memory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    modules = [
        {
            "capacity_gb": _bytes_to_gb(row.get("Capacity")),
            "rated_speed_mhz": _to_int(row.get("Speed")),
            # 동작 클럭이 정격보다 낮으면 XMP/EXPO 미적용 -> 진단 규칙 입력
            "configured_speed_mhz": _to_int(row.get("ConfiguredClockSpeed")),
            "manufacturer": _clean(row.get("Manufacturer")),
            "part_number": _clean(row.get("PartNumber")),
            "slot": _clean(row.get("DeviceLocator")),
        }
        for row in rows
    ]
    total = sum(module["capacity_gb"] or 0 for module in modules)
    return {
        "modules": modules,
        "module_count": len(modules),
        "total_gb": round(total, 2) if modules else None,
    }


def _wmi_vram_gb(value: Any) -> float | None:
    """Return AdapterRAM only while its 32-bit value is unambiguous."""
    size_gb = _bytes_to_gb(value)
    return None if size_gb is not None and size_gb >= 3.9 else size_gb


def shape_gpu(
    rows: list[dict[str, Any]], nvidia_memory_rows: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    nvidia_memory = {
        (_clean(row.get("Name")) or "").casefold(): _to_int(row.get("MemoryTotalMiB"))
        for row in nvidia_memory_rows or []
    }
    result = []
    for row in rows:
        width = _to_int(row.get("CurrentHorizontalResolution"))
        height = _to_int(row.get("CurrentVerticalResolution"))
        name = _clean(row.get("Name"))
        memory_mib = nvidia_memory.get((name or "").casefold())
        vram_gb = round(memory_mib / 1024, 2) if memory_mib is not None else _wmi_vram_gb(row.get("AdapterRAM"))
        result.append(
            {
                "name": name,
                # AdapterRAM은 32bit 필드다. NVIDIA는 nvidia-smi로 보강하고,
                # 경계값은 실제 용량으로 오인하지 않도록 결측 처리한다.
                "adapter_ram_gb": vram_gb,
                "driver_version": _clean(row.get("DriverVersion")),
                "driver_date": _cim_date(row.get("DriverDate")),
                "video_processor": _clean(row.get("VideoProcessor")),
                "resolution": "{0}x{1}".format(width, height) if width and height else None,
                "refresh_hz": _to_int(row.get("CurrentRefreshRate")),
                "integrated": is_integrated_gpu(name),
            }
        )
    return result


def is_integrated_gpu(name: str | None) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in _INTEGRATED_GPU_HINTS)


def shape_storage(
    drives: list[dict[str, Any]], physical: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    physical_by_index = {_to_int(row.get("DeviceId")): row for row in physical}

    result = []
    for drive in drives:
        extra = physical_by_index.get(_to_int(drive.get("Index")), {})
        result.append(
            {
                "model": _clean(drive.get("Model")),
                "interface": _clean(drive.get("InterfaceType")),
                "size_gb": _bytes_to_gb(drive.get("Size")),
                "partitions": _to_int(drive.get("Partitions")),
                "media_type": _MEDIA_TYPES.get(_to_int(extra.get("MediaType"))),
                "bus_type": _BUS_TYPES.get(_to_int(extra.get("BusType"))),
                "health": _HEALTH.get(_to_int(extra.get("HealthStatus"))),
            }
        )
    return result


def shape_motherboard(board: dict[str, Any], bios: dict[str, Any]) -> dict[str, Any]:
    return {
        "manufacturer": _clean(board.get("Manufacturer")),
        "product": _clean(board.get("Product")),
        "version": _clean(board.get("Version")),
        "bios": {
            "manufacturer": _clean(bios.get("Manufacturer")),
            "version": _clean(bios.get("SMBIOSBIOSVersion")),
            # BIOS가 수년째 그대로면 안정성/보안 진단 규칙의 입력이 된다.
            "released_at": _cim_date(bios.get("ReleaseDate")),
        },
    }
