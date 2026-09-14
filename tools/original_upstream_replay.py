#!/usr/bin/env python3
"""Fail-closed isolated planner for the original KLAPS pre-QBAL replay.

This tool never treats a renamed final product as an upstream input.  It
materializes hash-declared regular files and case-derived runtime clocks into scratch,
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
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT = "original_klaps_pre_qbal_generation_v1"
AUTHORITY = "original_klaps_source"
DEFAULT_REPLAY_SPEC_SHA256 = (
    "08b03eaf46c7b19e055af0da3585ee630c9578f8338910c91519ae9a90ef86e5"
)
EXPECTED_CASES = (
    ("20260816T120000Z", "2026-08-16T12:00:00Z", "262281200"),
    ("20260816T130000Z", "2026-08-16T13:00:00Z", "262281300"),
    ("20260816T140000Z", "2026-08-16T14:00:00Z", "262281400"),
    ("20260816T150000Z", "2026-08-16T15:00:00Z", "262281500"),
)
CASE_INPUTS = ("fua", "fsf", "lw3", "vrz", "vrt")
OBSERVATION_ROLES = ("snd", "pin", "adb")
LIGHTNING_ROLE = "lgt"
LIGHTNING_ALLOWED_ROOT = "ANAL/NE57/DAOU/00/lapsprd/lgt"
LIGHTNING_LINE_FORMAT = "1x,2i8,1x,i8"
CASE_ALLOWED_ROOTS = {
    "fua": "ANAL/NE57/DAOU/00/lapsprd/fua/wrf",
    "fsf": "ANAL/NE57/DAOU/00/lapsprd/fsf/wrf",
    "lw3": "klaps-v5.0_/baseline/20260831_wind_multitime/results",
    "vrz": "ANAL/NE57/DAOU/00/lapsprd/vrz",
    "vrt": "ANAL/NE57/DAOU/00/lapsprd/vrt",
}
RUNTIME_STATIC_PATHS = {
    "lc3_cdl_template": "cdl/lc3.cdl",
    "lcb_cdl_template": "cdl/lcb.cdl",
    "lcv_cdl_template": "cdl/lcv.cdl",
    "lps_cdl_template": "cdl/lps.cdl",
    "lt1_cdl_template": "cdl/lt1.cdl",
    "lsx_cdl_template": "cdl/lsx.cdl",
    "pbl_cdl_template": "cdl/pbl.cdl",
    "static_grid": "static/static.nest7grid",
    "grid_configuration_template": "static/nest7grid.parms",
    "pressure_configuration": "static/pressures.nl",
    "background_configuration": "static/background.nl",
    "temperature_configuration": "static/temp.nl",
    "surface_configuration": "static/surface_analysis.nl",
    "surface_drag_table": "static/drag_coef.dat",
    "cloud_configuration": "static/cloud.nl",
    "satellite_configuration_template": "static/satellite_lvd.nl",
    "goeslib_table": "static/goeslib/for044.dat",
}
RUNTIME_MOUNT = "/cloud-bal-case"
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


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_verified_bytes(path: Path, expected_hash: str) -> bytes:
    """Read one declared regular file and bind the returned bytes to its hash."""
    if path.is_symlink() or not path.is_file():
        raise ReplayError("declared source is not a regular file")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ReplayError(f"declared source read failed: {error}") from error
    actual_hash = sha256_bytes(payload)
    if actual_hash != expected_hash:
        raise ReplayError(
            f"declared source changed during binding: {actual_hash} != {expected_hash}"
        )
    return payload


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_units(value: object) -> str:
    return "".join(str(value).strip().lower().split())


def encode_systime(row: dict[str, str]) -> bytes:
    """Encode the original sched/systime.f six-line, 1960-epoch contract."""
    valid = datetime.fromisoformat(row["valid_time_utc"].replace("Z", "+00:00"))
    if valid.utcoffset() != timezone.utc.utcoffset(valid) or valid.second or valid.microsecond:
        raise ReplayError("systime requires an exact UTC minute")
    stamp = valid.strftime("%y%j%H%M")
    if row["laps_stamp"] != stamp or row["case_id"] != valid.strftime("%Y%m%dT%H%M%SZ"):
        raise ReplayError("systime case identity mismatch")
    seconds = int((valid - datetime(1960, 1, 1, tzinfo=timezone.utc)).total_seconds())
    if not 0 <= seconds <= 2147483647:
        raise ReplayError("systime is outside signed INTEGER*4 range")
    # Locale-independent month spelling matches cv_i4tim_asc_lp.
    month = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")[valid.month - 1]
    ascii_time = f"{valid.day:02d}-{month}-{valid.year:04d} {valid:%H%M}"
    return f" {seconds:11d}\n {stamp}\n{valid:%H}\n{valid:%M}\n{ascii_time}\n{stamp[:5]}\n".encode("ascii")


def rebind_runtime_configuration(role: str, payload: bytes) -> bytes:
    """Change path values only; the runner must bind the case at RUNTIME_MOUNT."""
    text = payload.decode("ascii")
    if role == "grid_configuration_template":
        text = text.replace("${KL05DABA}", RUNTIME_MOUNT + "/static-assets")
        text = text.replace("${KL05DAIO}", RUNTIME_MOUNT + "/observations/raw")
        if "${" in text:
            raise ReplayError("unsupported grid path placeholder")
    elif role == "background_configuration":
        if len(re.findall(r"^[ \t]*BGPATHS[ \t]*=", text, re.I | re.M)) != 1:
            raise ReplayError("exactly one BGPATHS assignment required")
        pattern = re.compile(r"^([ \t]*BGPATHS[ \t]*=)(.*?)(?=^[ \t]*[A-Za-z]\w*[ \t]*=|^[ \t]*/)", re.I | re.M | re.S)
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise ReplayError("exactly one BGPATHS assignment required")
        match = matches[0]
        values = match.group(2)
        if not re.fullmatch(r"\s*'[^']*'(?:\s*,\s*'[^']*')*\s*,?\s*", values):
            raise ReplayError("unsupported BGPATHS list")
        index = 0

        def replace_path(value: re.Match) -> str:
            nonlocal index
            index += 1
            if not value.group(1):
                return value.group(0)
            return f"'{RUNTIME_MOUNT}/background-source/{index:02d}'"

        values = re.sub(r"'([^']*)'", replace_path, values)
        text = text[:match.start(2)] + values + text[match.end(2):]
    else:
        raise ReplayError(f"no runtime path transformation for {role}")
    return text.encode("ascii")


def write_runtime_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def materialize_case_runtime(
    output_root: Path, row: dict[str, str], asset_sources: list[tuple[dict[str, object], Path]],
    input_sources: tuple | list = (),
) -> dict[str, object]:
    """Map declared inputs to legacy reader paths without granting execution."""
    payload = encode_systime(row)
    runtime = output_root / "cases" / safe_identifier(row["case_id"]) / "runtime"
    current = output_root
    for part in runtime.relative_to(output_root).parts:
        current /= part
        if current.is_symlink():
            raise ReplayError("runtime parent is a symlink")
    if runtime.exists():
        raise ReplayError("runtime already exists; refusing to overwrite")
    runtime.mkdir(parents=True, exist_ok=False)
    output_directories = (
        "lapsprd/lc3",
        "lapsprd/lcb",
        "lapsprd/lcv",
        "lapsprd/lps",
        "lapsprd/lsx",
        "lapsprd/tmp",
        "lapsprd/lt1",
        "lapsprd/tmg",
        "lapsprd/lpbl",
        "lapsprd/pbl",
        "log",
        "log/qc",
    )
    for relative in output_directories:
        (runtime / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
    (runtime / "time").mkdir()
    clock_path = runtime / "time/systime.dat"
    write_runtime_bytes(clock_path, payload)
    result: dict[str, object] = {
        "status": "PARTIAL", "execution_ready": False,
        "runtime_path": runtime.relative_to(output_root).as_posix(),
        "systime_sha256": sha256_file(clock_path),
        "systime_source": "DERIVED_FROM_PINNED_CASE_TIME",
        "execution_blockers": ["RUNTIME_TREE_INCOMPLETE", "CURRENT_TIME_LSX_NOT_PRODUCED",
                               "RUNTIME_MOUNT_AND_REFERENCED_INPUTS_REQUIRED"],
        "configuration_status": "PATHS_REBOUND_REFERENCED_INPUTS_INCOMPLETE",
        "required_runtime_mount": RUNTIME_MOUNT,
        "output_directories": list(output_directories),
        "copies": [],
        "findings": [],
    }
    for role in (*RUNTIME_STATIC_PATHS, *CASE_INPUTS):
        sources = asset_sources if role in RUNTIME_STATIC_PATHS else input_sources
        matches = [(receipt, source) for receipt, source in sources if receipt["role"] == role]
        if len(matches) != 1:
            result["findings"].append(f"EXACTLY_ONE_DECLARED_{role.upper()}_REQUIRED")
            continue
        receipt, source = matches[0]
        if role in RUNTIME_STATIC_PATHS:
            relative = Path(RUNTIME_STATIC_PATHS[role])
        else:
            relative = Path("lapsprd") / role
            if role in ("fua", "fsf"):
                relative /= "wrf"
            relative /= source.name
        if role in ("grid_configuration_template", "background_configuration"):
            template = Path("templates") / relative
            template_hash = immutable_copy(source, runtime / template, str(receipt["sha256"]), output_root)
            result["copies"].append({"role": role + ":template", "path": template.as_posix(), "sha256": template_hash})
            payload = rebind_runtime_configuration(role, (runtime / template).read_bytes())
            (runtime / relative).parent.mkdir(parents=True, exist_ok=True)
            write_runtime_bytes(runtime / relative, payload)
            copied_hash = sha256_file(runtime / relative)
        else:
            copied_hash = immutable_copy(source, runtime / relative, str(receipt["sha256"]), output_root)
        result["copies"].append({"role": role, "path": relative.as_posix(), "sha256": copied_hash})
        if role == "lt1_cdl_template":
            result["lt1_cdl_sha256"] = copied_hash
    for role in (*OBSERVATION_ROLES, LIGHTNING_ROLE, "lso", "previous_lso", "lvd"):
        matches = [
            (receipt, source)
            for receipt, source in input_sources
            if receipt.get("role") == role
        ]
        if not matches:
            continue
        if len(matches) != 1:
            result["findings"].append(f"AT_MOST_ONE_DECLARED_{role.upper()}_ALLOWED")
            continue
        receipt, source = matches[0]
        if receipt.get("status") != "PASS":
            result["findings"].append(f"DECLARED_{role.upper()}_NOT_SUCCESSFUL")
            continue
        product_dir = {"previous_lso": "lso", "lvd": "lvd/kogk2a"}.get(role, role)
        relative = Path("lapsprd") / product_dir / source.name
        expected_copy_hash = (
            receipt["expected_sha256"]
            if role == LIGHTNING_ROLE
            else receipt["sha256"]
        )
        copied_hash = immutable_copy(
            source, runtime / relative, str(expected_copy_hash), output_root
        )
        result["copies"].append({"role": role, "path": relative.as_posix(), "sha256": copied_hash})
    result["status"] = "PREPARED" if not result["findings"] else "PARTIAL"
    lrs_names: set[str] = set()
    for receipt, source in input_sources:
        if receipt.get("role") != "lrs":
            continue
        if receipt.get("status") != "PASS" or source.name in lrs_names:
            raise ReplayError("LRS runtime inputs must be successful and unique")
        lrs_names.add(source.name)
        relative = Path("lapsprd/lrs") / source.name
        copied_hash = immutable_copy(source, runtime / relative, str(receipt["sha256"]), output_root)
        result["copies"].append({"role": "lrs", "path": relative.as_posix(), "sha256": copied_hash})
    return result


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


def vrt_complete(source: Path | bytes, valid_time: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    try:
        import netCDF4
        import numpy as np

        dataset = (
            netCDF4.Dataset("inmemory-vrt.nc", "r", memory=source)
            if isinstance(source, bytes)
            else netCDF4.Dataset(source, "r")
        )
        with dataset:
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


def _strict_int(value: object) -> bool:
    return type(value) is int


def validate_lightning_contract(value: object, *, required: bool = False) -> list[str]:
    """Validate the pinned fixed-column LGT reader contract."""
    if value is None:
        return ["LIGHTNING_CONTRACT_NOT_DECLARED"] if required else []
    if not isinstance(value, dict):
        return ["LIGHTNING_CONTRACT_MALFORMED"]
    findings: list[str] = []
    if value.get("encoding") != "ascii":
        findings.append("LIGHTNING_ENCODING_MUST_BE_ASCII")
    if value.get("line_format") != LIGHTNING_LINE_FORMAT:
        findings.append("LIGHTNING_LINE_FORMAT_INVALID")
    for name in ("grid_nx", "grid_ny", "missing_value"):
        if not _strict_int(value.get(name)):
            findings.append(f"LIGHTNING_CONTRACT_{name.upper()}_INVALID")
    if _strict_int(value.get("grid_nx")) and value["grid_nx"] <= 0:
        findings.append("LIGHTNING_GRID_NX_NOT_POSITIVE")
    if _strict_int(value.get("grid_ny")) and value["grid_ny"] <= 0:
        findings.append("LIGHTNING_GRID_NY_NOT_POSITIVE")
    if _strict_int(value.get("missing_value")) and value["missing_value"] >= 0:
        findings.append("LIGHTNING_MISSING_VALUE_MUST_BE_NEGATIVE")
    if value.get("negative_policy") != "only_missing_value":
        findings.append("LIGHTNING_NEGATIVE_POLICY_INVALID")
    return findings


def validate_lightning_declarations(
    value: object, contract: dict[str, object], *, required: bool = False
) -> list[str]:
    """Validate case-keyed LGT declarations without opening source files."""
    if value is None:
        return ["LIGHTNING_OBSERVATIONS_NOT_DECLARED"] if required else []
    if not isinstance(value, dict):
        return ["LIGHTNING_OBSERVATIONS_SPEC_NOT_OBJECT"]
    expected_case_ids = {case_id for case_id, _, _ in EXPECTED_CASES}
    findings: list[str] = []
    if set(value) != expected_case_ids:
        findings.append("LIGHTNING_OBSERVATIONS_CASE_KEYS_INVALID")
    grid_nx = contract.get("grid_nx")
    grid_ny = contract.get("grid_ny")
    expected_lines = grid_nx * grid_ny if _strict_int(grid_nx) and _strict_int(grid_ny) else None
    stamp_by_case = {case_id: stamp for case_id, _, stamp in EXPECTED_CASES}
    for case_id, declaration in value.items():
        if case_id not in stamp_by_case:
            continue
        if not isinstance(declaration, dict):
            findings.append(f"LIGHTNING_DECLARATION_MALFORMED:{case_id}")
            continue
        expected_path = f"{LIGHTNING_ALLOWED_ROOT}/{stamp_by_case[case_id]}.lgt"
        if declaration.get("path") != expected_path:
            findings.append(f"LIGHTNING_PATH_MISMATCH:{case_id}")
        try:
            safe_relative(str(declaration.get("path", "")))
        except ReplayError:
            findings.append(f"LIGHTNING_PATH_UNSAFE:{case_id}")
        if not is_hex64(declaration.get("sha256")):
            findings.append(f"LIGHTNING_SHA256_INVALID:{case_id}")
        counts = declaration.get("expected_counts")
        if not isinstance(counts, dict) or set(counts) != {"missing", "zero", "positive"}:
            findings.append(f"LIGHTNING_EXPECTED_COUNTS_INVALID:{case_id}")
        elif not all(_strict_int(counts.get(name)) and counts[name] >= 0 for name in counts):
            findings.append(f"LIGHTNING_EXPECTED_COUNTS_INVALID:{case_id}")
        elif expected_lines is not None and sum(counts.values()) != expected_lines:
            findings.append(f"LIGHTNING_EXPECTED_COUNTS_TOTAL_INVALID:{case_id}")
        if "line_count" in declaration and declaration.get("line_count") != expected_lines:
            findings.append(f"LIGHTNING_LINE_COUNT_INVALID:{case_id}")
    return sorted(set(findings))


def validate_lightning_spec(spec: dict[str, object], *, required: bool = False) -> list[str]:
    contract = spec.get("lightning_contract")
    findings = validate_lightning_contract(contract, required=required)
    if isinstance(contract, dict):
        findings.extend(
            validate_lightning_declarations(
                spec.get("lightning_observations"), contract, required=required
            )
        )
    elif spec.get("lightning_observations") is not None:
        findings.append("LIGHTNING_CONTRACT_REQUIRED_FOR_OBSERVATIONS")
    return sorted(set(findings))


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
    # Older synthetic unit-test specs may omit LGT entirely.  When present,
    # however, its reader contract and all four declarations are mandatory.
    if "lightning_contract" in spec or "lightning_observations" in spec:
        lightning_findings = validate_lightning_spec(spec, required=True)
        if lightning_findings:
            raise ReplayError("; ".join(lightning_findings))
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


def parse_lightning_bytes(
    payload: bytes,
    contract: dict[str, object],
    expected_counts: object = None,
) -> tuple[dict[str, object], list[str]]:
    """Parse one LGT byte buffer using the pinned Fortran fixed-column layout."""
    findings = validate_lightning_contract(contract, required=True)
    contract_values = contract if isinstance(contract, dict) else {}
    summary: dict[str, object] = {
        "line_count": 0,
        "grid_nx": contract_values.get("grid_nx"),
        "grid_ny": contract_values.get("grid_ny"),
        "count_missing": 0,
        "count_zero": 0,
        "count_positive": 0,
        "coordinate_order": "i_outer_j_inner",
        "missing_value": contract_values.get("missing_value"),
    }
    if findings:
        return summary, sorted(set(findings))
    try:
        payload.decode("ascii")
    except UnicodeDecodeError:
        findings.append("LIGHTNING_NON_ASCII_BYTES")
        return summary, sorted(set(findings))

    grid_nx = int(contract["grid_nx"])
    grid_ny = int(contract["grid_ny"])
    missing_value = int(contract["missing_value"])
    lines = payload.splitlines(keepends=True)
    summary["line_count"] = len(lines)
    if len(lines) != grid_nx * grid_ny:
        findings.append("LIGHTNING_LINE_COUNT_MISMATCH")

    for index, line in enumerate(lines):
        if len(line) != 27 or line[-1:] != b"\n":
            findings.append(f"LIGHTNING_FIXED_LINE_INVALID:{index + 1}")
            if len(line) < 27:
                continue
        if line[0:1] != b" " or line[17:18] != b" ":
            findings.append(f"LIGHTNING_FIXED_SEPARATOR_INVALID:{index + 1}")
        fields = (line[1:9], line[9:17], line[18:26])
        parsed: list[int] = []
        field_invalid = False
        for field in fields:
            stripped = field.strip()
            if not stripped or re.fullmatch(rb"[+-]?[0-9]+", stripped) is None:
                field_invalid = True
                break
            parsed.append(int(stripped))
        if field_invalid:
            findings.append(f"LIGHTNING_FIXED_INTEGER_INVALID:{index + 1}")
            continue
        actual_i, actual_j, value = parsed
        expected_i = index // grid_ny + 1
        expected_j = index % grid_ny + 1
        if actual_i != expected_i or actual_j != expected_j:
            findings.append(
                f"LIGHTNING_COORDINATE_ORDER_INVALID:{index + 1}"
            )
        if value == missing_value:
            summary["count_missing"] = int(summary["count_missing"]) + 1
        elif value == 0:
            summary["count_zero"] = int(summary["count_zero"]) + 1
        elif value > 0:
            summary["count_positive"] = int(summary["count_positive"]) + 1
        else:
            findings.append(f"LIGHTNING_NEGATIVE_VALUE_DISALLOWED:{index + 1}")

    if isinstance(expected_counts, dict):
        actual_counts = {
            "missing": summary["count_missing"],
            "zero": summary["count_zero"],
            "positive": summary["count_positive"],
        }
        if expected_counts != actual_counts:
            for name in ("missing", "zero", "positive"):
                if expected_counts.get(name) != actual_counts[name]:
                    findings.append(f"LIGHTNING_COUNT_MISMATCH:{name}")
    elif expected_counts is not None:
        findings.append("LIGHTNING_EXPECTED_COUNTS_INVALID")
    return summary, sorted(set(findings))


def audit_lightning_observation(
    workspace: Path,
    row: dict[str, str],
    declaration: object,
    contract: object,
) -> tuple[dict[str, object], Path | None, list[str]]:
    """Hash and parse the exact LGT buffer declared for one replay case."""
    stamp = row.get("laps_stamp", "")
    expected_path = f"{LIGHTNING_ALLOWED_ROOT}/{stamp}.lgt"
    receipt: dict[str, object] = {
        "role": LIGHTNING_ROLE,
        "source_path": expected_path,
        "scope": "ASCII_FIXED_GRID_CONTENT_AND_HASH",
        "content_validation": "NOT_RUN",
    }
    findings: list[str] = []
    findings.extend(validate_lightning_contract(contract, required=True))
    if not isinstance(declaration, dict):
        findings.append("LIGHTNING_OBSERVATION_DECLARATION_MISSING_OR_INVALID")
        receipt.update(status="BLOCKED", findings=sorted(set(findings)))
        return receipt, None, sorted(set(findings))
    declared_path = declaration.get("path")
    expected_hash = declaration.get("sha256")
    receipt["source_path"] = declared_path if isinstance(declared_path, str) else expected_path
    receipt["expected_sha256"] = expected_hash
    if declared_path != expected_path:
        findings.append("LIGHTNING_OBSERVATION_PATH_MISMATCH")
    if not is_hex64(expected_hash):
        findings.append("LIGHTNING_OBSERVATION_SHA256_INVALID")
    expected_counts = declaration.get("expected_counts")
    if not isinstance(expected_counts, dict) or set(expected_counts) != {"missing", "zero", "positive"}:
        findings.append("LIGHTNING_EXPECTED_COUNTS_INVALID")
    elif not all(_strict_int(expected_counts.get(name)) and expected_counts[name] >= 0 for name in expected_counts):
        findings.append("LIGHTNING_EXPECTED_COUNTS_INVALID")
    if findings:
        receipt.update(status="BLOCKED", findings=sorted(set(findings)))
        return receipt, None, sorted(set(findings))

    source, path_error = contained_regular(workspace, expected_path)
    if path_error:
        findings.append(f"{path_error}:{LIGHTNING_ROLE}")
        receipt.update(status="BLOCKED", findings=sorted(set(findings)))
        return receipt, None, sorted(set(findings))
    try:
        # Hash and parse the same immutable byte buffer.  The parser never
        # reopens the source, so receipt content and hash refer to one value.
        payload = source.read_bytes()
    except OSError:
        findings.append("SOURCE_UNREADABLE:lgt")
        receipt.update(status="BLOCKED", findings=findings)
        return receipt, None, findings
    actual_hash = sha256_bytes(payload)
    receipt["sha256"] = actual_hash
    if actual_hash != expected_hash:
        findings.append("SOURCE_SHA256_MISMATCH:lgt")
    if not findings:
        summary, parse_findings = parse_lightning_bytes(
            payload, contract, expected_counts
        )
        receipt.update(summary)
        receipt["content_validation"] = "PASS" if not parse_findings else "BLOCKED"
        findings.extend(parse_findings)
    else:
        receipt["content_validation"] = "NOT_RUN_HASH_MISMATCH"
    receipt["status"] = "PASS" if not findings else "BLOCKED"
    if findings:
        receipt["findings"] = sorted(set(findings))
    return receipt, source if not findings else None, sorted(set(findings))


def audit_temperature_observations(
    workspace: Path,
    row: dict[str, str],
    declarations: object,
) -> tuple[
    list[dict[str, object]],
    list[tuple[dict[str, object], Path]],
    list[str],
]:
    """Audit only the declared temperature-observation bytes.

    This deliberately does not inspect observation contents or infer QC.  A
    null hash is an explicit assertion that the exact legacy reader path is
    absent; every other declaration is checked with the normal immutable-file
    audit.
    """
    receipts: list[dict[str, object]] = []
    sources: list[tuple[dict[str, object], Path]] = []
    findings: list[str] = []
    if not isinstance(declarations, list) or not declarations:
        findings.append("TEMPERATURE_OBSERVATIONS_NOT_DECLARED")
        if declarations is not None and not isinstance(declarations, list):
            findings.append("TEMPERATURE_OBSERVATION_DECLARATIONS_MALFORMED")
        return receipts, sources, findings

    seen: set[str] = set()
    expected_prefix = "ANAL/NE57/DAOU/00/lapsprd"
    for declaration in declarations:
        if not isinstance(declaration, dict):
            findings.append("TEMPERATURE_OBSERVATION_DECLARATION_MALFORMED")
            continue
        role_value = declaration.get("role")
        if not isinstance(role_value, str) or role_value not in OBSERVATION_ROLES:
            findings.append(f"TEMPERATURE_OBSERVATION_UNKNOWN_ROLE:{role_value}")
            continue
        role = role_value
        if role in seen:
            findings.append(f"TEMPERATURE_OBSERVATION_DUPLICATE_ROLE:{role}")
            continue
        seen.add(role)

        expected_path = f"{expected_prefix}/{role}/{row.get('laps_stamp', '')}.{role}"
        declared_path = declaration.get("path")
        expected_hash_present = "sha256" in declaration
        expected_hash = declaration.get("sha256")
        receipt: dict[str, object] = {
            "role": role,
            "source_path": declared_path if isinstance(declared_path, str) else "",
            "expected_sha256": expected_hash,
            "scope": "INPUT_BYTES_ONLY",
            "content_validation": "NOT_RUN",
        }
        receipts.append(receipt)
        declaration_findings: list[str] = []
        if declared_path != expected_path:
            declaration_findings.append(f"TEMPERATURE_OBSERVATION_PATH_MISMATCH:{role}")
        if not expected_hash_present:
            declaration_findings.append(f"TEMPERATURE_OBSERVATION_SHA256_NOT_DECLARED:{role}")
        if declaration_findings:
            receipt.update(status="BLOCKED", findings=declaration_findings)
            findings.extend(declaration_findings)
            continue

        # Path equality above makes this safe to pass to the shared audit.
        relative = expected_path
        if expected_hash is None:
            source, path_error = contained_regular(workspace, relative)
            if path_error == "SOURCE_REGULAR_FILE_MISSING" and not source.exists() and not source.is_symlink():
                receipt["sha256"] = None
                receipt["status"] = "EXPECTED_ABSENT"
                continue
            reason = (
                f"TEMPERATURE_OBSERVATION_EXPECTED_ABSENT_BUT_PRESENT:{role}"
                if source.exists() or source.is_symlink()
                else f"TEMPERATURE_OBSERVATION_ABSENCE_AUDIT_FAILED:{role}"
            )
            declaration_findings.append(reason)
            if path_error and path_error != "SOURCE_REGULAR_FILE_MISSING":
                declaration_findings.append(f"{path_error}:{role}")
            receipt.update(status="BLOCKED", findings=declaration_findings)
            findings.extend(declaration_findings)
            continue

        receipt_from_file, source, audit_findings = audit_declared_file(
            workspace,
            relative,
            expected_hash,
            role,
            f"{expected_prefix}/{role}",
        )
        receipt.update(receipt_from_file)
        receipt["scope"] = "INPUT_BYTES_ONLY"
        receipt["content_validation"] = "NOT_RUN"
        findings.extend(audit_findings)
        if source is not None and not audit_findings:
            sources.append((receipt, source))

    missing_roles = [role for role in OBSERVATION_ROLES if role not in seen]
    if missing_roles:
        findings.append("TEMPERATURE_OBSERVATIONS_NOT_DECLARED")
        findings.extend(
            f"TEMPERATURE_OBSERVATION_ROLE_NOT_DECLARED:{role}" for role in missing_roles
        )
    return receipts, sources, findings


def audit_surface_observation(workspace: Path, row: dict[str, str], declaration: object, *, previous: bool = False) -> tuple:
    """Bind raw LSO bytes for the pinned USE_LSO_QC=0 surface configuration."""
    prefix = "ANAL/NE57/DAOU/00/lapsprd/lso"
    role = "previous_lso" if previous else "lso"
    stamp = row["laps_stamp"]
    if previous:
        # Pinned surface batch mode: ihours=1, LAPS_CYCLE_TIME_CMN=3600.
        valid = datetime.fromisoformat(row["valid_time_utc"].replace("Z", "+00:00"))
        stamp = (valid - timedelta(seconds=3600)).strftime("%y%j%H%M")
    expected_path = f"{prefix}/{stamp}.lso"
    if not isinstance(declaration, dict) or declaration.get("path") != expected_path:
        findings = ["SURFACE_LSO_DECLARATION_MISSING_OR_INVALID"]
        return {"role": role, "source_path": expected_path, "status": "BLOCKED",
                "scope": "INPUT_BYTES_ONLY", "findings": findings}, None, findings
    if previous and "sha256" in declaration and declaration["sha256"] is None:
        source, error = contained_regular(workspace, expected_path)
        absent = error == "SOURCE_REGULAR_FILE_MISSING" and not source.exists() and not source.is_symlink()
        findings = [] if absent else ["PREVIOUS_LSO_EXPECTED_ABSENCE_FAILED"]
        return {"role": role, "source_path": expected_path, "expected_sha256": None,
                "sha256": None, "status": "EXPECTED_ABSENT" if absent else "BLOCKED",
                "scope": "INPUT_BYTES_ONLY", "content_validation": "NOT_RUN",
                "findings": findings}, None, findings
    receipt, source, findings = audit_declared_file(
        workspace, expected_path, declaration.get("sha256"), role, prefix)
    receipt.update(scope="INPUT_BYTES_ONLY", content_validation="NOT_RUN")
    return receipt, source if not findings else None, findings


def audit_satellite_observation(workspace: Path, row: dict[str, str], declaration: object) -> tuple:
    """Bind target-hour processed KOGK2A LVD bytes, not raw satellite retrieval."""
    prefix = "ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a"
    expected_path = f"{prefix}/{row['laps_stamp']}.lvd"
    if not isinstance(declaration, dict) or declaration.get("path") != expected_path:
        findings = ["SATELLITE_LVD_DECLARATION_MISSING_OR_INVALID"]
        return {"role": "lvd", "source_path": expected_path, "status": "BLOCKED",
                "scope": "INPUT_BYTES_ONLY", "findings": findings}, None, findings
    receipt, source, findings = audit_declared_file(
        workspace, expected_path, declaration.get("sha256"), "lvd", prefix)
    receipt.update(scope="INPUT_BYTES_ONLY", content_validation="NOT_RUN")
    return receipt, source if not findings else None, findings


def audit_lrs_selection(workspace: Path, row: dict[str, str], declarations: object) -> tuple:
    """Bind the complete LRS candidate set; reproduce the legacy nearest-time choice."""
    selection = {"status": "BLOCKED", "scope": "INPUT_BYTES_ONLY",
                 "content_validation": "NOT_RUN", "selected_path": None,
                 "policy": "NEAREST_EARLIER_TIE_WITHIN_3600_SECONDS", "inventory": []}
    sources: list = []
    findings: list[str] = []
    if not isinstance(declarations, list):
        return selection, sources, ["LRS_INPUTS_NOT_DECLARED"]
    prefix = "ANAL/NE57/DAOU/00/lapsprd/lrs"
    directory = workspace / prefix
    current = workspace
    for part in Path(prefix).parts:
        current /= part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            return selection, sources, ["LRS_DIRECTORY_INVALID"]
    actual = {path.relative_to(workspace).as_posix() for path in directory.glob("*.lrs")}
    declared: set[str] = set()
    candidates: list = []
    valid = datetime.fromisoformat(row["valid_time_utc"].replace("Z", "+00:00"))
    for item in declarations:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            findings.append("LRS_DECLARATION_MALFORMED")
            continue
        path = item["path"]
        name = PurePosixPath(path).name
        if path in declared:
            findings.append("LRS_DUPLICATE_PATH")
            continue
        declared.add(path)
        try:
            if path != f"{prefix}/{name}" or not re.fullmatch(r"\d{9}\.lrs", name):
                raise ValueError("unsupported LRS filename")
            # lapsparms.for pins iyear_earliest=1950, unlike Python's %y cutoff.
            yy = int(name[:2])
            year = (1900 if yy >= 50 else 2000) + yy
            time = datetime.strptime(f"{year}{name[2:9]}", "%Y%j%H%M").replace(tzinfo=timezone.utc)
            if time.strftime("%y%j%H%M") != name[:9]:
                raise ValueError("invalid LRS timestamp")
            seconds = (time - datetime(1960, 1, 1, tzinfo=timezone.utc)).total_seconds()
            if not 0 <= seconds <= 2147483647:
                raise ValueError("LRS timestamp outside native INTEGER*4 range")
        except ValueError:
            findings.append("LRS_PATH_OR_TIMESTAMP_INVALID")
            continue
        receipt, source, errors = audit_declared_file(workspace, path, item.get("sha256"), "lrs", prefix)
        receipt.update(scope="INPUT_BYTES_ONLY", content_validation="NOT_RUN")
        selection["inventory"].append(receipt)
        findings.extend(errors)
        if source is not None and not errors:
            sources.append((receipt, source))
            candidates.append((abs((time - valid).total_seconds()), time, path))
    if declared != actual:
        findings.append("LRS_CANDIDATE_SET_MISMATCH")
    selection["inventory_sha256"] = canonical_sha256(selection["inventory"])
    if findings:
        return selection, [], sorted(set(findings))
    if not candidates:
        selection["status"] = "EXPECTED_ABSENT"
    else:
        distance, _, path = min(candidates)
        selection.update(nearest_path=path, offset_seconds=distance)
        selection["status"] = "SELECTED" if distance <= 3600 else "OUTSIDE_WINDOW"
        if distance <= 3600:
            selection["selected_path"] = path
    return selection, sources, []


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

    temperature_observations = spec.get("temperature_observations")
    expected_case_ids = {case_id for case_id, _, _ in EXPECTED_CASES}
    if temperature_observations is None:
        temperature_observations_by_case: dict[str, object] = {}
    elif not isinstance(temperature_observations, dict):
        blockers.append("TEMPERATURE_OBSERVATIONS_SPEC_NOT_OBJECT")
        temperature_observations_by_case = {}
    else:
        temperature_observations_by_case = temperature_observations
        if set(temperature_observations) != expected_case_ids:
            blockers.append("TEMPERATURE_OBSERVATIONS_CASE_KEYS_INVALID")

    lightning_contract = spec.get("lightning_contract")
    lightning_contract_findings = validate_lightning_contract(
        lightning_contract, required=True
    )
    blockers.extend(lightning_contract_findings)
    lightning_observations = spec.get("lightning_observations")
    lightning_observations_by_case: dict[str, object]
    if not isinstance(lightning_observations, dict):
        blockers.append("LIGHTNING_OBSERVATIONS_SPEC_NOT_OBJECT")
        lightning_observations_by_case = {}
    else:
        lightning_observations_by_case = lightning_observations
        blockers.extend(
            validate_lightning_declarations(
                lightning_observations, lightning_contract if isinstance(lightning_contract, dict) else {}
            )
        )

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
        observation_declarations = temperature_observations_by_case.get(row["case_id"])
        observation_receipts, observation_sources, observation_findings = (
            audit_temperature_observations(
                workspace, row, observation_declarations
            )
        )
        input_receipts.extend(observation_receipts)
        input_sources.extend(observation_sources)
        lightning_declaration = lightning_observations_by_case.get(row["case_id"])
        lightning_receipt, lightning_source, lightning_findings = (
            audit_lightning_observation(
                workspace, row, lightning_declaration, lightning_contract
            )
        )
        input_receipts.append(lightning_receipt)
        if lightning_source is not None:
            input_sources.append((lightning_receipt, lightning_source))
        case_blockers.extend(lightning_findings)
        blockers.extend(lightning_findings)
        surface_declarations = spec.get("surface_observations", {})
        surface_declaration = surface_declarations.get(row["case_id"]) if isinstance(surface_declarations, dict) else None
        surface_receipt, surface_source, surface_findings = audit_surface_observation(workspace, row, surface_declaration)
        input_receipts.append(surface_receipt)
        if surface_source is not None:
            input_sources.append((surface_receipt, surface_source))
        case_blockers.extend(surface_findings)
        case_blockers.append("SURFACE_OBSERVATION_CONTENT_NOT_VALIDATED")
        blockers.extend(surface_findings)
        previous_declarations = spec.get("surface_previous_observations", {})
        previous_declaration = previous_declarations.get(row["case_id"]) if isinstance(previous_declarations, dict) else None
        previous_receipt, previous_source, previous_findings = audit_surface_observation(workspace, row, previous_declaration, previous=True)
        input_receipts.append(previous_receipt)
        if previous_source is not None:
            input_sources.append((previous_receipt, previous_source))
        case_blockers.extend(previous_findings)
        blockers.extend(previous_findings)
        satellite_declarations = spec.get("satellite_observations", {})
        satellite_declaration = satellite_declarations.get(row["case_id"]) if isinstance(satellite_declarations, dict) else None
        satellite_receipt, satellite_source, satellite_findings = audit_satellite_observation(workspace, row, satellite_declaration)
        input_receipts.append(satellite_receipt)
        if satellite_source is not None:
            input_sources.append((satellite_receipt, satellite_source))
        case_blockers.extend(satellite_findings)
        case_blockers.append("SATELLITE_OBSERVATION_CONTENT_NOT_VALIDATED")
        blockers.extend(satellite_findings)
        lrs_selection, lrs_sources, lrs_findings = audit_lrs_selection(workspace, row, spec.get("lrs_inputs"))
        input_receipts.extend(lrs_selection["inventory"])
        input_sources.extend(lrs_sources)
        case_blockers.extend(lrs_findings)
        blockers.extend(lrs_findings)
        case_blockers.extend(observation_findings)
        blockers.extend(observation_findings)
        case_blockers.append("TEMPERATURE_OBSERVATION_CONTENT_NOT_VALIDATED")
        blockers.append("TEMPERATURE_OBSERVATION_CONTENT_NOT_VALIDATED")
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
                expected_copy_hash = (
                    receipt.get("expected_sha256")
                    if receipt.get("role") == LIGHTNING_ROLE
                    else receipt["sha256"]
                )
                copied_hash = immutable_copy(
                    source, destination, str(expected_copy_hash), output_root
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
            try:
                vrt_payload = read_verified_bytes(
                    vrt_source, str(vrt_receipt.get("sha256", ""))
                )
                vrt_status, vrt_findings = vrt_complete(
                    vrt_payload, row["valid_time_utc"]
                )
            except ReplayError as error:
                vrt_status, vrt_findings = "BLOCKED", [
                    f"VRT_SNAPSHOT_BIND_FAILED:{error}"
                ]
        case_blockers.extend(vrt_findings)
        blockers.extend(vrt_findings)
        lrs_selection["inventory_sha256"] = canonical_sha256(lrs_selection["inventory"])
        declared_input_receipt_sha256 = canonical_sha256(
            {"inputs": [
                {
                    "role": item["role"],
                    "source_path": item["source_path"],
                    "sha256": item.get("sha256"),
                    "expected_sha256": item.get("expected_sha256"),
                    "status": item.get("status"),
                }
                for item in input_receipts
            ], "lrs_selection": lrs_selection}
        )
        try:
            runtime_inputs = materialize_case_runtime(output_root, row, asset_sources, input_sources)
            case_blockers.extend(runtime_inputs["findings"])
            case_blockers.extend(runtime_inputs["execution_blockers"])
        except (OSError, ValueError, ReplayError) as error:
            runtime_inputs = {"status": "PARTIAL", "execution_ready": False,
                              "findings": [f"RUNTIME_PREPARATION_FAILED:{error}"]}
            case_blockers.extend(runtime_inputs["findings"])
        blockers.extend(case_blockers)
        cases.append(
            {
                "case_id": row["case_id"],
                "valid_time_utc": row["valid_time_utc"],
                "laps_stamp": row["laps_stamp"],
                "status": "BLOCKED",
                "input_closure_sha256": None,
                "declared_input_receipt_sha256": declared_input_receipt_sha256,
                "temperature_observation_scope": "INPUT_BYTES_ONLY",
                "lightning_observation_scope": "ASCII_FIXED_GRID_CONTENT_AND_HASH",
                "lrs_selection": lrs_selection,
                "temperature_observation_content_validation": "NOT_RUN",
                "lightning_observation_content_validation": lightning_receipt.get(
                    "content_validation", "NOT_RUN"
                ),
                "inputs": input_receipts,
                "runtime_inputs": runtime_inputs,
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
        item.get("status") == "EXPECTED_ABSENT"
        or (
            item.get("status") == "PASS"
            and item.get("materialized_sha256") == item.get("sha256")
        )
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
