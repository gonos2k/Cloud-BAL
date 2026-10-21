#!/usr/bin/env python3
"""Audit receipt-closed PR94 compact longruns with frozen PR93 readers."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr87_completed_state_audit as completed_audit  # noqa: E402
import pr85_joint_stage_trace as stage_trace  # noqa: E402
from pr87_native_history import _finite  # noqa: E402

FROZEN_AUDITOR_PATH = (
    ROOT / "docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py"
)
FROZEN_AUDITOR_SHA256 = "8f9affa02e6d843d623911cfd6a9447a9ddb4ba0713cf927e2d5de2bcfb2e126"
SOURCE_BUILD_AUDIT_PATH = ROOT / "docs/evidence/pr94_longrun_diagnostics_20261021/source_build_audit.json"
SOURCE_BUILD_AUDIT_SHA256 = "a41aa4b1ed703803272649198483b7787aae5b1962d759c68f5644e3f54adf06"
BASELINE_ARM_DURATION = 600
_spec = importlib.util.spec_from_file_location("pr93_closed_run_audit", FROZEN_AUDITOR_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load frozen PR93 auditor: {FROZEN_AUDITOR_PATH}")
if hashlib.sha256(FROZEN_AUDITOR_PATH.read_bytes()).hexdigest() != FROZEN_AUDITOR_SHA256:
    raise RuntimeError("frozen PR93 auditor hash differs from the reviewed pin")
frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frozen)

TRACE_NAME = frozen.TRACE_NAME
FULL_STEPS = 30
DETAIL_STEPS = (60, 90, 180)
FIELDS = stage_trace.STATE_FIELDS
EXPECTED_SEQUENCE = tuple(zip(completed_audit.STATE_SEQUENCE, (0, 1, 2, 3, 0, 0), strict=True))
HISTORY_FIELDS = ("T", "P", "PB", "PH", "PHB", "U", "V", "W", "MU", "MUB")
HISTORY_START = dt.datetime(2026, 8, 16, 13, 0, 0)
HISTORY_TIMES = tuple(
    (HISTORY_START + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d_%H:%M:%S")
    for seconds in range(0, 601, 60)
)


class LongrunAuditError(RuntimeError):
    """The closed trace does not satisfy the selected compact profile."""


def _required_state_steps(completed: list[int]) -> set[int]:
    last_step = completed[-1] if completed else 0
    return set(range(1, min(last_step, FULL_STEPS) + 1)) | {
        step for step in DETAIL_STEPS if step <= last_step
    }


def validate_compact_state_profile(records: list[dict], completed: list[int]) -> dict:
    """Require six states through step 30/snapshots and one POST at every step."""
    if not completed:
        return {"status": "INCOMPLETE", "completed_steps": 0,
                "retained_state_records": 0, "fully_detailed_steps": [],
                "post_kdm6_records": 0, "post_only_steps": [],
                "scope": "No completed POST_KDM6 prefix is available to profile."}
    if completed != list(range(1, completed[-1] + 1)):
        raise LongrunAuditError("completed steps are not a contiguous prefix")
    per_step: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for row in records:
        step = row["timestep"]
        if step not in completed:
            raise LongrunAuditError(f"state record is outside completed prefix: step {step}")
        per_step[step].append((row["stage"], row["rkstep"]))
    detailed_steps = _required_state_steps(completed)
    post_counts = Counter(
        step for step, stages in per_step.items()
        for label, _rk in stages if label == "POST_KDM6"
    )
    missing_post = [step for step in completed if post_counts[step] != 1]
    if missing_post:
        raise LongrunAuditError(f"expected exactly one POST_KDM6 per completed step: {missing_post[:8]}")
    extra_steps = sorted(set(per_step) - set(completed))
    missing_steps = sorted(detailed_steps - set(per_step))
    if extra_steps or missing_steps:
        raise LongrunAuditError(f"retained state steps differ from compact profile: missing={missing_steps}, extra={extra_steps}")
    for step in completed:
        expected = (list(EXPECTED_SEQUENCE) if step in detailed_steps
                    else [("POST_KDM6", 0)])
        if per_step[step] != expected:
            raise LongrunAuditError(
                f"step {step} state cadence/RK sequence mismatch: expected {expected}, got {per_step[step]}"
            )
    return {
        "status": "PASS",
        "completed_steps": len(completed),
        "retained_state_records": sum(map(len, per_step.values())),
        "fully_detailed_steps": sorted(detailed_steps.intersection(
            set(range(1, FULL_STEPS + 1)) | set(DETAIL_STEPS)
        )),
        "post_kdm6_records": len(completed),
        "post_only_steps": sorted(set(completed) - detailed_steps),
        "scope": "The compact trace retains all six states through step 30, all six at steps 60/90/180 when completed, and POST_KDM6 once at every other completed timestep.",
    }


def _assert_state_record_equal(baseline: dict, compact: dict, step: int) -> None:
    metadata = ("kind", "timestep", "rkstep", "stage", "bounds", "density_contract_status")
    for key in metadata:
        if baseline[key] != compact[key]:
            raise LongrunAuditError(f"600-second prefix metadata differs at step {step}: {key}")
    for name in FIELDS:
        base_values = baseline["fields"][name]
        compact_values = compact["fields"][name]
        if base_values.dtype != compact_values.dtype or base_values.shape != compact_values.shape or \
                base_values.tobytes(order="C") != compact_values.tobytes(order="C"):
            raise LongrunAuditError(f"600-second prefix array differs at step {step}: {name}")


def _state_records(records):
    for row in records:
        if row["kind"] == 1:
            yield row


def _profile_metadata(record: dict) -> dict:
    """Retain only cadence fields; state arrays are large and used immediately."""
    return {key: record[key] for key in ("timestep", "stage", "rkstep")}


def _compact_completed_prefix(receipt: dict, arm: str) -> list[int]:
    snapshots = receipt.get("snapshots", {})
    completed = snapshots.get("completed_post_kdm6_timesteps")
    if completed == []:
        if snapshots.get("duplicate_post_kdm6_timesteps") or receipt.get("final_completed_step") not in (None, 0):
            raise LongrunAuditError(f"{arm}: empty completed prefix conflicts with receipt metadata")
        return []
    return frozen.derive_prefix(receipt, arm)


def _verify_executable_binding(receipt: dict, preflight: dict, expected_sha256: str,
                               label: str) -> None:
    candidate = preflight.get("candidate_build")
    if not isinstance(candidate, dict):
        raise LongrunAuditError(f"{label}: candidate build binding missing")
    observed = receipt.get("executed_executable_sha256")
    if (observed != expected_sha256
            or receipt.get("expected_executed_executable_sha256") != expected_sha256
            or candidate.get("executable_sha256") != expected_sha256
            or receipt.get("candidate_build") != candidate):
        raise LongrunAuditError(f"{label}: executed executable differs from pinned build")
    staged_executable = preflight.get("output")
    if not staged_executable:
        raise LongrunAuditError(f"{label}: preflight output root missing")
    staged_path = Path(staged_executable) / "run/wrf.exe"
    if not staged_path.is_file():
        raise LongrunAuditError(f"{label}: staged executable is missing")
    if frozen.sha256(staged_path) != expected_sha256:
        raise LongrunAuditError(f"{label}: staged executable hash differs from pinned build")


def _verify_runtime_bindings(root: Path, baseline_root: Path, receipt: dict,
                             baseline_receipt: dict, arm: str,
                             duration_seconds: int) -> dict:
    try:
        source_build_audit_bytes = SOURCE_BUILD_AUDIT_PATH.read_bytes()
    except OSError as error:
        raise LongrunAuditError(f"source/build audit missing: {error}") from error
    if hashlib.sha256(source_build_audit_bytes).hexdigest() != SOURCE_BUILD_AUDIT_SHA256:
        raise LongrunAuditError("source/build audit hash differs from the reviewed pin")
    source_build_audit = json.loads(source_build_audit_bytes)
    if source_build_audit.get("status") != "PASS_SOURCE_BUILD_NOT_RUNTIME":
        raise LongrunAuditError("source/build audit is not a passing source/build receipt")
    try:
        preflight = json.loads((root / "preflight.json").read_text(encoding="utf-8"))
        baseline_preflight = json.loads((baseline_root / "preflight.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LongrunAuditError(f"run preflight is unavailable or invalid: {error}") from error
    if (preflight.get("arm") != arm or baseline_preflight.get("arm") != arm
            or preflight.get("duration_seconds") != duration_seconds
            or baseline_preflight.get("duration_seconds") != BASELINE_ARM_DURATION):
        raise LongrunAuditError("run preflight arm or duration does not match audit request")
    baseline_build = source_build_audit["baseline_build"]
    compact_build = source_build_audit["diagnostic_build"]
    _verify_executable_binding(baseline_receipt, baseline_preflight,
                               baseline_build["executable_sha256"], f"C4 {arm} baseline")
    _verify_executable_binding(receipt, preflight,
                               compact_build["executable_sha256"], f"compact {arm} run")
    for role, audit_row, preflight_row in (
        ("C4 baseline", baseline_build, baseline_preflight.get("candidate_build", {})),
        ("compact", compact_build, preflight.get("candidate_build", {})),
    ):
        if (audit_row.get("sha256") != preflight_row.get("receipt_sha256")
                or audit_row.get("path") != preflight_row.get("receipt_path")):
            raise LongrunAuditError(f"{role}: build receipt differs from pinned source/build audit")

    if preflight.get("input_hashes") != baseline_preflight.get("input_hashes"):
        raise LongrunAuditError("compact and C4 inputs differ")
    if (preflight.get("candidate_wrfinput_sha256") != baseline_preflight.get("candidate_wrfinput_sha256")
            or preflight.get("candidate_wrfbdy_sha256") != baseline_preflight.get("candidate_wrfbdy_sha256")
            or receipt.get("candidate_wrfinput_sha256") != preflight.get("candidate_wrfinput_sha256")
            or baseline_receipt.get("candidate_wrfinput_sha256") != baseline_preflight.get("candidate_wrfinput_sha256")
            or receipt.get("candidate_wrfbdy_sha256") != preflight.get("candidate_wrfbdy_sha256")
            or baseline_receipt.get("candidate_wrfbdy_sha256") != baseline_preflight.get("candidate_wrfbdy_sha256")):
        raise LongrunAuditError("compact and C4 initial input or boundary differs")
    if (preflight.get("source_namelist_sha256") != baseline_preflight.get("source_namelist_sha256")
            or preflight.get("candidate_namelist_sha256") != receipt.get("candidate_namelist_sha256")
            or baseline_preflight.get("candidate_namelist_sha256") != baseline_receipt.get("candidate_namelist_sha256")):
        raise LongrunAuditError("run namelist binding differs from its preflight")
    source_namelist = Path(preflight["runtime_dir"]) / "namelist.input"
    from pr86_time_response import edit_namelist
    if (frozen.sha256(source_namelist) != preflight["source_namelist_sha256"]
            or preflight["source_namelist_sha256"] != baseline_preflight["source_namelist_sha256"]):
        raise LongrunAuditError("source namelist changed or differs between runs")
    source_text = source_namelist.read_text(encoding="utf-8")
    expected_compact_namelist = hashlib.sha256(
        edit_namelist(source_text, duration_seconds).encode()
    ).hexdigest()
    expected_baseline_namelist = hashlib.sha256(
        edit_namelist(source_text, BASELINE_ARM_DURATION).encode()
    ).hexdigest()
    if (expected_compact_namelist != preflight["candidate_namelist_sha256"]
            or expected_baseline_namelist != baseline_preflight["candidate_namelist_sha256"]):
        raise LongrunAuditError("namelist differs beyond the runner's duration/end-time edits")
    for label, run_receipt in (("C4 baseline", baseline_receipt), ("compact", receipt)):
        if (run_receipt.get("changed_staged_inputs") or run_receipt.get("changed_original_inputs")
                or run_receipt.get("processing_errors") or run_receipt.get("candidate_build_unchanged") is False):
            raise LongrunAuditError(f"{label}: finalized receipt reports changed inputs or provenance errors")
    return {
        "status": "PASS",
        "baseline_executable_sha256": baseline_build["executable_sha256"],
        "compact_executable_sha256": compact_build["executable_sha256"],
        "input_hashes_equal": True,
        "wrfinput_sha256": preflight["candidate_wrfinput_sha256"],
        "wrfbdy_sha256": preflight["candidate_wrfbdy_sha256"],
        "source_namelist_sha256": preflight["source_namelist_sha256"],
        "namelist_scope": "Both staged namelists reproduce the existing runner's duration/end-time/history edits from the same receipt-bound source namelist.",
        "source_build_audit_sha256": SOURCE_BUILD_AUDIT_SHA256,
    }


def compare_first_600_seconds(baseline_root: Path, baseline_receipt: dict,
                              compact_root: Path, compact_receipt: dict,
                              arm: str) -> dict:
    """Compare first-30 state records while both frozen readers verify whole-file hashes."""
    baseline_row = frozen.output_row(baseline_receipt, TRACE_NAME, f"baseline {arm}")
    compact_row = frozen.output_row(compact_receipt, TRACE_NAME, f"compact {arm}")
    baseline_path = baseline_root / "run" / baseline_row["compressed_path"]
    compact_path = compact_root / "run" / compact_row["compressed_path"]
    if not baseline_path.is_file() or not compact_path.is_file():
        raise LongrunAuditError("receipt-bound stage trace is missing")
    baseline_completed = set(frozen.derive_prefix(baseline_receipt, f"baseline {arm}"))
    compact_completed = set(_compact_completed_prefix(compact_receipt, f"compact {arm}"))
    common_prefix_steps = min(FULL_STEPS, max(compact_completed, default=0))
    baseline_iter = iter(_state_records(frozen._trace_records(
        baseline_path, baseline_row, f"baseline {arm}", baseline_completed
    )))
    compact_iter = iter(_state_records(frozen._trace_records(
        compact_path, compact_row, f"compact {arm}", compact_completed
    )))

    def next_prefix_state(iterator):
        for row in iterator:
            if row["timestep"] > common_prefix_steps:
                return None
            if row["timestep"] in baseline_completed and row["fields"] is None:
                raise LongrunAuditError("prefix state was not decoded")
            yield row

    base_prefix = iter(next_prefix_state(baseline_iter))
    compact_prefix = iter(next_prefix_state(compact_iter))
    compared = 0
    prefix_differences = []
    while True:
        try:
            base = next(base_prefix)
        except StopIteration:
            base = None
        try:
            compact = next(compact_prefix)
        except StopIteration:
            compact = None
        if base is None or compact is None:
            if base is not None or compact is not None:
                prefix_differences.append("baseline and compact common-prefix record counts differ")
            break
        try:
            _assert_state_record_equal(base, compact, base["timestep"])
        except LongrunAuditError as error:
            prefix_differences.append(str(error))
        compared += 1

    # Drain both full streams. Their frozen reader verifies compressed and expanded
    # hashes only after EOF, including any records beyond the compared prefix.
    for _row in baseline_iter:
        pass
    for _row in compact_iter:
        pass
    expected = common_prefix_steps * len(EXPECTED_SEQUENCE)
    if compared != expected:
        prefix_differences.append(f"expected {expected} prefix states, compared {compared}")
    return {
        "status": ("FAIL" if prefix_differences else
                   "PASS" if common_prefix_steps == FULL_STEPS else "INCOMPLETE"),
        "compared_state_records": compared,
        "common_prefix_steps": common_prefix_steps,
        "differences": prefix_differences,
        "scope": "Exact state metadata and big-endian serialized field bytes for six common completed states per step through min(step 30, compact completed prefix). Both whole traces were streamed to EOF and checked against their receipt-bound compressed and expanded hashes.",
        "baseline": {"compressed_sha256": baseline_row["compressed_sha256"],
                     "expanded_sha256": baseline_row["sha256"]},
        "compact": {"compressed_sha256": compact_row["compressed_sha256"],
                    "expanded_sha256": compact_row["sha256"]},
    }


def _closed_history_files(root: Path, receipt: dict, label: str) -> list[tuple[Path, str]]:
    """Resolve only history files named and hashed in the closed receipt."""
    rows = []
    for key in ("generated_files", "compressed_outputs", "history_files", "history_outputs"):
        for row in receipt.get(key, []):
            if not isinstance(row, dict):
                continue
            name = row.get("path", row.get("compressed_path", ""))
            if Path(name).name.startswith("wrfout_d01_"):
                rows.append((name, row))
    unique: dict[str, str] = {}
    for name, row in rows:
        digest = row.get("sha256", row.get("compressed_sha256"))
        if not isinstance(digest, str):
            raise LongrunAuditError(f"{label}: closed history receipt lacks a hash: {name}")
        if name in unique and unique[name] != digest:
            raise LongrunAuditError(f"{label}: conflicting receipt hashes for history: {name}")
        unique[name] = digest
    if not unique:
        raise LongrunAuditError(f"{label}: closed receipt has no WRF history files")
    files = []
    for name, expected_hash in sorted(unique.items()):
        path = root / "run" / name
        if not path.is_file():
            raise LongrunAuditError(f"{label}: receipt-bound history file is unavailable: {name}")
        if frozen.sha256(path) != expected_hash:
            raise LongrunAuditError(f"{label}: history file differs from closed receipt: {name}")
        files.append((path, expected_hash))
    return files


def _history_index(paths: list[Path], label: str) -> tuple[dict[str, tuple[Path, int]], dict]:
    index: dict[str, tuple[Path, int]] = {}
    metadata = {}
    for path in paths:
        try:
            with netCDF4.Dataset(path) as dataset:
                if "Times" not in dataset.variables:
                    raise LongrunAuditError(f"{label}: history is missing Times: {path.name}")
                times = [value.rstrip("\x00 ") for value in
                         netCDF4.chartostring(dataset.variables["Times"][:]).tolist()]
                if not times or not path.name.endswith(times[0]):
                    raise LongrunAuditError(f"{label}: history filename/time mismatch: {path.name}")
                for frame, timestamp in enumerate(times):
                    if timestamp in index:
                        raise LongrunAuditError(f"{label}: duplicate history timestamp {timestamp}")
                    index[timestamp] = (path, frame)
                metadata[path.name] = {
                    name: (str(dataset.variables[name].dtype),
                           tuple(dataset.variables[name].dimensions),
                           tuple(len(dataset.dimensions[dimension])
                                 for dimension in dataset.variables[name].dimensions
                                 if dimension != "Time"),
                           str(getattr(dataset.variables[name], "units", "")),
                           str(getattr(dataset.variables[name], "stagger", "")))
                    for name in HISTORY_FIELDS if name in dataset.variables
                }
        except OSError as error:
            raise LongrunAuditError(f"{label}: cannot read history {path.name}: {error}") from error
    return index, metadata


def _history_metadata_signature(index: dict, metadata: dict, label: str) -> dict:
    if not index:
        raise LongrunAuditError(f"{label}: no history frames found")
    signature = None
    for path, _frame in index.values():
        current = metadata[path.name]
        missing = sorted(set(HISTORY_FIELDS) - set(current))
        if missing:
            raise LongrunAuditError(f"{label}: history is missing declared fields: {missing}")
        if signature is None:
            signature = current
        elif current != signature:
            raise LongrunAuditError(f"{label}: history metadata changes between files")
    return signature or {}


def _read_history_values(path: Path, frame: int, label: str) -> tuple[dict, dict]:
    values, dtypes = {}, {}
    try:
        with netCDF4.Dataset(path) as dataset:
            dataset.set_auto_mask(False)
            for name in HISTORY_FIELDS:
                variable = dataset.variables[name]
                dtypes[name] = str(variable.dtype)
                # _finite rejects nonfinite values and declared fill/missing sentinels
                # before any cross-run arithmetic or field transformation.
                values[name] = _finite(dataset, name, frame)
    except (OSError, ValueError) as error:
        raise LongrunAuditError(f"{label}: invalid history frame {path.name}[{frame}]: {error}") from error
    return values, dtypes


def compare_closed_histories(baseline_root: Path, baseline_receipt: dict,
                             compact_root: Path, compact_receipt: dict,
                             arm: str) -> dict:
    """Compare receipt-bound native fields at every common minute through 600 s."""
    base_files = _closed_history_files(baseline_root, baseline_receipt, f"baseline {arm}")
    compact_files = _closed_history_files(compact_root, compact_receipt, f"compact {arm}")
    base_index, base_meta = _history_index([path for path, _ in base_files], f"baseline {arm}")
    compact_index, compact_meta = _history_index([path for path, _ in compact_files], f"compact {arm}")
    try:
        base_signature = _history_metadata_signature(base_index, base_meta, f"baseline {arm}")
        compact_signature = _history_metadata_signature(compact_index, compact_meta, f"compact {arm}")
    except LongrunAuditError as error:
        return {"status": "FAIL", "differences": [str(error)], "compared_timestamps": [],
                "scope": "Declared native history fields only; metadata validation failed."}
    if base_signature != compact_signature:
        return {"status": "FAIL", "differences": ["history dtype, dimensions, units, or stagger metadata differ"],
                "compared_timestamps": [], "metadata": {"baseline": base_signature,
                "compact": compact_signature},
                "scope": "Declared native history fields only; dtype, dimensions, units, and stagger must match exactly."}
    missing = {"baseline": sorted(set(HISTORY_TIMES) - set(base_index)),
               "compact": sorted(set(HISTORY_TIMES) - set(compact_index))}
    timestamps = [time for time in HISTORY_TIMES if time in base_index and time in compact_index]
    differences = []
    compared = 0
    for timestamp in timestamps:
        base_path, base_frame = base_index[timestamp]
        compact_path, compact_frame = compact_index[timestamp]
        try:
            base_values, base_dtypes = _read_history_values(base_path, base_frame, f"baseline {arm}")
            compact_values, compact_dtypes = _read_history_values(compact_path, compact_frame, f"compact {arm}")
        except LongrunAuditError as error:
            differences.append(str(error))
            continue
        for name in HISTORY_FIELDS:
            if base_dtypes[name] != compact_dtypes[name]:
                differences.append(f"{timestamp} {name}: original dtype differs")
            elif base_values[name].shape != compact_values[name].shape:
                differences.append(f"{timestamp} {name}: dimensions differ")
            elif not np.array_equal(base_values[name], compact_values[name]):
                differences.append(f"{timestamp} {name}: values differ")
        compared += 1
    for path, expected_hash in base_files:
        if frozen.sha256(path) != expected_hash:
            differences.append(f"baseline {arm}: history changed while reading: {path.name}")
    for path, expected_hash in compact_files:
        if frozen.sha256(path) != expected_hash:
            differences.append(f"compact {arm}: history changed while reading: {path.name}")
    return {"status": "FAIL" if differences else "PASS" if not any(missing.values()) else "INCOMPLETE",
            "compared_timestamps": timestamps, "compared_frames": compared,
            "missing_expected_timestamps": missing, "differences": differences,
            "metadata": base_signature,
            "scope": "Exact numeric equality per frame for T, P, PB, PH, PHB, U, V, W, MU, and MUB at common 0..600 second history timestamps. Original dtype, dimension names and non-Time extents, units, and stagger are validated; no derived fields or destaggering are included."}


def audit_compact_run(root: Path, baseline_root: Path, arm: str, duration_seconds: int) -> dict:
    if arm not in ("OFF", "COUPLED"):
        raise LongrunAuditError("compact longrun audit supports OFF and COUPLED; HYDRO remains a 600-second C4 control")
    if duration_seconds not in (1800, 3600):
        raise LongrunAuditError("duration must be 1800 or 3600 seconds")
    receipt, receipt_path = frozen.closed_receipt(root, arm)
    completed = _compact_completed_prefix(receipt, arm)
    baseline_receipt, baseline_receipt_path = frozen.closed_receipt(baseline_root, arm)
    baseline_completed = frozen.derive_prefix(baseline_receipt, f"baseline {arm}")
    if baseline_completed != list(range(1, 31)):
        raise LongrunAuditError("C4 baseline must be the closed 600-second timestep prefix")
    runtime_binding = _verify_runtime_bindings(root, baseline_root, receipt,
                                               baseline_receipt, arm, duration_seconds)
    if receipt.get("duration_seconds") not in (None, duration_seconds):
        raise LongrunAuditError("receipt duration differs from requested duration")

    trace_row = frozen.output_row(receipt, TRACE_NAME, arm)
    trace_path = root / "run" / trace_row["compressed_path"]
    if not trace_path.is_file():
        raise LongrunAuditError("receipt-bound compact trace is missing")
    policy = stage_trace._load_policy()
    state_records = []
    state_record_count = 0
    generic_failures, exact_failures, active_failures = [], [], []
    generic_checked, exact_checked, active_checked = 0, 0, 0
    for record in frozen._trace_records(trace_path, trace_row, arm, set(completed)):
        if record["kind"] != 1:
            continue
        state_record_count += 1
        if record["timestep"] not in completed:
            continue
        if record["fields"] is None:
            raise LongrunAuditError(f"completed state was not decoded: {record['timestep']} {record['stage']}")
        if record["density_contract_status"] != "AUTHORITATIVE_DRY_FROM_AL_ALB":
            raise LongrunAuditError("compact audit requires authoritative PR85QND2 density records")
        state_records.append(_profile_metadata(record))

        generic_checked += 1
        generic = completed_audit._stage_violations(record, policy)
        if any(generic["violations"].values()):
            generic_failures.append({"timestep": record["timestep"], "stage": record["stage"],
                                     "rkstep": record["rkstep"],
                                     "violations": generic["violations"]})

        active_checked += 1
        active = frozen.ice_policy_split(record["fields"], policy)
        if active["policy_status"] == "FAIL":
            active_failures.append({"timestep": record["timestep"], "stage": record["stage"],
                                    "rkstep": record["rkstep"], "result": active})

        if (record["stage"], record["rkstep"]) in frozen.ENDPOINT_STAGES:
            exact_checked += 1
            strict = completed_audit._strict_source_violations(
                completed_audit._strict_source_checks(record["fields"])
            )
            if strict:
                exact_failures.append({"timestep": record["timestep"], "stage": record["stage"],
                                       "rkstep": record["rkstep"], "violations": strict})

    profile_rows = [record for record in state_records]
    try:
        profile = validate_compact_state_profile(profile_rows, completed)
    except LongrunAuditError as error:
        profile = {"status": "FAIL", "error": str(error),
                   "completed_steps": len(completed),
                   "retained_state_records": len(profile_rows)}
    prefix = compare_first_600_seconds(baseline_root, baseline_receipt, root, receipt, arm)
    history = compare_closed_histories(baseline_root, baseline_receipt, root, receipt, arm)
    expected_steps = duration_seconds // 20
    return {
        "schema": "pr94_compact_longrun_audit_v1",
        "arm": arm,
        "requested_duration_seconds": duration_seconds,
        "runtime": {"status": receipt["status"], "completed_steps": len(completed),
                    "expected_steps": expected_steps,
                    "duration_complete": receipt["status"] == "COMPLETE" and len(completed) == expected_steps,
                    "receipt_path": str(receipt_path), "receipt_sha256": frozen.sha256(receipt_path),
                    "baseline_receipt_path": str(baseline_receipt_path),
                    "baseline_receipt_sha256": frozen.sha256(baseline_receipt_path)},
        "runtime_binding": runtime_binding,
        "trace_identity": {"compressed_sha256": trace_row["compressed_sha256"],
                           "expanded_sha256": trace_row["sha256"],
                           "expanded_bytes": trace_row["bytes"],
                           "state_records_yielded_by_frozen_reader": state_record_count,
                           "pbl_records": {"status": "hashed_and_skipped_by_frozen_reader",
                                           "counted": False}},
        "compact_profile": profile,
        "first_600_seconds_baseline_comparison": prefix,
        "closed_history_baseline_comparison": history,
        "generic_completed_state_audit": {"status": "FAIL" if generic_failures else "PASS",
                                           "checked_retained_states": generic_checked,
                                           "failures": generic_failures,
                                           "scope": "Existing PR87 generic Q/N/B pair, PSD cone with 8-ULP slack, and dry-density number-conversion predicates applied to every retained completed state."},
        "exact_source_endpoint_audit": {"status": "FAIL" if exact_failures else "PASS",
                                         "checked_retained_endpoints": exact_checked,
                                         "failures": exact_failures,
                                         "scope": "Existing exact source coefficient predicates at retained RK3/PRE_KDM6/POST_KDM6 endpoints only; no ULP slack. Ice exact counts remain diagnostic under the frozen predicate."},
        "active_ice_policy_split": {"status": "FAIL" if active_failures else "PASS",
                                     "checked_retained_states": active_checked,
                                     "failures": active_failures,
                                     "scope": "Existing 8-ULP active ice policy on every retained state, reported separately from generic and exact endpoint gates."},
        "scope_limits": [
            "The first 600 seconds compare six state records per step byte-for-byte; later full PRE_RK/RK1/RK2/RK3/PRE_KDM6 records are absent except at detailed snapshots.",
            "The closed-history comparison covers only T, P, PB, PH, PHB, U, V, W, MU, and MUB at shared minute timestamps through 600 seconds; it does not establish full-state equivalence.",
            "Generic, exact, and active ice checks apply only to retained completed state records; they do not validate omitted later predictors or endpoints.",
            "This offline audit does not read a live binary trace or establish physical neutrality, mass closure, or scientific validity.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--arm", choices=("OFF", "COUPLED"), required=True)
    parser.add_argument("--duration-seconds", type=int, choices=(1800, 3600), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite audit output: {args.output}")
    try:
        result = audit_compact_run(args.run_root, args.baseline_root, args.arm,
                                   args.duration_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    procedural_complete = (result["compact_profile"]["status"] == "PASS"
                           and result["first_600_seconds_baseline_comparison"]["status"] == "PASS"
                           and result["closed_history_baseline_comparison"]["status"] == "PASS"
                           and result["runtime_binding"]["status"] == "PASS"
                           and result["runtime"]["duration_complete"])
    print(json.dumps({"procedural_audit_complete": procedural_complete,
                      "compact_profile": result["compact_profile"]["status"],
                      "prefix": result["first_600_seconds_baseline_comparison"]["status"],
                      "closed_history": result["closed_history_baseline_comparison"]["status"],
                      "generic": result["generic_completed_state_audit"]["status"],
                      "exact": result["exact_source_endpoint_audit"]["status"],
                      "active_ice": result["active_ice_policy_split"]["status"],
                      "duration_complete": result["runtime"]["duration_complete"]}))
    checks = (result["compact_profile"]["status"],
              result["first_600_seconds_baseline_comparison"]["status"],
              result["closed_history_baseline_comparison"]["status"],
              result["runtime_binding"]["status"])
    return 0 if all(status == "PASS" for status in checks) and result["runtime"]["duration_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
