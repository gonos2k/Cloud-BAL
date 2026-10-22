#!/usr/bin/env python3
"""Safely stage and receipt source-bound multistep OFF/HYDRO/COUPLED runs."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import errno
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path

import numpy as np


RUNTIME = Path("/var/tmp/pr85_same13_{arm}_joint_v17_20261015a")
RUN_RECEIPT = Path("/var/tmp/pr85_evidence_bundle_20261015/actual_v17_{arm}_run_receipt.json")
DEFAULT_OUT = Path("/var/tmp/pr86_budget_response_20261016")
INTEL_PROFILE = Path(__file__).resolve().parents[1] / "tests/intel_toolchain.sh"
STATE_MAGIC, TENDENCY_MAGIC = b"PR85QND2", b"PR85PLB1"
STATE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
TENDENCY_FIELDS = ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
SNAPSHOTS = {1: "20s", 3: "1min", 15: "5min", 16: "320s", 24: "480s", 25: "500s",
             30: "10min", 60: "20min", 90: "30min", 180: "60min"}
SNAPSHOT_SECONDS = tuple(timestep * 20 for timestep in SNAPSHOTS)
LAUNCH_ENVIRONMENT = {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE"}
LAUNCH_ENVIRONMENT_SHA256 = hashlib.sha256(
    b"export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE").hexdigest()


def snapshot_schedule(duration: int) -> dict[int, str]:
    """Select frozen milestones through duration and include its final step."""
    if duration <= 0 or duration % 20:
        raise ValueError("duration must be a positive multiple of the frozen 20-second timestep")
    seconds_to_label = {timestep * 20: label for timestep, label in SNAPSHOTS.items()}
    seconds = {value for value in SNAPSHOT_SECONDS if value <= duration}
    seconds.add(duration)
    return {value // 20: seconds_to_label.get(value, f"{value}s")
            for value in sorted(seconds)}


def _fatal_lines(stage: Path) -> tuple[list[str], list[str]]:
    """Return fatal log lines, including bare research-kernel rejection messages."""
    fatal = []
    issues = []
    for name in ("candidate_run.log", "rsl.error.0000", "rsl.out.0000"):
        path = stage / name
        if not path.exists():
            path = stage / f"{name}.gz"
        if not path.exists():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", errors="replace") as stream:
                for line in stream:
                    generic_fatal = re.search(r"fatal|error stop|segmentation|signal", line, re.I)
                    kdm6_rejection = (name == "rsl.error.0000" and re.match(
                        r"^\s*(?:KDM6|PR85|PR87|PR93|ProgB)\b.*\b(?:invalid|unsupported|failed|requires|no valid|rejected)\b",
                        line, re.I))
                    if generic_fatal or kdm6_rejection:
                        fatal.append(line.rstrip())
        except Exception as exc:
            issues.append(f"fatal scan {path.name}: {exc}")
    return fatal, issues


def model_end_time(start_text: str, duration: int) -> str:
    start = re.search(r"start_year\s*=\s*(\d+).*?start_month\s*=\s*(\d+).*?start_day\s*=\s*(\d+)"
                      r".*?start_hour\s*=\s*(\d+).*?start_minute\s*=\s*(\d+).*?start_second\s*=\s*(\d+)",
                      start_text, re.S)
    if not start:
        raise ValueError("namelist start timestamp missing")
    timestamp = dt.datetime(*map(int, start.groups())) + dt.timedelta(seconds=duration)
    return timestamp.strftime("%Y-%m-%d_%H:%M:%S")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_build_binding(path: Path) -> dict:
    path = path.resolve()
    receipt = json.loads(path.read_text())
    if receipt.get("schema") != "pr87_native_overlay_build_v1" or \
            receipt.get("status") != "PASS_OVERLAY_BUILD" or receipt.get("full_clean_build") is not False:
        raise ValueError("candidate build receipt is not a passing PR87 overlay")
    profile_path = Path(receipt["compiler_profile_path"])
    profile_sha = receipt["compiler_profile_sha256"]
    if sha256(INTEL_PROFILE) != profile_sha or sha256(profile_path) != profile_sha:
        raise ValueError("candidate build Intel profile identity mismatch")
    executable = Path(receipt["executable_path"])
    executable_sha = receipt["executable_sha256"]
    if sha256(executable) != executable_sha:
        raise ValueError("candidate build executable hash mismatch")
    with executable.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("candidate build executable is not ELF")
    return {"receipt_path": str(path), "receipt_sha256": sha256(path),
            "schema": receipt["schema"], "status": receipt["status"],
            "identity": receipt["identity"], "profile_path": str(profile_path),
            "profile_sha256": profile_sha, "executable_path": str(executable),
            "executable_sha256": executable_sha}


def _staged_expected_hash(name: str, input_hashes: dict, candidate_build: dict | None,
                          candidate_namelist_sha256: str | None = None,
                          candidate_wrfinput_sha256: str | None = None) -> str:
    if name == "wrf.exe" and candidate_build:
        return candidate_build["executable_sha256"]
    if name == "namelist.input" and candidate_namelist_sha256:
        return candidate_namelist_sha256
    if name == "wrfinput_d01" and candidate_wrfinput_sha256:
        return candidate_wrfinput_sha256
    return input_hashes[name]


def _hydro_input_binding(path: Path) -> dict:
    """Bind a separately produced HYDRO input without changing its OFF template."""
    path = path.resolve()
    receipt = json.loads(path.read_text())
    if (receipt.get("schema") != "pr94_hydro_native_input_v1" or receipt.get("role") != "HYDRO" or
            receipt.get("status") != "PASS_HYDRO_NATIVE_INPUT"):
        raise ValueError("expected a source-bound PR94 HYDRO native input receipt")
    artifacts = {name: receipt[name] for name in (
        "wrfinput", "wrfbdy", "source_candidate", "moment_policy", "initialization_receipt")}
    chain = receipt.get("source_chain_receipts")
    if not isinstance(chain, list) or not chain:
        raise ValueError("HYDRO source-chain receipts are missing")
    for row in [*artifacts.values(), *chain]:
        if sha256(Path(row["path"])) != row["sha256"]:
            raise ValueError(f"HYDRO artifact changed: {row['path']}")
    return {"receipt_path": str(path), "receipt_sha256": sha256(path),
            "artifacts": artifacts, "source_chain_receipts": chain,
            "comparison_contract": receipt.get("comparison_contract")}


def _native_input_binding(path: Path) -> dict:
    """Bind a COUPLED U/V projection proposal and every declared source artifact."""
    path = path.resolve()
    receipt = json.loads(path.read_text())
    if (receipt.get("schema") != "pr99_native_uv_projection_proposal_v1" or
            receipt.get("status") != "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION" or
            receipt.get("role") != "COUPLED"):
        raise ValueError("expected a source-bound PR99 COUPLED native input proposal")
    artifacts = {name: receipt[name] for name in (
        "candidate", "parent", "reference", "boundary", "generator", "composition")}
    for row in artifacts.values():
        if sha256(Path(row["path"])) != row["sha256"]:
            raise ValueError(f"native proposal artifact changed: {row['path']}")
    if receipt.get("composition_sha256") != artifacts["composition"]["sha256"]:
        raise ValueError("native proposal composition hash is inconsistent")
    return {"binding_kind": "native_uv_projection", "role": "COUPLED",
            "receipt_path": str(path), "receipt_sha256": sha256(path),
            "schema": receipt["schema"], "status": receipt["status"],
            "artifacts": artifacts, "composition_sha256": receipt["composition_sha256"]}


def _input_binding_unchanged(binding: dict | None) -> bool:
    if binding is None:
        return True
    kind = binding.get("binding_kind", "hydro")
    if kind == "hydro":
        return _hydro_input_binding(Path(binding["receipt_path"])) == binding
    if kind == "native_uv_projection":
        return _native_input_binding(Path(binding["receipt_path"])) == binding
    return False


def _validate_native_template(binding: dict, template_receipt: dict) -> None:
    artifacts = binding["artifacts"]
    if artifacts["parent"]["sha256"] != template_receipt["candidate_wrfinput_sha256"]:
        raise ValueError("native proposal parent differs from the frozen COUPLED input")
    if artifacts["boundary"]["sha256"] != template_receipt["candidate_wrfbdy_sha256"]:
        raise ValueError("native proposal boundary differs from the frozen COUPLED boundary")


def edit_namelist(text: str, seconds: int) -> str:
    start = re.search(r"start_year\s*=\s*(\d+).*?start_month\s*=\s*(\d+).*?start_day\s*=\s*(\d+)"
                      r".*?start_hour\s*=\s*(\d+).*?start_minute\s*=\s*(\d+).*?start_second\s*=\s*(\d+)",
                      text, re.S)
    if not start:
        raise ValueError("namelist start timestamp missing")
    y, mo, day, hour, minute, sec = map(int, start.groups())
    end = dt.datetime(y, mo, day, hour, minute, sec) + dt.timedelta(seconds=seconds)
    updates = {"run_days": "0", "run_hours": "0", "run_minutes": str(seconds // 60),
               "run_seconds": str(seconds % 60), "end_year": str(end.year),
               "end_month": f"{end.month:02}", "end_day": f"{end.day:02}",
               "end_hour": f"{end.hour:02}", "end_minute": f"{end.minute:02}",
               "end_second": f"{end.second:02}", "history_interval": "1"}
    for name, value in updates.items():
        text, count = re.subn(rf"(?m)^(\s*{name}\s*=\s*)[^,\n]+", rf"\g<1>{value}", text, count=1)
        if count != 1:
            raise ValueError(f"expected one {name} namelist value")
    return text


def _field_stats(values: np.ndarray) -> dict:
    finite = np.isfinite(values)
    selected = values[finite]
    return {"cells": int(values.size), "finite": int(finite.sum()),
            "nonfinite": int((~finite).sum()), "negative": int((values < 0).sum()),
            "zero": int((values == 0).sum()),
            "min": float(selected.min()) if selected.size else None,
            "max": float(selected.max()) if selected.size else None}


def read_time_snapshots(path: Path, duration: int | None = None) -> dict:
    """Stream the stage trace and retain only selected POST_KDM6 snapshots."""
    selected_snapshots = snapshot_schedule(duration) if duration is not None else SNAPSHOTS
    snapshots, timesteps, completed, duplicate_post = {}, set(), set(), set()
    count = 0
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        while magic := stream.read(8):
            if len(magic) != 8:
                raise ValueError("truncated stage trace magic")
            label_raw, header = stream.read(32), stream.read(60)
            if len(label_raw) != 32 or len(header) != 60:
                raise ValueError("truncated stage trace header")
            label = label_raw.decode("ascii").strip()
            values = struct.unpack(">15i", header)
            kind, timestep, rkstep = values[:3]
            expected_kind = 1 if magic == STATE_MAGIC else 2 if magic == TENDENCY_MAGIC else -1
            if kind != expected_kind or timestep <= 0:
                raise ValueError(f"invalid trace record {count}: {label} timestep={timestep}")
            timesteps.add(timestep)
            count += 1
            bounds = values[3:]
            cells = ((bounds[9] - bounds[8] + 1) * (bounds[11] - bounds[10] + 1) *
                     (bounds[7] - bounds[6] + 1))
            if cells <= 0:
                raise ValueError("invalid active stage-trace bounds")
            is_snapshot = magic == STATE_MAGIC and label == "POST_KDM6" and timestep in selected_snapshots
            digest = hashlib.sha256(magic + label_raw + header)
            fields = {}
            names = STATE_FIELDS if magic == STATE_MAGIC else TENDENCY_FIELDS
            for field in names:
                raw = stream.read(cells * 4)
                if len(raw) != cells * 4:
                    raise ValueError(f"truncated {label} {field} at timestep {timestep}")
                digest.update(raw)
                if is_snapshot:
                    fields[field] = _field_stats(np.frombuffer(raw, dtype=">f4"))
            if is_snapshot:
                key = selected_snapshots[timestep]
                if key not in snapshots:
                    snapshots[key] = {
                        "timestep": timestep, "model_seconds": 20 * timestep,
                        "stage": label, "rkstep": rkstep, "active_cells": cells,
                        "record_sha256": digest.hexdigest(), "fields": fields,
                    }
            if magic == STATE_MAGIC and label == "POST_KDM6":
                if timestep in completed:
                    duplicate_post.add(timestep)
                completed.add(timestep)
    return {"record_count": count, "timesteps": sorted(timesteps),
            "completed_post_kdm6_timesteps": sorted(completed),
            "duplicate_post_kdm6_timesteps": sorted(duplicate_post), "snapshots": snapshots}


def _projected_step_bytes(receipt: dict, runtime: Path) -> int:
    # First-call and KDM6 source traces are one-time guarded by pr67_trace_complete.
    once = {"kdm6_first_call_pre.raw", "kdm6_first_call_post.raw", "pr67_kdm6_process.raw"}
    per_step = sum(row["bytes"] for name, row in receipt["native_trace_outputs"].items() if name not in once)
    per_step += (runtime / "rsl.error.0000").stat().st_size
    return per_step + 64 * 1024 * 1024


def _disk_reference_projection(reference_path: Path, arm: str, source_receipt_sha256: str,
                               source_namelist_sha256: str, input_hashes: dict,
                               executable_sha256: str, wrfinput_sha256: str,
                               wrfbdy_sha256: str, pr87_probe: str | None) -> dict:
    """Validate a successful same-input run and project disk use from its artifacts."""
    reference_path = reference_path.resolve()
    receipt = json.loads(reference_path.read_text())
    preflight_path = reference_path.parent / "preflight.json"
    preflight = json.loads(preflight_path.read_text())
    steps = receipt.get("timestep_count")
    if (receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0 or
            not isinstance(steps, int) or steps <= 0 or
            receipt.get("final_completed_step") != steps or
            receipt.get("maximum_seen_timestep") != steps or
            len(receipt.get("model_timestamps", [])) != steps or
            receipt.get("duplicate_post_kdm6_timesteps") or receipt.get("earliest_fatal") or
            receipt.get("fatal_lines") or receipt.get("processing_errors") or
            receipt.get("changed_staged_inputs") or receipt.get("changed_original_inputs") or
            receipt.get("candidate_build_unchanged") is not True):
        raise ValueError("disk reference receipt is incomplete or contains run errors")
    actual_timestamps = [row.get("timestamp") for row in receipt.get("model_timestamps", [])
                         if isinstance(row, dict)]
    if (actual_timestamps != receipt.get("expected_model_timestamps") or
            receipt.get("final_completed_step") != len(receipt.get("expected_model_timestamps", []))):
        raise ValueError("disk reference timestep sequence is not contiguous")
    if (preflight.get("arm") != arm or receipt.get("arm") != arm or
            preflight.get("source_receipt_sha256") != source_receipt_sha256 or
            preflight.get("source_namelist_sha256") != source_namelist_sha256 or
            preflight.get("input_hashes") != input_hashes or
            preflight.get("baseline_frozen_executable_sha256") != executable_sha256 or
            preflight.get("candidate_wrfinput_sha256") != wrfinput_sha256 or
            preflight.get("candidate_wrfbdy_sha256") != wrfbdy_sha256 or
            preflight.get("timestep_seconds") != 20 or
            preflight.get("namelist_changes", {}).get("history_interval_minutes") != 1 or
            receipt.get("pr87_probe") != pr87_probe or
            preflight.get("launch_environment", {}).get("OMP_NUM_THREADS") != "1" or
            preflight.get("launch_environment", {}).get("OMP_DYNAMIC") != "FALSE" or
            preflight.get("launch_environment", {}).get("launch_request_sha256") !=
            LAUNCH_ENVIRONMENT_SHA256):
        raise ValueError("disk reference preflight does not match candidate source and controls")
    candidate_build = preflight.get("candidate_build")
    if receipt.get("candidate_build") != candidate_build:
        raise ValueError("disk reference candidate build differs from preflight")
    expected_executable_sha256 = (candidate_build.get("executable_sha256") if candidate_build
                                  else preflight.get("executable_sha256"))
    if (receipt.get("expected_executed_executable_sha256") != expected_executable_sha256 or
            receipt.get("executed_executable_sha256") != expected_executable_sha256):
        raise ValueError("disk reference executable differs from preflight candidate")
    if candidate_build:
        try:
            if _candidate_build_binding(Path(candidate_build["receipt_path"])) != candidate_build:
                raise ValueError("disk reference candidate build receipt changed")
        except Exception as exc:
            raise ValueError("disk reference candidate build is not unchanged") from exc
    if (receipt.get("source_receipt_sha256") != source_receipt_sha256 or
            receipt.get("candidate_wrfinput_sha256") != wrfinput_sha256 or
            receipt.get("candidate_wrfbdy_sha256") != wrfbdy_sha256 or
            receipt.get("baseline_frozen_executable_sha256") != executable_sha256):
        raise ValueError("disk reference receipt input identity mismatch")

    stage = reference_path.parent / "run"
    generated = receipt.get("generated_files")
    compressed = receipt.get("compressed_outputs")
    if not isinstance(generated, list) or not isinstance(compressed, list):
        raise ValueError("disk reference artifact inventory missing")
    generated_by_name = {}
    for row in generated:
        name = row.get("path")
        if not isinstance(name, str) or Path(name).name != name or name in generated_by_name:
            raise ValueError("disk reference has duplicate or unsafe generated artifact paths")
        path = stage / name
        if (not path.is_file() or path.stat().st_size != row.get("bytes") or
                sha256(path) != row.get("sha256")):
            raise ValueError(f"disk reference artifact changed: {name}")
        generated_by_name[name] = row
    compressed_names, archive_names = set(), set()
    trace_bytes = 0
    for row in compressed:
        raw_name, archive_name = row.get("path"), row.get("compressed_path")
        if (not isinstance(raw_name, str) or Path(raw_name).name != raw_name or
                not isinstance(archive_name, str) or Path(archive_name).name != archive_name or
                raw_name == archive_name or raw_name in compressed_names or
                raw_name in archive_names or archive_name in archive_names or
                archive_name in compressed_names):
            raise ValueError("disk reference has duplicate or unsafe compressed artifact paths")
        compressed_names.add(raw_name)
        archive_names.add(archive_name)
        archive = stage / archive_name
        if (not archive.is_file() or archive.stat().st_size != row.get("compressed_bytes") or
                sha256(archive) != row.get("compressed_sha256")):
            raise ValueError(f"disk reference compressed archive changed: {archive_name}")
        digest, byte_count = hashlib.sha256(), 0
        try:
            with gzip.open(archive, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_count += len(block)
        except Exception as exc:
            raise ValueError(f"disk reference compressed archive is unreadable: {archive_name}") from exc
        if byte_count != row.get("bytes") or digest.hexdigest() != row.get("sha256"):
            raise ValueError(f"disk reference uncompressed artifact changed: {raw_name}")
        generated_row = generated_by_name.get(archive_name)
        if (generated_row is None or generated_row.get("bytes") != row.get("compressed_bytes") or
                generated_row.get("sha256") != row.get("compressed_sha256")):
            raise ValueError(f"disk reference archive inventory mismatch: {archive_name}")
        trace_bytes += row["bytes"]
    histories = [row for row in generated if row["path"].startswith("wrfout")]
    if not histories:
        raise ValueError("disk reference history artifact missing")
    history_bytes = sum(row["bytes"] for row in histories)
    multiplier = 3
    slack = 64 * 1024 * 1024
    measured_bytes = trace_bytes + history_bytes
    per_step = multiplier * math.ceil(measured_bytes / steps) + slack
    return {"method": "successful_same_input_receipt", "reference_receipt": str(reference_path),
            "reference_receipt_sha256": sha256(reference_path),
            "reference_preflight": str(preflight_path),
            "reference_preflight_sha256": sha256(preflight_path),
            "reference_arm": arm, "reference_timestep_count": steps,
            "source_trace_uncompressed_bytes": trace_bytes,
            "history_artifact_bytes": history_bytes,
            "measured_uncompressed_bytes": measured_bytes,
            "artifact_multiplier": multiplier, "safety_slack_bytes_per_step": slack,
            "cadence_seconds": 20, "per_step_projection_bytes": per_step,
            "history_artifacts": histories,
            "compressed_archive_count": len(compressed)}


def diagnostic_run_id(arm: str, out: Path) -> str:
    """Give the native trace writer a stable, whitespace-free run identity."""
    return arm + "_" + hashlib.sha256(str(out.resolve()).encode()).hexdigest()[:16]


def prepare(arm: str, duration: int, out: Path, safety_fraction: float = 0.85,
            candidate_build_path: Path | None = None,
            disk_reference_receipt_path: Path | None = None,
            hydro_input_receipt_path: Path | None = None,
            native_input_receipt_path: Path | None = None) -> dict:
    snapshot_schedule(duration)
    if hydro_input_receipt_path is not None and native_input_receipt_path is not None:
        raise ValueError("HYDRO and native projection input receipts are mutually exclusive")
    if arm == "HYDRO":
        if hydro_input_receipt_path is None or native_input_receipt_path is not None:
            raise ValueError("HYDRO requires its own input receipt")
    elif hydro_input_receipt_path is not None:
        raise ValueError("HYDRO input receipt is only valid for the HYDRO arm")
    if native_input_receipt_path is not None and arm != "COUPLED":
        raise ValueError("native projection input receipt is only valid for the COUPLED arm")
    if native_input_receipt_path is not None and duration != 20:
        raise ValueError("native projection input receipt is limited to one 20-second step")
    template_arm = "OFF" if arm == "HYDRO" else arm
    runtime = Path(str(RUNTIME).format(arm=template_arm))
    receipt_path = Path(str(RUN_RECEIPT).format(arm=template_arm))
    receipt = json.loads(receipt_path.read_text())
    inputs = {Path(row["path"]).name: row["sha256_after"] for row in receipt["run_isolation"]["inputs"]}
    exe = runtime / "wrf.exe"
    if sha256(exe) != receipt["native_executable_sha256"]:
        raise ValueError(f"{arm}: frozen executable hash changed")
    if sha256(runtime / "wrfinput_d01") != receipt["candidate_wrfinput_sha256"]:
        raise ValueError(f"{arm}: candidate input hash changed")
    if sha256(runtime / "wrfbdy_d01") != receipt["candidate_wrfbdy_sha256"]:
        raise ValueError(f"{arm}: boundary hash changed")
    bad = [n for n, h in inputs.items() if not (runtime / n).is_file() or sha256(runtime / n) != h]
    if bad:
        raise ValueError(f"{arm}: frozen inputs changed: {bad}")
    candidate_build = (_candidate_build_binding(candidate_build_path)
                       if candidate_build_path is not None else None)
    candidate_input = (_hydro_input_binding(hydro_input_receipt_path)
                       if hydro_input_receipt_path is not None else
                       _native_input_binding(native_input_receipt_path)
                       if native_input_receipt_path is not None else None)
    if (candidate_input and candidate_input.get("binding_kind", "hydro") == "hydro" and
            candidate_input["artifacts"]["wrfbdy"]["sha256"] != receipt["candidate_wrfbdy_sha256"]):
        raise ValueError("HYDRO boundary differs from the frozen matched boundary")
    if candidate_input and candidate_input.get("binding_kind") == "native_uv_projection":
        _validate_native_template(candidate_input, receipt)
        wrfinput_sha256 = candidate_input["artifacts"]["candidate"]["sha256"]
    else:
        wrfinput_sha256 = (candidate_input["artifacts"]["wrfinput"]["sha256"] if candidate_input
                          else receipt["candidate_wrfinput_sha256"])
    namelist = runtime / "namelist.input"
    original_namelist = namelist.read_text()
    edited = edit_namelist(original_namelist, duration)
    namelist_diff = "".join(difflib.unified_diff(
        original_namelist.splitlines(keepends=True), edited.splitlines(keepends=True),
        fromfile="v17/namelist.input", tofile="pr86/namelist.input"))
    steps = math.ceil(duration / 20)
    reference_projection = None
    if disk_reference_receipt_path is None:
        per_step_projection = _projected_step_bytes(receipt, runtime)
    else:
        reference_projection = _disk_reference_projection(
            disk_reference_receipt_path, arm, sha256(receipt_path), sha256(namelist), inputs,
            sha256(exe), wrfinput_sha256, receipt["candidate_wrfbdy_sha256"],
            os.environ.get("PR87_PROBE"))
        per_step_projection = reference_projection["per_step_projection_bytes"]
    projected = per_step_projection * steps
    disk = shutil.disk_usage(out.parent if out.parent.exists() else Path("/var/tmp"))
    required_free = math.ceil(projected / safety_fraction)
    return {
        "arm": arm, "duration_seconds": duration, "timestep_seconds": 20,
        "expected_timesteps": steps, "runtime_dir": str(runtime), "source_receipt": str(receipt_path),
        "source_receipt_sha256": sha256(receipt_path),
        "executable_sha256": sha256(exe), "candidate_wrfinput_sha256": wrfinput_sha256,
        "template_arm": template_arm, "candidate_input_binding": candidate_input,
        "baseline_frozen_executable_sha256": sha256(exe), "candidate_build": candidate_build,
        "candidate_wrfbdy_sha256": receipt["candidate_wrfbdy_sha256"], "input_file_count": len(inputs),
        "input_hashes": inputs, "source_namelist_sha256": sha256(namelist),
        "candidate_namelist_sha256": hashlib.sha256(edited.encode()).hexdigest(),
        "launch_environment": {**LAUNCH_ENVIRONMENT,
                               "status": "CONFIGURED_BY_RUNNER",
                               "launch_request_sha256": LAUNCH_ENVIRONMENT_SHA256},
        "diagnostic_environment": {"PR91_RUN_ID": diagnostic_run_id(arm, out)},
        "namelist_changes": {"runtime_seconds": duration, "end_time": model_end_time(original_namelist, duration),
                             "history_interval_minutes": 1}, "namelist_diff": namelist_diff,
        "namelist_text": edited,
        "first_v17_step_seconds": 662.69806,
        "disk_guard": {"free_bytes": disk.free, "per_step_projection_bytes": per_step_projection,
                       "active_run_projection_bytes": projected,
                       "required_free_bytes": required_free,
                       "safety_fraction": safety_fraction,
                       "status": "PASS" if disk.free >= required_free else "FAIL",
                       "reference": reference_projection},
        "output": str(out),
    }


def _stage(prepared: dict, out: Path) -> Path:
    runtime, stage = Path(prepared["runtime_dir"]), out / "run"
    stage.mkdir(parents=True)
    for name in prepared["input_hashes"]:
        if name not in {"namelist.input", "namelist.input.source"}:
            try:
                os.link(runtime / name, stage / name)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.copy2(runtime / name, stage / name)
    candidate_input = prepared.get("candidate_input_binding")
    if candidate_input:
        if not _input_binding_unchanged(candidate_input):
            raise ValueError("source-bound native input changed after preflight")
        staged_input = stage / "wrfinput_d01"
        staged_input.unlink()
        input_artifact = (candidate_input["artifacts"]["candidate"]
                          if candidate_input.get("binding_kind") == "native_uv_projection"
                          else candidate_input["artifacts"]["wrfinput"])
        shutil.copy2(input_artifact["path"], staged_input)
        if sha256(staged_input) != prepared["candidate_wrfinput_sha256"]:
            raise ValueError("staged candidate input hash mismatch")
    candidate_build = prepared.get("candidate_build")
    if candidate_build:
        staged_executable = stage / "wrf.exe"
        staged_executable.unlink()
        shutil.copy2(candidate_build["executable_path"], staged_executable)
        if sha256(staged_executable) != candidate_build["executable_sha256"]:
            raise ValueError("staged candidate executable hash mismatch")
    shutil.copy2(runtime / "namelist.input.source", stage / "namelist.input.source")
    (stage / "namelist.input").write_text(prepared["namelist_text"])
    (stage / "namelist.input.diff").write_text(prepared["namelist_diff"])
    return stage



def verify_staged_inputs(prepared: dict, stage: Path) -> None:
    """Reject changed staging bytes before WRF can consume them."""
    for name in prepared["input_hashes"]:
        expected = _staged_expected_hash(
            name, prepared["input_hashes"], prepared.get("candidate_build"),
            prepared.get("candidate_namelist_sha256"), prepared.get("candidate_wrfinput_sha256"))
        if sha256(stage / name) != expected:
            raise ValueError(f"staged input hash differs from preflight: {name}")


def _model_times(stage: Path) -> list[dict]:
    pattern = re.compile(r"Timing for main: time\s+(\S+)\s+on domain\s+\d+:\s+([0-9.Ee+\-]+) elapsed seconds")
    logs = {}
    for name in ("rsl.error.0000", "rsl.out.0000", "candidate_run.log"):
        path = stage / name
        if not path.exists():
            path = stage / f"{name}.gz"
        if path.exists():
            opener = gzip.open if path.suffix == ".gz" else open
            rows = []
            with opener(path, "rt", errors="replace") as stream:
                for line in stream:
                    if match := pattern.search(line):
                        rows.append({"timestamp": match.group(1),
                                     "elapsed_seconds": float(match.group(2))})
            if rows:
                times = [row["timestamp"] for row in rows]
                if len(times) != len(set(times)):
                    raise ValueError(f"duplicate model timestamps within {path.name}")
                logs[name] = rows
    if not logs:
        return []
    primary_name, primary = next(iter(logs.items()))
    primary_times = [row["timestamp"] for row in primary]
    for name, rows in list(logs.items())[1:]:
        if [row["timestamp"] for row in rows] != primary_times:
            raise ValueError(f"model timestamp sequence differs between {primary_name} and {name}")
    return primary


def _unknown_execution_layout(reason: str, preflight: dict | None = None) -> dict:
    return {"status": "UNKNOWN", "single_execution_layout": None, "reason": reason,
            "basis": "candidate namelist max_dom, same-run receipt-bound rsl.out.0000, and recorded launch request",
            "source_sha256": {
                "candidate_namelist": (preflight or {}).get("candidate_namelist_sha256"),
                "launch_request": (preflight or {}).get("launch_environment", {}).get(
                    "launch_request_sha256")}}


def _namelist_max_dom(text: str) -> int:
    uncommented = "\n".join(line.split("!", 1)[0] for line in text.splitlines())
    values = re.findall(r"(?im)^\s*max_dom\s*=\s*(\d+)\s*,?\s*$", uncommented)
    if len(values) != 1:
        raise ValueError("staged namelist must contain exactly one integer max_dom")
    return int(values[0])


def _rsl_layout(path: Path) -> tuple[set[tuple[int, int]], set[int]]:
    opener = gzip.open if path.suffix == ".gz" else open
    tasks, tiles = set(), set()
    task_pattern = re.compile(r"Ntasks\s+in\s+X\s+(\d+)\s*,\s*ntasks\s+in\s+Y\s+(\d+)", re.I)
    tile_pattern = re.compile(r"WRF\s*NUMBER\s*OF\s*TILES\s*=\s*(\d+)", re.I)
    with opener(path, "rt", errors="replace") as stream:
        for line in stream:
            if match := task_pattern.search(line):
                tasks.add((int(match.group(1)), int(match.group(2))))
            if match := tile_pattern.search(line):
                tiles.add(int(match.group(1)))
    return tasks, tiles


def _payload_sha256(path: Path) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    digest = hashlib.sha256()
    with opener(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rsl_output_is_bound(path: Path, receipt: dict) -> bool:
    payload_sha = _payload_sha256(path)
    if path.suffix == ".gz":
        if sha256(path) not in {row.get("compressed_sha256") for row in
                                receipt.get("compressed_outputs", [])
                                if row.get("compressed_path") == path.name}:
            return False
        return payload_sha in {row.get("sha256") for row in receipt.get("compressed_outputs", [])
                               if row.get("compressed_path") == path.name}
    return payload_sha in {row.get("sha256") for row in receipt.get("generated_files", [])
                           if row.get("path") == path.name}


def _execution_layout(preflight: dict, stage: Path, receipt: dict | None = None) -> dict:
    launch = preflight.get("launch_environment")
    if (not isinstance(launch, dict) or launch.get("status") != "CONFIGURED_BY_RUNNER"
            or launch.get("OMP_NUM_THREADS") != "1" or launch.get("OMP_DYNAMIC") != "FALSE"
            or launch.get("launch_request_sha256") != LAUNCH_ENVIRONMENT_SHA256):
        return _unknown_execution_layout("preflight lacks a verified runner launch request", preflight)
    namelist_path = stage / "namelist.input"
    rsl_path = next((path for path in (stage / "rsl.out.0000", stage / "rsl.out.0000.gz")
                     if path.is_file()), None)
    try:
        namelist_sha = sha256(namelist_path)
        if namelist_sha != preflight.get("candidate_namelist_sha256"):
            raise ValueError("staged namelist hash differs from preflight")
        max_dom = _namelist_max_dom(namelist_path.read_text(encoding="utf-8"))
        if rsl_path is None:
            raise ValueError("same-run rsl.out.0000 is absent")
        if receipt is not None and not _rsl_output_is_bound(rsl_path, receipt):
            raise ValueError("same-run rsl.out.0000 is not receipt-bound")
        tasks, tiles = _rsl_layout(rsl_path)
        if len(tasks) != 1 or len(tiles) != 1:
            raise ValueError("RSL rank or tile layout is absent or contradictory")
        ntasks_x, ntasks_y = next(iter(tasks))
        tile_count = next(iter(tiles))
        if min(ntasks_x, ntasks_y, tile_count) < 1 or max_dom < 1:
            raise ValueError("invalid execution-layout count")
        if max_dom != 1:
            raise ValueError(f"unsupported max_dom={max_dom}")
        single = (ntasks_x == 1 and ntasks_y == 1 and tile_count == 1
                  and launch["OMP_NUM_THREADS"] == "1")
        return {"status": "VERIFIED_SINGLE" if single else "KNOWN_MULTIPLE",
                "single_execution_layout": single, "domain_count": max_dom,
                "mpi_tasks_x": ntasks_x, "mpi_tasks_y": ntasks_y,
                "mpi_rank_count": ntasks_x * ntasks_y, "mpi_ranks": ntasks_x * ntasks_y,
                "tiles_per_domain": tile_count,
                "threads": int(launch["OMP_NUM_THREADS"]),
                "configured_omp_threads": int(launch["OMP_NUM_THREADS"]),
                "configured_omp_dynamic": launch["OMP_DYNAMIC"],
                "thread_count_basis": "configured by this runner launch request; not runtime-observed",
                "basis": "candidate namelist max_dom, same-run receipt-bound rsl.out.0000, and recorded launch request",
                "source_sha256": {"candidate_namelist": namelist_sha,
                                  "launch_request": launch["launch_request_sha256"],
                                  "rsl_out_0000_payload": _payload_sha256(rsl_path),
                                  "rsl_out_0000_artifact": sha256(rsl_path)}}
    except (OSError, ValueError, EOFError) as exc:
        return _unknown_execution_layout(str(exc), preflight)


def _compress_closed(stage: Path) -> list[dict]:
    result = []
    paths = list(stage.glob("*.raw")) + list(stage.glob("rsl.*")) + [stage / "candidate_run.log"]
    for path in sorted(paths):
        if not path.is_file():
            continue
        raw_sha, raw_bytes = sha256(path), path.stat().st_size
        target = path.with_name(path.name + ".gz")
        with path.open("rb") as source, target.open("xb") as target_stream:
            with gzip.GzipFile(fileobj=target_stream, mode="wb", compresslevel=1, mtime=0) as gz:
                shutil.copyfileobj(source, gz, 1024 * 1024)
        digest, byte_count = hashlib.sha256(), 0
        with gzip.open(target, "rb") as verified:
            for block in iter(lambda: verified.read(1024 * 1024), b""):
                digest.update(block)
                byte_count += len(block)
        if digest.hexdigest() != raw_sha or byte_count != raw_bytes:
            target.unlink()
            raise ValueError(f"compressed output failed integrity check: {path.name}")
        result.append({"path": path.name, "sha256": raw_sha, "bytes": raw_bytes,
                       "compressed_path": target.name, "compressed_sha256": sha256(target),
                       "compressed_bytes": target.stat().st_size})
        path.unlink()
    return result


def finalize_existing_run(arm: str, out: Path, duration: int,
                          candidate_build_path: Path | None = None) -> dict:
    """Rebuild a strict receipt from closed run files without rerunning WRF."""
    schedule = snapshot_schedule(duration)
    preflight = json.loads((out / "preflight.json").read_text())
    original = json.loads((out / "receipt.json").read_text()) if (out / "receipt.json").exists() else {}
    stage = out / "run"
    issues = []
    if preflight.get("arm", arm) != arm or original.get("arm", arm) != arm:
        issues.append("requested arm differs from run provenance")
    candidate_input = preflight.get("candidate_input_binding")
    binding_kind = candidate_input.get("binding_kind", "hydro") if candidate_input else None
    if arm == "HYDRO":
        if binding_kind != "hydro":
            issues.append("HYDRO arm requires its own source-bound input")
        elif (preflight.get("template_arm") != "OFF" or original.get("arm") != "HYDRO" or
              original.get("candidate_input_binding") != candidate_input or
              original.get("candidate_wrfinput_sha256") != preflight.get("candidate_wrfinput_sha256") or
              preflight.get("candidate_wrfinput_sha256") !=
              candidate_input.get("artifacts", {}).get("wrfinput", {}).get("sha256")):
            issues.append("HYDRO launch input provenance differs from preflight")
    elif binding_kind == "hydro":
        issues.append("HYDRO source-bound input is only valid for the HYDRO arm")
    elif binding_kind == "native_uv_projection":
        template_receipt = json.loads(Path(preflight["source_receipt"]).read_text())
        try:
            _validate_native_template(candidate_input, template_receipt)
        except (KeyError, ValueError) as exc:
            issues.append(str(exc))
        if (duration != 20 or preflight.get("duration_seconds") != 20 or
                arm != "COUPLED" or candidate_input.get("role") != "COUPLED" or
                preflight.get("template_arm") != "COUPLED" or original.get("arm") != "COUPLED" or
                original.get("candidate_input_binding") != candidate_input or
                original.get("candidate_wrfinput_sha256") != preflight.get("candidate_wrfinput_sha256") or
                preflight.get("candidate_wrfinput_sha256") !=
                candidate_input.get("artifacts", {}).get("candidate", {}).get("sha256")):
            issues.append("COUPLED native proposal provenance differs from preflight")
    elif candidate_input is not None:
        issues.append("unknown source-bound input kind")
    candidate_build = preflight.get("candidate_build")
    candidate_build_unchanged = True
    if candidate_build_path is not None and (not candidate_build or
                                              Path(candidate_build["receipt_path"]) != candidate_build_path.resolve()):
        issues.append("candidate build path differs from preflight")
        candidate_build_unchanged = False
    if candidate_build:
        try:
            if _candidate_build_binding(Path(candidate_build["receipt_path"])) != candidate_build:
                issues.append("candidate build identity changed after preflight")
                candidate_build_unchanged = False
        except Exception as exc:
            issues.append(f"candidate build validation: {exc}")
            candidate_build_unchanged = False
    if original.get("candidate_build") != candidate_build:
        issues.append("launch candidate build identity differs from preflight")
        candidate_build_unchanged = False
    try:
        executed_executable_sha256 = sha256(stage / "wrf.exe")
    except OSError:
        executed_executable_sha256 = None
        issues.append("staged executable is missing")
    expected_executable_sha256 = (candidate_build["executable_sha256"] if candidate_build
                                  else preflight.get("executable_sha256"))
    if executed_executable_sha256 != expected_executable_sha256:
        issues.append("staged executable hash differs from preflight")
    try:
        times = _model_times(stage)
    except Exception as exc:
        times = []
        issues.append(f"model time parsing: {exc}")
    fatal, fatal_scan_issues = _fatal_lines(stage)
    issues.extend(fatal_scan_issues)
    trace = stage / "pr85_joint_moment_stages.raw"
    if not trace.exists():
        trace = stage / "pr85_joint_moment_stages.raw.gz"
    try:
        snapshots = read_time_snapshots(trace, duration) if trace.is_file() else {
            "record_count": 0, "timesteps": [], "completed_post_kdm6_timesteps": [], "snapshots": {}}
    except Exception as exc:
        snapshots = {"record_count": 0, "timesteps": [],
                     "completed_post_kdm6_timesteps": [],
                     "duplicate_post_kdm6_timesteps": [], "snapshots": {}}
        issues.append(f"snapshot parse: {exc}")
    input_hashes = preflight.get("input_hashes", {})
    if not input_hashes:
        input_hashes = {Path(row["path"]).name: row["sha256_after"] for row in json.loads(
            Path(preflight["source_receipt"]).read_text())["run_isolation"]["inputs"]}
    changed_stage = []
    for name, expected in input_hashes.items():
        staged = stage / name
        if not staged.is_file():
            changed_stage.append(name)
            continue
        if name == "namelist.input":
            expected = preflight["candidate_namelist_sha256"]
        if sha256(staged) != _staged_expected_hash(
                name, input_hashes, candidate_build, preflight.get("candidate_namelist_sha256"),
                preflight.get("candidate_wrfinput_sha256")):
            changed_stage.append(name)
    candidate_input = preflight.get("candidate_input_binding")
    try:
        candidate_input_unchanged = _input_binding_unchanged(candidate_input)
    except (OSError, ValueError, KeyError) as exc:
        candidate_input_unchanged = False
        label = "HYDRO" if binding_kind == "hydro" else "source-bound native"
        issues.append(f"{label} input binding validation: {exc}")
    if not candidate_input_unchanged:
        message = ("HYDRO input binding changed after preflight" if binding_kind == "hydro"
                   else "source-bound input changed after preflight")
        issues.append(message)
    source = Path(preflight["runtime_dir"])
    source_after = {}
    changed_original = []
    for name, expected in input_hashes.items():
        try:
            digest = sha256(source / name)
        except OSError:
            digest = None
        source_after[name] = digest
        if digest != expected:
            changed_original.append(name)
    source_receipt_path = Path(preflight["source_receipt"])
    source_receipt_sha = preflight.get("source_receipt_sha256") or sha256(source_receipt_path)
    source_receipt_unchanged = sha256(source_receipt_path) == source_receipt_sha
    expected_times = [(dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=20 * i)).strftime("%Y-%m-%d_%H:%M:%S")
                      for i in range(1, duration // 20 + 1)]
    actual_times = [row["timestamp"] for row in times]
    completed = snapshots.get("completed_post_kdm6_timesteps", [])
    duplicate_post = snapshots.get("duplicate_post_kdm6_timesteps", [])
    complete = (original.get("returncode") == 0 and actual_times == expected_times and
                completed == list(range(1, duration // 20 + 1)) and not duplicate_post and
                not fatal and not issues and
                not changed_stage and not changed_original and source_receipt_unchanged and
                candidate_build_unchanged and candidate_input_unchanged and
                set(schedule.values()).issubset(snapshots["snapshots"]))
    compressed = original.get("compressed_outputs", [])
    for row in compressed:
        path = stage / row["compressed_path"]
        digest, byte_count = hashlib.sha256(), 0
        if not path.is_file() or sha256(path) != row["compressed_sha256"]:
            issues.append(f"compressed file hash mismatch: {row['compressed_path']}")
            continue
        try:
            with gzip.open(path, "rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_count += len(block)
        except OSError as exc:
            issues.append(f"compressed file cannot be read: {row['compressed_path']}: {exc}")
            continue
        if byte_count != row["bytes"] or digest.hexdigest() != row["sha256"]:
            issues.append(f"compressed payload hash mismatch: {row['compressed_path']}")
    if issues:
        complete = False
    generated = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                 for path in sorted(stage.iterdir()) if path.is_file()]
    receipt = {
        **original, "arm": arm, "status": "COMPLETE" if complete else "INCOMPLETE",
        "model_timestamps": times, "expected_model_timestamps": expected_times,
        "timestep_count": len(times), "earliest_fatal": fatal[0] if fatal else None,
        "fatal_lines": fatal[:100], "snapshots": snapshots,
        "maximum_seen_timestep": max(snapshots["timesteps"]) if snapshots["timesteps"] else None,
        "final_completed_step": max(completed) if completed else None,
        "duplicate_post_kdm6_timesteps": duplicate_post,
        "changed_staged_inputs": changed_stage, "changed_original_inputs": changed_original,
        "baseline_frozen_executable_sha256": preflight.get("baseline_frozen_executable_sha256",
                                                           preflight.get("executable_sha256")),
        "executed_executable_sha256": executed_executable_sha256,
        "expected_executed_executable_sha256": expected_executable_sha256,
        "candidate_build": candidate_build,
        "candidate_build_unchanged": candidate_build_unchanged,
        "candidate_input_binding": candidate_input,
        "candidate_input_unchanged": candidate_input_unchanged,
        "pr87_probe": original.get("pr87_probe"),
        "source_inputs_after_sha256": source_after, "processing_errors": issues,
        "source_receipt_sha256": source_receipt_sha,
        "source_receipt_unchanged": source_receipt_unchanged,
        "generated_files": generated,
    }
    receipt.pop("final_state_timestep", None)
    launch_provenance_path = out / "launch_provenance.json"
    launch_provenance = (json.loads(launch_provenance_path.read_text())
                         if launch_provenance_path.is_file() else {})
    launch_receipt_path = out / "receipt.launch.json"
    receipt.update({
        "launch_runner_source_sha256": launch_provenance.get("launch_runner_source_sha256"),
        "launch_runner_source_sha256_status": (
            "recorded in launch_provenance.json" if launch_provenance.get("launch_runner_source_sha256")
            else "not recorded at launch; source hash unavailable"),
        "successor_collector_source_sha256": sha256(Path(__file__).resolve()),
        "successor_collector_source_path": str(Path(__file__).resolve()),
        "launch_receipt_sha256": sha256(launch_receipt_path) if launch_receipt_path.is_file() else None,
        "launch_environment": preflight.get("launch_environment"),
    })
    receipt["execution_layout"] = _execution_layout(preflight, stage, receipt)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def run(arm: str, out: Path, duration: int, execute: bool, safety_fraction: float,
        candidate_build_path: Path | None = None,
        disk_reference_receipt_path: Path | None = None,
        hydro_input_receipt_path: Path | None = None,
        native_input_receipt_path: Path | None = None) -> dict:
    runner_path = Path(__file__).resolve()
    runner_sha256_at_entry = sha256(runner_path)
    schedule = snapshot_schedule(duration)
    out.mkdir(parents=True, exist_ok=False)
    prepared = prepare(arm, duration, out, safety_fraction, candidate_build_path,
                       disk_reference_receipt_path, hydro_input_receipt_path,
                       native_input_receipt_path)
    (out / "preflight.json").write_text(json.dumps({k: v for k, v in prepared.items()
                                                     if k != "namelist_text"}, indent=2) + "\n")
    if prepared["disk_guard"]["status"] != "PASS":
        raise RuntimeError(f"{arm}: active-run disk guard failed; executable not launched")
    if not execute:
        return {k: v for k, v in prepared.items() if k not in {"namelist_text", "input_hashes"}}
    stage = _stage(prepared, out)
    verify_staged_inputs(prepared, stage)
    candidate_build = prepared.get("candidate_build")
    expected_executable_sha256 = (candidate_build["executable_sha256"] if candidate_build
                                  else prepared["executable_sha256"])
    executed_executable_sha256 = sha256(stage / "wrf.exe")
    if executed_executable_sha256 != expected_executable_sha256:
        raise RuntimeError("staged executable hash differs from preflight")
    if candidate_build and _candidate_build_binding(Path(candidate_build["receipt_path"])) != candidate_build:
        raise RuntimeError("candidate build identity changed after preflight")
    candidate_input = prepared.get("candidate_input_binding")
    if not _input_binding_unchanged(candidate_input):
        raise RuntimeError("source-bound input identity changed after preflight")
    launch_provenance = {"launch_runner_source_path": str(runner_path),
                         "launch_runner_source_sha256": runner_sha256_at_entry,
                         "diagnostic_environment": prepared["diagnostic_environment"]}
    (out / "launch_provenance.json").write_text(json.dumps(launch_provenance, indent=2) + "\n")
    pr87_probe = os.environ.get("PR87_PROBE")
    command = ["/bin/bash", "-c", f". /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh --force >/dev/null 2>&1; . /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1; export OMP_NUM_THREADS={LAUNCH_ENVIRONMENT['OMP_NUM_THREADS']} OMP_DYNAMIC={LAUNCH_ENVIRONMENT['OMP_DYNAMIC']}; export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:${{LD_LIBRARY_PATH:-}}; ulimit -s unlimited; ./wrf.exe > candidate_run.log 2>&1"]
    start = time.monotonic()
    with (stage / "launcher.stdout").open("wb") as stdout, (stage / "launcher.stderr").open("wb") as stderr:
        process = subprocess.run(command, cwd=stage, stdout=stdout, stderr=stderr, check=False,
                                 env={**os.environ, **prepared["diagnostic_environment"]})
    elapsed = time.monotonic() - start
    processing_errors = []
    try:
        times = _model_times(stage)
    except Exception as exc:
        times = []
        processing_errors.append(f"model time parsing: {exc}")
    fatal, fatal_scan_issues = _fatal_lines(stage)
    processing_errors.extend(fatal_scan_issues)
    trace = stage / "pr85_joint_moment_stages.raw"
    try:
        snapshots = read_time_snapshots(trace, duration) if trace.is_file() else {
            "record_count": 0, "timesteps": [], "completed_post_kdm6_timesteps": [],
            "duplicate_post_kdm6_timesteps": [], "snapshots": {}}
    except Exception as exc:
        snapshots = {"record_count": 0, "timesteps": [],
                     "completed_post_kdm6_timesteps": [],
                     "duplicate_post_kdm6_timesteps": [], "snapshots": {}}
        processing_errors.append(f"snapshot parsing: {exc}")
    try:
        compressed = _compress_closed(stage)
    except Exception as exc:
        compressed = []
        processing_errors.append(f"post-run compression: {exc}")
    generated_files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                       for path in sorted(stage.iterdir()) if path.is_file()]
    inputs = prepared["input_hashes"]
    stage_hashes = {name: sha256(stage / name) for name in inputs
                    if name not in {"namelist.input", "namelist.input.source"}}
    stage_hashes["namelist.input"] = sha256(stage / "namelist.input")
    stage_hashes["namelist.input.source"] = sha256(stage / "namelist.input.source")
    changed_stage = [name for name, digest in stage_hashes.items()
                     if digest != _staged_expected_hash(
                         name, inputs, candidate_build, prepared["candidate_namelist_sha256"],
                         prepared["candidate_wrfinput_sha256"])]
    original_after = {name: sha256(Path(prepared["runtime_dir"]) / name) for name in inputs}
    changed_original = [name for name, digest in original_after.items() if digest != inputs[name]]
    start_time = dt.datetime(2026, 8, 16, 13)
    expected_times = [(start_time + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                      for step in range(1, duration // 20 + 1)]
    actual_times = [row["timestamp"] for row in times]
    completed_steps = snapshots.get("completed_post_kdm6_timesteps", [])
    duplicate_post = snapshots.get("duplicate_post_kdm6_timesteps", [])
    candidate_build_unchanged = True
    if candidate_build:
        try:
            candidate_build_unchanged = (
                _candidate_build_binding(Path(candidate_build["receipt_path"])) == candidate_build)
        except Exception as exc:
            candidate_build_unchanged = False
            processing_errors.append(f"candidate build validation: {exc}")
    try:
        candidate_input_unchanged = _input_binding_unchanged(candidate_input)
    except (OSError, ValueError, KeyError) as exc:
        candidate_input_unchanged = False
        processing_errors.append(f"source-bound input binding validation: {exc}")
    complete = (process.returncode == 0 and actual_times == expected_times and
                completed_steps == list(range(1, duration // 20 + 1)) and not duplicate_post and not fatal and
                not processing_errors and not changed_stage and not changed_original and
                sha256(Path(prepared["source_receipt"])) == prepared["source_receipt_sha256"] and
                executed_executable_sha256 == expected_executable_sha256 and
                candidate_build_unchanged and candidate_input_unchanged and
                set(schedule.values()).issubset(snapshots.get("snapshots", {})))
    receipt = {"arm": arm, "status": "COMPLETE" if complete else "INCOMPLETE",
               "run_identity": ("PR87 selected-object native candidate" if candidate_build
                                else "PR86 frozen executable run"),
               "returncode": process.returncode, "wall_seconds": elapsed, "model_timestamps": times,
               "timestep_count": len(times), "earliest_fatal": fatal[0] if fatal else None,
               "fatal_lines": fatal[:100], "snapshots": snapshots,
               "maximum_seen_timestep": max(snapshots["timesteps"]) if snapshots["timesteps"] else None,
               "final_completed_step": max(completed_steps) if completed_steps else None,
               "duplicate_post_kdm6_timesteps": duplicate_post,
               "expected_model_timestamps": expected_times,
               "changed_staged_inputs": changed_stage, "changed_original_inputs": changed_original,
               "source_inputs_after_sha256": original_after, "processing_errors": processing_errors,
               "frozen_executable_sha256": prepared["executable_sha256"],
               "baseline_frozen_executable_sha256": prepared["baseline_frozen_executable_sha256"],
               "executed_executable_sha256": executed_executable_sha256,
               "expected_executed_executable_sha256": expected_executable_sha256,
               "candidate_build": candidate_build, "candidate_build_unchanged": candidate_build_unchanged,
               "candidate_input_binding": candidate_input,
               "candidate_input_unchanged": candidate_input_unchanged,
               "launch_runner_source_path": str(runner_path),
               "launch_runner_source_sha256": runner_sha256_at_entry,
               "launch_runner_source_sha256_status": "captured at run entry before model execution",
               "pr87_probe": pr87_probe,
               "diagnostic_environment": prepared["diagnostic_environment"],
               "source_receipt_sha256": prepared["source_receipt_sha256"],
               "candidate_wrfinput_sha256": prepared["candidate_wrfinput_sha256"],
               "candidate_wrfbdy_sha256": prepared["candidate_wrfbdy_sha256"],
               "candidate_namelist_sha256": prepared["candidate_namelist_sha256"],
               "launch_environment": prepared["launch_environment"],
               "generated_files": generated_files, "compressed_outputs": compressed}
    receipt["execution_layout"] = _execution_layout(prepared, stage, receipt)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "COUPLED"), required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--execute", action="store_true", help="launch after hash and disk checks")
    parser.add_argument("--finalize", action="store_true", help="receipt a completed run directory without relaunch")
    parser.add_argument("--candidate-build", type=Path,
                        help="explicit PR87 overlay build receipt; default uses frozen PR86 executable")
    parser.add_argument("--hydro-input-receipt", type=Path,
                        help="source-bound HYDRO native input; OFF ancillary template remains immutable")
    parser.add_argument("--native-input-receipt", type=Path,
                        help="source-bound PR99 COUPLED native input proposal")
    parser.add_argument("--safety-fraction", type=float, default=0.85)
    parser.add_argument("--disk-reference-receipt", type=Path,
                        help="calibrate the disk guard from a successful same-input run receipt")
    args = parser.parse_args()
    try:
        snapshot_schedule(args.duration_seconds)
    except ValueError as exc:
        parser.error(f"--duration-seconds {exc}")
    if args.finalize and args.hydro_input_receipt is not None:
        parser.error("--finalize uses the launch-bound HYDRO receipt in preflight.json")
    if args.finalize and args.native_input_receipt is not None:
        parser.error("--finalize uses the launch-bound native input receipt in preflight.json")
    out = args.output or DEFAULT_OUT / args.arm
    result = (finalize_existing_run(args.arm, out, args.duration_seconds, args.candidate_build) if args.finalize else
              run(args.arm, out, args.duration_seconds, args.execute, args.safety_fraction,
                  args.candidate_build, args.disk_reference_receipt, args.hydro_input_receipt,
                  args.native_input_receipt))
    print(json.dumps({k: v for k, v in result.items() if k != "input_hashes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
