#!/usr/bin/env python3
"""Independently check the actual LAPSPREP candidate WPS/shadow pair."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


GRAVITY = np.float64(9.80665)
SURFACE = 200100.0
SEA_LEVEL = 201300.0
ACTIVE_LIMIT = 100100.0

UNITS = {
    "TT": "K",
    "UU": "m s{-1}",
    "VV": "m s{-1}",
    "RH": "%",
    "QV": "kg kg{-1}",
    "HGT": "m",
    "SOILHGT": "m",
    "QC": "kg kg{-1}",
    "QI": "kg kg{-1}",
    "QR": "kg kg{-1}",
    "QS": "kg kg{-1}",
    "QG": "kg kg{-1}",
    "SKINTEMP": "K",
    "PMSL": "Pa",
    "PSFC": "Pa",
}

MAPPED = {
    "TT": "candidate_temperature",
    "UU": "candidate_u",
    "VV": "candidate_v",
    "QV": "candidate_vapor",
    "HGT": "candidate_geopotential",
    "QC": "candidate_cloud_water",
    "QI": "candidate_cloud_ice",
    "QR": "candidate_rain",
    "QS": "candidate_snow",
    "QG": "candidate_graupel",
}
HYDROMETEORS = ("QC", "QI", "QR", "QS", "QG")
BASE_PRESSURE_FIELDS = ("TT", "UU", "VV", "RH", "QV", "HGT")
SURFACE_BOUNDARY_CONTRACT = "CANONICAL_SURFACE_BOUNDARY_V1"
PRESSURE_GEOMETRY_CONTRACT = "prescribed_surface_pressure_v1"


def _date_from_epoch(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime(
        "%Y-%m-%d_%H:%M:%S.0000"
    )


def read_shadow(path: Path) -> dict[str, object]:
    """Read only the sidecar fields needed for the WPS mapping contract."""
    with netCDF4.Dataset(path) as dataset:
        assert {name: len(dataset.dimensions[name]) for name in ("x", "y", "z")} == {
            "x": 235,
            "y": 283,
            "z": 22,
        }, "shadow grid dimensions changed"
        assert dataset.grid_id == "NE57_LAPS_PRESSURE"
        assert dataset.canonical_vertical_order == "bottom_to_top"
        assert dataset.netcdf_variable_order == "z,y,x"
        assert float(dataset.grid_dx_m) == 5000.0
        assert float(dataset.grid_dy_m) == 5000.0

        surface_boundary_present = "surface_boundary_contract" in dataset.ncattrs()
        pressure_geometry_present = "pressure_geometry_contract" in dataset.ncattrs()
        if surface_boundary_present:
            assert dataset.surface_boundary_contract == SURFACE_BOUNDARY_CONTRACT
        if pressure_geometry_present:
            assert dataset.pressure_geometry_contract == PRESSURE_GEOMETRY_CONTRACT
        candidate_present = "candidate_surface_pressure" in dataset.variables
        candidate_required = surface_boundary_present or pressure_geometry_present
        if candidate_required:
            assert candidate_present, (
                "surface-pressure contract requires candidate_surface_pressure"
            )

        names = (*MAPPED.values(), "pressure", "above_ground", "surface_pressure")
        if candidate_present:
            names += ("candidate_surface_pressure",)
        def read_array(name: str) -> np.ndarray:
            raw = dataset.variables[name][:]
            if np.ma.isMaskedArray(raw):
                assert not np.any(np.ma.getmaskarray(raw)), f"masked shadow field: {name}"
            return np.asarray(raw)

        values = {name: read_array(name) for name in names}
        assert values["pressure"].shape == (22,)
        assert values["above_ground"].shape == (22, 283, 235)
        assert values["surface_pressure"].shape == (283, 235)
        assert np.array_equal(
            values["pressure"], np.arange(110000.0, 4999.0, -5000.0, dtype=np.float32)
        )
        assert np.all((values["above_ground"] == 0) | (values["above_ground"] == 1))
        assert not np.any(values["above_ground"][:2])
        assert np.any(values["above_ground"][2:])
        for name in MAPPED.values():
            assert values[name].shape == (22, 283, 235)
            assert np.isfinite(values[name]).all()
        assert np.isfinite(values["surface_pressure"]).all()
        assert np.all(
            (values["surface_pressure"] >= 100.0)
            & (values["surface_pressure"] <= 120000.0)
        )
        sidecar_units = {
            "candidate_temperature": "K",
            "candidate_u": "m s-1",
            "candidate_v": "m s-1",
            "candidate_vapor": "kg kg-1 dryair",
            "candidate_geopotential": "m2 s-2",
            "candidate_cloud_water": "kg kg-1 dryair",
            "candidate_cloud_ice": "kg kg-1 dryair",
            "candidate_rain": "kg kg-1 dryair",
            "candidate_snow": "kg kg-1 dryair",
            "candidate_graupel": "kg kg-1 dryair",
        }
        for name, unit in sidecar_units.items():
            assert dataset.variables[name].units == unit
        surface_pressure_variable = dataset.variables["surface_pressure"]
        assert getattr(surface_pressure_variable, "units", "") == "Pa"

        expected_surface_pressure = values["surface_pressure"]
        if candidate_present:
            candidate_variable = dataset.variables["candidate_surface_pressure"]
            assert candidate_variable.dimensions == ("y", "x")
            assert np.dtype(candidate_variable.dtype) == np.dtype(np.float32)
            assert values["candidate_surface_pressure"].shape == (283, 235)
            assert getattr(candidate_variable, "units", "") == "Pa"
            assert np.isfinite(values["candidate_surface_pressure"]).all()
            assert np.all(
                (values["candidate_surface_pressure"] >= 100.0)
                & (values["candidate_surface_pressure"] <= 120000.0)
            )
            expected_surface_pressure = values["candidate_surface_pressure"]

        return {
            "pressure": values["pressure"].astype(np.float64),
            "above_ground": values["above_ground"].astype(bool),
            "surface_pressure": values["surface_pressure"].astype(np.float32),
            "candidate_surface_pressure": (
                values["candidate_surface_pressure"].astype(np.float32)
                if candidate_present else None
            ),
            "expected_surface_pressure": expected_surface_pressure.astype(np.float32),
            "expected_surface_pressure_units": "Pa",
            "fields": values,
            "hdate": _date_from_epoch(int(dataset.valid_time_epoch)),
        }


def _inventory(names: tuple[str, ...], pressure_levels: list[float], hdate: str):
    keys = {(name, level, hdate) for name in names for level in pressure_levels}
    keys.update((name, SURFACE, hdate) for name in names)
    return keys


def check_records(
    baseline: dict,
    candidate: dict,
    shadow: dict[str, object],
) -> None:
    """Check records and values without using the production mapper."""
    fields = shadow["fields"]
    pressure = shadow["pressure"]
    above_ground = shadow["above_ground"]
    expected_surface_pressure = shadow.get(
        "expected_surface_pressure", shadow["surface_pressure"]
    )
    assert shadow.get("expected_surface_pressure_units", "Pa") == "Pa"
    assert expected_surface_pressure.shape == (283, 235)
    assert np.isfinite(expected_surface_pressure).all()
    assert np.all(
        (expected_surface_pressure >= 100.0)
        & (expected_surface_pressure <= 120000.0)
    )
    hdate = shadow["hdate"]
    baseline_tt = [key[1] for key in baseline if key[0] == "TT"]
    assert baseline_tt[-1] == SURFACE
    pressure_levels = baseline_tt[:-1]
    active_pressure = [float(level) for level in pressure if level <= ACTIVE_LIMIT]
    assert pressure_levels == sorted(pressure_levels)
    assert set(pressure_levels) == set(active_pressure)

    expected_baseline = _inventory((*BASE_PRESSURE_FIELDS,), pressure_levels, hdate)
    expected_baseline.update(
        {("SKINTEMP", SURFACE, hdate), ("PMSL", SEA_LEVEL, hdate), ("PSFC", SURFACE, hdate)}
    )
    expected_candidate = set(expected_baseline)
    expected_candidate.update(_inventory(HYDROMETEORS, pressure_levels, hdate))
    expected_candidate.add(("SOILHGT", SURFACE, hdate))
    assert set(baseline) == expected_baseline, "baseline WPS inventory changed"
    assert set(candidate) == expected_candidate, "candidate WPS inventory changed"
    assert not any(key[0] in HYDROMETEORS for key in baseline)

    shape = (235, 283)
    metadata = next(iter(baseline.values()))[3]
    assert metadata["wind_grid_relative"] is True
    for records in (baseline, candidate):
        for key, (units, record_shape, values, record_metadata) in records.items():
            name, level, date = key
            assert units == UNITS[name], f"unexpected units for {key}"
            assert record_shape == shape, f"unexpected grid shape for {key}"
            assert date == hdate, f"unexpected valid time for {key}"
            assert record_metadata == metadata, f"grid metadata changed for {key}"
            assert np.isfinite(values).all(), f"non-finite WPS values for {key}"

    # The writer emits fields in its ascending legacy order.  The sidecar is
    # canonical bottom-to-top (descending pressure), so match by pressure value.
    pressure_index = {float(level): index for index, level in enumerate(pressure)}
    for key, (_, record_shape, values, _) in candidate.items():
        name, level, _ = key
        actual = values.reshape(record_shape, order="F")
        if name == "SOILHGT":
            np.testing.assert_array_equal(
                actual,
                baseline[("HGT", SURFACE, hdate)][2].reshape(shape, order="F"),
            )
            continue
        if name == "PSFC":
            np.testing.assert_array_equal(actual, expected_surface_pressure.T)
            continue
        if name in HYDROMETEORS:
            if level == SURFACE:
                expected = np.zeros(shape, dtype=np.float32)
            else:
                z = pressure_index[level]
                expected = np.where(above_ground[z].T, fields[MAPPED[name]][z].T, 0.0)
            np.testing.assert_array_equal(actual, expected, err_msg=f"hydrometeor mismatch: {key}")
            continue
        if level == SURFACE or level == SEA_LEVEL or name in ("RH", "SKINTEMP", "PMSL"):
            # Surface TT is candidate-owned by the mapper, but the diagnostic
            # intentionally has no 2-D surface-temperature field.  The actual
            # run retains the baseline value; all other ancillary/RH slabs are
            # required to remain baseline byte-for-byte.
            np.testing.assert_array_equal(actual, baseline[key][2].reshape(shape, order="F"),
                                          err_msg=f"retained record changed: {key}")
            continue
        z = pressure_index[level]
        expected = fields[MAPPED[name]][z].T
        if name == "HGT":
            expected = np.asarray(
                np.asarray(fields[MAPPED[name]][z], dtype=np.float64) / GRAVITY,
                dtype=np.float32,
            ).T
        mask = above_ground[z].T
        retained = baseline[key][2].reshape(shape, order="F")
        np.testing.assert_array_equal(actual, np.where(mask, expected, retained),
                                      err_msg=f"candidate mapping mismatch: {key}")


def _reject_mutation(baseline: dict, candidate: dict, shadow: dict, label: str, mutate) -> None:
    mutate()
    try:
        check_records(baseline, candidate, shadow)
    except AssertionError:
        return
    raise AssertionError(f"checker accepted {label} mutation")


def _check_surface_pressure_mutation(
    baseline: dict, candidate: dict, shadow: dict[str, object]
) -> None:
    """Prove PSFC follows a changed candidate field, not stale background PS."""
    hdate = shadow["hdate"]
    psfc_key = ("PSFC", SURFACE, hdate)
    expected = np.asarray(shadow["expected_surface_pressure"], dtype=np.float32).copy()
    background = np.asarray(shadow["surface_pressure"], dtype=np.float32)
    original = expected[0, 0]
    for delta in (1.0, -1.0):
        proposed = np.float32(original + delta)
        if 100.0 <= proposed <= 120000.0 and proposed != background[0, 0]:
            expected[0, 0] = proposed
            break
    else:
        raise AssertionError("unable to construct a nonzero candidate PSFC mutation")
    assert 100.0 <= expected[0, 0] <= 120000.0
    assert expected[0, 0] != background[0, 0]

    changed_shadow = dict(shadow)
    changed_shadow["expected_surface_pressure"] = expected
    changed_shadow["candidate_surface_pressure"] = expected
    units, record_shape, _, metadata = candidate[psfc_key]
    candidate_psfc = candidate.copy()
    candidate_psfc[psfc_key] = (
        units,
        record_shape,
        expected.T.reshape(-1, order="F"),
        metadata,
    )
    check_records(baseline, candidate_psfc, changed_shadow)

    stale_candidate = candidate.copy()
    stale_candidate[psfc_key] = (
        units,
        record_shape,
        baseline[psfc_key][2].copy(),
        metadata,
    )
    _reject_mutation(
        baseline,
        stale_candidate,
        changed_shadow,
        "stale background PSFC",
        lambda: None,
    )

    bad_shadow = dict(shadow)
    bad_expected = expected.copy()
    bad_expected[0, 0] = np.nan
    bad_shadow["expected_surface_pressure"] = bad_expected
    _reject_mutation(baseline, candidate, bad_shadow, "NaN candidate PSFC", lambda: None)

    bad_shadow = dict(shadow)
    bad_shadow["expected_surface_pressure"] = expected[:-1]
    _reject_mutation(baseline, candidate, bad_shadow, "candidate PSFC shape", lambda: None)

    bad_shadow = dict(shadow)
    bad_shadow["expected_surface_pressure_units"] = "hPa"
    _reject_mutation(baseline, candidate, bad_shadow, "candidate PSFC units", lambda: None)


def check(root: Path) -> None:
    baseline = read_wps(root / "baseline.wps")
    candidate = read_wps(root / "candidate.wps")
    shadow = read_shadow(root / "candidate.wps.shadow.nc")
    check_records(baseline, candidate, shadow)

    hdate = shadow["hdate"]
    pressure_level = next(key[1] for key in candidate if key[0] == "TT" and key[1] < SURFACE)
    z = next(i for i, level in enumerate(shadow["pressure"]) if level == pressure_level)
    cell = tuple(np.argwhere(shadow["above_ground"][z])[0])
    value_key = ("TT", pressure_level, hdate)
    raw_index = cell[1] + cell[0] * candidate[value_key][1][0]
    old_value = candidate[value_key][2][raw_index]

    def mutate_value() -> None:
        candidate[value_key][2][raw_index] += 1.0

    _reject_mutation(baseline, candidate, shadow, "value", mutate_value)
    candidate[value_key][2][raw_index] = old_value

    level_key = ("TT", pressure_level, hdate)
    moved = candidate.pop(level_key)
    candidate[("TT", pressure_level - 1.0, hdate)] = moved
    _reject_mutation(baseline, candidate, shadow, "level", lambda: None)
    candidate.pop(("TT", pressure_level - 1.0, hdate))
    candidate[level_key] = moved

    rh_key = next(key for key in candidate if key[0] == "RH")
    old_rh = candidate[rh_key][2][0]

    def mutate_rh() -> None:
        candidate[rh_key][2][0] += 1.0

    _reject_mutation(baseline, candidate, shadow, "retained RH", mutate_rh)
    candidate[rh_key][2][0] = old_rh
    terrain_key = ("SOILHGT", SURFACE, hdate)
    terrain_record = candidate.pop(terrain_key)
    _reject_mutation(baseline, candidate, shadow, "missing source terrain", lambda: None)
    candidate[terrain_key] = terrain_record
    old_terrain = terrain_record[2][0]
    terrain_record[2][0] += 1.0
    _reject_mutation(baseline, candidate, shadow, "source terrain value", lambda: None)
    terrain_record[2][0] = old_terrain
    _check_surface_pressure_mutation(baseline, candidate, shadow)
    check_records(baseline, candidate, shadow)
    print(
        "PASS actual LAPSPREP WPS/shadow: 235 records, source terrain, "
        "exact metadata, sidecar mapping, 9 mutations"
    )


if __name__ == "__main__":
    check(Path(sys.argv[1]))
