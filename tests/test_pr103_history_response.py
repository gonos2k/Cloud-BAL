from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr103_history_response as reader


def test_adds_direct_array_pairs_and_preserves_fivearm_metrics():
    masks = {"support": np.array([True, True, False, False]),
             "buffer": np.array([True, True, True, True])}
    zero = np.array([0.0, 0.0, 0.0, 0.0])
    arrays = {"OFF": {}, "HYDRO": {}, "COUPLED": {}, "P": {}, "STRUCTURED": {}, "A": {}}
    arrays["HYDRO"] = {field: zero for field in reader.FIELDS}
    arrays["COUPLED"] = {field: zero for field in reader.FIELDS}
    arrays["P"] = {field: np.array([1.0, 1.0, 1.0, 1.0]) for field in reader.FIELDS}
    arrays["STRUCTURED"] = {field: np.array([2.0, 2.0, 2.0, 2.0]) for field in reader.FIELDS}
    arrays["OFF"] = {field: zero for field in reader.FIELDS}
    arrays["A"] = {field: np.array([1.0, -1.0, 1.0, -1.0]) for field in reader.FIELDS}

    metrics = {}
    for field, (_, unit) in reader.FIELDS.items():
        minus_off = {}
        for arm in ("HYDRO", "COUPLED", "P", "STRUCTURED"):
            minus_off[arm] = {region: reader._metrics(arrays[arm][field][mask], arrays["OFF"][field][mask])
                              for region, mask in masks.items()}
        metrics[field] = {"unit": unit, "minus_OFF": minus_off}
    readback = {"metrics": {"0": metrics}}
    baseline_metrics = copy.deepcopy(readback["metrics"])

    reader._append_frame_metrics(readback, 0, arrays, masks)

    assert readback["metrics"]["0"]["W"]["minus_OFF"]["A"]["support"]["rms"] == 1.0
    assert readback["paired_metrics"]["A_minus_P"]["0"]["W"]["support"]["rms"] == np.sqrt(2.0)
    assert abs(1.0 - 1.0) == 0.0  # Subtracting independent RMS values would hide this pair response.
    for arm in ("HYDRO", "COUPLED", "P", "STRUCTURED"):
        assert readback["metrics"]["0"]["W"]["minus_OFF"][arm] == baseline_metrics["0"]["W"]["minus_OFF"][arm]


def test_fresh_output_and_failed_receipt_are_preserved(tmp_path, monkeypatch):
    output = tmp_path / "run"
    def fail_after_closed_sidecar(_root, directory, owned_files):
        reader._write_fresh(directory / "history_readback.json", {"schema": "fixture"}, owned_files)
        reader._write_fresh(directory / "closed_history_readback_receipt.json",
                            {"schema": "pr103_closed_history_readback_receipt_v1",
                             "status": "CLOSED"}, owned_files)
        reader._write_fresh(directory / "allsavedtime_response.json", {"schema": "fixture"}, owned_files)
        raise RuntimeError("fixture failure after CLOSED receipt")

    monkeypatch.setattr(reader, "_analyze", fail_after_closed_sidecar)
    try:
        reader.analyze(tmp_path / "A_RUN", output)
    except RuntimeError as exc:
        assert str(exc) == "fixture failure after CLOSED receipt"
    else:
        raise AssertionError("analysis failure was not propagated")
    failure_receipt = json.loads((output / "execution_receipt.json").read_text())
    assert failure_receipt["status"] == "FAILED"
    assert sorted(path.name for path in output.iterdir()) == ["execution_receipt.json"]
    with pytest.raises(FileNotFoundError):
        reader.time_response._verify_new_arm_receipt(
            output / "closed_history_readback_receipt.json", tmp_path / "history_readback.json",
            "0" * 64, reader.TIMES)
    with pytest.raises(ValueError, match="must be fresh"):
        reader.analyze(tmp_path / "A_RUN", output)
