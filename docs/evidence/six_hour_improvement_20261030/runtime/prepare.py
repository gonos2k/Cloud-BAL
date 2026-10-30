#!/usr/bin/env python3
"""Stage the six-hour improved B1 run from the sealed one-hour POLICY_BG case."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path


PLAN = Path("/var/tmp/firsthour-runtime-plan-20261030")
SOURCE = PLAN / "producer_pair/forecast/run_POLICY_BG"
SCRATCH = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
EVIDENCE = Path(__file__).resolve().parent
PRIOR_1H = SOURCE
BASELINE_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8")
EXPECTED = {
    "wrf.exe": "68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f",
    "wrfinput_d01": "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5",
    "namelist.input": "23f5c3cb94d44831c22d86a754fa30d242456d8d14cd70a72d89b00cdec4f3a3",
    "wrfbdy_d01": "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45",
}
POLICY_RECEIPT = SOURCE / "receipt.json"
BASELINE_RECEIPT = EVIDENCE.parents[1] / "current_forecast_paper_20261029/runtime/original_hydro_completed_receipt.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def set_once(text: str, field: str, old: str, new: str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(field)}\s*=\s*){re.escape(old)}(\s*,?\s*)$", re.MULTILINE | re.IGNORECASE)
    result, count = pattern.subn(rf"\g<1>{new}\g<2>", text)
    assert count == 1, (field, count)
    return result


def main() -> None:
    assert not SCRATCH.exists(), f"Refusing to overwrite {SCRATCH}"
    SCRATCH.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(SCRATCH.parent).free
    assert free_bytes > 5 * 1024**3, f"Only {free_bytes} bytes free before staging"
    declared = json.loads((SOURCE / "inputs.json").read_text())
    source_hashes = declared["staged"]
    assert len(source_hashes) == 89
    assert all((SOURCE / name).is_file() and not (SOURCE / name).is_symlink() for name in source_hashes)
    policy_receipt = json.loads(POLICY_RECEIPT.read_text())
    assert policy_receipt["exit"] == 0
    assert policy_receipt["success_marker"] and policy_receipt["histories_exact"]
    source_before = {name: sha256(SOURCE / name) for name in source_hashes}
    assert source_before == source_hashes
    for name, digest in EXPECTED.items():
        assert source_hashes[name] == digest
    assert EXPECTED["wrfbdy_d01"] == "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45"
    assert BASELINE_RECEIPT.is_file()
    baseline_receipt = json.loads(BASELINE_RECEIPT.read_text())
    assert baseline_receipt["ORIGINAL"]["status"] == "COMPLETE"

    previous_hour = PRIOR_1H / "wrfout_d01_2026-08-16_13:00:00"
    assert previous_hour.is_file()
    history_1h_sha = sha256(previous_hour)
    assert history_1h_sha == policy_receipt["output_sha256"][previous_hour.name]
    old_baseline_boundary = BASELINE_ROOT / "original/wrfbdy_d01"
    assert sha256(old_baseline_boundary) == EXPECTED["wrfbdy_d01"]
    baseline_18 = BASELINE_ROOT / "original/wrfout_d01_2026-08-16_18:00:00"
    assert baseline_18.is_file()

    evidence_paths = [
        SOURCE / "inputs.json", POLICY_RECEIPT,
        PRIOR_1H / "wrfout_d01_2026-08-16_12:00:00", previous_hour,
        BASELINE_RECEIPT, old_baseline_boundary, baseline_18,
    ]
    evidence_before = {str(path): sha256(path) for path in evidence_paths}
    SCRATCH.mkdir(parents=True)
    for name in source_hashes:
        shutil.copy2(SOURCE / name, SCRATCH / name)

    original_text = (SCRATCH / "namelist.input").read_text()
    extended = set_once(original_text, "history_end_s", "3600", "21600")
    extended = set_once(extended, "run_hours", "1", "6")
    extended = set_once(extended, "end_hour", "13", "18")
    (SCRATCH / "namelist.input").write_text(extended)
    changed = {
        "history_end_s": ("3600", "21600"),
        "run_hours": ("1", "6"),
        "end_hour": ("13", "18"),
    }
    assert "history_interval_s = 3600" in extended
    for field, (before, after) in changed.items():
        assert re.search(rf"^\s*{field}\s*=\s*{after}\b", extended, re.MULTILINE | re.IGNORECASE)
        assert re.search(rf"^\s*{field}\s*=\s*{before}\b", original_text, re.MULTILINE | re.IGNORECASE)

    staged = {name: sha256(SCRATCH / name) for name in source_hashes}
    assert all(staged[name] == source_hashes[name] for name in source_hashes if name != "namelist.input")
    assert staged["wrf.exe"] == EXPECTED["wrf.exe"]
    assert staged["wrfinput_d01"] == EXPECTED["wrfinput_d01"]
    assert staged["wrfbdy_d01"] == EXPECTED["wrfbdy_d01"]
    assert staged["namelist.input"] != source_hashes["namelist.input"]
    assert len(list(SCRATCH.iterdir())) == 89
    source_after = {name: sha256(SOURCE / name) for name in source_hashes}
    evidence_after = {str(path): sha256(path) for path in evidence_paths}
    assert source_after == source_before and evidence_after == evidence_before

    preflight = {
        "status": "PASS",
        "case": "IMPROVED_BG_FIXED",
        "scratch_directory": str(SCRATCH),
        "source_directory": str(SOURCE),
        "declared_input_count": len(staged),
        "input_changes": {"namelist.input": changed},
        "policy_source_sha256_before": source_before,
        "policy_source_sha256_after": source_after,
        "staged_sha256": staged,
        "existing_evidence_sha256_before": evidence_before,
        "existing_evidence_sha256_after": evidence_after,
        "candidate_executable_sha256": EXPECTED["wrf.exe"],
        "candidate_native_input_sha256": EXPECTED["wrfinput_d01"],
        "boundary_sha256": EXPECTED["wrfbdy_d01"],
        "one_hour_namelist_sha256": EXPECTED["namelist.input"],
        "six_hour_namelist_sha256": staged["namelist.input"],
        "history_interval_s": 3600,
        "prior_one_hour_history": str(previous_hour),
        "prior_one_hour_history_sha256": history_1h_sha,
        "six_hour_boundary_precedent": str(old_baseline_boundary),
        "six_hour_boundary_precedent_sha256": sha256(old_baseline_boundary),
        "existing_six_hour_history_18utc": str(baseline_18),
        "existing_six_hour_history_18utc_sha256": sha256(baseline_18),
    }
    (EVIDENCE / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    inputs = {
        "staged": staged,
        "source_policy_bg": source_before,
        "source_directory": str(SOURCE),
        "input_count": len(staged),
        "case": "IMPROVED_BG_FIXED",
        "executable_sha256": EXPECTED["wrf.exe"],
        "wrfinput_sha256": EXPECTED["wrfinput_d01"],
        "wrfbdy_sha256": EXPECTED["wrfbdy_d01"],
        "namelist_changes": changed,
    }
    (SCRATCH / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (EVIDENCE / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    print(json.dumps({
        "status": "PASS", "scratch_directory": str(SCRATCH),
        "declared_input_count": len(staged), "changed_file": "namelist.input",
        "namelist_changes": changed,
        "fixed_executable_sha256": EXPECTED["wrf.exe"],
        "policy_input_sha256": EXPECTED["wrfinput_d01"],
        "boundary_sha256": EXPECTED["wrfbdy_d01"],
        "boundary_covers_18utc_precedent": True,
        "prior_one_hour_history_sha256": history_1h_sha,
    }, indent=2))


if __name__ == "__main__":
    main()
