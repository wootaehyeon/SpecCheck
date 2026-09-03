"""Agent 기초 동작 테스트.

CIM(Windows)에 의존하지 않는 순수 로직만 검증한다. 수집 자체가 아니라
"수집 결과가 계약 형식을 지키는가"가 검증 대상이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from speccheck_agent.collectors import registry
from speccheck_agent.collectors.base import Collector, CollectorResult
from speccheck_agent.collectors.hardware import (
    is_integrated_gpu,
    shape_cpu,
    shape_gpu,
    shape_memory,
    shape_storage,
)
from speccheck_agent.pipeline import SnapshotStore, to_spec_profile
from speccheck_agent.snapshot import SCHEMA_VERSION, build_snapshot

CONTRACT = (
    Path(__file__).resolve().parents[2] / "shared" / "contracts" / "telemetry_snapshot.schema.json"
)


# --- 계약 --------------------------------------------------------------------


def test_schema_version_matches_contract():
    """SCHEMA_VERSION과 계약 파일의 $id가 어긋나면 Backend가 스냅샷을 거절한다."""
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert SCHEMA_VERSION in schema["$id"]


def test_snapshot_has_required_fields():
    snapshot = build_snapshot([], scan_mode="actual")
    for field in ("schema_version", "snapshot_id", "collected_at", "scan_mode", "agent", "sections"):
        assert field in snapshot
    assert snapshot["agent"]["version"]


def test_snapshot_sections_keyed_by_collector_name():
    results = [
        CollectorResult(name="hardware", status="ok", milestone="M1", data={"cpu": []}),
        CollectorResult(name="security", status="planned", milestone="M6"),
    ]
    sections = build_snapshot(results)["sections"]
    assert sections["hardware"]["status"] == "ok"
    assert sections["security"]["status"] == "planned"


# --- Collector 레지스트리 ----------------------------------------------------


def test_every_collector_is_registered_under_its_own_name():
    for name, cls in registry().items():
        assert cls.name == name
        assert cls.milestone.startswith("M")


def test_unimplemented_collector_reports_planned_without_running():
    class Stub(Collector):
        name = "stub"
        milestone = "M9"
        implemented = False

        def collect(self):
            raise AssertionError("실행되면 안 된다")

    result = Stub().run()
    assert result.status == "planned"


def test_collector_error_is_contained_in_its_own_section():
    """collector 하나가 죽어도 스캔 전체는 계속돼야 한다."""

    class Boom(Collector):
        name = "boom"
        requires_windows = False

        def collect(self):
            raise RuntimeError("장치 없음")

    result = Boom().run()
    assert result.status == "error"
    assert "장치 없음" in result.error


def test_partial_flag_downgrades_status():
    class Partial(Collector):
        name = "partial"
        requires_windows = False

        def collect(self):
            return {"cpu": [], "_partial": True}

    result = Partial().run()
    assert result.status == "partial"
    assert "_partial" not in result.data


# --- 정규화 ------------------------------------------------------------------


def test_shape_memory_sums_module_capacity():
    rows = [
        {"Capacity": str(8 * 1024 ** 3), "Speed": 3200, "ConfiguredClockSpeed": 2400},
        {"Capacity": str(8 * 1024 ** 3), "Speed": 3200, "ConfiguredClockSpeed": 2400},
    ]
    memory = shape_memory(rows)
    assert memory["total_gb"] == 16.0
    assert memory["module_count"] == 2
    # 정격 3200인데 2400으로 동작 -> XMP 미적용 진단 규칙의 입력
    assert memory["modules"][0]["configured_speed_mhz"] < memory["modules"][0]["rated_speed_mhz"]


def test_shape_cpu_trims_vendor_padding():
    rows = [{"Name": "  Intel(R) Core(TM) i7-13700K  ", "NumberOfCores": "16"}]
    cpu = shape_cpu(rows)[0]
    assert cpu["name"] == "Intel(R) Core(TM) i7-13700K"
    assert cpu["cores"] == 16


def test_shape_gpu_prefers_nvidia_smi_memory_over_limited_wmi_value():
    rows = [{"Name": "NVIDIA GeForce RTX 5080", "AdapterRAM": 4 * 1024 ** 3 - 1}]
    vendor_rows = [{"Name": "NVIDIA GeForce RTX 5080", "MemoryTotalMiB": 16303}]

    gpu = shape_gpu(rows, vendor_rows)[0]

    assert gpu["adapter_ram_gb"] == 15.92


def test_shape_gpu_does_not_report_ambiguous_wmi_4gb_boundary():
    rows = [{"Name": "AMD Radeon RX 7800 XT", "AdapterRAM": 4 * 1024 ** 3 - 1}]

    gpu = shape_gpu(rows)[0]

    assert gpu["adapter_ram_gb"] is None


def test_shape_storage_joins_media_type_by_disk_index():
    drives = [{"Model": "Samsung SSD", "Size": str(512 * 1024 ** 3), "Index": 0}]
    physical = [{"DeviceId": "0", "MediaType": 4, "BusType": 17, "HealthStatus": 0}]
    disk = shape_storage(drives, physical)[0]
    assert disk["media_type"] == "SSD"
    assert disk["bus_type"] == "NVMe"
    assert disk["health"] == "Healthy"


def test_shape_storage_survives_missing_physical_disk_namespace():
    drives = [{"Model": "WDC HDD", "Size": str(1024 ** 4), "Index": 0}]
    disk = shape_storage(drives, [])[0]
    assert disk["model"] == "WDC HDD"
    assert disk["media_type"] is None


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Intel(R) Iris(R) Xe Graphics", True),
        ("Intel(R) UHD Graphics 770", True),
        ("NVIDIA GeForce RTX 4070", False),
        ("AMD Radeon RX 7800 XT", False),
        (None, False),
    ],
)
def test_integrated_gpu_detection(name, expected):
    assert is_integrated_gpu(name) is expected


def test_spec_profile_prefers_discrete_gpu():
    snapshot = build_snapshot(
        [
            CollectorResult(
                name="hardware",
                status="ok",
                data={
                    "cpu": [{"name": "i7-13700K", "cores": 16}],
                    "gpu": [
                        {"name": "Intel UHD Graphics", "integrated": True},
                        {"name": "NVIDIA GeForce RTX 4070", "integrated": False},
                    ],
                    "memory": {"total_gb": 32.0, "module_count": 2, "modules": []},
                    "storage": [],
                    "motherboard": {},
                },
            )
        ]
    )
    profile = to_spec_profile(snapshot)
    assert profile["gpu"]["name"] == "NVIDIA GeForce RTX 4070"
    assert profile["cpu"]["name"] == "i7-13700K"


def test_spec_profile_ignores_failed_section():
    """실패한 섹션의 데이터는 견적 입력으로 새어나가면 안 된다."""
    snapshot = build_snapshot(
        [CollectorResult(name="hardware", status="error", error="CIM 실패", data={"cpu": [{"name": "X"}]})]
    )
    assert to_spec_profile(snapshot)["cpu"]["name"] is None


# --- 저장소 ------------------------------------------------------------------


def test_store_roundtrip(tmp_path: Path):
    snapshot = build_snapshot([CollectorResult(name="hardware", status="ok", data={"cpu": []})])
    with SnapshotStore(tmp_path / "agent.db") as store:
        store.save(snapshot)
        assert store.latest()["snapshot_id"] == snapshot["snapshot_id"]
        # 짧은 prefix로도 조회할 수 있어야 CLI에서 쓸 만하다
        assert store.get(snapshot["snapshot_id"][:8]) is not None

        rows = store.list_recent()
        assert len(rows) == 1 and rows[0]["uploaded_at"] is None

        store.mark_uploaded(snapshot["snapshot_id"])
        assert store.list_recent()[0]["uploaded_at"] is not None
