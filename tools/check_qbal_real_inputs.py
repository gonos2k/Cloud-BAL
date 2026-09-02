#!/usr/bin/env python3
"""Validate prepared real inputs and the original pre-QBAL read closure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import netCDF4
import numpy as np


FORBIDDEN_PARTS = ("bigfile", "lapsprep/wps", "/balance/", "met_em")
FORBIDDEN_NAMES = ("LAPS:", "KLBG:")
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
    "lt1": {
        "z": 22,
        "variables": {"ht": ("meters",), "t3": ("degreeskelvin",)},
    },
    "lq3": {"z": 22, "variables": {"sh": ("kg/kg",)}},
    "lco": {"z": 22, "variables": {"com": ("pascals/second",)}},
    "lsx": {"z": 1, "variables": {"ps": ("pascals",)}},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_units(value: object) -> str:
    return "".join(str(value).strip().lower().split())


def forbidden_reason(path: Path) -> str | None:
    text = path.as_posix()
    lowered = text.lower()
    if any(part.lower() in lowered for part in FORBIDDEN_PARTS):
        return "downstream/final product path"
    if any(path.name.lower().startswith(prefix.lower()) for prefix in FORBIDDEN_NAMES):
        return "merged final product name"
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


def inspect_netcdf(
    path: Path, kind: str, valid_time: str, reference_time: str
) -> dict[str, object]:
    spec = FILE_SPECS[kind]
    findings: list[str] = []
    details: dict[str, object] = {}
    with netCDF4.Dataset(path, "r") as dataset:
        dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
        details["dimensions"] = dimensions
        for name, size in (("x", 235), ("y", 283), ("z", spec["z"])):
            if dimensions.get(name) != size:
                findings.append(f"dimension {name}={dimensions.get(name)} expected {size}")
        if dimensions.get("record") != 1:
            findings.append(f"record={dimensions.get('record')} expected 1")

        for variable_name, accepted_units in spec["variables"].items():
            variable = dataset.variables.get(variable_name)
            if variable is None:
                findings.append(f"missing variable {variable_name}")
                continue
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

        epoch = expected_epoch(valid_time)
        valtime = dataset.variables.get("valtime")
        if valtime is None or valtime.size != 1:
            findings.append("missing scalar valtime")
        else:
            actual_valtime = float(np.asarray(valtime[:]).reshape(-1)[0])
            details["valtime"] = actual_valtime
            if abs(actual_valtime - epoch) > 0.5:
                findings.append(f"valtime={actual_valtime} expected {epoch}")

        reference_epoch = expected_epoch(reference_time)
        reftime = dataset.variables.get("reftime")
        if reftime is None or reftime.size != 1:
            findings.append("missing scalar reftime")
        else:
            actual_reftime = float(np.asarray(reftime[:]).reshape(-1)[0])
            details["reftime"] = actual_reftime
            if abs(actual_reftime - reference_epoch) > 0.5:
                findings.append(
                    f"reftime={actual_reftime} expected {reference_epoch}"
                )

        if spec["z"] == 22:
            level = dataset.variables.get("level")
            if level is None:
                findings.append("missing pressure level coordinate")
            else:
                values = np.asarray(level[:], dtype=float).reshape(-1)
                details["level_hpa"] = values.tolist()
                if values.shape != PRESSURE_LEVELS_HPA.shape or not np.allclose(
                    values, PRESSURE_LEVELS_HPA, rtol=0.0, atol=1.0e-5
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
    actual_hash = sha256(path)
    result["sha256"] = actual_hash
    if expected_hash is not None and actual_hash != expected_hash:
        result.update(status="FAIL", findings=["SHA-256 mismatch"])
        return result
    try:
        result.update(inspect_netcdf(path, kind, valid_time, reference_time))
    except Exception as error:  # a malformed file is an input failure
        result.update(status="FAIL", findings=[f"NetCDF validation error: {error}"])
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
        else:
            actual_hash = sha256(path)
            if actual_hash != expected_hash:
                status, findings = "FAIL", ["SHA-256 mismatch"]
        results.append({"path": str(path), "status": status, "findings": findings})
    return results


def validate_pre_qbal(
    root: Path | None, row: dict[str, str]
) -> list[dict[str, object]]:
    products = ("lt1", "lq3", "lw3", "lco", "lsx")
    reason = (
        "hash-pinned original-upstream generation manifest is required; "
        "pathname and NetCDF schema cannot prove pre-QBAL lineage"
    )
    if root is None:
        reason = "original upstream regeneration root and pinned manifest are missing"
    return [
        {"kind": product, "status": "MISSING", "findings": [reason]}
        for product in products
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Preserve the lexical root so a symlinked workspace cannot hide aliases.
    workspace = args.workspace_root.absolute()
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
    static_results = validate_static(workspace)
    cases = []
    prepared_failure = any(item["status"] != "PASS" for item in static_results)
    direct_complete = True
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
        pre_qbal = validate_pre_qbal(args.pre_qbal_root, row)
        case_prepared_ok = all(item["status"] == "PASS" for item in prepared)
        case_direct_ok = all(item["status"] == "PASS" for item in pre_qbal)
        prepared_failure = prepared_failure or not case_prepared_ok
        direct_complete = direct_complete and case_direct_ok
        cases.append(
            {
                "case_id": row["case_id"],
                "valid_time_utc": row["valid_time_utc"],
                "prepared_status": "PASS" if case_prepared_ok else "FAIL",
                "direct_qbal_status": "PASS" if case_direct_ok else "BLOCKED",
                "prepared": prepared,
                "pre_qbal": pre_qbal,
            }
        )

    if prepared_failure:
        overall, exit_status = "FAIL", 2
    elif not direct_complete:
        overall, exit_status = "BLOCKED_PENDING_ORIGINAL_UPSTREAM_REGENERATION", 3
    else:
        overall, exit_status = "READY_FOR_ISOLATED_QBAL_SHADOW", 0
    report = {
        "contract": "original_qbal_real_input_v1",
        "authority": "original_klaps_source",
        "final_bigfile_allowed_as_input": False,
        "manifest_sha256": manifest_hash,
        "overall_status": overall,
        "static": static_results,
        "cases": cases,
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
