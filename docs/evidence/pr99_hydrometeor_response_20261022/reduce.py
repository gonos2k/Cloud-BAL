#!/usr/bin/env python3
"""Reduce receipt-bound first-call KDM6 hydrometeor traces for PR99."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

CLOUD_BAL = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CLOUD_BAL / "tools"))
from native_kdm6_trace import read_dump  # noqa: E402
from pr87_native_history import _finite  # noqa: E402
from pr94_cloud_response import make_masks, pattern_metrics, vector_metrics  # noqa: E402

ORIGINAL_RUNS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr98_native_effect_20261022/native_capture_runs")
ORIGINAL_INPUTS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre")
PROPOSAL_RUN = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr99_native_uv20_capture_20261022/run")
PROPOSAL_INPUT = Path("/var/tmp/pr99_native_projection_v4_20261022/wrfinput_d01")
PROPOSAL_BDY = PROPOSAL_RUN / "run/wrfbdy_d01"
COMPOSITION = CLOUD_BAL / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
FIELDS = {"QC": "QCLOUD", "QI": "QICE", "QR": "QRAIN", "QS": "QSNOW", "QG": "QGRAUP"}
SHAPE_KJI = (39, 280, 232)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run_paths() -> dict[str, tuple[Path, Path, Path]]:
    result = {}
    for arm in ("OFF", "HYDRO", "C1_COUPLED"):
        original = "COUPLED" if arm == "C1_COUPLED" else arm
        result[arm] = (
            ORIGINAL_RUNS / f"{original}_20s",
            ORIGINAL_INPUTS / f"{original}_600s_c1/run/wrfinput_d01",
            ORIGINAL_INPUTS / f"{original}_600s_c1/run/wrfbdy_d01",
        )
    result["PROPOSAL"] = (PROPOSAL_RUN, PROPOSAL_INPUT, PROPOSAL_BDY)
    return result


def receipt_binding(arm: str, run: Path, input_path: Path,
                    boundary_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_path = run / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("arm") != ("COUPLED" if arm in ("C1_COUPLED", "PROPOSAL") else arm) or
            receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0 or
            receipt.get("final_completed_step") != 1 or receipt.get("timestep_count") != 1):
        raise ValueError(f"{arm} receipt is not a closed one-step run")
    if sha256(input_path) != receipt.get("candidate_wrfinput_sha256"):
        raise ValueError(f"{arm} input hash does not match its receipt")
    if sha256(boundary_path) != receipt.get("candidate_wrfbdy_sha256"):
        raise ValueError(f"{arm} boundary hash does not match its receipt")
    timestamp_rows = receipt.get("model_timestamps", [])
    if len(timestamp_rows) != 1:
        raise ValueError(f"{arm} receipt has no unique model timestamp")
    return {
        "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
        "status": receipt["status"], "returncode": receipt["returncode"],
        "final_completed_step": receipt["final_completed_step"],
        "timestamp": timestamp_rows[0]["timestamp"],
        "input_path": str(input_path), "input_sha256": receipt["candidate_wrfinput_sha256"],
        "boundary_path": str(boundary_path), "boundary_sha256": receipt["candidate_wrfbdy_sha256"],
        "executable_sha256": receipt["executed_executable_sha256"],
    }, receipt


def verified_trace(run: Path, name: str, receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [row for row in receipt.get("compressed_outputs", []) if row.get("path") == f"{name}.raw"]
    if len(rows) != 1:
        raise ValueError(f"expected exactly one receipt row for {name}.raw")
    row = rows[0]
    expected_gzip = f"{name}.raw.gz"
    if row.get("compressed_path") != expected_gzip:
        raise ValueError(f"unexpected compressed path for {name}.raw")
    compressed_path = run / "run" / expected_gzip
    if sha256(compressed_path) != row.get("compressed_sha256"):
        raise ValueError(f"compressed trace SHA mismatch: {compressed_path}")
    with tempfile.NamedTemporaryFile(suffix=".raw") as raw_file:
        with gzip.open(compressed_path, "rb") as source:
            for block in iter(lambda: source.read(1 << 20), b""):
                raw_file.write(block)
        raw_file.flush()
        trace = read_dump(Path(raw_file.name))
    if trace["sha256"] != row.get("sha256") or trace["bytes"] != row.get("bytes"):
        raise ValueError(f"expanded trace does not match receipt: {compressed_path}")
    binding = {"path": str(compressed_path), "compressed_sha256": row["compressed_sha256"],
               "expanded_sha256": row["sha256"], "expanded_bytes": row["bytes"]}
    return trace, binding


def load_initial_fields(input_path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    fields, identities = {}, {}
    with netCDF4.Dataset(input_path) as dataset:
        dataset.set_auto_mask(False)
        for short_name, variable_name in FIELDS.items():
            whole_field = _finite(dataset, variable_name, 0)
            variable = dataset.variables[variable_name]
            raw_whole_field = np.asarray(variable[0])
            if whole_field.shape != (39, 282, 234):
                raise ValueError(f"unexpected full-grid shape for {variable_name}: {whole_field.shape}")
            cropped = whole_field[:, 1:-1, 1:-1]
            if cropped.shape != SHAPE_KJI or not np.isfinite(cropped).all():
                raise ValueError(f"bad cropped initial field {variable_name}")
            fields[short_name] = cropped.astype(np.float64, copy=False)
            identities[short_name] = {
                "variable": variable_name, "shape": list(raw_whole_field.shape),
                "dtype": raw_whole_field.dtype.str,
                "full_array_sha256": hashlib.sha256(raw_whole_field.tobytes(order="C")).hexdigest(),
            }
    return fields, identities


def simple_stats(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64).ravel()
    if not np.isfinite(values).all():
        raise ValueError("metric input contains nonfinite values")
    return {"cells": int(values.size), "rms_kgkg": float(np.sqrt(np.mean(values * values))),
            "signed_mean_kgkg": float(np.mean(values)),
            "signed_sum_kgkg_cell_sum": float(np.sum(values, dtype=np.float64)),
            "max_abs_kgkg": float(np.max(np.abs(values)))}


def reduce(output_path: Path) -> None:
    composition = json.loads(COMPOSITION.read_text())
    masks = make_masks(composition["composed_qc_vertical_influence"], SHAPE_KJI)
    responses, receipts, traces, initial, input_identities = {}, {}, {}, {}, {}
    paths = run_paths()
    for arm, (run, input_path, boundary_path) in paths.items():
        binding, receipt = receipt_binding(arm, run, input_path, boundary_path)
        receipts[arm] = binding
        pre, pre_binding = verified_trace(run, "kdm6_first_call_pre", receipt)
        post, post_binding = verified_trace(run, "kdm6_first_call_post", receipt)
        if (pre["stage"] != 1 or post["stage"] != 2 or pre["itimestep"] != 1 or
                post["itimestep"] != 1 or pre["bounds"] != post["bounds"] or
                pre["params"] != post["params"] or pre["active_shape_xyz"] != [232, 280, 39]):
            raise ValueError(f"{arm} pre/post trace headers or grid are inconsistent")
        traces[arm] = {"pre": pre_binding, "post": post_binding,
                       "active_shape_xyz": pre["active_shape_xyz"],
                       "bounds": pre["bounds"], "params": pre["params"]}
        responses[arm] = {}
        for field in FIELDS:
            before = pre["fields"][field].transpose(1, 0, 2).astype(np.float64)
            after = post["fields"][field].transpose(1, 0, 2).astype(np.float64)
            if not np.isfinite(before).all() or not np.isfinite(after).all():
                raise ValueError(f"{arm} {field} trace has nonfinite values")
            increment = after - before
            regional = {region: simple_stats(increment[mask]) for region, mask in masks.items()}
            responses[arm][field] = {"pre": before, "post": after, "increment": increment,
                                     "increment_by_region": regional}
        initial[arm], input_identities[arm] = load_initial_fields(input_path)

    if len({x["timestamp"] for x in receipts.values()}) != 1:
        raise ValueError("run timestamps differ")
    if len({x["executable_sha256"] for x in receipts.values()}) != 1:
        raise ValueError("executed executable differs across arms")
    if len({x["boundary_sha256"] for x in receipts.values()}) != 1:
        raise ValueError("boundary input differs across arms")
    if len({json.dumps((x["bounds"], x["params"]), sort_keys=True) for x in traces.values()}) != 1:
        raise ValueError("trace grids or call parameters differ across arms")
    for field in FIELDS:
        if input_identities["PROPOSAL"][field]["shape"] != input_identities["C1_COUPLED"][field]["shape"] or \
                input_identities["PROPOSAL"][field]["dtype"] != input_identities["C1_COUPLED"][field]["dtype"] or \
                input_identities["PROPOSAL"][field]["full_array_sha256"] != input_identities["C1_COUPLED"][field]["full_array_sha256"]:
            raise ValueError(f"proposal full-grid {field} input differs from original C1 COUPLED")

    output: dict[str, Any] = {
        "schema": "pr99_native_hydrometeor_firstcall_response_v1",
        "scope": "one native KDM6 call at model time 20 s (T1): captured PRE and POST states and their increment; not full host history or end-of-forecast state",
        "arms": receipts, "trace_bindings": traces,
        "input_hydrometeor_identity": input_identities,
        "support_definition": {"composition_path": str(COMPOSITION.relative_to(CLOUD_BAL)),
            "composition_sha256": sha256(COMPOSITION), "support_cells": 613, "columns": 16,
            "active_shape_kji": list(SHAPE_KJI), "regions": list(masks)},
        "units": "Q* mixing ratios kg/kg dry; signed_sum is a cell sum, not extensive water mass",
        "metrics": {},
    }
    for field in FIELDS:
        baseline = initial["C1_COUPLED"][field] - initial["OFF"][field]
        metric = output["metrics"][field] = {
            "initial_C1_COUPLED_minus_OFF": {"source_field": FIELDS[field], "region_metrics": {}},
            "arm_POST_minus_PRE_microincrement": {
                arm: responses[arm][field]["increment_by_region"] for arm in paths},
            "proposal_minus_OFF_POST_state": {}, "proposal_minus_OFF_PRE_state": {},
            "HYDRO_minus_OFF_PRE_state": {},
            "original_C1_COUPLED_minus_OFF_PRE_state": {},
            "HYDRO_minus_OFF_POST_state": {},
            "original_C1_COUPLED_minus_OFF_POST_state": {},
            "proposal_minus_original_C1_COUPLED_POST_state": {},
            "proposal_minus_HYDRO_POST_state": {},
            "proposal_minus_OFF_microincrement": {"whole_region": vector_metrics(
                np.zeros_like(responses["PROPOSAL"][field]["increment"]),
                responses["PROPOSAL"][field]["increment"] - responses["OFF"][field]["increment"]),
                "by_region": {}},
            "proposal_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "proposal_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "HYDRO_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "original_C1_COUPLED_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "HYDRO_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "original_C1_COUPLED_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
            "proposal_minus_HYDRO_POST_state_projected_on_initial_C1_COUPLED_minus_OFF": {},
        }
        for region, mask in masks.items():
            post_contrast = responses["PROPOSAL"][field]["post"][mask] - responses["OFF"][field]["post"][mask]
            pre_contrast = responses["PROPOSAL"][field]["pre"][mask] - responses["OFF"][field]["pre"][mask]
            c1_contrast = responses["C1_COUPLED"][field]["post"][mask] - responses["OFF"][field]["post"][mask]
            proposal_c1 = responses["PROPOSAL"][field]["post"][mask] - responses["C1_COUPLED"][field]["post"][mask]
            proposal_pre = responses["PROPOSAL"][field]["pre"][mask] - responses["OFF"][field]["pre"][mask]
            hydro_pre = responses["HYDRO"][field]["pre"][mask] - responses["OFF"][field]["pre"][mask]
            c1_pre = responses["C1_COUPLED"][field]["pre"][mask] - responses["OFF"][field]["pre"][mask]
            hydro_contrast = responses["HYDRO"][field]["post"][mask] - responses["OFF"][field]["post"][mask]
            proposal_hydro = responses["PROPOSAL"][field]["post"][mask] - responses["HYDRO"][field]["post"][mask]
            increment_contrast = (responses["PROPOSAL"][field]["increment"][mask] -
                                  responses["OFF"][field]["increment"][mask])
            metric["initial_C1_COUPLED_minus_OFF"]["region_metrics"][region] = simple_stats(baseline[mask])
            metric["proposal_minus_OFF_POST_state"][region] = simple_stats(post_contrast)
            metric["proposal_minus_OFF_PRE_state"][region] = simple_stats(pre_contrast)
            metric["HYDRO_minus_OFF_PRE_state"][region] = simple_stats(hydro_pre)
            metric["original_C1_COUPLED_minus_OFF_PRE_state"][region] = simple_stats(c1_pre)
            metric["HYDRO_minus_OFF_POST_state"][region] = simple_stats(hydro_contrast)
            metric["original_C1_COUPLED_minus_OFF_POST_state"][region] = simple_stats(c1_contrast)
            metric["proposal_minus_original_C1_COUPLED_POST_state"][region] = simple_stats(proposal_c1)
            metric["proposal_minus_HYDRO_POST_state"][region] = simple_stats(proposal_hydro)
            metric["proposal_minus_OFF_microincrement"]["by_region"][region] = simple_stats(increment_contrast)
            metric["proposal_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], post_contrast)
            metric["proposal_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], proposal_pre)
            metric["HYDRO_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], hydro_pre)
            metric["original_C1_COUPLED_minus_OFF_PRE_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], c1_pre)
            metric["HYDRO_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], hydro_contrast)
            metric["original_C1_COUPLED_minus_OFF_POST_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], c1_contrast)
            metric["proposal_minus_HYDRO_POST_state_projected_on_initial_C1_COUPLED_minus_OFF"][region] = \
                pattern_metrics(baseline[mask], proposal_hydro)
    output["projection_policy"] = {
        "comparison": "initial C1_COUPLED−OFF T0 mixing-ratio difference versus proposal−OFF POST-state contrast at T1",
        "interpretation": "descriptive alignment only; not causal attribution",
        "undefined_cases": "projection is null for exact-zero baseline norm; cosine is null if either vector norm is zero",
    }
    output["bindings"] = {
        "composition_path": str(COMPOSITION), "composition_sha256": sha256(COMPOSITION),
        "reader_source_sha256": sha256(CLOUD_BAL / "tools/native_kdm6_trace.py"),
        "history_reader_source_sha256": sha256(CLOUD_BAL / "tools/pr87_native_history.py"),
        "mask_source_sha256": sha256(CLOUD_BAL / "tools/pr94_cloud_response.py"),
    }
    with output_path.open("x", encoding="utf-8") as target:
        json.dump(output, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new JSON path; existing files are not overwritten")
    args = parser.parse_args()
    reduce(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
