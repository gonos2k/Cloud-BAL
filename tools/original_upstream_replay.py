#!/usr/bin/env python3
"""Fail-closed isolated planner for the original KLAPS pre-QBAL replay.

This tool never treats a renamed final product as an upstream input.  It
materializes only hash-declared regular files into a new scratch generation,
checks the Intel executable identity and VRT completion, and writes a manifest
even when the original upstream chain cannot safely be started.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT = "original_klaps_pre_qbal_generation_v1"
AUTHORITY = "original_klaps_source"
DEFAULT_REPLAY_SPEC_SHA256 = (
    "4675d18e7b1bccd6716b85c4310cef0ee4e3413f5cc16c1c6da1ea6897953bfb"
)
EXPECTED_CASES = (
    ("20260816T120000Z", "2026-08-16T12:00:00Z", "262281200"),
    ("20260816T130000Z", "2026-08-16T13:00:00Z", "262281300"),
    ("20260816T140000Z", "2026-08-16T14:00:00Z", "262281400"),
    ("20260816T150000Z", "2026-08-16T15:00:00Z", "262281500"),
)
CASE_INPUTS = ("fua", "fsf", "lw3", "vrz", "vrt")
CASE_ALLOWED_ROOTS = {
    "fua": "ANAL/NE57/DAOU/00/lapsprd/fua/wrf",
    "fsf": "ANAL/NE57/DAOU/00/lapsprd/fsf/wrf",
    "lw3": "klaps-v5.0_/baseline/20260831_wind_multitime/results",
    "vrz": "ANAL/NE57/DAOU/00/lapsprd/vrz",
    "vrt": "ANAL/NE57/DAOU/00/lapsprd/vrt",
}
PRODUCT_STAGE = {
    "lt1": ("temperature_analysis", "klps_anal_temp.exe"),
    "lq3": ("humidity_analysis", "klps_anal_humd.exe"),
    "lw3": ("wind_analysis", "klps_anal_wind_openmp.exe"),
    "lco": ("derived_cloud_analysis", "klps_anal_derv.exe"),
    "lsx": ("surface_analysis", "klps_anal_lsfc.exe"),
}
STAGE_SEQUENCE = (
    "wind_analysis",
    "surface_analysis",
    "vrt_complete_gate",
    "temperature_analysis",
    "cloud_analysis",
    "humidity_analysis",
    "derived_cloud_analysis",
)
STAGE_PRODUCT = {
    "wind_analysis": "lw3",
    "surface_analysis": "lsx",
    "vrt_complete_gate": None,
    "temperature_analysis": "lt1",
    "cloud_analysis": None,
    "humidity_analysis": "lq3",
    "derived_cloud_analysis": "lco",
}
STAGE_EXECUTABLE = {
    "wind_analysis": "klps_anal_wind_openmp.exe",
    "surface_analysis": "klps_anal_lsfc.exe",
    "temperature_analysis": "klps_anal_temp.exe",
    "cloud_analysis": "klps_anal_clod.exe",
    "humidity_analysis": "klps_anal_humd.exe",
    "derived_cloud_analysis": "klps_anal_derv.exe",
}
FORBIDDEN_PARTS = (
    "bigfile",
    "lapsprep/wps",
    "/balance/",
    "met_em",
)
FORBIDDEN_PREFIXES = ("laps:", "klbg:")
HEX64 = set("0123456789abcdef")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
UTC_EPOCH_UNITS = "seconds since (1970-1-1 00:00:00.0)"
VRT_MIN_ACTIVE_FRACTION = 0.005
BLOCKED_MANIFEST_ROOT: Path | None = None


class ReplayError(RuntimeError):
    """The requested replay violates the immutable scratch contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_units(value: object) -> str:
    return "".join(str(value).strip().lower().split())


def write_manifest(output_root: Path, manifest: dict[str, object]) -> Path:
    path = output_root / "PRE_QBAL_MANIFEST.json"
    temporary = output_root / ".PRE_QBAL_MANIFEST.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def product_receipts(
    row: dict[str, str], status: str
) -> dict[str, dict[str, object]]:
    products: dict[str, dict[str, object]] = {}
    for kind, (stage, executable) in PRODUCT_STAGE.items():
        receipt: dict[str, object] = {
            "path": f"{kind}/{row['laps_stamp']}.{kind}",
            "sha256": None,
            "source_class": "pre_qbal_intermediate",
            "valid_time_utc": row["valid_time_utc"],
            "producer_stage": stage,
            "producer_executable": executable,
        }
        if status != "COMPLETE":
            receipt["status"] = "NOT_PRODUCED"
        products[kind] = receipt
    return products


def minimal_blocked_manifest(reason: str) -> dict[str, object]:
    cases = []
    for case_id, valid_time, laps_stamp in EXPECTED_CASES:
        row = {"valid_time_utc": valid_time, "laps_stamp": laps_stamp}
        cases.append(
            {
                "case_id": case_id,
                "valid_time_utc": valid_time,
                "laps_stamp": laps_stamp,
                "status": "BLOCKED",
                "input_closure_sha256": None,
                "products": product_receipts(row, "BLOCKED"),
                "blockers": [reason],
            }
        )
    return {
        "contract": CONTRACT,
        "authority": AUTHORITY,
        "source_tree": "klaps-v5.0_",
        "source_tree_sha256": canonical_sha256([]),
        "compiler_family": "Intel",
        "configuration_sha256": canonical_sha256([]),
        "generation_status": "BLOCKED",
        "execution_requested": False,
        "execution_started": False,
        "final_bigfile_allowed_as_input": False,
        "promotion_eligible": False,
        "blockers": [reason],
        "cases": cases,
    }


def is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= HEX64
    )


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ReplayError(f"unsafe relative path: {value!r}")
    return path


def safe_identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value) or value in {".", ".."}:
        raise ReplayError(f"unsafe identifier: {value!r}")
    return value


def forbidden_input(value: str) -> str | None:
    normalized = "/" + PurePosixPath(value).as_posix().lower().strip("/") + "/"
    name = PurePosixPath(value).name.lower()
    if any(part in normalized for part in FORBIDDEN_PARTS):
        return "FORBIDDEN_DOWNSTREAM_OR_FINAL_INPUT"
    if any(
        part.lower().startswith(prefix)
        for part in PurePosixPath(value).parts
        for prefix in FORBIDDEN_PREFIXES
    ):
        return "FORBIDDEN_MERGED_FINAL_INPUT"
    return None


def contained_regular(workspace: Path, relative: str) -> tuple[Path, str | None]:
    try:
        parts = safe_relative(relative).parts
    except ReplayError as error:
        return workspace, str(error)
    current = workspace
    for part in parts:
        current /= part
        if current.is_symlink():
            return current, "SOURCE_PATH_CONTAINS_SYMLINK"
    path = workspace.joinpath(*parts)
    try:
        path.resolve(strict=False).relative_to(workspace.resolve(strict=True))
    except (OSError, ValueError):
        return path, "SOURCE_PATH_ESCAPES_WORKSPACE"
    if not path.is_file() or path.is_symlink():
        return path, "SOURCE_REGULAR_FILE_MISSING"
    if path.stat(follow_symlinks=False).st_nlink != 1:
        return path, "SOURCE_HARDLINK_FORBIDDEN"
    return path, None


def contained_directory(workspace: Path, relative: str) -> tuple[Path, str | None]:
    """Resolve one declared directory without following any path symlink."""
    try:
        parts = safe_relative(relative).parts
    except ReplayError as error:
        return workspace, str(error)
    path = workspace
    for part in parts:
        path /= part
        if path.is_symlink():
            return path, "SOURCE_TREE_PATH_CONTAINS_SYMLINK"
    try:
        path.resolve(strict=True).relative_to(workspace.resolve(strict=True))
    except (OSError, ValueError):
        return path, "SOURCE_TREE_PATH_ESCAPES_WORKSPACE"
    if not path.is_dir() or path.is_symlink():
        return path, "SOURCE_TREE_DIRECTORY_MISSING"
    return path, None


def validate_scratch_root(root: Path, allowed_root: Path) -> Path:
    allowed_lexical = Path(os.path.abspath(allowed_root))
    allowed_lexical.mkdir(parents=True, exist_ok=True)
    if allowed_lexical.is_symlink() or allowed_lexical.resolve() != allowed_lexical:
        raise ReplayError("allowed scratch root contains a symlink")
    root_lexical = Path(os.path.abspath(root))
    try:
        root_lexical.relative_to(allowed_lexical)
    except ValueError as error:
        raise ReplayError("replay root must be below the dedicated scratch root") from error
    current = allowed_lexical
    for part in root_lexical.relative_to(allowed_lexical).parts:
        current /= part
        if current.is_symlink():
            raise ReplayError("replay root contains a symlink")
    if root_lexical.exists() and any(root_lexical.iterdir()):
        raise ReplayError("replay root must be new or empty")
    root_lexical.mkdir(parents=True, exist_ok=True)
    if root_lexical.resolve() != root_lexical:
        raise ReplayError("replay root resolved outside its lexical location")
    return root_lexical


def immutable_copy(
    source: Path,
    destination: Path,
    expected_sha256: str,
    output_root: Path,
) -> str:
    output_resolved = output_root.resolve(strict=True)
    try:
        destination.relative_to(output_root)
    except ValueError as error:
        raise ReplayError("copy destination escaped the generation root") from error
    current = output_root
    for part in destination.relative_to(output_root).parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ReplayError("copy destination parent is a symlink")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.parent.resolve(strict=True).relative_to(output_resolved)
    except ValueError as error:
        raise ReplayError("copy destination parent escaped the generation root") from error
    if destination.exists() or destination.is_symlink():
        raise ReplayError(f"copy destination already exists: {destination}")
    source_stat = source.stat(follow_symlinks=False)
    source_descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    destination_descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        with os.fdopen(source_descriptor, "rb") as input_stream, os.fdopen(
            destination_descriptor, "wb"
        ) as output_stream:
            shutil.copyfileobj(input_stream, output_stream, 8 * 1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    os.chmod(destination, 0o400)
    destination_stat = destination.stat(follow_symlinks=False)
    if destination_stat.st_nlink != 1 or (
        destination_stat.st_dev == source_stat.st_dev
        and destination_stat.st_ino == source_stat.st_ino
    ):
        destination.unlink(missing_ok=True)
        raise ReplayError("materialized input is linked to its protected source")
    source_hash = sha256_file(source)
    if source_hash != expected_sha256 or sha256_file(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise ReplayError("materialized input hash mismatch")
    return source_hash


def hash_tree(root: Path) -> tuple[str, list[str]]:
    """Hash names, types, link targets and regular-file contents."""
    records: list[dict[str, object]] = []
    blockers: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return canonical_sha256([]), ["SOURCE_TREE_MISSING_OR_SYMLINKED"]
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
            blockers.append(f"SOURCE_TREE_SYMLINK_FORBIDDEN:{relative}")
        elif path.is_file():
            if path.stat(follow_symlinks=False).st_nlink != 1:
                blockers.append(f"SOURCE_TREE_HARDLINK_FORBIDDEN:{relative}")
                continue
            try:
                file_hash = sha256_file(path)
            except OSError:
                blockers.append(f"SOURCE_TREE_FILE_UNREADABLE:{relative}")
            else:
                records.append({"path": relative, "type": "file", "sha256": file_hash})
        elif not path.is_dir():
            blockers.append("SOURCE_TREE_CONTAINS_SPECIAL_ENTRY")
    return canonical_sha256(records), sorted(set(blockers))


def intel_binary(path: Path) -> bool:
    """Require a structurally valid x86-64 ELF plus Intel runtime identity."""
    sample = path.read_bytes()
    if len(sample) < 64 or sample[:7] != b"\x7fELF\x02\x01\x01":
        return False
    try:
        header = struct.unpack_from("<HHIQQQIHHHHHH", sample, 16)
    except struct.error:
        return False
    elf_type, machine, version, _, program_offset, section_offset, _, header_size, \
        program_entry_size, program_count, section_entry_size, section_count, _ = header
    if (
        elf_type not in (2, 3)
        or machine != 62
        or version != 1
        or header_size != 64
        or program_entry_size != 56
        or program_count < 1
        or program_offset + program_entry_size * program_count > len(sample)
        or (section_count and (
            section_entry_size != 64
            or section_offset + section_entry_size * section_count > len(sample)
        ))
    ):
        return False
    load_segment = False
    for index in range(program_count):
        try:
            segment = struct.unpack_from(
                "<IIQQQQQQ", sample, program_offset + index * program_entry_size
            )
        except struct.error:
            return False
        segment_type, _, file_offset, _, _, file_size, _, _ = segment
        if file_offset + file_size > len(sample):
            return False
        load_segment = load_segment or segment_type == 1
    if not load_segment:
        return False
    markers = (
        b"Intel(r) Visual Fortran run-time error",
        b"libifcore",
        b"libimf.so",
    )
    return any(marker in sample for marker in markers)


def probe_strict_sandbox(specification: dict[str, object]) -> dict[str, object]:
    probe = specification.get("sandbox_probe")
    if not isinstance(probe, dict):
        return {"status": "BLOCKED", "reason": "SANDBOX_PROBE_NOT_DECLARED"}
    executable = Path(str(probe.get("executable", "")))
    payload = Path(str(probe.get("payload", "")))
    if executable != Path("/usr/bin/bwrap") or payload != Path("/usr/bin/true"):
        return {"status": "BLOCKED", "reason": "SANDBOX_PROBE_PATH_NOT_PINNED"}
    for path, hash_name in (
        (executable, "executable_sha256"),
        (payload, "payload_sha256"),
    ):
        if path.is_symlink() or not path.is_file() or not is_hex64(probe.get(hash_name)):
            return {"status": "BLOCKED", "reason": "SANDBOX_PROBE_FILE_INVALID"}
        if sha256_file(path) != probe[hash_name]:
            return {"status": "BLOCKED", "reason": "SANDBOX_PROBE_SHA256_MISMATCH"}
    command = [
        str(executable),
        "--die-with-parent",
        "--unshare-all",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--",
        str(payload),
    ]
    try:
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "BLOCKED", "reason": type(error).__name__}
    if completed.returncode != 0:
        reason = (completed.stderr or completed.stdout).strip().splitlines()
        return {
            "status": "BLOCKED",
            "reason": reason[0][:240] if reason else f"BWRAP_STATUS_{completed.returncode}",
        }
    return {
        "status": "PASS",
        "executable_sha256": sha256_file(executable),
        "payload_sha256": sha256_file(payload),
    }


def vrt_complete(path: Path, valid_time: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    try:
        import netCDF4
        import numpy as np

        with netCDF4.Dataset(path, "r") as dataset:
            dimensions = {name: len(value) for name, value in dataset.dimensions.items()}
            expected_dimensions = {
                "record": 1,
                "z": 22,
                "x": 235,
                "y": 283,
                "nav": 1,
                "namelen": 132,
            }
            if dimensions != expected_dimensions:
                findings.append("VRT_DIMENSIONS_INVALID")
            tid = dataset.variables.get("tid")
            if (
                tid is None
                or tid.dtype != np.dtype("float32")
                or tid.dimensions != ("record", "z", "y", "x")
            ):
                findings.append("VRT_TID_MISSING_OR_MALFORMED")
            else:
                units = normalize_units(getattr(tid, "units", ""))
                if units != "nul":
                    findings.append("VRT_TID_UNITS_INVALID")
                masked_values = np.ma.asarray(tid[:])
                values = np.ma.getdata(masked_values).astype(float)
                usable = (
                    ~np.ma.getmaskarray(masked_values)
                    & np.isfinite(values)
                    & (np.abs(values) < 1.0e36)
                )
                minimum_usable = max(
                    1, int(np.ceil(values.size * VRT_MIN_ACTIVE_FRACTION))
                )
                if np.count_nonzero(usable) < minimum_usable:
                    findings.append("VRT_FINITE_COVERAGE_INSUFFICIENT")
                allowed = (values == -10.0) | ((values >= 0.0) & (values <= 2.0))
                if np.any(usable & ~allowed):
                    findings.append("VRT_TID_RANGE_INVALID")
            level = dataset.variables.get("level")
            expected_levels = np.arange(50.0, 1100.1, 50.0)
            if (
                level is None
                or level.dtype != np.dtype("float32")
                or level.dimensions != ("z",)
                or normalize_units(getattr(level, "units", "")) != "hectopascals"
            ):
                findings.append("VRT_PRESSURE_LEVELS_MISSING")
            else:
                level_values = np.ma.asarray(level[:])
                if (
                    np.ma.is_masked(level_values)
                    or level_values.shape != expected_levels.shape
                    or not np.array_equal(np.asarray(level_values), expected_levels)
                ):
                    findings.append("VRT_PRESSURE_LEVELS_INVALID")
            expected_epoch = datetime.fromisoformat(
                valid_time.replace("Z", "+00:00")
            ).timestamp()
            for variable_name in ("valtime", "reftime"):
                time_variable = dataset.variables.get(variable_name)
                if time_variable is None or time_variable.size != 1:
                    findings.append(f"VRT_{variable_name.upper()}_MISSING")
                    continue
                if (
                    time_variable.dtype != np.dtype("float64")
                    or time_variable.dimensions != ("record",)
                    or normalize_units(getattr(time_variable, "units", ""))
                    != normalize_units(UTC_EPOCH_UNITS)
                ):
                    findings.append(f"VRT_{variable_name.upper()}_SCHEMA_INVALID")
                time_values = np.ma.asarray(time_variable[:]).reshape(-1)
                if time_values.count() != 1:
                    findings.append(f"VRT_{variable_name.upper()}_MASKED")
                    continue
                actual_time = float(time_values.compressed()[0])
                if not np.isfinite(actual_time) or actual_time != expected_epoch:
                    findings.append(f"VRT_{variable_name.upper()}_MISMATCH")
    except Exception as error:
        findings.append(f"VRT_OPEN_OR_READ_FAILED:{type(error).__name__}")
    return ("PASS" if not findings else "BLOCKED", findings)


def load_cases(path: Path, expected_hash: str) -> tuple[list[dict[str, str]], list[str]]:
    blockers: list[str] = []
    if sha256_file(path) != expected_hash:
        blockers.append("CASE_MANIFEST_SHA256_MISMATCH")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {"case_id", "valid_time_utc", "background_reftime_utc", "laps_stamp"}
    required.update(f"{role}_{suffix}" for role in CASE_INPUTS for suffix in ("path", "sha256"))
    if any(not required <= set(row) for row in rows):
        raise ReplayError("case manifest is missing required columns")
    identity = tuple(
        (row.get("case_id"), row.get("valid_time_utc"), row.get("laps_stamp"))
        for row in rows
    )
    if identity != EXPECTED_CASES:
        raise ReplayError("case manifest must contain the pinned ordered four cases")
    for row in rows:
        safe_identifier(str(row.get("case_id", "")))
    return rows, blockers


def validate_spec(spec: object) -> dict[str, object]:
    if not isinstance(spec, dict):
        raise ReplayError("replay spec must be a JSON object")
    if not isinstance(spec.get("source_tree_path"), str):
        raise ReplayError("source_tree_path is required")
    if spec.get("source_tree") != "klaps-v5.0_":
        raise ReplayError("source_tree must be klaps-v5.0_")
    source_tree_path = str(spec["source_tree_path"])
    source_tree_parts = safe_relative(source_tree_path).parts
    if not source_tree_parts or source_tree_parts[0] != spec["source_tree"]:
        raise ReplayError("source_tree_path must be inside klaps-v5.0_")
    forbidden = forbidden_input(source_tree_path)
    if forbidden:
        raise ReplayError(f"source_tree_path is forbidden: {forbidden}")
    assets = spec.get("assets")
    stages = spec.get("stages")
    environment = spec.get("environment")
    global_blockers = spec.get("global_blockers")
    if not isinstance(assets, list) or not isinstance(stages, list):
        raise ReplayError("assets and stages must be arrays")
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in environment.items()
    ):
        raise ReplayError("environment must contain only string pairs")
    if not isinstance(global_blockers, list) or not all(
        isinstance(item, str) for item in global_blockers
    ):
        raise ReplayError("global_blockers must be a string array")
    for asset in assets:
        if not isinstance(asset, dict) or not all(
            isinstance(asset.get(name), str) for name in ("role", "path", "sha256")
        ):
            raise ReplayError("asset declaration is malformed")
        safe_identifier(str(asset["role"]))
        safe_relative(str(asset["path"]))
    stage_ids: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("id"), str):
            raise ReplayError("stage declaration is malformed")
        stage_id = str(stage["id"])
        safe_identifier(stage_id)
        if stage_id in stage_ids:
            raise ReplayError("stage identities must be unique")
        stage_ids.append(stage_id)
        if stage_id not in STAGE_PRODUCT or stage.get("product") != STAGE_PRODUCT[stage_id]:
            raise ReplayError("stage product mapping is invalid")
        closure = stage.get("closure_blockers")
        if not isinstance(closure, list) or not all(isinstance(item, str) for item in closure):
            raise ReplayError("stage closure blockers must be a string array")
        expected_executable = STAGE_EXECUTABLE.get(stage_id)
        if expected_executable is None:
            if stage.get("executable") is not None:
                raise ReplayError("gate stage cannot declare an executable")
        else:
            if not isinstance(stage.get("executable"), str) or not isinstance(
                stage.get("executable_sha256"), str
            ):
                raise ReplayError("stage executable declaration is malformed")
            safe_relative(str(stage["executable"]))
            if PurePosixPath(str(stage["executable"])).name != expected_executable:
                raise ReplayError("stage executable mapping is invalid")
    if tuple(stage_ids) != STAGE_SEQUENCE:
        raise ReplayError("stage sequence must place the VRT gate before temperature")
    probe = spec.get("sandbox_probe")
    if not isinstance(probe, dict) or not all(
        isinstance(probe.get(name), str)
        for name in ("executable", "executable_sha256", "payload", "payload_sha256")
    ):
        raise ReplayError("sandbox probe declaration is malformed")
    return spec


def audit_declared_file(
    workspace: Path,
    relative: str,
    expected_hash: str,
    role: str,
    allowed_root: str,
) -> tuple[dict[str, object], Path | None, list[str]]:
    receipt: dict[str, object] = {
        "role": role,
        "source_path": relative,
        "expected_sha256": expected_hash,
    }
    blockers: list[str] = []
    allowed_parts = safe_relative(allowed_root).parts
    try:
        relative_parts = safe_relative(relative).parts
    except ReplayError:
        relative_parts = ()
    if relative_parts[:len(allowed_parts)] != allowed_parts:
        blockers.append(f"SOURCE_OUTSIDE_DECLARED_ROLE_ROOT:{role}")
    if not is_hex64(expected_hash):
        blockers.append(f"INVALID_EXPECTED_SHA256:{role}")
    forbidden = forbidden_input(relative)
    if forbidden:
        blockers.append(f"{forbidden}:{role}")
    source, path_error = contained_regular(workspace, relative)
    if path_error:
        blockers.append(f"{path_error}:{role}")
        receipt.update(status="BLOCKED", findings=blockers)
        return receipt, None, blockers
    try:
        actual_hash = sha256_file(source)
    except OSError:
        blockers.append(f"SOURCE_UNREADABLE:{role}")
        receipt.update(status="BLOCKED", findings=blockers)
        return receipt, None, blockers
    receipt["sha256"] = actual_hash
    if actual_hash != expected_hash:
        blockers.append(f"SOURCE_SHA256_MISMATCH:{role}")
    receipt["status"] = "PASS" if not blockers else "BLOCKED"
    if blockers:
        receipt["findings"] = blockers
    return receipt, source, blockers


def main() -> int:
    global BLOCKED_MANIFEST_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--workspace-root", type=Path, default=repo_root.parent)
    parser.add_argument(
        "--case-manifest",
        type=Path,
        default=repo_root / "tests/qbal_real_cases_20260816.tsv",
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=repo_root / "tests/original_upstream_replay_20260816.json",
    )
    parser.add_argument(
        "--spec-sha256",
        help="external SHA-256 pin; required for every non-default replay spec",
    )
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    allowed_root = repo_root / "scratch/original_upstream_replay"
    try:
        output_root = validate_scratch_root(args.root, allowed_root)
    except ReplayError as error:
        json.dump(
            {
                "contract": CONTRACT,
                "authority": AUTHORITY,
                "generation_status": "BLOCKED",
                "blockers": [f"UNSAFE_REPLAY_ROOT:{error}"],
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2

    BLOCKED_MANIFEST_ROOT = output_root

    manifest_path = output_root / "PRE_QBAL_MANIFEST.json"
    blockers: list[str] = []
    try:
        workspace_candidate = args.workspace_root.absolute()
        if workspace_candidate.is_symlink():
            raise ReplayError("workspace root cannot be a symlink")
        workspace = workspace_candidate.resolve(strict=True)
        if not workspace.is_dir():
            raise ReplayError("workspace root must be a directory")
        replay_spec_sha256 = sha256_file(args.spec)
        default_spec = repo_root / "tests/original_upstream_replay_20260816.json"
        expected_spec_sha256 = args.spec_sha256
        if expected_spec_sha256 is None and args.spec.resolve() == default_spec.resolve():
            expected_spec_sha256 = DEFAULT_REPLAY_SPEC_SHA256
        if not is_hex64(expected_spec_sha256) or replay_spec_sha256 != expected_spec_sha256:
            raise ReplayError("replay spec SHA-256 pin is missing or mismatched")
        spec = validate_spec(json.loads(args.spec.read_text(encoding="utf-8")))
        if spec.get("contract") != "original_klaps_upstream_replay_plan_v1":
            blockers.append("REPLAY_SPEC_CONTRACT_INVALID")
        if spec.get("compiler_family") != "Intel":
            blockers.append("NON_INTEL_REPLAY_SPEC_REJECTED")
        expected_manifest_hash = spec.get("case_manifest_sha256")
        if not is_hex64(expected_manifest_hash):
            raise ReplayError("replay spec lacks a pinned case manifest hash")
        rows, case_blockers = load_cases(args.case_manifest, expected_manifest_hash)
        blockers.extend(case_blockers)
    except Exception as error:
        manifest = minimal_blocked_manifest(
            f"REPLAY_SPEC_OR_CASE_MANIFEST_INVALID:{type(error).__name__}"
        )
        write_manifest(output_root, manifest)
        return 3

    source_tree_path, source_tree_error = contained_directory(
        workspace, str(spec["source_tree_path"])
    )
    if source_tree_error:
        source_tree_sha256 = canonical_sha256([])
        source_tree_blockers = [source_tree_error]
    else:
        source_tree_sha256, source_tree_blockers = hash_tree(source_tree_path)
    blockers.extend(source_tree_blockers)
    blockers.extend(str(item) for item in spec.get("global_blockers", []))

    sandbox = probe_strict_sandbox(spec)
    if sandbox["status"] != "PASS":
        blockers.append("STRICT_READ_WRITE_SANDBOX_PROBE_FAILED")

    asset_receipts: list[dict[str, object]] = []
    executable_receipts: list[dict[str, object]] = []
    asset_sources: list[tuple[dict[str, object], Path]] = []
    stage_receipts: list[dict[str, object]] = []
    for asset in spec.get("assets", []):
        receipt, source, findings = audit_declared_file(
            workspace,
            asset["path"],
            asset["sha256"],
            asset["role"],
            "ANAL/NE57/DABA",
        )
        asset_receipts.append(receipt)
        blockers.extend(findings)
        if source is not None and not findings:
            asset_sources.append((receipt, source))

    for stage in spec.get("stages", []):
        stage_id = str(stage["id"])
        stage_blockers = [str(item) for item in stage.get("closure_blockers", [])]
        executable = stage.get("executable")
        executable_receipt: dict[str, object] | None = None
        if executable:
            executable_receipt, source, findings = audit_declared_file(
                workspace,
                str(executable),
                str(stage.get("executable_sha256", "")),
                f"executable:{stage_id}",
                "klaps-v5.0_",
            )
            executable_receipt["stage"] = stage_id
            if source is not None and not findings and not intel_binary(source):
                findings.append(f"NON_INTEL_EXECUTABLE:{stage_id}")
                executable_receipt["status"] = "BLOCKED"
                executable_receipt["findings"] = findings
            executable_receipts.append(executable_receipt)
            stage_blockers.extend(findings)
            if source is not None and not findings:
                asset_sources.append((executable_receipt, source))
        blockers.extend(stage_blockers)
        stage_receipts.append(
            {
                "stage": stage_id,
                "status": "PENDING" if stage_id == "vrt_complete_gate" else "NOT_RUN",
                "execution_started": False,
                "blockers": sorted(set(stage_blockers)),
            }
        )

    configuration_sha256 = canonical_sha256(
        {
            "environment": spec.get("environment", {}),
            "assets": [
                {"role": item["role"], "sha256": item.get("sha256")}
                for item in asset_receipts
            ],
            "executables": [
                {"stage": item["stage"], "sha256": item.get("sha256")}
                for item in executable_receipts
            ],
        }
    )

    for receipt, source in asset_sources:
        role = str(receipt["role"]).replace(":", "_")
        destination = output_root / "declared_inputs/common" / role / source.name
        try:
            copied_hash = immutable_copy(
                source, destination, str(receipt["sha256"]), output_root
            )
            receipt["materialized_path"] = destination.relative_to(output_root).as_posix()
            receipt["materialized_sha256"] = copied_hash
        except Exception as error:
            blockers.append(f"MATERIALIZATION_FAILED:{role}:{type(error).__name__}")

    cases: list[dict[str, object]] = []
    shared_blockers = sorted(set(blockers))
    for row in rows:
        input_receipts: list[dict[str, object]] = []
        input_sources: list[tuple[dict[str, object], Path]] = []
        case_blockers: list[str] = list(shared_blockers)
        for role in CASE_INPUTS:
            receipt, source, findings = audit_declared_file(
                workspace,
                row[f"{role}_path"],
                row[f"{role}_sha256"],
                role,
                CASE_ALLOWED_ROOTS[role],
            )
            input_receipts.append(receipt)
            case_blockers.extend(findings)
            blockers.extend(findings)
            if source is not None and not findings:
                input_sources.append((receipt, source))
        for receipt, source in input_sources:
            destination = (
                output_root
                / "cases"
                / row["case_id"]
                / "declared_inputs"
                / str(receipt["role"])
                / source.name
            )
            try:
                copied_hash = immutable_copy(
                    source, destination, str(receipt["sha256"]), output_root
                )
                receipt["materialized_path"] = destination.relative_to(output_root).as_posix()
                receipt["materialized_sha256"] = copied_hash
            except Exception as error:
                reason = (
                    f"MATERIALIZATION_FAILED:{receipt['role']}:{type(error).__name__}"
                )
                case_blockers.append(reason)
                blockers.append(reason)
        vrt_receipt = next(item for item in input_receipts if item["role"] == "vrt")
        vrt_source = next(
            (source for receipt, source in input_sources if receipt["role"] == "vrt"),
            None,
        )
        if vrt_source is None:
            vrt_status, vrt_findings = "BLOCKED", ["VRT_SOURCE_UNAVAILABLE"]
        else:
            vrt_status, vrt_findings = vrt_complete(vrt_source, row["valid_time_utc"])
        case_blockers.extend(vrt_findings)
        blockers.extend(vrt_findings)
        declared_input_receipt_sha256 = canonical_sha256(
            [
                {
                    "role": item["role"],
                    "source_path": item["source_path"],
                    "sha256": item.get("sha256"),
                }
                for item in input_receipts
            ]
        )
        cases.append(
            {
                "case_id": row["case_id"],
                "valid_time_utc": row["valid_time_utc"],
                "laps_stamp": row["laps_stamp"],
                "status": "BLOCKED",
                "input_closure_sha256": None,
                "declared_input_receipt_sha256": declared_input_receipt_sha256,
                "inputs": input_receipts,
                "vrt_completion_gate": {
                    "status": vrt_status,
                    "findings": vrt_findings,
                    "source_sha256": vrt_receipt.get("sha256"),
                },
                "products": product_receipts(row, "BLOCKED"),
                "blockers": sorted(set(case_blockers)),
            }
        )

    for stage in stage_receipts:
        if stage["stage"] == "vrt_complete_gate":
            failed_vrt = [
                case["case_id"]
                for case in cases
                if case["vrt_completion_gate"]["status"] != "PASS"
            ]
            stage["status"] = "PASS" if not failed_vrt else "BLOCKED"
            stage["blockers"] = [f"VRT_NOT_COMPLETE:{case_id}" for case_id in failed_vrt]

    all_copy_receipts = asset_receipts + executable_receipts + [
        item for case in cases for item in case["inputs"]
    ]
    materialization = "COPIED" if all(
        item.get("status") == "PASS" and item.get("materialized_sha256") == item.get("sha256")
        for item in all_copy_receipts
    ) else "INCOMPLETE"
    if materialization != "COPIED":
        blockers.append("DECLARED_INPUT_MATERIALIZATION_INCOMPLETE")
    blockers.append("UPSTREAM_EXECUTION_NOT_AUTHORIZED")

    manifest = {
        "contract": CONTRACT,
        "authority": AUTHORITY,
        "source_tree": spec.get("source_tree", "klaps-v5.0_"),
        "source_tree_sha256": source_tree_sha256,
        "replay_harness_sha256": sha256_file(Path(__file__).resolve()),
        "replay_spec_sha256": replay_spec_sha256,
        "case_manifest_sha256": sha256_file(args.case_manifest),
        "compiler_family": "Intel",
        "configuration_sha256": configuration_sha256,
        "environment": spec.get("environment", {}),
        "generation_status": "BLOCKED",
        "execution_requested": False,
        "execution_started": False,
        "materialization": materialization,
        "final_bigfile_allowed_as_input": False,
        "promotion_eligible": False,
        "sandbox_gate": sandbox,
        "blockers": sorted(set(blockers)),
        "assets": asset_receipts,
        "executables": executable_receipts,
        "stages": stage_receipts,
        "cases": cases,
    }
    write_manifest(output_root, manifest)
    print(manifest_path)
    return 3


if __name__ == "__main__":
    try:
        status = main()
    except Exception as error:
        if BLOCKED_MANIFEST_ROOT is None:
            raise
        manifest = minimal_blocked_manifest(
            f"UNEXPECTED_PREFLIGHT_FAILURE:{type(error).__name__}"
        )
        path = write_manifest(BLOCKED_MANIFEST_ROOT, manifest)
        print(path)
        status = 3
    raise SystemExit(status)
