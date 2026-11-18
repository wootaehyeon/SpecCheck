from app.services.workload import summarize


def samples(writes):
    rows = []
    for i, busy in enumerate(writes):
        rows.append({
            "t": i * 2, "ticks": i * 20_000_000, "cpu": i * 18_000_000,
            "available": 400, "pages": 0, "apps": [],
            "disks": [{"Name": "1 D:", "Frequency_PerfTime": 1000,
                       "AvgDisksecPerRead": 0, "AvgDisksecPerRead_Base": 0,
                       "AvgDisksecPerWrite": busy * 30, "AvgDisksecPerWrite_Base": busy}],
        })
    return {"samples": rows, "memoryMB": 1000, "cores": 4}


def test_latency_needs_completed_operations_and_contiguous_load():
    result = summarize(samples([0, 1, 2, 2, 3]))
    assert result["candidates"] == []
    assert result["timeline"][2]["disks"][0]["Write"] is None
    result = summarize(samples([0, 1, 2, 3]))
    assert result["candidates"] == [{"signal": "디스크 1 D: 쓰기", "seconds": 6}]
    assert result["timeline"][0]["disks"][0]["Read"] is None


def test_process_restart_does_not_transfer_cpu_or_io_counters():
    raw = samples([0, 0, 0])
    for i, row in enumerate(raw["samples"]):
        row["apps"] = [{"Name": "App", "IDProcess": 8, "ElapsedTime": int(i > 0),
                        "PercentProcessorTime": i * 20_000_000,
                        "WorkingSetPrivate": 1048576, "IODataBytesPersec": i * 2097152}]
    result = summarize(raw)
    assert [ranking[0]["value"] for ranking in result["rankings"]] == [12.5, 1, 0.5]
