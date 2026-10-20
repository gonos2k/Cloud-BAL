#!/usr/bin/env python3
"""Audit closed PR93 C4 native receipts and traces without materializing traces."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUT_DEFAULT = ROOT / "docs/evidence/pr93_active_ice_20261020/runtime"
sys.path.insert(0, str(ROOT / "tools"))
import pr85_joint_stage_trace as stage_trace  # noqa: E402
import pr87_completed_state_audit as completed_audit  # noqa: E402

STATE_MAGIC = {b"PR85QND2", b"PR85QNB1"}
PBL_MAGIC = b"PR85PLB1"
STATE_FIELDS = stage_trace.STATE_FIELDS
PBL_FIELDS = stage_trace.PBL_FIELDS
STATE_SEQUENCE = completed_audit.STATE_SEQUENCE
ENDPOINT_STAGES = completed_audit.STRICT_ENDPOINT_STAGES
TRACE_NAME = "pr85_joint_moment_stages.raw.gz"
ICE_LEDGER_NAME = "pr85_kdm6_psd_boundary.raw.gz"
TARGET = {"i": 230, "call_j": 247, "timestep": 24}


class AuditError(RuntimeError):
    pass


class HashingReader:
    """Hash compressed bytes as GzipFile consumes its single input stream."""
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes = 0

    def read(self, size=-1):
        block = self.stream.read(size)
        self.digest.update(block)
        self.bytes += len(block)
        return block

    def read1(self, size=-1):
        return self.read(size)

    def readable(self):
        return True

    def seekable(self):
        return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def closed_receipt(root: Path, arm: str) -> tuple[dict, Path]:
    receipt_path = root / "receipt.json"
    if not receipt_path.is_file():
        raise AuditError(f"{arm}: no finalized receipt at {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("arm", "").upper() != arm:
        raise AuditError(f"{arm}: receipt arm mismatch")
    if receipt.get("status") not in {"COMPLETE", "INCOMPLETE"}:
        raise AuditError(f"{arm}: collector receipt is not finalized")
    if "snapshots" not in receipt or "compressed_outputs" not in receipt or \
            "processing_errors" not in receipt:
        raise AuditError(f"{arm}: receipt lacks collector-closed fields")
    if receipt["processing_errors"]:
        raise AuditError(f"{arm}: collector reported processing errors")
    return receipt, receipt_path


def output_row(receipt: dict, name: str, arm: str) -> dict:
    matches = [row for row in receipt["compressed_outputs"]
               if row.get("compressed_path") == name]
    if len(matches) != 1:
        raise AuditError(f"{arm}: expected one receipt row for {name}, got {len(matches)}")
    row = matches[0]
    if not all(key in row for key in ("path", "sha256", "bytes", "compressed_path",
                                      "compressed_sha256", "compressed_bytes")):
        raise AuditError(f"{arm}: incomplete output identity for {name}")
    generated_raw = [item for item in receipt.get("generated_files", [])
                     if item.get("path") == row["path"]]
    generated_compressed = [item for item in receipt.get("generated_files", [])
                            if item.get("path") == row["compressed_path"]]
    generated = generated_raw[0] if len(generated_raw) == 1 else \
        generated_compressed[0] if not generated_raw and len(generated_compressed) == 1 else None
    expected_sha, expected_bytes = ((row["sha256"], row["bytes"]) if generated_raw else
                                    (row["compressed_sha256"], row["compressed_bytes"]))
    if generated is None or generated.get("sha256") != expected_sha or generated.get("bytes") != expected_bytes:
        raise AuditError(f"{arm}: output row disagrees with generated-file receipt")
    return row


def derive_prefix(receipt: dict, arm: str) -> list[int]:
    snapshots = receipt["snapshots"]
    completed = snapshots.get("completed_post_kdm6_timesteps")
    if not isinstance(completed, list) or not completed:
        raise AuditError(f"{arm}: no closed completed POST_KDM6 prefix")
    prefix = list(range(1, len(completed) + 1))
    if completed != prefix or snapshots.get("duplicate_post_kdm6_timesteps"):
        raise AuditError(f"{arm}: receipt completed timesteps are not a unique contiguous prefix")
    if receipt.get("final_completed_step") != prefix[-1]:
        raise AuditError(f"{arm}: final_completed_step disagrees with snapshots")
    return prefix


def _trace_records(trace_path: Path, receipt_row: dict, arm: str, completed: set[int]):
    """Yield one decoded record at a time and verify gzip/raw identities on EOF."""
    compressed_sha = hashlib.sha256()
    expanded_sha = hashlib.sha256()
    expanded_bytes = 0
    state_geometry = None
    with trace_path.open("rb") as raw_stream:
        compressed = HashingReader(raw_stream)
        with gzip.GzipFile(fileobj=compressed, mode="rb") as stream:
            index = 0
            while True:
                magic = stream.read(8)
                if not magic:
                    break
                label_raw = stream.read(32)
                header = stream.read(60)
                if len(magic) != 8 or len(label_raw) != 32 or len(header) != 60:
                    raise AuditError(f"{arm}: truncated stage trace record {index}")
                expanded_sha.update(magic + label_raw + header)
                expanded_bytes += 100
                label = label_raw.decode("ascii").strip()
                values = struct.unpack(">15i", header)
                kind, timestep, rkstep = values[:3]
                expected_kind = 1 if magic in STATE_MAGIC else 2 if magic == PBL_MAGIC else -1
                if kind != expected_kind or timestep <= 0 or rkstep < 0:
                    raise AuditError(f"{arm}: invalid trace metadata at record {index}")
                bounds = dict(zip(("ims", "ime", "jms", "jme", "kms", "kme",
                                   "its", "ite", "jts", "jte", "kts", "kte"), values[3:], strict=True))
                for low, high, mem_low, mem_high in (("its", "ite", "ims", "ime"),
                                                     ("jts", "jte", "jms", "jme"),
                                                     ("kts", "kte", "kms", "kme")):
                    if bounds[low] > bounds[high] or bounds[low] < bounds[mem_low] or bounds[high] > bounds[mem_high]:
                        raise AuditError(f"{arm}: invalid active trace bounds at record {index}")
                geometry = tuple(bounds[key] for key in ("ims", "ime", "jms", "jme", "kms", "kme",
                                                         "its", "ite", "jts", "jte", "kts", "kte"))
                if expected_kind == 1:
                    if state_geometry is not None and state_geometry != geometry:
                        raise AuditError(f"{arm}: state geometry changed")
                    state_geometry = geometry
                shape = (bounds["jte"] - bounds["jts"] + 1,
                         bounds["kte"] - bounds["kts"] + 1,
                         bounds["ite"] - bounds["its"] + 1)
                cells = math.prod(shape)
                names = STATE_FIELDS if expected_kind == 1 else PBL_FIELDS if expected_kind == 2 else ()
                if not names:
                    raise AuditError(f"{arm}: unknown trace magic {magic!r}")
                fields = {}
                keep = expected_kind == 1 and timestep in completed
                for name in names:
                    raw_field = stream.read(cells * 4)
                    if len(raw_field) != cells * 4:
                        raise AuditError(f"{arm}: truncated {label} {name} at record {index}")
                    expanded_sha.update(raw_field)
                    expanded_bytes += len(raw_field)
                    if keep:
                        fields[name] = np.frombuffer(raw_field, dtype=">f4").reshape(shape)
                if expected_kind == 1:
                    yield {"index": index, "kind": kind, "timestep": timestep,
                           "rkstep": rkstep, "stage": label, "bounds": bounds,
                           "fields": fields if keep else None,
                           "density_contract_status": ("AUTHORITATIVE_DRY_FROM_AL_ALB"
                                                       if magic == b"PR85QND2" else
                                                       "UNVERIFIED_LEGACY_DECLARATION")}
                index += 1
    if compressed.digest.hexdigest() != receipt_row["compressed_sha256"] or \
            compressed.bytes != receipt_row["compressed_bytes"]:
        raise AuditError(f"{arm}: compressed trace hash/size differs from closed receipt")
    if expanded_sha.hexdigest() != receipt_row["sha256"] or expanded_bytes != receipt_row["bytes"]:
        raise AuditError(f"{arm}: expanded trace hash/size differs from closed receipt")


def step1_trace_prefix(trace_path: Path, receipt_row: dict, arm: str) -> dict:
    """Hash exact state and PBL records through the first timestep-2 record."""
    full_expanded = hashlib.sha256()
    prefix_expanded = hashlib.sha256()
    full_bytes = prefix_bytes = prefix_records = 0
    reached_step2 = False
    with trace_path.open("rb") as raw_stream:
        compressed = HashingReader(raw_stream)
        with gzip.GzipFile(fileobj=compressed, mode="rb") as stream:
            index = 0
            while True:
                magic = stream.read(8)
                if not magic:
                    break
                label = stream.read(32)
                header = stream.read(60)
                if len(label) != 32 or len(header) != 60:
                    raise AuditError(f"{arm}: truncated stage trace record {index}")
                values = struct.unpack(">15i", header)
                kind, timestep = values[:2]
                if magic in STATE_MAGIC:
                    expected_kind, names = 1, STATE_FIELDS
                elif magic == PBL_MAGIC:
                    expected_kind, names = 2, PBL_FIELDS
                else:
                    raise AuditError(f"{arm}: unknown stage trace magic {magic!r}")
                if kind != expected_kind or timestep <= 0:
                    raise AuditError(f"{arm}: invalid record metadata at {index}")
                bounds = dict(zip(("ims", "ime", "jms", "jme", "kms", "kme",
                                   "its", "ite", "jts", "jte", "kts", "kte"), values[3:], strict=True))
                shape = (bounds["jte"] - bounds["jts"] + 1,
                         bounds["kte"] - bounds["kts"] + 1,
                         bounds["ite"] - bounds["its"] + 1)
                cells = math.prod(shape)
                chunks = [magic, label, header]
                for _name in names:
                    raw_field = stream.read(cells * 4)
                    if len(raw_field) != cells * 4:
                        raise AuditError(f"{arm}: truncated field in stage trace record {index}")
                    chunks.append(raw_field)
                record = b"".join(chunks)
                full_expanded.update(record)
                full_bytes += len(record)
                if not reached_step2 and timestep <= 1:
                    prefix_expanded.update(record)
                    prefix_bytes += len(record)
                    prefix_records += 1
                elif timestep == 2:
                    reached_step2 = True
                elif timestep > 2 and not reached_step2:
                    raise AuditError(f"{arm}: timestep {timestep} precedes first timestep-2 record")
                index += 1
    if compressed.digest.hexdigest() != receipt_row["compressed_sha256"] or \
            compressed.bytes != receipt_row["compressed_bytes"]:
        raise AuditError(f"{arm}: compressed trace hash/size differs from closed receipt")
    if full_expanded.hexdigest() != receipt_row["sha256"] or full_bytes != receipt_row["bytes"]:
        raise AuditError(f"{arm}: expanded trace hash/size differs from closed receipt")
    if prefix_records == 0:
        raise AuditError(f"{arm}: stage trace has no timestep-1 state or PBL records")
    return {"sha256": prefix_expanded.hexdigest(), "bytes": prefix_bytes,
            "record_count": prefix_records, "first_timestep2_seen": reached_step2,
            "scope": "Exact serialized state and PBL trace records with timestep <=1, stopping at the first timestep-2 record or at EOF if this one-step attempt has no timestep-2 record."}


def compare_initial_step_prefixes(initial_root: Path, bound_root: Path, arm: str) -> dict:
    """Compare closed one-step launch and bound-run traces; do not infer C18 identity."""
    initial_receipt, initial_receipt_path = closed_receipt(initial_root, arm)
    bound_receipt, bound_receipt_path = closed_receipt(bound_root, arm)
    initial_row = output_row(initial_receipt, TRACE_NAME, f"initial {arm}")
    bound_row = output_row(bound_receipt, TRACE_NAME, f"bound {arm}")
    initial_trace = initial_root / "run" / initial_row["compressed_path"]
    bound_trace = bound_root / "run" / bound_row["compressed_path"]
    if not initial_trace.is_file() or not bound_trace.is_file():
        raise AuditError("step-1 prefix comparison trace is missing")
    pins = ("executed_executable_sha256", "expected_executed_executable_sha256",
            "launch_runner_source_sha256",
            "source_receipt_sha256", "source_receipt_unchanged",
            "candidate_wrfinput_sha256", "candidate_wrfbdy_sha256",
            "candidate_namelist_sha256", "candidate_build")
    pin_comparison = {key: {"initial": initial_receipt.get(key), "bound": bound_receipt.get(key),
                            "equal": initial_receipt.get(key) == bound_receipt.get(key)}
                      for key in pins}
    initial_prefix = step1_trace_prefix(initial_trace, initial_row, f"initial {arm}")
    bound_prefix = step1_trace_prefix(bound_trace, bound_row, f"bound {arm}")
    return {"arm": arm,
            "status": "MATCH" if initial_prefix["sha256"] == bound_prefix["sha256"] and
            initial_prefix["bytes"] == bound_prefix["bytes"] else "MISMATCH",
            "receipts": {"initial": {"path": str(initial_receipt_path),
                                       "sha256": sha256(initial_receipt_path),
                                       "status": initial_receipt["status"]},
                         "bound": {"path": str(bound_receipt_path),
                                   "sha256": sha256(bound_receipt_path),
                                   "status": bound_receipt["status"]}},
            "source_and_input_pins": pin_comparison,
            "same_source_and_input_pins": all(row["equal"] for row in pin_comparison.values()),
            "initial_step1_prefix": initial_prefix, "bound_step1_prefix": bound_prefix,
            "note": "Equal step-1 trace prefixes support only this run-pair comparison. They do not establish C18 source-prefix identity or historical causality."}


def ice_policy_split(fields: dict, policy: dict) -> dict:
    qi = np.asarray(fields["QI"], dtype=np.float32)
    ni = np.asarray(fields["NI"], dtype=np.float32)
    valid = np.isfinite(qi) & np.isfinite(ni) & (qi > 0) & (ni > 0)
    ratio = np.zeros(qi.shape, dtype=np.float64)
    ratio[valid] = qi[valid].astype(np.float64) / ni[valid].astype(np.float64)
    bounds, _basis = stage_trace._policy_bounds(policy, "ice")
    low_tol = stage_trace._eight_ulp(bounds[0])
    high_tol = stage_trace._eight_ulp(bounds[1])
    outside = valid & ((ratio < bounds[0]) | (ratio > bounds[1]))
    beyond = valid & ((ratio < bounds[0] - low_tol) | (ratio > bounds[1] + high_tol))
    active = qi > float(np.nextafter(np.float32(1.0e-14), np.float32(-np.inf), dtype=np.float32))
    return {"bounds_QI_over_NI_kg_per_particle": bounds,
            "cutoff_real32": float(np.nextafter(np.float32(1.0e-14), np.float32(-np.inf), dtype=np.float32)),
            "exact_outlier_cells": int(outside.sum()),
            "beyond_8ulp_cells": int(beyond.sum()),
            "active_exact_outliers": int((outside & active).sum()),
            "inactive_exact_outliers": int((outside & ~active).sum()),
            "active_beyond_8ulp": int((beyond & active).sum()),
            "inactive_beyond_8ulp": int((beyond & ~active).sum()),
            "policy_status": "PASS" if not (beyond & active).any() else "FAIL",
            "scope": "QI/NI is specific particle mean mass in stage trace. Active policy uses existing 8-REAL32-ULP allowance; positive inactive ice below the exact native cutoff is reported separately."}


def exact_psd_ledger(trace_path: Path, receipt_row: dict, arm: str) -> dict:
    expanded = hashlib.sha256()
    expanded_bytes = 0
    pairs = defaultdict(dict)
    counts = defaultdict(int)
    boundary_rows = []
    boundary_context = None
    boundary_call_index = -1
    with trace_path.open("rb") as raw_stream:
        hashed = HashingReader(raw_stream)
        with gzip.GzipFile(fileobj=hashed, mode="rb") as stream:
            for raw_line in stream:
                expanded.update(raw_line)
                expanded_bytes += len(raw_line)
                line = raw_line.decode("ascii").strip()
                if line.startswith("# PR90_KDM6_PSD_BOUNDARY_CONTEXT"):
                    values = line.split()
                    boundary_context = {"timestep": int(values[-2]), "lat": int(values[-1])}
                    boundary_call_index += 1
                    continue
                if line.startswith("PR85_KDM6_PSD_BOUNDARY,") and boundary_context is not None:
                    values = line.split(",")
                    if len(values) != 19:
                        raise AuditError(f"{arm}: malformed PSD boundary row ({len(values)} columns)")
                    row = {"species": values[1], "stage": values[2], "i": int(values[3]),
                           "lat": int(values[4]), "k": int(values[5]), "side": int(values[6]),
                           "Q": float(values[7].replace("D", "E")),
                           "rhoDry": float(values[8].replace("D", "E")),
                           "lambdaMin": float(values[9].replace("D", "E")),
                           "lambdaMax": float(values[10].replace("D", "E")),
                           "Nbefore": float(values[11].replace("D", "E")),
                           "Nnative": float(values[12].replace("D", "E")),
                           "Ndirected": float(values[13].replace("D", "E")),
                           "nativeDelta": float(values[14].replace("D", "E")),
                           "storageCorrection": float(values[15].replace("D", "E")),
                           "exactNmin": float(values[16].replace("D", "E")),
                           "exactNmax": float(values[17].replace("D", "E")),
                           "legacyAvailable": values[18].strip().upper() == "T",
                           "context": dict(boundary_context), "call_index": boundary_call_index}
                    if (row["species"].lower() == "ice" and row["i"] == TARGET["i"] and
                            row["lat"] == TARGET["call_j"] and boundary_context["lat"] == TARGET["call_j"] and
                            boundary_context["timestep"] == TARGET["timestep"]):
                        row["signed_N_change_directed_minus_before"] = row["Ndirected"] - row["Nbefore"]
                        boundary_rows.append(row)
                if not raw_line.startswith(b"PR93_ICE_SED_"):
                    continue
                parts = raw_line.decode("ascii").split()
                if len(parts) != 15:
                    raise AuditError(f"{arm}: malformed PR93 ice capture row ({len(parts)} columns)")
                label = parts[0]
                values = list(map(int, parts[1:8]))
                bits = [int(value, 16) for value in parts[8:11]]
                scalars = [float(value.replace("D", "E")) for value in parts[11:15]]
                step, i, call_j, loop, substep, mstep, k = values
                if (i, call_j, step) != (TARGET["i"], TARGET["call_j"], TARGET["timestep"]):
                    continue
                key = (loop, substep, mstep, k)
                side = "before" if label.endswith("BEFORE") else "after"
                if side in pairs[key]:
                    raise AuditError(f"{arm}: duplicate {label} row for {key}")
                q, n, rho = (struct.unpack(">f", struct.pack(">I", value))[0] for value in bits)
                delz, mass_rate, number_rate, dt = scalars
                pairs[key][side] = {"step": step, "i": i, "call_j": call_j, "loop": loop,
                                     "substep": substep, "mstep": mstep, "k": k,
                                     "QI_bits32": f"{bits[0]:08X}", "NI_volume_bits32": f"{bits[1]:08X}",
                                     "dry_density_bits32": f"{bits[2]:08X}",
                                     "QI": q, "NI_volume": n, "dry_density": rho,
                                     "DELZ": delz, "mass_rate": mass_rate,
                                     "number_rate": number_rate, "dt": dt}
                counts[side] += 1
    if hashed.digest.hexdigest() != receipt_row["compressed_sha256"] or \
            hashed.bytes != receipt_row["compressed_bytes"]:
        raise AuditError(f"{arm}: compressed PSD ledger identity mismatch")
    if expanded.hexdigest() != receipt_row["sha256"] or expanded_bytes != receipt_row["bytes"]:
        raise AuditError(f"{arm}: expanded PSD ledger identity mismatch")
    boundary_summary = summarize_boundary_rows(boundary_rows)
    if counts["before"] == 0 and counts["after"] == 0:
        return {"status": "NO_SELECTED_CAPTURE", "target": TARGET,
                "compressed_sha256": receipt_row["compressed_sha256"],
                "expanded_sha256": receipt_row["sha256"],
                "psd_boundary_reconstruction": boundary_summary}
    if counts["before"] == 0 or counts["after"] == 0:
        raise AuditError(f"{arm}: one-sided selected capture rows")
    unmatched = [list(key) for key, value in pairs.items() if set(value) != {"before", "after"}]
    if unmatched:
        raise AuditError(f"{arm}: unmatched before/after capture keys: {unmatched[:5]}")
    call_levels = defaultdict(set)
    for loop, substep, mstep, k in pairs:
        call_levels[(loop, substep, mstep)].add(k)
    for call, levels in call_levels.items():
        ordered_levels = sorted(levels)
        if len(ordered_levels) != 39 or ordered_levels != list(range(ordered_levels[0], ordered_levels[0] + 39)):
            raise AuditError(f"{arm}: selected capture {call} does not cover 39 contiguous levels")

    policy = stage_trace._load_policy()
    bounds, _ = stage_trace._policy_bounds(policy, "ice")
    low_tol, high_tol = stage_trace._eight_ulp(bounds[0]), stage_trace._eight_ulp(bounds[1])

    def state(row):
        q, n, rho = row["QI"], row["NI_volume"], row["dry_density"]
        if not all(math.isfinite(x) for x in (q, n, rho)) or rho <= 0 or q < 0 or n < 0:
            return {"valid": False, "mean_mass_kg": None, "reason": "nonfinite_or_unpaired_nonnegative_state"}
        if q == 0 and n == 0:
            return {"valid": True, "mean_mass_kg": None, "reason": "joint_absence"}
        if q <= 0 or n <= 0:
            return {"valid": False, "mean_mass_kg": None, "reason": "orphan_or_nonpositive_pair"}
        mean = float(rho) * float(q) / float(n)
        lower_ok = mean >= bounds[0] - low_tol
        upper_ok = mean <= bounds[1] + high_tol
        inactive_limit = float(np.nextafter(np.float32(1.0e-14), np.float32(-np.inf), dtype=np.float32))
        inactive = q <= inactive_limit
        valid = lower_ok and upper_ok or (inactive and n > 0)
        return {"valid": bool(valid), "mean_mass_kg": mean,
                "strict_active_cone": bool(lower_ok and upper_ok),
                "inactive_exception": bool(inactive and n > 0),
                "reason": "active_cone" if lower_ok and upper_ok else "native_inactive_pair" if valid else "outside_active_cone"}

    ordered = sorted(pairs.items(), key=lambda item: item[0])
    transitions = []
    observations = []
    for key, pair in ordered:
        before, after = pair["before"], pair["after"]
        before_state, after_state = state(before), state(after)
        observations.append({"loop_substep_k": list(key),
                             "before_state": before_state, "after_state": after_state,
                             "before_raw": before, "after_raw": after})
        if before_state["valid"] and not after_state["valid"]:
            transitions.append({"loop_substep_k": list(key),
                                "before_state": before_state, "after_state": after_state,
                                "before_raw": before, "after_raw": after})
    first_transition = None
    if transitions:
        call_key = transitions[0]["loop_substep_k"][:3]
        first_transition = {"loop_substep_mstep": call_key,
                            "levels": [row for row in transitions
                                       if row["loop_substep_k"][:3] == call_key],
                            "note": "First all-level transition call. The column call reports a post-call state; ordering among levels in one call is not inferred."}
    k20_observations = [row for row in observations if row["loop_substep_k"][3] == 20]
    k20_transition = next((row for row in transitions if row["loop_substep_k"][3] == 20), None)
    first_invalid_observation = next((row for row in observations
                                      if not row["before_state"]["valid"]), None)
    initial_before_invalid = bool(observations and not observations[0]["before_state"]["valid"])
    return {"status": "FIRST_VALID_TO_INVALID_CAPTURED" if first_transition else
            "FIRST_OBSERVED_STATE_ALREADY_INVALID" if initial_before_invalid else
            "NO_VALID_TO_INVALID_TRANSITION_CAPTURED",
            "target": TARGET, "formula": "REAL64(dry_density)*REAL64(QI)/REAL64(NI_volume)",
            "bounds_kg": bounds, "endpoint_8ulp_tolerances_kg": [low_tol, high_tol],
            "ordered_call_keys": [list(key) for key, _ in ordered],
            "first_transition": first_transition, "first_observed": first_invalid_observation,
            "k20_target_summary": {"observations": k20_observations,
                                   "first_valid_to_invalid": k20_transition,
                                   "note": "Separate target-level result; it does not imply write order relative to other levels."},
            "psd_boundary_reconstruction": boundary_summary,
            "all_observed_pairs": observations,
            "attribution": "This is a C4 run capture. It is not attributed to historical C18 unless the executable/source-prefix and input identities are independently proven identical."}


def summarize_boundary_rows(rows: list[dict]) -> dict:
    first_call = min((row["call_index"] for row in rows), default=None)
    stages = defaultdict(lambda: {"rows": 0, "signed_N_change_sum_unweighted": 0.0,
                                  "after_first_call_rows": 0})
    for row in rows:
        item = stages[row["stage"]]
        item["rows"] += 1
        item["signed_N_change_sum_unweighted"] += row["signed_N_change_directed_minus_before"]
        if first_call is not None and row["call_index"] > first_call:
            item["after_first_call_rows"] += 1
    return {"selected_rows": rows, "first_selected_call_index": first_call,
            "by_stage": dict(stages),
            "scope": "Selected ice PSD boundary reconstruction diagnostics only. N changes are unweighted event-row sums, not a carrier-integrated or global N budget and not evidence of nucleation. Rows after the first selected call are counted separately as possible direct-miss catches when the source trace flag was false; this is a scope label, not a causal attribution."}


def audit_arm(root: Path, arm: str) -> dict:
    receipt, receipt_path = closed_receipt(root, arm)
    prefix = derive_prefix(receipt, arm)
    trace_row = output_row(receipt, TRACE_NAME, arm)
    ice_row = output_row(receipt, ICE_LEDGER_NAME, arm)
    trace_path = root / "run" / trace_row["compressed_path"]
    ice_path = root / "run" / ice_row["compressed_path"]
    if not trace_path.is_file() or not ice_path.is_file():
        raise AuditError(f"{arm}: receipt-bound compressed trace is missing")

    policy = stage_trace._load_policy()
    state_rows = defaultdict(list)
    active_rows = []
    exact_gate_rows, predictor_rows = [], []
    qnb_rows = []
    for record in _trace_records(trace_path, trace_row, arm, set(prefix)):
        if record["timestep"] not in prefix:
            continue
        if record["fields"] is None:
            raise AuditError(f"{arm}: completed timestep record was not decoded")
        if record["density_contract_status"] != "AUTHORITATIVE_DRY_FROM_AL_ALB":
            raise AuditError(f"{arm}: exact source audit requires authoritative dry-density trace records")
        state_rows[record["timestep"]].append((record["stage"], record["rkstep"]))
        result = completed_audit._stage_violations(record, policy)
        pair_conversion = {"violations": result["violations"],
                           "mass_moment_pairs": result["pairs"],
                           "number_conversion": result["number_conversion"]}
        qnb_rows.append({"timestep": record["timestep"], "stage": record["stage"],
                         "rkstep": record["rkstep"], **pair_conversion})
        split = ice_policy_split(record["fields"], policy)
        active_rows.append({"timestep": record["timestep"], "stage": record["stage"],
                            "rkstep": record["rkstep"], **split})
        source_checks = completed_audit._strict_source_checks(record["fields"])
        strict_violations = completed_audit._strict_source_violations(source_checks)
        row = {"timestep": record["timestep"], "stage": record["stage"],
               "rkstep": record["rkstep"], "violations": strict_violations,
               "diagnostic_ice_exact_counts": source_checks["ice_diagnostic"]["counts"]}
        if (record["stage"], record["rkstep"]) in ENDPOINT_STAGES:
            exact_gate_rows.append(row)
        else:
            predictor_rows.append(row)

    expected_state_sequence = tuple(zip(STATE_SEQUENCE, (0, 1, 2, 3, 0, 0), strict=True))
    for timestep in prefix:
        if tuple(state_rows[timestep]) != expected_state_sequence:
            raise AuditError(f"{arm}: timestep {timestep} state sequence differs from completed-state contract")
    if len(state_rows) != len(prefix):
        raise AuditError(f"{arm}: decoded state count does not cover receipt prefix")

    ledger = exact_psd_ledger(ice_path, ice_row, arm)
    exact_failures = [row for row in exact_gate_rows if row["violations"]]
    pair_conversion_failures = [row for row in qnb_rows if any(row["violations"].values())]
    return {"schema": "pr93_closed_run_audit_v1", "arm": arm,
            "receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path),
                        "status": receipt["status"], "returncode": receipt.get("returncode"),
                        "final_completed_step": receipt["final_completed_step"],
                        "completed_prefix": prefix,
                        "candidate_build": receipt.get("candidate_build"),
                        "executed_executable_sha256": receipt.get("executed_executable_sha256"),
                        "candidate_wrfinput_sha256": receipt.get("candidate_wrfinput_sha256"),
                        "candidate_wrfbdy_sha256": receipt.get("candidate_wrfbdy_sha256"),
                        "candidate_namelist_sha256": receipt.get("candidate_namelist_sha256")},
            "trace_identity": {"compressed_path": str(trace_path),
                               "compressed_sha256": trace_row["compressed_sha256"],
                               "expanded_sha256": trace_row["sha256"],
                               "expanded_bytes": trace_row["bytes"]},
            "exact_source_endpoint_audit": {"status": "FAIL" if exact_failures else "PASS",
                                            "scope": "Existing PR87 exact source coefficient violations at RK3, PRE_KDM6, POST_KDM6 only; no ULP slack. Exact ice counts are diagnostic, not this generic gate.",
                                            "failures": exact_failures,
                                            "predictor_diagnostics_not_gated": predictor_rows},
            "active_ice_policy_split": {"status": "FAIL" if any(row["policy_status"] == "FAIL" for row in active_rows) else "PASS",
                                        "scope": "Existing 8-ULP active ice policy, with source-inactive positive pairs separately counted, on all six states per completed timestep.",
                                        "per_state": active_rows},
            "qnb_pair_conversion_audit": {"status": "FAIL" if pair_conversion_failures else "PASS",
                                           "scope": "Existing PR87 generic Q/N/B pair, PSD cone with 8-ULP slack, and dry-density number conversion checks per completed state.",
                                           "failure_count": len(pair_conversion_failures),
                                           "per_state": qnb_rows},
            "selected_ice_sedimentation_capture": ledger,
            "scope_limits": ["The receipt determines the completed prefix; later partial states are parsed and hashed but not treated as completed states.",
                             "The PSD capture's mean uses the exact KDM6 freezing expression rho*QI/NI_volume; the completed-state trace stores specific NI and uses QI/NI.",
                             "A C4 capture does not establish historical C18 causality without exact source-prefix and input identity proof.",
                             "Graph freshness and source checks do not establish runtime or scientific validation."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, default=Path("/var/tmp/pr93_OFF_600s_c4_bound_20261020"))
    parser.add_argument("--coupled-root", type=Path, default=Path("/var/tmp/pr93_COUPLED_600s_c4_bound_20261020"))
    parser.add_argument("--initial-off-root", type=Path, default=Path("/var/tmp/pr93_OFF_600s_c4_execution_20261020"))
    parser.add_argument("--initial-coupled-root", type=Path, default=Path("/var/tmp/pr93_COUPLED_600s_c4_execution_20261020"))
    parser.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    try:
        reports = {arm.lower(): audit_arm(root, arm.upper()) for arm, root in
                   (("OFF", args.off_root), ("COUPLED", args.coupled_root))}
        prefix_comparisons = {
            "off": compare_initial_step_prefixes(args.initial_off_root, args.off_root, "OFF"),
            "coupled": compare_initial_step_prefixes(args.initial_coupled_root, args.coupled_root, "COUPLED"),
        }
        args.output.mkdir(parents=True, exist_ok=True)
        for arm, report in reports.items():
            target = args.output / f"{arm}_closed_audit.json"
            with target.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
        summary = {arm: {"receipt_status": report["receipt"]["status"],
                         "completed_steps": len(report["receipt"]["completed_prefix"]),
                         "exact_source_status": report["exact_source_endpoint_audit"]["status"],
                         "active_ice_status": report["active_ice_policy_split"]["status"],
                         "qnb_status": report["qnb_pair_conversion_audit"]["status"],
                         "ice_capture_status": report["selected_ice_sedimentation_capture"]["status"]}
                   for arm, report in reports.items()}
        with (args.output / "initial_step1_prefix_comparison.json").open("x", encoding="utf-8") as stream:
            json.dump({"schema": "pr93_initial_step1_prefix_comparison_v1",
                       "comparisons": prefix_comparisons}, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        summary["initial_step1_prefixes_match"] = all(
            report["status"] == "MATCH" for report in prefix_comparisons.values())
        with (args.output / "closed_audit_summary.json").open("x", encoding="utf-8") as stream:
            json.dump({"schema": "pr93_closed_run_audit_summary_v1", "arms": summary},
                      stream, indent=2, sort_keys=True)
            stream.write("\n")
    except (AuditError, OSError, EOFError, ValueError, KeyError, TypeError, UnicodeDecodeError, struct.error, gzip.BadGzipFile) as exc:
        parser.error(str(exc))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
