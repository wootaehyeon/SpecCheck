"""Shared missing-data handling for M6-M8 local analysis."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def data(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    section = (snapshot.get("sections") or {}).get(name) or {}
    return section.get("data") or {} if section.get("status") in {"ok", "partial"} else {}


def features(snapshot: dict[str, Any]) -> dict[str, float]:
    """Extract stable numeric signals from the current M2 telemetry contract."""
    result: dict[str, float] = {}
    performance = data(snapshot, "performance")
    for group, metric in (("cpu", "usage_percent"), ("memory", "committed_percent"), ("disk", "queue_length")):
        value = ((performance.get(group) or {}).get(metric) or {}).get("avg")
        if number(value):
            result["performance.{0}.{1}".format(group, metric)] = float(value)

    storage = data(snapshot, "storage_health")
    for volume in storage.get("volumes") or []:
        if volume.get("is_system") and number(volume.get("free_percent")):
            result["storage.free_percent"] = float(volume["free_percent"])
    for disk in storage.get("disks") or []:
        disk_id = str(disk.get("index", disk.get("disk_id", "")))
        if not disk_id.isdecimal():
            continue
        for key in ("wear_percent", "reallocated_sectors"):
            if number(disk.get(key)):
                result["disk.{0}.{1}".format(disk_id, key)] = float(disk[key])

    totals = data(snapshot, "reliability").get("totals") or {}
    whea = sum(value for key, value in totals.items() if key.startswith("whea_") and number(value))
    if whea:
        result["reliability.whea_count"] = float(whea)
    return result


def history_segment(current: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep earlier actual snapshots from one device; a note starts a new baseline."""
    end = timestamp(current.get("collected_at"))
    device_id = current.get("device_id")
    if not end or not device_id or current.get("scan_mode") != "actual":
        return []
    rows: dict[datetime, dict[str, Any]] = {}
    for item in history:
        observed = timestamp(item.get("collected_at"))
        if (observed and observed < end and item.get("device_id") == device_id
                and item.get("scan_mode") == "actual" and item.get("snapshot_id") != current.get("snapshot_id")):
            rows[observed] = item
    ordered = [rows[key] for key in sorted(rows)] + [current]
    for index in range(len(ordered) - 1, -1, -1):
        if ordered[index].get("notes"):
            return ordered[index:]
    return ordered
