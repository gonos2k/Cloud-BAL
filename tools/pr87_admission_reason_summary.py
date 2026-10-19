#!/usr/bin/env python3
"""Summarize PR87 full-proposal endpoint reason records by proposal activity.

Endpoint reasons are first failed full-proposal checks, not certificates for
the constraint that selected the admitted alpha. Weighting uses the frozen
PR86 same-cell call geometry only after proving candidate pre/post captures are
byte-identical to that arm's frozen v17 first call.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pr86_process_budget import LedgerError
from pr86_water_budget import cell_slot, load_call_measure

BASELINE_RUNS = {
    "OFF": Path("/var/tmp/pr85_same13_OFF_joint_v17_20261015a"),
    "COUPLED": Path("/var/tmp/pr85_same13_COUPLED_joint_v17_20261015a"),
}
RAW_NAME = "pr87_admission_reason.raw"
REASON_NAMES = {
    0: "VALID",
    1: "BADINPUT",
    2: "DONORNEGATIVE",
    3: "ORPHAN",
    4: "CUTOFF",
    5: "PSDCLOUD",
    6: "RAIN",
    7: "ICE",
    8: "TEMPERATURE",
    9: "BULKDENSITY",
}
STATUS_NAMES = {0: "FEASIBLE_SEARCH", 1: "NO_FEASIBLE_STEP", 2: "SEARCH_FAILURE_OR_UNSUPPORTED_G_VOLUME"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise LedgerError(f"not a regular file: {path}")


def _candidate_call(root: Path, arm: str, frozen_call: dict[str, Any], *,
                    allow_first_call_only: bool) -> dict[str, Any]:
    preflight_path = root / "preflight.json"
    receipt_path = root / "receipt.json"
    _regular_file(preflight_path)
    _regular_file(receipt_path)
    preflight = json.loads(preflight_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if preflight.get("arm") != arm or receipt.get("arm") != arm:
        raise LedgerError(f"candidate receipt arm does not match requested {arm}")
    if Path(preflight.get("runtime_dir", "")).resolve() != frozen_call["run_root"].resolve():
        raise LedgerError("candidate preflight does not identify the frozen geometry run")
    source_receipt = Path(preflight.get("source_receipt", ""))
    _regular_file(source_receipt)
    source_sha = _sha256(source_receipt)
    frozen_receipt_sha = frozen_call["identities"]["receipt"]["sha256"]
    if (source_sha != preflight.get("source_receipt_sha256") or
            source_sha != frozen_receipt_sha or
            receipt.get("source_receipt_sha256") != source_sha):
        raise LedgerError("candidate source receipt does not bind frozen call geometry")
    complete_window = receipt.get("status") == "COMPLETE" and receipt.get("returncode") == 0
    first_call_only_window = (
        receipt.get("status") == "INCOMPLETE" and receipt.get("returncode") != 0 and
        receipt.get("timestep_count", 0) >= 1 and
        receipt.get("final_completed_step", 0) >= 1
    )
    if not complete_window and not (allow_first_call_only and first_call_only_window):
        raise LedgerError("candidate native run did not complete successfully")
    build = preflight.get("candidate_build", {})
    if (build != receipt.get("candidate_build") or
            build.get("status") != "PASS_OVERLAY_BUILD" or
            receipt.get("candidate_build_unchanged") is not True or
            receipt.get("executed_executable_sha256") != build.get("executable_sha256") or
            receipt.get("expected_executed_executable_sha256") != build.get("executable_sha256")):
        raise LedgerError("candidate receipt does not bind an unchanged overlay executable")
    build_receipt = Path(build.get("receipt_path", ""))
    _regular_file(build_receipt)
    if _sha256(build_receipt) != build.get("receipt_sha256"):
        raise LedgerError("candidate build receipt hash mismatch")
    build_details = json.loads(build_receipt.read_text())
    if build_details.get("status") != "PASS_OVERLAY_BUILD":
        raise LedgerError("candidate build receipt is not a passing overlay build")
    kdm6_source = build_details.get("source_overrides", {}).get("module_mp_kdm6.o", {})
    if not kdm6_source.get("requested_sha256") or \
            kdm6_source.get("requested_sha256") != kdm6_source.get("staged_sha256"):
        raise LedgerError("candidate build receipt does not bind staged KDM6 reason source")

    compressed = {row.get("path"): row for row in receipt.get("compressed_outputs", [])}
    run_dir = root / "run"

    def verify_output(name: str) -> Path:
        row = compressed.get(name)
        if not row or not row.get("compressed_path") or not row.get("compressed_sha256"):
            raise LedgerError(f"candidate receipt does not bind {name}")
        path = (run_dir / row["compressed_path"]).resolve()
        if path.parent != run_dir.resolve():
            raise LedgerError(f"candidate output path escapes run root: {name}")
        _regular_file(path)
        if _sha256(path) != row["compressed_sha256"]:
            raise LedgerError(f"candidate compressed output hash mismatch: {name}")
        digest = hashlib.sha256()
        try:
            with gzip.open(path, "rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    digest.update(block)
        except OSError as exc:
            raise LedgerError(f"candidate compressed output is unreadable: {name}") from exc
        if digest.hexdigest() != row.get("sha256"):
            raise LedgerError(f"candidate raw output hash mismatch: {name}")
        return path

    for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"):
        frozen_sha = frozen_call["identities"][name]["sha256"]
        candidate_sha = compressed.get(name, {}).get("sha256")
        if candidate_sha != frozen_sha:
            raise LedgerError(f"candidate {name} differs from frozen {arm} call geometry")
        verify_output(name)

    reason_path = verify_output(RAW_NAME)
    reason_entry = compressed[RAW_NAME]
    return {"path": str(receipt_path), "sha256": _sha256(receipt_path),
            "preflight_path": str(preflight_path), "preflight_sha256": _sha256(preflight_path),
            "build_receipt_path": str(build_receipt), "build_receipt_sha256": build["receipt_sha256"],
            "kdm6_reason_source_sha256": kdm6_source["requested_sha256"],
            "arm": arm,
            "candidate_run_status": receipt["status"],
            "candidate_run_returncode": receipt["returncode"],
            "completed_window": ("FULL_REQUESTED_WINDOW" if complete_window
                                 else "FIRST_CALL_CAPTURE_ONLY_RUN_INCOMPLETE"),
            "raw_compressed_path": str(reason_path),
            "raw_sha256": reason_entry["sha256"],
            "raw_compressed_sha256": reason_entry["compressed_sha256"],
            "raw_bytes": reason_entry["bytes"],
            "frozen_source_receipt_sha256": source_sha,
            "candidate_first_call_capture_sha256": {
                name: compressed[name]["sha256"]
                for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw")}}


def _parse_row(line: str, line_number: int) -> tuple[str, list[int], list[float]]:
    fields = line.split()
    if not fields or fields[0] != "PR87_ADMISSION":
        raise LedgerError(f"line {line_number}: expected PR87_ADMISSION")
    if len(fields) != 14:
        raise LedgerError(f"line {line_number}: expected 14 tokens, got {len(fields)}")
    if fields[1] not in ("AUT", "G"):
        raise LedgerError(f"line {line_number}: unsupported group {fields[1]!r}")
    try:
        ids = [int(value) for value in fields[2:10]]
        values = [float(value.replace("D", "E").replace("d", "e"))
                  for value in fields[10:]]
    except ValueError as exc:
        raise LedgerError(f"line {line_number}: invalid numeric field") from exc
    if not all(math.isfinite(value) for value in values):
        raise LedgerError(f"line {line_number}: nonfinite real field")
    i, lat, k, loop, status, endpoint_reason, vapor_reason, paired = ids
    if i < 1 or lat < 1 or k < 1 or loop < 1:
        raise LedgerError(f"line {line_number}: nonpositive cell or loop index")
    if status not in STATUS_NAMES:
        raise LedgerError(f"line {line_number}: unknown search status {status}")
    if endpoint_reason not in REASON_NAMES:
        raise LedgerError(f"line {line_number}: unknown endpoint reason {endpoint_reason}")
    if vapor_reason not in (0, 10) or paired not in (0, 1):
        raise LedgerError(f"line {line_number}: invalid vapor reason or full_evap_pending flag")
    alpha, activity, density, dz = values
    if not (0.0 <= alpha < 1.0 and activity > 0.0 and density > 0.0 and dz > 0.0):
        raise LedgerError(f"line {line_number}: row does not describe a suppressed positive proposal")
    return fields[1], ids, values


def _new_bucket() -> dict[str, float | int]:
    return {"records": 0, "emitted_proposal_activity_kg": 0.0,
            "approved_activity_kg": 0.0, "rejected_activity_kg": 0.0,
            "full_evap_pending_records": 0}


def analyze_arm(root: Path, arm: str, *, allow_first_call_only: bool = False) -> dict[str, Any]:
    if arm not in BASELINE_RUNS:
        raise LedgerError(f"unsupported arm {arm}")
    frozen = load_call_measure(BASELINE_RUNS[arm])
    candidate = _candidate_call(root, arm, frozen,
                                allow_first_call_only=allow_first_call_only)
    bounds, call = frozen["bounds"], frozen
    by_group: dict[str, dict[str, Any]] = {
        group: {"records": 0, "emitted_proposal_activity_kg": 0.0,
                "rows_by_reason_status": {}}
        for group in ("AUT", "G")
    }
    row_count = 0
    path = Path(candidate["raw_compressed_path"])
    with gzip.open(path, "rt", encoding="ascii") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip() or line.startswith("#"):
                continue
            group, ids, values = _parse_row(line, line_number)
            i, lat, k, _loop, status, endpoint_reason, vapor_reason, paired = ids
            alpha, specific_activity, density, dz = values
            slot = cell_slot(bounds, i, lat, k)
            if density != float(call["rho_dry_jki"][slot]):
                raise LedgerError(f"reason rhoDry differs from frozen same-cell call at {(i,lat,k)}")
            if dz != float(call["delz_jki"][slot]):
                raise LedgerError(f"reason DELZ differs from frozen same-cell call at {(i,lat,k)}")
            activity = (specific_activity * density * dz *
                        float(call["area_ji"][slot[0], slot[2]]))
            if not math.isfinite(activity) or activity <= 0.0:
                raise LedgerError(f"invalid proposal activity at {(i,lat,k)}")
            group_acc = by_group[group]
            group_acc["records"] += 1
            group_acc["emitted_proposal_activity_kg"] += activity
            group_acc["approved_activity_kg"] = group_acc.get("approved_activity_kg", 0.0) + activity * alpha
            group_acc["rejected_activity_kg"] = group_acc.get("rejected_activity_kg", 0.0) + activity * (1.0 - alpha)
            key = f"endpoint={endpoint_reason}:{REASON_NAMES[endpoint_reason]}|vapor={vapor_reason}|status={status}:{STATUS_NAMES[status]}"
            bucket = group_acc["rows_by_reason_status"].setdefault(key, _new_bucket())
            bucket["records"] += 1
            bucket["emitted_proposal_activity_kg"] += activity
            bucket["approved_activity_kg"] += activity * alpha
            bucket["rejected_activity_kg"] += activity * (1.0 - alpha)
            bucket["full_evap_pending_records"] += paired
            row_count += 1

    for group_acc in by_group.values():
        for bucket in group_acc["rows_by_reason_status"].values():
            mass = float(bucket["emitted_proposal_activity_kg"])
            bucket["rejected_over_emitted_proposal"] = (
                float(bucket["rejected_activity_kg"]) / mass if mass else None)
            bucket["approved_over_emitted_proposal"] = (
                float(bucket["approved_activity_kg"]) / mass if mass else None)
            bucket["proposal_activity_fraction"] = (
                mass / float(group_acc["emitted_proposal_activity_kg"])
                if group_acc["emitted_proposal_activity_kg"] else None)
        proposal = float(group_acc["emitted_proposal_activity_kg"])
        group_acc["rejected_over_emitted_proposal"] = (
            float(group_acc["rejected_activity_kg"]) / proposal if proposal else None)
        group_acc["approved_over_emitted_proposal"] = (
            float(group_acc["approved_activity_kg"]) / proposal if proposal else None)
        group_acc["activity_measure"] = (
            "half-L1 Q+QV activity weighted by frozen rhoDry*DELZ*area, among emitted alpha<1 rows")
    return {
        "arm": arm,
        "candidate_run_root": str(root),
        "candidate_receipt": candidate,
        "candidate_run_status": candidate["candidate_run_status"],
        "candidate_run_returncode": candidate["candidate_run_returncode"],
        "completed_window": candidate["completed_window"],
        "same_cell_weighting": {
            "mapping": "reason (i,lat,k) maps directly to frozen first-call (i,j,k) with j=lat",
            "proposal_activity": "reported half-L1 Q plus QV specific vector activity * frozen-call rhoDry * DELZ * exact frozen MAPFAC_M area",
            "native_hybrid_mass_same_call_capture": False,
        },
        "classification": "first failed FULL-proposal endpoint check; not the unique active-bound certificate",
        "records": row_count,
        "groups": by_group,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True,
                        help="candidate run containing the receipt and reason raw file")
    parser.add_argument("--arm", choices=tuple(BASELINE_RUNS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-call-only", action="store_true",
                        help="allow an incomplete run only when one completed first-call post capture matches the frozen run")
    args = parser.parse_args()
    report = {"schema": "pr87_admission_reason_summary_v1",
              "endpoint_reason_codes": REASON_NAMES,
              "vapor_reason_codes": {0: "VALID", 10: "NEGATIVE_OR_NONFINITE_VAPOR"},
              "search_status_codes": STATUS_NAMES,
              "limitations": [
                  "Rows are emitted only for AUT/G proposals with pre-composite alpha below one and positive Q/QV activity.",
                  "Endpoint reason is the first failed full-proposal check and does not identify the boundary active at admitted alpha.",
                  "Mass is a half-L1 vector-activity proxy, not primitive gross reaction mass.",
                  "Weights use frozen v17 call geometry only after candidate pre/post first-call captures match byte-for-byte.",
                  "Same-call host hybrid mass geometry was not captured.",
              ],
              "arm_result": analyze_arm(args.run_root, args.arm,
                                        allow_first_call_only=args.first_call_only)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({group: values["rows_by_reason_status"]
                      for group, values in report["arm_result"]["groups"].items()}, indent=2))


if __name__ == "__main__":
    main()
