import importlib.util
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr91_history_response", ROOT / "tools/pr91_history_response.py")
response = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(response)


def test_interaction_is_difference_of_paired_arm_differences():
    c5_off = np.asarray([1.0, 2.0])
    c5_on = np.asarray([4.0, 8.0])
    c7_off = np.asarray([3.0, 5.0])
    c7_on = np.asarray([9.0, 12.0])
    delta = response._interaction_delta(c7_on - c7_off, c5_on - c5_off)
    assert np.array_equal(delta, np.asarray([3.0, 1.0]))


def test_interaction_rejects_nonmatching_native_arrays():
    with pytest.raises(ValueError, match="arrays differ in shape"):
        response._interaction_delta(np.zeros((2, 3)), np.zeros((2, 4)))


def test_support_and_neighbor_scopes_are_fixed_distinct_masks():
    support = np.zeros((5, 5), dtype=bool)
    support[2, 2] = True
    masks = response._masks({"shape": [5, 5]}, support)
    assert masks["whole_grid"].sum() == 25
    assert masks["interior_boundary_ring_excluded"].sum() == 9
    assert masks["C7_T0_water_support_27_columns"].sum() == 1
    assert masks["one_cell_neighbor_of_C7_T0_support"].sum() == 8
    assert not np.any(masks["one_cell_neighbor_of_C7_T0_support"] & support)


def test_c7_transient_includes_three_minute_endpoint_but_interaction_stays_common():
    assert response.C7_TIMES == (0, 60, 120, 180)
    assert response.COMMON_TIMES == (0, 60, 120)


def test_receipt_arm_must_match_requested_history_arm(tmp_path):
    history = tmp_path / "history.nc"
    history.write_bytes(b"receipt-bound history")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "arm": "OFF", "status": "COMPLETE", "returncode": 0,
        "generated_files": [{"path": history.name,
                             "sha256": hashlib.sha256(history.read_bytes()).hexdigest()}],
        "expected_model_timestamps": ["2026-08-16_13:00:20"] * 6,
        "candidate_wrfinput_sha256": "input", "candidate_wrfbdy_sha256": "boundary"}))
    with pytest.raises(ValueError, match="expected 'COUPLED'"):
        response._receipt_identity(receipt, history, "COUPLED", 120)


def _write_geometry(path: Path, latitude_shift: float = 0.0, records: int = 2) -> None:
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("Time", records)
        ds.createDimension("south_north", 2)
        ds.createDimension("west_east", 3)
        ds.DX, ds.DY = 5000.0, 5000.0
        lat = ds.createVariable("XLAT", "f8", ("Time", "south_north", "west_east"))
        lon = ds.createVariable("XLONG", "f8", ("Time", "south_north", "west_east"))
        lat[:] = np.arange(records * 6).reshape(records, 2, 3) + latitude_shift
        lon[:] = np.arange(records * 6).reshape(records, 2, 3)


def test_cross_case_geometry_checks_first_grid_record_and_ignores_time_count(tmp_path):
    reference, candidate = tmp_path / "c5.nc", tmp_path / "c7.nc"
    _write_geometry(reference, records=3)
    _write_geometry(candidate, records=4)
    check = response._verify_cross_case_static_geometry(reference, candidate)
    assert check["non_Time_dimensions_exact_match"]
    assert all(row["exact_match"] for row in check["static_fields"].values())

    changed = tmp_path / "changed.nc"
    _write_geometry(changed, latitude_shift=0.01, records=4)
    with pytest.raises(ValueError, match="static grid field XLAT differs"):
        response._verify_cross_case_static_geometry(reference, changed)
