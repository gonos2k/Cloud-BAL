#!/usr/bin/env python3
"""Write a compatibility receipt without changing the sealed raw run receipt."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRATCH = Path("/var/tmp/firsthour-factorial-runtime-20261030/run_BG_BASE")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    preflight = json.loads((HERE / "preflight.json").read_text())
    raw_path = HERE / "receipt.json"
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    assert raw["status"] == "SUCCESS"
    assert raw["exit"] == 0 and raw["success_marker"] and raw["histories_exact"]
    assert raw["staged_inputs_unchanged"]
    assert raw["policy_source_inputs_unchanged"]
    assert raw["existing_producer_evidence_unchanged"]
    assert len(preflight["staged_sha256"]) == 89

    staged_now = {name: sha256(SCRATCH / name) for name in preflight["staged_sha256"]}
    source_now = {
        name: sha256(Path(preflight["policy_source_directory"]) / name)
        for name in preflight["policy_source_sha256_before"]
    }
    assert staged_now == preflight["staged_sha256"]
    assert source_now == preflight["policy_source_sha256_before"]
    for name, digest in raw["output_sha256"].items():
        assert sha256(SCRATCH / name) == digest

    (SCRATCH / "raw_receipt.json").write_bytes(raw_bytes)
    shutil.copy2(HERE / "inputs.json", SCRATCH / "runtime_inputs.json")
    normalized = {
        "status": "SUCCESS",
        "factorial_cell": "H0xB1",
        "cell_definition": "original WRF executable with producer background-preserved input",
        "exit": raw["exit"],
        "success_marker": raw["success_marker"],
        "histories": raw["histories"],
        "histories_exact": raw["histories_exact"],
        "staged_unchanged": raw["staged_inputs_unchanged"],
        "source_unchanged": raw["policy_source_inputs_unchanged"] and raw["existing_producer_evidence_unchanged"],
        "staged_sha256": raw["staged_sha256_after"],
        "source_before": preflight["policy_source_sha256_before"],
        "source_after": raw["policy_source_sha256_after"],
        "producer_evidence_before": preflight["existing_evidence_sha256_before"],
        "producer_evidence_after": raw["existing_evidence_sha256_after"],
        "output_sha256": raw["output_sha256"],
        "start_utc": raw["start_utc"],
        "end_utc": raw["end_utc"],
        "elapsed_seconds": raw["elapsed_seconds"],
        "argv": raw["argv"],
        "scratch_directory": str(SCRATCH),
        "raw_evidence_receipt": str(raw_path),
        "raw_evidence_receipt_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "scope": raw["scope"],
    }
    normalized_bytes = (json.dumps(normalized, indent=2) + "\n").encode()
    (SCRATCH / "receipt.json").write_bytes(normalized_bytes)
    (HERE / "normalized_receipt.json").write_bytes(normalized_bytes)
    manifest = {
        "raw_receipt_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "normalized_receipt_sha256": hashlib.sha256(normalized_bytes).hexdigest(),
        "scratch_receipt_sha256": sha256(SCRATCH / "receipt.json"),
        "scratch_raw_receipt_sha256": sha256(SCRATCH / "raw_receipt.json"),
        "scratch_runtime_inputs_sha256": sha256(SCRATCH / "runtime_inputs.json"),
        "staged_input_count": len(staged_now),
        "staged_inputs_revalidated": True,
        "source_inputs_revalidated": True,
        "outputs_revalidated": True,
    }
    (HERE / "normalization_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
