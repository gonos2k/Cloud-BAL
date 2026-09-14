#!/usr/bin/env python3
"""Create the small numerical LAPS/NetCDF tree used by the real caller test."""

from __future__ import annotations

import argparse
from pathlib import Path

import netCDF4
import numpy as np


STAMP = "260010300"
NX, NY, NZ = 2, 2, 3
LEVELS_HPA = np.array([500.0, 400.0, 300.0], dtype=np.float32)
BASE_SPECIFIC_HUMIDITY = np.array([0.001, 0.002, 0.003], dtype=np.float32)
HOTSTART_SPECIFIC_HUMIDITY = np.array([0.12, 0.14, 0.16], dtype=np.float32)
HOTSTART_CONCENTRATIONS = {
    "lwc": np.array([0.010, 0.012, 0.014], dtype=np.float32),
    "rai": np.array([0.020, 0.022, 0.024], dtype=np.float32),
    "sno": np.array([0.030, 0.032, 0.034], dtype=np.float32),
    "ice": np.array([0.040, 0.042, 0.044], dtype=np.float32),
    "pic": np.array([0.050, 0.052, 0.054], dtype=np.float32),
}


def make_file(
    root: Path,
    extension: str,
    names: tuple[str, ...],
    *,
    sh_bad: str | None,
    bad_temperature: bool,
    bad_surface_mr: bool,
    surface_pressure: float,
    hotstart: bool,
    levels_hpa: np.ndarray,
    reverse_levels: bool,
    invalid_fields: set[str],
    make_sfc_uv: bool,
) -> None:
    path = root / "lapsprd" / extension / f"{STAMP}.{extension}"
    depth = 1 if extension == "lsx" else NZ
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("record", 1)
        dataset.createDimension("z", depth)
        dataset.createDimension("x", NX)
        dataset.createDimension("y", NY)
        levels = dataset.createVariable("level", "f4", ("z",))
        levels[:] = levels_hpa[:depth]

        def level_index(level_hpa: float) -> int:
            index = int(np.flatnonzero(levels_hpa[:depth] == level_hpa)[0])
            return depth - 1 - index if reverse_levels else index

        for name in names:
            variable = dataset.createVariable(name, "f4", ("record", "z", "y", "x"))
            values = np.zeros((1, depth, NY, NX), dtype=np.float32)
            if name in {"ht"}:
                if make_sfc_uv and depth > 1:
                    values[...] = np.array([200.0, 300.0, 50.0], dtype=np.float32)[:depth][
                        None, :, None, None
                    ]
                else:
                    values[...] = 1000.0
            elif name in {"t3", "t"}:
                values[...] = 1000.0 if bad_temperature and name == "t3" else 280.0
            elif name in {"u3", "u"}:
                if make_sfc_uv and name == "u3" and depth > 1:
                    values[...] = np.array([50.0, 40.0, 30.0], dtype=np.float32)[:depth][
                        None, :, None, None
                    ]
                else:
                    values[...] = 2.0
            elif name in {"v3", "v"}:
                if make_sfc_uv and name == "v3" and depth > 1:
                    values[...] = np.array([-50.0, -40.0, -30.0], dtype=np.float32)[:depth][
                        None, :, None, None
                    ]
                else:
                    values[...] = -2.0
            elif name in {"om", "vv"}:
                values[...] = 0.0
            elif name in {"rhl", "rh"}:
                values[...] = 50.0
            elif name == "sh":
                specific_humidity = (HOTSTART_SPECIFIC_HUMIDITY if hotstart
                                     else BASE_SPECIFIC_HUMIDITY)
                values[...] = specific_humidity[:depth][None, :, None, None]
                if sh_bad in {"nan", "nan500"}:
                    target_level = 500.0 if sh_bad == "nan500" else 400.0
                    target = level_index(target_level)
                    values[0, target, 0, 0] = np.nan
                elif sh_bad in {"inf", "inf500"}:
                    target_level = 500.0 if sh_bad == "inf500" else 400.0
                    target = level_index(target_level)
                    values[0, target, 0, 0] = np.inf
                elif sh_bad in {"missing500", "negative-missing500", "missing300"}:
                    target_level = 500.0 if sh_bad != "missing300" else 300.0
                    target = level_index(target_level)
                    missing = -1.0e37 if sh_bad == "negative-missing500" else 1.0e37
                    values[0, target, :, :] = missing
                elif sh_bad == "high500":
                    target = level_index(500.0)
                    values[0, target, 0, 0] = 0.3
            elif hotstart and name in HOTSTART_CONCENTRATIONS:
                values[...] = HOTSTART_CONCENTRATIONS[name][:depth][None, :, None, None]
            elif name == "mr":
                surface_mr = 200.0 if bad_surface_mr else (80.0 if hotstart else 8.0)
                values[...] = surface_mr  # source contract is g/kg
            elif name == "ps":
                values[...] = surface_pressure
            elif name == "msl":
                values[...] = 100000.0
            elif name == "tgd":
                values[...] = 285.0
            if name in invalid_fields:
                values[...] = 1000.0
            variable[:] = values
            if reverse_levels and depth > 1:
                variable[:] = values[:, ::-1, :, :]


def build_fixture(root: Path, case: str) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for extension in ("lt1", "lw3", "lh3", "lsx", "lq3", "lwc"):
        (root / "lapsprd" / extension).mkdir(parents=True)
    (root / "lapsprd" / "lapsprep" / "wps").mkdir(parents=True)
    (root / "static").mkdir()

    hotstart = case == "hotstart-vapor"
    mixed_output = case.startswith("mixed-")
    make_sfc_uv = case in {"make-sfc-uv", "ascending-make-sfc-uv"}
    reverse_levels = case.startswith("ascending-")
    levels_hpa = LEVELS_HPA[::-1].copy() if reverse_levels else LEVELS_HPA.copy()
    if case == "duplicate-pressure":
        levels_hpa = np.array([500.0, 400.0, 400.0], dtype=np.float32)
    elif case == "nonmonotonic-pressure":
        levels_hpa = np.array([500.0, 300.0, 400.0], dtype=np.float32)

    surface_pressure = 90000.0
    if case.startswith("subterrain-") or case == "ascending-subterrain-sh":
        surface_pressure = 45000.0
    if case == "subterrain-equality":
        surface_pressure = 50000.0
    elif case == "subterrain-bad-psfc":
        surface_pressure = 1000.0

    missing_fields: set[str] = set()
    invalid_fields: set[str] = set()
    if case.endswith("missing-om"):
        missing_fields.add("om")
    elif case.endswith("missing-vv"):
        missing_fields.add("vv")
    elif case.endswith("invalid-om"):
        invalid_fields.add("om")
    elif case.endswith("invalid-vv"):
        invalid_fields.add("vv")
    elif case == "missing-u3":
        missing_fields.add("u3")
    elif case == "missing-v3":
        missing_fields.add("v3")
    elif case == "invalid-u3":
        invalid_fields.add("u3")
    elif case == "invalid-v3":
        invalid_fields.add("v3")

    vapor_enabled = case != "default"
    strict_cases = {
        "strict-vapor", "strict-bad-t", "hotstart-vapor", "ascending-vapor",
        "duplicate-pressure", "nonmonotonic-pressure", "make-sfc-uv",
        "ascending-make-sfc-uv", "missing-u3", "missing-v3", "invalid-u3", "invalid-v3",
        "subterrain-sh", "subterrain-sh-negative", "ascending-subterrain-sh",
    }
    strict_contracts = case in strict_cases or case.startswith(("wps-", "mixed-"))
    cap_policy = "KEEP" if hotstart else "TRANSFER"
    output_formats = "'wps','cdf'" if mixed_output else "'wps'"
    setup = [
        "&lapsprep_nl",
        f" HOTSTART={'.true.' if hotstart else '.false.'}, BALANCE=.false., "
        f"OUTPUT_FORMAT={output_formats},",
        f" GRID_SCALE='NONE', HYDRO_MODE='CONSERVATIVE', CAP_POLICY='{cap_policy}',",
        f" WIND_COORDINATE='GRID_RELATIVE', "
        f"MAKE_SFC_UV={'.true.' if make_sfc_uv else '.false.'}, "
        f"ENFORCE_FIELD_CONTRACTS={'.true.' if strict_contracts else '.false.'},",
    ]
    if vapor_enabled:
        setup.append(" WPS_OUTPUT_VAPOR=.true.,")
    if hotstart:
        setup.append(" LWC2VAPOR_THRESH=0.0, SNOW_THRESH=1.1,")
    setup.append("/")
    (root / "static" / "lapsprep.nl").write_text("\n".join(setup) + "\n", encoding="ascii")

    sh_bad = {
        "nan": "nan",
        "inf": "inf",
        "subterrain-nan": "nan500",
        "subterrain-inf": "inf500",
        "subterrain-sh": "missing500",
        "subterrain-sh-negative": "negative-missing500",
        "ascending-subterrain-sh": "missing500",
        "subterrain-aboveground": "missing300",
        "subterrain-equality": "missing500",
        "subterrain-high": "high500",
    }.get(case)
    bad_temperature = case in {"bad-t", "strict-bad-t"}
    bad_surface_mr = case == "bad-mr"
    lt1_names = tuple(name for name in ("ht", "t3") if name not in missing_fields)
    lw3_names = tuple(name for name in ("u3", "v3", "om") if name not in missing_fields)
    lh3_names = tuple(name for name in ("rhl",) if name not in missing_fields)
    lsx_names = tuple(
        name for name in ("u", "v", "t", "rh", "tgd", "ps", "msl", "mr", "vv")
        if name not in missing_fields
    )
    make_file(root, "lt1", lt1_names, sh_bad=sh_bad, bad_temperature=bad_temperature,
              bad_surface_mr=bad_surface_mr, surface_pressure=surface_pressure,
              hotstart=hotstart, levels_hpa=levels_hpa,
              reverse_levels=reverse_levels, invalid_fields=invalid_fields,
              make_sfc_uv=make_sfc_uv)
    make_file(root, "lw3", lw3_names, sh_bad=sh_bad, bad_temperature=bad_temperature,
              bad_surface_mr=bad_surface_mr, surface_pressure=surface_pressure,
              hotstart=hotstart, levels_hpa=levels_hpa,
              reverse_levels=reverse_levels, invalid_fields=invalid_fields,
              make_sfc_uv=make_sfc_uv)
    make_file(root, "lh3", lh3_names, sh_bad=sh_bad, bad_temperature=bad_temperature,
              bad_surface_mr=bad_surface_mr, surface_pressure=surface_pressure,
              hotstart=hotstart, levels_hpa=levels_hpa,
              reverse_levels=reverse_levels, invalid_fields=invalid_fields,
              make_sfc_uv=make_sfc_uv)
    make_file(
        root,
        "lsx",
        lsx_names,
        sh_bad=sh_bad,
        bad_temperature=bad_temperature, bad_surface_mr=bad_surface_mr,
        surface_pressure=surface_pressure, hotstart=hotstart, levels_hpa=levels_hpa,
        reverse_levels=reverse_levels,
        invalid_fields=invalid_fields, make_sfc_uv=make_sfc_uv,
    )
    if case not in {"missing-sh", "subterrain-missing-sh"}:
        make_file(root, "lq3", ("sh",), sh_bad=sh_bad, bad_temperature=bad_temperature,
                  bad_surface_mr=bad_surface_mr, surface_pressure=surface_pressure,
                  hotstart=hotstart, levels_hpa=levels_hpa,
                  reverse_levels=reverse_levels, invalid_fields=invalid_fields,
                  make_sfc_uv=make_sfc_uv)
    if hotstart:
        make_file(root, "lwc", tuple(HOTSTART_CONCENTRATIONS), sh_bad=sh_bad,
                  bad_temperature=bad_temperature, bad_surface_mr=bad_surface_mr,
                  surface_pressure=surface_pressure, hotstart=True, levels_hpa=levels_hpa,
                  reverse_levels=reverse_levels,
                  invalid_fields=invalid_fields, make_sfc_uv=make_sfc_uv)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("case", choices=(
        "default", "vapor", "strict-vapor", "hotstart-vapor", "missing-sh", "subterrain-missing-sh",
        "nan", "inf", "subterrain-sh", "subterrain-sh-negative", "ascending-subterrain-sh",
        "subterrain-aboveground", "subterrain-equality", "subterrain-nan", "subterrain-inf",
        "subterrain-high", "subterrain-bad-psfc",
        "bad-t", "strict-bad-t", "bad-mr", "wps-missing-om", "wps-missing-vv",
        "wps-invalid-om", "wps-invalid-vv", "mixed-missing-om", "mixed-missing-vv",
        "mixed-invalid-om", "mixed-invalid-vv", "missing-u3", "missing-v3", "invalid-u3",
        "invalid-v3", "ascending-vapor", "duplicate-pressure", "nonmonotonic-pressure",
        "make-sfc-uv", "ascending-make-sfc-uv",
    ))
    args = parser.parse_args()
    build_fixture(args.root, args.case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
