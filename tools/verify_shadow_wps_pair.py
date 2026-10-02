#!/usr/bin/env python3
"""Check stored pressure-level WPS values against the matching SHADOW candidate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat

import netCDF4
import numpy as np

from compare_baseline import read_wps
from validate_shadow_diagnostics import validate as validate_shadow


GRAVITY = np.float64(9.80665)
SURFACE = 200100.0
SEA_LEVEL = 201300.0

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
        nx, ny, nz = (len(dataset.dimensions[name]) for name in ("x", "y", "z"))
        assert nx > 0 and ny > 0 and nz > 1
        assert dataset.canonical_vertical_order == "bottom_to_top"
        assert dataset.netcdf_variable_order == "z,y,x"
        assert float(dataset.grid_dx_m) > 0.0
        assert float(dataset.grid_dy_m) > 0.0
        assert int(dataset.diagnostic_schema_version) in (7, 8), (
            "full WPS candidate readback requires the thermo extension"
        )

        surface_boundary_present = "surface_boundary_contract" in dataset.ncattrs()
        pressure_geometry_present = "pressure_geometry_contract" in dataset.ncattrs()
        if surface_boundary_present:
            assert dataset.surface_boundary_contract == SURFACE_BOUNDARY_CONTRACT
        if pressure_geometry_present:
            assert dataset.pressure_geometry_contract == PRESSURE_GEOMETRY_CONTRACT
        candidate_present = "candidate_surface_pressure" in dataset.variables
        candidate_temperature_present = "candidate_surface_temperature" in dataset.variables
        candidate_required = surface_boundary_present or pressure_geometry_present
        if candidate_required:
            assert candidate_present, (
                "surface-pressure contract requires candidate_surface_pressure"
            )
            assert candidate_temperature_present, (
                "surface-boundary contract requires candidate_surface_temperature"
            )

        names = (*MAPPED.values(), "pressure", "above_ground", "surface_pressure")
        if candidate_present:
            names += ("candidate_surface_pressure",)
        if candidate_temperature_present:
            names += ("candidate_surface_temperature",)
        candidate_domain_present = "candidate_above_ground" in dataset.variables
        if candidate_domain_present:
            names += ("candidate_above_ground",)
        def read_array(name: str) -> np.ndarray:
            raw = dataset.variables[name][:]
            if np.ma.isMaskedArray(raw):
                assert not np.any(np.ma.getmaskarray(raw)), f"masked shadow field: {name}"
            return np.asarray(raw)

        values = {name: read_array(name) for name in names}
        assert values["pressure"].shape == (nz,)
        assert values["above_ground"].shape == (nz, ny, nx)
        assert values["surface_pressure"].shape == (ny, nx)
        assert np.all(np.diff(values["pressure"]) < 0.0)
        assert np.all((values["above_ground"] == 0) | (values["above_ground"] == 1))
        candidate_domain = values.get("candidate_above_ground", values["above_ground"])
        assert candidate_domain.shape == (nz, ny, nx)
        assert np.all((candidate_domain == 0) | (candidate_domain == 1))
        assert np.any(candidate_domain)
        for name in MAPPED.values():
            assert values[name].shape == (nz, ny, nx)
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
            assert values["candidate_surface_pressure"].shape == (ny, nx)
            assert getattr(candidate_variable, "units", "") == "Pa"
            assert np.isfinite(values["candidate_surface_pressure"]).all()
            assert np.all(
                (values["candidate_surface_pressure"] >= 100.0)
                & (values["candidate_surface_pressure"] <= 120000.0)
            )
            expected_surface_pressure = values["candidate_surface_pressure"]
        if candidate_temperature_present:
            candidate_temperature_variable = dataset.variables["candidate_surface_temperature"]
            assert candidate_temperature_variable.dimensions == ("y", "x")
            assert np.dtype(candidate_temperature_variable.dtype) == np.dtype(np.float32)
            assert values["candidate_surface_temperature"].shape == (ny, nx)
            assert getattr(candidate_temperature_variable, "units", "") == "K"
            assert int(candidate_temperature_variable.valid_time) == int(dataset.valid_time_epoch)
            assert np.isfinite(values["candidate_surface_temperature"]).all()

        return {
            "pressure": values["pressure"].astype(np.float64),
            "above_ground": values["above_ground"].astype(bool),
            "candidate_above_ground": candidate_domain.astype(bool),
            "surface_pressure": values["surface_pressure"].astype(np.float32),
            "candidate_surface_pressure": (
                values["candidate_surface_pressure"].astype(np.float32)
                if candidate_present else None
            ),
            "expected_surface_pressure": expected_surface_pressure.astype(np.float32),
            "expected_surface_pressure_units": "Pa",
            "expected_surface_temperature": (
                values["candidate_surface_temperature"].astype(np.float32)
                if candidate_temperature_present else None
            ),
            "expected_surface_temperature_units": "K",
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
    above_ground = shadow.get("candidate_above_ground", shadow["above_ground"])
    shape = (above_ground.shape[2], above_ground.shape[1])
    expected_surface_pressure = shadow.get(
        "expected_surface_pressure", shadow["surface_pressure"]
    )
    assert shadow.get("expected_surface_pressure_units", "Pa") == "Pa"
    assert expected_surface_pressure.shape == (shape[1], shape[0])
    assert np.isfinite(expected_surface_pressure).all()
    assert np.all(
        (expected_surface_pressure >= 100.0)
        & (expected_surface_pressure <= 120000.0)
    )
    expected_surface_temperature = shadow.get("expected_surface_temperature")
    if expected_surface_temperature is not None:
        assert shadow.get("expected_surface_temperature_units") == "K"
        assert expected_surface_temperature.shape == (shape[1], shape[0])
        assert np.isfinite(expected_surface_temperature).all()
    hdate = shadow["hdate"]
    baseline_tt = [key[1] for key in baseline if key[0] == "TT"]
    assert baseline_tt[-1] == SURFACE
    pressure_levels = baseline_tt[:-1]
    active_pressure = [float(level) for level, active in zip(pressure, above_ground)
                       if np.any(active)]
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
        if name == "TT" and level == SURFACE and expected_surface_temperature is not None:
            np.testing.assert_array_equal(actual, expected_surface_temperature.T,
                                          err_msg="candidate surface TT mismatch")
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
            # Historical sidecars without a candidate surface field retained
            # baseline surface TT.  Other ancillary/RH slabs remain baseline.
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


PAIR_PRODUCTS = (
    "baseline.wps", "candidate.wps", "candidate.wps.shadow.nc",
)


def validator_source_sha256() -> str:
    digest = hashlib.sha256()
    for source in (Path(__file__), Path(__file__).with_name("compare_baseline.py"),
                   Path(__file__).with_name("validate_shadow_diagnostics.py"),
                   Path(__file__).with_name("pressure_transition_reference.py"),
                   Path(__file__).with_name("pressure_radar_reference.py")):
        payload = source.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def verify_pair(root: Path) -> dict[str, object]:
    """Check one closed pair against its retained WPS baseline."""
    if not __debug__:
        raise ValueError("optimized Python disables pair contract checks")
    baseline = read_wps(root / PAIR_PRODUCTS[0])
    candidate = read_wps(root / PAIR_PRODUCTS[1])
    shadow = read_shadow(root / PAIR_PRODUCTS[2])
    check_records(baseline, candidate, shadow)
    _, failures = validate_shadow(root / PAIR_PRODUCTS[2])
    if failures:
        raise ValueError(f"SHADOW diagnostic failed validation: {failures[0]}")
    return shadow


def verify_snapshot(snapshot: Path) -> dict[str, object]:
    """Return a pair-only semantic receipt for OutputTransaction."""
    if snapshot.is_symlink() or not snapshot.is_dir() or snapshot.parent.name != ".snapshots":
        raise ValueError("pair validation requires a detached transaction snapshot")
    context = json.loads((snapshot / "TRANSACTION.json").read_text(encoding="utf-8"))
    if context.get("products") != list(PAIR_PRODUCTS) or context.get("require_validation") is not True:
        raise ValueError("pair snapshot product declaration is incomplete")
    shadow = verify_pair(snapshot)
    if shadow["hdate"] != _date_from_epoch(context["valid_time"]):
        raise ValueError("pair valid time differs from transaction context")
    records = []
    for product in PAIR_PRODUCTS:
        path = snapshot / product
        status = path.lstat()
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError(f"unsafe pair product: {product}")
        payload = path.read_bytes()
        records.append({"path": product, "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()})
    return {
        "schema": 1,
        "status": "PASS",
        "transaction_id": snapshot.name,
        "snapshot_identity": [snapshot.stat().st_dev, snapshot.stat().st_ino],
        "validator": {
            "name": "verify_shadow_wps_pair",
            "source_sha256": validator_source_sha256(),
        },
        "products": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_snapshot(args.snapshot), sort_keys=True))
    except Exception as error:
        parser.exit(1, f"WPS/SHADOW pair rejected: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
