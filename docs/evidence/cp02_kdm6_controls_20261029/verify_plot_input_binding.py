#!/usr/bin/env python3
"""Exercise the frozen plot inputs and reject a one-value profile mutation."""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]
ANALYSIS = EVIDENCE / "analysis"
PLOT_SCRIPT = EVIDENCE / "plot_kdm6_controls.py"
OUTPUT_PNG = EVIDENCE / "kdm6_qr_weighted_profiles.png"
OUTPUT_METADATA = EVIDENCE / "kdm6_qr_weighted_profiles.metadata.json"
RECEIPT = EVIDENCE / "plot_input_binding_check.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_plot(analysis_dir):
    return subprocess.run(
        [sys.executable, str(PLOT_SCRIPT), "--analysis-dir", str(analysis_dir),
         "--evidence-dir", str(EVIDENCE)],
        text=True, capture_output=True, check=False,
    )


def write_receipt(record):
    temporary = RECEIPT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, RECEIPT)


def main():
    valid_run = run_plot(ANALYSIS)
    if valid_run.returncode != 0:
        raise RuntimeError("canonical plot input failed: " + valid_run.stderr)
    valid_outputs = {"png_sha256": sha256(OUTPUT_PNG), "metadata_sha256": sha256(OUTPUT_METADATA)}

    profiles_path = ANALYSIS / "selected_profiles.csv"
    original_profiles_sha256 = sha256(profiles_path)
    with tempfile.TemporaryDirectory(prefix="cp02-kdm6-mutated-plot-input-") as temp:
        mutated_analysis = Path(temp)
        shutil.copyfile(ANALYSIS / "summary.json", mutated_analysis / "summary.json")
        with profiles_path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            fieldnames = reader.fieldnames
            rows = list(reader)
        old_value = float(rows[0]["qr"])
        rows[0]["qr"] = repr(old_value + 0.001)
        altered_profiles = mutated_analysis / "selected_profiles.csv"
        with altered_profiles.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        altered_profiles_sha256 = sha256(altered_profiles)
        before_tampered_run = {"png_sha256": sha256(OUTPUT_PNG),
                               "metadata_sha256": sha256(OUTPUT_METADATA)}
        rejected_run = run_plot(mutated_analysis)
        after_tampered_run = {"png_sha256": sha256(OUTPUT_PNG),
                              "metadata_sha256": sha256(OUTPUT_METADATA)}

    if rejected_run.returncode == 0:
        raise AssertionError("plot accepted a changed qr value")
    if "analyzer_selected_profiles SHA-256 differs from frozen plot input" not in rejected_run.stderr:
        raise AssertionError("altered profile was rejected for an unexpected reason: " + rejected_run.stderr)
    if before_tampered_run != after_tampered_run or valid_outputs != after_tampered_run:
        raise AssertionError("altered profile changed an existing plot output")

    record = {
        "schema": "cp02-kdm6-plot-input-binding-check-v1",
        "status": "PASS_CANONICAL_ACCEPTED_MUTATED_PROFILE_REJECTED_OUTPUTS_PRESERVED",
        "script": {"path": PLOT_SCRIPT.relative_to(ROOT).as_posix(), "sha256": sha256(PLOT_SCRIPT)},
        "inputs": {
            "summary_sha256": sha256(ANALYSIS / "summary.json"),
            "canonical_selected_profiles_sha256": original_profiles_sha256,
            "mutated_selected_profiles_sha256": altered_profiles_sha256,
            "initial_fields_sha256": sha256(EVIDENCE / "inputs/selected_initial_fields.csv"),
        },
        "canonical_run": {"exit_code": valid_run.returncode, **valid_outputs},
        "mutation": {
            "field": "qr", "row_index": 0, "original_value": repr(old_value),
            "mutated_value": repr(old_value + 0.001),
            "rejected_exit_code": rejected_run.returncode,
            "rejection": "analyzer_selected_profiles SHA-256 differs from frozen plot input",
            "existing_output_hashes_before": before_tampered_run,
            "existing_output_hashes_after": after_tampered_run,
        },
    }
    write_receipt(record)
    print(json.dumps({"receipt": str(RECEIPT), "status": record["status"]}, indent=2))


if __name__ == "__main__":
    main()
