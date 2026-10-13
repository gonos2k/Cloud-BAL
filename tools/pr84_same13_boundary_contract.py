#!/usr/bin/env python3
"""Read-only contract check for same13 KDM6 scalar boundary carriers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


SUFFIXES = ("_BXS", "_BXE", "_BYS", "_BYE",
            "_BTXS", "_BTXE", "_BTYS", "_BTYE")
PAIRS = (("QCLOUD", "QNCLOUD"), ("QICE", "QNICE"),
         ("QRAIN", "QNRAIN"), ("QGRAUP", "QIB"))
WATER_MASSES = ("QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP")
KDM6_MOMENTS = ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
BOUNDARY_UNITS = {
    **{name: "kg kg-1" for name in WATER_MASSES},
    "QNCCN": "kg(-1)", "QNCLOUD": "kg(-1)", "QNICE": "kg-1",
    "QNRAIN": "kg(-1)", "QIB": "m(3) kg(-1)",
}
RETAINED_EMPTY_BOUNDARY_SHA256 = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize_boundary(path: Path, *,
                       expected_empty_sha256: str = RETAINED_EMPTY_BOUNDARY_SHA256
                       ) -> dict[str, object]:
    """Read one wrfbdy file and report carrier availability and pair support."""
    before = sha256(path)
    carriers = tuple(dict.fromkeys((*WATER_MASSES, *KDM6_MOMENTS)))
    fields: dict[str, dict[str, object]] = {}
    missing: list[str] = []
    invalid_units: list[str] = []
    invalid_geometry: list[str] = []
    invalid_values: dict[str, list[str]] = {}
    pair_violations: list[str] = []
    with Dataset(path, "r") as boundary:
        if "Time" not in boundary.dimensions or "bdy_width" not in boundary.dimensions:
            raise ValueError("wrfbdy requires Time and bdy_width dimensions")
        times = ["".join(value.decode() for value in row).rstrip()
                 for row in boundary.variables["Times"][:]]
        width = len(boundary.dimensions["bdy_width"])
        time_contract_pass = times == ["2026-08-16_13:00:00", "2026-08-16_14:00:00"]
        geometry_contract_pass = (
            len(boundary.dimensions["Time"]) == 2 and width == 5
            and len(boundary.dimensions["bottom_top"]) == 39
            and len(boundary.dimensions["south_north"]) == 282
            and len(boundary.dimensions["west_east"]) == 234
        )
        for base in carriers:
            for suffix in SUFFIXES:
                name = base + suffix
                variable = boundary.variables.get(name)
                if variable is None:
                    missing.append(name)
                    continue
                raw = variable[:]
                reasons: list[str] = []
                masked_data = None
                if np.ma.isMaskedArray(raw):
                    mask = np.ma.getmaskarray(raw)
                    if np.any(mask):
                        reasons.append("masked")
                        masked_data = np.ma.getdata(raw)
                        for attribute in ("_FillValue", "missing_value"):
                            if attribute not in variable.ncattrs():
                                continue
                            sentinels = np.asarray(variable.getncattr(attribute)).reshape(-1)
                            if any(np.any(masked_data == sentinel) for sentinel in sentinels):
                                reasons.append(attribute)
                        values = None
                    else:
                        values = np.asarray(raw)
                else:
                    values = np.asarray(raw)
                if values is not None:
                    for attribute in ("_FillValue", "missing_value"):
                        if attribute not in variable.ncattrs():
                            continue
                        sentinels = np.asarray(variable.getncattr(attribute)).reshape(-1)
                        for sentinel in sentinels:
                            try:
                                equals_sentinel = (np.isnan(values) if np.isnan(sentinel)
                                                   else values == sentinel)
                            except TypeError:
                                equals_sentinel = values == sentinel
                            if np.any(equals_sentinel):
                                reasons.append(attribute)
                                break
                    if not np.all(np.isfinite(values)):
                        reasons.append("nonfinite")
                if reasons:
                    invalid_values[name] = reasons
                units = getattr(variable, "units", None)
                units_valid = isinstance(units, str) and units.strip() == BOUNDARY_UNITS[base]
                if not units_valid:
                    invalid_units.append(name)
                expected_dims = (("Time", "bdy_width", "bottom_top", "south_north")
                                 if suffix.endswith(("BXS", "BXE", "BTXS", "BTXE")) else
                                 ("Time", "bdy_width", "bottom_top", "west_east"))
                if tuple(variable.dimensions) != expected_dims:
                    invalid_geometry.append(name)
                fields[name] = {
                    "shape": list(raw.shape),
                    "units": units,
                    "units_valid": units_valid,
                    "nonzero_count": int(np.count_nonzero(values)) if values is not None else None,
                    "min": float(np.min(values)) if values is not None else None,
                    "max": float(np.max(values)) if values is not None else None,
                }
        # Check boundary state snapshots (B), not BT tendencies: microphysics
        # may change mass and number tendencies independently.
        for mass, moment in PAIRS:
            for suffix in SUFFIXES[:4]:
                mass_name, moment_name = mass + suffix, moment + suffix
                if mass_name not in boundary.variables or moment_name not in boundary.variables:
                    continue
                q_raw, n_raw = boundary.variables[mass_name][:], boundary.variables[moment_name][:]
                if (np.ma.isMaskedArray(q_raw) and np.any(np.ma.getmaskarray(q_raw))) or (
                        np.ma.isMaskedArray(n_raw) and np.any(np.ma.getmaskarray(n_raw))):
                    continue
                q, n = np.asarray(q_raw), np.asarray(n_raw)
                if np.any(q < 0):
                    pair_violations.append(f"negative:{mass_name}")
                if np.any(n < 0):
                    pair_violations.append(f"negative:{moment_name}")
                if np.any((q > 0) & (n == 0)):
                    pair_violations.append(f"positive_mass_zero_moment:{mass_name}:{moment_name}")
                if np.any((q == 0) & (n > 0)):
                    pair_violations.append(f"zero_mass_positive_moment:{mass_name}:{moment_name}")
    after = sha256(path)
    all_zero = bool(fields) and all(field["nonzero_count"] == 0 for field in fields.values())
    structural_pass = (time_contract_pass and geometry_contract_pass and not missing
                       and not invalid_units and not invalid_geometry and not invalid_values
                       and not pair_violations)
    retained_empty_pass = (structural_pass and all_zero and before == expected_empty_sha256
                           and after == expected_empty_sha256)
    return {
        "schema": "pr84_same13_boundary_contract_v1",
        "path": str(path.resolve()),
        "sha256_before": before,
        "sha256_after": after,
        "read_only_integrity": before == after,
        "times": times,
        "time_contract_pass": time_contract_pass,
        "geometry_contract_pass": geometry_contract_pass,
        "bdy_width": width,
        "water_mass_fields": list(WATER_MASSES),
        "kdm6_moment_fields": list(KDM6_MOMENTS),
        "unpaired_ccn_carrier": "QNCCN",
        "field_count_expected": len(carriers) * len(SUFFIXES),
        "field_count_observed": len(fields),
        "missing_fields": missing,
        "invalid_units": invalid_units,
        "invalid_geometry": invalid_geometry,
        "invalid_values": invalid_values,
        "expected_boundary_units": BOUNDARY_UNITS,
        "fields": fields,
        "positive_mass_zero_moment_boundary_pairs": pair_violations,
        "all_boundary_carriers_zero": all_zero,
        "forcing_state": "empty_zero_zero" if all_zero else "populated_or_mixed",
        "structural_pass": structural_pass,
        "retained_empty_boundary_sha256_required": expected_empty_sha256,
        "empty_forcing_pair_support": retained_empty_pass,
        "positive_boundary_pair_requires_source_review": not all_zero,
        "support_pass": retained_empty_pass,
        "status": ("PASS_RETAINED_EMPTY_BOUNDARY" if retained_empty_pass
                   else "BLOCKED_BOUNDARY_SUPPORT"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrfbdy", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize_boundary(args.wrfbdy.resolve(strict=True))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if result["support_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
