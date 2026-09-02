#!/usr/bin/env python3
"""Validate prepared real inputs and the original pre-QBAL read closure."""

from __future__ import annotations

import argparse
import csv
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
    "u3": (-200.0, 200.0),
    "v3": (-200.0, 200.0),
    "t3": (150.0, 350.0),
    "tsf": (150.0, 350.0),
    "ht": (-1000.0, 60000.0),
    "sh": (0.0, 0.1),
    "om": (-20000.0, 20000.0),
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


def inspect_netcdf(
    path: Path, kind: str, valid_time: str, reference_time: str
) -> dict[str, object]:
    spec = FILE_SPECS[kind]
    findings: list[str] = []
    details: dict[str, object] = {}
    with netCDF4.Dataset(path, "r") as dataset:
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
            values = np.ma.asarray(variable[:])
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
    static_results = validate_static(workspace)
    cases = []
    prepared_failure = any(item["status"] != "PASS" for item in static_results)
    direct_failure = pre_qbal_manifest["status"] == "FAIL"
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
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
