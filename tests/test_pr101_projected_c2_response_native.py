"""Integration gates requiring retained private PR99/PR101 receipts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr101_projected_c2_response import (  # noqa: E402
    CONTROL_ROOT,
    REVIEWED_PREFLIGHT,
    _trace_receipt_row,
    _validate_reviewed_control,
)

_CONTROL_ASSETS_AVAILABLE = (REVIEWED_PREFLIGHT.is_file() and all(
    (CONTROL_ROOT / arm / name).is_file()
    for arm in ("OFF", "HYDRO", "COUPLED") for name in ("receipt.json", "preflight.json")))
_MISSING_CONTROL_ASSETS = pytest.mark.skipif(
    not _CONTROL_ASSETS_AVAILABLE,
    reason="retained private PR99 closed controls and reviewed PR101 preflight are unavailable")


@pytest.mark.parametrize("arm", ["OFF", "HYDRO", "COUPLED"])
@_MISSING_CONTROL_ASSETS
def test_original_c2_trace_inventory_routes_compressed_raw_name(arm):
    receipt = json.loads((CONTROL_ROOT / arm / "receipt.json").read_text())
    row = _trace_receipt_row(receipt)
    compressed_entry = next(item for item in receipt["generated_files"]
                            if item["path"] == row["compressed_path"])
    assert row["path"] == "pr85_joint_moment_stages.raw"
    assert row["compressed_path"] == "pr85_joint_moment_stages.raw.gz"
    assert len(row["sha256"]) == 64 and row["bytes"] > 0
    assert compressed_entry["sha256"] == row["compressed_sha256"]


@pytest.mark.parametrize("arm", ["OFF", "HYDRO", "COUPLED"])
@_MISSING_CONTROL_ASSETS
def test_original_c2_receipt_and_input_match_reviewed_preflight_pin(arm):
    root = CONTROL_ROOT / arm
    receipt = json.loads((root / "receipt.json").read_text())
    preflight = json.loads((root / "preflight.json").read_text())
    reviewed = json.loads(REVIEWED_PREFLIGHT.read_text())
    _validate_reviewed_control(arm, root, receipt, preflight, reviewed)
    changed = dict(receipt, candidate_wrfinput_sha256="replacement-input")
    with pytest.raises(ValueError, match="reviewed PR101 receipt/preflight/input pins"):
        _validate_reviewed_control(arm, root, changed, preflight, reviewed)
