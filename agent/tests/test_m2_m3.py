"""M2 collector / M3 저장·정규화 테스트.

CIM(Windows)에 의존하지 않는다. collector가 CIM에서 받은 **행(dict)을 어떻게
계약 형식으로 바꾸는가**만 검증하므로 어느 환경에서도 돈다. PowerShell 호출
자체는 실기기 검증(roadmap의 '실측 1회')이 담당한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from speccheck_agent.collectors import performance as perf
from speccheck_agent.collectors import reliability as rel
from speccheck_agent.collectors import storage_health as sh
from speccheck_agent.collectors.base import CollectorResult
from speccheck_agent.pipeline import (
    DB_SCHEMA_VERSION,
    SnapshotStore,
    section_summaries,
    to_health_profile,
    to_spec_profile,
)
from speccheck_agent.snapshot import build_snapshot
from speccheck_agent.win import cim

GB = 1024 ** 3


# --- CIM 배치 확장 ------------------------------------------------------------


def test_batch_accepts_raw_script_for_non_cim_sources():
    """Get-WinEvent나 샘플링 루프도 같은 PowerShell 기동 안에서 처리한다."""
    assert cim._spec_to_script({"script": "Get-WinEvent -LogName System"}) == (
        "Get-WinEvent -LogName System"
    )


def test_batch_script_rejects_newlines():
    """배치는 문장을 ';' 로 이어 한 줄로 만든다. 개행이 섞이면 조용히 깨진다."""
    with pytest.raises(cim.CimError):
        cim._spec_to_script({"script": "line one\nline two"})


# --- storage_health -----------------------------------------------------------


def smart_block(attributes: dict[int, tuple[int, int]]) -> list[int]:
    """SMART VendorSpecific 블록을 합성한다.

    ``{속성ID: (정규화 값, raw 값)}`` -> 2바이트 헤더 + 12바이트 엔트리들.
    """
    payload = [0x10, 0x00]
    for attribute_id, (value, raw) in attributes.items():
        entry = [attribute_id, 0x00, 0x00, value, value]
        entry += [(raw >> (8 * i)) & 0xFF for i in range(6)]  # 6바이트 little-endian
        entry.append(0x00)
        payload += entry
    return payload + [0] * (512 - len(payload))


def test_parse_smart_reads_raw_and_normalized_values():
    block = smart_block({5: (100, 12), 197: (100, 3), 9: (95, 21000)})
    attributes = sh.parse_smart_attributes(block)

    assert attributes["reallocated_sectors"]["raw"] == 12
    assert attributes["pending_sectors"]["raw"] == 3
    assert attributes["power_on_hours"]["raw"] == 21000
    assert attributes["power_on_hours"]["value"] == 95


def test_parse_smart_ignores_unknown_attributes():
    """규칙이 쓰지 않는 속성은 버린다. 스냅샷 크기와 해석 비용을 줄인다."""
    assert sh.parse_smart_attributes(smart_block({0xAA: (100, 5)})) == {}


@pytest.mark.parametrize("value", [None, "", [], [1, 2, 3]])
def test_parse_smart_survives_malformed_block(value):
    assert sh.parse_smart_attributes(value) == {}


def test_volume_marks_system_drive():
    rows = [
        {"DeviceID": "C:", "FileSystem": "NTFS", "Size": str(500 * GB), "FreeSpace": str(50 * GB)},
        {"DeviceID": "D:", "FileSystem": "NTFS", "Size": str(1000 * GB), "FreeSpace": str(900 * GB)},
    ]
    volumes = sh.shape_volumes(rows, system="C:")

    assert volumes[0]["is_system"] is True
    assert volumes[0]["free_percent"] == 10.0
    assert volumes[1]["is_system"] is False


def test_disk_joins_smart_by_device_path():
    """SMART InstanceName은 PNPDeviceID 뒤에 '_0'이 붙고 대소문자가 다르다."""
    drives = [
        {
            "Index": 0,
            "Model": "Samsung SSD 970",
            "Size": str(500 * GB),
            "PNPDeviceID": r"SCSI\DISK&VEN_NVME&PROD_SAMSUNG\4&2B6A&0&000000",
        }
    ]
    status = [
        {"InstanceName": r"SCSI\Disk&Ven_NVMe&Prod_Samsung\4&2b6a&0&000000_0",
         "PredictFailure": False, "Reason": 0}
    ]
    data = [
        {"InstanceName": r"SCSI\Disk&Ven_NVMe&Prod_Samsung\4&2b6a&0&000000_0",
         "VendorSpecific": smart_block({5: (100, 4), 197: (100, 0)})}
    ]

    disk = sh.shape_disks(drives, status, data, [])[0]
    assert disk["smart_supported"] is True
    assert disk["reallocated_sectors"] == 4
    assert disk["predict_failure"] is False


def test_disk_without_smart_is_marked_unsupported():
    """USB 외장이나 권한 부족으로 SMART이 없어도 디스크 자체는 남는다."""
    drives = [{"Index": 0, "Model": "Generic USB", "Size": str(64 * GB), "PNPDeviceID": "USB\\X"}]
    disk = sh.shape_disks(drives, [], [], [])[0]

    assert disk["smart_supported"] is False
    # 결측을 0으로 채우면 "불량 섹터 0개 = 정상"이라는 잘못된 판정이 만들어진다
    assert disk["reallocated_sectors"] is None
    assert disk["wear_percent"] is None


def test_system_disk_is_marked_by_partition_lookup():
    """OS가 어느 물리 디스크에 있는지 알아야 '시스템 드라이브가 HDD' 판정이 성립한다."""
    drives = [
        {"Index": 0, "Model": "ST2000DM008", "Size": str(2000 * GB), "PNPDeviceID": "A"},
        {"Index": 1, "Model": "Samsung SSD 990", "Size": str(500 * GB), "PNPDeviceID": "B"},
    ]
    disks = sh.shape_disks(drives, [], [], [], system_index=1)

    assert disks[0]["is_system"] is False
    assert disks[1]["is_system"] is True


def test_unknown_system_disk_is_none_not_false():
    """'아니다'와 '모른다'를 섞으면 규칙이 없는 근거로 판정하게 된다."""
    drives = [{"Index": 0, "Model": "X", "Size": str(500 * GB), "PNPDeviceID": "A"}]
    assert sh.shape_disks(drives, [], [], [], system_index=None)[0]["is_system"] is None


def test_system_partition_script_uses_the_actual_system_drive():
    assert "-DriveLetter D" in sh._queries("D:")["system_partition"]["script"]


def test_wear_prefers_reliability_counter_over_smart():
    drives = [{"Index": 0, "Model": "NVMe", "Size": str(500 * GB), "PNPDeviceID": "X"}]
    counters = [{"DeviceId": "0", "Wear": 12, "Temperature": 41, "PowerOnHours": 900}]

    disk = sh.shape_disks(drives, [], [], counters)[0]
    assert disk["wear_percent"] == 12
    assert disk["temperature_c"] == 41
    assert disk["power_on_hours"] == 900


def test_wear_falls_back_to_ssd_life_left_attribute():
    """SSD Life Left(0xE7)는 '남은 비율'이므로 뒤집어 소모율로 맞춘다."""
    drives = [{"Index": 0, "Model": "SATA SSD", "Size": str(500 * GB), "PNPDeviceID": "X"}]
    data = [{"InstanceName": "X_0", "VendorSpecific": smart_block({231: (18, 0)})}]

    assert sh.shape_disks(drives, [], data, [])[0]["wear_percent"] == 82


def test_smart_access_denied_becomes_actionable_message(monkeypatch):
    """로케일마다 다른 원문 대신 사용자가 할 수 있는 일을 알려준다."""
    monkeypatch.setattr(cim, "is_elevated", lambda: False)
    messages = sh._explain_errors({"smart_status": "Access is denied. "})

    assert "관리자 권한" in messages[0]
    assert "Access is denied" not in messages[0]


# --- reliability --------------------------------------------------------------


def event_group(provider: str, event_id: int, count: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "Provider": provider,
        "EventId": event_id,
        "Count": count,
        "FirstAt": (now - timedelta(days=5)).isoformat(),
        "LastAt": now.isoformat(),
    }


def test_events_are_aggregated_by_category():
    groups = [
        event_group("Microsoft-Windows-WHEA-Logger", 17, 4),
        event_group("Microsoft-Windows-WHEA-Logger", 19, 3),
        event_group("Microsoft-Windows-WHEA-Logger", 18, 1),
        event_group("Microsoft-Windows-Kernel-Power", 41, 2),
        event_group("disk", 153, 6),
    ]
    data = rel.shape_reliability(groups, days=30)

    # 17과 19는 둘 다 '정정된 오류'라 같은 분류로 합쳐진다
    assert data["totals"]["whea_corrected"] == 7
    assert data["totals"]["whea_fatal"] == 1
    assert data["totals"]["unexpected_shutdown"] == 2
    assert data["totals"]["disk_error"] == 6


def test_all_categories_are_present_even_when_zero():
    """규칙이 '값 없음'과 '0건'을 구분할 필요가 없어야 한다."""
    totals = rel.shape_reliability([], days=30)["totals"]
    assert set(totals) == set(rel.CATEGORIES)
    assert all(count == 0 for count in totals.values())


def test_unknown_provider_is_counted_but_not_classified():
    data = rel.shape_reliability([event_group("Some-Other-Provider", 7, 3)], days=30)
    assert data["unmatched_events"] == 3
    assert data["events"] == []
    assert data["totals"]["disk_error"] == 0


def test_events_carry_human_readable_label():
    data = rel.shape_reliability([event_group("Microsoft-Windows-WHEA-Logger", 18, 1)], days=30)
    assert data["events"][0]["label"] == "치명적 하드웨어 오류"
    assert data["events"][0]["category"] == "whea_fatal"


def test_truncated_log_is_flagged():
    """로그가 관측 구간보다 짧으면 0건이 '이상 없음'을 뜻하지 않는다."""
    recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()

    assert rel.shape_reliability([], days=30, log_oldest_at=recent)["log_covers_window"] is False
    assert rel.shape_reliability([], days=30, log_oldest_at=old)["log_covers_window"] is True
    assert rel.shape_reliability([], days=30)["log_covers_window"] is None


def test_query_script_covers_every_catalogued_event():
    """카탈로그에 추가한 이벤트가 조회 필터에서 빠지면 영원히 0건이 된다."""
    script = rel.build_script(30)
    for provider, event_id in rel.EVENT_CATALOG:
        assert provider in script
        assert str(event_id) in script


# --- performance --------------------------------------------------------------


def test_stats_report_average_and_extremes():
    """평균만 높으면 상시 부하, 최대만 높으면 스파이크다. 구분이 있어야 한다."""
    samples = [{"CpuPercent": 90}, {"CpuPercent": 10}, {"CpuPercent": 50}]
    result = perf.stats(samples, "CpuPercent")

    assert result["avg"] == 50.0
    assert result["max"] == 90.0
    assert result["min"] == 10.0
    assert result["samples"] == [90.0, 10.0, 50.0]


def test_stats_on_empty_samples_returns_nulls_not_zeros():
    assert perf.stats([], "CpuPercent") == {"avg": None, "max": None, "min": None, "samples": []}


def test_sampling_script_is_single_line():
    """배치 실행은 개행을 허용하지 않는다."""
    script = perf.build_sampling_script(3, 1000)
    assert "\n" not in script
    assert "Start-Sleep -Milliseconds 1000" in script
    cim._spec_to_script({"script": script})  # 예외가 나면 실패


def test_power_plan_is_identified_by_guid_not_name():
    """ElementName은 로케일마다 다르다. GUID로 판정해야 한국어 Windows에서도 맞다."""
    row = [{"Active": "전원 구성표 GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (절전)"}]
    plan = perf.shape_power_plan(row)

    assert plan["scheme"] == "power_saver"
    assert plan["is_power_saver"] is True


def test_balanced_power_plan_is_not_flagged():
    row = [{"Active": "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"}]
    assert perf.shape_power_plan(row)["is_power_saver"] is False


def test_unknown_power_plan_stays_unknown():
    assert perf.shape_power_plan([])["scheme"] is None


def test_thermal_converts_tenths_of_kelvin_to_celsius():
    rows = [{"CurrentTemperature": 3131}, {"CurrentTemperature": 3231}]
    thermal = perf.shape_thermal(rows)

    assert thermal["available"] is True
    assert thermal["max_c"] == 50.0
    assert thermal["zones_c"] == [40.0, 50.0]


def test_thermal_absence_is_normal_not_an_error():
    """온도 미지원 메인보드가 많다. 결측이 collector 실패가 되면 안 된다."""
    thermal = perf.shape_thermal([{"CurrentTemperature": 0}])
    assert thermal["available"] is False
    assert thermal["max_c"] is None


def test_top_processes_keep_only_image_names():
    """명령줄·경로는 수집하지 않는다는 프라이버시 경계를 고정한다."""
    rows = [{"Name": "chrome#2", "PercentProcessorTime": 45, "WorkingSetPrivate": 512 * 1024 ** 2}]
    process = perf.shape_top_processes(rows)[0]

    assert process == {"name": "chrome#2", "cpu_percent": 45.0, "memory_mb": 512.0}


# --- M3 정규화 ----------------------------------------------------------------


def make_snapshot(**sections) -> dict:
    results = [
        CollectorResult(name=name, status="ok", milestone="M2", data=data)
        for name, data in sections.items()
    ]
    return build_snapshot(results)


def test_health_profile_keys_are_stable_without_any_m2_section():
    """소비자가 키 존재 여부를 방어하지 않아도 되게 한다."""
    profile = to_health_profile(make_snapshot())

    assert set(profile) == {"system_volume", "worst_disk", "events", "load"}
    assert profile["system_volume"]["free_gb"] is None
    assert profile["events"]["whea_corrected"] is None
    assert profile["load"]["cpu_avg_percent"] is None


def test_health_profile_picks_system_volume_and_worst_disk():
    snapshot = make_snapshot(
        storage_health={
            "volumes": [
                {"drive": "D:", "free_gb": 10.0, "free_percent": 1.0, "is_system": False},
                {"drive": "C:", "size_gb": 500.0, "free_gb": 200.0, "free_percent": 40.0, "is_system": True},
            ],
            "disks": [
                {"model": "healthy", "wear_percent": 2, "reallocated_sectors": 0, "pending_sectors": 0},
                {"model": "failing", "wear_percent": 5, "reallocated_sectors": 40, "pending_sectors": 2,
                 "predict_failure": False},
            ],
        }
    )
    profile = to_health_profile(snapshot)

    assert profile["system_volume"]["drive"] == "C:"
    assert profile["worst_disk"]["model"] == "failing"


def test_spec_profile_merges_inventory_with_wear():
    """견적 계층은 '무엇이 달렸는가'와 '얼마나 닳았는가'를 한 목록에서 본다."""
    snapshot = make_snapshot(
        hardware={
            "cpu": [], "gpu": [], "memory": {}, "motherboard": {},
            "storage": [
                {"model": "Samsung SSD 970", "size_gb": 465.76, "media_type": "SSD", "bus_type": "NVMe"},
                {"model": "ST2000DM008", "size_gb": 1863.01, "media_type": "HDD", "bus_type": "SATA"},
            ],
        },
        storage_health={
            "volumes": [],
            # 열거 순서가 인벤토리와 다르다 - 모델/용량으로 맞춰야 한다
            "disks": [
                {"index": 0, "model": "ST2000DM008", "size_gb": 1863.01, "wear_percent": None,
                 "reallocated_sectors": 8, "pending_sectors": 0},
                {"index": 1, "model": "Samsung SSD 970", "size_gb": 465.76, "wear_percent": 11,
                 "reallocated_sectors": 0, "pending_sectors": 0},
            ],
        },
    )
    storage = to_spec_profile(snapshot)["storage"]

    assert storage[0]["model"] == "Samsung SSD 970"
    assert storage[0]["wear_percent"] == 11
    assert storage[1]["reallocated_sectors"] == 8


def test_spec_profile_storage_keys_exist_without_health_section():
    snapshot = make_snapshot(
        hardware={"cpu": [], "gpu": [], "memory": {}, "motherboard": {},
                  "storage": [{"model": "X", "size_gb": 500.0}]}
    )
    disk = to_spec_profile(snapshot)["storage"][0]

    assert "wear_percent" in disk and disk["wear_percent"] is None


def test_section_summaries_include_unusable_sections():
    """못 본 항목이 목록에서 사라지면 '이상 없음'처럼 보인다."""
    snapshot = build_snapshot(
        [
            CollectorResult(name="hardware", status="ok", data={"cpu": [], "memory": {}, "storage": []}),
            CollectorResult(name="storage_health", status="error", error="CIM 실패"),
            CollectorResult(name="security", status="planned", milestone="M6"),
        ]
    )
    summaries = {item["name"]: item for item in section_summaries(snapshot)}

    assert summaries["storage_health"]["status"] == "error"
    assert summaries["storage_health"]["headline"] == "CIM 실패"
    assert summaries["security"]["status"] == "planned"


# --- M3 저장소 ----------------------------------------------------------------


def test_new_database_is_created_at_current_version(tmp_path: Path):
    with SnapshotStore(tmp_path / "agent.db") as store:
        assert store.schema_version == DB_SCHEMA_VERSION


def test_migration_keeps_existing_snapshots(tmp_path: Path):
    """스키마가 올라가도 과거 스냅샷은 남아야 한다 - 추세 분석의 근거다."""
    db_path = tmp_path / "old.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE snapshots (
            snapshot_id TEXT PRIMARY KEY, device_id TEXT, collected_at TEXT NOT NULL,
            scan_mode TEXT NOT NULL, schema_version TEXT NOT NULL, agent_version TEXT,
            uploaded_at TEXT, payload TEXT NOT NULL);
        CREATE TABLE collector_runs (
            snapshot_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
            milestone TEXT, duration_ms REAL, error TEXT, PRIMARY KEY (snapshot_id, name));
        """
    )
    legacy.execute(
        "INSERT INTO snapshots VALUES ('old-1', 'dev-a', '2026-01-01T00:00:00+00:00',"
        " 'actual', '1.0.0', '0.1.0', NULL, '{\"snapshot_id\": \"old-1\"}')"
    )
    legacy.commit()
    legacy.close()

    with SnapshotStore(db_path) as store:
        assert store.schema_version == DB_SCHEMA_VERSION
        assert store.count() == 1
        assert store.get("old-1")["snapshot_id"] == "old-1"
        # 새 컬럼이 붙었는지
        store.save(build_snapshot([], device_id="dev-a") | {"notes": "RAM 교체 후"})
        assert store.list_recent()[0]["notes"] == "RAM 교체 후"


def test_migration_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "agent.db"
    for _ in range(3):
        with SnapshotStore(db_path) as store:
            assert store.schema_version == DB_SCHEMA_VERSION


def _snapshot_at(days_ago: int, device_id: str = "dev-a") -> dict:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    snapshot = build_snapshot([], device_id=device_id)
    snapshot["collected_at"] = moment.isoformat(timespec="seconds")
    return snapshot


def test_prune_requires_both_conditions(tmp_path: Path):
    """오래됐어도 최근 N개 안에 들면 남긴다."""
    with SnapshotStore(tmp_path / "agent.db") as store:
        for days in (400, 300, 200, 1):
            store.save(_snapshot_at(days))

        # 최근 3개는 보호되므로 400일짜리 하나만 지워진다
        assert store.prune(keep_last=3, older_than_days=180) == 1
        assert store.count() == 3


def test_prune_without_conditions_deletes_nothing(tmp_path: Path):
    with SnapshotStore(tmp_path / "agent.db") as store:
        store.save(_snapshot_at(500))
        assert store.prune() == 0
        assert store.count() == 1


def test_history_is_scoped_to_device_and_ordered_oldest_first(tmp_path: Path):
    with SnapshotStore(tmp_path / "agent.db") as store:
        store.save(_snapshot_at(10, "dev-a"))
        store.save(_snapshot_at(1, "dev-a"))
        store.save(_snapshot_at(5, "dev-b"))

        history = store.history("dev-a")
        assert len(history) == 2
        assert history[0]["collected_at"] < history[1]["collected_at"]
        assert store.device_ids() == ["dev-a", "dev-b"]
