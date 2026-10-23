#!/usr/bin/env python3
"""Prepare, but do not run, a receipt-bound PR87 overlay build plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_RECEIPT = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
BASE_RECEIPT_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
BUILDER = "tools/pr87_build_native_overlay.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_plan(transformed_module_em: Path, scratch: Path, receipt_path: Path = BASE_RECEIPT) -> dict:
    receipt_bytes = receipt_path.read_bytes()
    if receipt_path == BASE_RECEIPT and hashlib.sha256(receipt_bytes).hexdigest() != BASE_RECEIPT_SHA256:
        raise ValueError("receipt-pinned C2 base overlay identity changed")
    receipt = json.loads(receipt_bytes)
    if receipt.get("schema") != "pr87_native_overlay_build_v1" or receipt.get("status") != "PASS_OVERLAY_BUILD":
        raise ValueError("C2 receipt is not a successful native overlay build")
    if receipt.get("model_run") is not False:
        raise ValueError("C2 base build receipt unexpectedly includes a model run")
    if scratch.exists():
        raise ValueError(f"build scratch must be new: {scratch}")
    if not transformed_module_em.is_file() or b"MODULE pr101_upper_wind_capture" not in transformed_module_em.read_bytes():
        raise ValueError("transformed module_em source is missing PR101 observer module")

    overrides = {}
    baseline_override_hashes = {}
    for member, record in receipt["source_overrides"].items():
        if member == "module_em.o":
            overrides[member] = str(transformed_module_em.resolve())
            baseline_override_hashes[member] = record["requested_sha256"]
            continue
        source = Path(record["requested_path"])
        if sha256(source) != record["requested_sha256"]:
            raise ValueError(f"base C2 override changed: {member}")
        overrides[member] = str(source)
        baseline_override_hashes[member] = record["requested_sha256"]

    extra = receipt["extra_observer"]
    extra_source = Path(extra["requested_source_path"])
    if sha256(extra_source) != extra["requested_source_sha256"]:
        raise ValueError("base C2 extra observer source changed")
    return {
        "schema": "pr101_upper_wind_build_plan_v1",
        "execution": "NOT_RUN_REQUIRES_ROOT_REVIEW_AND_COMMON_GUARD_GO",
        "builder": BUILDER,
        "base_receipt": {"path": str(receipt_path), "sha256": sha256(receipt_path)},
        "base_overlay_executable_sha256": receipt["executable_sha256"],
        "base_archive_sha256": receipt["archive_sha256"],
        "transformed_module_em": {"path": str(transformed_module_em.resolve()),
                                   "sha256": sha256(transformed_module_em)},
        "baseline_override_hashes": baseline_override_hashes,
        "source_overrides": overrides,
        "extra_source": str(extra_source),
        "scratch": str(scratch),
        "builder_argv": ["python3", BUILDER, "--scratch", str(scratch),
                         "--source-overrides", json.dumps(overrides, separators=(",", ":")),
                         "--extra-source", str(extra_source), "--reproduction-profile"],
        "compiler_profile": {"path": receipt["compiler_profile_path"],
                              "sha256": receipt["compiler_profile_sha256"],
                              "compiler": receipt["compiler_path"],
                              "compiler_sha256": receipt["compiler_sha256"],
                              "version": receipt["compiler_version"]},
        "base_C2_inputs_and_namelist": "root common guard binds these; do not reuse C1 P20 inputs",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transformed-module-em", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overrides-output", type=Path, required=True)
    args = parser.parse_args()
    plan = make_plan(args.transformed_module_em, args.scratch, args.receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    args.overrides_output.write_text(json.dumps(plan["source_overrides"], indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
