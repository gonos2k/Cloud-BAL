#!/usr/bin/env python3
"""Validate prepared real inputs and the original pre-QBAL read closure."""

from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np


FORBIDDEN_PARTS = ("bigfile", "lapsprep/wps", "/balance/", "met_em")
FORBIDDEN_NAMES = ("LAPS:", "KLBG:")
PRE_QBAL_MANIFEST_NAME = "PRE_QBAL_MANIFEST.json"
PRE_QBAL_MANIFEST_CONTRACT = "original_klaps_pre_qbal_generation_v1"
PRE_QBAL_PRODUCTS = ("lt1", "lq3", "lw3", "lco", "lsx")
LCO_EVIDENCE_CONTRACT = "derived_lco_evidence_v1"
LCO_EVIDENCE_INDEX_SHA256 = (
    "a842a6db01e4ebec4c516262db7a3fe1c3d27bc70ed5c3ef00924b2a315667ba"
)
LCO_SOURCE_CDL_SHA256 = (
    "70045ee14609f93f7ebbe107237b8ded69958ef7a4644abaa0495295eb4c5651"
)
LCO_PRODUCER_SHA256 = (
    "c4665726def2f67e05775e23ded681992adb7a0c91d0374ca90c5da1e7273f25"
)
PRE_QBAL_PRODUCERS = {
    "lt1": ("temperature_analysis", "klps_anal_temp.exe"),
    "lq3": ("humidity_analysis", "klps_anal_humd.exe"),
    "lw3": ("wind_analysis", "klps_anal_wind_openmp.exe"),
    "lco": ("derived_cloud_analysis", "klps_anal_derv.exe"),
    "lsx": ("surface_analysis", "klps_anal_lsfc.exe"),
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
GRID_X = 235
GRID_Y = 283
NAV_SIZE = 1
NAME_LENGTH = 132
# The legacy FSF CDL rounds only these two encoded coordinates.  Keep the
# tolerance tied to the documented decimal precision; the additional term
# allows each float32 encoding to land on an adjacent representable value.
NAVIGATION_ABSOLUTE_TOLERANCES = {"La1": 5.0e-6, "Lo1": 5.0e-5}
MIN_DEFAULT_ACTIVE_FRACTION = 0.50
UTC_EPOCH_UNITS = "seconds since (1970-1-1 00:00:00.0)"
PRESSURE_LEVELS_HPA = np.arange(50.0, 1100.1, 50.0)
EXPECTED_MANIFEST_SHA256 = (
    "b6dba2f813773b09261280b5b865636594071b95957789f9aab1495ad2b4f29f"
)
EXPECTED_CASES = (
    ("20260816T120000Z", "2026-08-16T12:00:00Z", "262281200"),
    ("20260816T130000Z", "2026-08-16T13:00:00Z", "262281300"),
    ("20260816T140000Z", "2026-08-16T14:00:00Z", "262281400"),
    ("20260816T150000Z", "2026-08-16T15:00:00Z", "262281500"),
)
ALLOWED_ROOTS = {
    "fua": "ANAL/NE57/DAOU/00/lapsprd/fua/wrf",
    "fsf": "ANAL/NE57/DAOU/00/lapsprd/fsf/wrf",
    "lw3": "klaps-v5.0_/baseline/20260831_wind_multitime/results",
    "vrz": "ANAL/NE57/DAOU/00/lapsprd/vrz",
    "vrt": "ANAL/NE57/DAOU/00/lapsprd/vrt",
}

STATIC_INPUTS = {
    "ANAL/NE57/DABA/static.nest7grid":
        "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b",
    "ANAL/NE57/DABA/namelist/nest7grid.parms":
        "ad70f80fb4050a8a14a2b48e725c00f16480977c9e5f4ec3f8904ee72f9430c2",
    "ANAL/NE57/DABA/namelist/pressures.nl":
        "a02a5e18c39cfaa505d3f52cbf1ec9366ca9f91dc24508fdd0167d3f7ebd014f",
    "ANAL/NE57/DABA/namelist/background.nl":
        "5cc1361c2cce28e384aff83ba13288ea0d1bb27d0ce78496cacb5dd82f23adc5",
    "ANAL/NE57/DABA/namelist/balance.nl":
        "8a8c2c70df69684a78833ad7d6882a248c6e140c5b208f4b29dd1c0c61d1c13a",
    "ANAL/NE57/DABA/namelist/deriv.nl":
        "3cd8b73816cd9a208fecd793cc9a9e7101cbe2b0c5208874a1ac23a4dd5cd072",
}

FILE_SPECS = {
    "lsx": {
        "z": 1,
        "variables": {"t": ("degreeskelvin",), "ps": ("pascals",)},
    },
    "lt1": {
        "z": 22,
        "variables": {"t3": ("degreeskelvin",), "ht": ("meters",)},
    },
    "lco": {
        "z": 22,
        "variables": {"com": ("pascals/second",)},
    },
    "fua": {
        "z": 22,
        "variables": {
            "u3": ("m/s",), "v3": ("m/s",), "t3": ("kelvins",),
            "ht": ("meters",), "sh": ("kg/kg",), "om": ("pa/s",),
            "lwc": ("kg/m**3",), "ice": ("kg/m**3",),
            "rai": ("kg/m**3",), "sno": ("kg/m**3",),
            "pic": ("kg/m**3",),
        },
    },
    "fsf": {
        "z": 1,
        "variables": {"psf": ("pascals",), "tsf": ("kelvins",)},
    },
    "lw3": {
        "z": 22,
        "variables": {
            "u3": ("meters/second",), "v3": ("meters/second",),
            "om": ("pascals/second",),
        },
    },
    "vrz": {"z": 22, "variables": {"ref": ("dbz",)}},
    "vrt": {"z": 22, "variables": {"tid": ("nul",)}},
}

VARIABLE_RANGES = {
    "t": (150.0, 350.0),
    "ps": (50000.0, 110000.0),
    "u3": (-200.0, 200.0),
    "v3": (-200.0, 200.0),
    "t3": (150.0, 350.0),
    "tsf": (150.0, 350.0),
    "ht": (-1000.0, 60000.0),
    "sh": (0.0, 0.1),
    "om": (-20000.0, 20000.0),
    "com": (-200.0, 200.0),
    "psf": (10000.0, 120000.0),
    "lwc": (0.0, 1.0),
    "ice": (0.0, 1.0),
    "rai": (0.0, 1.0),
    "sno": (0.0, 1.0),
    "pic": (0.0, 1.0),
    "ref": (-10.0, 100.0),
    "tid": (-10.0, 2.0),
}
MIN_ACTIVE_FRACTION = {"psf": 0.30, "tid": 0.005}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def detached_netcdf(
    path: Path, expected_hash: str | None = None
):
    """Read and validate one immutable NetCDF byte snapshot.

    The returned Dataset is backed by the bytes already hashed, so later
    replacement of ``path`` cannot change the content being inspected.
    """
    path = Path(path).absolute()
    if (
        not path.is_file()
        or path_contains_symlink(path)
        or path.stat().st_nlink != 1
    ):
        raise ValueError("regular non-hardlinked file required")
    payload = path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if expected_hash is not None and actual_hash != expected_hash:
        raise ValueError(
            f"SHA-256 mismatch: actual {actual_hash}, expected {expected_hash}"
        )
    dataset = netCDF4.Dataset("inmemory.nc", "r", memory=payload)
    try:
        yield dataset, actual_hash
    finally:
        dataset.close()


def normalize_units(value: object) -> str:
    return "".join(str(value).strip().lower().split())


def forbidden_reason(path: Path) -> str | None:
    text = path.as_posix()
    lowered = text.lower()
    if any(part.lower() in lowered for part in FORBIDDEN_PARTS):
        return "downstream/final product path"
    if any(
        component.lower().startswith(prefix.lower())
        for component in path.parts
        for prefix in FORBIDDEN_NAMES
    ):
        return "merged final product name"
    return None


def forbidden_metadata_reason(value: object) -> str | None:
    lowered = str(value).lower().replace("\\", "/")
    if any(part.lower() in lowered for part in FORBIDDEN_PARTS):
        return "downstream/final product provenance"
    if "downstream" in lowered or "merged final" in lowered:
        return "downstream/final product provenance"
    if any(prefix.lower() in lowered for prefix in FORBIDDEN_NAMES):
        return "merged final product provenance"
    return None


def contained_input(
    workspace: Path,
    relative_path: str,
    kind: str,
    allowed_root: str | None = None,
) -> tuple[Path, str | None]:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        return workspace, "input path must be relative and cannot traverse parents"
    current = workspace
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return workspace, "input path cannot contain a symlink"
    resolved = (workspace / relative).resolve()
    try:
        resolved.relative_to(workspace)
        resolved.relative_to(
            (workspace / (allowed_root or ALLOWED_ROOTS[kind])).resolve()
        )
    except ValueError:
        return resolved, f"{kind} input is outside its allowed original-data root"
    return resolved, None


def expected_epoch(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("valid_time_utc must carry an explicit UTC offset")
    return parsed.astimezone(timezone.utc).timestamp()


def inspect_time_coordinate(
    dataset: netCDF4.Dataset,
    name: str,
    expected: float,
    details: dict[str, object],
    findings: list[str],
) -> None:
    variable = dataset.variables.get(name)
    if variable is None or variable.size != 1:
        findings.append(f"missing scalar {name}")
        return
    if (
        variable.dtype != np.dtype("float64")
        or variable.dimensions != ("record",)
        or normalize_units(getattr(variable, "units", ""))
        != normalize_units(UTC_EPOCH_UNITS)
    ):
        findings.append(f"{name} schema is not exact float64 record UTC epoch")
    values = np.ma.asarray(variable[:]).reshape(-1)
    if values.count() != 1:
        findings.append(f"{name} is masked")
        return
    actual = float(values.compressed()[0])
    details[name] = actual
    if not np.isfinite(actual) or actual != expected:
        findings.append(f"{name}={actual} expected {expected}")


def read_unpacked_field(variable: netCDF4.Variable) -> np.ma.MaskedArray:
    """Ignore stale CDL valid_range, but retain explicit missing-value masks."""
    if any(name in variable.ncattrs() for name in ("scale_factor", "add_offset", "_Unsigned")):
        raise ValueError(f"{variable.name}: packed fields are not supported")
    variable.set_auto_maskandscale(False)
    values = np.asarray(variable[:])
    mask = np.zeros(values.shape, dtype=bool)
    for name in ("_FillValue", "missing_value"):
        for missing in np.asarray(getattr(variable, name, [])).reshape(-1):
            mask |= values == missing
    return np.ma.array(values, mask=mask)


def _inspect_netcdf_dataset(
    dataset: netCDF4.Dataset, kind: str, valid_time: str, reference_time: str,
    *, raw_fields: bool = False,
) -> dict[str, object]:
    spec = FILE_SPECS[kind]
    findings: list[str] = []
    details: dict[str, object] = {}
    for attribute_name in dataset.ncattrs():
        value = dataset.getncattr(attribute_name)
        reason = forbidden_metadata_reason(value)
        if reason:
            findings.append(f"global attribute {attribute_name}: {reason}")
    for variable_name, variable in dataset.variables.items():
        for attribute_name in variable.ncattrs():
            reason = forbidden_metadata_reason(variable.getncattr(attribute_name))
            if reason:
                findings.append(
                    f"{variable_name} attribute {attribute_name}: {reason}"
                )
    dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
    details["dimensions"] = dimensions
    expected_dimensions = {
        "record": 1,
        "z": spec["z"],
        "x": GRID_X,
        "y": GRID_Y,
        "nav": NAV_SIZE,
        "namelen": NAME_LENGTH,
    }
    if dimensions != expected_dimensions:
        findings.append(
            f"dimensions={dimensions} expected exactly {expected_dimensions}"
        )

    for variable_name, accepted_units in spec["variables"].items():
        variable = dataset.variables.get(variable_name)
        if variable is None:
            findings.append(f"missing variable {variable_name}")
            continue
        if variable.dtype != np.dtype("float32"):
            findings.append(
                f"{variable_name} dtype={variable.dtype} expected float32"
            )
        units = normalize_units(getattr(variable, "units", ""))
        if units not in accepted_units:
            findings.append(
                f"{variable_name} units={units!r} expected {accepted_units}"
            )
        expected_dimensions = ("record", "z", "y", "x")
        if variable.dimensions != expected_dimensions:
            findings.append(
                f"{variable_name} dimensions={variable.dimensions} "
                f"expected {expected_dimensions}"
            )
        values = (read_unpacked_field(variable)
                  if raw_fields or kind == "lt1" else np.ma.asarray(variable[:]))
        active = np.asarray(values.compressed(), dtype=float)
        details[f"{variable_name}_active_cells"] = int(active.size)
        total_cells = int(np.prod(values.shape, dtype=np.int64))
        minimum_active = max(
            1,
            int(np.ceil(
                total_cells
                * MIN_ACTIVE_FRACTION.get(
                    variable_name, MIN_DEFAULT_ACTIVE_FRACTION
                )
            )),
        )
        if kind == "lco":
            # COM is a sparse cloud-forcing field.  Above-ground cells
            # may legitimately retain the explicit NetCDF fill value.
            minimum_active = 1
        if kind == "lt1":
            # Exact coverage is checked against independent PSFC below;
            # a fixed fraction would reject valid high-terrain columns.
            minimum_active = 1
        if active.size < minimum_active:
            findings.append(
                f"{variable_name} active_cells={active.size} below required "
                f"coverage {minimum_active}/{total_cells}"
            )
        elif not np.all(np.isfinite(active)):
            findings.append(f"{variable_name} has non-finite unmasked values")
        else:
            lower, upper = VARIABLE_RANGES[variable_name]
            actual_min = float(np.min(active))
            actual_max = float(np.max(active))
            details[f"{variable_name}_min"] = actual_min
            details[f"{variable_name}_max"] = actual_max
            if actual_min < lower or actual_max > upper:
                findings.append(
                    f"{variable_name} range=[{actual_min},{actual_max}] "
                    f"outside [{lower},{upper}]"
                )

    inspect_time_coordinate(
        dataset, "valtime", expected_epoch(valid_time), details, findings
    )
    inspect_time_coordinate(
        dataset, "reftime", expected_epoch(reference_time), details, findings
    )

    if spec["z"] == 22:
        level = dataset.variables.get("level")
        if level is None:
            findings.append("missing pressure level coordinate")
        else:
            if (
                level.dtype != np.dtype("float32")
                or level.dimensions != ("z",)
                or normalize_units(getattr(level, "units", ""))
                != "hectopascals"
            ):
                findings.append("pressure level schema is not exact float32 hPa")
            values = np.ma.asarray(level[:], dtype=float).reshape(-1)
            active = values.compressed()
            details["level_hpa"] = active.tolist()
            if active.shape != PRESSURE_LEVELS_HPA.shape or not np.array_equal(
                active, PRESSURE_LEVELS_HPA
            ):
                findings.append("pressure levels are not exact 50..1100 hPa")

    if kind == "vrz" and "ref" in dataset.variables:
        values = np.ma.getdata(dataset.variables["ref"][:]).astype(float)
        finite = np.isfinite(values) & (np.abs(values) < 1.0e36)
        details["radar_finite_cells"] = int(np.count_nonzero(finite))
        details["radar_no_echo_minus10_cells"] = int(
            np.count_nonzero(finite & (values == -10.0))
        )
        details["radar_usable_ge0_cells_before_terrain"] = int(
            np.count_nonzero(finite & (values >= 0.0) & (values <= 100.0))
        )
        details["radar_max_dbz"] = float(np.max(values[finite]))
    elif kind == "vrt" and "tid" in dataset.variables:
        values = np.ma.getdata(dataset.variables["tid"][:]).astype(float)
        finite = np.isfinite(values) & (np.abs(values) < 1.0e36)
        details["bright_band_tid2_cells"] = int(
            np.count_nonzero(finite & (values == 2.0))
        )
        details["tid_no_marker_minus10_cells"] = int(
            np.count_nonzero(finite & (values == -10.0))
        )

    details["status"] = "PASS" if not findings else "FAIL"
    details["findings"] = findings
    return details




def inspect_netcdf(
    path: Path, kind: str, valid_time: str, reference_time: str,
    *, raw_fields: bool = False,
) -> dict[str, object]:
    with netCDF4.Dataset(path, "r") as dataset:
        return _inspect_netcdf_dataset(
            dataset, kind, valid_time, reference_time, raw_fields=raw_fields
        )

def inspect_navigation(candidate, reference, findings: list[str]) -> None:
    """Compare encoded legacy navigation; this does not certify native metrics."""
    for name in ("Nx", "Ny", "La1", "Lo1", "LoV", "Latin1", "Latin2", "Dx", "Dy", "grid_type", "x_dim", "y_dim"):
        left, right = candidate.variables.get(name), reference.variables.get(name)
        char = name in ("grid_type", "x_dim", "y_dim")
        dtype = np.dtype("S1" if char else "int16" if name in ("Nx", "Ny") else "float32")
        dims = ("nav", "namelen") if char else ("nav",)
        if any(v is None or v.dtype != dtype or v.dimensions != dims for v in (left, right)):
            findings.append(f"navigation {name}: invalid schema")
            continue
        if char:
            # C writers use NUL padding, while Fortran may use spaces.
            left.set_auto_maskandscale(False)
            right.set_auto_maskandscale(False)
            left_text = left[:].tobytes().decode("ascii").strip(" \x00")
            right_text = right[:].tobytes().decode("ascii").strip(" \x00")
            if not right_text or left_text != right_text:
                findings.append(f"navigation {name}: candidate/reference mismatch")
            if name in ("x_dim", "y_dim") and right_text != name[0]:
                findings.append(f"navigation {name}: wrong axis label")
            continue

        left_values = left[:]
        right_values = right[:]
        values_match = (
            not np.ma.is_masked(left_values)
            and not np.ma.is_masked(right_values)
        )
        if values_match and name in NAVIGATION_ABSOLUTE_TOLERANCES:
            left_float64 = np.asarray(left_values, dtype=np.float64)
            right_float64 = np.asarray(right_values, dtype=np.float64)
            values_match = bool(
                np.all(np.isfinite(left_float64))
                and np.all(np.isfinite(right_float64))
            )
            if values_match:
                # A decimal source value can round by half an ULP when each
                # side is encoded as float32.  Account for both encodings.
                left_ulp = np.abs(np.spacing(np.asarray(left_values, dtype=np.float32)))
                right_ulp = np.abs(np.spacing(np.asarray(right_values, dtype=np.float32)))
                tolerance = (
                    NAVIGATION_ABSOLUTE_TOLERANCES[name]
                    + 0.5 * (left_ulp + right_ulp)
                )
                values_match = bool(
                    np.all(np.abs(left_float64 - right_float64) <= tolerance)
                )
        elif values_match:
            values_match = np.array_equal(left_values, right_values)

        if (not values_match
                or normalize_units(getattr(left, "units", "")) != normalize_units(getattr(right, "units", ""))):
            findings.append(f"navigation {name}: candidate/reference mismatch")
        if not char and not np.all(np.isfinite(right_values)):
            findings.append(f"navigation {name}: non-finite reference")
        if name in ("Nx", "Ny") and right[0] != (GRID_X if name == "Nx" else GRID_Y):
            findings.append(f"navigation {name}: wrong domain size")


def inspect_lt1_candidate(
    path: Path, fsf_path: Path, valid_time: str, reference_time: str
) -> dict[str, object]:
    """Check LT1 contents against an independent FSF, not producer authority.

    LT1 reftime is the analysis time; FSF reftime is the background cycle.
    Navigation comparison preserves legacy encoded Dx/Dy, without asserting
    that their stale unit labels establish a physical grid metric.
    PSFC uses the existing real-reader boundary range (50000..110000 Pa),
    deliberately narrower than the generic pressure-geometry routine.
    """
    details: dict[str, object] = {
        "scope": "LT1_CONTENT_ONLY", "generation_status": "BLOCKED",
        "promotion_allowed": False,
    }
    findings: list[str] = []
    try:
        candidate = inspect_netcdf(path, "lt1", valid_time, valid_time)
        reference = inspect_netcdf(
            fsf_path, "fsf", valid_time, reference_time, raw_fields=True
        )
        details.update(candidate=candidate, reference=reference)
        findings.extend(f"LT1: {item}" for item in candidate["findings"])
        findings.extend(f"FSF: {item}" for item in reference["findings"])
        # Do not index malformed dimensions or absent mandatory fields.
        if findings:
            return dict(details, status="FAIL", findings=findings)
        with netCDF4.Dataset(path, "r") as lt1, netCDF4.Dataset(fsf_path, "r") as fsf:
            psfc = read_unpacked_field(fsf.variables["psf"])[0, 0]
            psfc_values = np.ma.getdata(psfc)
            if (np.any(np.ma.getmaskarray(psfc))
                    or not np.all(np.isfinite(psfc_values))
                    or np.any(psfc_values < 50000.0)
                    or np.any(psfc_values > 110000.0)):
                findings.append("FSF: complete finite PSFC domain in 50000..110000 Pa required")
            else:
                active = PRESSURE_LEVELS_HPA[:, None, None] * 100.0 <= psfc_values
                details["above_ground_cells"] = int(np.count_nonzero(active))
                for name in ("t3", "ht"):
                    variable = lt1.variables[name]
                    values = read_unpacked_field(variable)[0]
                    usable = ~np.ma.getmaskarray(values) & np.isfinite(np.ma.getdata(values))
                    lower, upper = VARIABLE_RANGES[name]
                    usable &= (np.ma.getdata(values) >= lower) & (np.ma.getdata(values) <= upper)
                    if np.any(active & ~usable):
                        findings.append(f"{name}: incomplete above-ground coverage")
                    for attr, expected in (
                        ("LAPS_var", name.upper()),
                        ("LAPS_units", "K" if name == "t3" else "METERS"),
                        ("lvl_coord", "HPA"),
                    ):
                        if str(getattr(variable, attr, "")).strip() != expected:
                            findings.append(f"{name}: invalid {attr}")
                    inventory = lt1.variables.get(f"{name}_fcinv")
                    if (inventory is None or inventory.dtype != np.dtype("int16")
                            or inventory.dimensions != ("record", "z")
                            or not np.all(np.ma.filled(inventory[:], 0) == 1)):
                        findings.append(f"{name}: all 22 written inventory levels required")
            for name, expected in (("imax", GRID_X), ("jmax", GRID_Y), ("kmax", 44), ("kdim", 44)):
                variable = lt1.variables.get(name)
                if (variable is None or variable.dtype != np.dtype("int32")
                        or variable.dimensions != ()
                        or np.ma.is_masked(variable[...]) or variable[...] != expected):
                    findings.append(f"LT1: invalid {name}, expected {expected}")
            inspect_navigation(lt1, fsf, findings)
    except (OSError, ValueError, TypeError, IndexError, KeyError, RuntimeError) as error:
        findings.append(f"NetCDF validation error: {error}")
    return dict(details, status="FAIL" if findings else "PASS", findings=findings)


def _inspect_lsx_datasets(
    lsx: netCDF4.Dataset,
    fsf: netCDF4.Dataset,
    valid_time: str,
    reference_time: str,
) -> dict[str, object]:
    """Check LSX T/PS against an already detached FSF snapshot."""
    details = {
        "scope": "LSX_CONTENT_ONLY",
        "generation_status": "BLOCKED",
        "promotion_allowed": False,
        "producer_provenance": "NOT_VERIFIED",
    }
    findings: list[str] = []
    candidate = _inspect_netcdf_dataset(
        lsx, "lsx", valid_time, valid_time, raw_fields=True
    )
    reference = _inspect_netcdf_dataset(
        fsf, "fsf", valid_time, reference_time, raw_fields=True
    )
    details.update(candidate=candidate, reference=reference)
    findings.extend(f"LSX: {item}" for item in candidate["findings"])
    findings.extend(f"FSF: {item}" for item in reference["findings"])
    if not findings:
        for name, units in (("t", "K"), ("ps", "PA")):
            variable = lsx.variables[name]
            values = read_unpacked_field(variable)
            if np.any(np.ma.getmaskarray(values)):
                findings.append(f"{name}: complete surface coverage required")
            for attr, expected in (
                ("LAPS_var", name.upper()),
                ("LAPS_units", units),
                ("lvl_coord", "AGL"),
            ):
                if str(getattr(variable, attr, "")).strip() != expected:
                    findings.append(f"{name}: invalid {attr}")
            inventory = lsx.variables.get(f"{name}_fcinv")
            if (
                inventory is None
                or inventory.dtype != np.dtype("int16")
                or inventory.dimensions != ("record", "z")
                or not np.all(np.ma.filled(inventory[:], 0) == 1)
            ):
                findings.append(f"{name}: written surface inventory required")
        for name, expected in (
            ("imax", GRID_X),
            ("jmax", GRID_Y),
            ("kmax", 24),
            ("kdim", 24),
        ):
            variable = lsx.variables.get(name)
            if (
                variable is None
                or variable.dtype != np.dtype("int32")
                or variable.dimensions != ()
                or np.ma.is_masked(variable[...])
                or variable[...] != expected
            ):
                findings.append(f"LSX: invalid {name}, expected {expected}")
        level = lsx.variables.get("level")
        if (
            level is None
            or level.dtype != np.dtype("float32")
            or level.dimensions != ("z",)
            or normalize_units(getattr(level, "units", "")) != "none"
            or np.ma.is_masked(level[:])
            or not np.array_equal(level[:], [0.0])
        ):
            findings.append("LSX: surface level must be AGL zero")
        inspect_navigation(lsx, fsf, findings)
    return dict(details, status="FAIL" if findings else "PASS", findings=findings)


def inspect_lsx_candidate(
    path: Path, fsf_path: Path, valid_time: str, reference_time: str
) -> dict[str, object]:
    """Check LSX using the same detached bytes that are hashed."""
    details = {
        "scope": "LSX_CONTENT_ONLY",
        "generation_status": "BLOCKED",
        "promotion_allowed": False,
        "producer_provenance": "NOT_VERIFIED",
    }
    findings: list[str] = []
    paths = (Path(path).absolute(), Path(fsf_path).absolute())
    try:
        stamp = datetime.fromisoformat(
            valid_time.replace("Z", "+00:00")
        ).strftime("%y%j%H%M")
        if paths[0].name != f"{stamp}.lsx":
            raise ValueError("LSX filename does not match exact analysis time")
        if any(forbidden_reason(item) for item in paths):
            raise ValueError("downstream/final product path")
        if paths[0].samefile(paths[1]):
            raise ValueError("independent LSX and FSF files required")
        with detached_netcdf(paths[0]) as (lsx, lsx_hash), detached_netcdf(
            paths[1]
        ) as (fsf, fsf_hash):
            details.update(
                _inspect_lsx_datasets(lsx, fsf, valid_time, reference_time),
                lsx_sha256=lsx_hash,
                fsf_sha256=fsf_hash,
            )
    except (OSError, ValueError, TypeError, IndexError, KeyError, RuntimeError) as error:
        findings.append(f"LSX validation error: {error}")
    if findings:
        details["findings"] = findings
        details["status"] = "FAIL"
    return details if findings else details


def _inspect_lco_datasets(
    lco: netCDF4.Dataset,
    fsf: netCDF4.Dataset,
    valid_time: str,
    reference_time: str,
    *,
    lsx: netCDF4.Dataset | None = None,
    lco_sha256: str | None = None,
    fsf_sha256: str | None = None,
    lsx_sha256: str | None = None,
) -> dict[str, object]:
    """Inspect detached LCO/FSF bytes and optional same-case LSX analysis PS."""
    details: dict[str, object] = {
        "scope": "LCO_CONTENT_ONLY",
        "generation_status": "BLOCKED",
        "promotion_allowed": False,
        "cloud_omega_authority": "EVIDENCE_ONLY",
        "omega_target_authority": "NO_AUTHORITY",
        "omega_target_sigma_provided": False,
        "dynamic_authority": False,
    }
    findings: list[str] = []
    candidate = _inspect_netcdf_dataset(
        lco, "lco", valid_time, valid_time, raw_fields=True
    )
    reference = _inspect_netcdf_dataset(
        fsf, "fsf", valid_time, reference_time, raw_fields=True
    )
    details.update(candidate=candidate, reference=reference)
    if lco_sha256 is not None:
        details["lco_sha256"] = lco_sha256
    if fsf_sha256 is not None:
        details["fsf_sha256"] = fsf_sha256
    findings.extend(f"LCO: {item}" for item in candidate["findings"])
    findings.extend(f"FSF: {item}" for item in reference["findings"])
    analysis = None
    if lsx is not None:
        analysis = _inspect_lsx_datasets(lsx, fsf, valid_time, reference_time)
        details["analysis_reference"] = analysis
        if lsx_sha256 is not None:
            details["lsx_sha256"] = lsx_sha256
        findings.extend(f"LSX: {item}" for item in analysis["findings"])

    if not findings:
        com = lco.variables["com"]
        for attribute, expected in (
            ("LAPS_var", "COM"),
            ("LAPS_units", "PA/S"),
            ("lvl_coord", "HPA"),
        ):
            if str(getattr(com, attribute, "")).strip() != expected:
                findings.append(f"com: invalid {attribute}")

        inventory = lco.variables.get("com_fcinv")
        if (
            inventory is None
            or inventory.dtype != np.dtype("int16")
            or inventory.dimensions != ("record", "z")
            or not np.all(np.ma.filled(inventory[:], 0) == 1)
        ):
            findings.append("com: all 22 written inventory levels required")

        for name, expected in (
            ("imax", GRID_X),
            ("jmax", GRID_Y),
            ("kmax", 22),
            ("kdim", 22),
        ):
            variable = lco.variables.get(name)
            if (
                variable is None
                or variable.dtype != np.dtype("int32")
                or variable.dimensions != ()
                or np.ma.is_masked(variable[...])
                or variable[...] != expected
            ):
                findings.append(f"LCO: invalid {name}, expected {expected}")

        inspect_navigation(lco, fsf, findings)
        raw_com = read_unpacked_field(com)
        raw_values = np.asarray(np.ma.getdata(raw_com), dtype=float)
        missing = np.ma.getmaskarray(raw_com)
        finite = np.isfinite(raw_values)
        if np.any(~missing & ~finite):
            findings.append("com: non-finite unmasked values")
        active = ~missing & finite
        if not np.any(active):
            findings.append("com: at least one active cloud-omega cell required")
        if not np.any(missing):
            findings.append("com: explicit sparse missing mask is required")

        psf = read_unpacked_field(fsf.variables["psf"])[0, 0]
        psf_values = np.asarray(np.ma.getdata(psf), dtype=float)
        psf_missing = np.ma.getmaskarray(psf)
        if np.any(psf_missing) or not np.all(np.isfinite(psf_values)):
            findings.append("FSF: finite PSFC is required for terrain accounting")
        else:
            levels = np.asarray(lco.variables["level"][:], dtype=float)
            background_mask = levels[:, None, None] * 100.0 <= psf_values
            background_summary = {
                "background_mask_reference": "FSF_PSF_BACKGROUND",
                "background_above_ground_cells": int(
                    np.count_nonzero(background_mask)
                ),
                "background_above_ground_active_cells": int(
                    np.count_nonzero(active[0] & background_mask)
                ),
                "background_above_ground_missing_cells": int(
                    np.count_nonzero(missing[0] & background_mask)
                ),
            }
            # Preserve the existing names as explicitly background metrics.
            details.update(
                com_total_cells=int(raw_values.size),
                com_active_cells=int(np.count_nonzero(active)),
                com_missing_cells=int(np.count_nonzero(missing)),
                above_ground_cells=background_summary["background_above_ground_cells"],
                above_ground_active_cells=background_summary[
                    "background_above_ground_active_cells"
                ],
                above_ground_missing_cells=background_summary[
                    "background_above_ground_missing_cells"
                ],
                sparse_missing_allowed_above_ground=True,
                background_mask_reference_hash=fsf_sha256,
                **background_summary,
            )
            if not np.any(active[0] & background_mask):
                findings.append("com: no active cloud-omega support above ground")

            if analysis is not None and analysis["status"] == "PASS":
                analysis_ps = read_unpacked_field(lsx.variables["ps"])[0, 0]
                analysis_ps_values = np.asarray(
                    np.ma.getdata(analysis_ps), dtype=float
                )
                analysis_mask = levels[:, None, None] * 100.0 <= analysis_ps_values
                details.update(
                    analysis_mask_reference="LSX_PS_ANALYSIS",
                    analysis_mask_reference_hash=lsx_sha256,
                    analysis_above_ground_cells=int(
                        np.count_nonzero(analysis_mask)
                    ),
                    analysis_above_ground_active_cells=int(
                        np.count_nonzero(active[0] & analysis_mask)
                    ),
                    analysis_above_ground_missing_cells=int(
                        np.count_nonzero(missing[0] & analysis_mask)
                    ),
                    analysis_mask_provenance=(
                        "same-case indexed LSX product and successful surface stage"
                    ),
                )

    return dict(details, status="FAIL" if findings else "PASS", findings=findings)


def inspect_lco_candidate(
    path: Path,
    fsf_path: Path,
    valid_time: str,
    reference_time: str,
    lsx_path: Path | None = None,
) -> dict[str, object]:
    """Check LCO using detached bytes; optional LSX supplies analysis-mask metrics."""
    paths = [Path(path).absolute(), Path(fsf_path).absolute()]
    if lsx_path is not None:
        paths.append(Path(lsx_path).absolute())
    details: dict[str, object] = {
        "scope": "LCO_CONTENT_ONLY",
        "generation_status": "BLOCKED",
        "promotion_allowed": False,
        "cloud_omega_authority": "EVIDENCE_ONLY",
        "omega_target_authority": "NO_AUTHORITY",
        "omega_target_sigma_provided": False,
        "dynamic_authority": False,
    }
    findings: list[str] = []
    try:
        stamp = datetime.fromisoformat(
            valid_time.replace("Z", "+00:00")
        ).strftime("%y%j%H%M")
        if paths[0].name != f"{stamp}.lco":
            raise ValueError("LCO filename does not match exact analysis time")
        if lsx_path is not None and paths[2].name != f"{stamp}.lsx":
            raise ValueError("LSX filename does not match exact analysis time")
        if any(forbidden_reason(item) for item in paths):
            raise ValueError("downstream/final product path")
        if len({item for item in paths}) != len(paths):
            raise ValueError("independent LCO, FSF and LSX files required")
        with detached_netcdf(paths[0]) as (lco, lco_hash), detached_netcdf(
            paths[1]
        ) as (fsf, fsf_hash):
            if lsx_path is None:
                result = _inspect_lco_datasets(
                    lco, fsf, valid_time, reference_time,
                    lco_sha256=lco_hash, fsf_sha256=fsf_hash,
                )
            else:
                with detached_netcdf(paths[2]) as (lsx, lsx_hash):
                    result = _inspect_lco_datasets(
                        lco, fsf, valid_time, reference_time,
                        lsx=lsx,
                        lco_sha256=lco_hash,
                        fsf_sha256=fsf_hash,
                        lsx_sha256=lsx_hash,
                    )
            details.update(result)
    except (OSError, ValueError, TypeError, IndexError, KeyError, RuntimeError) as error:
        findings.append(f"LCO validation error: {error}")
    if findings:
        details.update(status="FAIL", findings=findings)
    return details


def validate_file(
    workspace: Path,
    relative_path: str,
    expected_hash: str | None,
    kind: str,
    valid_time: str,
    reference_time: str,
    allowed_root: str | None = None,
) -> dict[str, object]:
    path, containment_error = contained_input(
        workspace, relative_path, kind, allowed_root
    )
    result: dict[str, object] = {"path": str(path), "kind": kind}
    if containment_error:
        result.update(status="FAIL", findings=[containment_error])
        return result
    reason = forbidden_reason(path)
    if reason:
        result.update(status="FAIL", findings=[reason])
        return result
    if not path.is_file() or path.is_symlink():
        result.update(status="MISSING", findings=["regular non-symlink file required"])
        return result
    before = path.stat()
    if before.st_nlink != 1:
        result.update(status="FAIL", findings=["hard-linked input is forbidden"])
        return result
    actual_hash = sha256(path)
    result["sha256"] = actual_hash
    if expected_hash is not None and actual_hash != expected_hash:
        result.update(status="FAIL", findings=["SHA-256 mismatch"])
        return result
    try:
        result.update(inspect_netcdf(path, kind, valid_time, reference_time))
    except Exception as error:  # a malformed file is an input failure
        result.update(status="FAIL", findings=[f"NetCDF validation error: {error}"])
    after = path.stat()
    identity_before = (
        before.st_dev, before.st_ino, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev, after.st_ino, after.st_size,
        after.st_mtime_ns, after.st_ctime_ns,
    )
    if identity_before != identity_after:
        result.update(
            status="FAIL",
            findings=["input changed between checksum and NetCDF validation"],
        )
    return result


def validate_static(workspace: Path) -> list[dict[str, object]]:
    results = []
    for relative, expected_hash in STATIC_INPUTS.items():
        path, containment_error = contained_input(
            workspace, relative, "static", str(Path(relative).parent)
        )
        status = "PASS"
        findings: list[str] = []
        if containment_error:
            status, findings = "FAIL", [containment_error]
        elif forbidden_reason(path):
            status, findings = "FAIL", ["forbidden path"]
        elif not path.is_file() or path.is_symlink():
            status, findings = "MISSING", ["regular non-symlink file required"]
        elif path.stat().st_nlink != 1:
            status, findings = "FAIL", ["hard-linked input is forbidden"]
        else:
            actual_hash = sha256(path)
            if actual_hash != expected_hash:
                status, findings = "FAIL", ["SHA-256 mismatch"]
        results.append({"path": str(path), "status": status, "findings": findings})
    return results


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def path_contains_symlink(path: Path) -> bool:
    """Return true when any existing component of an absolute path is a link."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def rooted_regular_file(root: Path, relative_path: str) -> tuple[Path, str | None]:
    """Resolve a manifest product without permitting aliases or final products."""
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        return root, "product path must be relative and cannot traverse parents"
    current = root
    if path_contains_symlink(root):
        return root, "pre-QBAL root path cannot contain a symlink"
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return current, "product path cannot contain a symlink"
    resolved_root = root.resolve()
    resolved = current.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return resolved, "product is outside the isolated pre-QBAL root"
    reason = forbidden_reason(resolved)
    if reason:
        return resolved, reason
    if not resolved.is_file():
        return resolved, "regular non-symlink file required"
    if resolved.stat().st_nlink != 1:
        return resolved, "hard-linked input is forbidden"
    return resolved, None


def load_pre_qbal_manifest(
    root: Path | None,
    expected_hash: str | None,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    """Load one externally hash-pinned, original-producer generation manifest."""
    context: dict[str, object] = {
        "status": "MISSING",
        "findings": [],
        "sha256": None,
        "cases": {},
    }
    if root is None:
        context["findings"] = [
            "original upstream regeneration root and pinned manifest are missing"
        ]
        return context
    root = root.absolute()
    if not root.is_dir() or path_contains_symlink(root):
        context["status"] = "FAIL"
        context["findings"] = [
            "pre-QBAL root must be a real directory with no symlink components"
        ]
        return context
    if not is_sha256(expected_hash):
        context["status"] = "FAIL"
        context["findings"] = [
            "an external lowercase SHA-256 pin for the generation manifest is required"
        ]
        return context

    manifest = (manifest_path or root / PRE_QBAL_MANIFEST_NAME).absolute()
    try:
        relative_manifest = manifest.relative_to(root)
    except ValueError:
        context["status"] = "FAIL"
        context["findings"] = ["generation manifest must be inside pre-QBAL root"]
        return context
    resolved_manifest, manifest_error = rooted_regular_file(
        root, relative_manifest.as_posix()
    )
    if manifest_error:
        context["status"] = "FAIL"
        context["findings"] = [f"generation manifest: {manifest_error}"]
        return context
    try:
        manifest_bytes = resolved_manifest.read_bytes()
    except OSError as error:
        context["status"] = "FAIL"
        context["findings"] = [f"generation manifest read error: {error}"]
        return context
    actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
    context["sha256"] = actual_hash
    if actual_hash != expected_hash:
        context["status"] = "FAIL"
        context["findings"] = ["generation manifest SHA-256 mismatch"]
        return context
    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        context["status"] = "FAIL"
        context["findings"] = [f"generation manifest parse error: {error}"]
        return context
    if not isinstance(document, dict):
        context["status"] = "FAIL"
        context["findings"] = ["generation manifest must be a JSON object"]
        return context

    findings: list[str] = []
    required_values = {
        "contract": PRE_QBAL_MANIFEST_CONTRACT,
        "authority": "original_klaps_source",
        "source_tree": "klaps-v5.0_",
        "compiler_family": "Intel",
    }
    for name, expected in required_values.items():
        if document.get(name) != expected:
            findings.append(f"{name}={document.get(name)!r} expected {expected!r}")
    for name in ("source_tree_sha256", "configuration_sha256"):
        if not is_sha256(document.get(name)):
            findings.append(f"{name} must be a lowercase SHA-256")
    generation_status = document.get("generation_status")
    if generation_status not in ("COMPLETE", "BLOCKED"):
        findings.append("generation_status must be COMPLETE or BLOCKED")
    elif generation_status == "COMPLETE":
        findings.append(
            "COMPLETE generation receipts are unsupported until product semantics "
            "are independently validated"
        )

    cases = document.get("cases")
    if not isinstance(cases, list):
        findings.append("cases must be an ordered array")
        cases = []
    case_identity = tuple(
        (
            item.get("case_id"),
            item.get("valid_time_utc"),
            item.get("laps_stamp"),
        )
        if isinstance(item, dict) else (None, None, None)
        for item in cases
    )
    if case_identity != EXPECTED_CASES:
        findings.append("manifest cases are not the pinned ordered four-case set")

    seen_cases: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or case_id in seen_cases:
            findings.append("case_id must be unique and nonempty")
            continue
        seen_cases.add(case_id)
        expected_case_status = (
            "COMPLETE" if generation_status == "COMPLETE" else "BLOCKED"
        )
        if item.get("status") != expected_case_status:
            findings.append(
                f"case {case_id} status={item.get('status')!r} "
                f"expected {expected_case_status!r}"
            )
        if generation_status == "COMPLETE":
            if not is_sha256(item.get("input_closure_sha256")):
                findings.append(f"case {case_id} input_closure_sha256 is invalid")
        elif item.get("input_closure_sha256") is not None:
            findings.append(
                f"case {case_id} blocked input_closure_sha256 must be null"
            )
        products = item.get("products")
        if not isinstance(products, dict):
            findings.append(f"case {case_id} products must be an object")
            continue
        if set(products) != set(PRE_QBAL_PRODUCTS):
            findings.append(
                f"case {case_id} products must be exactly "
                + ",".join(PRE_QBAL_PRODUCTS)
            )
        for kind in PRE_QBAL_PRODUCTS:
            product = products.get(kind)
            if not isinstance(product, dict):
                findings.append(f"case {case_id} product {kind} is missing")
                continue
            expected_path = f"{kind}/{item.get('laps_stamp')}.{kind}"
            expected_stage, expected_executable = PRE_QBAL_PRODUCERS[kind]
            constraints = {
                "path": expected_path,
                "source_class": "pre_qbal_intermediate",
                "valid_time_utc": item.get("valid_time_utc"),
                "producer_stage": expected_stage,
                "producer_executable": expected_executable,
            }
            for name, expected in constraints.items():
                if product.get(name) != expected:
                    findings.append(
                        f"case {case_id} {kind} {name}={product.get(name)!r} "
                        f"expected {expected!r}"
                    )
            if generation_status == "COMPLETE":
                if not is_sha256(product.get("sha256")):
                    findings.append(f"case {case_id} {kind} sha256 is invalid")
            elif (
                product.get("sha256") is not None
                or product.get("status") != "NOT_PRODUCED"
            ):
                findings.append(
                    f"case {case_id} {kind} must be NOT_PRODUCED with null sha256"
                )
            path_value = product.get("path")
            if isinstance(path_value, str):
                product_path = root / path_value
                reason = forbidden_reason(product_path)
                if reason:
                    findings.append(f"case {case_id} {kind}: {reason}")
    if findings:
        context["status"] = "FAIL"
        context["findings"] = findings
        return context
    context["status"] = "BLOCKED"
    context["findings"] = [
        "original upstream generation is BLOCKED; direct products were not produced"
    ]
    return context


def _parse_json_bytes(payload: bytes) -> tuple[object | None, str | None]:
    try:
        return json.loads(payload.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError) as error:
        return None, str(error)


def _read_json_file(path: Path) -> tuple[object | None, str | None]:
    try:
        return _parse_json_bytes(path.read_bytes())
    except OSError as error:
        return None, str(error)


def _lco_evidence_file(
    evidence_root: Path, relative_path: str
) -> tuple[Path, str | None]:
    return rooted_regular_file(evidence_root, relative_path)


def _validate_lco_producer(
    evidence_root: Path,
    stage: dict[str, object],
    staging: dict[str, object],
    findings: list[str],
) -> None:
    executable_manifest = stage.get("executable_manifest")
    if not isinstance(executable_manifest, str):
        findings.append("derived executable manifest is missing")
        return
    match = re.fullmatch(
        r"([0-9a-f]{64})\s+(.+?)\s*", executable_manifest.strip()
    )
    if match is None:
        findings.append("derived executable manifest is not a SHA-256 receipt")
        return
    expected_hash, executable_value = match.groups()
    executable = Path(executable_value)
    if not executable.is_absolute() or path_contains_symlink(executable):
        findings.append("derived executable must be an absolute non-symlink path")
        return
    if not executable.is_file() or executable.stat().st_nlink != 1:
        findings.append("derived executable must be a regular non-hardlinked file")
        return
    actual_hash = sha256(executable)
    if actual_hash != expected_hash:
        findings.append("derived executable SHA-256 does not match its receipt")
    if expected_hash != LCO_PRODUCER_SHA256:
        findings.append("derived executable SHA-256 is not the pinned producer")
    if executable.name != "klps_anal_derv.exe":
        findings.append("derived executable name is not klps_anal_derv.exe")

    build_value = stage.get("build")
    if not isinstance(build_value, str):
        findings.append("derived build directory is missing")
    else:
        build = Path(build_value)
        if not build.is_dir() or path_contains_symlink(build):
            findings.append("derived build directory must be a real directory")
        elif build.resolve() != executable.parent.resolve():
            findings.append("derived executable is outside the recorded build directory")

    runroot_value = staging.get("runroot")
    if not isinstance(runroot_value, str):
        findings.append("staging runroot is missing")
        return
    runroot = Path(runroot_value)
    inventory_path, inventory_error = _lco_evidence_file(
        evidence_root, "derived.read_inventory.json"
    )
    if inventory_error:
        findings.append(f"derived read inventory: {inventory_error}")
        return
    inventory, parse_error = _read_json_file(inventory_path)
    if parse_error or not isinstance(inventory, dict):
        findings.append(f"derived read inventory parse error: {parse_error or 'object required'}")
        return
    if inventory.get("parser_complete") is not True:
        findings.append("derived read inventory is not parser-complete")
    if inventory.get("unresolved") != []:
        findings.append("derived read inventory has unresolved paths")
    consumed = inventory.get("consumed_paths")
    expected_cdl = (runroot / "cdl" / "lco.cdl").as_posix()
    consumed_paths = (
        list(consumed.keys()) if isinstance(consumed, dict) else consumed
    )
    if not isinstance(consumed_paths, list) or expected_cdl not in consumed_paths:
        findings.append("derived read inventory does not bind the LCO CDL input")
    executed = inventory.get("executed")
    if not isinstance(executed, list) or not any(
        isinstance(item, dict)
        and "klps_anal_derv.exe" in str(item.get("call", ""))
        for item in executed
    ):
        findings.append("derived read inventory does not show klps_anal_derv.exe execution")


def _validate_lco_cdl_lineage(
    evidence_root: Path,
    staging: dict[str, object],
    findings: list[str],
) -> None:
    sources = staging.get("sources")
    if not isinstance(sources, dict):
        findings.append("staging source inventory is missing")
        return
    source_record = sources.get("cdl/lco.cdl")
    if not isinstance(source_record, dict):
        findings.append("staging source inventory lacks cdl/lco.cdl")
        return
    source_value = source_record.get("source")
    source_hash = source_record.get("sha256")
    if not isinstance(source_value, str) or not is_sha256(source_hash):
        findings.append("LCO CDL source and lowercase SHA-256 are required")
        return
    source = Path(source_value)
    if (
        not source.is_file()
        or path_contains_symlink(source)
        or source.stat().st_nlink != 1
    ):
        findings.append("LCO CDL source must be a regular non-hardlinked file")
    else:
        actual_source_hash = sha256(source)
        if actual_source_hash != source_hash:
            findings.append("LCO CDL source SHA-256 does not match staging receipt")
        if source_hash != LCO_SOURCE_CDL_SHA256:
            findings.append("LCO CDL source SHA-256 is not the pinned source")

    runroot_value = staging.get("runroot")
    if not isinstance(runroot_value, str):
        findings.append("staging runroot is missing")
        return
    runroot = Path(runroot_value)
    runroot_cdl, cdl_error = _lco_evidence_file(
        runroot, "cdl/lco.cdl"
    )
    if cdl_error:
        findings.append(f"runroot LCO CDL: {cdl_error}")
    elif sha256(runroot_cdl) != source_hash:
        findings.append("runroot LCO CDL does not match staged source bytes")


def _validate_lco_case(
    case: dict[str, object],
    expected_row: dict[str, str],
    workspace: Path,
    findings: list[str],
) -> dict[str, object]:
    case_findings: list[str] = []
    hour = case.get("hour")
    if not isinstance(hour, int) or isinstance(hour, bool):
        case_findings.append("hour must be an integer")
        return {"status": "FAIL", "findings": case_findings}
    evidence_value = case.get("evidence")
    runroot_value = case.get("runroot")
    if not isinstance(evidence_value, str) or not Path(evidence_value).is_absolute():
        case_findings.append("evidence must be an absolute path")
        return {"hour": hour, "status": "FAIL", "findings": case_findings}
    if not isinstance(runroot_value, str) or not Path(runroot_value).is_absolute():
        case_findings.append("runroot must be an absolute path")
    evidence_root = Path(evidence_value)
    if not evidence_root.is_dir() or path_contains_symlink(evidence_root):
        case_findings.append("evidence must be a real directory with no symlink components")
        return {"hour": hour, "status": "FAIL", "findings": case_findings}

    stages_path, stages_error = _lco_evidence_file(evidence_root, "stages.json")
    staging_path, staging_error = _lco_evidence_file(evidence_root, "staging.json")
    if stages_error:
        case_findings.append(f"stages receipt: {stages_error}")
    if staging_error:
        case_findings.append(f"staging receipt: {staging_error}")
    stages: object | None = None
    staging: object | None = None
    if not stages_error:
        stages, parse_error = _read_json_file(stages_path)
        if parse_error or not isinstance(stages, list):
            case_findings.append(f"stages receipt parse error: {parse_error or 'array required'}")
            stages = None
    if not staging_error:
        staging, parse_error = _read_json_file(staging_path)
        if parse_error or not isinstance(staging, dict):
            case_findings.append(f"staging receipt parse error: {parse_error or 'object required'}")
            staging = None
    if not isinstance(stages, list) or not isinstance(staging, dict):
        return {"hour": hour, "status": "FAIL", "findings": case_findings}

    if case.get("status") != "BOUNDED_FINAL_LOGGING_CASE_PASS":
        case_findings.append("case status is not a bounded final logging pass")
    if case.get("initial_inputs_byte_equal") is not True:
        case_findings.append("initial inputs are not byte-equal to the fixed baseline")
    if case.get("other_final_file_differences") != []:
        case_findings.append("final evidence reports unapproved file differences")
    if runroot_value != staging.get("runroot"):
        case_findings.append("index and staging runroot disagree")

    staging_case = staging.get("case")
    if not isinstance(staging_case, dict):
        case_findings.append("staging case identity is missing")
    else:
        for name, expected in expected_row.items():
            if staging_case.get(name) != expected:
                case_findings.append(
                    f"staging case {name}={staging_case.get(name)!r} expected {expected!r}"
                )

    indexed_stages = case.get("stages")
    if indexed_stages != stages:
        case_findings.append("index stages differ from the pinned evidence stages receipt")
    derived_candidates = [
        item for item in stages
        if isinstance(item, dict) and item.get("stage") == "derived"
    ]
    if len(derived_candidates) != 1:
        case_findings.append("exactly one derived stage receipt is required")
        return {"hour": hour, "status": "FAIL", "findings": case_findings}
    derived = derived_candidates[0]
    if derived.get("exit") != 0:
        case_findings.append("derived producer did not exit successfully")

    stamp = expected_row["laps_stamp"]
    output_relative = f"lapsprd/lco/{stamp}.lco"
    added = derived.get("added")
    changed = derived.get("changed")
    removed = derived.get("removed")
    if not isinstance(added, list):
        case_findings.append("derived receipt added output list is missing")
        added = []
    if not isinstance(changed, list):
        case_findings.append("derived receipt changed output list is missing")
        changed = []
    if not isinstance(removed, list):
        case_findings.append("derived receipt removed output list is missing")
        removed = []
    if output_relative not in added:
        case_findings.append("derived receipt does not record the expected LCO output")
    if output_relative in changed or output_relative in removed:
        case_findings.append("expected LCO output was changed or removed in the derived receipt")

    surface_candidates = [
        item for item in stages
        if isinstance(item, dict) and item.get("stage") == "surface"
    ]
    if len(surface_candidates) != 1:
        case_findings.append("exactly one surface stage receipt is required for LSX binding")
        surface = {}
    else:
        surface = surface_candidates[0]
        if surface.get("exit") != 0:
            case_findings.append("surface producer did not exit successfully")
    lsx_relative = f"lapsprd/lsx/{stamp}.lsx"
    surface_added = surface.get("added") if isinstance(surface, dict) else None
    surface_changed = surface.get("changed") if isinstance(surface, dict) else None
    surface_removed = surface.get("removed") if isinstance(surface, dict) else None
    if not isinstance(surface_added, list):
        case_findings.append("surface receipt added output list is missing")
        surface_added = []
    if not isinstance(surface_changed, list):
        case_findings.append("surface receipt changed output list is missing")
        surface_changed = []
    if not isinstance(surface_removed, list):
        case_findings.append("surface receipt removed output list is missing")
        surface_removed = []
    if lsx_relative not in surface_added:
        case_findings.append("surface receipt does not record the expected LSX output")
    if lsx_relative in surface_changed or lsx_relative in surface_removed:
        case_findings.append("expected LSX output was changed or removed in the surface receipt")

    indexed_products = case.get("netcdf_products")
    if not isinstance(indexed_products, list):
        case_findings.append("indexed NetCDF product list is missing")
        indexed_products = []
    product_entries = [
        item for item in indexed_products
        if isinstance(item, dict) and item.get("role") == "lco"
    ]
    if len(product_entries) != 1:
        case_findings.append("exactly one indexed LCO product is required")
        product_entry: dict[str, object] = {}
    else:
        product_entry = product_entries[0]
        if product_entry.get("byte_equal_to_fixed_baseline") is not True:
            case_findings.append("indexed LCO product is not byte-equal to its fixed baseline")
    lsx_product_entries = [
        item for item in indexed_products
        if isinstance(item, dict) and item.get("role") == "lsx"
    ]
    if len(lsx_product_entries) != 1:
        case_findings.append("exactly one indexed LSX product is required for analysis-mask binding")
        lsx_product_entry: dict[str, object] = {}
    else:
        lsx_product_entry = lsx_product_entries[0]
        if lsx_product_entry.get("byte_equal_to_fixed_baseline") is not True:
            case_findings.append("indexed LSX product is not byte-equal to its fixed baseline")
    output_path, output_error = _lco_evidence_file(
        evidence_root, f"final_lapsprd/lco/{stamp}.lco"
    )
    if output_error:
        case_findings.append(f"LCO output: {output_error}")
    lco_hash = product_entry.get("sha256")
    if not is_sha256(lco_hash):
        case_findings.append("indexed LCO product SHA-256 is required")

    lsx_path, lsx_error = _lco_evidence_file(
        evidence_root, f"final_lapsprd/lsx/{stamp}.lsx"
    )
    if lsx_error:
        case_findings.append(f"LSX output: {lsx_error}")
    lsx_hash = lsx_product_entry.get("sha256")
    if not is_sha256(lsx_hash):
        case_findings.append("indexed LSX product SHA-256 is required for analysis-mask binding")

    if isinstance(staging, dict):
        _validate_lco_cdl_lineage(evidence_root, staging, case_findings)
        _validate_lco_producer(evidence_root, derived, staging, case_findings)

    fsf_path, fsf_error = contained_input(
        workspace, expected_row["fsf_path"], "fsf"
    )
    if fsf_error:
        case_findings.append(f"FSF input: {fsf_error}")
    content_summary: dict[str, object] = {}
    if not output_error and not lsx_error and not fsf_error:
        try:
            with detached_netcdf(output_path, lco_hash) as (lco, accepted_lco_hash):
                with detached_netcdf(
                    fsf_path, expected_row["fsf_sha256"]
                ) as (fsf, accepted_fsf_hash):
                    if output_path.samefile(fsf_path):
                        raise ValueError("independent LCO and FSF files required")
                    with detached_netcdf(lsx_path, lsx_hash) as (
                        lsx, accepted_lsx_hash
                    ):
                        if output_path.samefile(lsx_path) or fsf_path.samefile(lsx_path):
                            raise ValueError("independent LCO, FSF and LSX files required")
                        content = _inspect_lco_datasets(
                            lco,
                            fsf,
                            expected_row["valid_time_utc"],
                            expected_row["background_reftime_utc"],
                            lsx=lsx,
                            lco_sha256=accepted_lco_hash,
                            fsf_sha256=accepted_fsf_hash,
                            lsx_sha256=accepted_lsx_hash,
                        )
                        case_findings.extend(
                            f"LCO content: {item}" for item in content["findings"]
                        )
                        content_summary = {
                            name: content[name]
                            for name in (
                                "lco_sha256",
                                "fsf_sha256",
                                "lsx_sha256",
                                "com_active_cells",
                                "com_missing_cells",
                                "above_ground_cells",
                                "above_ground_active_cells",
                                "above_ground_missing_cells",
                                "sparse_missing_allowed_above_ground",
                                "background_mask_reference",
                                "background_mask_reference_hash",
                                "background_above_ground_cells",
                                "background_above_ground_active_cells",
                                "background_above_ground_missing_cells",
                                "analysis_mask_reference",
                                "analysis_mask_reference_hash",
                                "analysis_above_ground_cells",
                                "analysis_above_ground_active_cells",
                                "analysis_above_ground_missing_cells",
                                "analysis_mask_provenance",
                            )
                            if name in content
                        }
        except (OSError, ValueError, TypeError, IndexError, KeyError, RuntimeError) as error:
            message = str(error)
            if "SHA-256 mismatch" in message and isinstance(lco_hash, str):
                case_findings.append(
                    "indexed LCO SHA-256 does not match final output bytes"
                )
            else:
                case_findings.append(f"LCO content snapshot: {message}")
    result: dict[str, object] = {
        "hour": hour,
        "case_id": expected_row["case_id"],
        "valid_time_utc": expected_row["valid_time_utc"],
        "reference_time_utc": expected_row["valid_time_utc"],
        "background_reftime_utc": expected_row["background_reftime_utc"],
        "evidence": str(evidence_root),
        "status": "FAIL" if case_findings else "PASS",
        "findings": case_findings,
        "cloud_omega_authority": "EVIDENCE_ONLY",
        "omega_target_authority": "NO_AUTHORITY",
        "omega_target_sigma_provided": False,
        "dynamic_authority": False,
    }
    result.update(content_summary)
    return result


def validate_lco_evidence(
    index_path: Path,
    workspace: Path,
    rows: list[dict[str, str]],
    expected_index_hash: str | None,
) -> dict[str, object]:
    """Validate final four-case LCO receipts without granting target authority."""
    context: dict[str, object] = {
        "contract": LCO_EVIDENCE_CONTRACT,
        "status": "MISSING",
        "generation_status": "BLOCKED",
        "promotion_allowed": False,
        "cloud_omega_authority": "EVIDENCE_ONLY",
        "omega_target_authority": "NO_AUTHORITY",
        "omega_target_sigma_provided": False,
        "dynamic_authority": False,
        "findings": [],
        "cases": [],
    }
    findings: list[str] = []
    index_path = Path(index_path).absolute()
    if not is_sha256(expected_index_hash):
        findings.append("an external lowercase SHA-256 pin for the LCO evidence index is required")
    if (
        not index_path.is_file()
        or path_contains_symlink(index_path)
        or index_path.stat().st_nlink != 1
    ):
        findings.append("LCO evidence index must be a regular non-hardlinked file")
    elif is_sha256(expected_index_hash):
        try:
            index_bytes = index_path.read_bytes()
        except OSError as error:
            findings.append(f"LCO evidence index read error: {error}")
            index_bytes = b""
        actual_hash = hashlib.sha256(index_bytes).hexdigest()
        context["sha256"] = actual_hash
        if actual_hash != expected_index_hash:
            findings.append("LCO evidence index SHA-256 mismatch")
    if findings:
        context.update(status="FAIL", findings=findings)
        return context

    document, parse_error = _parse_json_bytes(index_bytes)
    if parse_error or not isinstance(document, list):
        context.update(
            status="FAIL",
            findings=[f"LCO evidence index parse error: {parse_error or 'ordered array required'}"],
        )
        return context
    expected_rows = {int(row["valid_time_utc"][11:13]): row for row in rows}
    if tuple(
        (row.get("case_id"), row.get("valid_time_utc"), row.get("laps_stamp"))
        for row in rows
    ) != EXPECTED_CASES:
        findings.append("prepared-case manifest identity is not the pinned four-case set")
    expected_identity = tuple(
        (
            int(row["valid_time_utc"][11:13]),
            row["case_id"],
            row["valid_time_utc"],
        )
        for row in rows
    )
    actual_identity_items: list[tuple[object, object, object]] = []
    for item in document:
        if not isinstance(item, dict):
            actual_identity_items.append((None, None, None))
            continue
        hour = item.get("hour")
        expected = expected_rows.get(hour) if isinstance(hour, int) else None
        actual_identity_items.append(
            (
                hour,
                expected.get("case_id") if expected else None,
                expected.get("valid_time_utc") if expected else None,
            )
        )
    actual_identity = tuple(actual_identity_items)
    if len(document) != 4 or actual_identity != expected_identity:
        findings.append("LCO evidence index is not the pinned ordered four-case set")
    cases: list[dict[str, object]] = []
    if not findings:
        for item in document:
            try:
                row = expected_rows[item["hour"]]
                cases.append(_validate_lco_case(item, row, workspace, findings))
            except (KeyError, TypeError, ValueError, OSError) as error:
                findings.append(f"LCO evidence case validation error: {error}")
                cases.append({"status": "FAIL", "findings": [str(error)]})
    context["cases"] = cases
    if findings or any(item["status"] != "PASS" for item in cases):
        if not findings:
            findings.append("one or more LCO evidence cases failed validation")
        context.update(status="FAIL", findings=findings)
        return context
    context.update(
        status="PASS",
        findings=[
            "all four final LCO outputs pass content and producer/output lineage checks; "
            "COM remains cloud-omega evidence only"
        ],
    )
    return context


def validate_pre_qbal(
    root: Path | None,
    row: dict[str, str],
    manifest_context: dict[str, object],
) -> list[dict[str, object]]:
    del root, row  # COMPLETE execution has no authority until replay is implemented.
    status = (
        "MISSING"
        if manifest_context["status"] in ("MISSING", "BLOCKED") else "FAIL"
    )
    reason = "; ".join(str(item) for item in manifest_context["findings"])
    return [
        {"kind": product, "status": status, "findings": [reason]}
        for product in PRE_QBAL_PRODUCTS
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    script_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--workspace-root", type=Path, default=script_root.parent,
        help="KLAPS50 root containing ANAL and klaps-v5.0_",
    )
    parser.add_argument(
        "--manifest", type=Path,
        default=script_root / "tests/qbal_real_cases_20260816.tsv",
    )
    parser.add_argument(
        "--pre-qbal-root", type=Path,
        help="isolated lapsprd root containing regenerated lt1/lq3/lw3/lco/lsx",
    )
    parser.add_argument(
        "--pre-qbal-manifest", type=Path,
        help=(
            "generation manifest inside --pre-qbal-root; defaults to "
            f"{PRE_QBAL_MANIFEST_NAME}"
        ),
    )
    parser.add_argument(
        "--pre-qbal-manifest-sha256",
        help="externally recorded lowercase SHA-256 of the generation manifest",
    )
    parser.add_argument(
        "--lco-evidence-index", type=Path,
        help="final four-case derived LCO evidence index",
    )
    parser.add_argument(
        "--lco-evidence-index-sha256",
        help="externally recorded lowercase SHA-256 of the LCO evidence index",
    )
    parser.add_argument("--inspect-lt1", type=Path, help="read-only LT1 content check; no generation authority")
    parser.add_argument("--inspect-lsx", type=Path, help="read-only LSX T/PS check; no generation authority")
    parser.add_argument("--case-id", choices=[case[0] for case in EXPECTED_CASES])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace_root.resolve()
    manifest_hash = sha256(args.manifest)
    with args.manifest.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    case_identity = tuple(
        (row.get("case_id"), row.get("valid_time_utc"), row.get("laps_stamp"))
        for row in rows
    )
    if manifest_hash != EXPECTED_MANIFEST_SHA256 or case_identity != EXPECTED_CASES:
        json.dump(
            {
                "contract": "original_qbal_real_input_v1",
                "overall_status": "FAIL",
                "manifest_sha256": manifest_hash,
                "findings": ["prepared-case manifest identity is not the pinned four-case set"],
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2
    if args.inspect_lt1 is not None or args.inspect_lsx is not None:
        result = {"status": "FAIL", "generation_status": "BLOCKED", "promotion_allowed": False}
        try:
            if args.inspect_lt1 is not None and args.inspect_lsx is not None:
                raise ValueError("choose exactly one content inspection")
            kind = "lsx" if args.inspect_lsx is not None else "lt1"
            if args.case_id is None:
                raise ValueError(f"--inspect-{kind} requires --case-id")
            if any(value is not None for value in (args.pre_qbal_root, args.pre_qbal_manifest, args.pre_qbal_manifest_sha256)):
                raise ValueError("content inspection cannot be combined with generation options")
            row = next(row for row in rows if row["case_id"] == args.case_id)
            fsf, error = contained_input(workspace, row["fsf_path"], "fsf")
            if error:
                raise ValueError(error)
            paths = ((args.inspect_lsx if kind == "lsx" else args.inspect_lt1).absolute(), fsf)
            reason = forbidden_reason(paths[0])
            if reason:
                raise ValueError(reason)
            if any(not path.is_file() or path_contains_symlink(path) or path.stat().st_nlink != 1 for path in paths):
                raise ValueError("regular non-hardlinked files required")
            before = [sha256(path) for path in paths]
            if before[1] != row["fsf_sha256"]:
                raise ValueError("FSF does not match pinned case hash")
            inspector = inspect_lsx_candidate if kind == "lsx" else inspect_lt1_candidate
            result = inspector(*paths, row["valid_time_utc"], row["background_reftime_utc"])
            result.update(case_id=args.case_id, fsf_sha256=before[1])
            result[f"{kind}_sha256"] = before[0]
            if before != [sha256(path) for path in paths]:
                result.update(status="FAIL", findings=result["findings"] + ["inputs changed during inspection"])
        except (OSError, ValueError) as error:
            result.update(status="FAIL", findings=[str(error)])
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if result["status"] == "PASS" else 2
    if args.case_id is not None:
        raise SystemExit("--case-id requires --inspect-lt1 or --inspect-lsx")
    pre_qbal_manifest_path = args.pre_qbal_manifest
    if (
        pre_qbal_manifest_path is not None
        and not pre_qbal_manifest_path.is_absolute()
        and args.pre_qbal_root is not None
    ):
        pre_qbal_manifest_path = args.pre_qbal_root / pre_qbal_manifest_path
    pre_qbal_manifest = load_pre_qbal_manifest(
        args.pre_qbal_root,
        args.pre_qbal_manifest_sha256,
        pre_qbal_manifest_path,
    )
    lco_evidence = None
    if args.lco_evidence_index is not None:
        lco_evidence = validate_lco_evidence(
            args.lco_evidence_index,
            workspace,
            rows,
            args.lco_evidence_index_sha256,
        )
    static_results = validate_static(workspace)
    cases = []
    prepared_failure = any(item["status"] != "PASS" for item in static_results)
    direct_failure = (
        pre_qbal_manifest["status"] == "FAIL"
        or (lco_evidence is not None and lco_evidence["status"] == "FAIL")
    )
    for row in rows:
        prepared = []
        for kind in ("fua", "fsf", "lw3", "vrz", "vrt"):
            prepared.append(
                validate_file(
                    workspace, row[f"{kind}_path"], row[f"{kind}_sha256"],
                    kind, row["valid_time_utc"],
                    row["background_reftime_utc"]
                    if kind in ("fua", "fsf") else row["valid_time_utc"],
                )
            )
        pre_qbal = validate_pre_qbal(
            args.pre_qbal_root, row, pre_qbal_manifest
        )
        case_prepared_ok = all(item["status"] == "PASS" for item in prepared)
        case_direct_ok = all(item["status"] == "PASS" for item in pre_qbal)
        prepared_failure = prepared_failure or not case_prepared_ok
        if pre_qbal_manifest["status"] == "PASS" and not case_direct_ok:
            direct_failure = True
        direct_status = "PASS" if case_direct_ok else "BLOCKED"
        if any(item["status"] == "FAIL" for item in pre_qbal):
            direct_status = "FAIL"
        cases.append(
            {
                "case_id": row["case_id"],
                "valid_time_utc": row["valid_time_utc"],
                "prepared_status": "PASS" if case_prepared_ok else "FAIL",
                "direct_qbal_status": direct_status,
                "prepared": prepared,
                "pre_qbal": pre_qbal,
            }
        )

    if prepared_failure or direct_failure:
        overall, exit_status = "FAIL", 2
    else:
        overall, exit_status = "BLOCKED_PENDING_ORIGINAL_UPSTREAM_REGENERATION", 3
    report = {
        "contract": "original_qbal_real_input_v1",
        "authority": "original_klaps_source",
        "final_bigfile_allowed_as_input": False,
        "manifest_sha256": manifest_hash,
        "pre_qbal_generation_manifest": {
            "path": str(
                pre_qbal_manifest_path
                or (
                    args.pre_qbal_root / PRE_QBAL_MANIFEST_NAME
                    if args.pre_qbal_root is not None else ""
                )
            ),
            "expected_sha256": args.pre_qbal_manifest_sha256,
            "actual_sha256": pre_qbal_manifest["sha256"],
            "status": pre_qbal_manifest["status"],
            "findings": pre_qbal_manifest["findings"],
        },
        "overall_status": overall,
        "static": static_results,
        "cases": cases,
    }
    if lco_evidence is not None:
        report["lco_evidence"] = lco_evidence
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
