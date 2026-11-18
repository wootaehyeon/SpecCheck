"""Versioned numerical telemetry features. No diagnostic thresholds or labels here."""
from datetime import datetime, timezone
import math

FEATURE_VERSION = 1
# Ordered feature names, used by both training and inference.
FEATURES = {
    "HW-RAM-001": ("speed_ratio",),
    "HW-RAM-002": ("total_gb",),
    "HW-DISK-001": ("is_hdd",),
    "SW-GPU-001": ("age_days",),
    "SW-BIOS-001": ("age_days",),
    "ST-SPACE-001": ("free_percent", "free_gb"),
    "ST-SMART-001": ("reallocated_sectors", "pending_sectors"),
    "ST-SMART-002": ("predict_failure",),
    "ST-WEAR-001": ("wear_percent",),
    "RL-WHEA-001": ("whea_corrected",),
    "RL-WHEA-002": ("whea_fatal",),
    "RL-CRASH-001": ("crash_count",),
    "RL-DISK-001": ("io_error_count",),
    "PF-MEM-001": ("committed_percent", "available_mb"),
    "PF-CPU-001": ("cpu_avg", "cpu_min"),
    "PF-POWER-001": ("is_power_saver",),
    "PF-THROTTLE-001": ("clock_ratio", "cpu_avg", "temperature"),
    "SEC-SYSMON-025": ("tampering_count",),
    "SEC-SYSMON-COVERAGE": ("log_gap", "truncated", "error_count"),
}


def number(value):
    if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
        return float(value)
    return None


def age(value, now):
    try:
        dt = datetime.fromisoformat(str(value))
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        return number((now - dt).days)
    except (ValueError, TypeError):
        return None


def extract(snapshot):
    """Return entity-level rows; missing required values abstain instead of becoming zero."""
    rows = {key: [] for key in FEATURES}

    def add(key, values, source, raw):
        values = [number(v) for v in values]
        if all(v is not None for v in values):
            rows[key].append((values, source, raw))

    hw = snapshot.data("hardware")
    mem = hw.get("memory") or {}
    add("HW-RAM-002", [mem.get("total_gb")], "hardware.memory", mem)
    for i, module in enumerate(mem.get("modules") or []):
        rated, configured = number(module.get("rated_speed_mhz")), number(module.get("configured_speed_mhz"))
        if rated and configured:
            add("HW-RAM-001", [configured / rated], f"hardware.memory.modules[{i}]", module)
    disks = hw.get("storage") or []
    primary = disks[0] if disks else None
    identified = False
    for disk in snapshot.data("storage_health").get("disks") or []:
        if disk.get("is_system"):
            identified = True
            primary = next((d for d in disks if str(d.get("model", "")).strip().lower() == str(disk.get("model", "")).strip().lower()), None)
            break
    if primary and primary.get("media_type") in ("HDD", "SSD"):
        add("HW-DISK-001", [primary["media_type"] == "HDD"], "hardware.storage", {**primary, "identified": identified})
    now = datetime.now(timezone.utc)
    for gpu in hw.get("gpu") or []:
        add("SW-GPU-001", [age(gpu.get("driver_date"), now)], "hardware.gpu", gpu)
    bios = (hw.get("motherboard") or {}).get("bios") or {}
    add("SW-BIOS-001", [age(bios.get("released_at"), now)], "hardware.motherboard.bios", bios)
    storage = snapshot.data("storage_health")
    for volume in storage.get("volumes") or []:
        if volume.get("is_system"):
            add("ST-SPACE-001", [volume.get("free_percent"), volume.get("free_gb")], "storage_health.volumes[system]", volume)
            break
    for i, disk in enumerate(storage.get("disks") or []):
        source = f"storage_health.disks[{i}]"
        # Either SMART counter is useful independently; both missing means unknown.
        if any(number(disk.get(k)) is not None for k in FEATURES["ST-SMART-001"]):
            add("ST-SMART-001", [disk.get(k) or 0 for k in FEATURES["ST-SMART-001"]], source, disk)
        add("ST-SMART-002", [disk.get("predict_failure")], source, disk)
        add("ST-WEAR-001", [disk.get("wear_percent")], source, disk)
    totals = snapshot.data("reliability").get("totals") or {}
    for key, field in (("RL-WHEA-001", "whea_corrected"), ("RL-WHEA-002", "whea_fatal")):
        add(key, [totals.get(field)], "reliability.totals", totals)
    for key, fields in (("RL-CRASH-001", ("unexpected_shutdown", "bugcheck")), ("RL-DISK-001", ("disk_error", "filesystem_error"))):
        if any(number(totals.get(f)) is not None for f in fields):
            add(key, [sum(number(totals.get(f)) or 0 for f in fields)], "reliability.totals", totals)
    perf = snapshot.data("performance")
    cpu, mem = perf.get("cpu") or {}, perf.get("memory") or {}
    usage = cpu.get("usage_percent") or {}
    add("PF-MEM-001", [(mem.get("committed_percent") or {}).get("avg"), (mem.get("available_mb") or {}).get("avg")], "performance.memory", mem)
    add("PF-CPU-001", [usage.get("avg"), usage.get("min")], "performance.cpu.usage_percent", usage)
    power = perf.get("power_plan") or {}
    add("PF-POWER-001", [power.get("is_power_saver")], "performance.power_plan", power)
    thermal = perf.get("thermal") or {}
    # Impute missing temperature as 0 for the model only; raw evidence never reports it as measured.
    temp = number(thermal.get("max_c"))
    add("PF-THROTTLE-001", [(cpu.get("clock") or {}).get("ratio"), usage.get("avg"), temp if temp is not None else 0], "performance.cpu.clock", cpu.get("clock") or {})
    security = snapshot.data("security")
    events = security.get("events") or []
    if snapshot.scan_mode == "actual" and "events" in security:
        add("SEC-SYSMON-025", [sum(e.get("event_id") == 25 for e in events)], "security.events", {"count": len(events)})
    if security and "sysmon" not in security:
        add("SEC-SYSMON-COVERAGE", [bool(security.get("log_gap")), bool(security.get("truncated")), sum(e.get("event_id") == 255 for e in events)], "security", {"log_gap": security.get("log_gap"), "truncated": security.get("truncated")})
    return rows
