"""Storage Health collector (Phase 2 / M2).

하드웨어 인벤토리(``hardware`` collector)가 "무엇이 달렸는가"를 본다면
이 collector는 "얼마나 닳았는가"를 본다.

데이터 소스

- SMART 속성
  ``MSStorageDriver_FailurePredictStatus`` / ``...PredictData`` (root/wmi)
  재할당 섹터(05), 대기 섹터(C5), 통전 시간(09), 쓰기 총량(F1/F2)
- NVMe/SSD 수명
  ``Get-PhysicalDisk | Get-StorageReliabilityCounter`` (Wear, Temperature)
- 볼륨 여유 공간
  ``Win32_LogicalDisk`` (DriveType=3, FreeSpace, Size)

설계 노트: 시스템 드라이브 여유 공간 부족은 체감 성능 저하의 가장 흔한
원인이면서 "구매하지 않아도 되는" 대표 사례다. No-Purchase Scenario의
핵심 근거가 되므로 우선 구현한다.

SMART은 USB 외장 디스크와 일부 NVMe 컨트롤러에서 조회되지 않는다. 그런
디스크는 ``smart_supported: false`` 로 남기고 나머지 디스크는 정상 수집한다.
전체 실패가 아니라 ``partial`` 로 떨어져야 한다는 것이 이 collector의 규약이다.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ..win import cim
from .base import Collector, register

_BYTES_PER_GB = 1024 ** 3
#: SMART VendorSpecific 블록은 2바이트 헤더 뒤에 12바이트 속성이 최대 30개 이어진다.
_SMART_HEADER_BYTES = 2
_SMART_ENTRY_BYTES = 12
_SMART_MAX_ENTRIES = 30

#: 진단 규칙이 쓰는 SMART 속성만 이름을 붙여 남긴다. 나머지는 버린다.
SMART_ATTRIBUTES: dict[int, str] = {
    5: "reallocated_sectors",  # 0x05 재할당된 섹터 - 물리 손상의 직접 증거
    9: "power_on_hours",  # 0x09 통전 시간
    187: "reported_uncorrectable",  # 0xBB 정정 불가 오류 보고 수
    196: "reallocation_events",  # 0xC4 재할당 시도 횟수
    197: "pending_sectors",  # 0xC5 대기 중인 불안정 섹터 - 재할당 직전 상태
    198: "offline_uncorrectable",  # 0xC6 오프라인 검사에서 정정 불가
    231: "ssd_life_left",  # 0xE7 SSD 잔여 수명 (정규화 값 = %)
    233: "media_wearout",  # 0xE9 미디어 마모도
    241: "host_writes_lba",  # 0xF1 호스트가 쓴 총 LBA
    242: "host_reads_lba",  # 0xF2 호스트가 읽은 총 LBA
}

#: 대부분의 SATA/NVMe 디스크가 보고하는 LBA 크기. 총 쓰기량 환산에만 쓴다.
_LBA_BYTES = 512

#: ``Get-StorageReliabilityCounter`` 는 물리 디스크마다 따로 물어야 해서 파이프라인이
#: 필요하다. CIM 단일 조회로 표현할 수 없으므로 script 통로를 쓴다.
_RELIABILITY_SCRIPT = (
    "Get-PhysicalDisk | ForEach-Object { "
    "$counter = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
    "if ($counter) { [pscustomobject]@{ DeviceId = $_.DeviceId; Wear = $counter.Wear; "
    "Temperature = $counter.Temperature; PowerOnHours = $counter.PowerOnHours; "
    "ReadErrorsTotal = $counter.ReadErrorsTotal; WriteErrorsTotal = $counter.WriteErrorsTotal } } }"
)

#: OS가 설치된 볼륨이 어느 물리 디스크에 있는지. 여러 디스크가 달린 PC에서
#: "시스템 드라이브가 HDD인가"를 판정하려면 이 연결이 반드시 필요하다.
#: Win32_DiskDrive의 Index 0을 시스템 디스크로 가정하면 데이터용 HDD가
#: 0번인 흔한 구성에서 그대로 오진이 된다.
_SYSTEM_PARTITION_SCRIPT = (
    "$partition = Get-Partition -DriveLetter {0} -ErrorAction SilentlyContinue; "
    "[pscustomobject]@{{ DiskNumber = $partition.DiskNumber }}"
)


def _queries(system: str) -> dict[str, dict[str, Any]]:
    queries = dict(QUERIES)
    queries["system_partition"] = {
        "script": _SYSTEM_PARTITION_SCRIPT.format(system.rstrip(":")[:1] or "C")
    }
    return queries


QUERIES: dict[str, dict[str, Any]] = {
    # DriveType=3 = 고정 디스크. 네트워크 드라이브와 이동식 매체는 진단 대상이 아니다.
    "volume": {
        "class_name": "Win32_LogicalDisk",
        "where": "DriveType=3",
        "properties": ["DeviceID", "FileSystem", "Size", "FreeSpace"],
    },
    # PNPDeviceID는 SMART InstanceName과 잇는 조인 키로만 쓰고 스냅샷에는 남기지 않는다.
    "drive": {
        "class_name": "Win32_DiskDrive",
        "properties": ["Index", "Model", "Size", "PNPDeviceID"],
    },
    "smart_status": {
        "class_name": "MSStorageDriver_FailurePredictStatus",
        "namespace": "root/wmi",
        "properties": ["InstanceName", "PredictFailure", "Reason"],
    },
    "smart_data": {
        "class_name": "MSStorageDriver_FailurePredictData",
        "namespace": "root/wmi",
        "properties": ["InstanceName", "VendorSpecific"],
    },
    "reliability": {"script": _RELIABILITY_SCRIPT},
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


def system_drive() -> str:
    """OS가 설치된 드라이브 문자. 여유 공간 규칙의 판정 대상이다."""
    return (os.environ.get("SystemDrive") or "C:").upper()


@register
class StorageHealthCollector(Collector):
    name = "storage_health"
    milestone = "M2"
    description = "SMART / 수명 / 볼륨 여유 공간"

    def collect(self) -> dict[str, Any]:
        drive = system_drive()
        rows, errors = cim.query_batch(_queries(drive))

        system_index = _system_disk_index(rows.get("system_partition", []))
        disks = shape_disks(
            rows.get("drive", []),
            rows.get("smart_status", []),
            rows.get("smart_data", []),
            rows.get("reliability", []),
            system_index=system_index,
        )

        data: dict[str, Any] = {
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "system_drive": drive,
            "system_disk_index": system_index,
            "volumes": shape_volumes(rows.get("volume", []), drive),
            "disks": disks,
        }

        # SMART 미지원은 환경의 한계이지 수집 실패가 아니다. 다만 진단 신뢰도에는
        # 영향이 있으므로 partial로 낮춰 "못 본 것"을 명시한다.
        if errors or any(not disk["smart_supported"] for disk in disks):
            data["_partial"] = True
        if errors:
            data["collect_errors"] = _explain_errors(errors)
        return data


def _explain_errors(errors: dict[str, str]) -> list[str]:
    """수집 실패 사유를 조치 가능한 문장으로 바꾼다.

    SMART 조회는 관리자 권한이 없으면 "액세스가 거부되었습니다"로 막힌다.
    원문 오류는 로케일마다 다르고 사용자가 무엇을 해야 하는지 알려주지 않으므로,
    권한 상태를 직접 확인해 사유를 다시 쓴다.
    """
    elevated = cim.is_elevated()
    explained = []
    for key, message in errors.items():
        if key.startswith("smart") and not elevated:
            explained.append(
                "{0}: SMART 조회에는 관리자 권한이 필요합니다. "
                "관리자 권한으로 다시 실행하면 수명/불량 섹터를 함께 진단합니다.".format(key)
            )
        else:
            explained.append("{0}: {1}".format(key, message))
    return explained


# --- 정규화 함수 (CIM 행 -> 계약 형식) --------------------------------------
# 순수 함수로 분리해 CIM 없이도 단위 테스트할 수 있게 한다.


def shape_volumes(rows: list[dict[str, Any]], system: str | None = None) -> list[dict[str, Any]]:
    """고정 볼륨별 용량과 여유 공간."""
    system = (system or "C:").upper()

    volumes = []
    for row in rows:
        drive = (_clean(row.get("DeviceID")) or "").upper()
        size_gb = _bytes_to_gb(row.get("Size"))
        free_gb = _bytes_to_gb(row.get("FreeSpace"))
        volumes.append(
            {
                "drive": drive or None,
                "file_system": _clean(row.get("FileSystem")),
                "size_gb": size_gb,
                "free_gb": free_gb,
                "free_percent": _percent(free_gb, size_gb),
                "is_system": bool(drive) and drive == system,
            }
        )
    return volumes


def _percent(part: float | None, whole: float | None) -> float | None:
    if part is None or not whole:
        return None
    return round(part / whole * 100, 1)


def parse_smart_attributes(vendor_specific: Any) -> dict[str, dict[str, int]]:
    """SMART VendorSpecific 블록에서 관심 속성만 뽑는다.

    블록 구조: 2바이트 헤더 + (12바이트 x 최대 30) 속성. 각 속성은
    ``[0] ID | [1..2] 플래그 | [3] 현재 정규화 값 | [4] 최악값 | [5..10] raw(LE) | [11] 예약``.

    정규화 값(0~253)과 raw 값을 둘 다 남긴다. 재할당 섹터처럼 절대 개수가
    의미 있는 속성은 raw를, SSD 잔여 수명처럼 백분율인 속성은 정규화 값을
    규칙이 쓰기 때문이다.
    """
    if not isinstance(vendor_specific, (list, tuple)):
        return {}

    payload = [byte for byte in (_to_int(item) for item in vendor_specific) if byte is not None]
    if len(payload) < _SMART_HEADER_BYTES + _SMART_ENTRY_BYTES:
        return {}

    attributes: dict[str, dict[str, int]] = {}
    for index in range(_SMART_MAX_ENTRIES):
        start = _SMART_HEADER_BYTES + index * _SMART_ENTRY_BYTES
        entry = payload[start : start + _SMART_ENTRY_BYTES]
        if len(entry) < _SMART_ENTRY_BYTES:
            break

        attribute_id = entry[0]
        if attribute_id == 0:  # ID 0 = 미사용 슬롯
            continue
        name = SMART_ATTRIBUTES.get(attribute_id)
        if name is None:
            continue

        raw = 0
        for offset, byte in enumerate(entry[5:11]):  # 6바이트 little-endian
            raw |= byte << (8 * offset)
        attributes[name] = {"id": attribute_id, "value": entry[3], "worst": entry[4], "raw": raw}

    return attributes


def _instance_key(value: Any) -> str | None:
    """SMART InstanceName과 PNPDeviceID를 같은 형태로 맞춘다.

    InstanceName은 PNPDeviceID 뒤에 ``_0`` 이 붙은 형태이며 대소문자가 다르다.
    이 값은 조인 키로만 쓰고 스냅샷에는 남기지 않는다 (재식별 가능성 차단).
    """
    text = _clean(value)
    if text is None:
        return None
    key = text.upper()
    if key.endswith("_0"):
        key = key[:-2]
    return key


def _index_by_instance(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _instance_key(row.get("InstanceName"))
        if key is not None:
            indexed[key] = row
    return indexed


def _system_disk_index(rows: list[dict[str, Any]]) -> int | None:
    """OS 볼륨이 올라간 물리 디스크 번호. 확인하지 못하면 None."""
    return _to_int((rows[0] if rows else {}).get("DiskNumber"))


def shape_disks(
    drives: list[dict[str, Any]],
    smart_status: list[dict[str, Any]],
    smart_data: list[dict[str, Any]],
    reliability: list[dict[str, Any]],
    system_index: int | None = None,
) -> list[dict[str, Any]]:
    """물리 디스크별 SMART / 수명 / 실패 예측을 하나로 합친다."""
    status_by_key = _index_by_instance(smart_status)
    data_by_key = _index_by_instance(smart_data)

    counters_by_index: dict[int, dict[str, Any]] = {}
    for row in reliability:
        device_index = _to_int(row.get("DeviceId"))
        if device_index is not None:
            counters_by_index[device_index] = row

    disks = []
    for drive in drives:
        index = _to_int(drive.get("Index"))
        key = _instance_key(drive.get("PNPDeviceID"))
        status = status_by_key.get(key, {}) if key else {}
        raw_data = data_by_key.get(key, {}) if key else {}
        attributes = parse_smart_attributes(raw_data.get("VendorSpecific"))
        counter = counters_by_index.get(index, {}) if index is not None else {}

        disks.append(
            {
                "index": index,
                "model": _clean(drive.get("Model")),
                "size_gb": _bytes_to_gb(drive.get("Size")),
                # 시스템 디스크를 특정하지 못했으면 False가 아니라 None이다.
                # "아니다"와 "모른다"를 섞으면 규칙이 없는 근거로 판정하게 된다.
                "is_system": None if system_index is None else index == system_index,
                "smart_supported": bool(attributes) or bool(status),
                # PredictFailure는 펌웨어 자체의 임박 실패 판정이다. 가장 강한 신호.
                "predict_failure": _predict_failure(status),
                "predict_failure_reason": _to_int(status.get("Reason")),
                "smart": attributes,
                "reallocated_sectors": _raw(attributes, "reallocated_sectors"),
                "pending_sectors": _raw(attributes, "pending_sectors"),
                "uncorrectable_sectors": _raw(attributes, "offline_uncorrectable"),
                "power_on_hours": _power_on_hours(attributes, counter),
                "host_writes_tb": _lba_to_tb(_raw(attributes, "host_writes_lba")),
                "wear_percent": _wear_percent(attributes, counter),
                "temperature_c": _to_int(counter.get("Temperature")),
                "read_errors_total": _to_int(counter.get("ReadErrorsTotal")),
                "write_errors_total": _to_int(counter.get("WriteErrorsTotal")),
            }
        )
    return disks


def _predict_failure(status: dict[str, Any]) -> bool | None:
    value = status.get("PredictFailure")
    if value is None:
        return None
    return bool(value)


def _raw(attributes: dict[str, dict[str, int]], name: str) -> int | None:
    entry = attributes.get(name)
    return entry["raw"] if entry else None


def _lba_to_tb(lba: int | None) -> float | None:
    if lba is None:
        return None
    return round(lba * _LBA_BYTES / (1024 ** 4), 2)


def _power_on_hours(attributes: dict[str, dict[str, int]], counter: dict[str, Any]) -> int | None:
    """SMART 우선. NVMe는 SMART 대신 신뢰성 카운터에만 값이 있는 경우가 많다."""
    hours = _raw(attributes, "power_on_hours")
    if hours is not None:
        return hours
    return _to_int(counter.get("PowerOnHours"))


def _wear_percent(attributes: dict[str, dict[str, int]], counter: dict[str, Any]) -> int | None:
    """수명 소모율(%). 0이면 새 디스크, 100이면 보증 수명 소진."""
    wear = _to_int(counter.get("Wear"))
    if wear is not None:
        return wear

    # SSD Life Left / Media Wearout은 "남은 비율"이므로 뒤집어 소모율로 맞춘다.
    for name in ("ssd_life_left", "media_wearout"):
        entry = attributes.get(name)
        if entry and 0 <= entry["value"] <= 100:
            return 100 - entry["value"]
    return None
