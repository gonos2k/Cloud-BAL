#!/usr/bin/env python3
"""Reduce a closed PR101 projected run against the matched C2 controls."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

import pr94_cloud_response as cloud
import pr86_compare_response as history
from native_kdm6_trace import read_dump
from pr86_time_response import STATE_FIELDS, STATE_MAGIC, TENDENCY_MAGIC


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
CONTROL_ROOT = ROOT / "pr99_c2_matched640_20261022"
P20_ROOT = ROOT / "pr99_native_uv20_capture_20261022/run"
EXPECTED_EXE = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
EXPECTED_BOUNDARY = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"
EXPECTED_NAMELIST = "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8"
EXPECTED_RUNNER = "087f9f3a9f80f5679db7c228d99dde269200028d823553e0a2045a855cbba439"
EXPECTED_INPUT = "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3"
EXPECTED_PROPOSAL = "a6fdd4907228b6bcd95d2eba3e61539adcedf69c0154c23a9e1a2edeb6c6b5d0"
EXPECTED_BUILD = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
EXPECTED_COMPOSITION = "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64"
REVIEWED_PREFLIGHT = Path(__file__).resolve().parents[1] / "docs/evidence/pr101_projected_c2_20261023/preflight.json"
REVIEWED_PREFLIGHT_SHA = "61578f2627bfc3dcc55d7fcf61c56ebf65d611a5fc1896445ff9fda988cbf3fb"
EXPECTED_TIMESTAMPS = [
    (dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
    for step in range(1, 33)]
SELECTED_FIELDS = ("Q", "QC", "QI", "QR", "QS", "QG")
PR99_C2_AUDIT_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_closed_receipt(receipt: dict, preflight: dict, arm: str) -> None:
    times = [row.get("timestamp") for row in receipt.get("model_timestamps", [])]
    if (receipt.get("arm") != arm or preflight.get("arm") != arm
            or receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0
            or receipt.get("timestep_count") != 32 or receipt.get("final_completed_step") != 32
            or receipt.get("maximum_seen_timestep") != 32
            or receipt.get("expected_model_timestamps") != EXPECTED_TIMESTAMPS
            or times != EXPECTED_TIMESTAMPS or receipt.get("earliest_fatal") is not None
            or receipt.get("candidate_build_unchanged") is not True
            or receipt.get("candidate_input_unchanged") is not True
            or receipt.get("processing_errors") != [] or receipt.get("fatal_lines") != []
            or receipt.get("changed_staged_inputs") != []
            or receipt.get("changed_original_inputs") != []
            or receipt.get("duplicate_post_kdm6_timesteps") != []):
        raise ValueError(f"{arm} is not a clean closed 640-second receipt")
    if receipt.get("candidate_wrfinput_sha256") != preflight.get("candidate_wrfinput_sha256"):
        raise ValueError(f"{arm} candidate input differs from its receipt preflight")
    if (preflight.get("duration_seconds") != 640 or preflight.get("expected_timesteps") != 32
            or receipt.get("candidate_wrfbdy_sha256") != EXPECTED_BOUNDARY
            or receipt.get("candidate_namelist_sha256") != EXPECTED_NAMELIST
            or receipt.get("executed_executable_sha256") != EXPECTED_EXE):
        raise ValueError(f"{arm} receipt differs from matched C2 run controls")


def _require_supervisor_closed() -> None:
    launch = load_json(Path("/var/tmp/pr101_projected_c2_launch_20261023/launch.json"))
    pid = launch.get("runner_pid")
    if not isinstance(pid, int):
        raise ValueError("launch receipt has no supervisor PID")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise ValueError("cannot verify PR101 supervisor termination") from exc
    raise ValueError(f"PR101 runner PID {pid} is still live; do not read run artifacts")


def _closed_run(run_root: Path, expected_arm: str) -> tuple[dict, dict]:
    receipt_path, preflight_path = run_root / "receipt.json", run_root / "preflight.json"
    if not receipt_path.is_file() or not preflight_path.is_file():
        raise ValueError(f"closed receipt is missing under {run_root}")
    receipt, preflight = load_json(receipt_path), load_json(preflight_path)
    validate_closed_receipt(receipt, preflight, expected_arm)
    return receipt, preflight


def _validate_reviewed_control(arm: str, run_root: Path, receipt: dict,
                               preflight: dict, reviewed: dict) -> None:
    pin = reviewed.get("matched_controls", {}).get(arm)
    receipt_path, preflight_path = run_root / "receipt.json", run_root / "preflight.json"
    if (not pin or sha256(receipt_path) != pin.get("receipt_sha256")
            or sha256(preflight_path) != pin.get("preflight_sha256")
            or receipt.get("candidate_wrfinput_sha256") != pin.get("candidate_wrfinput_sha256")
            or preflight.get("candidate_wrfinput_sha256") != pin.get("candidate_wrfinput_sha256")):
        raise ValueError(f"{arm} closed control differs from reviewed PR101 receipt/preflight/input pins")


def _single_layout(receipt: dict) -> bool:
    layout = receipt.get("execution_layout", {})
    return (layout.get("status") == "VERIFIED_SINGLE"
            and layout.get("single_execution_layout") is True
            and layout.get("mpi_rank_count") == 1
            and layout.get("tiles_per_domain") == 1
            and layout.get("threads") == 1)


def _trace_receipt_row(receipt: dict) -> dict:
    compressed = next((row for row in receipt.get("compressed_outputs", [])
                       if row.get("path") == "pr85_joint_moment_stages.raw"), None)
    if not compressed:
        raise ValueError("closed receipt lacks the joint-stage trace artifact")
    generated = next((row for row in receipt.get("generated_files", [])
                      if row.get("path") == compressed.get("compressed_path")), None)
    if (not generated or generated.get("sha256") != compressed.get("compressed_sha256")
            or generated.get("bytes") != compressed.get("compressed_bytes")):
        raise ValueError("compressed trace inventory differs from closed receipt")
    return compressed


def _trace_row(run_root: Path, receipt: dict) -> tuple[Path, dict]:
    compressed = _trace_receipt_row(receipt)
    path = run_root / "run" / compressed["compressed_path"]
    if not path.is_file() or sha256(path) != compressed["compressed_sha256"]:
        raise ValueError("closed joint-stage trace compressed artifact changed")
    return path, compressed


def _state_field_kji(raw: bytes, shape_kji: tuple[int, int, int]) -> np.ndarray:
    """Decode Fortran trace storage (J,K,I) into the fixed masks' (K,J,I)."""
    nz, ny, nx = shape_kji
    expected = nz * ny * nx * 4
    if len(raw) != expected:
        raise ValueError("state field payload size differs from trace geometry")
    return np.frombuffer(raw, dtype=">f4").reshape((ny, nz, nx)).transpose(1, 0, 2)


def _crop_active_grid(values: np.ndarray, active_shape: tuple[int, int, int]) -> np.ndarray:
    if values.shape == active_shape:
        return values
    full_shape = (active_shape[0], active_shape[1] + 2, active_shape[2] + 2)
    if values.shape == full_shape:
        return values[:, 1:-1, 1:-1]
    raise ValueError(f"trace grid {values.shape} differs from active grid {active_shape}")


def _read_fixed_trace(path: Path, raw_row: dict, timesteps: set[int],
                      support: np.ndarray, buffer: np.ndarray) -> dict[int, dict]:
    results, completed, duplicates = {}, set(), set()
    digest, byte_count = hashlib.sha256(), 0
    with gzip.open(path, "rb") as stream:
        while magic := stream.read(8):
            label_raw, header = stream.read(32), stream.read(60)
            if len(label_raw) != 32 or len(header) != 60:
                raise ValueError("truncated closed joint-stage record header")
            label = label_raw.decode("ascii").strip()
            values = struct.unpack(">15i", header)
            kind, step, _rkstep = values[:3]
            if (kind != (1 if magic == STATE_MAGIC else 2 if magic == TENDENCY_MAGIC else -1)
                    or step <= 0):
                raise ValueError("invalid closed joint-stage record identity")
            bounds = values[3:]
            its, ite, jts, jte, kts, kte = bounds[6], bounds[7], bounds[8], bounds[9], bounds[10], bounds[11]
            shape = (kte - kts + 1, jte - jts + 1, ite - its + 1)
            cells = int(np.prod(shape))
            if shape not in (support.shape, (support.shape[0], support.shape[1] + 2,
                                               support.shape[2] + 2)) or buffer.shape != support.shape:
                raise ValueError(f"trace grid {shape} differs from fixed support {support.shape}")
            digest.update(magic + label_raw + header)
            byte_count += 100
            selected = magic == STATE_MAGIC and label == "POST_KDM6" and step in timesteps
            fields = {}
            names = STATE_FIELDS if magic == STATE_MAGIC else ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
            for name in names:
                raw = stream.read(cells * 4)
                if len(raw) != cells * 4:
                    raise ValueError(f"truncated {label} {name} payload at step {step}")
                digest.update(raw)
                byte_count += len(raw)
                if selected and name in SELECTED_FIELDS:
                    array = _crop_active_grid(_state_field_kji(raw, shape), support.shape)
                    fields[name] = {"support": array[support].astype(np.float64),
                                    "buffer": array[buffer].astype(np.float64)}
            if magic == STATE_MAGIC and label == "POST_KDM6":
                if step in completed:
                    duplicates.add(step)
                completed.add(step)
                if selected:
                    if step in results:
                        raise ValueError(f"duplicate selected POST_KDM6 snapshot {step}")
                    results[step] = fields
    if (digest.hexdigest() != raw_row["sha256"] or byte_count != raw_row["bytes"]
            or duplicates or not timesteps.issubset(completed) or timesteps != set(results)):
        raise ValueError("joint-stage trace does not match its closed receipt or milestones")
    return results


def _read_projected_trace_and_policy(run_root: Path, receipt: dict,
                                     support: np.ndarray, buffer: np.ndarray,
                                     selected_timesteps: set[int]) -> tuple[dict, dict]:
    sys.path.insert(0, str(PR99_C2_AUDIT_ROOT / "tools"))
    import pr98_boundary_audit as c1_audit

    c1_audit.verify_reader_pins()
    auditor = c1_audit.load_closed_auditor()
    closed_receipt, receipt_path = auditor.closed_receipt(run_root, "PROJECTED")
    if closed_receipt != receipt:
        raise ValueError("PROJECTED closed auditor read a different receipt")
    prefix = auditor.derive_prefix(receipt, "PROJECTED")
    trace_row = auditor.output_row(receipt, auditor.TRACE_NAME, "PROJECTED")
    trace_path = run_root / "run" / trace_row["compressed_path"]
    policy = auditor.stage_trace._load_policy()
    state_rows, active_rows, exact_rows, predictor_rows, qnb_rows = {}, [], [], [], []
    responses = {}
    for record in auditor._trace_records(trace_path, trace_row, "PROJECTED", set(prefix)):
        step = record["timestep"]
        if step not in prefix:
            continue
        fields = record["fields"]
        if fields is None or record["density_contract_status"] != "AUTHORITATIVE_DRY_FROM_AL_ALB":
            raise ValueError("PROJECTED completed trace record lacks authoritative source fields")
        state_rows.setdefault(step, []).append((record["stage"], record["rkstep"]))
        conversion = auditor.completed_audit._stage_violations(record, policy)
        qnb_rows.append({"timestep": step, "stage": record["stage"], "rkstep": record["rkstep"],
                         "violations": conversion["violations"],
                         "mass_moment_pairs": conversion["pairs"],
                         "number_conversion": conversion["number_conversion"]})
        ice = auditor.ice_policy_split(fields, policy)
        active_rows.append({"timestep": step, "stage": record["stage"], "rkstep": record["rkstep"], **ice})
        source = auditor.completed_audit._strict_source_checks(fields)
        row = {"timestep": step, "stage": record["stage"], "rkstep": record["rkstep"],
               "violations": auditor.completed_audit._strict_source_violations(source),
               "diagnostic_ice_exact_counts": source["ice_diagnostic"]["counts"]}
        (exact_rows if (record["stage"], record["rkstep"]) in auditor.ENDPOINT_STAGES
         else predictor_rows).append(row)
        if record["stage"] == "POST_KDM6" and step in selected_timesteps:
            kji_fields = {name: _crop_active_grid(values.transpose(1, 0, 2), support.shape)
                          for name, values in fields.items()
                          if name in SELECTED_FIELDS}
            if set(kji_fields) != set(SELECTED_FIELDS):
                raise ValueError("PROJECTED POST_KDM6 trace lacks required water species")
            responses[step] = {name: {"support": values[support].astype(np.float64),
                                      "buffer": values[buffer].astype(np.float64)}
                               for name, values in kji_fields.items()}
    expected = tuple(zip(auditor.STATE_SEQUENCE, (0, 1, 2, 3, 0, 0), strict=True))
    if (list(state_rows) != prefix or any(tuple(state_rows[step]) != expected for step in prefix)
            or set(responses) != selected_timesteps):
        raise ValueError("PROJECTED trace state sequence or selected POST_KDM6 milestones differ from closure")
    ice_row = auditor.output_row(receipt, auditor.ICE_LEDGER_NAME, "PROJECTED")
    ice_path = run_root / "run" / ice_row["compressed_path"]
    ledger = auditor.exact_psd_ledger(ice_path, ice_row, "PROJECTED")
    exact_failures = [row for row in exact_rows if row["violations"]]
    qnb_failures = [row for row in qnb_rows if any(row["violations"].values())]
    policy_report = {
        "reader_pins": c1_audit.verify_reader_pins(),
        "exact_source_endpoint": {"status": "FAIL" if exact_failures else "PASS",
                                   "scope": "Frozen PR93 RK3/PRE_KDM6/POST_KDM6 exact endpoint predicates; predictor states remain diagnostic.",
                                   "failures": exact_failures, "predictor_diagnostics": predictor_rows},
        "active_ice_policy_split": {"status": "FAIL" if any(row["policy_status"] == "FAIL" for row in active_rows) else "PASS",
                                    "scope": "Frozen PR93 eight-ULP active ice policy with inactive positive pairs reported separately, all completed state records.",
                                    "per_state": active_rows},
        "generic_qnb_pair_conversion": {"status": "FAIL" if qnb_failures else "PASS",
                                        "scope": "Frozen PR93 generic Q/N/B pair, PSD cone, and dry-density conversion audit per completed state.",
                                        "failure_count": len(qnb_failures), "per_state": qnb_rows},
        "ice_sedimentation_ledger": ledger,
        "trace_identity": {"compressed_sha256": trace_row["compressed_sha256"],
                           "expanded_sha256": trace_row["sha256"], "expanded_bytes": trace_row["bytes"]},
    }
    return responses, policy_report


def _metrics(current: np.ndarray, reference: np.ndarray) -> dict:
    if (current.shape != reference.shape or not np.isfinite(current).all()
            or not np.isfinite(reference).all()):
        raise ValueError("response arrays must share finite support")
    delta = current - reference
    return {"count": int(delta.size), "signed_sum": float(np.sum(delta, dtype=np.float64)),
            "rms": float(np.sqrt(np.mean(delta * delta))),
            "l1": float(np.sum(np.abs(delta), dtype=np.float64)),
            "max_abs": float(np.max(np.abs(delta)))}


def _expand_bound_trace(run_root: Path, receipt: dict, name: str, directory: Path) -> tuple[Path, dict]:
    row = next((item for item in receipt.get("compressed_outputs", [])
                if item.get("path") == name), None)
    if row is None:
        raise ValueError(f"closed receipt lacks {name}")
    compressed_path = run_root / "run" / row["compressed_path"]
    if not compressed_path.is_file() or sha256(compressed_path) != row["compressed_sha256"]:
        raise ValueError(f"compressed first-call artifact changed: {name}")
    output = directory / name
    digest, size = hashlib.sha256(), 0
    with gzip.open(compressed_path, "rb") as source, output.open("wb") as target:
        while block := source.read(1024 * 1024):
            digest.update(block)
            size += len(block)
            target.write(block)
    if digest.hexdigest() != row["sha256"] or size != row["bytes"]:
        raise ValueError(f"expanded first-call artifact differs from closed receipt: {name}")
    return output, row


def _compare_first_call(run_root: Path, receipt: dict) -> dict:
    p20_receipt_path = P20_ROOT / "receipt.json"
    p20_preflight_path = P20_ROOT / "preflight.json"
    p20_receipt, p20_preflight = load_json(p20_receipt_path), load_json(p20_preflight_path)
    if (p20_receipt.get("status") != "COMPLETE" or p20_receipt.get("returncode") != 0
            or p20_receipt.get("arm") != "COUPLED" or p20_preflight.get("duration_seconds") != 20
            or p20_receipt.get("timestep_count") != 1 or p20_receipt.get("final_completed_step") != 1
            or p20_receipt.get("candidate_wrfinput_sha256") != EXPECTED_INPUT
            or p20_preflight.get("candidate_wrfinput_sha256") != EXPECTED_INPUT
            or p20_preflight.get("candidate_input_binding", {}).get("receipt_sha256") != EXPECTED_PROPOSAL):
        raise ValueError("P20 reference is not a closed one-step capture of this exact projected input")
    roots = {"P20": P20_ROOT, "PROJECTED_C2": run_root}
    receipts = {"P20": p20_receipt, "PROJECTED_C2": receipt}
    comparisons = {}
    with tempfile.TemporaryDirectory(prefix="pr101_c2_firstcall_") as temp:
        work = Path(temp)
        for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"):
            loaded = {}
            for arm in roots:
                path, _identity = _expand_bound_trace(roots[arm], receipts[arm], name, work)
                loaded[arm] = read_dump(path)
                if loaded[arm]["stage"] != (1 if name.endswith("pre.raw") else 2) or loaded[arm]["itimestep"] != 1:
                    raise ValueError(f"{arm} {name} is not the first KDM6 call")
            p20, c2 = loaded["P20"], loaded["PROJECTED_C2"]
            same_header = (p20["bounds"] == c2["bounds"] and p20["params"] == c2["params"]
                           and p20["active_shape_xyz"] == c2["active_shape_xyz"])
            differing_fields = [field for field in p20["fields"]
                                if field not in c2["fields"] or not np.array_equal(p20["fields"][field], c2["fields"][field])]
            p20_hash = next(row["sha256"] for row in p20_receipt["compressed_outputs"] if row["path"] == name)
            c2_hash = next(row["sha256"] for row in receipt["compressed_outputs"] if row["path"] == name)
            comparisons[name] = {"P20_uncompressed_sha256": p20_hash,
                                 "PROJECTED_C2_uncompressed_sha256": c2_hash,
                                 "byte_identical": p20_hash == c2_hash,
                                 "header_identical": same_header,
                                 "array_identical": not differing_fields,
                                 "differing_fields": differing_fields}
        pr67_name = "pr67_kdm6_process.raw"
        p20_rows = [row for row in p20_receipt.get("compressed_outputs", []) if row.get("path") == pr67_name]
        c2_rows = [row for row in receipt.get("compressed_outputs", []) if row.get("path") == pr67_name]
        if p20_rows and c2_rows:
            comparisons[pr67_name] = {"P20_uncompressed_sha256": p20_rows[0]["sha256"],
                                      "PROJECTED_C2_uncompressed_sha256": c2_rows[0]["sha256"],
                                      "byte_identical": p20_rows[0]["sha256"] == c2_rows[0]["sha256"],
                                      "comparison": "raw payload hash only; format not interpreted"}
        else:
            comparisons[pr67_name] = {"status": "NOT_PRESENT_IN_BOTH_CLOSED_RECEIPTS"}
    exact = all(comparisons[name]["byte_identical"] and comparisons[name]["header_identical"]
                and comparisons[name]["array_identical"]
                for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"))
    same_executable = (p20_receipt.get("executed_executable_sha256") ==
                       receipt.get("executed_executable_sha256"))
    return {"status": ("EXACT_EXECUTION_IDENTITY" if exact and same_executable else
                        "EXACT_STATE_MATCH_DIFFERENT_EXECUTABLE" if exact else
                        "FIRST_CALL_DIFFERENCE"),
            "P20_receipt_path": str(p20_receipt_path), "P20_receipt_sha256": sha256(p20_receipt_path),
            "P20_executable_sha256": p20_receipt.get("executed_executable_sha256"),
            "PROJECTED_C2_executable_sha256": receipt.get("executed_executable_sha256"),
            "same_executable": same_executable,
            "same_projected_input_sha256": EXPECTED_INPUT,
            "artifacts": comparisons,
            "interpretation": ("P20 pre/post KDM6 arrays exactly match the C2 P first-call arrays, but the executable hashes differ; this is cross-executable state identity only." if exact and not same_executable else
                               "P20 pre/post KDM6 captures match the first call in the same executable." if exact else
                               "Keep P20 and C2 P evidence separate; the earlier P20 capture does not establish the C2 P first-call state. No cross-build validation is inferred.")}


def _closed_history_index(run_root: Path, receipt: dict) -> tuple[dict, dict]:
    expected_files = {row["path"]: row for row in receipt.get("generated_files", [])
                      if row.get("path", "").startswith("wrfout_d01_")}
    if not expected_files:
        raise ValueError("closed receipt has no generated history artifacts")
    for name, row in expected_files.items():
        path = run_root / "run" / name
        if not path.is_file() or path.stat().st_size != row["bytes"]:
            raise ValueError(f"history artifact differs from closed receipt: {name}")
    index, identities = history.history_index(run_root / "run")
    if {Path(path).name for path in identities} != set(expected_files):
        raise ValueError("closed history directory differs from receipt inventory")
    if any(identities[str(run_root / "run" / name)]["sha256"] != row["sha256"]
           for name, row in expected_files.items()):
        raise ValueError("closed history hash differs from receipt inventory")
    coverage = history.history_coverage(set(index), set(index))
    if not coverage["complete"]:
        raise ValueError("history does not contain common 0..600-second minute records")
    return index, identities


def _history_response(roots: dict[str, Path], receipts: dict[str, dict], masks: dict) -> dict:
    indexes, identities = {}, {}
    for arm, root in roots.items():
        indexes[arm], identities[arm] = _closed_history_index(root, receipts[arm])
    times = history.history_coverage(set(indexes["PROJECTED"]), set(indexes["COUPLED"]))
    if not times["complete"]:
        raise ValueError("PROJECTED and original COUPLED history times are not identical at 0..600 seconds")
    regions = {name: masks[name] for name in ("original_613_native_support", "fixed_5_cell_chebyshev_buffer")}
    zero_stamp = history.START.strftime("%Y-%m-%d_%H:%M:%S")
    initial_fields = {}
    for arm, index in indexes.items():
        _, fields, _ = history.load_history(*index[zero_stamp])
        initial_fields[arm] = {field: {name: values[mask].astype(np.float64)
                                      for name, mask in regions.items()}
                               for field, values in fields.items()}
    del fields
    stored, face_records = {}, {}
    for seconds in range(0, 601, 60):
        stamp = (history.START + history.dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d_%H:%M:%S")
        loaded = {}
        for arm, index in indexes.items():
            if stamp not in index:
                raise ValueError(f"{arm} history is missing {stamp}")
            timestamp, fields, _meta = history.load_history(*index[stamp])
            if timestamp != stamp:
                raise ValueError(f"{arm} history frame timestamp differs from {stamp}")
            loaded[arm] = fields
        stored[seconds] = {}
        compare_fields = ("pressure", "geopotential", "T", "QVAPOR", "QCLOUD", "QICE",
                          "QRAIN", "QSNOW", "QGRAUP", "U", "V", "W")
        for reference_arm in ("OFF", "HYDRO", "COUPLED"):
            pair = {}
            for field in compare_fields:
                left = loaded["PROJECTED"][field]
                right = loaded[reference_arm][field]
                if left.shape != (39, 280, 232) or right.shape != left.shape:
                    raise ValueError(f"{field} history has unexpected active-grid shape")
                pair[field] = {}
                for name, mask in regions.items():
                    projected_values = left[mask].astype(np.float64)
                    reference_values = right[mask].astype(np.float64)
                    metric = _metrics(projected_values, reference_values)
                    metric.update({"reference_rms": float(np.sqrt(np.mean(reference_values**2))),
                                   "projected_rms": float(np.sqrt(np.mean(projected_values**2)))})
                    if field in {"QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP"}:
                        baseline = (initial_fields["PROJECTED"][field][name] -
                                    initial_fields[reference_arm][field][name])
                        metric.update(cloud.pattern_metrics(baseline,
                                                            projected_values - reference_values))
                    pair[field][name] = {"unit": ("Pa" if field == "pressure" else
                                                    "m2 s-2" if field == "geopotential" else
                                                    "K perturbation potential temperature" if field == "T" else
                                                    "m s-1" if field in {"U", "V", "W"} else "kg/kg dry"),
                                         "selected_values": int(mask.sum()), **metric}
            stored[seconds][f"PROJECTED_minus_{reference_arm}"] = pair
        if seconds in (0, 60, 600):
            raw_faces = {arm: cloud.read_face_winds(*indexes[arm][stamp]) for arm in indexes}
            face_records[seconds] = {}
            for reference_arm in ("OFF", "HYDRO", "COUPLED"):
                face_records[seconds][f"PROJECTED_minus_{reference_arm}"] = {}
                for field in ("U_face", "V_face", "W_face"):
                    delta = raw_faces["PROJECTED"][field] - raw_faces[reference_arm][field]
                    face_records[seconds][f"PROJECTED_minus_{reference_arm}"][field] = {
                        "unit": "m s-1", "shape": list(delta.shape),
                        "rms": float(np.sqrt(np.mean(delta.astype(np.float64) ** 2))),
                        "max_abs": float(np.max(np.abs(delta))),
                        "signed_sum": float(np.sum(delta, dtype=np.float64))}
    for arm, root in roots.items():
        for path, identity in identities[arm].items():
            if sha256(Path(path)) != identity["sha256"]:
                raise ValueError(f"{arm} history changed during response analysis")
    return {"records": stored, "raw_staggered_face_diagnostics": face_records,
            "history_artifacts": identities,
            "scope": "Common saved times 0..600 seconds only. T is perturbation potential temperature; U/V/W face diagnostics remain staggered and separately reported."}


def analyze(run_root: Path) -> dict:
    _require_supervisor_closed()
    receipt, preflight = _closed_run(run_root, "PROJECTED")
    if not _single_layout(receipt):
        raise ValueError("PROJECTED run layout differs from reviewed single-rank policy")
    if sha256(REVIEWED_PREFLIGHT) != REVIEWED_PREFLIGHT_SHA:
        raise ValueError("reviewed PR101 preflight evidence changed")
    reviewed = load_json(REVIEWED_PREFLIGHT)
    controls = {}
    for arm in ("OFF", "HYDRO", "COUPLED"):
        root = CONTROL_ROOT / arm
        control_receipt, control_preflight = _closed_run(root, arm)
        _validate_reviewed_control(arm, root, control_receipt, control_preflight, reviewed)
        controls[arm] = (control_receipt, control_preflight)
        if (control_receipt.get("executed_executable_sha256") != receipt.get("executed_executable_sha256")
                or control_receipt.get("candidate_wrfbdy_sha256") != receipt.get("candidate_wrfbdy_sha256")
                or control_receipt.get("candidate_namelist_sha256") != receipt.get("candidate_namelist_sha256")
                or control_receipt.get("launch_environment") != receipt.get("launch_environment")
                or not _single_layout(control_receipt)):
            raise ValueError(f"{arm} control does not match PROJECTED executable, boundary, namelist, and FP environment")
    binding = preflight.get("candidate_input_binding")
    if (preflight.get("template_arm") != "COUPLED" or not binding
            or binding.get("binding_kind") != "native_uv_projection"
            or binding.get("receipt_sha256") != EXPECTED_PROPOSAL
            or receipt.get("candidate_wrfinput_sha256") != EXPECTED_INPUT
            or preflight.get("candidate_build", {}).get("receipt_sha256") != EXPECTED_BUILD
            or receipt.get("launch_runner_source_sha256") != EXPECTED_RUNNER):
        raise ValueError("PROJECTED receipt input/build/runner provenance differs from reviewed preflight")
    firstcall_response = _compare_first_call(run_root, receipt)
    composition_path = Path(binding["artifacts"]["composition"]["path"])
    comp = load_json(composition_path)
    if (sha256(composition_path) != EXPECTED_COMPOSITION
            or binding.get("composition_sha256") != EXPECTED_COMPOSITION):
        raise ValueError("PR99 fixed-support composition identity changed")
    masks = cloud.make_masks(comp["composed_qc_vertical_influence"], (39, 280, 232))
    support, buffer = masks["original_613_native_support"], masks["fixed_5_cell_chebyshev_buffer"]
    if (int(support.sum()) != 613 or int(buffer.any(axis=0).sum()) != 196
            or int(buffer.sum()) != 39 * 196):
        raise ValueError("PR99 fixed 613-cell support or 196-column buffer identity changed")
    selected_times = {int(step) for step in receipt["snapshots"]["completed_post_kdm6_timesteps"]
                      if step in {1, 3, 15, 16, 24, 25, 30, 32}}
    if selected_times != {1, 3, 15, 16, 24, 25, 30, 32}:
        raise ValueError("PROJECTED closed receipt lacks selected response milestones")
    arms = {name: (CONTROL_ROOT / name, item[0]) for name, item in controls.items()}
    roots = {"PROJECTED": run_root, **{arm: value[0] for arm, value in arms.items()}}
    closed_receipts = {"PROJECTED": receipt, **{arm: value[1] for arm, value in arms.items()}}
    history_response = _history_response(roots, closed_receipts, masks)
    selected_times = {int(step) for step in receipt["snapshots"]["completed_post_kdm6_timesteps"]
                      if step in {1, 3, 15, 16, 24, 25, 30, 32}}
    if selected_times != {1, 3, 15, 16, 24, 25, 30, 32}:
        raise ValueError("PROJECTED closed receipt lacks selected response milestones")
    projected_trace, source_policy = _read_projected_trace_and_policy(
        run_root, receipt, support, buffer, selected_times)
    traces = {"PROJECTED": projected_trace}
    for arm, (root, arm_receipt) in arms.items():
        path, raw_row = _trace_row(root, arm_receipt)
        traces[arm] = _read_fixed_trace(path, raw_row, selected_times, support, buffer)
    comparisons = {}
    for reference_arm in ("OFF", "HYDRO", "COUPLED"):
        rows = {}
        for step in sorted(selected_times):
            rows[step] = {region: {
                field: _metrics(traces["PROJECTED"][step][field][region],
                                traces[reference_arm][step][field][region])
                for field in SELECTED_FIELDS}
                for region in ("support", "buffer")}
        comparisons[f"PROJECTED_minus_{reference_arm}"] = rows
    return {
        "schema": "pr101_projected_c2_closed_response_v1",
        "status": "RECEIPT_CLOSED_FIXED_SUPPORT_RESPONSE",
        "lineage": "PR99 P projected input × C2 executable at 640 s; compared with original PR99 C2 OFF/HYDRO/COUPLED controls",
        "candidate": {"receipt_path": str(run_root / "receipt.json"),
                      "receipt_sha256": sha256(run_root / "receipt.json"),
                      "input_sha256": receipt["candidate_wrfinput_sha256"],
                      "executable_sha256": receipt["executed_executable_sha256"],
                      "namelist_sha256": receipt["candidate_namelist_sha256"],
                      "boundary_sha256": receipt["candidate_wrfbdy_sha256"]},
        "controls": {arm: {"receipt_path": str(CONTROL_ROOT / arm / "receipt.json"),
                            "receipt_sha256": sha256(CONTROL_ROOT / arm / "receipt.json"),
                            "input_sha256": item[0]["candidate_wrfinput_sha256"]}
                      for arm, item in controls.items()},
        "fixed_support": {"composition_path": str(composition_path), "composition_sha256": sha256(composition_path),
                          "support_cells": int(support.sum()), "buffer_columns": int(buffer.any(axis=0).sum()),
                          "buffer_cells": int(buffer.sum())},
        "milestones_seconds": [step * 20 for step in sorted(selected_times)],
        "history_response": history_response,
        "first_call_p20_c2_comparison": firstcall_response,
        "regions": {"support": "613 source-composed QC cells across 39 native levels",
                    "buffer": "196-column five-cell Chebyshev buffer across 39 native levels"},
        "field_units": {"Q": "kg/kg", "QC": "kg/kg", "QI": "kg/kg", "QR": "kg/kg",
                        "QS": "kg/kg", "QG": "kg/kg"},
        "metrics": "PROJECTED minus each closed control; signed sum, RMS, L1, max absolute difference from receipt-bound POST_KDM6 state arrays",
        "comparisons": comparisons,
        "closed_source_audits": source_policy,
        "limits": ["These state responses do not isolate causality within model physics.",
                   "This C2 P run is separate from the 20-second P capture; no C1/P20 plus old-C2 combined validation is claimed.",
                   "Response metrics do not establish physical approval or observation skill."],
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
