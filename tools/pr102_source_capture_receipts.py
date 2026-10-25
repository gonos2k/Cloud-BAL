#!/usr/bin/env python3
"""Bind closed PR102 H/P/N diagnostic captures to their noninterference proofs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
RUNS = ROOT / "pr102_native_structure20_capture_20261025"
EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/pr102_execution_20261025"
BASE_EXE = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
DIAGNOSTIC_EXE = "aca04cd72a886d41fedcae51e2bbb9cc0b03688e4b9db96ddd12ebc62981b6e0"
BUILD = Path("/var/tmp/pr102_c2_native_capture_build_v3_20261025/pr102_c2_native_capture_build.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def checked_rows(rows: list[dict]) -> list[dict]:
    unique = {}
    for row in rows:
        path = Path(row["path"]).resolve()
        digest = sha256(path)
        if digest != row["sha256"]:
            raise ValueError(f"evidence changed: {path}")
        unique[str(path)] = {"path": str(path), "sha256": digest}
    return list(unique.values())


def make_receipt(label: str, capture: dict, proof_path: Path, identity_path: Path,
                 control: dict, control_label: str) -> Path:
    run_path = Path(capture["diagnostic_receipt"]["path"])
    run = json.loads(run_path.read_text())
    if (run.get("status") != "COMPLETE" or run.get("returncode") != 0 or
            run.get("final_completed_step") != 1 or
            run.get("candidate_wrfinput_sha256") != capture["candidate_input_sha256"] or
            ref(run_path) != capture["diagnostic_receipt"]):
        raise ValueError(f"{label} run receipt is not closed as expected")
    if capture.get("diagnostic_executable_sha256") != DIAGNOSTIC_EXE:
        raise ValueError(f"{label} uses an unexpected diagnostic executable")
    build_ref = ref(BUILD)
    build = json.loads(BUILD.read_text())
    if (build.get("schema") != "pr102_c2_native_capture_build_v1" or
            build.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
            build.get("base_c2_executable_sha256") != BASE_EXE or
            build.get("executable_sha256") != DIAGNOSTIC_EXE):
        raise ValueError("shared diagnostic build receipt is not a passing C2 overlay")
    identity_ref = ref(identity_path)
    run_dir = run_path.parent / "run"
    source_rows = []
    for item in run.get("generated_files", []):
        name = Path(item["path"]).name
        if name.startswith("pr98_") and name.endswith(".bin"):
            source_rows.append({"path": str((run_dir / name).resolve()), "sha256": item["sha256"]})
    if len(source_rows) != 57:
        raise ValueError(f"{label} must bind all 57 PR98 source snapshots")
    if label == "CANDIDATE":
        analysis = json.loads(proof_path.read_text())
        proof_summary = {"status": "PASS", "evidence": ref(proof_path),
                         "launch_identity": identity_ref,
                         "t0": analysis["t0_history"]["status"],
                         "first20": analysis["first20_trace"]["status"],
                         "t1": analysis["t1_post"]["status"]}
    else:
        analysis = json.loads(proof_path.read_text())
        proof_summary = {"status": "PASS", "evidence": ref(proof_path),
                         "closed_control_identity": identity_ref,
                         "t0": analysis["controls"][control_label]["t0_history"]["status"],
                         "first20": analysis["controls"][control_label]["first20_trace"]["status"],
                         "t1": analysis["controls"][control_label]["t1_post"]["status"]}
    if any(proof_summary[key] != "PASS" for key in ("t0", "first20", "t1")):
        raise ValueError(f"{label} noninterference proof is incomplete")
    rows = [ref(run_path), build_ref, *source_rows, ref(proof_path), identity_ref,
            ref(Path(control["path"]))]
    if label == "CANDIDATE":
        baseline_root = Path(control["path"]).parent
        rows.extend(ref(baseline_root / name) for name in ("preflight.json", "launch_provenance.json"))
    else:
        control_root = Path(control["path"]).parent
        rows.append(ref(control_root / "preflight.json"))
    rows = checked_rows(rows)
    record = {"schema": "pr102_native_source_capture_v1", "status": "COMPLETE",
              "role": label, "candidate_wrfinput_sha256": capture["candidate_input_sha256"],
              "baseline_c2_executable_sha256": BASE_EXE,
              "diagnostic_executable_sha256": DIAGNOSTIC_EXE,
              "diagnostic_build_receipt": build_ref,
              "diagnostic_build_receipt_sha256": build_ref["sha256"],
              "captured_sources": ["RU", "RV", "MUDF"], "completed_steps": 1,
              "run_receipt": ref(run_path), "control_receipt": control,
              "namelist_sha256": run["candidate_namelist_sha256"],
              "boundary_sha256": run["candidate_wrfbdy_sha256"],
              "launch_environment": run["launch_environment"],
              "noninterference": proof_summary, "artifacts": rows}
    out = EVIDENCE / "source_captures" / f"{label.lower()}_source_capture.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return out


def main() -> None:
    hp_path = EVIDENCE / "hp20_capture_noninterference.json"
    n_path = EVIDENCE / "candidate_n20_capture_noninterference.json"
    hp, n = json.loads(hp_path.read_text()), json.loads(n_path.read_text())
    if hp.get("status") != "PASS_CAPTURE_NONINTERFERENCE" or n.get("status") != "PASS_CAPTURE_NONINTERFERENCE":
        raise ValueError("H/P/N runtime noninterference must pass before receipt creation")
    if json.loads(n_path.read_text()).get("diagnostic_build", {}).get("sha256") != ref(BUILD)["sha256"]:
        raise ValueError("N noninterference proof does not bind the current diagnostic build")
    n_identity = EVIDENCE / "n20_actual_launch_identity.json"
    if sha256(n_identity) != "021e4c112b0a678d1612e679b9a9722823f4c99039cd5e8976e3e97fd2a0320a":
        raise ValueError("N launch identity changed")
    hp_identity = EVIDENCE / "hp20_control_identity.json"
    if sha256(hp_identity) != "e64a20d90ee5f3f0e5c2e4eb4f9bbd345ed90b6f02a71b345067940f6e0f98fe":
        raise ValueError("H/P control identity changed")
    outputs = (
        make_receipt("HYDRO", hp["controls"]["HYDRO"], hp_path, hp_identity,
                     hp["controls"]["HYDRO"]["control_receipt"], "HYDRO"),
        make_receipt("ORIGINAL_P", hp["controls"]["PROJECTED"], hp_path, hp_identity,
                     hp["controls"]["PROJECTED"]["control_receipt"], "PROJECTED"),
        make_receipt("CANDIDATE", n, n_path, n_identity, n["control_receipt"], "BASELINE20"),
    )
    for path in outputs:
        print(path, sha256(path))


if __name__ == "__main__":
    main()
