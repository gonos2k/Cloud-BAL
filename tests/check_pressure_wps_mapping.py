#!/usr/bin/env python3
"""Independent WPS record check for the pressure-candidate mapping fixture."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


def check(root: Path) -> None:
    original = read_wps(root / "pressure_background.wps")
    candidate = read_wps(root / "pressure_candidate.wps")
    descending = read_wps(root / "pressure_descending.wps")
    default_outputs = {
        "pressure_background.wps": original,
        "pressure_candidate.wps": candidate,
        "pressure_descending.wps": descending,
    }
    full = read_wps(root / "pressure_full22.wps")
    reverse = read_wps(root / "pressure_full22_descending.wps")
    default_outputs.update({
        "pressure_full22.wps": full,
        "pressure_full22_descending.wps": reverse,
    })
    for name, fields in default_outputs.items():
        assert not any(key[0] == "SOILHGT" for key in fields), (
            f"legacy output unexpectedly contains SOILHGT: {name}"
        )

    assert original.keys() == candidate.keys(), "lost or invented WPS records"
    assert descending.keys() == candidate.keys(), "order-dependent record inventory"
    for key, item in candidate.items():
        other = descending[key]
        assert item[:2] == other[:2] and item[3] == other[3]
        np.testing.assert_array_equal(item[2], other[2], err_msg=f"order-dependent slab: {key}")
    assert [key[1] for key in candidate if key[0] == "TT"] == [65000,80000,95000,200100]
    assert [key[1] for key in descending if key[0] == "TT"] == [95000,80000,65000,200100]
    levels = {95000.0: 1, 80000.0: 2, 65000.0: 3}
    units = {"TT": "K", "UU": "m s{-1}", "VV": "m s{-1}", "HGT": "m"}
    units.update({name: "kg kg{-1}" for name in ("QV", "QC", "QI", "QR", "QS", "QG")})
    for name in units:
        assert {key[1] for key in candidate if key[0] == name} == set(levels) | {200100.0}

    i, j = np.indices((3, 2), dtype=np.float64) + 1
    for key, (unit, shape, values, metadata) in candidate.items():
        name, level, valid_time = key
        old_unit, old_shape, old_values, old_metadata = original[key]
        assert unit == old_unit and shape == old_shape == (3, 2)
        assert metadata == old_metadata and metadata["wind_grid_relative"] is True
        assert valid_time == "2026-09-01_03:32:00.0000"
        actual = values.reshape(shape, order="F")
        expected = old_values.reshape(shape, order="F").copy()
        if name in units:
            assert unit == units[name], (name, unit)
        if level in levels and name in units:
            k = levels[level]
            formula = {
                "TT": 275 + 13*i + 7*j + 5*k,
                "UU": 21 + 2*i + 3*j + 0.4*k,
                "VV": -16 + i - 2*j + 0.8*k,
                "HGT": ((500 + 31*i + 19*j + 29*k).astype(np.float32).astype(np.float64)
                        / 9.80665).astype(np.float32),
                "QV": .006 + .0004*i + .0007*j + .0009*k,
                "QC": .00110 + .00011*i + .00012*j + .00013*k,
                "QI": .00120 + .00011*i + .00012*j + .00014*k,
                "QR": .00130 + .00011*i + .00013*j + .00012*k,
                "QS": .00140 + .00012*i + .00011*j + .00013*k,
                "QG": .00150 + .00013*i + .00012*j + .00011*k,
            }[name]
            above = np.ones(shape, dtype=bool)
            if k == 1:
                above[1, 0] = False
            expected[above] = formula[above]
            assert np.array_equal(actual[~above], expected[~above]), "changed subterranean fill"
        elif name == "TT" and level == 200100.0:
            expected[:] = 279
            expected[0, 0] = 283
        elif name == "PSFC":
            expected[:] = 100700
            expected[1, 0] = 90000
        else:
            # Includes ancillary RH, explicit surface vapor/wind/height,
            # separate skin temperature/SLP and writer-owned surface species.
            assert np.array_equal(actual, expected), ("changed retained field", key)
        np.testing.assert_allclose(actual, expected, rtol=5e-7, atol=1e-12,
                                   err_msg=f"wrong mapped WPS values: {key}")
    assert full.keys() == reverse.keys()
    levels22 = list(range(5000, 100001, 5000))
    assert [key[1] for key in full if key[0] == "TT"] == levels22 + [200100]
    assert [key[1] for key in reverse if key[0] == "TT"] == levels22[::-1] + [200100]
    for key, (unit, shape, values, metadata) in full.items():
        assert key[1] not in (105000, 110000), "writer emitted a skipped level"
        assert shape == (2, 1) and metadata["wind_grid_relative"] is True
        assert key[2] == "2026-09-01_03:32:00.0000"
        np.testing.assert_array_equal(values, reverse[key][2])
        assert (unit, shape, metadata) == (reverse[key][0], reverse[key][1], reverse[key][3])
        if key[0] in units:
            assert unit == units[key[0]]
        if key[1] in levels22 and key[0] in units:
            k = 23 - key[1] / 5000
            expected = {"TT": 270 + k, "HGT": np.float32(1000*k / 9.80665),
                        "UU": 5, "VV": -2, "QV": np.float32(.002),
                        "QC": 0, "QI": 0, "QR": 0, "QS": 0, "QG": 0}[key[0]]
            np.testing.assert_array_equal(values, np.full(values.shape, expected))
    for name in units:
        assert {key[1] for key in full if key[0] == name} == set(levels22) | {200100}

    surface = read_wps(root / "pressure_surface_height.wps")
    soil_keys = [key for key in surface if key[0] == "SOILHGT"]
    assert soil_keys == [("SOILHGT", 200100.0, "2026-09-01_03:32:00.0000")]
    soil_unit, soil_shape, soil_values, soil_metadata = surface[soil_keys[0]]
    assert soil_unit == "m" and soil_shape == (3, 2)
    assert soil_metadata["wind_grid_relative"] is True
    actual_soil = soil_values.reshape(soil_shape, order="F")
    i, j = np.indices(soil_shape, dtype=np.float32)
    expected_soil = 100.0 + 10.0 * (i + 1.0) + (j + 1.0)
    np.testing.assert_array_equal(actual_soil, expected_soil, err_msg="wrong SOILHGT values")
    hgt_key = ("HGT", 200100.0, "2026-09-01_03:32:00.0000")
    np.testing.assert_array_equal(soil_values, surface[hgt_key][2], err_msg="SOILHGT differs from surface HGT")

    print("PASS pressure-candidate WPS values, full 22-level selection, and opt-in SOILHGT")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
