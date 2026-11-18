"""Summarize simultaneous Windows counter intervals for one reproduction run."""
import json
import subprocess
from collections import defaultdict
from pathlib import Path


def latency(previous, current, direction):
    field = "AvgDisksecPer" + direction
    count = current[field + "_Base"] - previous[field + "_Base"]
    ticks = current[field] - previous[field]
    frequency = current["Frequency_PerfTime"]
    if count > 0 and ticks >= 0 and frequency > 0:
        return round(1000 * ticks / frequency / count, 2)
    return None


def summarize(raw):
    samples = raw["samples"]
    timeline = []
    totals = defaultdict(lambda: [0., 0., 0.])
    streak = {}
    longest = {}
    for prev, now in zip(samples, samples[1:]):
        seconds = now["t"] - prev["t"]
        ticks = now["ticks"] - prev["ticks"]
        cpu = max(0, min(100, 100 * (1 - (now["cpu"] - prev["cpu"]) / ticks)))
        memory = 100 * (1 - now["available"] / raw["memoryMB"])
        old_apps = {(p["IDProcess"], p["ElapsedTime"]): p for p in prev["apps"]}
        apps = defaultdict(lambda: [0., 0., 0.])
        for p in now["apps"]:
            name = p["Name"].split("#")[0]
            values = apps[name]
            values[1] += p["WorkingSetPrivate"] / 1024**2
            old = old_apps.get((p["IDProcess"], p["ElapsedTime"]))
            if old:
                values[0] += max(0, p["PercentProcessorTime"] - old["PercentProcessorTime"]) / ticks * 100 / raw["cores"]
                values[2] += max(0, p["IODataBytesPersec"] - old["IODataBytesPersec"]) / seconds / 1024**2
        for name, values in apps.items():
            for i, value in enumerate(values):
                totals[name][i] += value * seconds

        active = set()
        if cpu >= 85 and apps and max(v[0] for v in apps.values()) >= 10:
            active.add("CPU")
        if memory >= 90 and now["pages"] > 0:
            active.add("메모리")
        old_disks = {d["Name"]: d for d in prev["disks"]}
        disks = []
        for d in now["disks"]:
            name = d["Name"]
            if name not in old_disks:
                continue
            disk = {"name": name}
            for direction, label in [("Read", "읽기"), ("Write", "쓰기")]:
                ms = latency(old_disks[name], d, direction)
                disk[direction] = ms
                if ms is not None and ms >= 25:
                    active.add(f"디스크 {name} {label}")
            disks.append(disk)
        streak = {key: streak.get(key, 0) + seconds for key in active}
        for key, duration in streak.items():
            longest[key] = max(duration, longest.get(key, 0))
        timeline.append(dict(t=round(now["t"] - samples[0]["t"], 1), cpu=round(cpu, 1),
                             memory=round(memory, 1), disks=disks,
                             leaders=[max(apps, key=lambda n: apps[n][i]) if any(v[i] for v in apps.values()) else None for i in range(3)]))
    duration = samples[-1]["t"] - samples[0]["t"]
    rankings = [[{"name": n, "value": round(v[i] / duration, 2)}
                 for n, v in sorted(totals.items(), key=lambda item: -item[1][i])[:3] if v[i] > 0]
                for i in range(3)]
    return dict(timeline=timeline, rankings=rankings, candidates=[
        {"signal": k, "seconds": round(s, 1)} for k, s in sorted(longest.items(), key=lambda x: -x[1]) if s >= 5])


def measure():
    output = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(Path(__file__).with_name("sample_workload.ps1"))],
        capture_output=True, check=True, timeout=75, creationflags=subprocess.CREATE_NO_WINDOW)
    return summarize(json.loads(output.stdout.decode("utf-8-sig")))
