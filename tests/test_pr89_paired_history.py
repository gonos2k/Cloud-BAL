import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr89_paired_history", ROOT / "tools/pr89_paired_history.py")
paired = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(paired)


def _var(ds, name, dims, values, units):
    var = ds.createVariable(name, "f8", dims)
    var[:] = values
    var.units = units


def _history(path: Path, arm_shift: float, endpoint_shift: float, *, dx=2.0):
    with netCDF4.Dataset(path, "w") as ds:
        dims = (("Time", 2), ("DateStrLen", 19), ("bottom_top", 2),
                ("bottom_top_stag", 3), ("south_north", 4),
                ("south_north_stag", 5), ("west_east", 5), ("west_east_stag", 6))
        for name, size in dims:
            ds.createDimension(name, size)
        ds.DX, ds.DY = dx, 3.0
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        for record, timestamp in enumerate(("2026-08-16_13:00:00", "2026-08-16_13:01:00")):
            times[record, :] = np.asarray(list(timestamp), dtype="S1")
        yx = ("Time", "south_north", "west_east")
        zyx = ("Time", "bottom_top", "south_north", "west_east")
        z = ("Time", "bottom_top")
        zstag = ("Time", "bottom_top_stag", "south_north", "west_east")
        base = np.zeros((2, 4, 5))
        base[1] = endpoint_shift
        for name, value, unit in (("MU", 1000.0, "Pa"), ("MUB", 0.0, "Pa"),
                                  ("MAPFAC_MX", 1.0, ""), ("MAPFAC_MY", 1.0, "")):
            _var(ds, name, yx, np.full((2, 4, 5), value), unit)
        _var(ds, "C1H", z, np.asarray([[1.0, 0.5]] * 2), "Dimensionless")
        _var(ds, "C2H", z, np.asarray([[100.0, 200.0]] * 2), "Pa")
        _var(ds, "DNW", z, np.asarray([[-0.5, -0.5]] * 2), "Dimensionless")
        for name in paired.native.WATER:
            values = np.full((2, 2, 4, 5), 0.01 + arm_shift)
            values[1] += endpoint_shift
            _var(ds, name, zyx, values, "kg kg-1")
        for name in paired.native.MOMENTS:
            values = np.full((2, 2, 4, 5), 2.0 + arm_shift)
            values[1] += endpoint_shift
            _var(ds, name, zyx, values, "kg(-1)")
        _var(ds, "QIB", zyx, np.full((2, 2, 4, 5), 1e-8 + arm_shift), "m(3) kg(-1)")
        _var(ds, "P", zyx, np.full((2, 2, 4, 5), 10.0 + arm_shift), "Pa")
        _var(ds, "PB", zyx, np.full((2, 2, 4, 5), 90000.0), "Pa")
        _var(ds, "PH", zstag, np.full((2, 3, 4, 5), 1.0 + arm_shift), "m2 s-2")
        _var(ds, "PHB", zstag, np.full((2, 3, 4, 5), 1000.0), "m2 s-2")
        _var(ds, "T", zyx, np.full((2, 2, 4, 5), 0.25 + arm_shift), "K")
        u = np.full((2, 2, 4, 6), arm_shift)
        u[1] += endpoint_shift
        v = np.full((2, 2, 5, 5), arm_shift)
        v[1] += endpoint_shift
        w = np.full((2, 3, 4, 5), arm_shift)
        w[1] += endpoint_shift
        _var(ds, "U", ("Time", "bottom_top", "south_north", "west_east_stag"), u, "m s-1")
        _var(ds, "V", ("Time", "bottom_top", "south_north_stag", "west_east"), v, "m s-1")
        _var(ds, "W", zstag, w, "m s-1")


def _receipt(path: Path, history: Path):
    start = datetime(2026, 8, 16, 13, 0, 0)
    expected = [(start + timedelta(seconds=20 * i)).strftime("%Y-%m-%d_%H:%M:%S")
                for i in (1, 2, 3)]
    data = {"status": "COMPLETE", "returncode": 0, "expected_model_timestamps": expected,
            "model_timestamps": [{"timestamp": t} for t in expected],
            "generated_files": [{"path": history.name,
                                 "sha256": hashlib.sha256(history.read_bytes()).hexdigest()}]}
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setattr(paired.native, "_constants", lambda _: (9.81, {"g_m_s2": 9.81}))
    off = tmp_path / "wrfout_d01_2026-08-16_13:00:00"
    coupled = tmp_path / "coupled_wrfout_d01_2026-08-16_13:00:00"
    _history(off, 0.0, 0.0)
    _history(coupled, 0.002, 0.004)
    return (off, _receipt(tmp_path / "off.json", off), coupled,
            _receipt(tmp_path / "coupled.json", coupled), tmp_path / "unused_constants.json")


def test_carrier_identity_is_independent_of_extensive_difference():
    m_off = np.asarray([2.0, 4.0])
    r_off = np.asarray([0.1, 0.4])
    m_coupled = np.asarray([3.0, 6.0])
    r_coupled = np.asarray([0.3, 0.2])
    extensive, carrier, mixing = paired._decomposition(m_off, r_off, m_coupled, r_coupled)
    direct = m_coupled * r_coupled - m_off * r_off
    assert np.allclose(extensive, direct, rtol=0.0, atol=1e-15)
    assert not np.allclose(carrier, direct)
    assert not np.allclose(mixing, direct)


def test_receipt_bound_pair_has_fixed_scopes_and_exact_geometry(pair):
    off, off_receipt, coupled, coupled_receipt, constants = pair
    result = paired._analyze(off, off_receipt, coupled, coupled_receipt, constants)
    assert all(row["exact_match"] for row in
               result["geometry"]["cross_arm_exact_match"]["static_fields"].values())
    assert result["geometry"]["cross_arm_exact_match"]["dx_m"] == 2.0
    pressure = result["field_comparisons"]["P+PB"]["descriptor"]
    assert pressure["exact_match_across_arms"]
    assert pressure["variables"][0]["units"] == "Pa"
    assert result["field_comparisons"]["U"]["descriptor"]["variables"][0][
        "dimensions_without_time"] == ["bottom_top", "south_north", "west_east_stag"]
    support = result["geometry"]["scope_definitions"]["initial_native_analysis_water_support"]
    assert support["selected_horizontal_columns"] == 20
    assert len(support["packed_bitmask_sha256_little_bitorder"]) == 64
    scopes = result["field_comparisons"]["QCLOUD"]["deltaX_T60_COUPLED_minus_OFF"]["scopes"]
    assert set(scopes) == {"same_fixed_whole_native_grid", "same_fixed_interior_boundary_ring_excluded",
                           "initial_native_analysis_water_support"}
    carrier = result["endpoint_carrier_decomposition_T60"]["QCLOUD"]["scopes"][
        "same_fixed_whole_native_grid"]
    assert carrier["exact_identity_residual_max_abs"] < 1e-12
    assert set(carrier["temporal_extensive_change_by_arm"]) == {"OFF", "COUPLED"}
    evolution = carrier["delta_extensive_evolution_T60_minus_T0"]
    assert evolution["exact_identity_residual_max_abs"] < 1e-12
    assert np.isclose(evolution["extensive_change"]["signed_total"],
                      evolution["mean_dry_mass_times_mixing_ratio_contribution"]["signed_total"] +
                      evolution["mean_mixing_ratio_times_dry_mass_contribution"]["signed_total"],
                      rtol=0.0, atol=1e-12)


def test_empty_t0_water_support_is_reported_without_failing(pair):
    off, _, coupled, coupled_receipt, constants = pair
    with netCDF4.Dataset(off) as off_ds, netCDF4.Dataset(coupled, "r+") as coupled_ds:
        for name in paired.native.WATER:
            coupled_ds.variables[name][0] = off_ds.variables[name][0]
    _receipt(coupled_receipt, coupled)
    result = paired._analyze(off, _receipt(off.parent / "off.json", off), coupled,
                             coupled_receipt, constants)
    support = result["geometry"]["scope_definitions"]["initial_native_analysis_water_support"]
    assert support["selected_horizontal_columns"] == 0
    row = result["field_comparisons"]["QCLOUD"]["deltaX_T60_COUPLED_minus_OFF"]["scopes"][
        "initial_native_analysis_water_support"]
    assert row["status"] == "EMPTY_SCOPE"
    assert row["selected_cell_count"] == 0
    assert row["max_abs_cell"] is None
    assert row["max_abs_column"] is None
    carrier = result["endpoint_carrier_decomposition_T60"]["QCLOUD"]["scopes"][
        "initial_native_analysis_water_support"]
    assert carrier["exact_identity_residual_max_abs"] is None


def test_pair_rejects_geometry_and_receipt_hash_mismatch(pair):
    off, off_receipt, coupled, coupled_receipt, constants = pair
    bad_geometry = paired._records(coupled)[1]
    bad_geometry["dx"] = 999.0
    with pytest.raises(ValueError, match="mass grids differ"):
        paired._pair_geometry(paired._records(off)[1], bad_geometry)
    coupled_receipt.write_text(coupled_receipt.read_text().replace(
        hashlib.sha256(coupled.read_bytes()).hexdigest(), "0" * 64))
    with pytest.raises(ValueError, match="not hash-bound"):
        paired._analyze(off, off_receipt, coupled, coupled_receipt, constants)
