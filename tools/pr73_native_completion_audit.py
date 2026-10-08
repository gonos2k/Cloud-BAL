#!/usr/bin/env python3
"""Audit whether a PR73 native first-rejection run reached required post-call captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path

REQUIRED_POST_CALL = {
    "pr67_kdm6_process.raw": "KDM6 process observer output after the initial species preflight.",
    "pr69_water.raw": "Native water-budget observer output expected after the relevant KDM6 call.",
    "kdm6_first_call_post.raw": "KDM6 post-call trace written only after the KDM6 call returns.",
    "wrfout_d01_2026-08-16_12:00:20": (
        "Configured 20-second history endpoint for the 20-second run; requires the model step to finish."
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(native_receipt: Path, output: Path) -> dict[str, object]:
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite completion audit: {output}")
    receipt = json.loads(native_receipt.read_text(encoding="utf-8"))
    run_root = Path(receipt["run_root"])
    records = []
    for name, rationale in REQUIRED_POST_CALL.items():
        path = run_root / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            records.append({"path": name, "rationale": rationale, "status": "MISSING"})
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            records.append({"path": name, "rationale": rationale, "status": "INVALID_FILE_IDENTITY"})
            continue
        records.append({
            "path": name,
            "rationale": rationale,
            "status": "PRESENT",
            "size_bytes": info.st_size,
            "sha256": sha256(path),
        })
    missing = [item["path"] for item in records if item["status"] != "PRESENT"]
    result: dict[str, object] = {
        "schema": "pr73_native_completion_audit_v1",
        "status": "INCOMPLETE_REQUIRED_POST_CALL_OUTPUTS" if missing else "REQUIRED_POST_CALL_OUTPUTS_PRESENT",
        "native_receipt": str(native_receipt),
        "native_receipt_sha256": sha256(native_receipt),
        "native_run_root": str(run_root),
        "native_run_status": receipt.get("status"),
        "native_status": (
            "REJECTED"
            if receipt.get("status") == "CAPTURED_CONTROLLED_FIRST_REJECTION"
            and "KDM6_FIRST_VIOLATION|" in receipt.get("first_violation_line", "")
            else "UNCLASSIFIED"
        ),
        "native_returncode": receipt.get("returncode"),
        "native_declared_output_isolation": receipt.get("output_isolation"),
        "required_output_guard_status": "FAIL" if missing else "PASS",
        "scope_note": (
            "The original native receipt guarded the prior run's produced-output list. "
            "This independent audit checks post-call completion outputs even when the model exits early."
        ),
        "required_post_call_outputs": records,
        "missing_required_post_call_outputs": missing,
        "model_step_completion_evidence": (
            "NOT_ESTABLISHED" if missing else "ALL_REQUIRED_POST_CALL_OUTPUTS_PRESENT"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_receipt", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.native_receipt, args.output)
    print(f"PR73_NATIVE_COMPLETION {result['status']}")
    print(f"PR73_NATIVE_COMPLETION_MISSING {result['missing_required_post_call_outputs']}")


if __name__ == "__main__":
    main()
