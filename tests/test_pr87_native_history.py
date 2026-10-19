import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr87_native_history", ROOT / "tools/pr87_native_history.py")
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)
CONSTANTS = ROOT / "docs/evidence/pr87_followup_20261019/history/receipt.json"


def _var(ds, name, dims, values, units, *, fill_value=None):
    var = ds.createVariable(name, "f8", dims, fill_value=fill_value)
    var[:] = values
    var.units = units


def _history(path: Path, timestamp: str, mu_value: float, *, dnw=(-0.5, -0.5),
             negative_maps=False, fill_water=False, negative_carrier=False) -> None:
    with netCDF4.Dataset(path, "w") as ds:
        for name, size in (("Time", 1), ("DateStrLen", 19), ("bottom_top", 2),
                           ("bottom_top_stag", 3), ("south_north", 4),
                           ("south_north_stag", 5), ("west_east", 5),
                           ("west_east_stag", 6)):
            ds.createDimension(name, size)
        ds.DX, ds.DY = 2.0, 3.0
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list(timestamp), dtype="S1")
        horiz = ("Time", "south_north", "west_east")
        mass = ("Time", "bottom_top", "south_north", "west_east")
        coeff = ("Time", "bottom_top")
        stagger_z = ("Time", "bottom_top_stag", "south_north", "west_east")
        for name, value in (("MU", mu_value), ("MUB", 0.0)):
            _var(ds, name, horiz, np.full((1, 4, 5), value), "Pa")
        map_value = -1.0 if negative_maps else 1.0
        _var(ds, "MAPFAC_MX", horiz, np.full((1, 4, 5), map_value), "")
        _var(ds, "MAPFAC_MY", horiz, np.full((1, 4, 5), map_value), "")
        _var(ds, "C1H", coeff, [[1.0, 0.5]], "Dimensionless")
        c2 = [-2000.0, -2000.0] if negative_carrier else [100.0, 200.0]
        _var(ds, "C2H", coeff, [c2], "Pa")
        _var(ds, "DNW", coeff, [dnw], "")
        for name in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP"):
            fill = -9999.0 if fill_water and name == "QCLOUD" else None
            _var(ds, name, mass, np.full((1, 2, 4, 5), 0.01), "kg kg-1", fill_value=fill)
            if fill is not None:
                ds.variables[name][0, 0, 0, 0] = fill
        for name in ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN"):
            _var(ds, name, mass, np.full((1, 2, 4, 5), 2.0), "kg(-1)")
        _var(ds, "QIB", mass, np.full((1, 2, 4, 5), 1.0e-8), "m(3) kg(-1)")
        for name, value in (("P", 10.0), ("PB", 90000.0)):
            _var(ds, name, mass, np.full((1, 2, 4, 5), value), "Pa")
        for name, value in (("PH", 1.0), ("PHB", 1000.0)):
            _var(ds, name, stagger_z, np.full((1, 3, 4, 5), value), "m2 s-2")
        _var(ds, "T", mass, np.full((1, 2, 4, 5), 0.25), "K")
        _var(ds, "U", ("Time", "bottom_top", "south_north", "west_east_stag"),
             np.full((1, 2, 4, 6), mu_value / 1000), "m s-1")
        _var(ds, "V", ("Time", "bottom_top", "south_north_stag", "west_east"),
             np.full((1, 2, 5, 5), mu_value / 2000), "m s-1")
        _var(ds, "W", stagger_z, np.full((1, 3, 4, 5), mu_value / 3000), "m s-1")


def _receipts(tmp_path: Path, paths: list[Path]) -> Path:
    start = datetime.strptime(paths[0].name.removeprefix("wrfout_").removesuffix(".nc"),
                              "%Y-%m-%d_%H:%M:%S")
    history_end = datetime.strptime(paths[-1].name.removeprefix("wrfout_").removesuffix(".nc"),
                                    "%Y-%m-%d_%H:%M:%S")
    duration = int((history_end - start).total_seconds())
    expected = [(start + timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                for step in range(1, duration // 20 + 1)]
    stamp_rows = [{"timestamp": value, "elapsed_seconds": 20 * (index + 1)}
                  for index, value in enumerate(expected)]
    receipt = {
        "status": "COMPLETE", "returncode": 0, "model_timestamps": stamp_rows,
        "expected_model_timestamps": expected,
        "timestep_count": len(stamp_rows), "final_completed_step": len(stamp_rows),
        "generated_files": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                             "bytes": p.stat().st_size} for p in paths],
    }
    target = tmp_path / "run_receipt.json"
    target.write_text(json.dumps(receipt))
    return target


def _pair(tmp_path: Path, *, bad_dnw=False, negative_maps=False, fill_water=False,
          negative_carrier=False):
    paths = [tmp_path / "wrfout_2026-08-16_13:00:00.nc",
             tmp_path / "wrfout_2026-08-16_13:01:00.nc"]
    _history(paths[0], "2026-08-16_13:00:00", 1000.0)
    _history(paths[1], "2026-08-16_13:01:00", 1200.0,
             dnw=(0.5, 0.5) if bad_dnw else (-0.5, -0.5),
             negative_maps=negative_maps, fill_water=fill_water,
             negative_carrier=negative_carrier)
    return paths, _receipts(tmp_path, paths)


def test_dynamic_hybrid_inventory_and_state_delta(tmp_path):
    paths, receipt = _pair(tmp_path)
    result = native._analyze(paths, receipt, CONSTANTS, 60, 60, False)
    assert result["status"] == "ACCOUNTED"
    assert result["scoped_data_status"] == "PASS_SCOPED_DATA"
    assert result["physical_approval"] is False
    assert result["state_and_observation_evaluations"] == "NOT_EVALUATED"
    assert result["history_times"] == ["2026-08-16_13:00:00", "2026-08-16_13:01:00"]
    assert result["window"]["run_start_timestamp"] == "2026-08-16_13:00:00"
    assert result["window"]["runner_timestep_seconds"] == 20
    assert result["window"]["requested_endpoint_seconds"] == 60
    first, last = result["records"]
    assert first["inventory"]["all_native_mass_cells"]["mass_cell_count"] == 40
    assert first["inventory"]["interior_excluding_boundary_ring"]["mass_cell_count"] == 12
    g = 9.81000041961669922
    # The hybrid formula gives dp=(550,350) Pa initially and (650,400) finally.
    first_mass = 20 * 6 * (550 + 350) / g
    last_mass = 20 * 6 * (650 + 400) / g
    assert first["inventory"]["all_native_mass_cells"]["water_total_kg"] == pytest.approx(0.06 * first_mass)
    assert last["inventory"]["all_native_mass_cells"]["water_total_kg"] == pytest.approx(0.06 * last_mass)
    assert last["inventory"]["all_native_mass_cells"]["BG_rime_volume_m3"] == pytest.approx(1e-8 * last_mass)
    assert last["inventory"]["all_native_mass_cells"]["dry_mass_kg"] == pytest.approx(last_mass)
    assert last["inventory_delta_from_elapsed_zero"]["all_native_mass_cells"]["dry_mass_kg"] == pytest.approx(
        last_mass - first_mass)
    assert last["inventory_delta_from_elapsed_zero"]["all_native_mass_cells"]["water_total_kg"] == pytest.approx(
        0.06 * (last_mass - first_mass))
    assert first["native_state_delta_from_elapsed_zero"] == {}
    delta = last["native_state_delta_from_elapsed_zero"]
    assert delta["P+PB"]["max_abs"] == 0.0
    assert delta["T_perturb_potential"]["max_abs"] == 0.0
    assert delta["U_mass_point"]["mean"] == pytest.approx(0.2)
    assert delta["V_mass_point"]["mean"] == pytest.approx(0.1)
    assert delta["W_mass_point"]["mean"] == pytest.approx(200 / 3000)
    assert last["physical_change_metrics_from_elapsed_zero"]["all_native_mass_cells"]["total_water"]["L1"] == pytest.approx(
        abs(0.06 * (last_mass - first_mass)))
    assert "moment:QNICE" in last["physical_change_metrics_from_elapsed_zero"]["all_native_mass_cells"]
    assert "BG_rime_volume" in last["physical_change_metrics_from_elapsed_zero"]["all_native_mass_cells"]


def test_invalid_layer_geometry_and_irregular_window_are_rejected(tmp_path):
    paths, receipt = _pair(tmp_path, bad_dnw=True)
    with pytest.raises(ValueError, match="DNW must be negative"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    paths, receipt = _pair(tmp_path, negative_maps=True)
    with pytest.raises(ValueError, match="each map factor must be positive"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    paths, receipt = _pair(tmp_path, bad_dnw=True, negative_carrier=True)
    with pytest.raises(ValueError, match="hybrid pressure carrier positive"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    paths, receipt = _pair(tmp_path)
    with netCDF4.Dataset(paths[1], "a") as ds:
        ds.variables["MU"][:] = -1200.0
    receipt = _receipts(tmp_path, paths)
    with pytest.raises(ValueError, match=r"MU\+MUB and each map factor must be positive"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    paths, receipt = _pair(tmp_path, fill_water=True)
    with pytest.raises(ValueError, match="declared _FillValue sentinel"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    altered_constants = tmp_path / "constants_changed.json"
    constants_data = json.loads(CONSTANTS.read_text())
    constants_data["constants_real32_promoted_to_real64"]["g"] = "9.81"
    altered_constants.write_text(json.dumps(constants_data))
    with pytest.raises(ValueError, match="constants receipt hash"):
        native._constants(altered_constants)

    paths, receipt = _pair(tmp_path)
    data = json.loads(receipt.read_text())
    data["model_timestamps"][-1]["timestamp"] = "2026-08-16_13:00:40"
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="completed model timestamps do not match"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)

    paths, receipt = _pair(tmp_path)
    data = json.loads(receipt.read_text())
    data["expected_model_timestamps"] = ["2026-08-16_12:59:40", "2026-08-16_13:00:00",
                                          "2026-08-16_13:00:20"]
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="history origin does not match"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)


def test_varying_mass_signed_and_l1_changes_and_short_incomplete_window(tmp_path):
    paths, receipt = _pair(tmp_path)
    with netCDF4.Dataset(paths[1], "a") as ds:
        qv = ds.variables["QVAPOR"]
        qv[0, 0, 1, 1] = 0.0
        qv[0, 1, 2, 2] = 0.02
    receipt = _receipts(tmp_path, paths)
    data = json.loads(receipt.read_text())
    data["status"] = "INCOMPLETE"
    data["returncode"] = 1
    data["expected_model_timestamps"].append("2026-08-16_13:01:20")
    data["model_timestamps"].append({"timestamp": "2026-08-16_13:01:20", "elapsed_seconds": 80})
    data["timestep_count"] = 4
    data["final_completed_step"] = 4
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="explicit incomplete-window"):
        native._analyze(paths, receipt, CONSTANTS, 60, 60, False)
    result = native._analyze(paths, receipt, CONSTANTS, 60, 60, True)
    endpoint = result["records"][-1]
    change = endpoint["physical_change_metrics_from_elapsed_zero"]["all_native_mass_cells"]["total_water"]
    assert change["L1"] > abs(change["signed_total"])
    assert change["max_abs_cell"] > 0
    assert change["max_abs_column"] > 0
    assert result["window"]["observed_endpoint_seconds"] == 60
    assert result["window"]["run_completed_timestamp"] == "2026-08-16_13:01:20"
    assert result["window"]["requested_endpoint_seconds"] == 60
    assert result["window"]["runner_timestep_seconds"] == 20
