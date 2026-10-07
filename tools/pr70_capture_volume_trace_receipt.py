#!/usr/bin/env python3
"""Bind parsed PR70 native donor checkpoints to source, build, and run receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED_SELECTED_SHA256 = "fbfa823b7cba54f0fdd5ffb1cfeaf58fc5722e845508f954e6c992a7aa32a594"
EXPECTED_BASE_OBSERVER_SHA256 = "ee688498b32b7a1ccaf69858f62f4e457f7153df4fb8b965acfd069d8eefb425"
EXPECTED_TRACE_SOURCE_SHA256 = "5278f2df07216a3b6ba180d1e732cdaa7e7bc1194bac2e2e3261d338c12dfe5e"
EXPECTED_INPUT_RECEIPT_SHA256 = "98b308e7e39d47cf989ca329ba09edf2ffe6f7212a18ddae18eb4f4fd3f36240"
EXPECTED_PR69_NATIVE_RECEIPT_SHA256 = "3b39e94f4d2249717d242526ab17066f0293b2d7eba8390bbfaecbfde960db9c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_trace(path: Path) -> tuple[list[dict], dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events = []
    donor = None
    progb = re.compile(r"^\s*PR70_PROGB(PRE|POST)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$")
    donor_start = re.compile(r"^\s*PR70_PGDEP_DONOR\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$")
    for index, line in enumerate(lines):
        match = progb.match(line)
        if match:
            phase, stage, j, i, k = match.groups()[:5]
            qg_token = match.group(6).split()[0]
            tail = lines[index + 1].split()
            events.append({
                "phase": phase,
                "stage": int(stage),
                "lat": int(j),
                "i": int(i),
                "k": int(k),
                "qg": float(qg_token),
                "brs": float(tail[0]),
                "dtcld": float(tail[1]),
                "density_setup_gate": tail[2] == "T",
            })
            continue
        match = donor_start.match(line)
        if match:
            j, i, k = map(int, match.groups()[:3])
            qg = float(match.group(4).split()[0])
            values = lines[index + 1].split()
            donor = {
                "lat": j, "i": i, "k": k, "qg": qg,
                "brs": float(values[0]),
                "dtcld": float(values[1]),
                "pgdep": float(values[2]),
                "rh_ice": float(values[3]),
                "rhox_observed": float(values[4]),
                "density_setup_gate": values[5] == "T",
                "rhox_supported_100_900": values[6] == "T",
            }
    if len(events) != 12 or donor is None:
        raise ValueError(f"expected 12 call records and one donor record, got {len(events)} and {donor}")
    return events, donor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-source", type=Path, required=True)
    parser.add_argument("--base-observer-source", type=Path, required=True)
    parser.add_argument("--trace-source", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--input-receipt", type=Path, required=True)
    parser.add_argument("--pr69-native-receipt", type=Path, required=True)
    parser.add_argument("--audit-doc", type=Path, required=True)
    parser.add_argument("--source-audit", type=Path, required=True)
    parser.add_argument("--observer-patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    hashes = {
        "selected_source": sha256(args.selected_source),
        "base_observer_source": sha256(args.base_observer_source),
        "trace_source": sha256(args.trace_source),
        "build_receipt": sha256(args.build_receipt),
        "run_receipt": sha256(args.run_receipt),
        "run_log": sha256(args.run_log),
        "input_receipt": sha256(args.input_receipt),
        "pr69_native_receipt": sha256(args.pr69_native_receipt),
        "audit_doc": sha256(args.audit_doc),
        "source_audit": sha256(args.source_audit),
        "observer_patch": sha256(args.observer_patch),
    }
    expected = {
        "selected_source": EXPECTED_SELECTED_SHA256,
        "base_observer_source": EXPECTED_BASE_OBSERVER_SHA256,
        "trace_source": EXPECTED_TRACE_SOURCE_SHA256,
        "input_receipt": EXPECTED_INPUT_RECEIPT_SHA256,
        "pr69_native_receipt": EXPECTED_PR69_NATIVE_RECEIPT_SHA256,
    }
    for name, digest in expected.items():
        if hashes[name] != digest:
            raise SystemExit(f"{name} hash mismatch: {hashes[name]}")

    build = json.loads(args.build_receipt.read_text(encoding="utf-8"))
    run = json.loads(args.run_receipt.read_text(encoding="utf-8"))
    input_receipt = json.loads(args.input_receipt.read_text(encoding="utf-8"))
    pr69_native = json.loads(args.pr69_native_receipt.read_text(encoding="utf-8"))
    if pr69_native["input_binding"]["input_receipt_sha256"] != hashes["input_receipt"]:
        raise SystemExit("retained PR69 native receipt does not bind the same input receipt")
    events, donor = parse_trace(args.run_log)
    pre = [event for event in events if event["phase"] == "PRE"]
    post = [event for event in events if event["phase"] == "POST"]
    if [event["stage"] for event in pre] != [1, 2, 2, 3, 4, 5]:
        raise ValueError(f"unexpected executed ProgB stages: {[event['stage'] for event in pre]}")
    if [event["stage"] for event in post] != [1, 2, 2, 3, 4, 5]:
        raise ValueError("ProgB pre/post stage sets do not match")
    if any(event["density_setup_gate"] for event in events):
        raise ValueError("unexpected supported density gate in captured stages")
    if not (donor["qg"] > 0.0 and donor["pgdep"] < 0.0 and donor["density_setup_gate"] is False):
        raise ValueError("captured donor does not match expected unsupported sublimation state")

    donor["donor_density_qg_over_brs"] = donor["qg"] / donor["brs"]
    donor["donor_specific_volume_brs_over_qg"] = donor["brs"] / donor["qg"]
    donor["mass_loss_rate_limit"] = -donor["qg"] / donor["dtcld"]
    donor["pgdep_times_dtcld"] = donor["pgdep"] * donor["dtcld"]
    donor["post_sublimation_qg_before_source_cleanup"] = donor["qg"] + donor["pgdep_times_dtcld"]
    donor["source_generated_volume_rate_if_proportional"] = -donor["brs"] / donor["dtcld"]

    receipt = {
        "schema": "pr70_native_volume_trace_receipt_v1",
        "status": "CONTROLLED_REJECTION_REPRODUCED_WITH_SOURCE_BOUND_CHECKPOINTS",
        "scope": "Observer-only matched research run; no physical process behavior changed.",
        "hashes": hashes,
        "build": {
            "base": build["base"],
            "ifx": build["toolchain"],
            "compile_argv": build["compile"]["argv"],
            "object_sha256": build["compile"]["object_sha256"],
            "archive_sha256_before": build["archive"]["fresh_before_sha256"],
            "archive_sha256_after": build["archive"]["fresh_after_sha256"],
            "archive_member_count": build["archive"]["member_count"],
            "archive_member_sha256": build["archive"]["member_sha256"],
            "link_argv": build["link"]["argv"],
            "executable_sha256": build["link"]["executable_sha256"],
        },
        "runtime": {
            "run_root": run["run_root"],
            "command": run["command"],
            "returncode": run["returncode"],
            "input_integrity": run["input_integrity"],
            "output_isolation": run["output_isolation"],
            "missing_required_outputs": ["kdm6_first_call_post.raw"],
            "input_count": len(input_receipt["inputs"]),
            "input_receipt_sha256": hashes["input_receipt"],
            "rank_and_tile": "one task, one WRF tile (runtime log: task 0 of 1; tile 1)",
            "execution_date": "UTC 2026-10-07; workspace local date 2026-10-08",
            "lat_semantics": "The observer captured local KDM6 argument lat=2; no conversion to global j is asserted.",
            "host_closure": "partial; exact retained-host build lineage not newly established",
        },
        "progb_calls_before_pgdep": events,
        "pgdep_donor": donor,
        "source_order": {
            "progb_call_sites": [1389, 1492, 1583, 1732, 1927],
            "qg_bg_creation_between_last_two_calls": {
                "source_lines": [1897, 1898],
                "qg_write": "qg += pfrzdtr",
                "bg_write": "brs += pfrzdtr / denr",
                "retained_denr": pr69_native["run"]["diagnostic"]["other_fixed_partner_mass_rates_and_density"]["denr"],
                "denr_source": {"receipt": str(args.pr69_native_receipt), "sha256": hashes["pr69_native_receipt"]},
                "stage4_qg_bg": [pre[4]["qg"], pre[4]["brs"]],
                "stage5_qg_bg": [pre[5]["qg"], pre[5]["brs"]],
                "interpretation": "The tiny donor pair is created by rain freezing between stage 4 and stage 5, not inferred from a prior rho value.",
            },
        },
        "review_limit": "QG/BG gives a donor density near 1000 kg m-3, outside ProgB_param's 100–900 kg m-3 supported interval. The proportional debit identity is retained as an unvalidated relation and is not proposed as an accepted rule. Positive pgdep source-growth volume remains unsupported without a source density rule.",
        "fatal_semantics": "The controlled fatal rejection occurs before a post-call capture. It is not rollback and this run is not accepted native behavior or water-budget closure.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "events": len(events), "donor_density": donor["donor_density_qg_over_brs"], "status": receipt["runtime"]["input_integrity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
