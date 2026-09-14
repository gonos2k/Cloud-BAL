#!/usr/bin/env python3
"""Small executable gates for an isolated original-producer E01 run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


REPLAY_PATH = Path(__file__).with_name("original_upstream_replay.py")
REPLAY_SPEC = importlib.util.spec_from_file_location("e01_replay", REPLAY_PATH)
assert REPLAY_SPEC is not None and REPLAY_SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(REPLAY_SPEC)
REPLAY_SPEC.loader.exec_module(REPLAY)

CONTRACT = "original_klaps_e01_completion_gate_v1"
STAGE_ORDER = (
    "wind_openmp",
    "surface",
    "vrt_complete_gate",
    "temperature",
    "cloud",
    "humidity",
    "derived",
)
NEGATIVE_EXPECTATIONS: Mapping[str, tuple[str, tuple[tuple[str, int], ...]]] = {
    "vrt-race": ("VRT hash-to-reopen race rejected", ()),
    "missing-producer": ("temperature producer SHA-256 mismatch", ()),
    "missing-producer-path": (
        "temperature producer is not a regular non-hardlinked file",
        (),
    ),
    "stale-com": ("generated namespace is not fresh", ()),
    "different-cycle": ("does not match background reftime", ()),
    "fail-stage": (
        "stage temperature exited 1",
        (
            ("wind_openmp", 0),
            ("surface", 0),
            ("vrt_complete_gate", 0),
            ("temperature", 1),
        ),
    ),
}
GENERATED_PREFIXES = (
    "lapsprd/lw3/",
    "lapsprd/lsx/",
    "lapsprd/lt1/",
    "lapsprd/lq3/",
    "lapsprd/lco/",
    "lapsprd/lpbl/",
    "lapsprd/pbl/",
    "lapsprd/lps/",
    "lapsprd/lc3/",
    "lapsprd/lcb/",
    "lapsprd/lcv/",
    "lapsprd/lh3/",
    "lapsprd/lh4/",
    "lapsprd/lcp/",
    "lapsprd/lct/",
    "lapsprd/lfr/",
    "lapsprd/lhe/",
    "lapsprd/lil/",
    "lapsprd/liw/",
    "lapsprd/lmd/",
    "lapsprd/lmr/",
    "lapsprd/lmt/",
    "lapsprd/lrp/",
    "lapsprd/lst/",
    "lapsprd/lty/",
    "lapsprd/lwc/",
)


class GateError(RuntimeError):
    """The isolated E01 contract cannot be safely continued."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as error:
        raise GateError(f"cannot read {path}: {error}") from error


def inventory(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink() or path.stat().st_nlink != 1:
            raise GateError(f"inventory contains unsafe file: {path}")
        result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def _epoch(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GateError(f"invalid UTC timestamp: {value}") from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise GateError(f"timestamp is not UTC: {value}")
    if parsed.second or parsed.microsecond:
        raise GateError(f"timestamp is not an exact minute: {value}")
    return parsed.timestamp()


def _cycle_token(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y%m%dT%H%M%SZ")


def validate_case_identity(row: Mapping[str, str], source_cycle_id: str) -> None:
    valid_time = str(row["valid_time_utc"])
    background = str(row["background_reftime_utc"])
    _epoch(valid_time)
    _epoch(background)
    parsed = datetime.fromisoformat(valid_time.replace("Z", "+00:00"))
    expected_case = parsed.strftime("%Y%m%dT%H%M%SZ")
    expected_stamp = parsed.strftime("%y%j%H%M")
    if row.get("case_id") != expected_case:
        raise GateError("case_id does not match valid_time_utc")
    if row.get("laps_stamp") != expected_stamp:
        raise GateError("laps_stamp does not match valid_time_utc")
    expected_cycle = _cycle_token(background)
    if source_cycle_id != expected_cycle:
        raise GateError(
            f"source cycle {source_cycle_id!r} does not match background "
            f"reftime {background!r}"
        )


def _regular_path(root: Path, relative: str, role: str) -> Path:
    root = root.resolve(strict=True)
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise GateError(f"{role} source cannot be resolved: {relative}") from error
    if not resolved.is_relative_to(root):
        raise GateError(f"{role} source escapes runroot: {relative}")
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise GateError(f"{role} source is not a regular non-hardlinked file")
    return path


def bind_input_bytes(
    root: Path, relative: str, expected_hash: str, role: str
) -> bytes:
    path = _regular_path(root, relative, role)
    payload = path.read_bytes()
    actual_hash = sha256_bytes(payload)
    if actual_hash != expected_hash:
        raise GateError(
            f"{role} SHA-256 mismatch: {actual_hash} != {expected_hash}"
        )
    return payload


def bind_producer_executable(
    path: Path, expected_hash: str, stage: str
) -> str:
    """Check the exact executable bytes before the corresponding launch."""
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise GateError(f"{stage} producer is not a regular non-hardlinked file")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise GateError(
            f"{stage} producer SHA-256 mismatch: {actual_hash} != {expected_hash}"
        )
    return actual_hash


def _netcdf_times(payload: bytes, role: str) -> tuple[float, float]:
    try:
        import netCDF4
        import numpy as np

        with netCDF4.Dataset("inmemory-e01-input.nc", "r", memory=payload) as dataset:
            values: list[float] = []
            for name in ("valtime", "reftime"):
                variable = dataset.variables.get(name)
                if variable is None or variable.dimensions != ("record",):
                    raise GateError(f"{role} lacks exact {name} coordinate")
                if str(getattr(variable, "units", "")).strip() != REPLAY.UTC_EPOCH_UNITS:
                    raise GateError(f"{role} {name} units are not UTC epoch")
                array = np.ma.asarray(variable[:]).reshape(-1)
                if array.size != 1 or np.ma.is_masked(array[0]):
                    raise GateError(f"{role} {name} is missing or masked")
                value = float(array[0])
                if not np.isfinite(value):
                    raise GateError(f"{role} {name} is not finite")
                values.append(value)
            return values[0], values[1]
    except GateError:
        raise
    except Exception as error:
        raise GateError(f"{role} NetCDF time read failed: {error}") from error


def bind_case_inputs(
    root: Path,
    row: Mapping[str, str],
    source_cycle_id: str,
    lgt_hash: str,
    path_overrides: Mapping[str, str] | None = None,
    lgt_relative: str | None = None,
) -> dict[str, object]:
    """Hash-bind case inputs and validate their declared source clocks."""
    validate_case_identity(row, source_cycle_id)
    valid_epoch = _epoch(str(row["valid_time_utc"]))
    background_epoch = _epoch(str(row["background_reftime_utc"]))
    path_overrides = path_overrides or {}
    hashes: dict[str, str] = {}
    bound: dict[str, bytes] = {}
    for role in ("fua", "fsf", "lw3", "vrz", "vrt"):
        relative = str(path_overrides.get(role, row[f"{role}_path"]))
        expected_hash = str(row[f"{role}_sha256"])
        payload = bind_input_bytes(root, relative, expected_hash, role)
        hashes[role] = expected_hash
        bound[role] = payload
    lgt_relative = lgt_relative or (
        f"ANAL/NE57/DAOU/00/lapsprd/lgt/{row['laps_stamp']}.lgt"
    )
    bind_input_bytes(root, lgt_relative, lgt_hash, "lgt")
    hashes["lgt"] = lgt_hash

    for role in ("fua", "fsf"):
        actual_valid, actual_reftime = _netcdf_times(bound[role], role)
        if actual_valid != valid_epoch or actual_reftime != background_epoch:
            raise GateError(
                f"{role} clock mismatch: got ({actual_valid}, {actual_reftime}), "
                f"expected ({valid_epoch}, {background_epoch})"
            )
    for role in ("vrz", "vrt"):
        actual_valid, actual_reftime = _netcdf_times(bound[role], role)
        if actual_valid != valid_epoch or actual_reftime != valid_epoch:
            raise GateError(
                f"{role} clock mismatch: got ({actual_valid}, {actual_reftime}), "
                f"expected ({valid_epoch}, {valid_epoch})"
            )
    vrt_status, vrt_findings = REPLAY.vrt_complete(
        bound["vrt"], str(row["valid_time_utc"])
    )
    if vrt_status != "PASS":
        raise GateError(f"VRT completion blocked: {','.join(vrt_findings)}")
    return {
        "contract": CONTRACT,
        "case_id": row["case_id"],
        "valid_time_utc": row["valid_time_utc"],
        "background_reftime_utc": row["background_reftime_utc"],
        "source_cycle_id": source_cycle_id,
        "input_hashes": hashes,
        "vrt_sha256": sha256_bytes(bound["vrt"]),
        "vrt_status": vrt_status,
        "vrt_findings": vrt_findings,
    }


def assert_fresh_generated_namespace(
    initial_inventory: Mapping[str, str],
) -> None:
    stale = [
        path
        for path in initial_inventory
        if any(path.startswith(prefix) for prefix in GENERATED_PREFIXES)
    ]
    if stale:
        raise GateError(
            "generated namespace is not fresh: " + ",".join(sorted(stale))
        )


def assert_initial_unchanged(
    root: Path, initial_inventory: Mapping[str, str]
) -> None:
    current = inventory(root)
    missing = sorted(set(initial_inventory) - set(current))
    changed = sorted(
        path
        for path in set(initial_inventory) & set(current)
        if initial_inventory[path] != current[path]
    )
    if missing or changed:
        raise GateError(
            f"initial input inventory changed: missing={missing}, changed={changed}"
        )


def assert_stage_success(
    stage: str,
    exit_code: int,
    previous_stage: str | None,
    expected_previous: str | None | object = None,
) -> None:
    if stage not in STAGE_ORDER:
        raise GateError(f"unknown E01 stage: {stage}")
    stage_index = STAGE_ORDER.index(stage)
    required_previous = None if stage_index == 0 else STAGE_ORDER[stage_index - 1]
    if expected_previous is not None and expected_previous != required_previous:
        raise GateError(
            f"caller supplied predecessor {expected_previous!r} for {stage}; "
            f"required={required_previous!r}"
        )
    if previous_stage != required_previous:
        raise GateError(
            f"stage order violation: previous={previous_stage!r}, "
            f"expected={required_previous!r}"
        )
    if exit_code != 0:
        raise GateError(f"stage {stage} exited {exit_code}")


def _stage_signature(
    stages: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, int], ...]:
    try:
        return tuple((str(item["stage"]), int(item["exit"])) for item in stages)
    except (KeyError, TypeError, ValueError) as error:
        raise GateError(f"negative stage record is malformed: {error}") from error


def assert_fault_specific_rejection(
    fault: str,
    findings: Sequence[str],
    stages: Sequence[Mapping[str, object]],
) -> None:
    """Require a named negative to fail for its declared cause and stage prefix."""
    expectation = NEGATIVE_EXPECTATIONS.get(fault)
    if expectation is None:
        raise GateError(f"unknown negative fault: {fault}")
    marker, expected_stages = expectation
    if not any(marker in finding for finding in findings):
        raise GateError(
            f"{fault} negative lacks its causal finding {marker!r}: {list(findings)!r}"
        )
    actual_stages = _stage_signature(stages)
    if actual_stages != expected_stages:
        raise GateError(
            f"{fault} negative reached unexpected stages: "
            f"actual={actual_stages!r}, expected={expected_stages!r}"
        )


def write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
