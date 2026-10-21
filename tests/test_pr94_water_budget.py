from __future__ import annotations

import importlib.util
import gzip
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr94_water_budget.py"
SPEC = importlib.util.spec_from_file_location("pr94_water_budget", MODULE_PATH)
budget = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(budget)


def test_available_residual_uses_vertical_inventory_change_and_surface_outflow():
    # Opposing layer changes cancel within a column; precipitation is column
    # outflow and is added once after vertical integration.
    inventory_delta = np.array([[[2.0, -1.0]], [[-2.0, 3.0]]])
    precipitation = np.array([[0.5, 1.0]])

    residual = budget.available_column_residual(inventory_delta, precipitation)

    np.testing.assert_array_equal(residual, [[0.5, 3.0]])


def test_available_residual_requires_native_kji_inventory_shape():
    with pytest.raises(ValueError, match="incompatible"):
        budget.available_column_residual(np.zeros((2, 2)), np.zeros((2, 2)))


def test_inventory_and_column_l1_are_distinct_diagnostics():
    cells = np.array([[[4.0]], [[-3.0]]])

    stats = budget._stats(cells)

    assert stats["signed_total_kg"] == 1.0
    assert stats["L1_kg"] == 7.0
    assert stats["max_abs_cell_kg"] == 4.0
    assert stats["max_abs_column_kg"] == 1.0
    assert stats["column_L1_kg"] == 1.0


def test_column_stats_report_signed_l1_and_maximum_native_location():
    values = np.array([[3.0, -4.0], [1.0, 2.0]])
    latitude = np.array([[40.0, 40.0], [41.0, 41.0]])
    longitude = np.array([[130.0, 131.0], [130.0, 131.0]])

    stats = budget.column_map_stats(values, latitude, longitude)

    assert stats["signed_total_kg"] == 2.0
    assert stats["L1_kg"] == 10.0
    assert stats["max_abs_kg"] == 4.0
    assert stats["max_location"] == {"j_zero_based": 0, "i_zero_based": 1,
                                      "latitude_deg": 40.0, "longitude_deg": 131.0}


def test_column_export_writes_private_arrays_and_paired_map_once(tmp_path):
    maps = {}
    for arm, delta in (("OFF", 1.0), ("COUPLED", -1.0)):
        maps[arm] = {"inventory_change_kg": np.array([[delta, 0.0], [0.0, 0.0]]),
                     "precipitation_outflow_kg": np.ones((2, 2)),
                     "available_inventory_change_plus_precipitation_kg": np.full((2, 2), delta + 1.0),
                     "latitude_deg": np.array([[40.0, 40.0], [41.0, 41.0]]),
                     "longitude_deg": np.array([[130.0, 131.0], [130.0, 131.0]]),
                     "cell_area_m2": np.full((2, 2), 25.0)}
    private = tmp_path / "private"
    plot = tmp_path / "public" / "columns.png"

    summary = budget.export_column_diagnostics(private, plot, maps)

    assert summary["private_npz"]["sha256"]
    assert summary["paired_map_png"]["sha256"]
    with np.load(private / "water_columns.npz") as saved:
        np.testing.assert_array_equal(saved["OFF_inventory_change_kg"], maps["OFF"]["inventory_change_kg"])
        np.testing.assert_array_equal(saved["COUPLED_available_inventory_change_plus_precipitation_kg"],
                                      maps["COUPLED"]["available_inventory_change_plus_precipitation_kg"])
    with pytest.raises(FileExistsError):
        budget.export_column_diagnostics(private, plot, maps)


def test_ledger_marker_count_accepts_indented_fortran_records(tmp_path):
    ledger = tmp_path / "source.raw.gz"
    with gzip.open(ledger, "wt") as stream:
        stream.write("  BASELINE_JOINT_FEASIBLE 1 1 T\n")
        stream.write("SOURCE_FIRST_PAIR_FALLBACK 1 1 F F F F\n")
        stream.write("  BASELINE_JOINT_FEASIBLE 1 2 F\n")

    assert budget.count_ledger_marker_rows(ledger, "BASELINE_JOINT_FEASIBLE") == 2


def test_paired_grid_rejects_changed_timestamp_and_coordinates(tmp_path):
    import netCDF4
    roots = {arm: tmp_path / arm for arm in ("OFF", "COUPLED")}
    paths = {}
    for arm, root in roots.items():
        folder = root / "run"
        folder.mkdir(parents=True)
        paths[arm] = folder / "wrfout_d01_2026-08-16_13:00:00"
        with netCDF4.Dataset(paths[arm], "w") as ds:
            ds.DX = ds.DY = 5000.0
            ds.createDimension("Time", 1)
            ds.createDimension("j", 1)
            ds.createDimension("i", 1)
            for name in ("Times", "MAPFAC_MX", "MAPFAC_MY", "XLAT", "XLONG", "C1H", "C2H", "DNW", "MU"):
                ds.createVariable(name, "f8", ("Time", "j", "i"))[:] = 1.0
    assert budget.verify_paired_grid(roots)["coordinates_and_hybrid_coefficients_exact_match"]
    with netCDF4.Dataset(paths["COUPLED"], "a") as ds:
        ds["Times"][:] = 2.0
    with pytest.raises(ValueError, match="timestamps"):
        budget.verify_paired_grid(roots)
    with netCDF4.Dataset(paths["COUPLED"], "a") as ds:
        ds["Times"][:] = 1.0
        ds["XLAT"][:] = 2.0
    with pytest.raises(ValueError, match="XLAT"):
        budget.verify_paired_grid(roots)
