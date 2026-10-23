#!/usr/bin/env python3
"""Reduce receipt-closed PR99-C2 bulk-storage tags after parent GO.

The reducer reads no fixed run directory. It evaluates only a closed audit
with PASS on all 32 steps; the pinned host layout then requires RK 1, 2, and 3
for each step. Incomplete runs are explicitly NOT_EVALUATED. No model or replay
is launched here.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Callable

SCHEMA = "pr100_closed_bulk_storage_inputs_v2"
BUILD_PATH = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
BUILD_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
PREFLIGHT_SHA256 = "e5ebd3fe173ec8deee525d2553a347f88ff86a68041f6fc2fac8fbd7df4554a1"
ROOT_GO_SHA256 = "5420c264a6dabf1361e6ff4b0e448efdeee9b0f51811fcef79cb894005760363"
EXECUTABLE_SHA256 = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
COMPILED_SOURCE_SHA256 = "d82efa15ee1c0a44080a8ef40b8a8aef436661f2093b6f66bef7e666584aa296"
ARMS = ("OFF", "HYDRO", "COUPLED")


class EvidenceError(ValueError):
    """Closure bindings or diagnostic rows are incomplete or inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_pin(spec: dict, label: str) -> tuple[Path, str]:
    path = Path(spec["path"])
    expected = spec["sha256"]
    actual = sha256(path)
    if actual != expected:
        raise EvidenceError(f"{label} SHA mismatch")
    return path, actual


def _unsigned(token: str, field: str) -> int:
    if not token.isdecimal():
        raise EvidenceError(f"invalid {field}: {token!r}")
    return int(token)


def _decimal(token: str, field: str) -> Decimal:
    try:
        value = Decimal(token.replace("D", "E").replace("d", "e"))
    except InvalidOperation as exc:
        raise EvidenceError(f"invalid {field}: {token!r}") from exc
    if not value.is_finite():
        raise EvidenceError(f"nonfinite {field}: {token!r}")
    return value


def _parse_storage(fields: list[str], line: int) -> dict | None:
    if not fields or fields[0] != "BULK_VOLUME_ABSENCE":
        return None
    if len(fields) != 6:
        raise EvidenceError(f"malformed storage row at expanded line {line}")
    count = _unsigned(fields[3], "bulk adjustment count")
    dq, db = _decimal(fields[4], "delta_Q"), _decimal(fields[5], "delta_B")
    if count == 0 and (dq != 0 or db != 0):
        raise EvidenceError(f"zero-count storage row has nonzero delta at line {line}")
    if count > 0 and not (dq < 0 and db < 0):
        raise EvidenceError(f"positive-count absence row must preserve signed negative losses at line {line}")
    return {"step": _unsigned(fields[1], "step"), "rk": _unsigned(fields[2], "RK"),
            "count": count, "delta_Q_printed_decimal": str(dq),
            "delta_B_printed_decimal": str(db), "expanded_line": line}


def _parse_tiny_role(fields: list[str], line: int) -> dict | None:
    if not fields or fields[0] != "PR87_GRAUPEL_TINY_BG_ROLE":
        return None
    if len(fields) != 9:
        raise EvidenceError(f"malformed tiny-B role row at RSL line {line}")
    b64, rho_word = fields[7].upper(), fields[8].upper()
    if len(b64) != 16 or any(c not in "0123456789ABCDEF" for c in b64):
        raise EvidenceError(f"invalid B64 bit word at RSL line {line}")
    if len(rho_word) != 16 or any(c not in "0123456789ABCDEF" for c in rho_word):
        raise EvidenceError(f"invalid raw rho transfer word at RSL line {line}")
    count = _unsigned(fields[3], "tiny-B witness count")
    coordinate = [_unsigned(x, "coordinate") for x in fields[4:7]]
    if count <= 0 or min(coordinate) <= 0:
        raise EvidenceError(f"tiny-B witness row has invalid count/coordinate at RSL line {line}")
    return {"step": _unsigned(fields[1], "step"), "rk": _unsigned(fields[2], "RK"),
            "count": count,
            "first_coordinate_ijk": coordinate,
            "first_B64_bit_word": b64,
            "first_rho_transfer_word_uninterpreted": rho_word,
            "rsl_line": line,
            "interpretation": "conditional host successful-mixture witness; not certificate-only"}


def _scan_gzip(spec: dict, label: str,
               parse: Callable[[list[str], int], dict | None]) -> tuple[list[dict], dict]:
    """Hash encoded bytes, consume gzip through EOF/CRC, and parse matching lines."""
    path, before_sha = _verify_pin(spec, f"{label} compressed artifact")
    expected_bytes = spec["compressed_bytes"]
    if path.stat().st_size != expected_bytes:
        raise EvidenceError(f"{label} compressed byte count mismatch")
    expanded_hash = hashlib.sha256()
    expanded_bytes = 0
    records: list[dict] = []
    try:
        with gzip.open(path, "rb") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                expanded_hash.update(raw_line)
                expanded_bytes += len(raw_line)
                try:
                    text = raw_line.decode("ascii", errors="strict")
                except UnicodeDecodeError as exc:
                    raise EvidenceError(f"{label} has non-ASCII line {line_number}") from exc
                row = parse(text.split(), line_number)
                if row is not None:
                    records.append(row)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise EvidenceError(f"{label} gzip decode failed before verified EOF: {exc}") from exc
    after_sha = sha256(path)
    if after_sha != before_sha:
        raise EvidenceError(f"{label} compressed artifact changed while reading")
    expanded_sha = expanded_hash.hexdigest()
    if expanded_sha != spec["expanded_sha256"] or expanded_bytes != spec["expanded_bytes"]:
        raise EvidenceError(f"{label} expanded identity differs from receipt")
    return records, {"compressed_path": str(path), "compressed_sha256": before_sha,
                     "compressed_bytes": expected_bytes, "expanded_sha256": expanded_sha,
                     "expanded_bytes": expanded_bytes, "read_to_gzip_eof": True}


def _artifact_receipt_binding(receipt: dict, run_root: Path, raw_name: str) -> dict:
    compressed_name = f"{raw_name}.gz"
    generated = [row for row in receipt.get("generated_files", [])
                 if row.get("path") == compressed_name]
    compressed = [row for row in receipt.get("compressed_outputs", [])
                  if row.get("path") == raw_name and
                  row.get("compressed_path") == compressed_name]
    if len(generated) != 1 or len(compressed) != 1:
        raise EvidenceError(f"receipt must contain exactly one compressed generated/output row for {raw_name}")
    generated_row, zipped = generated[0], compressed[0]
    if (generated_row.get("sha256") != zipped.get("compressed_sha256") or
            generated_row.get("bytes") != zipped.get("compressed_bytes")):
        raise EvidenceError(f"generated/compressed receipt metadata disagree for {raw_name}")
    path = run_root / "run" / zipped["compressed_path"]
    run_dir = (run_root / "run").resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(run_dir):
        raise EvidenceError(f"artifact escapes receipt run directory: {raw_name}")
    return {"path": str(resolved), "sha256": zipped["compressed_sha256"],
            "compressed_bytes": zipped["compressed_bytes"],
            "expanded_sha256": zipped["sha256"], "expanded_bytes": zipped["bytes"],
            "generated_file_path": generated_row["path"], "generated_file_sha256": generated_row["sha256"],
            "generated_file_bytes": generated_row["bytes"],
            "compressed_output_path": zipped["compressed_path"],
            "compressed_output_sha256": zipped["compressed_sha256"],
            "compressed_output_bytes": zipped["compressed_bytes"]}


def _expected_calls(arm_name: str, audit_arm: dict) -> set[tuple[int, int]]:
    procedural = audit_arm.get("procedural", {})
    trace = audit_arm.get("trace", {}).get("snapshots", {})
    completed = trace.get("completed_post_kdm6_timesteps")
    if (procedural.get("status") != "PASS" or
            procedural.get("completed_steps") != 32 or
            procedural.get("final_completed_step") != 32 or
            completed != list(range(1, 33)) or
            trace.get("duplicate_post_kdm6_timesteps")):
        raise EvidenceError(
            f"{arm_name}: NOT_EVALUATED; full 32-step C2 PASS required for fixed RK coverage")
    # Source/build contract: every complete 20-second host step contains RK 1, 2, and 3.
    return {(step, rk) for step in range(1, 33) for rk in (1, 2, 3)}


def reduce_arm(name: str, arm: dict, audit: dict, audit_sha: str,
               build_sha: str) -> dict:
    if name not in ARMS:
        raise EvidenceError(f"unexpected arm name {name!r}")
    receipt_path, receipt_sha = _verify_pin(arm["receipt"], f"{name} run receipt")
    run_root = Path(arm["run_root"]).resolve()
    if receipt_path.resolve() != run_root / "receipt.json":
        raise EvidenceError(f"{name}: receipt path does not match declared run root")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("arm", "").upper() != name:
        raise EvidenceError(f"{name}: receipt arm mismatch")
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise EvidenceError(f"{name}: NOT_EVALUATED; all three arms must be closed COMPLETE/0")
    candidate = receipt.get("candidate_build", {})
    if (candidate.get("receipt_path") != str(BUILD_PATH) or
            candidate.get("receipt_sha256") != build_sha or
            candidate.get("executable_sha256") != EXECUTABLE_SHA256 or
            receipt.get("executed_executable_sha256") != EXECUTABLE_SHA256 or
            receipt.get("expected_executed_executable_sha256") != EXECUTABLE_SHA256):
        raise EvidenceError(f"{name}: receipt does not bind reviewed C2 build/executable")
    audit_arm = audit.get("arms", {}).get(name, {})
    identity = audit_arm.get("identity", {})
    if (audit.get("candidate") != "PR99-C2" or
            audit.get("build_receipt_sha256") != build_sha or
            audit.get("executable_sha256") != EXECUTABLE_SHA256 or
            set(audit.get("run_roots", {})) != set(ARMS) or
            set(audit.get("arms", {})) != set(ARMS) or
            audit.get("run_roots", {}).get(name) != str(run_root) or
            identity.get("status") != "PASS" or
            identity.get("run_receipt_sha256") != receipt_sha):
        raise EvidenceError(f"{name}: closed-audit identity does not bind receipt and matched cohort")
    if arm.get("closed_audit_sha256") != audit_sha:
        raise EvidenceError(f"{name}: wrong closed-audit pin")

    ledger_spec = _artifact_receipt_binding(receipt, run_root, "pr87_joint_storage.raw")
    stdout_spec = _artifact_receipt_binding(receipt, run_root, "rsl.out.0000")
    storage_rows, ledger_binding = _scan_gzip(ledger_spec, f"{name} storage ledger", _parse_storage)
    tiny_rows, stdout_binding = _scan_gzip(stdout_spec, f"{name} RSL stdout", _parse_tiny_role)

    observed = [(row["step"], row["rk"]) for row in storage_rows]
    if len(observed) != len(set(observed)):
        raise EvidenceError(f"{name}: duplicate storage ledger step/RK keys")
    expected = _expected_calls(name, audit_arm)
    observed_set = set(observed)
    missing, extra = sorted(expected - observed_set), sorted(observed_set - expected)
    if missing or extra:
        raise EvidenceError(f"{name}: storage call coverage differs from closed trace; missing={missing}, extra={extra}")

    successful_keys = observed_set
    for row in tiny_rows:
        row["same_call_storage_ledger_commit_row_present"] = (
            row["step"], row["rk"]) in successful_keys
    qsum = sum((Decimal(row["delta_Q_printed_decimal"]) for row in storage_rows), Decimal(0))
    bsum = sum((Decimal(row["delta_B_printed_decimal"]) for row in storage_rows), Decimal(0))
    return {
        "arm": name,
        "receipt": {"path": str(receipt_path), "sha256": receipt_sha,
                    "status": receipt["status"], "returncode": receipt["returncode"],
                    "final_completed_step": receipt.get("final_completed_step")},
        "closed_audit_sha256": audit_sha,
        "build_receipt_sha256": build_sha,
        "executable_sha256": EXECUTABLE_SHA256,
        "storage_ledger_artifact": ledger_binding,
        "stdout_artifact": stdout_binding,
        "successful_rk_coverage_basis":
            "closed auditor PASS for all 32 POST_KDM6 steps; pinned C2 host layout is RK 1, 2, 3 per completed step",
        "rk_coverage": {"expected_successful_calls": [list(key) for key in sorted(expected)],
                        "observed_successful_commit_calls": [list(key) for key in sorted(observed_set)],
                        "missing": missing, "extra": extra, "status": "PASS"},
        "bulk_absence_rows": storage_rows,
        "tiny_bg_host_witness_events": tiny_rows,
        "aggregate": {
            "bulk_adjustment_count_all_policy_paths": sum(row["count"] for row in storage_rows),
            "signed_delta_Q_sum_of_printed_decimal_strings": str(qsum),
            "signed_delta_B_sum_of_printed_decimal_strings": str(bsum),
            "decimal_sum_context_precision": getcontext().prec,
            "sum_precision_note": "rounded Decimal reductions of printed ES26.17 strings at the recorded context precision; not exact underlying binary sums or physical kg amounts",
            "units": "separate carrier-weighted mixing-ratio amounts in pressure coordinates; no kg conversion",
            "count_scope": "adjustment-5 aggregate combines ordinary bulk storage and new certificate acceptance; certificate-only count is not observed",
            "zero_loss_claim": "not inferred from aggregate totals; per-event source predicate is the loss-budget authority",
        },
        "tiny_role_scope": "conditional stdout host event; preserve every row and raw transfer words; same-call ledger join establishes call-level association only, not certificate-only cell attribution",
    }


def run(manifest_path: Path, expected_audit_sha: str) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise EvidenceError(f"manifest schema must be {SCHEMA}")
    audit_path, audit_sha = _verify_pin(manifest["closed_audit"], "closed audit")
    if audit_sha != expected_audit_sha:
        raise EvidenceError("closed audit differs from externally supplied final pin")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit.get("schema") != "pr99_c2_closed_audit_v1" or
            audit.get("reviewed_c2_preflight_sha256") != PREFLIGHT_SHA256 or
            audit.get("root_launch_go_sha256") != ROOT_GO_SHA256):
        raise EvidenceError("closed audit does not bind reviewed preflight and root GO")
    if set(manifest.get("arms", {})) != set(ARMS):
        raise EvidenceError("manifest must include exactly OFF, HYDRO, and COUPLED")
    for arm_name in ARMS:
        arm_audit = audit.get("arms", {}).get(arm_name, {})
        if arm_audit.get("procedural", {}).get("status") != "PASS":
            raise EvidenceError(f"{arm_name}: NOT_EVALUATED; all arms require complete 640-second PASS")
    build_path, build_sha = _verify_pin(manifest["build_receipt"], "C2 build receipt")
    if build_path.resolve() != BUILD_PATH.resolve():
        raise EvidenceError("build receipt path differs from reviewed C2 path")
    if build_sha != BUILD_SHA256:
        raise EvidenceError("build receipt differs from reviewed C2 build pin")
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build.get("executable_sha256") != EXECUTABLE_SHA256:
        raise EvidenceError("build receipt executable differs from reviewed C2 candidate")
    if sha256(Path(build["executable_path"])) != EXECUTABLE_SHA256:
        raise EvidenceError("reviewed C2 executable changed")
    source_override = build.get("source_overrides", {}).get("module_em.o", {})
    staged_source = Path(source_override.get("staged_path", "/missing/module_em.F"))
    if (source_override.get("requested_sha256") != COMPILED_SOURCE_SHA256 or
            source_override.get("staged_sha256") != COMPILED_SOURCE_SHA256 or
            not staged_source.is_file() or sha256(staged_source) != COMPILED_SOURCE_SHA256):
        raise EvidenceError("compiled module_em source differs from frozen source pin")
    outputs = [reduce_arm(name, manifest["arms"][name], audit, audit_sha, build_sha)
               for name in ARMS]
    return {"schema": "pr100_closed_bulk_storage_reduction_v2",
            "manifest_sha256": sha256(manifest_path),
            "closed_audit_sha256": audit_sha,
            "build_receipt_sha256": build_sha,
            "executable_sha256": EXECUTABLE_SHA256,
            "compiled_source_sha256": COMPILED_SOURCE_SHA256,
            "arms": outputs,
            "interpretation": "closed aggregate adjustment ledger and conditional host witnesses only; no certificate-only location/count, physical kg scaling, or source-event zero-loss claim"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-audit-sha256", required=True)
    args = parser.parse_args()
    result = run(args.manifest, args.expected_audit_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
