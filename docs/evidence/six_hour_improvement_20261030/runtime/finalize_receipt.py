#!/usr/bin/env python3
"""Bind the raw six-hour runtime receipt to preflight and prefix comparison."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import netCDF4
import numpy as np


HERE = Path(__file__).resolve().parent
SCRATCH = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
SOURCE = Path("/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    raw_path = HERE / "receipt.json"
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    preflight_path = HERE / "preflight.json"
    preflight_bytes = preflight_path.read_bytes()
    preflight = json.loads(preflight_bytes)
    compare_path = HERE / "one_hour_comparison.json"
    compare_bytes = compare_path.read_bytes()
    comparison = json.loads(compare_bytes)
    assert raw["status"] == "SUCCESS" and raw["exit"] == 0 and raw["success_marker"]
    assert raw["histories_exact"] and len(raw["histories"]) == 7
    assert raw["staged_inputs_unchanged"] and raw["policy_source_inputs_unchanged"] and raw["existing_evidence_unchanged"]
    assert comparison["whole_file_exact"]
    assert comparison["current_sha256"] == raw["output_sha256"]["wrfout_d01_2026-08-16_13:00:00"]
    assert preflight["status"] == "PASS"
    assert preflight["candidate_executable_sha256"] == "68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f"
    assert preflight["candidate_native_input_sha256"] == "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5"
    assert preflight["boundary_sha256"] == "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45"
    assert preflight["history_interval_s"] == 3600
    assert preflight["input_changes"]["namelist.input"] == {
        "history_end_s": ["3600", "21600"], "run_hours": ["1", "6"], "end_hour": ["13", "18"]
    }

    staged_after = {name: sha256(SCRATCH / name) for name in preflight["staged_sha256"]}
    source_after = {name: sha256(SOURCE / name) for name in preflight["policy_source_sha256_before"]}
    assert staged_after == raw["staged_sha256_after"] == preflight["staged_sha256"]
    assert source_after == raw["policy_source_sha256_after"] == preflight["policy_source_sha256_before"]
    for name, digest in raw["output_sha256"].items():
        assert sha256(SCRATCH / name) == digest
    validated = []
    for name in raw["histories"]:
        expected_time = name.removeprefix("wrfout_d01_")
        with netCDF4.Dataset(SCRATCH / name) as dataset:
            times = netCDF4.chartostring(dataset["Times"][:]).tolist()
            assert times == [expected_time], (name, times)
            for field in ("RAINC", "RAINNC", "RAINSH"):
                values = dataset[field][:]
                assert not np.ma.is_masked(values) and np.isfinite(values).all(), (name, field)
        validated.append({"name": name, "time": expected_time, "sha256": raw["output_sha256"][name]})
    history_validation = {
        "status": "PASS",
        "history_count": len(validated),
        "histories": validated,
        "checked_variables": ["Times", "RAINC", "RAINNC", "RAINSH"],
        "finite_unmasked_precipitation_fields": True,
    }
    (HERE / "history_validation.json").write_text(json.dumps(history_validation, indent=2) + "\n")

    (SCRATCH / "raw_receipt.json").write_bytes(raw_bytes)
    shutil.copy2(HERE / "inputs.json", SCRATCH / "runtime_inputs.json")
    normalized = {
        **raw,
        "factorial_cell": "H1xB1 / IMPROVED_BG_FIXED",
        "staged_unchanged": raw["staged_inputs_unchanged"],
        "source_unchanged": raw["policy_source_inputs_unchanged"] and raw["existing_evidence_unchanged"],
        "source_before": preflight["policy_source_sha256_before"],
        "source_after": raw["policy_source_sha256_after"],
        "raw_receipt_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_receipt_path": str(raw_path),
        "preflight_sha256": hashlib.sha256(preflight_bytes).hexdigest(),
        "preflight_path": str(preflight_path),
        "one_hour_comparison_sha256": hashlib.sha256(compare_bytes).hexdigest(),
        "one_hour_comparison_path": str(compare_path),
        "contract": {
            "fixed_executable_sha256": preflight["candidate_executable_sha256"],
            "policy_wrfinput_sha256": preflight["candidate_native_input_sha256"],
            "boundary_sha256": preflight["boundary_sha256"],
            "one_hour_namelist_sha256": preflight["one_hour_namelist_sha256"],
            "six_hour_namelist_sha256": preflight["six_hour_namelist_sha256"],
            "namelist_changes": preflight["input_changes"]["namelist.input"],
            "history_interval_s": preflight["history_interval_s"],
        },
    }
    normalized_bytes = (json.dumps(normalized, indent=2) + "\n").encode()
    (HERE / "normalized_receipt.json").write_bytes(normalized_bytes)
    (SCRATCH / "receipt.json").write_bytes(normalized_bytes)

    script_hashes = json.loads((HERE / "scripts.sha256.json").read_text())
    assert {name: sha256(HERE / name) for name in script_hashes} == script_hashes
    source_paths = preflight["policy_source_sha256_before"]
    symlinks = [name for name in source_paths if (SOURCE / name).is_symlink()]
    link_audit = {
        "declared_source_count": len(source_paths),
        "source_symlink_count": len(symlinks),
        "source_symlink_names": symlinks,
        "all_source_paths_regular_files": all((SOURCE / name).is_file() and not (SOURCE / name).is_symlink() for name in source_paths),
        "linked_targets_count": 0 if not symlinks else None,
    }
    assert link_audit["declared_source_count"] == 89 and not symlinks and link_audit["all_source_paths_regular_files"]
    (HERE / "source_link_audit.json").write_text(json.dumps(link_audit, indent=2) + "\n")

    binding = {
        "raw_receipt_sha256": sha256(raw_path),
        "preflight_sha256": sha256(preflight_path),
        "one_hour_comparison_sha256": sha256(compare_path),
        "normalized_receipt_sha256": hashlib.sha256(normalized_bytes).hexdigest(),
        "staged_input_count": len(staged_after),
        "history_output_count": len(raw["output_sha256"]),
        "history_validation_sha256": sha256(HERE / "history_validation.json"),
        "history_validation_passed": history_validation["status"] == "PASS",
        "staged_inputs_revalidated": True,
        "source_inputs_revalidated": True,
        "outputs_revalidated": True,
        "first_hour_exact_match": comparison["whole_file_exact"],
        "boundary_namelist_contract_revalidated": True,
        "launch_script_hashes": script_hashes,
    }
    (HERE / "normalization_manifest.json").write_text(json.dumps(binding, indent=2) + "\n")
    print(json.dumps(binding, indent=2))


if __name__ == "__main__":
    main()
