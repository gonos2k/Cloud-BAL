#!/usr/bin/env python3
"""Replay captured D1 graupel producer and storage operands in pinned Intel builds."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_graupel_store_replay as store_replay
import pr92_source_replay as source_replay

D1_SOURCE = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/module_em_d1.F"
D1_SHA256 = "1d6538e3e1aeb59a2f0f38b2ec8de8aef11c4991e2d6ae0c8d4641b065c821ef"
POLICY_CORE = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/policy_core_reviewed.f90"
POLICY_SHA256 = "8ce23e675a23283fb047a88f6ca0d26444ed2f56a9e7dfdc872a1602a6f1d6bf"
BASELINE_CORE = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/baseline_core_pre_policy.f90"
BASELINE_SHA256 = "cf1384a06a82e2f3d03b4ca61db8fbfb8ad2e61d889e4290d790d7aa4d3be466"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _capture_text(path: Path) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", errors="strict") as stream:
        return stream.read()


def _parse_captures(producer_path: Path, consumer_path: Path) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="pr92_capture_parse_") as folder:
        producer = Path(folder) / "producer.raw"
        consumer = Path(folder) / "consumer.raw"
        producer.write_text(_capture_text(producer_path))
        consumer.write_text(_capture_text(consumer_path))
        return (source_replay.parse_producer_capture(producer),
                source_replay.parse_consumer_capture(consumer))


def _extract(source: str, name: str) -> str:
    starts = list(re.finditer(rf"(?im)^\s*(?:pure\s+)?(?:logical\s+)?(?:subroutine|function)\s+{name}\s*\(", source))
    if len(starts) != 1:
        raise ValueError(f"expected exactly one D1 helper {name}")
    end = re.search(rf"(?im)^\s*end\s+(?:subroutine|function)\s+{name}\s*$",
                    source[starts[0].start():])
    if not end:
        raise ValueError(f"D1 helper {name} has no matching end")
    return source[starts[0].start():starts[0].start() + end.end()].rstrip()


def _hex_real(bits: str, kind: str) -> str:
    return f"transfer(int(z'{bits}',int{kind}),0.0_real{32 if kind == '32' else 64})"


def _data_module(producers: dict, stores: list[dict], identity: list[dict]) -> str:
    """Emit compact hexadecimal fixtures as Fortran parameters."""
    producer_rows = []
    producer_stencils = []
    producer_metrics = []
    producer_scales = []
    producer_tendencies = []
    producer_diffs = []
    for record in producers.values():
        producer_rows.extend(map(str, (record[name] for name in source_replay.PRODUCER_KEYS)))
        producer_metrics.extend(record["metrics32_bits"])
        producer_scales.extend(record["scale32_bits"])
        producer_tendencies.extend([record["before32_bits"], record["after32_bits"]])
        producer_diffs.append(record["diffusion64_bits"])
        for dy in (-1, 0, 1):
            producer_stencils.extend(record["stencil"][dy])
    store64 = [value for row in stores for value in row["candidate_bits64"]]
    store32 = [value for row in stores for value in row["r32_bits"]]
    id64 = [value for row in identity for value in row["r64_bits"]]
    id32 = [value for row in identity for value in row["r32_bits"]]
    idstencil = [value for row in identity for dy in (-1, 0, 1) for value in row["stencil"][dy]]
    idmetrics = [value for row in identity for value in row["metrics32_bits"]]
    idface = [value for row in identity for value in row["face_coeff64_bits"]]
    idnames = {"producer_id": (producer_rows, 7), "producer_stencil": (producer_stencils, 9),
               "producer_metrics": (producer_metrics, 10), "producer_scale": (producer_scales, 4),
               "producer_tendency": (producer_tendencies, 2),
               "producer_diff": (producer_diffs, 1), "store64": (store64, 13),
               "store32": (store32, 6), "identity64": (id64, 12),
               "identity32": (id32, 8), "identity_stencil": (idstencil, 12),
               "identity_metrics": (idmetrics, 10), "identity_face": (idface, 16)}
    declarations = []
    for name, (values, width) in idnames.items():
        rows = len(values) // width
        kind = "int64" if name in {"store64", "identity64", "identity_face", "producer_diff"} else "int32"
        if name == "producer_id":
            literals = ", &\n    ".join(f"{value}" for value in values)
        else:
            literals = ", &\n    ".join(f"int(z'{value}',{kind})" for value in values)
        declarations.append(f"  integer({kind}),parameter :: {name}({width},{rows})=reshape([ &\n    {literals}], [{width},{rows}])")
    return "module captured_data\n  use iso_fortran_env, only: int32,int64\n  implicit none\n" + \
        "\n".join(declarations) + "\nend module captured_data\n"


def _adapter(source: str) -> str:
    diffusion = _extract(source, "graupel_diffusion_point")
    strict = _extract(source, "strict_graupel_pair")
    globals_block = """module d1_graupel_adapter
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer,parameter :: real128=selected_real_kind(33,4931)
  integer,parameter :: ims=-1,ime=1,kms=1,kme=1,jms=-1,jme=1
  real(real32) :: mut_diff(-1:1,-1:1),xkmhd_diff(-1:1,1:1,-1:1)
  real(real32) :: msfux_diff(-1:2,-1:1),msfuy_diff(-1:2,-1:1)
  real(real32) :: msfvx_inv_diff(-1:1,-1:1),msfvy_diff(-1:1,-1:2)
  real(real32) :: msftx(-1:1,-1:1),msfty(-1:1,-1:1),c1(1:1),c2(1:1)
  real(real32) :: rdx,rdy
contains
"""
    return globals_block + diffusion + "\n" + strict + "\nend module d1_graupel_adapter\n"


def _policy_module(source: str) -> str:
    if sha256(source.encode()) != POLICY_SHA256:
        raise ValueError("reviewed policy core hash mismatch")
    return source.replace("module cloud_bal_joint_transport", "module cloud_bal_policy_replay", 1).replace(
        "end module cloud_bal_joint_transport", "end module cloud_bal_policy_replay", 1)


def _core_sources(policy_text: str) -> dict[str, str]:
    baseline = BASELINE_CORE.read_text()
    if sha256(baseline.encode()) != BASELINE_SHA256:
        raise ValueError("baseline core hash mismatch")
    return {"baseline.f90": baseline, "policy.f90": _policy_module(policy_text)}


def _producer_for_identity(producers: dict, identity: dict, channel: int) -> tuple[tuple, dict] | None:
    bounds = identity.get("producer_identity")
    if bounds is None:
        return None
    step, rk, il, ih, jl, jh, kl, kh = bounds
    if step != identity["step"] or rk != identity["rk"]:
        raise ValueError("producer identity epoch/RK differs from consumer capture")
    matches = [(key, row) for key, row in producers.items()
               if key[0] == step and key[1] == rk and key[2] == channel and
               key[4:] == (identity["i"], identity["j"], identity["k"])]
    if len(matches) != 1:
        raise ValueError(f"expected one channel {channel} producer at consumer cell")
    key, row = matches[0]
    if row["identity"] != bounds or not (il <= key[4] <= ih and jl <= key[5] <= jh and kl <= key[6] <= kh):
        raise ValueError("producer record does not match captured diffusion bounds")
    return key, row


def _producer_diffusion_bits(producers: dict, store: dict, channel: int) -> str | None:
    coordinate = tuple(store[key] for key in ("step", "rk")) + (channel,) + tuple(
        store[key] for key in ("i", "j", "k"))
    matches = [row for key, row in producers.items() if key[0:3] == coordinate[0:3] and
               key[4:] == coordinate[3:]]
    if len(matches) > 1:
        raise ValueError(f"duplicate channel {channel} producer at store coordinate {coordinate}")
    return matches[0]["diffusion64_bits"] if matches else None


def _parse_replay_stdout(stdout: str, producers: dict, stores: list[dict], identities: list[dict], arm: str) -> dict:
    producer_rows, identity_rows, store_rows = {}, {}, {}
    expected_tags = {"PRODUCER_REPLAY", "IDENTITY_REPLAY", "STORE_REPLAY"}
    for line in stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "PRODUCER_REPLAY" and len(fields) == 12:
            row_id = int(fields[1])
            if row_id in producer_rows:
                raise ValueError("duplicate producer replay row")
            producer_rows[row_id] = {"valid": fields[2] == "T", "increment_bits": fields[3],
                "expected_bits": fields[4], "identity": list(map(int, fields[5:12]))}
        elif fields[0] == "IDENTITY_REPLAY" and len(fields) == 10:
            row_id = int(fields[1])
            if row_id in identity_rows:
                raise ValueError("duplicate identity replay row")
            identity_rows[row_id] = {"q_valid": fields[2] == "T", "n_valid": fields[3] == "T",
                "q_faces_match": fields[4] == "T", "n_faces_match": fields[5] == "T",
                "q_increment_bits": fields[6], "q_expected_bits": fields[7],
                "n_increment_bits": fields[8], "n_expected_bits": fields[9]}
        elif fields[0] == "STORE_REPLAY" and len(fields) == 12:
            row_id = int(fields[1])
            if row_id in store_rows:
                raise ValueError("duplicate store replay row")
            store_rows[row_id] = {"formula_matches": fields[2] == "T", "baseline_stage": int(fields[3]),
                "baseline_adjustment": int(fields[4]), "baseline_valid": fields[5] == "T",
                "policy_stage": int(fields[6]), "policy_valid": fields[7] == "T",
                "policy_adjustment": int(fields[8]), "stored_pair_strict": fields[9] == "T",
                "stored_q_bits": fields[10], "stored_n_bits": fields[11]}
        else:
            if fields[0] not in expected_tags:
                raise ValueError(f"unknown Fortran replay row tag {fields[0]}")
            raise ValueError(f"malformed Fortran replay row for {fields[0]}")
    if (len(producer_rows) != len(producers) or len(identity_rows) != len(identities) or
            len(store_rows) != len(stores)):
        raise ValueError("Fortran replay output row count differs from captures")
    producer_classifications, producer_rows_by_key = [], {}
    for index, record in enumerate(producers.values(), start=1):
        replayed = producer_rows[index]
        key = tuple(int(record[name]) for name in source_replay.PRODUCER_KEYS)
        producer_rows_by_key[key] = replayed
        exact = (replayed["identity"] == list(key) and replayed["valid"] and
                 replayed["increment_bits"].upper() == replayed["expected_bits"].upper())
        if not exact:
            raise ValueError(f"producer replay mismatch at key {key}")
        producer_classifications.append({"key": list(key), "increment_matches": exact})
    identity_classifications = []
    for index, record in enumerate(identities, start=1):
        replayed = identity_rows[index]
        q_producer_pair = _producer_for_identity(producers, record, 7)
        n_producer_pair = _producer_for_identity(producers, record, 8)
        q_producer_key, q_producer = q_producer_pair if q_producer_pair else (None, None)
        n_producer_key, n_producer = n_producer_pair if n_producer_pair else (None, None)
        q_total, n_total = record["r64"][4:6]
        cache_bits = record.get("cache_delta64_bits")
        if cache_bits is None:
            raise ValueError("first identity capture lacks the source cache delta")
        cache = [source_replay._float64(value) for value in cache_bits]
        cache_match = (struct.pack(">d", q_total + cache[0]).hex().upper() == record["r64_bits"][0].upper() and
                       struct.pack(">d", n_total + cache[1]).hex().upper() == record["r64_bits"][1].upper())
        source_formula_matches = []
        alternate_grouping_matches = []
        for idx, captured in enumerate((q_producer, n_producer)):
            total32 = source_replay._float32(record["r32_bits"][4 + idx])
            before32 = source_replay._float32(captured["before32_bits"])
            after32 = source_replay._float32(captured["after32_bits"])
            diffusion64 = source_replay._float64(captured["diffusion64_bits"])
            expected_bits = struct.pack(">d", total32 + ((before32 + diffusion64) - after32)).hex().upper()
            source_formula_matches.append(expected_bits == record["r64_bits"][idx].upper())
            alternate_bits = struct.pack(">d", (total32 - after32) + (before32 + diffusion64)).hex().upper()
            alternate_grouping_matches.append(alternate_bits == record["r64_bits"][idx].upper())
        fallback_matches = [replayed["q_valid"] and replayed["q_faces_match"] and
                            replayed["q_increment_bits"].upper() == replayed["q_expected_bits"].upper(),
                            replayed["n_valid"] and replayed["n_faces_match"] and
                            replayed["n_increment_bits"].upper() == replayed["n_expected_bits"].upper()]
        fallback_match = all(fallback_matches)
        if not fallback_match:
            raise ValueError("first identity Q/N helper replay did not match capture")
        producer_keys = [q_producer_key, n_producer_key]
        producer_replays = [producer_rows_by_key[key] for key in producer_keys]
        identity_scale = [struct.pack(">f", source_replay._float64(record["r64_bits"][idx])).hex().upper()
                          for idx in (7, 8, 9, 10)]
        geometry_match = (q_producer["metrics32_bits"] == record["metrics32_bits"] and
                          n_producer["metrics32_bits"] == record["metrics32_bits"] and
                          q_producer["scale32_bits"] == identity_scale and
                          n_producer["scale32_bits"] == identity_scale)
        q_state_match = all(q_producer["stencil"][dy][:3] == record["stencil"][dy][:3]
                            for dy in (-1, 0, 1))
        n_state_match = all(n_producer["stencil"][dy][:3] == record["stencil"][dy][3:6]
                            for dy in (-1, 0, 1))
        operator_stencil_match = all(
            q_producer["stencil"][dy][3:9] == record["stencil"][dy][6:12] and
            n_producer["stencil"][dy][3:9] == record["stencil"][dy][6:12]
            for dy in (-1, 0, 1))
        identity_classifications.append({
            "coordinate": [record[key] for key in ("step", "rk", "i", "j", "k")],
            "producer_identity_bounds": record["producer_identity"],
            "qg_producer_key": list(q_producer_key), "qib_producer_key": list(n_producer_key),
            "source_q_expression_matches_qs64": source_formula_matches[0],
            "source_n_expression_matches_ns64": source_formula_matches[1],
            "alternate_grouping_matches_qs_ns64": alternate_grouping_matches,
            "source_formula_operands": {
                "Q": {"FINAL_QT32": record["r32_bits"][4], "BEFORE_D32": q_producer["before32_bits"],
                      "AFTER_D32": q_producer["after32_bits"], "D64": q_producer["diffusion64_bits"]},
                "N": {"FINAL_NT32": record["r32_bits"][5], "BEFORE_D32": n_producer["before32_bits"],
                      "AFTER_D32": n_producer["after32_bits"], "D64": n_producer["diffusion64_bits"]}},
            "total_qt64_plus_cache_delta_matches_source": cache_match,
            "producer_and_consumer_metrics_bits_match": geometry_match,
            "producer_scale32_bits": {"QG": q_producer["scale32_bits"], "QIB": n_producer["scale32_bits"]},
            "consumer_scale64_bits": record["r64_bits"][7:11],
            "producer_stencil32_bits": {"QG": q_producer["stencil"], "QIB": n_producer["stencil"]},
            "consumer_stencil32_bits": record["stencil"],
            "qg_and_consumer_q_state_bits_match": q_state_match,
            "qib_and_consumer_n_state_bits_match": n_state_match,
            "producer_and_consumer_operator_stencil_bits_match": operator_stencil_match,
            "first_consumer_diffusion_matches": fallback_match,
            "first_consumer_q_and_n_diffusion_match": fallback_matches,
            "producer_and_fallback_diffusion_equal": [
                producer_replays[0]["increment_bits"].upper() == replayed["q_increment_bits"].upper(),
                producer_replays[1]["increment_bits"].upper() == replayed["n_increment_bits"].upper()]})
    store_classifications = []
    unresolved_reasons = []
    for index, record in enumerate(stores, start=1):
        replayed = store_rows[index]
        coordinate = [record[key] for key in ("step", "rk", "i", "j", "k")]
        producer_qd = _producer_diffusion_bits(producers, record, 7)
        producer_bd = _producer_diffusion_bits(producers, record, 8)
        source_q = record["candidate_bits64"][2]
        source_b = record["candidate_bits64"][3]
        expected_stage = record["failure_stage"]
        if not replayed["formula_matches"] or replayed["baseline_valid"] or replayed["baseline_stage"] != expected_stage:
            raise ValueError(f"baseline store replay mismatch at {coordinate}")
        q_stored = struct.unpack(">f", int(replayed["stored_q_bits"], 16).to_bytes(4, "big"))[0]
        n_stored = struct.unpack(">f", int(replayed["stored_n_bits"], 16).to_bytes(4, "big"))[0]
        bulk_absent = replayed["policy_valid"] and replayed["policy_adjustment"] == 5
        stage2_preview = (expected_stage == 2 and not replayed["policy_valid"] and
                          replayed["policy_stage"] == 2)
        reasons = ["stage2_policy_preview_unchanged"] if stage2_preview else []
        if expected_stage != 6 and not stage2_preview:
            reasons.append("baseline_stage_not_6")
        if not replayed["policy_valid"] and not stage2_preview:
            reasons.append("policy_rejected")
        if replayed["policy_adjustment"] != 5 and not stage2_preview:
            reasons.append("policy_adjustment_not_5")
        if replayed["policy_valid"] and not replayed["stored_pair_strict"]:
            reasons.append("policy_output_outside_strict_cone")
        if bulk_absent and (q_stored != 0.0 or n_stored != 0.0):
            reasons.append("bulk_absence_output_nonzero")
        classification = ("bulk_volume_quantum_absence" if not reasons else
                          "unresolved_stage2_policy_preview" if stage2_preview else "unresolved")
        if reasons:
            unresolved_reasons.append({"coordinate": coordinate, "reasons": reasons})
        store_classifications.append({
            "arm": arm, "context": record["context"], "coordinate": coordinate,
            "candidate_q_bits64": record["candidate_bits64"][0],
            "candidate_b_bits64": record["candidate_bits64"][1],
            "source_payload": {
                "q_source_bits64": record["candidate_bits64"][2],
                "b_source_bits64": record["candidate_bits64"][3],
                "q_adjustment_bits64": record["candidate_bits64"][4],
                "b_adjustment_bits64": record["candidate_bits64"][5]},
            "producer_diffusion_comparison": {
                "q_producer_d64_bits": producer_qd, "b_producer_d64_bits": producer_bd,
                "source_q_equals_q_producer_d64": producer_qd is not None and source_q.upper() == producer_qd.upper(),
                "source_b_equals_b_producer_d64": producer_bd is not None and source_b.upper() == producer_bd.upper()},
            "density_and_mass_bounds_bits64": record["candidate_bits64"][6:9],
            "carrier_and_base_bits64": record["candidate_bits64"][9:13],
            "input_r32_bits": record["r32_bits"],
            "store_options": {"storage_active": True, "allow_normal_q_adjustment": True,
                              "allow_joint_quantum_absence": True, "strict_mass_ratio": True,
                              "allow_bulk_volume_quantum_absence": True},
            "captured_failure_stage": expected_stage,
            "candidate_formula_matches": replayed["formula_matches"],
            "baseline_failure_stage_matches": replayed["baseline_stage"] == expected_stage,
            "policy_failure_stage": replayed["policy_stage"],
            "policy_valid": replayed["policy_valid"], "policy_adjustment": replayed["policy_adjustment"],
            "stored_pair_strict": replayed["stored_pair_strict"],
            "classification": classification, "unresolved_reasons": reasons})
    expected_full_count = {"OFF": 7, "CPL": 12}[arm]
    full_rows = [row for row in store_classifications if row["context"] == "FULL"]
    full_coordinates = [tuple(row["coordinate"]) for row in full_rows]
    if len(full_rows) != expected_full_count or len(set(full_coordinates)) != expected_full_count:
        raise ValueError(f"expected {expected_full_count} unique FULL coordinates for {arm}; got {len(full_rows)}")
    contexts = {name: sum(row["context"] == name for row in store_classifications)
                for name in sorted({row["context"] for row in store_classifications})}
    stage2_full = [row for row in store_classifications
                   if row["context"] == "FULL" and row["captured_failure_stage"] == 2]
    pure_d = [row["producer_diffusion_comparison"] for row in stage2_full]
    source_closed = bool(identity_classifications) and all(row["source_q_expression_matches_qs64"] and
                        row["source_n_expression_matches_ns64"] and
                        row["total_qt64_plus_cache_delta_matches_source"] and
                        row["producer_and_consumer_metrics_bits_match"] and
                        row["producer_and_consumer_operator_stencil_bits_match"]
                        for row in identity_classifications)
    stage6_rows = [row for row in store_classifications if row["captured_failure_stage"] == 6]
    stage6_closed = bool(stage6_rows) and all(row["classification"] == "bulk_volume_quantum_absence"
                                              for row in stage6_rows)
    unexpected_unresolved = [row for row in unresolved_reasons
                             if row["reasons"] != ["stage2_policy_preview_unchanged"]]
    stage2_count = sum(row["classification"] == "unresolved_stage2_policy_preview"
                       for row in store_classifications)
    status = ("LEGACY_REPLAY_PENDING" if source_closed and stage6_closed and not unexpected_unresolved
              else "UNRESOLVED")
    return {"status": status, "source_chain_closure": source_closed,
            "stage6_bulk_closure": stage6_closed,
            "all_store_cases_closed": not unresolved_reasons,
            "legacy_replay_status": "PENDING" if stage2_count else "NOT_CAPTURED",
            "legacy_witness_status": "NOT_CAPTURED",
            "stage2_policy_preview_count": stage2_count,
            "producer_count": len(producer_classifications),
            "producer_replays": producer_classifications,
            "identity_replays": identity_classifications,
            "store_context_counts": contexts,
            "arm": arm,
            "full_store_count": len(full_rows),
            "stage2_full_source_producer_comparison": {
                "record_count": len(stage2_full),
                "q_source_equals_q_producer_d64_count": sum(row["source_q_equals_q_producer_d64"] for row in pure_d),
                "b_source_equals_b_producer_d64_count": sum(row["source_b_equals_b_producer_d64"] for row in pure_d),
                "both_source_channels_equal_producer_d64_count": sum(
                    row["source_q_equals_q_producer_d64"] and row["source_b_equals_b_producer_d64"]
                    for row in pure_d),
                "missing_producer_channel_count": sum(row["q_producer_d64_bits"] is None or
                                                      row["b_producer_d64_bits"] is None for row in pure_d)},
            "certifier_store_count": sum(row["context"] == "CERTIFIER" for row in store_classifications),
            "unresolved_count": len(unresolved_reasons),
            "unresolved_store_records": unresolved_reasons,
            "store_record_count": len(store_classifications),
            "store_failure_coordinates": store_classifications}


def _runtime_stdout(compiler_stdout: str) -> str:
    """Discard compiler diagnostics before the first replay row; preserve strict runtime parsing."""
    lines = compiler_stdout.splitlines()
    tags = {"PRODUCER_REPLAY", "IDENTITY_REPLAY", "STORE_REPLAY"}
    start = next((index for index, line in enumerate(lines)
                  if line.split() and line.split()[0] in tags), None)
    if start is None:
        raise ValueError("pinned compile output contains no replay rows")
    return "\n".join(lines[start:]).strip()


def combine_arm_reports(off: dict, cpl: dict) -> dict[str, Any]:
    """Join independent arm reports and require all 19 labeled store cases."""
    def value(report: dict, key: str) -> Any:
        return report.get(key, report.get("rows", {}).get(key))

    if value(off, "arm") != "OFF" or value(cpl, "arm") != "CPL":
        raise ValueError("combined reports must be ordered OFF then CPL")
    off_rows = value(off, "store_failure_coordinates")
    cpl_rows = value(cpl, "store_failure_coordinates")
    off_cases = [row for row in off_rows if row["context"] == "FULL"]
    cpl_cases = [row for row in cpl_rows if row["context"] == "FULL"]
    cases = off_cases + cpl_cases
    off_count = sum(row["arm"] == "OFF" for row in cases)
    cpl_count = sum(row["arm"] == "CPL" for row in cases)
    if len(cases) != 19 or off_count != 7 or cpl_count != 12:
        raise ValueError("combined reports must contain 7 OFF and 12 CPL store cases")
    arm_statuses = {off["status"], cpl["status"]}
    status = ("LEGACY_REPLAY_PENDING" if arm_statuses <= {"PASS", "LEGACY_REPLAY_PENDING"}
              else "UNRESOLVED")
    return {"schema": "pr92_d1_source_store_combined_v1",
            "status": status,
            "arm_status": {"OFF": off["status"], "CPL": cpl["status"]},
            "source_chain_closure": value(off, "source_chain_closure") and value(cpl, "source_chain_closure"),
            "stage6_bulk_closure": value(off, "stage6_bulk_closure") and value(cpl, "stage6_bulk_closure"),
            "all_store_cases_closed": value(off, "all_store_cases_closed") and value(cpl, "all_store_cases_closed"),
            "legacy_replay_status": "PENDING" if value(off, "legacy_replay_status") == "PENDING" or
                                    value(cpl, "legacy_replay_status") == "PENDING" else "NOT_CAPTURED",
            "legacy_witness_status": "NOT_CAPTURED",
            "full_store_record_count": len(cases), "full_store_cases": cases,
            "certifier_record_count": value(off, "certifier_store_count") + value(cpl, "certifier_store_count"),
            "certifier_records": [row for row in off_rows + cpl_rows if row["context"] == "CERTIFIER"]}


def _harness() -> str:
    return r"""program source_store_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use captured_data
  use d1_graupel_adapter
  use cloud_bal_joint_transport, only: joint_moment_store
  use cloud_bal_policy_replay, only: policy_store => joint_moment_store
  implicit none
  real(real32) :: field(-1:1,1:1,-1:1),field_n(-1:1,1:1,-1:1),sq,sn,psq,psn,rho32
  real(real64) :: inc,ninc,q,n,qs,ns,qa,na,rho,mn,mx,oldmass,newmass,qbase,nbase,dt64
  real(real128) :: face(4),nface(4)
  integer(int64) :: words(2),candidate_q_bits,candidate_n_bits
  integer :: r,dy,x,adj,stage,padj,pstage
  logical :: valid,nvalid,pvalid,formula_ok,qface_ok,nface_ok,stored_strict
  do r=1,size(producer_id,2)
    call load_producer(r)
    call graupel_diffusion_point(field,0,1,0,inc,face,valid)
    write(*,'(A,1X,I0,1X,L1,2(1X,Z16.16),1X,7(I0,1X))') 'PRODUCER_REPLAY',r,valid, &
      transfer(inc,0_int64),producer_diff(1,r),producer_id(:,r)
  end do
  do r=1,size(identity64,2)
    call load_identity(r)
    call graupel_diffusion_point(field,0,1,0,inc,face,valid)
    call graupel_diffusion_point(field_n,0,1,0,ninc,nface,nvalid)
    qface_ok=valid
    nface_ok=nvalid
    do x=1,4
      words=transfer(face(x),words)
      qface_ok=qface_ok.and.all(words==identity_face(2*x-1:2*x,r))
      words=transfer(nface(x),words)
      nface_ok=nface_ok.and.all(words==identity_face(8+2*x-1:8+2*x,r))
    end do
    write(*,'(A,1X,I0,4(1X,L1),4(1X,Z16.16))') 'IDENTITY_REPLAY',r,valid,nvalid,qface_ok,nface_ok, &
      transfer(inc,0_int64),identity64(3,r),transfer(ninc,0_int64),identity64(4,r)
  end do
  do r=1,size(store64,2)
    q=transfer(store64(1,r),q); n=transfer(store64(2,r),n)
    qs=transfer(store64(3,r),qs); ns=transfer(store64(4,r),ns)
    qa=transfer(store64(5,r),qa); na=transfer(store64(6,r),na)
    rho=transfer(store64(7,r),rho); mn=transfer(store64(8,r),mn); mx=transfer(store64(9,r),mx)
    oldmass=transfer(store64(10,r),oldmass); newmass=transfer(store64(11,r),newmass)
    qbase=transfer(store64(12,r),qbase); nbase=transfer(store64(13,r),nbase)
    dt64=real(transfer(store32(1,r),0.0_real32),real64)
    candidate_q_bits=transfer((oldmass*qbase+dt64*(qs+qa))/newmass,candidate_q_bits)
    candidate_n_bits=transfer((oldmass*nbase+dt64*(ns+na))/newmass,candidate_n_bits)
    formula_ok=candidate_q_bits==store64(1,r).and.candidate_n_bits==store64(2,r)
    rho32=transfer(store32(4,r),rho32)
    call joint_moment_store(q,n,rho32,mn,mx,.true.,sq,sn,adj,valid, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      failure_stage=stage)
    call policy_store(q,n,rho32,mn,mx,.true.,psq,psn,padj,pvalid, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      allow_bulk_volume_quantum_absence=.true.,failure_stage=pstage)
    stored_strict=.false.
    if (pvalid) stored_strict=strict_graupel_pair(real(psq,real64),real(psn,real64),mn,mx)
    write(*,'(A,1X,I0,1X,L1,1X,I0,1X,I0,1X,L1,1X,I0,1X,L1,1X,I0,1X,L1,2(1X,Z8.8))') &
      'STORE_REPLAY',r,formula_ok,stage,adj,valid,pstage,pvalid,padj,stored_strict, &
      transfer(psq,0_int32),transfer(psn,0_int32)
  end do
contains
  subroutine load_producer(row)
    integer,intent(in) :: row
    integer :: xx,yy
    field=0.0_real32; field_n=0.0_real32; mut_diff=0.0_real32; xkmhd_diff=0.0_real32
    do yy=1,3
      do xx=1,3
        field(xx-2,1,yy-2)=transfer(producer_stencil(xx,yy+3*(row-1)),0.0_real32)
        xkmhd_diff(xx-2,1,yy-2)=transfer(producer_stencil(3+xx,yy+3*(row-1)),0.0_real32)
        mut_diff(xx-2,yy-2)=transfer(producer_stencil(6+xx,yy+3*(row-1)),0.0_real32)
      end do
    end do
    call load_metrics(producer_metrics(:,row))
    c1(1)=transfer(producer_scale(1,row),c1(1)); c2(1)=transfer(producer_scale(2,row),c2(1))
    rdx=transfer(producer_scale(3,row),rdx); rdy=transfer(producer_scale(4,row),rdy)
  end subroutine load_producer

  subroutine load_identity(row)
    integer,intent(in) :: row
    integer :: xx,yy
    field=0.0_real32; mut_diff=0.0_real32; xkmhd_diff=0.0_real32
    do yy=1,3
      do xx=1,3
        field(xx-2,1,yy-2)=transfer(identity_stencil(xx,yy+3*(row-1)),0.0_real32)
        field_n(xx-2,1,yy-2)=transfer(identity_stencil(3+xx,yy+3*(row-1)),0.0_real32)
        xkmhd_diff(xx-2,1,yy-2)=transfer(identity_stencil(6+xx,yy+3*(row-1)),0.0_real32)
        mut_diff(xx-2,yy-2)=transfer(identity_stencil(9+xx,yy+3*(row-1)),0.0_real32)
      end do
    end do
    call load_metrics(identity_metrics(:,row))
    c1(1)=real(transfer(identity64(8,row),0.0_real64),real32)
    c2(1)=real(transfer(identity64(9,row),0.0_real64),real32)
    rdx=real(transfer(identity64(10,row),0.0_real64),real32)
    rdy=real(transfer(identity64(11,row),0.0_real64),real32)
  end subroutine load_identity

  subroutine load_metrics(m)
    integer(int32),intent(in) :: m(10)
    msfux_diff(0,0)=transfer(m(1),0.0_real32); msfux_diff(1,0)=transfer(m(2),0.0_real32)
    msfuy_diff(0,0)=transfer(m(3),0.0_real32); msfuy_diff(1,0)=transfer(m(4),0.0_real32)
    msfvx_inv_diff(0,0)=transfer(m(5),0.0_real32); msfvx_inv_diff(0,1)=transfer(m(6),0.0_real32)
    msfvy_diff(0,0)=transfer(m(7),0.0_real32); msfvy_diff(0,1)=transfer(m(8),0.0_real32)
    msftx(0,0)=transfer(m(9),0.0_real32); msfty(0,0)=transfer(m(10),0.0_real32)
  end subroutine load_metrics
end program source_store_replay
"""


def replay(producer_path: Path, consumer_path: Path, output: Path, arm: str,
           d1_source: Path = D1_SOURCE, policy_core: Path = POLICY_CORE,
           receipt_path: Path | None = None) -> dict[str, Any]:
    if arm not in {"OFF", "CPL"}:
        raise ValueError("arm must be OFF or CPL")
    source_bytes = d1_source.read_bytes()
    policy_bytes = policy_core.read_bytes()
    baseline_bytes = BASELINE_CORE.read_bytes()
    if sha256(source_bytes) != D1_SHA256:
        raise ValueError("D1 source hash mismatch")
    if sha256(policy_bytes) != POLICY_SHA256 or sha256(baseline_bytes) != BASELINE_SHA256:
        raise ValueError("baseline or reviewed policy core hash mismatch")
    receipt = json.loads(receipt_path.read_text()) if receipt_path else None
    if receipt is not None and receipt.get("arm") not in {arm, "COUPLED" if arm == "CPL" else "OFF"}:
        raise ValueError("run receipt arm does not match replay arm")
    producers, consumer = _parse_captures(producer_path, consumer_path)
    all_identities = consumer["identity_failures"]
    all_stores = consumer["store_failures"]
    identities = [row for row in all_identities if row["step"] == 15 and row["rk"] == 1]
    stores = [row for row in all_stores if row["step"] == 15 and row["rk"] == 1]
    if not stores:
        raise ValueError("consumer capture has no T15/RK1 store records")
    first_identity = identities[:1]
    historical_counts: dict[str, int] = {}
    for row in all_stores:
        if row["step"] == 15 and row["rk"] == 1:
            continue
        key = f"step={row['step']}/rk={row['rk']}/{row['context']}"
        historical_counts[key] = historical_counts.get(key, 0) + 1
    data = _data_module(producers, stores, first_identity)
    sources = _core_sources(policy_bytes.decode())
    helper_text = _adapter(source_bytes.decode())
    sources["d1_helpers.f90"] = helper_text
    sources["captures.f90"] = data
    sources["fixture.f90"] = _harness()
    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated"
    generated.mkdir(exist_ok=True)
    for name, text in sources.items():
        generated.joinpath(name).write_text(text)
    captures = store_replay.run_source_profile("O0", sources, executable="pr92_replay_o0")
    second = store_replay.run_source_profile("O2", sources, executable="pr92_replay_o2")
    runtime0 = _runtime_stdout(captures["stdout"])
    runtime2 = _runtime_stdout(second["stdout"])
    if runtime0 != runtime2:
        raise RuntimeError("O0 and O2 replay output differs")
    rows = _parse_replay_stdout(runtime0, producers, stores, first_identity, arm)
    rows["historical_excluded_store_counts"] = historical_counts
    result = {"schema": "pr92_d1_source_store_replay_v1", "status": rows["status"],
              "profiles": {"O0": captures, "O2": second}, "runtime_stdout": runtime0,
              "runtime_stdout_sha256": sha256(runtime0.encode()), "rows": rows,
              "hashes": {"d1_module_sha256": sha256(source_bytes),
                         "d1_helper_text_sha256": sha256(helper_text.encode()),
                         "producer_capture_sha256": sha256(producer_path.read_bytes()),
                         "consumer_capture_sha256": sha256(consumer_path.read_bytes()),
                         "baseline_core_sha256": sha256(baseline_bytes),
                         "policy_core_sha256": sha256(policy_bytes),
                         "data_source_sha256": sha256(data.encode()),
                         "fixture_tool_sha256": sha256(Path(__file__).read_bytes()),
                         "source_parser_tool_sha256": sha256(Path(source_replay.__file__).read_bytes()),
                         "store_compiler_tool_sha256": sha256(Path(store_replay.__file__).read_bytes()),
                         "intel_profile_sha256": sha256((ROOT / "tests/intel_toolchain.sh").read_bytes())},
              "compiler_profiles": ["O0", "O2"],
              "source_run_receipt": ({"status": receipt.get("status"),
                                      "returncode": receipt.get("returncode"),
                                      "timestep_count": receipt.get("timestep_count"),
                                      "final_completed_step": receipt.get("final_completed_step"),
                                      "processing_errors": receipt.get("processing_errors")}
                                     if receipt is not None else None),
              "generated_source_files": {name: sha256(text.encode()) for name, text in sources.items()}}
    if receipt_path is not None:
        result["hashes"]["source_run_receipt_sha256"] = sha256(receipt_path.read_bytes())
    output.joinpath("replay.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", required=True, type=Path)
    parser.add_argument("--consumer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=("OFF", "CPL"))
    parser.add_argument("--d1-source", type=Path, default=D1_SOURCE)
    parser.add_argument("--policy-core", type=Path, default=POLICY_CORE)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = replay(args.producer, args.consumer, args.output, args.arm, args.d1_source, args.policy_core,
                    args.receipt)
    print(json.dumps({"status": result["status"], "arm": args.arm,
                      "store_records": result["rows"]["store_record_count"],
                      "full_store_records": result["rows"]["full_store_count"],
                      "certifier_records": result["rows"]["certifier_store_count"],
                      "unresolved": result["rows"]["unresolved_count"],
                      "report": str(args.output / "replay.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
