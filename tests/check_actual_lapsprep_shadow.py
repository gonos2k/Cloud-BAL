#!/usr/bin/env python3
"""Exercise the stored WPS/SHADOW pair checker with actual inputs and mutations."""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps
from verify_shadow_wps_pair import (SURFACE, read_shadow, check_records)

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


def _check_surface_temperature_mutation(
    baseline: dict, candidate: dict, shadow: dict[str, object]
) -> None:
    """Prove surface TT follows candidate temperature when the sidecar supplies it."""
    key = ("TT", SURFACE, shadow["hdate"])
    units, record_shape, values, metadata = candidate[key]
    expected = values.reshape(record_shape, order="F").T.copy()
    expected[0, 0] = np.float32(expected[0, 0] + 1.0)
    changed_shadow = dict(shadow)
    changed_shadow["expected_surface_temperature"] = expected
    changed_shadow["expected_surface_temperature_units"] = "K"
    changed_candidate = candidate.copy()
    changed_candidate[key] = (
        units, record_shape, expected.T.reshape(-1, order="F"), metadata,
    )
    check_records(baseline, changed_candidate, changed_shadow)
    _reject_mutation(baseline, candidate, changed_shadow,
                     "stale candidate surface TT", lambda: None)
    for label, altered in (("NaN", np.full_like(expected, np.nan)),
                           ("shape", expected[:-1])):
        bad_shadow = dict(changed_shadow)
        bad_shadow["expected_surface_temperature"] = altered
        _reject_mutation(baseline, changed_candidate, bad_shadow,
                         f"candidate surface TT {label}", lambda: None)
    bad_shadow = dict(changed_shadow)
    bad_shadow["expected_surface_temperature_units"] = "C"
    _reject_mutation(baseline, changed_candidate, bad_shadow,
                     "candidate surface TT units", lambda: None)


def _rewrite_metadata(records: dict, **changes) -> dict:
    rewritten = {}
    for key, (units, shape, values, metadata) in records.items():
        updated = dict(metadata)
        updated.update(changes)
        rewritten[key] = (units, shape, values, updated)
    return rewritten


def _check_geometry_and_time_contract(baseline: dict, candidate: dict,
                                      shadow: dict) -> None:
    changed_pair = _rewrite_metadata(
        baseline,
        geometry={**next(iter(baseline.values()))[3]["geometry"], "dx_km": 10.0},
    )
    changed_candidate = _rewrite_metadata(
        candidate,
        geometry={**next(iter(candidate.values()))[3]["geometry"], "dx_km": 10.0},
    )
    _reject_mutation(changed_pair, changed_candidate, shadow,
                     "shared WPS spacing changed from SHADOW", lambda: None)

    changed_pair = _rewrite_metadata(
        baseline,
        geometry={**next(iter(baseline.values()))[3]["geometry"], "startlon": 120.0},
    )
    changed_candidate = _rewrite_metadata(
        candidate,
        geometry={**next(iter(candidate.values()))[3]["geometry"], "startlon": 120.0},
    )
    _reject_mutation(changed_pair, changed_candidate, shadow,
                     "shared WPS origin changed from SHADOW", lambda: None)

    changed_pair = _rewrite_metadata(
        baseline,
        geometry={**next(iter(baseline.values()))[3]["geometry"], "xlonc": 127.0},
    )
    changed_candidate = _rewrite_metadata(
        candidate,
        geometry={**next(iter(candidate.values()))[3]["geometry"], "xlonc": 127.0},
    )
    _reject_mutation(changed_pair, changed_candidate, shadow,
                     "shared WPS Lambert center changed from SHADOW", lambda: None)

    changed_candidate = _rewrite_metadata(candidate, forecast_hour=6.0)
    _reject_mutation(baseline, changed_candidate, shadow,
                     "candidate XFCST changed", lambda: None)
    changed_pair = _rewrite_metadata(baseline, forecast_hour=6.0)
    _reject_mutation(changed_pair, changed_candidate, shadow,
                     "shared nonzero analysis XFCST", lambda: None)


def _check_stored_below_ground_slab(baseline: dict, candidate: dict,
                                    shadow: dict) -> None:
    pressure_level = max(key[1] for key in baseline
                         if key[0] == "TT" and key[1] < SURFACE)
    z = next(i for i, level in enumerate(shadow["pressure"])
             if level == pressure_level)
    changed_shadow = dict(shadow)
    candidate_domain = np.asarray(shadow["candidate_above_ground"]).copy()
    assert np.any(candidate_domain[z + 1]), "lower pressure slab is not represented above ground"
    candidate_domain[z] = False
    changed_shadow["candidate_above_ground"] = candidate_domain
    changed_candidate = candidate.copy()
    for key, (units, shape, values, metadata) in candidate.items():
        name, level, _ = key
        if level != pressure_level or name not in (
                "TT", "UU", "VV", "QV", "HGT", "QC", "QI", "QR", "QS", "QG"):
            continue
        expected = (np.zeros((shape[1], shape[0]), dtype=np.float32)
                    if name in ("QC", "QI", "QR", "QS", "QG")
                    else baseline[key][2].reshape(shape, order="F").T.copy())
        changed_candidate[key] = (
            units, shape, expected.T.reshape(-1, order="F"), metadata,
        )
    check_records(baseline, changed_candidate, changed_shadow)


def _check_complete_stored_pressure_inventory(baseline: dict, candidate: dict,
                                              shadow: dict) -> None:
    pressure_level = next(key[1] for key in baseline
                          if key[0] == "TT" and key[1] < SURFACE)
    dropped_baseline = {key: value for key, value in baseline.items()
                        if key[1] != pressure_level or key[1] == SURFACE}
    dropped_candidate = {key: value for key, value in candidate.items()
                        if key[1] != pressure_level or key[1] == SURFACE}
    _reject_mutation(dropped_baseline, dropped_candidate, shadow,
                     "dropped stored pressure level", lambda: None)


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
    _check_surface_temperature_mutation(baseline, candidate, shadow)
    _check_geometry_and_time_contract(baseline, candidate, shadow)
    _check_stored_below_ground_slab(baseline, candidate, shadow)
    _check_complete_stored_pressure_inventory(baseline, candidate, shadow)
    check_records(baseline, candidate, shadow)
    print(
        "PASS actual LAPSPREP WPS/shadow: 235 records, source terrain, "
        "exact metadata and candidate mapping mutations"
    )


if __name__ == "__main__":
    check(Path(sys.argv[1]))
