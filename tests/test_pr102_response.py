from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr102_response as response


def test_response_metrics_are_paired_descriptive_and_finite():
    result = response.response_metrics(np.array([3.0, -1.0]), np.array([1.0, 2.0]))
    assert result == {"n": 2, "signed_sum": -1.0, "rms": np.sqrt(6.5),
                      "l1": 5.0, "max_abs": 3.0,
                      "candidate_rms": np.sqrt(5.0), "reference_rms": np.sqrt(2.5)}
    with pytest.raises(ValueError, match="identical finite support"):
        response.response_metrics(np.array([1.0, np.nan]), np.array([0.0, 0.0]))
    with pytest.raises(ValueError, match="identical finite support"):
        response.response_metrics(np.ones(2), np.ones(3))


def test_source_arm_aliases_are_explicit_and_pair_direction_is_preserved():
    native = {"absolute_by_arm": {"OFF": {"l2": 1}, "HYDRO": {"l2": 2}, "COUPLED": {"l2": 4}},
              "paired_increments": {"HYDRO_minus_OFF": {"delta_l2": 1},
                                    "COUPLED_minus_HYDRO": {"delta_l2": 2},
                                    "COUPLED_minus_OFF": {"delta_l2": 3}},
              "increments": {"h_H_minus_O": {"l2": 1}, "b_C_minus_H": {"l2": 2},
                            "net_C_minus_O": {"l2": 3}}}
    renamed = response._rename_source_roles(native)
    assert renamed["absolute_by_arm"] == {"H": {"l2": 1}, "P": {"l2": 2}, "N": {"l2": 4}}
    assert renamed["paired_increments"] == {"P_minus_H": {"delta_l2": 1},
                                              "N_minus_P": {"delta_l2": 2},
                                              "N_minus_H": {"delta_l2": 3}}
    assert renamed["increments"] == {"P_minus_H": {"l2": 1}, "N_minus_P": {"l2": 2},
                                      "N_minus_H": {"l2": 3}}


def test_structured_run_requires_all_32_pinned_times_and_closed_preflight(tmp_path):
    times = [(response.history.START + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
             for step in range(1, 33)]
    receipt = {"arm": "STRUCTURED", "status": "COMPLETE", "returncode": 0,
               "timestep_count": 32, "final_completed_step": 32, "maximum_seen_timestep": 32,
               "model_timestamps": [{"timestamp": value} for value in times],
               "earliest_fatal": None, "processing_errors": [], "fatal_lines": [],
               "changed_staged_inputs": [], "changed_original_inputs": [],
               "duplicate_post_kdm6_timesteps": [], "candidate_build_unchanged": True,
               "candidate_input_unchanged": True,
               "executed_executable_sha256": response.preflight.EXPECTED_EXECUTABLE,
               "candidate_wrfbdy_sha256": response.preflight.EXPECTED_BOUNDARY,
               "candidate_namelist_sha256": response.preflight.EXPECTED_NAMELIST,
               "candidate_wrfinput_sha256": "candidate-input"}
    run_preflight = {"arm": "STRUCTURED", "duration_seconds": 640, "expected_timesteps": 32,
                     "candidate_wrfinput_sha256": "candidate-input"}
    acceptance = {"schema": "pr102_execution_preflight_v1", "arm": "STRUCTURED",
                  "status": "READY_FOR_ROOT_REVIEW_NO_LAUNCH"}
    (tmp_path / "receipt.json").write_text(json.dumps(receipt))
    (tmp_path / "preflight.json").write_text(json.dumps(run_preflight))
    closed, _ = response._closed_structured_run(tmp_path, acceptance)
    assert closed["timestep_count"] == 32

    receipt["model_timestamps"] = receipt["model_timestamps"][:-1]
    (tmp_path / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="timestamps differ"):
        response._closed_structured_run(tmp_path, acceptance)



def _dry_capture_fixture(tmp_path, monkeypatch):
    roots, receipt_rows = {}, {}
    c1h = np.array([0.5, 0.25], dtype=np.float32)
    dnw = np.array([-0.25, -0.5], dtype=np.float32)
    area = np.full((6, 6), 2.0, dtype=np.float64)
    increments = {"H": 0.5, "P": 1.0, "N": 1.5}
    for role in ("H", "P", "N"):
        root = tmp_path / role
        root.mkdir()
        input_path = root / "wrfinput_d01"
        input_path.write_bytes(role.encode())
        roots[role] = root
        receipt_rows[role] = {"input_sha256": response.sha256(input_path)}

    class Dataset:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def set_auto_mask(self, _):
            pass

    monkeypatch.setattr(response.netCDF4, "Dataset", lambda _: Dataset())
    monkeypatch.setattr(response, "_read_map_geometry", lambda *_: (area.copy(), None, None))
    monkeypatch.setattr(response, "_finite", lambda _ds, name, _record:
                        c1h.copy() if name == "C1H" else dnw.copy())
    monkeypatch.setattr(response, "_constants", lambda _:
                        (10.0, {"path": "manufactured", "sha256": "a" * 64, "g_m_s2": 10.0}))

    bounds = (1, 6, 1, 6, 2, 5, 2, 5)
    def capture(root, prefix, _rank):
        role = root.name
        before = np.full((6, 6), 10.0, dtype=np.float32)
        if prefix == "pr98_mu_small_in_":
            return {"fortran_bounds": bounds, "sha256": "b" * 64, "role": role}, before
        if prefix == "pr98_mu_small_out_":
            after = before + np.float32(increments[role])
            return {"fortran_bounds": bounds, "sha256": "c" * 64, "role": role}, after
        if prefix == "pr98_dts_small":
            return {"fortran_bounds": (), "sha256": "d" * 64, "role": role}, np.array(10.0, dtype=np.float32)
        if prefix == "pr98_geom_c1h":
            return {"fortran_bounds": (1, 2), "sha256": "e" * 64, "role": role}, c1h.copy()
        if prefix == "pr98_mudf_small_out_":
            mudf = np.full((6, 6), increments[role] / 10.0, dtype=np.float32)
            return {"fortran_bounds": bounds, "sha256": "f" * 64, "role": role}, mudf
        raise AssertionError(prefix)
    monkeypatch.setattr(response.native, "native_capture_file", capture)
    return roots, receipt_rows


def test_dry_column_rate_maps_fixed_columns_and_reports_kg_per_second(tmp_path, monkeypatch):
    roots, receipt_rows = _dry_capture_fixture(tmp_path, monkeypatch)
    support = np.ones((2, 4, 4), dtype=bool)
    result = response._dry_column_rates(roots, receipt_rows, support)
    assert result["units"] == "kg/s per native support column"
    assert result["support_columns"] == 16
    assert result["arms"]["H"]["native_columns_ij"] == [
        (i, j) for i in range(2, 6) for j in range(2, 6)]
    assert result["arms"]["H"]["hybrid_beta"] == 0.25
    assert result["arms"]["H"]["dry_column_rate_kg_s_per_column"]["rms"] == pytest.approx(0.0025)
    assert result["paired_increments"]["N_minus_P"]["rms"] == pytest.approx(0.0025)
    assert result["hydro_baseline_nonzero"] is True
    assert result["arms"]["H"]["mu_update_minus_mudf"]["unit"] == "native MU units/s"


def test_dry_column_rate_rejects_support_coordinate_mismatch(tmp_path, monkeypatch):
    roots, receipt_rows = _dry_capture_fixture(tmp_path, monkeypatch)
    original = response.native.support_column_mask
    def shifted_mask(meta, shape, support_columns):
        mask = original(meta, shape, support_columns)
        return np.roll(mask, 1, axis=0) if meta["role"] == "N" else mask
    monkeypatch.setattr(response.native, "support_column_mask", shifted_mask)
    with pytest.raises(ValueError, match="support coordinates differ"):
        response._dry_column_rates(roots, receipt_rows, np.ones((2, 4, 4), dtype=bool))
