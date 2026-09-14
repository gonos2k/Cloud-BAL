#!/usr/bin/env python3
"""Validate fields produced by the actual lapsprep caller fixture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
from compare_baseline import read_wps  # noqa: E402


R_DRY = 287.1
EPSILON = 0.622
HOTSTART_LEVELS = (50000.0, 40000.0, 30000.0)
HOTSTART_SPECIFIC_HUMIDITY = (0.12, 0.14, 0.16)
HOTSTART_CONCENTRATIONS = {
    "QC": (0.010, 0.012, 0.014),
    "QR": (0.020, 0.022, 0.024),
    "QS": (0.030, 0.032, 0.034),
    "QI": (0.040, 0.042, 0.044),
    "QG": (0.050, 0.052, 0.054),
}

OFF_REQUIRED_FIELDS = {
    "TT", "UU", "VV", "RH", "QV", "HGT", "QC", "QI", "QR", "QS", "QG",
    "SKINTEMP", "PMSL", "PSFC", "SOILHGT",
}
OFF_HYDROMETEORS = ("QC", "QI", "QR", "QS", "QG")
OFF_BACKGROUND_FIELDS = {
    "TT": "background_temperature",
    "UU": "background_u",
    "VV": "background_v",
    "QV": "background_vapor",
    "HGT": "background_geopotential",
    "QC": "background_cloud_water",
    "QI": "background_cloud_ice",
    "QR": "background_rain",
    "QS": "background_snow",
    "QG": "background_graupel",
}
GRAVITY = 9.80665
SURFACE_LEVEL = 200100.0


def fields(path: Path) -> dict[tuple[str, float], tuple[str, np.ndarray, str]]:
    parsed = read_wps(path)
    return {
        (field, level): (units, slab, hdate)
        for (field, level, hdate), (units, _shape, slab, _metadata) in parsed.items()
    }


def check_default(path: Path) -> None:
    output = fields(path)
    if any(field == "QV" for field, _ in output):
        raise AssertionError("default namelist unexpectedly emitted QV")
    if not any(field == "RH" for field, _ in output):
        raise AssertionError("default output lost legacy RH")


def check_vapor(path: Path) -> None:
    output = fields(path)
    qv = {level: values for (field, level), values in output.items() if field == "QV"}
    expected_levels = {50000.0, 40000.0, 30000.0, 200100.0}
    if set(qv) != expected_levels:
        raise AssertionError(f"QV levels {sorted(qv)} != {sorted(expected_levels)}")

    for level, specific_humidity in zip((50000.0, 40000.0, 30000.0), (0.001, 0.002, 0.003)):
        units, values, hdate = output[("QV", level)]
        expected = np.float32(specific_humidity / (1.0 - specific_humidity))
        if units != "kg kg{-1}" or hdate != "2026-01-01_03:00:00.0000":
            raise AssertionError(f"QV metadata changed at {level}: {units!r}, {hdate!r}")
        if not np.allclose(values, expected, rtol=0.0, atol=2.0e-8):
            raise AssertionError(f"SH/(1-SH) conversion failed at {level}: {values}")

    units, surface_values, _ = output[("QV", 200100.0)]
    if units != "kg kg{-1}" or not np.allclose(surface_values, 0.008, rtol=0.0, atol=1.0e-7):
        raise AssertionError(f"surface g/kg conversion failed: {surface_values}")
    if not np.allclose(output[("TT", 50000.0)][1], 280.0, rtol=0.0, atol=1.0e-6):
        raise AssertionError("temperature field was not retained")
    if not any(field == "RH" for field, _ in output):
        raise AssertionError("QV output lost legacy RH")


def check_hotstart_vapor(path: Path) -> None:
    output = fields(path)
    expected_levels = {*HOTSTART_LEVELS, 200100.0}
    qv = {level: values for (field, level), values in output.items() if field == "QV"}
    if set(qv) != expected_levels:
        raise AssertionError(f"hotstart QV levels {sorted(qv)} != {sorted(expected_levels)}")

    for level, specific_humidity in zip(HOTSTART_LEVELS, HOTSTART_SPECIFIC_HUMIDITY):
        units, values, hdate = output[("QV", level)]
        expected = specific_humidity / (1.0 - specific_humidity)
        if units != "kg kg{-1}" or hdate != "2026-01-01_03:00:00.0000":
            raise AssertionError(f"hotstart QV metadata changed at {level}: {units!r}, {hdate!r}")
        if not np.allclose(values, expected, rtol=0.0, atol=2.0e-7):
            raise AssertionError(f"hotstart QV conversion failed at {level}: {values}")

    units, surface_values, _ = output[("QV", 200100.0)]
    if units != "kg kg{-1}" or not np.allclose(surface_values, 0.08, rtol=0.0, atol=2.0e-7):
        raise AssertionError(f"hotstart surface vapor conversion failed: {surface_values}")

    for level in HOTSTART_LEVELS:
        if not np.allclose(output[("TT", level)][1], 280.0, rtol=0.0, atol=1.0e-6):
            raise AssertionError(f"temperature field was not retained at {level}")

    # The expected values are independent of the implementation: concentrations
    # are divided by dry-air density with the host lapsprep constants.
    for field, concentrations in HOTSTART_CONCENTRATIONS.items():
        for level, specific_humidity, concentration in zip(
            HOTSTART_LEVELS, HOTSTART_SPECIFIC_HUMIDITY, concentrations
        ):
            vapor_mixing_ratio = specific_humidity / (1.0 - specific_humidity)
            dry_density = level / (R_DRY * 280.0 * (1.0 + vapor_mixing_ratio / EPSILON))
            expected = concentration / dry_density
            units, values, _ = output[(field, level)]
            if units != "kg kg{-1}" or not np.allclose(values, expected, rtol=2.0e-6, atol=2.0e-8):
                raise AssertionError(
                    f"{field} dry-air concentration conversion failed at {level}: "
                    f"{values}, expected {expected}"
                )
            if np.any(values <= 0.0):
                raise AssertionError(f"{field} unexpectedly lost its nonzero concentration at {level}")

            # Guard the regression against the previous approximate moist-gas
            # denominator, which must not accidentally satisfy this fixture.
            approximate_density = level / (R_DRY * 280.0 * (1.0 + 0.61 * vapor_mixing_ratio))
            old_expected = concentration / approximate_density
            if np.allclose(values, old_expected, rtol=1.0e-5, atol=1.0e-7):
                raise AssertionError(
                    f"{field} at {level} still matches the approximate moist-gas denominator"
                )

    if not any(field == "RH" for field, _ in output):
        raise AssertionError("hotstart QV output lost legacy RH")


def check_off(path: Path, reference: Path | None = None) -> None:
    """Historical canonical-inventory checker for pre-host-identity OFF artifacts.

    This explicit legacy mode is not the current OFF contract. Current cold
    ordinary/OFF equality is tested by test_lapsprep_off.py.

    OFF deliberately has no diagnostic NetCDF sidecar.  A prior SHADOW sidecar
    can be supplied as an independent canonical-background oracle; the WPS
    product is then compared only at represented pressure cells.
    """
    parsed = read_wps(path)
    dates = {key[2] for key in parsed}
    if len(dates) != 1:
        raise AssertionError(f"OFF WPS output has inconsistent valid times: {sorted(dates)}")
    output = fields(path)
    output_names = {field for field, _ in output}
    missing = OFF_REQUIRED_FIELDS - output_names
    unexpected = output_names - OFF_REQUIRED_FIELDS
    if missing or unexpected:
        raise AssertionError(
            f"OFF WPS inventory mismatch; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    shadow_path = Path(str(path) + ".shadow.nc")
    if shadow_path.exists():
        raise AssertionError("OFF unexpectedly emitted a SHADOW diagnostic sidecar")
    terrain = {level for name, level in output if name == "SOILHGT"}
    if terrain != {SURFACE_LEVEL} or output[("SOILHGT", SURFACE_LEVEL)][0] != "m":
        raise AssertionError("OFF source terrain level/units mismatch")
    np.testing.assert_array_equal(output[("SOILHGT", SURFACE_LEVEL)][1],
                                  output[("HGT", SURFACE_LEVEL)][1])

    pressure_levels = {
        level for (field, level) in output if field == "TT" and level != SURFACE_LEVEL
    }
    if not pressure_levels:
        raise AssertionError("OFF output has no represented pressure levels")
    for field in (*OFF_HYDROMETEORS, "QV"):
        levels = {level for name, level in output if name == field}
        if levels != {*pressure_levels, SURFACE_LEVEL}:
            raise AssertionError(f"OFF {field} levels {sorted(levels)} are incomplete")
        units = {values[0] for (name, _), values in output.items() if name == field}
        if units != {"kg kg{-1}"}:
            raise AssertionError(f"OFF {field} units changed: {sorted(units)}")
        surface = output[(field, SURFACE_LEVEL)][1]
        if not np.all(np.isfinite(surface)):
            raise AssertionError(f"OFF {field} surface slab is non-finite")
        if field in OFF_HYDROMETEORS and not np.allclose(surface, 0.0, rtol=0.0, atol=0.0):
            raise AssertionError(f"OFF {field} surface slab is not the explicit zero fill")

    if reference is None:
        return

    try:
        import netCDF4
    except ImportError as exc:  # pragma: no cover - fixture environments have netCDF4
        raise AssertionError("OFF canonical identity check requires netCDF4") from exc

    with netCDF4.Dataset(reference) as dataset:
        pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
        above_ground = np.asarray(dataset.variables["above_ground"][:], dtype=bool)
        expected_shape = (
            len(dataset.dimensions["x"]),
            len(dataset.dimensions["y"]),
        )
        expected_hdate = datetime.fromtimestamp(
            int(dataset.valid_time_epoch), timezone.utc
        ).strftime("%Y-%m-%d_%H:%M:%S.0000")
        background = {
            name: np.asarray(dataset.variables[name][:])
            for name in OFF_BACKGROUND_FIELDS.values()
        }
    shapes = {record_shape for _, record_shape, _, _ in parsed.values()}
    if shapes != {expected_shape}:
        raise AssertionError(f"OFF WPS record shape changed: {sorted(shapes)}")
    if dates != {expected_hdate}:
        raise AssertionError(f"OFF WPS valid time {sorted(dates)} != {expected_hdate}")
    pressure_index = {float(level): index for index, level in enumerate(pressure)}
    for field, sidecar_name in OFF_BACKGROUND_FIELDS.items():
        sidecar = background[sidecar_name]
        for level in sorted(pressure_levels):
            if level not in pressure_index:
                raise AssertionError(f"OFF pressure level {level} missing from canonical reference")
            expected = sidecar[pressure_index[level]]
            if field == "HGT":
                expected = np.asarray(
                    np.asarray(expected, dtype=np.float64) / np.float64(GRAVITY),
                    dtype=np.float32,
                )
            # WPS records are flat Fortran-order slabs and the sidecar uses
            # z,y,x.  Reconstruct the WPS x,y shape before comparing cells.
            actual = output[(field, level)][1].reshape(
                (expected.shape[1], expected.shape[0]), order="F"
            )
            mask = above_ground[pressure_index[level]]
            np.testing.assert_array_equal(
                actual[mask.T], expected.T[mask.T],
                err_msg=f"OFF {field} changed canonical background at {level}",
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("default", "vapor", "hotstart-vapor", "off"))
    parser.add_argument("output", type=Path)
    parser.add_argument("reference", type=Path, nargs="?", help="optional SHADOW sidecar background oracle")
    args = parser.parse_args()
    if args.mode == "default":
        check_default(args.output)
    elif args.mode == "vapor":
        check_vapor(args.output)
    elif args.mode == "hotstart-vapor":
        check_hotstart_vapor(args.output)
    else:
        check_off(args.output, args.reference)
    print(f"lapsprep {args.mode} WPS output contract passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
