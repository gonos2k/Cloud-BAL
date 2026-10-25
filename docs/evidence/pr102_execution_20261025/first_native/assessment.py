#!/usr/bin/env python3
"""Prepare a receipt-pinned descriptive report for the closed PR102 H/P/N captures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50")
TOOLS = ROOT / "scratch/pr102_wind_structure_20261025/Cloud-BAL/tools"
sys.path.insert(0, str(TOOLS))
import netCDF4
import numpy as np
import pr102_response as response
import pr102_execution_preflight as execution
import pr98_native_effect as native
import pr99_native_mass_effect as mass_effect

EXPECTED_TOOL_HASHES = {
    "pr102_response.py": "9e30de564c85b5cfdbb8c9141d3f86f68d2958582892c62ad7578c77affe866e",
    "pr98_native_effect.py": "985b40b93f4cf1f7dc0246efa9f837d621a06b52e6d49171f05f92c5c82459d5",
    "pr102_execution_preflight.py": "e80f5fc69e4b8cc7ee4dbe0281265faa7f1a97c9856c1be52e02a42ab9900277",
    "pr99_native_mass_effect.py": "a0e4d8487b105799d13a2332dfa5f21896b50ac1b0806eebe80ff354531c1e3f",
    "pr86_compare_response.py": "64b2f97f452035cae328576d26216c54877fa778b3eeabe17cdb9980103aaa5c",
    "pr87_native_history.py": "d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71",
    "pr95_call_budget.py": "b7ca2a0d4c5f56ecd9c2628c1d8f47b8131d8a0bbb4e12ce047281673159961f",
    "pr94_cloud_response.py": "a626b22f234b3095202982a4fe32d89d9ab6c200e4a9547f6a06a8b109536537",
    "pr98_native_capture.py": "0ce97110281f2196c5d2731c9fb5322da93376aad3f4ba4ab977e268149c4c8d",
    "pr102_native_wind_candidate.py": "f044c57605942504a0c8ece22b915e8bd64bc2ddacb46a9cecd6920081f15b85",
    "pr86_time_response.py": "35adaa773773c046311d731ea1426821befb225a444092405098b4ee4e8baa43",
}
CONSTANTS_SHA256 = "7b6cc54597b1d67c35ec112decab192cae3d1d5035ec03f5fb418a081df38670"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def code_pins() -> list[dict]:
    paths = {TOOLS / name: expected for name, expected in EXPECTED_TOOL_HASHES.items()}
    paths[Path(mass_effect.CONSTANTS)] = CONSTANTS_SHA256
    script = Path(__file__).resolve()
    actual = []
    for path, expected in sorted(paths.items(), key=lambda row: str(row[0])):
        observed = sha256(path)
        if observed != expected:
            raise ValueError(f"frozen first-native source changed: {path}")
        actual.append({"path": str(path), "sha256": observed})
    actual.append({"path": str(script), "sha256": sha256(script)})
    return actual


def artifact_pins(preflight: dict, preflight_path: Path, roots: dict[str, Path],
                  receipts: dict[str, dict]) -> list[dict]:
    pins = {Path(row["path"]).resolve(): row["sha256"]
            for row in preflight.get("evidence_artifacts", [])}

    def add_pin(path: Path, expected: str) -> None:
        path = path.resolve()
        if path in pins and pins[path] != expected:
            raise ValueError(f"conflicting receipt hashes for artifact: {path}")
        pins[path] = expected

    add_pin(preflight_path, sha256(preflight_path))
    for role, root in roots.items():
        add_pin(root / "wrfinput_d01", receipts[role]["input_sha256"])
    result = []
    for path, expected in sorted(pins.items(), key=lambda pair: str(pair[0])):
        observed = sha256(path)
        if observed != expected:
            raise ValueError(f"candidate-bound input artifact changed: {path}")
        result.append({"path": str(path), "sha256": observed})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-preflight", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="must not exist; refuses replacement")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing non-fresh output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)

    code_before = code_pins()
    preflight_path = args.execution_preflight.resolve()
    preflight = json.loads(preflight_path.read_text())
    response._verify_execution_preflight(preflight)
    control_rows = execution._controls()
    source_roots, source_receipts = response._source_capture_roots(preflight)
    expected_inputs = {"H": control_rows["HYDRO"]["candidate_wrfinput_sha256"],
                       "P": control_rows["PROJECTED"]["candidate_wrfinput_sha256"],
                       "N": preflight["candidate_wrfinput_sha256"]}
    if {role: row["input_sha256"] for role, row in source_receipts.items()} != expected_inputs:
        raise ValueError("H/P/N source captures differ from the receipt-pinned control/candidate inputs")
    masks, composition_sha = response._fixed_masks(native.COMPOSITION)
    roots_for_inputs = {role: source_roots[role] for role in ("H", "P", "N")}
    artifacts_before = artifact_pins(preflight, preflight_path, roots_for_inputs, source_receipts)

    source_raw = native.analyze_native_capture(
        {"OFF": source_roots["H"], "HYDRO": source_roots["P"], "COUPLED": source_roots["N"]},
        masks["support"])
    source_response = response._rename_source_roles(source_raw)
    source_response["source_capture_role_mapping"] = {"H": "HYDRO", "P": "original P", "N": "candidate"}
    dry_rates = response._dry_column_rates(source_roots, source_receipts, masks["support"])
    artifacts_after = artifact_pins(preflight, preflight_path, roots_for_inputs, source_receipts)
    code_after = code_pins()
    if artifacts_before != artifacts_after:
        raise ValueError("a pinned source capture, input, or preflight artifact changed during assessment")
    if code_before != code_after:
        raise ValueError("a frozen response source changed during assessment")

    script_path = Path(__file__).resolve()
    report = {"schema": "pr102_first_native_response_v1", "status": "DESCRIPTIVE_ONLY",
              "assessment_scope": "one-step H/P/N native source capture only; no 640-second output opened",
              "source": {"source_code_pins_before": code_before,
                         "source_code_pins_after": code_after,
                         "execution_preflight": {"path": str(preflight_path), "sha256": sha256(preflight_path)},
                         "composition_sha256": composition_sha,
                         "runtime": {"numpy": np.__version__, "netCDF4": netCDF4.__version__}},
              "source_capture_receipts": source_receipts,
              "pre_artifact_pins": artifacts_before, "post_artifact_pins": artifacts_after,
              "native_source_coordinate_response": source_response,
              "physical_dry_column_rate": dry_rates,
              "limits": ["Raw RU/RV remain native source-coordinate diagnostics; MUDF and dry-column rate use separate stages and units.",
                         "The MU update versus combined MUDF comparison is descriptive, not a continuity-flux closure.",
                         "No response-derived cutoff or observation-skill claim is made."],
              "observation_skill": "NOT_EVALUATED", "physical_approval": "FAIL_OPEN"}
    with (output_dir / "first_native_response.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
