import uuid

import pytest

from speccheck_agent.snapshot import build_snapshot


def test_requested_snapshot_id_is_preserved():
    expected = str(uuid.uuid4())
    assert build_snapshot([], snapshot_id=expected)["snapshot_id"] == expected


def test_standalone_scan_still_generates_unique_ids():
    assert build_snapshot([])["snapshot_id"] != build_snapshot([])["snapshot_id"]


def test_invalid_snapshot_id_is_rejected():
    with pytest.raises(ValueError):
        build_snapshot([], snapshot_id="not-a-uuid")
