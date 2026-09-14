#!/usr/bin/env python3
"""Compare live pipeline WPS with its same-run diagnostic, not native state."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps

FIELDS = dict(TT="temperature", UU="u", VV="v", QV="vapor", HGT="geopotential",
              QC="cloud_water", QI="cloud_ice", QR="rain", QS="snow", QG="graupel")
UNITS = {name: "kg kg{-1}" for name in FIELDS}
UNITS.update(TT="K", UU="m s{-1}", VV="m s{-1}", HGT="m", RH="%",
             PSFC="Pa", PMSL="Pa", SKINTEMP="K")
SURFACE = 200100.0


def check_records(original, candidate, data):
    pressure, above, fields, surface_pressure, hdate = data
    assert original.keys() == candidate.keys(), "WPS record identity changed"
    expected_keys = {(name, float(p), hdate) for name in (*FIELDS, "RH")
                     for p in (*pressure, SURFACE)}
    expected_keys.update((name, level, hdate) for name, level in
                         (("PSFC", SURFACE), ("SKINTEMP", SURFACE), ("PMSL", 201300.0)))
    # Legacy SNOWCOVR output is commented out; do not claim serialization.
    assert set(candidate) == expected_keys, "WPS field/level inventory mismatch"
    assert [key[1] for key in candidate if key[0] == "TT"] == [*pressure[::-1], SURFACE]
    changed = {name: False for name in ("TT", "QV", "HGT")}
    for key, (unit, shape, values, metadata) in candidate.items():
        name, level, _ = key
        old_unit, old_shape, old_values, old_metadata = original[key]
        assert unit == old_unit == UNITS[name] and shape == old_shape == above.shape[1:][::-1]
        assert metadata == old_metadata and metadata["wind_grid_relative"] is True
        actual = values.reshape(shape, order="F")
        old = old_values.reshape(shape, order="F")
        assert np.isfinite(actual).all() and np.isfinite(old).all()
        if name in FIELDS and level in pressure:
            k = list(pressure).index(level)
            mask = above[k].T
            expected = fields["candidate_" + FIELDS[name]][k].T
            expected_old = fields["background_" + FIELDS[name]][k].T
            if name == "HGT":
                expected = (expected / 9.80665).astype(np.float32)
                expected_old = (expected_old / 9.80665).astype(np.float32)
            np.testing.assert_array_equal(old[mask], expected_old[mask])
            np.testing.assert_array_equal(actual, np.where(mask, expected, old))
            if name in changed:
                changed[name] |= bool(np.any(actual != old))
        else:
            np.testing.assert_array_equal(actual, old, err_msg=f"retained record changed: {key}")
            if name == "PSFC":
                np.testing.assert_array_equal(actual, surface_pressure.T)
    assert all(changed.values()), f"missing live physical response: {changed}"


def check(root):
    original = read_wps(root / "pipeline_pressure_background.wps")
    candidate = read_wps(root / "pipeline_pressure_candidate.wps")
    # Runner separately applies the existing independent physics verifier.
    with netCDF4.Dataset(root / "pipeline_pressure_candidate.nc") as ds:
        assert ds.diagnostic_schema_version == 7
        assert ds.pressure_geopotential_contract == "pressure_hydrostatic_increment_v1"
        pressure = np.asarray(ds["pressure"][:], dtype=np.float64)
        assert np.all(np.diff(pressure) < 0)
        above = np.asarray(ds["above_ground"][:], dtype=bool)
        fields = {state + "_" + field: np.asarray(ds[state + "_" + field][:], dtype=np.float64)
                  for state in ("background", "candidate") for field in FIELDS.values()}
        surface_pressure = np.asarray(ds["surface_pressure"][:])
        hdate = datetime.fromtimestamp(int(ds.valid_time_epoch), timezone.utc).strftime("%Y-%m-%d_%H:%M:%S.0000")
    data = pressure, above, fields, surface_pressure, hdate
    check_records(original, candidate, data)

    mutations = [deepcopy(original)]
    for name in ("QV", "QC"):
        bad = deepcopy(candidate)
        bad[(name, float(pressure[-1]), hdate)][2][0] += 0.001
        mutations.append(bad)
    bad = deepcopy(candidate)
    bad.pop(next(iter(bad)))
    mutations.append(bad)
    bad = deepcopy(candidate)
    key = next(iter(bad))
    bad[(key[0], key[1], "1900-01-01_00:00:00.0000")] = bad.pop(key)
    mutations.append(bad)
    bad = deepcopy(candidate)
    next(iter(bad.values()))[3]["wind_grid_relative"] = False
    mutations.append(bad)
    bad = deepcopy(candidate)
    bad[("UU", SURFACE, hdate)][2][0] += 1.0
    mutations.append(bad)
    for bad in mutations:
        try:
            check_records(original, bad, data)
        except AssertionError:
            continue
        raise AssertionError("WPS checker accepted a corrupted candidate")
    print("PASS live pipeline to WPS: same-run values, units, levels, retained records and 7 mutations")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
