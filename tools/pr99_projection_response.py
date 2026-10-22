#!/usr/bin/env python3
"""Compare a receipt-closed PR99 proposal capture with the frozen three-arm C1 captures."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import pr98_native_effect as native
import pr86_time_response as runner
from pr87_native_history import _constants, _finite
from pr95_call_budget import _read_map_geometry
from pr99_native_mass_effect import column_mass_rate, CONSTANTS


def capture_identity(binding):
    """Checkout copies may move; keep their source/manifest/inventory hashes."""
    result = {key: value for key, value in binding.items()
              if key not in {"capture_builder_source_path", "arms"}}
    result["arms"] = {
        arm: {key: value for key, value in row.items()
              if key not in {"manifest_path", "inventory_path"}}
        for arm, row in binding["arms"].items()}
    return result


def validate_closed_capture(receipt, preflight):
    """Require a clean one-step receipt before opening any proposal state file."""
    expected_times = receipt.get("expected_model_timestamps")
    actual_times = [row["timestamp"] for row in receipt.get("model_timestamps", [])]
    if (receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0
            or receipt.get("arm") != "COUPLED" or preflight.get("arm") != "COUPLED"
            or preflight.get("duration_seconds") != 20
            or receipt.get("final_completed_step") != 1 or receipt.get("timestep_count") != 1
            or receipt.get("maximum_seen_timestep") != 1
            or expected_times != actual_times or len(actual_times) != 1
            or receipt.get("earliest_fatal") is not None
            or receipt.get("candidate_build_unchanged") is not True
            or receipt.get("candidate_input_unchanged") is not True
            or any(receipt.get(name) != [] for name in (
                "processing_errors", "fatal_lines", "changed_staged_inputs",
                "changed_original_inputs", "duplicate_post_kdm6_timesteps"))):
        raise ValueError("expected a clean closed one-step proposal receipt")


def analyze(root: Path):
    evidence = native.CAPTURE_EVIDENCE
    build = json.loads((evidence / "build_provenance.json").read_text())
    original = native.verify_capture_manifests(
        native.CAPTURE_RUNS, evidence, build,
        json.loads((evidence / "frozen_c1_noninterference.json").read_text()))
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    preflight = json.loads((root / "preflight.json").read_text())
    validate_closed_capture(receipt, preflight)
    if (receipt.get("source_receipt_sha256") != preflight.get("source_receipt_sha256")
            or native.cloud.sha256(Path(preflight["source_receipt"])) != preflight["source_receipt_sha256"]):
        raise ValueError("proposal source receipt changed")
    binding = preflight.get("candidate_input_binding")
    if (not binding or binding.get("binding_kind") != "native_uv_projection"
            or receipt.get("candidate_input_binding") != binding
            or not runner._input_binding_unchanged(binding)):
        raise ValueError("expected a closed, source-bound one-step PR99 proposal capture")
    baseline = json.loads((native.CAPTURE_RUNS["COUPLED"].parent / "receipt.json").read_text())
    expected_build = baseline["candidate_build"]
    if (receipt.get("candidate_build") != expected_build
            or runner._candidate_build_binding(Path(expected_build["receipt_path"])) != expected_build
            or receipt.get("candidate_wrfbdy_sha256") !=
               baseline["candidate_wrfbdy_sha256"]
            or receipt.get("executed_executable_sha256") != expected_build["executable_sha256"]):
        raise ValueError("proposal and frozen captures do not use the same model and boundary")
    stage = root / "run"
    if native.cloud.sha256(stage / "wrfinput_d01") != receipt.get("candidate_wrfinput_sha256"):
        raise ValueError("proposal staged input changed")
    input_audit = native.compare_all_initial_variables(
        {"HYDRO": native.RUNS["COUPLED"], "COUPLED": root},
        {"HYDRO": json.loads((native.RUNS["COUPLED"] / "receipt.json").read_text()),
         "COUPLED": receipt})
    if (input_audit["variable_count"] != 208 or not input_audit["variable_names_equal"]
            or not input_audit["global_attributes_equal"] or not input_audit["all_except_UV_exact"]
            or input_audit["differing_variables"] != ["U", "V"]):
        raise ValueError("proposal changes stored state or metadata beyond U/V")
    input_audit["role_mapping"] = {"HYDRO": "original C1 COUPLED parent",
                                   "COUPLED": "PR99 projected U/V proposal"}
    snapshots = [row for row in receipt["generated_files"] if row["path"].startswith("pr98_")
                 and row["path"].endswith(".bin")]
    if len(snapshots) != 57:
        raise ValueError("proposal does not contain the complete 57-snapshot native capture")
    for row in snapshots:
        path = stage / row["path"]
        if path.stat().st_size != row["bytes"] or native.cloud.sha256(path) != row["sha256"]:
            raise ValueError(f"proposal capture changed: {path.name}")
        if (row["path"].startswith(("pr98_geom_c1h", "pr98_geom_c2h", "pr98_geom_msf"))
                and row["sha256"] != original["geometry_snapshot_sha256"][row["path"]]["COUPLED"]):
            raise ValueError(f"proposal static native geometry differs: {path.name}")
    composition = json.loads(native.COMPOSITION.read_text())["composed_qc_vertical_influence"]
    support = native.cloud.make_masks(composition, (39, 280, 232))["original_613_native_support"]
    roots = {**native.CAPTURE_RUNS, "COUPLED": stage}
    # Reuse the identical source-coordinate reductions; COUPLED here denotes
    # the proposed treatment, explicitly distinguished from original C1 below.
    response = native.analyze_native_capture(roots, support)
    import netCDF4
    with netCDF4.Dataset(stage / "wrfinput_d01") as ds:
        ds.set_auto_mask(False)
        area, _, _ = _read_map_geometry(ds, slice(None), slice(None))
        c1h, dnw = (_finite(ds, name, 0) for name in ("C1H", "DNW"))
    gravity, gravity_pin = _constants(CONSTANTS)
    meta, before = native.native_capture_file(stage, "pr98_mu_small_in_", 2)
    out_meta, after = native.native_capture_file(stage, "pr98_mu_small_out_", 2)
    _, seconds = native.native_capture_file(stage, "pr98_dts_small", 0)
    if meta["fortran_bounds"] != out_meta["fortran_bounds"]:
        raise ValueError("proposal MU endpoints have different bounds")
    mask = native.support_column_mask(meta, before.shape, support.any(axis=0))
    ims, _, jms = meta["fortran_bounds"][:3]
    coords = [(int(i+ims), int(j+jms)) for i, j in np.argwhere(mask)]
    weights = np.ones_like(before, dtype=float)
    weights[mask] = [area[j-1, i-1] for i, j in coords]
    rate, beta = column_mass_rate(before, after, float(seconds), c1h, dnw, weights, gravity)
    values = rate[mask]
    old_path = native.ROOT / "docs/evidence/pr98_native_effect_20261022/native_effect.json"
    old = json.loads(old_path.read_text())["tendency_capture"]
    mass_path = native.ROOT / "docs/evidence/pr99_native_mass_20261022/observed_column_rate.json"
    old_mass = json.loads(mass_path.read_text())
    if (capture_identity(old["capture_binding"]) != capture_identity(original)
            or capture_identity(old_mass["capture_binding"]) != capture_identity(original)):
        raise ValueError("original C1 comparison reports bind a different native capture")
    comparison = {}
    for variable in ("ru", "rv"):
        prior = old["native_source_arrays"]["momentum_arrays"][variable]["dry_rk_assembled_out"]["absolute_by_arm"]
        current = response["momentum_arrays"][variable]["dry_rk_assembled_out"]["absolute_by_arm"]
        comparison[variable+"_assembled_L2"] = {
            "units": "native source-coordinate units; not acceleration or energy",
            "HYDRO": prior["HYDRO"]["l2"], "original_C1_COUPLED": prior["COUPLED"]["l2"],
            "proposal": current["COUPLED"]["l2"],
            "proposal_over_original": current["COUPLED"]["l2"]/prior["COUPLED"]["l2"],
            "proposal_over_HYDRO": current["COUPLED"]["l2"]/prior["HYDRO"]["l2"]}
    comparison["observed_dry_column_rate_L2"] = {
        "units": "kg/s", "HYDRO": old_mass["arms"]["HYDRO"]["L2_kg_s"],
        "original_C1_COUPLED": old_mass["arms"]["COUPLED"]["L2_kg_s"],
        "proposal": float(np.linalg.norm(values))}
    return {"schema": "pr99_projection_native_response_v1",
            "receipt": {"path": str(receipt_path), "sha256": native.cloud.sha256(receipt_path)},
            "proposal_binding": binding, "frozen_capture_binding": original,
            "all_stored_input_variables_comparison": input_audit,
            "proposal_capture_files": snapshots, "native_source_coordinate_response": response,
            "comparison_to_original_C1": comparison,
            "comparison_source_reports": {str(p): native.cloud.sha256(p) for p in (old_path, mass_path)},
            "treatment_label": "COUPLED fields in this report are the PR99 projected U/V proposal",
            "proposal_observed_dry_column_rate": {
                "units": "kg/s", "hybrid_beta": beta, "seconds": float(seconds),
                "native_columns_ij": coords, "signed": float(values.sum()),
                "L1": float(np.abs(values).sum()), "L2": float(np.linalg.norm(values)),
                "max_abs": float(np.abs(values).max()), "gravity_binding": gravity_pin},
            "limits": ["One 20-second diagnostic integration, not a new three-arm longrun.",
                       "Momentum source-coordinate norms are not physical accelerations or energy.",
                       "A reduced dry-mass response does not establish momentum or observation benefit."],
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = analyze(args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
