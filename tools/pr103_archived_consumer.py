#!/usr/bin/env python3
"""Run one candidate archived calc_ww_cp call and assess its fixed native bounds."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np

import pr86_time_response as runner
import pr102_archived_consumer as archived
import pr102_native_ww_bound as bound
import pr99_native_consumer_metrics as metrics
import pr99_native_consumer_replay as native


ROOT = Path(__file__).resolve().parents[1]
PR102_CANONICAL_H_WW = Path("/var/tmp/pr102_archived_consumer_20261025/reference_hydro/native_consumer_ww.bin")
PR102_CANONICAL_H_WW_SHA256 = "71ea495f0897a07c84be63bcf2ae7a168f59d32fa6546fd7e42a118d8b0f1707"
PR102_CANONICAL_H_RECEIPT = ROOT / "docs/evidence/pr102_execution_20261025/archived_consumer/assessment_receipt.json"
PR102_CANONICAL_H_RECEIPT_SHA256 = "e91be241a9782a0b0be388437af24f2cc40ec56a2db3a342f5362cc9149faf59"


def _pin(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": runner.sha256(path)}


def _require(path: Path, digest: str) -> dict:
    pin = _pin(path)
    if pin["sha256"] != digest:
        raise ValueError(f"pinned archived-consumer artifact changed: {path}")
    return pin


def _proposal_receipt(path: Path) -> tuple[dict, dict]:
    binding = runner._amplitude_control_input_binding(path)
    return json.loads(path.read_text()), binding


def _root_go(path: Path, proposal: dict, binding: dict, output: Path) -> dict:
    pin = _pin(path)
    go = json.loads(path.read_text())
    if (go.get("schema") != "pr103_archived_consumer_go_v1" or
            go.get("status") != "GO" or go.get("launch_authorized") is not True or
            go.get("proposal_sha256") != binding["receipt_sha256"] or
            go.get("candidate_wrfinput_sha256") != binding["artifacts"]["candidate"]["sha256"] or
            go.get("archived_consumer_executable_sha256") != archived.EXECUTABLE_SHA or
            go.get("compiler_profile_sha256") != archived.PROFILE_SHA or
            Path(go.get("output_directory", "")).resolve() != output.resolve()):
        raise ValueError("PR103 archived-consumer root GO does not authorize this exact call")
    return {**pin, "proposal_sha256": binding["receipt_sha256"],
            "candidate_wrfinput_sha256": binding["artifacts"]["candidate"]["sha256"],
            "output_directory": str(output.resolve())}


def _read_arrays(path: Path) -> dict[str, np.ndarray]:
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_mask(False)
        arrays, *_ = native.native_arrays(dataset, 0)
    return arrays


def _validate_archived_consumer_pins() -> list[dict]:
    pins = [
        _require(archived.EXECUTABLE, archived.EXECUTABLE_SHA),
        _require(archived.PROFILE, archived.PROFILE_SHA),
        _require(archived.native.DRIVER, archived.DRIVER_SHA),
        _require(archived.CANONICAL, archived.CANONICAL_SHA),
        _require(archived.MEMBER_PROOF, archived.MEMBER_PROOF_SHA),
    ]
    canonical_record = json.loads(archived.CANONICAL.read_text())
    canonical = canonical_record.get("provenance", {})
    proof = json.loads(archived.MEMBER_PROOF.read_text())
    if (canonical.get("standalone_executable_sha256") != archived.EXECUTABLE_SHA or
            canonical.get("driver_sha256") != archived.DRIVER_SHA or
            canonical.get("intel_profile_sha256") != archived.PROFILE_SHA or
            proof.get("status") != "BYTE_IDENTICAL" or
            len(proof.get("cohorts", [])) != 2):
        raise ValueError("archived native consumer provenance does not match")
    return pins


def assess(proposal_path: Path, output: Path, root_go_path: Path | None = None,
           execute: bool = False) -> dict:
    proposal_path = proposal_path.resolve()
    proposal, binding = _proposal_receipt(proposal_path)
    if not execute:
        return {"schema": "pr103_archived_consumer_plan_v1", "status": "PLAN_ONLY",
                "proposal": _pin(proposal_path), "candidate_wrfinput_sha256":
                    binding["artifacts"]["candidate"]["sha256"],
                "consumer_executable": _require(archived.EXECUTABLE, archived.EXECUTABLE_SHA),
                "hydro_reference_output": _require(PR102_CANONICAL_H_WW,
                                                     PR102_CANONICAL_H_WW_SHA256),
                "launch_authorized": False}
    if root_go_path is None:
        raise ValueError("an explicit PR103 archived-consumer root GO is required for execution")
    go = _root_go(root_go_path, proposal, binding, output)
    _validate_archived_consumer_pins()
    archived.require_fresh_directory(output)
    output.mkdir(parents=True, exist_ok=False)

    hydro_input = Path(binding["artifacts"]["reference_hydro"]["path"])
    candidate_input = Path(binding["artifacts"]["candidate"]["path"])
    composition_path = Path(binding["artifacts"]["composition"]["path"])
    hydro_reference = _require(PR102_CANONICAL_H_WW, PR102_CANONICAL_H_WW_SHA256)
    canonical_assessment = _require(PR102_CANONICAL_H_RECEIPT,
                                    PR102_CANONICAL_H_RECEIPT_SHA256)
    canonical_record = json.loads(PR102_CANONICAL_H_RECEIPT.read_text())
    if (canonical_record.get("dry_mass_check", {}).get("status") != "PASS" or
            canonical_record.get("candidate_wrfinput_sha256") != binding["artifacts"]["reference_structured"]["sha256"]):
        raise ValueError("reused HYDRO consumer output is not pinned by the closed PR102 reference assessment")
    before = [_pin(path) for path in (proposal_path, candidate_input, hydro_input,
              composition_path, archived.EXECUTABLE, archived.PROFILE, archived.MPI_ENV,
              archived.native.DRIVER, archived.CANONICAL, archived.MEMBER_PROOF,
              Path(archived.native.__file__), Path(archived.__file__), Path(runner.__file__),
              Path(bound.__file__), Path(bound.cloud.__file__), Path(metrics.__file__),
              Path(archived.unlimited_stack.__code__.co_filename),
              PR102_CANONICAL_H_WW, PR102_CANONICAL_H_RECEIPT)]

    candidate_run = archived.run_case(candidate_input,
                                      binding["artifacts"]["candidate"]["sha256"],
                                      output / "candidate")
    if candidate_run.get("status") != "COMPLETE" or candidate_run.get("returncode") != 0:
        raise ValueError("PR103 archived calc_ww_cp call did not complete")
    candidate_ww_path = output / "candidate/native_consumer_ww.bin"
    candidate_ww = metrics.read_ww(candidate_ww_path)
    hydro_ww = metrics.read_ww(PR102_CANONICAL_H_WW)
    comparison = bound.compare_actual(_read_arrays(candidate_input), _read_arrays(hydro_input),
                                      candidate_ww, hydro_ww, composition_path)
    after = [_pin(Path(row["path"])) for row in before]
    if before != after:
        raise ValueError("PR103 consumer input or pinned source changed during the archived call")
    gates = {name: comparison[name] for name in ("reference_constraint", "source_arithmetic")}
    passed = comparison.get("status") == "PASS" and all(row.get("status") == "PASS"
                                                          for row in gates.values())
    dependencies = [
        *before,
        {"path": go["path"], "sha256": go["sha256"]},
        _pin(composition_path), _pin(Path(__file__).resolve()),
        hydro_reference, canonical_assessment,
        _pin(output / "candidate/receipt.json"), _pin(output / "candidate/launch.json"),
        _pin(output / "candidate/run.log"), _pin(output / "candidate/native_consumer_input.bin"),
        _pin(candidate_ww_path),
    ]
    receipt = {
        "schema": "pr103_archived_consumer_assessment_v1",
        "status": "PASS" if passed else "FAIL",
        "execution_status": "COMPLETE",
        "proposal": _pin(proposal_path),
        "candidate_wrfinput_sha256": binding["artifacts"]["candidate"]["sha256"],
        "candidate_parent_sha256": binding["artifacts"]["original_p"]["sha256"],
        "archived_consumer_executable": _pin(archived.EXECUTABLE),
        "compiler_profile": _pin(archived.PROFILE),
        "base_c2_executable_sha256": runner.PR102_BASE_C2_EXECUTABLE_SHA256,
        "actual_call": {"arm": "AMPLITUDE", "receipt": _pin(output / "candidate/receipt.json"),
                        "output": _pin(candidate_ww_path),
                        "reference_hydro_output": hydro_reference,
                        "reference_hydro_assessment": canonical_assessment},
        "gates": gates,
        "comparison": comparison,
        "source_bindings_before": before,
        "source_bindings_after": after,
        "root_go": go,
        "artifacts": dependencies,
        "physical_approval": "FAIL_OPEN",
        "observation_skill": "NOT_EVALUATED",
        "scope": "One archived calc_ww_cp call on final stored A; H output reused from the closed PR102 canonical run.",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    target = output / "assessment.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-go", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = assess(args.proposal, args.output, args.root_go, args.execute)
    print(json.dumps({"schema": result["schema"], "status": result["status"],
                      "output": str(args.output.resolve()),
                      "candidate_wrfinput_sha256": result["candidate_wrfinput_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
