#!/usr/bin/env python3
"""Build and compare an isolated Cloud-BAL diagnostic WPS patch.

The operational LAPS file is copied byte-for-byte.  Only hydrometeor cells
changed by the real-data Cloud-BAL column stage are replaced in the patch.
All other fields, including wind, remain operational values.  This is not a
full-pipeline candidate and cannot isolate a Cloud-BAL increment while the
canonical and operational mass bases remain unresolved.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import os
import stat
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from netCDF4 import Dataset

from compare_baseline import _records, read_wps
from cloud_bal_transaction import verify_current_generation
from prepare_operational_comparison import DIAGNOSTIC_PATCH_VALID, prepare


HYDROMETEORS = {
    "QC": ("background_cloud_water", "candidate_cloud_water"),
    "QI": ("background_cloud_ice", "candidate_cloud_ice"),
    "QR": ("background_rain", "candidate_rain"),
    "QS": ("background_snow", "candidate_snow"),
    "QG": ("background_graupel", "candidate_graupel"),
}
SHADOW_CONFIGURATION = "radar-only-shadow-ifx-2026-v3"
AUTHORITATIVE_HOURS = (12, 13, 14, 15)
# ``full`` is the original four-hour replay contract.  The explicit P1 scope
# is limited to the archived operational LAPS inventory (13/14/15 UTC).
FULL_SCOPE = "full"
P1_OPERATIONAL_SCOPE = "p1-operational"
P1_OPERATIONAL_HOURS = (13, 14, 15)
P1_EXCLUDED_UTC_HOURS = (12,)
P1_EXCLUSION_STATUS = "EXCLUDED_HISTORICAL_NOT_AVAILABLE"
P1_EXCLUSION_REASON = "ARCHIVED_OPERATIONAL_LAPS_MISSING"
P1_EXCLUSION_PROVENANCE = (
    "OPERATIONAL_COMPARISON_CONTRACT_2026_08_16_INVENTORY"
)
PLOT_LEVEL_PA = 55000
HYDROMETEOR_LIMIT_GKG = 15.0
HYDROMETEOR_DELTA_LIMIT_GKG = 15.0
WIND_SPEED_LIMIT_MS = 80.0
WIND_DELTA_LIMIT_MS = 0.1
DIAGNOSTIC_COMPLETE = "COMPLETE_DIAGNOSTIC"
DIAGNOSTIC_PARTIAL = "PARTIAL_DIAGNOSTIC"
DIAGNOSTIC_INCOMPLETE = "INCOMPLETE_DIAGNOSTIC"
COMPARISON_NOT_READY_MASS = "NOT_READY_MASS_BASIS_UNRESOLVED"
NO_DIAGNOSTIC_ARTIFACT = "NO_DIAGNOSTIC_PATCH_AVAILABLE"


@dataclass(frozen=True)
class CasePaths:
    case_id: str
    original: Path
    live_original: Path
    shadow: Path


@dataclass(frozen=True)
class InputSnapshot:
    path: Path
    source_device: int
    source_inode: int
    source_size: int
    sha256: str


def strict_root_path(
    value: Path,
    label: str,
    *,
    must_exist: bool = True,
    allow_final_symlink: bool = False,
) -> Path:
    """Return an absolute root after checking every lexical path component."""

    raw = value if value.is_absolute() else Path.cwd() / value
    if ".." in raw.parts:
        raise ValueError(f"{label} must not contain parent traversal: {value}")

    component = Path(raw.anchor)
    missing = False
    parts = raw.parts[1:]
    for index, part in enumerate(parts):
        component /= part
        try:
            mode = os.lstat(component).st_mode
        except FileNotFoundError:
            missing = True
            continue
        except OSError as exc:
            raise ValueError(f"{label} is not accessible: {value}") from exc
        if missing:
            raise ValueError(f"{label} has an invalid lexical path: {value}")
        final_pointer = allow_final_symlink and index == len(parts) - 1
        if stat.S_ISLNK(mode) and not final_pointer:
            raise ValueError(f"{label} contains a symlink component: {value}")

    if must_exist and missing:
        raise ValueError(f"{label} is not an existing directory: {value}")
    lexical = Path(os.path.abspath(os.fspath(raw)))
    if must_exist and not lexical.is_dir():
        raise ValueError(f"{label} is not an existing directory: {value}")
    return lexical


def normalize_scope(scope: str | None) -> str:
    """Return one of the two explicit comparison scopes."""

    if scope is None:
        return FULL_SCOPE
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("comparison scope must be a non-empty string")
    normalized = scope.strip().lower()
    if normalized not in (FULL_SCOPE, P1_OPERATIONAL_SCOPE):
        choices = f"{FULL_SCOPE!r} or {P1_OPERATIONAL_SCOPE!r}"
        raise ValueError(f"unknown comparison scope {scope!r}; use {choices}")
    return normalized


def scope_contract(scope: str | None = None) -> dict[str, object]:
    """Return the hour and exclusion contract for a comparison scope."""

    scope = normalize_scope(scope)
    if scope == P1_OPERATIONAL_SCOPE:
        return {
            "scope": scope,
            "hours": P1_OPERATIONAL_HOURS,
            "excluded_utc_hours": P1_EXCLUDED_UTC_HOURS,
            "excluded_utc_status": P1_EXCLUSION_STATUS,
            "excluded_utc_reason": P1_EXCLUSION_REASON,
            "excluded_utc_provenance": P1_EXCLUSION_PROVENANCE,
        }
    return {
        "scope": FULL_SCOPE,
        "hours": AUTHORITATIVE_HOURS,
        "excluded_utc_hours": (),
        "excluded_utc_status": "NOT_APPLICABLE_FULL_SCOPE",
        "excluded_utc_reason": "NOT_APPLICABLE_FULL_SCOPE",
        "excluded_utc_provenance": "FULL_SCOPE_INCLUDES_12_UTC",
    }


def scope_exclusions(scope: str | None = None) -> list[dict[str, object]]:
    """Return explicit records for cases intentionally outside a scope."""

    contract = scope_contract(scope)
    return [
        {
            "case_id": f"20260816T{hour:02d}0000Z",
            "valid_time": f"2026-08-16T{hour:02d}:00:00Z",
            "status": contract["excluded_utc_status"],
            "reason": contract["excluded_utc_reason"],
            "provenance": contract["excluded_utc_provenance"],
        }
        for hour in contract["excluded_utc_hours"]
    ]


def validate_hours(
    hours: Sequence[int], allow_partial: bool = False,
    scope: str = FULL_SCOPE,
) -> tuple[int, ...]:
    """Validate the requested diagnostic hours before creating any output.

    A scope's ordered UTC hours are authoritative only when all of them are
    requested.  A smaller replay is useful for debugging only when it is
    explicitly marked as partial; it can never become authoritative.
    """

    contract = scope_contract(scope)
    scope = contract["scope"]
    scoped_hours = contract["hours"]
    requested = tuple(hours)
    if not requested:
        raise ValueError("at least one diagnostic hour is required")
    if any(isinstance(hour, bool) or not isinstance(hour, int) for hour in requested):
        raise ValueError("diagnostic hours must be integers")

    unknown = sorted(set(requested) - set(AUTHORITATIVE_HOURS))
    if unknown:
        raise ValueError(f"unknown diagnostic hour(s): {unknown}")

    excluded = sorted(set(requested) - set(scoped_hours))
    if excluded:
        if scope == P1_OPERATIONAL_SCOPE and 12 in excluded:
            raise ValueError(
                "12 UTC is excluded from the P1 operational scope; "
                "the archived operational LAPS product is missing"
            )
        raise ValueError(
            f"diagnostic hour(s) {excluded} are outside comparison scope {scope}"
        )

    duplicate = sorted({hour for hour in requested if requested.count(hour) > 1})
    if duplicate:
        raise ValueError(f"duplicate diagnostic hour(s): {duplicate}")

    if requested != tuple(sorted(requested)):
        raise ValueError(
            "diagnostic hours must be in authoritative order: "
            f"{scoped_hours}"
        )
    if requested != scoped_hours and not allow_partial:
        raise ValueError(
            "a diagnostic hour subset requires --allow-partial-diagnostic"
        )
    return requested


def plot_field_specs(level: int = PLOT_LEVEL_PA) -> list[dict]:
    """Return the fixed plot contract for the one diagnostic level.

    Plot IDs and selectors must be generated together so a figure and its
    sealed comparison manifest cannot silently use different levels.
    """

    if isinstance(level, bool) or not isinstance(level, (int, float)):
        raise ValueError("plot level must be numeric")
    if float(level) != float(PLOT_LEVEL_PA):
        raise ValueError(f"plot level must equal PLOT_LEVEL_PA ({PLOT_LEVEL_PA})")
    level_hpa = int(PLOT_LEVEL_PA // 100)
    suffix = f"{level_hpa}hpa"
    return [
        {
            "plot_id": f"rain-{suffix}", "field": "QR",
            "level": float(PLOT_LEVEL_PA),
            "scale": {"value_min": 0.0, "value_max": 0.02,
                      "delta_abs_max": 0.02},
        },
        {
            "plot_id": f"snow-{suffix}", "field": "QS",
            "level": float(PLOT_LEVEL_PA),
            "scale": {"value_min": 0.0, "value_max": 0.02,
                      "delta_abs_max": 0.02},
        },
        {
            "plot_id": f"u-wind-{suffix}", "field": "UU",
            "level": float(PLOT_LEVEL_PA),
            "scale": {"value_min": -60.0, "value_max": 60.0,
                      "delta_abs_max": 1.0},
        },
    ]


def status_values(
    requested_hours: Sequence[int], requested_case_set_complete: bool,
    available_pairs: bool = True, scope: str = FULL_SCOPE,
) -> dict[str, object]:
    """Build the separate diagnostic-execution and comparison statuses."""

    if not isinstance(requested_case_set_complete, bool):
        raise ValueError("requested-case completeness must be boolean")
    if not isinstance(available_pairs, bool):
        raise ValueError("available-pairs state must be boolean")
    contract = scope_contract(scope)
    scope = contract["scope"]
    scoped_hours = contract["hours"]
    requested = validate_hours(requested_hours, allow_partial=True, scope=scope)
    authoritative_complete = (
        requested == scoped_hours
        and requested_case_set_complete
        and available_pairs
    )
    if requested != scoped_hours:
        execution = DIAGNOSTIC_PARTIAL
    elif authoritative_complete:
        execution = DIAGNOSTIC_COMPLETE
    else:
        execution = DIAGNOSTIC_INCOMPLETE
    comparison_readiness = (
        COMPARISON_NOT_READY_MASS
        if authoritative_complete
        else "NOT_READY_REQUESTED_CASES_INCOMPLETE"
    )
    return {
        "diagnostic_execution": execution,
        "diagnostic_exit": 0 if authoritative_complete else 3,
        "comparison_readiness": comparison_readiness,
        "comparison_status": comparison_readiness,
        "available_artifact_validity": (
            DIAGNOSTIC_PATCH_VALID if available_pairs else NO_DIAGNOSTIC_ARTIFACT
        ),
        "algorithm_comparison_ready": False,
        "promotion_eligible": False,
        "mass_basis_gate": "BLOCKED_UNRESOLVED",
        "authoritative_complete": authoritative_complete,
        "requested_hours": list(requested),
        "authoritative_hours": list(scoped_hours),
        "requested_case_set_complete": requested_case_set_complete,
        "comparison_scope": scope,
        "scope_hours": list(scoped_hours),
        "excluded_utc_hours": list(contract["excluded_utc_hours"]),
        "excluded_utc_status": contract["excluded_utc_status"],
        "excluded_utc_reason": contract["excluded_utc_reason"],
        "excluded_utc_provenance": contract["excluded_utc_provenance"],
    }


def render_status(values: dict[str, object]) -> str:
    """Render the machine-readable status file without ambiguous aliases."""

    required = (
        "diagnostic_execution", "comparison_readiness",
        "comparison_status", "available_artifact_validity", "mass_basis_gate",
        "diagnostic_exit", "algorithm_comparison_ready", "promotion_eligible",
        "authoritative_complete", "requested_hours", "authoritative_hours",
        "requested_case_set_complete", "comparison_scope", "scope_hours",
        "excluded_utc_hours", "excluded_utc_reason",
        "excluded_utc_status", "excluded_utc_provenance",
    )
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError(f"status values missing keys: {missing}")
    text_keys = required[:5]
    if any(
        not isinstance(values[key], str) or len(values[key].splitlines()) != 1
        for key in text_keys
    ):
        raise ValueError("status values must be single-line strings")
    expected = status_values(
        values["requested_hours"],
        values["requested_case_set_complete"],
        available_pairs=values["available_artifact_validity"] == DIAGNOSTIC_PATCH_VALID,
        scope=values["comparison_scope"],
    )
    if any(values[key] != expected[key] for key in expected):
        raise ValueError("status values are inconsistent with the case inventory")
    lines = [
        f"diagnostic_execution={values['diagnostic_execution']}",
        f"diagnostic_exit={values['diagnostic_exit']}",
        f"comparison_readiness={values['comparison_readiness']}",
        f"comparison_status={values['comparison_status']}",
        f"available_artifact_validity={values['available_artifact_validity']}",
        f"comparison_scope={values['comparison_scope']}",
        "scope_hours=" + ",".join(str(hour) for hour in values["scope_hours"]),
        "excluded_utc_hours=" + (
            ",".join(str(hour) for hour in values["excluded_utc_hours"])
            if values["excluded_utc_hours"] else "NONE"
        ),
        f"excluded_utc_status={values['excluded_utc_status']}",
        f"excluded_utc_reason={values['excluded_utc_reason']}",
        f"excluded_utc_provenance={values['excluded_utc_provenance']}",
        "algorithm_comparison_ready=false",
        "promotion_eligible=false",
        f"mass_basis_gate={values['mass_basis_gate']}",
        "full_end_to_end=NO",
        "dynamic_balance_authorized=NO",
        "operational_original_modified=NO",
        "science_promotion=NO",
    ]
    return "\n".join(lines) + "\n"


def sha256(path: Path) -> str:
    payload, _ = stable_file_bytes(path)
    return hashlib.sha256(payload).hexdigest()


def file_identity(status: os.stat_result) -> tuple[int, ...]:
    return (
        status.st_dev, status.st_ino, status.st_size,
        status.st_mtime_ns, status.st_ctime_ns, status.st_nlink,
    )


def open_directory(path: Path) -> int:
    """Open an absolute directory without following symlink components."""

    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError:
        os.close(descriptor)
        raise


def stable_file_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    parent_fd = None
    descriptor = None
    try:
        absolute = Path(os.path.abspath(path))
        parent_fd = open_directory(absolute.parent)
        descriptor = os.open(
            absolute.name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        if parent_fd is not None:
            os.close(parent_fd)
        raise ValueError(f"unsafe input file: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"input must be an independent regular file: {path}")
        blocks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
        after = os.fstat(descriptor)
        try:
            named = os.stat(
                absolute.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as exc:
            raise ValueError(f"input path changed while being read: {path}") from exc
        source_changed = file_identity(before) != file_identity(after)
        path_changed = (named.st_dev, named.st_ino) != (
            after.st_dev, after.st_ino
        )
        if source_changed or path_changed:
            raise ValueError(f"input changed while being read: {path}")
        payload = b"".join(blocks)
        if len(payload) != after.st_size:
            raise ValueError(f"input size changed while being read: {path}")
        return payload, after
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def snapshot_input(
    source: Path, destination: Path, *, mode: int = 0o400
) -> InputSnapshot:
    """Copy the exact bytes returned by one stable source-file read."""

    payload, source_status = stable_file_bytes(source)
    digest = hashlib.sha256(payload).hexdigest()
    try:
        parent_fd = open_directory(destination.parent)
    except OSError as exc:
        raise ValueError(f"unsafe input snapshot destination: {destination}") from exc
    output_fd = None
    try:
        output_fd = os.open(
            destination.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        view = memoryview(payload)
        while view:
            written = os.write(output_fd, view)
            if written <= 0:
                raise ValueError(f"input snapshot write failed: {destination}")
            view = view[written:]
        os.fchmod(output_fd, mode)
        os.fsync(output_fd)
        copied = os.fstat(output_fd)
        named = os.stat(
            destination.name, dir_fd=parent_fd, follow_symlinks=False
        )
        os.lseek(output_fd, 0, os.SEEK_SET)
        copied_digest = hashlib.sha256()
        for block in iter(lambda: os.read(output_fd, 1024 * 1024), b""):
            copied_digest.update(block)
        verified = os.fstat(output_fd)
        copy_changed = file_identity(copied) != file_identity(verified)
        path_mismatch = (
            verified.st_dev, verified.st_ino, verified.st_size, verified.st_nlink
        ) != (named.st_dev, named.st_ino, len(payload), 1)
        checksum_mismatch = copied_digest.hexdigest() != digest
        if copy_changed or path_mismatch or checksum_mismatch:
            raise ValueError(f"input snapshot checksum mismatch: {source}")
        return InputSnapshot(
            path=destination,
            source_device=source_status.st_dev,
            source_inode=source_status.st_ino,
            source_size=source_status.st_size,
            sha256=digest,
        )
    except (OSError, ValueError) as exc:
        if output_fd is not None:
            try:
                os.unlink(destination.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"unsafe input snapshot destination: {destination}") from exc
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(parent_fd)


def paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve(strict=True)
    right = right.resolve(strict=True)
    return left == right or left in right.parents or right in left.parents


def require_matching_inputs(
    original: InputSnapshot, live: InputSnapshot, case_id: str = "input pair"
) -> None:
    if (original.source_device, original.source_inode) == (
        live.source_device, live.source_inode
    ):
        raise ValueError("archived and live operational inputs are the same file")
    if original.sha256 != live.sha256:
        raise ValueError(f"archived/live operational mismatch for {case_id}")


def archive_receipt(path: Path, digest: str | None = None) -> tuple[Path, str]:
    if digest is None:
        payload, _ = stable_file_bytes(path)
        digest = hashlib.sha256(payload).hexdigest()
    for parent in path.parents:
        receipt = parent / "SHA256SUMS"
        if not receipt.is_file():
            continue
        relative = path.relative_to(parent).as_posix()
        payload, _ = stable_file_bytes(receipt)
        for line in payload.decode("utf-8").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[0] == digest and parts[1].lstrip("*") == relative:
                return receipt, hashlib.sha256(payload).hexdigest()
    raise ValueError(f"archived operational input lacks a pre-existing receipt: {path}")


def shadow_generation(
    root: Path, source_commit: str
) -> tuple[Path, dict[str, dict], str]:
    if root.name != "current" or not root.is_symlink():
        raise ValueError("--shadow-root must be a committed current-generation pointer")
    generation = verify_current_generation(root.parent)
    if generation != root.resolve(strict=True):
        raise ValueError("--shadow-root does not resolve to the verified current generation")
    manifest_path = generation / "MANIFEST.json"
    manifest_bytes, _ = stable_file_bytes(manifest_path)
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("schema") != 2:
        raise ValueError("unsupported SHADOW generation manifest")
    if manifest.get("source_commit") != source_commit:
        raise ValueError("SHADOW generation source commit differs from --source-commit")
    if manifest.get("configuration") != SHADOW_CONFIGURATION:
        raise ValueError("SHADOW generation configuration is not the approved profile")
    summary_path = generation / "RUN_SUMMARY.json"
    summary_bytes, _ = stable_file_bytes(summary_path)
    summary = json.loads(summary_bytes.decode("utf-8"))
    if (summary.get("source_commit") != source_commit
            or summary.get("source_tree_clean") is not True
            or summary.get("numerical_contract") != "PASS"
            or summary.get("promotion_eligible") is not False):
        raise ValueError("SHADOW generation summary is not eligible for diagnostic use")
    products = manifest.get("products")
    if not isinstance(products, list):
        raise ValueError("SHADOW generation product inventory is invalid")
    by_path = {item.get("path"): item for item in products if isinstance(item, dict)}
    if len(by_path) != len(products):
        raise ValueError("SHADOW generation product inventory has duplicate paths")
    if verify_current_generation(root.parent) != generation:
        raise ValueError("SHADOW current generation changed while it was inspected")
    return generation, by_path, hashlib.sha256(manifest_bytes).hexdigest()


def write_record(stream, endian: str, payload: bytes) -> None:
    marker = struct.pack(endian + "i", len(payload))
    stream.write(marker)
    stream.write(payload)
    stream.write(marker)


def wps_records(path: Path) -> list[tuple[str, bytes]]:
    return list(_records(path))


def build_candidate(original: Path, shadow: Path, output: Path) -> dict:
    records = wps_records(original)
    if len(records) % 5:
        raise ValueError(f"incomplete WPS record group: {original}")

    modified_by_field: dict[str, int] = {field: 0 for field in HYDROMETEORS}
    modified_by_level: dict[str, int] = {}
    with Dataset(shadow) as dataset:
        if getattr(dataset, "result_authority", "") != "DIAGNOSTIC_PROPOSAL_ONLY":
            raise ValueError(f"unexpected SHADOW authority: {shadow}")
        if int(getattr(dataset, "operational_state_changed", 1)) != 0:
            raise ValueError(f"SHADOW diagnostic claims an operational change: {shadow}")

        pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
        rounded_pressure = np.rint(pressure).astype(np.int64)
        if (len(set(rounded_pressure.tolist())) != pressure.size
                or np.any(np.abs(pressure - rounded_pressure) > 0.5)):
            raise ValueError("diagnostic pressure levels do not map one-to-one to WPS levels")
        pressure_index = {int(value): index for index, value in enumerate(rounded_pressure)}
        above_ground = np.asarray(dataset.variables["above_ground"][:], dtype=bool)
        column_changed = np.asarray(dataset.variables["column_changed"][:], dtype=bool)
        radar_valid = np.asarray(dataset.variables["radar_valid"][:], dtype=bool)
        hydro_support = np.asarray(dataset.variables["hydro_support"][:], dtype=bool)
        replacement_union = np.zeros_like(column_changed)
        field_values = {
            field: (
                np.asarray(dataset.variables[background][:], dtype=np.float64),
                np.asarray(dataset.variables[candidate][:], dtype=np.float64),
            )
            for field, (background, candidate) in HYDROMETEORS.items()
        }
        expected_masks = {
            field: (
                above_ground
                & column_changed
                & np.isfinite(background)
                & np.isfinite(candidate)
                & (candidate != background)
            )
            for field, (background, candidate) in field_values.items()
        }
        applied_masks = {
            field: np.zeros_like(column_changed) for field in HYDROMETEORS
        }
        applied_levels: set[tuple[str, int]] = set()

        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("wb") as stream:
            for offset in range(0, len(records), 5):
                group = records[offset : offset + 5]
                endian = group[0][0]
                if any(item[0] != endian for item in group):
                    raise ValueError("mixed-endian WPS record group")
                metadata = group[1][1]
                field = metadata[60:69].decode("ascii", "replace").strip()
                level = int(round(struct.unpack(endian + "f", metadata[140:144])[0]))
                nx, ny = struct.unpack(endian + "ii", metadata[144:152])
                slab = group[4][1]

                if field in HYDROMETEORS and level in pressure_index:
                    k = pressure_index[level]
                    if (field, k) in applied_levels:
                        raise ValueError(f"duplicate WPS hydrometeor level: {field} {level}")
                    applied_levels.add((field, k))
                    background, candidate = field_values[field]
                    replacement = expected_masks[field][k]
                    if replacement.shape != (ny, nx):
                        raise ValueError(
                            f"grid mismatch for {field} at {level} Pa: "
                            f"{replacement.shape} != {(ny, nx)}"
                        )
                    values = np.frombuffer(slab, dtype=endian + "f4").copy().reshape(ny, nx)
                    if np.any(candidate[k][replacement] < 0.0):
                        raise ValueError(f"negative candidate {field} at {level} Pa")
                    values[replacement] = candidate[k][replacement].astype(np.float32)
                    slab = values.astype(endian + "f4", copy=False).tobytes(order="C")
                    count = int(np.count_nonzero(replacement))
                    replacement_union[k] |= replacement
                    applied_masks[field][k] = replacement
                    modified_by_field[field] += count
                    modified_by_level[str(level)] = modified_by_level.get(str(level), 0) + count

                for record_index, (_, payload) in enumerate(group):
                    write_record(stream, endian, slab if record_index == 4 else payload)
        temporary.replace(output)

        outside_support = replacement_union & ~hydro_support
        if np.any(outside_support):
            raise ValueError("hydrometeor replacement escaped Cloud-BAL support")
        for field in HYDROMETEORS:
            if not np.array_equal(applied_masks[field], expected_masks[field]):
                raise ValueError(f"WPS does not represent every canonical {field} change")
        flux_names = (
            "flux_input", "flux_deposited", "flux_suspended", "flux_boundary_exit",
            "flux_terrain_intercept", "flux_observation_blocked",
            "flux_no_echo_blocked",
            "flux_microphysical_loss", "flux_ledger_error",
        )
        flux = {name: float(getattr(dataset, name)) for name in flux_names}

    unique_modified = int(np.count_nonzero(replacement_union))
    radar_overlap = int(np.count_nonzero(replacement_union & radar_valid))
    return {
        "modified_by_field": modified_by_field,
        "modified_by_level": modified_by_level,
        "modified_cells": sum(modified_by_field.values()),
        "unique_modified_cells": unique_modified,
        "modified_cells_with_valid_radar": radar_overlap,
        "modified_cells_without_valid_radar": unique_modified - radar_overlap,
        "transport_lineage_available": False,
        "outside_hydrometeor_support_cells": 0,
        "flux_ledger": flux,
        "flux_relative_closure_error": abs(flux["flux_ledger_error"]) / max(
            abs(flux["flux_input"]), 1.0
        ),
    }


def valid(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (np.abs(values) < 1.0e20)


def compare_products(original: Path, candidate: Path) -> tuple[list[dict], dict]:
    old = read_wps(original)
    new = read_wps(candidate)
    if set(old) != set(new):
        raise ValueError("candidate WPS field inventory differs from the operational original")

    rows: list[dict] = []
    changed_fields: set[str] = set()
    for key in sorted(old, key=lambda item: (item[0], item[1], item[2])):
        field, level, hdate = key
        old_units, old_shape, old_values, old_metadata = old[key]
        new_units, new_shape, new_values, new_metadata = new[key]
        if (old_units, old_shape, old_metadata) != (new_units, new_shape, new_metadata):
            raise ValueError(f"metadata changed for {key}")
        common = valid(old_values) & valid(new_values)
        delta = new_values[common] - old_values[common]
        changed = int(np.count_nonzero(delta))
        if changed:
            changed_fields.add(field)
        if field in HYDROMETEORS:
            rows.append(
                {
                    "field": field,
                    "level_pa": int(round(level)),
                    "valid_time": hdate,
                    "valid_cells": int(np.count_nonzero(common)),
                    "changed_cells": changed,
                    "bias": float(np.mean(delta)) if delta.size else None,
                    "rms_delta": float(np.sqrt(np.mean(delta * delta))) if delta.size else None,
                    "max_abs_delta": float(np.max(np.abs(delta))) if delta.size else None,
                }
            )

    unauthorized = changed_fields - set(HYDROMETEORS)
    if unauthorized:
        raise ValueError(f"unauthorized WPS fields changed: {sorted(unauthorized)}")
    return rows, {"changed_fields": sorted(changed_fields)}


def arrays_at_level(path: Path, level: int) -> dict[str, np.ndarray]:
    fields = read_wps(path)
    arrays = {}
    for (field, record_level, _), (_, (nx, ny), slab, _) in fields.items():
        if int(round(record_level)) == level:
            arrays[field] = slab.reshape(ny, nx)
    return arrays


def finite_image(values: np.ndarray) -> np.ndarray:
    return np.where(valid(values), values, np.nan)


def plot_case(
    case_id: str,
    original: Path,
    candidate: Path,
    shadow: Path,
    level: int,
    output: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    old = arrays_at_level(original, level)
    new = arrays_at_level(candidate, level)
    old_hydro = sum(finite_image(old[field]) for field in HYDROMETEORS) * 1000.0
    new_hydro = sum(finite_image(new[field]) for field in HYDROMETEORS) * 1000.0
    old_speed = np.hypot(finite_image(old["UU"]), finite_image(old["VV"]))
    new_speed = np.hypot(finite_image(new["UU"]), finite_image(new["VV"]))

    with Dataset(shadow) as dataset:
        pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
        k = int(np.argmin(np.abs(pressure - level)))
        lon = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
        lat = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
        radar = np.asarray(dataset.variables["radar_dbz"][k], dtype=np.float64)
        radar_valid = np.asarray(dataset.variables["radar_valid"][k], dtype=bool)
        changed = np.asarray(dataset.variables["column_changed"][k], dtype=bool)

    hydro_delta = new_hydro - old_hydro

    fig, axes = plt.subplots(2, 4, figsize=(19, 9), constrained_layout=True)
    common = {"shading": "auto", "rasterized": True}
    panels = [
        (old_hydro, "Operational total hydrometeor", "viridis", 0.0, HYDROMETEOR_LIMIT_GKG, None),
        (new_hydro, "Diagnostic patch total hydrometeor", "viridis", 0.0, HYDROMETEOR_LIMIT_GKG, None),
        (hydro_delta, "Patch - operational", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-HYDROMETEOR_DELTA_LIMIT_GKG, vcenter=0.0,
                      vmax=HYDROMETEOR_DELTA_LIMIT_GKG)),
        (np.where(radar_valid, radar, np.nan), "S-band radar reflectivity", "turbo", 5.0, 65.0, None),
        (old_speed, "Operational wind speed", "magma", 0.0, WIND_SPEED_LIMIT_MS, None),
        (new_speed, "Diagnostic patch wind speed (copied)", "magma", 0.0, WIND_SPEED_LIMIT_MS, None),
        (new_speed - old_speed, "Patch - operational wind", "RdBu_r",
         -WIND_DELTA_LIMIT_MS, WIND_DELTA_LIMIT_MS, None),
        (changed.astype(float), "Cloud-BAL column-change mask", "Greys", 0.0, 1.0, None),
    ]
    units = ["g kg$^{-1}$", "g kg$^{-1}$", "g kg$^{-1}$", "dBZ",
             "m s$^{-1}$", "m s$^{-1}$", "m s$^{-1}$", "0/1"]
    for axis, panel, unit in zip(axes.ravel(), panels, units):
        values, title, cmap, vmin, vmax, norm = panel
        kwargs = {"cmap": cmap, **common}
        if norm is None:
            kwargs.update(vmin=vmin, vmax=vmax)
        else:
            kwargs["norm"] = norm
        image = axis.pcolormesh(lon, lat, values, **kwargs)
        axis.set_title(title)
        axis.set_xlabel("longitude")
        axis.set_ylabel("latitude")
        fig.colorbar(image, ax=axis, shrink=0.82, label=unit)
    fig.suptitle(
        f"{case_id} at {level / 100:.0f} hPa — operational/diagnostic-patch comparison\n"
        "Not a full-pipeline candidate; wind is copied and mass basis is unresolved",
        fontsize=14,
    )
    fig.savefig(output, dpi=150)
    plt.close(fig)


def case_paths(args, hour: int) -> CasePaths:
    case_id = f"20260816T{hour:02d}0000Z"
    filename = f"LAPS:2026-08-16_{hour:02d}:00"
    return CasePaths(
        case_id=case_id,
        original=args.original_root / f"20260816{hour:02d}" / filename,
        live_original=args.live_root / f"20260816{hour:02d}" / filename,
        shadow=args.shadow_root / f"{case_id}.nc",
    )


def validate_scope_inventory(original_root: Path, live_root: Path, scope: str) -> None:
    """Reject a scoped exclusion whose operational input is now present."""

    for hour in scope_contract(scope)["excluded_utc_hours"]:
        filename = f"LAPS:2026-08-16_{hour:02d}:00"
        paths = (
            original_root / f"20260816{hour:02d}" / filename,
            live_root / f"20260816{hour:02d}" / filename,
        )
        if any(path.exists() or path.is_symlink() for path in paths):
            raise ValueError(
                f"{hour:02d} UTC cannot remain excluded because an operational "
                "LAPS input is present"
            )


def artifact(root: Path, role: str, origin: str, path: Path) -> dict:
    result = {
        "evidence_role": role,
        "origin": origin,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "wind_coordinate": "GRID_RELATIVE",
    }
    if role == "REAL_OPERATIONAL_ORIGINAL":
        attestation = path.parent / "SHA256SUMS"
        result["attestation"] = {
            "format": "SHA256SUMS",
            "path": attestation.relative_to(root).as_posix(),
            "sha256": sha256(attestation),
        }
    elif role == "DERIVED_DIAGNOSTIC_PATCH":
        attestation = path.parent / "PATCH_RECEIPT.json"
        result["attestation"] = {
            "format": "LOCAL_DERIVATION_RECEIPT",
            "path": attestation.relative_to(root).as_posix(),
            "sha256": sha256(attestation),
        }
    return result


def seal_case(root: Path, case_id: str, source_commit: str, original: Path,
              candidate: Path, operational: Path, shadow: Path, hour: int) -> dict:
    (original.parent / "SHA256SUMS").write_text(
        f"{sha256(original)}  {original.name}\n", encoding="utf-8"
    )
    receipt = {
        "schema": 1,
        "receipt_type": "LOCAL_DERIVATION_RECEIPT",
        "source_commit": source_commit,
        "configuration": SHADOW_CONFIGURATION,
        "patch_operation": "ABSOLUTE_REPLACE_DIAGNOSTIC_ONLY",
        "full_product_candidate": False,
        "mass_basis_resolved": False,
        "algorithm_comparison_ready": False,
        "parent_product_sha256": sha256(original),
        "shadow_diagnostic_sha256": sha256(shadow),
        "product": {
            "path": candidate.name,
            "bytes": candidate.stat().st_size,
            "sha256": sha256(candidate),
        },
    }
    (candidate.parent / "PATCH_RECEIPT.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    valid_time = f"2026-08-16T{hour:02d}:00:00Z"
    return {
        "pair_id": f"laps-{case_id}",
        "product_kind": "LAPS",
        "format": "WPS_INTERMEDIATE",
        "valid_time": valid_time,
        "original": artifact(
            root, "REAL_OPERATIONAL_ORIGINAL", "ARCHIVED_OPERATIONAL_KLAPS", original
        ),
        "candidate": artifact(
            root, "DERIVED_DIAGNOSTIC_PATCH",
            "OPERATIONAL_COPY_WITH_CANONICAL_HYDROMETEOR_PATCH", candidate
        ),
        "operational_unchanged": artifact(
            root, "OPERATIONAL_UNCHANGED", "LIVE_OPERATIONAL_KLAPS_UNCHANGED",
            operational,
        ),
        "plot_fields": plot_field_specs(PLOT_LEVEL_PA),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--live-root", required=True, type=Path)
    parser.add_argument("--shadow-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--scope", choices=(FULL_SCOPE, P1_OPERATIONAL_SCOPE),
        default=FULL_SCOPE,
        help=(
            "comparison scope: full (12/13/14/15 UTC) or "
            "p1-operational (13/14/15 UTC)"
        ),
    )
    parser.add_argument("--hours", nargs="+", type=int, default=None)
    parser.add_argument(
        "--allow-partial-diagnostic",
        action="store_true",
        help="allow an explicitly non-authoritative subset of the selected scope",
    )
    args = parser.parse_args()

    try:
        args.scope = normalize_scope(args.scope)
        if args.hours is None:
            args.hours = list(scope_contract(args.scope)["hours"])
        requested_hours = validate_hours(
            args.hours, allow_partial=args.allow_partial_diagnostic,
            scope=args.scope,
        )
        args.original_root = strict_root_path(args.original_root, "original-root")
        args.live_root = strict_root_path(args.live_root, "live-root")
        args.shadow_root = strict_root_path(
            args.shadow_root, "shadow-root", allow_final_symlink=True
        )
        args.output = strict_root_path(
            args.output, "output", must_exist=False
        )
        validate_scope_inventory(
            args.original_root, args.live_root, args.scope
        )
    except ValueError as exc:
        print(f"invalid comparison request: {exc}", file=sys.stderr)
        return 2

    if args.output.exists():
        print(f"output already exists: {args.output}", file=sys.stderr)
        return 2
    if len(args.source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in args.source_commit
    ):
        print("--source-commit must be a 40-character lowercase SHA", file=sys.stderr)
        return 2
    project = Path(__file__).resolve().parents[1]
    tool_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=project, text=True
    ).strip()
    if tool_commit != args.source_commit:
        print("comparison tool HEAD differs from --source-commit", file=sys.stderr)
        return 2
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=project, text=True
    ).strip():
        print("comparison tool source tree must be clean", file=sys.stderr)
        return 2
    shadow_root, shadow_products, shadow_manifest_sha = shadow_generation(
        args.shadow_root, args.source_commit
    )
    shadow_publication_root = args.shadow_root.parent
    args.shadow_root = shadow_root
    if paths_overlap(args.original_root, args.live_root):
        raise ValueError("archived and live operational roots must not overlap")
    args.output.mkdir(parents=True)

    scope = scope_contract(args.scope)
    report = {
        "schema_version": 1,
        "comparison_scope": scope["scope"],
        "scope_hours": list(scope["hours"]),
        "excluded_utc_hours": list(scope["excluded_utc_hours"]),
        "excluded_utc_status": scope["excluded_utc_status"],
        "excluded_utc_reason": scope["excluded_utc_reason"],
        "excluded_utc_provenance": scope["excluded_utc_provenance"],
        "scope_exclusions": scope_exclusions(args.scope),
        "comparison_authority": "DIAGNOSTIC_FIELD_LEVEL_ONLY",
        "algorithm_comparison_status": "NOT_RUN_FULL_END_TO_END",
        "full_product_candidate": False,
        "comparison_effect_isolated": False,
        "mass_basis_resolved": False,
        "dynamic_balance_authorized": False,
        "operational_original_modified": False,
        "input_snapshot_contract": (
            "LOCAL_CONTENT_SNAPSHOT_NO_AUTHENTICATION"
        ),
        "candidate_construction": (
            "diagnostic operational WPS copy with QC/QI/QR/QS/QG absolute values "
            "replaced only where the real-data Cloud-BAL column stage changed them"
        ),
        "mass_basis_caveat": (
            "operational WPS declares kg kg-1; Cloud-BAL declares kg kg-1 dryair; "
            "the legacy producer does not fully prove an identical denominator"
        ),
        "source_commit": args.source_commit,
        "comparison_tool_source_commit": tool_commit,
        "comparison_tool_sha256": sha256(Path(__file__).resolve()),
        "shadow_generation_manifest_sha256": shadow_manifest_sha,
        "cases": [],
    }
    all_rows: list[dict] = []
    contract_pairs: list[dict] = []

    for hour in requested_hours:
        paths = case_paths(args, hour)
        case_report = {"case_id": paths.case_id}
        missing = [
            label
            for label, path in (
                ("operational_original", paths.original),
                ("live_operational_original", paths.live_original),
                ("shadow_diagnostic", paths.shadow),
            )
            if not path.is_file()
        ]
        if missing:
            case_report.update(status="NOT_AVAILABLE", missing=missing)
            report["cases"].append(case_report)
            continue

        case_root = args.output / paths.case_id
        original_dir = case_root / "original"
        candidate_dir = case_root / "candidate"
        operational_dir = case_root / "operational_unchanged"
        figures_dir = case_root / "figures"
        shadow_dir = case_root / "shadow_input"
        receipt_dir = case_root / "source_receipt"
        original_dir.mkdir(parents=True)
        candidate_dir.mkdir()
        operational_dir.mkdir()
        figures_dir.mkdir()
        shadow_dir.mkdir()
        receipt_dir.mkdir()
        isolated_original = original_dir / paths.original.name
        candidate = candidate_dir / paths.original.name
        operational = operational_dir / paths.original.name
        shadow_input = shadow_dir / paths.shadow.name
        original_snapshot = snapshot_input(paths.original, isolated_original)
        live_snapshot = snapshot_input(paths.live_original, operational)
        shadow_snapshot = snapshot_input(paths.shadow, shadow_input)
        require_matching_inputs(original_snapshot, live_snapshot, paths.case_id)
        receipt_path, receipt_sha = archive_receipt(
            paths.original, original_snapshot.sha256
        )
        receipt_snapshot = snapshot_input(
            receipt_path, receipt_dir / "SHA256SUMS"
        )
        if receipt_snapshot.sha256 != receipt_sha:
            raise ValueError("archive receipt changed while it was snapshotted")

        shadow_entry = shadow_products.get(paths.shadow.name)
        if (not isinstance(shadow_entry, dict)
                or shadow_entry.get("sha256") != shadow_snapshot.sha256
                or shadow_entry.get("bytes") != shadow_snapshot.source_size):
            raise ValueError(f"SHADOW diagnostic is not generation-bound: {paths.case_id}")
        if verify_current_generation(shadow_publication_root) != args.shadow_root:
            raise ValueError("SHADOW generation changed while input was snapshotted")
        expected_epoch = calendar.timegm((2026, 8, 16, hour, 0, 0))
        with Dataset(shadow_input) as shadow_dataset:
            if int(getattr(shadow_dataset, "valid_time_epoch", -1)) != expected_epoch:
                raise ValueError(f"SHADOW valid time differs from case: {paths.case_id}")

        original_sha = original_snapshot.sha256
        shadow_sha = shadow_snapshot.sha256
        build = build_candidate(isolated_original, shadow_input, candidate)
        rows, comparison = compare_products(isolated_original, candidate)
        level = PLOT_LEVEL_PA
        if build["modified_by_level"]:
            case_status = "COMPLETED_DIAGNOSTIC"
        else:
            with Dataset(shadow_input) as dataset:
                pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
            if not np.any(np.rint(pressure).astype(np.int64) == PLOT_LEVEL_PA):
                raise ValueError(f"fixed diagnostic level is absent: {PLOT_LEVEL_PA}")
            case_status = "COMPLETED_NO_CHANGE"
        figure = figures_dir / f"{paths.case_id}_{level // 100}hPa.png"
        plot_case(paths.case_id, isolated_original, candidate, shadow_input, level, figure)
        contract_pairs.append(seal_case(
            args.output, paths.case_id, args.source_commit, isolated_original,
            candidate, operational, shadow_input, hour,
        ))

        for row in rows:
            row["case_id"] = paths.case_id
            all_rows.append(row)
        case_report.update(
            status=case_status,
            operational_original=str(paths.original.resolve()),
            isolated_original=str(isolated_original.resolve()),
            shadow_diagnostic=str(paths.shadow.absolute()),
            shadow_diagnostic_sha256=shadow_sha,
            shadow_snapshot=str(shadow_input.resolve()),
            candidate=str(candidate.resolve()),
            operational_unchanged=str(operational.resolve()),
            figure=str(figure.resolve()),
            operational_sha256=original_sha,
            operational_original_source_identity={
                "device": original_snapshot.source_device,
                "inode": original_snapshot.source_inode,
                "bytes": original_snapshot.source_size,
            },
            live_operational_source_identity={
                "device": live_snapshot.source_device,
                "inode": live_snapshot.source_inode,
                "bytes": live_snapshot.source_size,
            },
            shadow_source_identity={
                "device": shadow_snapshot.source_device,
                "inode": shadow_snapshot.source_inode,
                "bytes": shadow_snapshot.source_size,
            },
            source_archive_receipt=str(receipt_path.resolve()),
            source_archive_receipt_sha256=receipt_sha,
            source_archive_receipt_snapshot=str(receipt_snapshot.path.resolve()),
            isolated_original_sha256=sha256(isolated_original),
            candidate_sha256=sha256(candidate),
            selected_level_pa=level,
            **build,
            **comparison,
        )
        report["cases"].append(case_report)

    complete_statuses = {"COMPLETED_DIAGNOSTIC", "COMPLETED_NO_CHANGE"}
    requested_cases_complete = all(
        case["status"] in complete_statuses for case in report["cases"]
    )

    with (args.output / "field_statistics.tsv").open("w", newline="") as stream:
        columns = [
            "case_id", "field", "level_pa", "valid_time", "valid_cells",
            "changed_cells", "bias", "rms_delta", "max_abs_delta",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)
    contract_manifest = args.output / "comparison-manifest.json"
    comparison_id = f"operational-shadow-{args.scope}-{args.source_commit[:12]}"
    contract_manifest.write_text(json.dumps({
        "schema_version": 1,
        "comparison_id": comparison_id,
        "pairs": contract_pairs,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scope_manifest = args.output / "scope-manifest.json"
    scope_manifest.write_text(json.dumps({
        "schema_version": 1,
        "comparison_id": comparison_id,
        "comparison_scope": scope["scope"],
        "scope_hours": list(scope["hours"]),
        "scope_exclusions": scope_exclusions(args.scope),
        "source_commit": args.source_commit,
        "comparison_tool_sha256": report["comparison_tool_sha256"],
        "shadow_generation_manifest_sha256": shadow_manifest_sha,
        "comparison_manifest_sha256": sha256(contract_manifest),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if contract_pairs:
        readiness = prepare(
            contract_manifest, args.output, args.output / "contract_evidence"
        )
        if readiness["status"] != DIAGNOSTIC_PATCH_VALID:
            raise ValueError(
                "operational comparison contract failed: "
                + "; ".join(readiness["failures"])
            )
    else:
        readiness = {
            "status": "NOT_RUN_NO_AVAILABLE_PAIRS",
            "algorithm_comparison_status": "NOT_RUN",
        }
    status = status_values(
        requested_hours, requested_cases_complete,
        available_pairs=bool(contract_pairs), scope=args.scope,
    )
    report["requested_case_set_complete"] = requested_cases_complete
    report["diagnostic_execution"] = {
        "status": status["diagnostic_execution"],
        "comparison_scope": status["comparison_scope"],
        "scope_hours": status["scope_hours"],
        "excluded_utc_hours": status["excluded_utc_hours"],
        "excluded_utc_status": status["excluded_utc_status"],
        "excluded_utc_reason": status["excluded_utc_reason"],
        "excluded_utc_provenance": status["excluded_utc_provenance"],
        "requested_hours": status["requested_hours"],
        "authoritative_hours": status["authoritative_hours"],
        "authoritative_complete": status["authoritative_complete"],
        "requested_case_set_complete": status["requested_case_set_complete"],
    }
    report["diagnostic_execution_status"] = status["diagnostic_execution"]
    report["comparison_readiness"] = status["comparison_readiness"]
    report["comparison_status"] = status["comparison_status"]
    report["available_artifact_validity"] = status["available_artifact_validity"]
    report["diagnostic_exit"] = status["diagnostic_exit"]
    report["algorithm_comparison_ready"] = status["algorithm_comparison_ready"]
    report["promotion_eligible"] = status["promotion_eligible"]
    report["mass_basis_gate"] = status["mass_basis_gate"]
    report["structural_comparison_readiness"] = {
        "status": status["comparison_readiness"],
        "available_pairs_status": readiness["status"],
        "available_artifact_validity": status["available_artifact_validity"],
        "algorithm_comparison_status": readiness["algorithm_comparison_status"],
        "readiness_path": (
            str((args.output / "contract_evidence" / "READINESS.json").resolve())
            if contract_pairs else None
        ),
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (args.output / "STATUS.txt").write_text(
        render_status(status)
    )
    print(args.output.resolve())
    return 0 if status["authoritative_complete"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
