#!/usr/bin/env python3
"""Stage the one missing first-hour factorial cell without changing its inputs."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


PLAN = Path("/var/tmp/firsthour-runtime-plan-20261030")
POLICY_RUN = PLAN / "producer_pair/forecast/run_POLICY_BG"
BASE_EXE = PLAN / "experiment/run_BASE_H/wrf.exe"
NATIVE_INPUT = PLAN / "producer_pair/native_HYDRO_BACKGROUND_PRECIP/real/wrfinput_d01"
DEST = Path("/var/tmp/firsthour-factorial-runtime-20261030/run_BG_BASE")
OUT = Path(__file__).resolve().parent
EXPECTED = {
    "wrf.exe": "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168",
    "wrfinput_d01": "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5",
    "namelist.input": "23f5c3cb94d44831c22d86a754fa30d242456d8d14cd70a72d89b00cdec4f3a3",
    "wrfbdy_d01": "74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    declared = json.loads((POLICY_RUN / "inputs.json").read_text())
    source_hashes = declared["staged"]
    assert len(source_hashes) == 89, len(source_hashes)
    policy_receipt = json.loads((POLICY_RUN / "receipt.json").read_text())
    assert policy_receipt["exit"] == 0
    assert all(policy_receipt[key] for key in ("success_marker", "histories_exact", "staged_unchanged", "source_unchanged", "evidence_unchanged"))
    assert not DEST.exists(), f"Refusing to overwrite {DEST}"

    before = {name: sha256(POLICY_RUN / name) for name in source_hashes}
    assert before == source_hashes, "POLICY_BG declared inputs changed"
    assert sha256(BASE_EXE) == EXPECTED["wrf.exe"]
    assert sha256(NATIVE_INPUT) == EXPECTED["wrfinput_d01"]
    assert all(source_hashes[name] == digest for name, digest in EXPECTED.items() if name != "wrf.exe")
    assert sha256(POLICY_RUN / "wrf.exe") == source_hashes["wrf.exe"]

    native_receipt = PLAN / "producer_pair/native_HYDRO_BACKGROUND_PRECIP/receipt.json"
    producer_receipt = PLAN / "producer_pair/run_HYDRO_BACKGROUND_PRECIP/receipt.json"
    scoped_check = PLAN / "producer_pair/policy_scoped_check.json"
    source_receipt = PLAN / "experiment/run_FIX_H/receipt.json"
    evidence_paths = [
        POLICY_RUN / "inputs.json", POLICY_RUN / "receipt.json", BASE_EXE,
        NATIVE_INPUT, native_receipt, producer_receipt,
        PLAN / "producer_pair/run_HYDRO_BACKGROUND_PRECIP/output.wps.shadow.nc",
        PLAN / "producer_pair/build_receipt.json", scoped_check, source_receipt,
        PLAN / "experiment/run_FIX_H/inputs.json",
    ]
    evidence_before = {str(path): sha256(path) for path in evidence_paths}
    DEST.mkdir(parents=True)
    for name in source_hashes:
        shutil.copy2(BASE_EXE if name == "wrf.exe" else POLICY_RUN / name, DEST / name)

    staged = {name: sha256(DEST / name) for name in source_hashes}
    assert staged == {**source_hashes, "wrf.exe": EXPECTED["wrf.exe"]}
    assert staged["wrfinput_d01"] == EXPECTED["wrfinput_d01"]
    assert staged["namelist.input"] == EXPECTED["namelist.input"]
    assert staged["wrfbdy_d01"] == EXPECTED["wrfbdy_d01"]
    assert len(list(DEST.iterdir())) == 89
    assert {name: sha256(POLICY_RUN / name) for name in source_hashes} == before
    assert {str(path): sha256(path) for path in evidence_paths} == evidence_before

    preflight = {
        "status": "PASS",
        "cell": "producer-background-preserved x original-WRF",
        "scratch_directory": str(DEST),
        "policy_source_directory": str(POLICY_RUN),
        "original_executable": str(BASE_EXE),
        "declared_input_count": len(staged),
        "only_declared_input_changed_from_POLICY_BG": "wrf.exe",
        "staged_sha256": staged,
        "policy_source_sha256_before": before,
        "policy_source_sha256_after": {name: sha256(POLICY_RUN / name) for name in source_hashes},
        "existing_evidence_sha256_before": evidence_before,
        "existing_evidence_sha256_after": {str(path): sha256(path) for path in evidence_paths},
        "candidate_native_input_sha256": sha256(NATIVE_INPUT),
        "policy_runtime_receipt": str(POLICY_RUN / "receipt.json"),
        "expected_namelist_sha256": EXPECTED["namelist.input"],
        "expected_boundary_sha256": EXPECTED["wrfbdy_d01"],
    }
    (OUT / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
    staged_inputs = {
        "staged": staged,
        "source_policy_bg": before,
        "original_executable": EXPECTED["wrf.exe"],
        "candidate_native_input": EXPECTED["wrfinput_d01"],
        "policy_source_directory": str(POLICY_RUN),
        "original_executable_path": str(BASE_EXE),
        "input_count": len(staged),
        "factorial_cell": "H0xB1 (original executable x policy input)",
    }
    (DEST / "inputs.json").write_text(json.dumps(staged_inputs, indent=2) + "\n")
    (OUT / "inputs.json").write_text(json.dumps(staged_inputs, indent=2) + "\n")
    print(json.dumps({key: preflight[key] for key in (
        "status", "cell", "scratch_directory", "declared_input_count",
        "only_declared_input_changed_from_POLICY_BG", "candidate_native_input_sha256",
        "expected_namelist_sha256", "expected_boundary_sha256",
    )}, indent=2))


if __name__ == "__main__":
    main()
