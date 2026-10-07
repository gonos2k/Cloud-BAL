#!/usr/bin/env python3
"""Summarize guarded PR65 domain metrics on the KDM trace's exact active overlap."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump


EXPECTED_DIMS = {"Time": 2, "bottom_top": 39, "south_north": 282, "west_east": 234}
EXPECTED_TIMES = ("2026-08-16_12:00:00", "2026-08-16_12:00:20")
ACTIVE_SHAPE_KJI = (39, 280, 232)
DOMAIN_BOUNDS = {"i": (1, 235), "j": (1, 283), "k": (1, 40)}
ACTIVE_BOUNDS = {"i": (2, 233), "j": (2, 281), "k": (1, 39)}
VARIABLES = ("QCLOUD", "QNCLOUD", "QGRAUP", "QNCCN", "REFL_10CM")
VARIABLE_DIMS = ("Time", "bottom_top", "south_north", "west_east")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_regular_nonsymlink(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError:
        return False


def validate_run_receipt(run: Path, required_outputs: tuple[str, ...]) -> dict[str, object]:
    receipt_path = run / "run-isolation.json"
    receipt = json.loads(receipt_path.read_text())
    if (Path(receipt["run_root"]).resolve() != run.resolve()
            or receipt["returncode"] != 0
            or receipt["input_integrity"] != "PASS"
            or receipt["output_isolation"] != "PASS"
            or receipt["changed_inputs"]
            or receipt["input_read_issues"]
            or receipt["output_issues"]):
        raise ValueError(f"{run}: run-isolation receipt did not pass")
    inputs = {Path(item["path"]).name: item for item in receipt["inputs"]}
    manifest = inputs.get("runtime_reference_manifest.json")
    manifest_path = run / "runtime_reference_manifest.json"
    if (manifest is None or not is_regular_nonsymlink(manifest_path)
            or Path(manifest["path"]).resolve() != manifest_path.resolve()):
        raise ValueError(f"{run}: runtime reference manifest is missing or not receipt-bound")
    manifest_hash = sha256(manifest_path)
    if (manifest["sha256_before"] != manifest_hash
            or manifest["sha256_after"] != manifest_hash):
        raise ValueError(f"{run}: runtime reference manifest hash mismatch")
    output_records = receipt["outputs"]
    for name in required_outputs:
        matches = [item for item in output_records if Path(item["path"]).name == name]
        path = run / name
        if len(matches) != 1 or not is_regular_nonsymlink(path):
            raise ValueError(f"{run}: required output {name} is absent from receipt")
        output = matches[0]
        declared_path = Path(output["path"])
        if not declared_path.is_absolute():
            declared_path = run / declared_path
        if declared_path.resolve() != path.resolve():
            raise ValueError(f"{run}: output {name} receipt path mismatch")
        if (output["nlink"] != 1 or path.stat().st_nlink != 1
                or output["sha256"] != sha256(path)):
            raise ValueError(f"{run}: output {name} has a link-count or hash mismatch")
    return {
        "receipt_sha256": sha256(receipt_path),
        "receipt_path": str(receipt_path),
        "returncode": receipt["returncode"],
        "input_integrity": receipt["input_integrity"],
        "output_isolation": receipt["output_isolation"],
        "runtime_reference_manifest_path": str(manifest_path),
        "runtime_reference_manifest_sha256": manifest_hash,
        "verified_outputs": list(required_outputs),
        "scope": "local guard receipt, input/output hashes, and live output link counts; no external attestation or executable/compiler authority",
    }


def read_times(variable: netCDF4.Variable) -> tuple[str, ...]:
    return tuple("".join(item.decode("ascii") for item in row) for row in variable[:])


def validate_dataset(dataset: netCDF4.Dataset, label: str) -> tuple[str, ...]:
    dimensions = {name: len(dataset.dimensions[name]) for name in EXPECTED_DIMS
                  if name in dataset.dimensions}
    if dimensions != EXPECTED_DIMS:
        raise ValueError(f"{label}: unexpected NetCDF dimensions: {dimensions}")
    if "Times" not in dataset.variables or dataset.variables["Times"].dimensions != ("Time", "DateStrLen"):
        raise ValueError(f"{label}: unexpected Times variable dimensions")
    times = read_times(dataset.variables["Times"])
    if times != EXPECTED_TIMES:
        raise ValueError(f"{label}: unexpected NetCDF Times: {times}")
    for name in VARIABLES:
        if name not in dataset.variables:
            raise ValueError(f"{label}: missing variable {name}")
        if dataset.variables[name].dimensions != VARIABLE_DIMS:
            raise ValueError(f"{label}: unexpected dimensions for {name}: {dataset.variables[name].dimensions}")
    return times


def crop_slices(bounds: dict[str, int]) -> tuple[slice, slice, slice]:
    actual = {
        "i": (bounds["its"], bounds["ite"]),
        "j": (bounds["jts"], bounds["jte"]),
        "k": (bounds["kts"], bounds["kte"]),
    }
    if actual != ACTIVE_BOUNDS:
        raise ValueError(f"unexpected KDM active bounds: {actual}")
    domain = {
        "i": (bounds["ids"], bounds["ide"]),
        "j": (bounds["jds"], bounds["jde"]),
        "k": (bounds["kds"], bounds["kde"]),
    }
    if domain != DOMAIN_BOUNDS:
        raise ValueError(f"unexpected KDM domain bounds: {domain}")
    return (
        slice(bounds["kts"] - bounds["kds"], bounds["kte"] - bounds["kds"] + 1),
        slice(bounds["jts"] - bounds["jds"], bounds["jte"] - bounds["jds"] + 1),
        slice(bounds["its"] - bounds["ids"], bounds["ite"] - bounds["ids"] + 1),
    )


def active_field(variable: netCDF4.Variable, time_index: int,
                 slices: tuple[slice, slice, slice]) -> np.ndarray:
    if variable.dimensions != VARIABLE_DIMS:
        raise ValueError(f"unexpected dimensions for {variable.name}: {variable.dimensions}")
    raw = variable[(time_index, *slices)]
    if np.ma.isMaskedArray(raw) and np.ma.getmaskarray(raw).any():
        raise ValueError(f"masked values in {variable.name} active crop")
    values = np.asarray(raw, dtype=np.float64)
    if values.shape != ACTIVE_SHAPE_KJI:
        raise ValueError(f"{variable.name} active crop shape {values.shape} != {ACTIVE_SHAPE_KJI}")
    return values


def field_summary(values: np.ndarray, timestamp: str, reflectivity: bool = False) -> dict[str, object]:
    finite = np.isfinite(values)
    selected = values[finite]
    if selected.size == 0:
        raise ValueError(f"{timestamp}: field has no finite active values")
    mean = float(np.mean(selected, dtype=np.float64))
    p99 = float(np.percentile(selected, 99))
    if not np.isfinite((mean, p99)).all():
        raise ValueError(f"{timestamp}: nonfinite field reduction")
    result: dict[str, object] = {
        "time": timestamp,
        "shape_kji": list(values.shape),
        "active_overlap_cells": int(values.size),
        "finite_count": int(finite.sum()),
        "nonfinite_count": int((~finite).sum()),
        "min": finite_min(values, timestamp),
        "max": finite_max(values, timestamp),
        "mean": mean,
        "p99": p99,
    }
    if reflectivity:
        positive = selected[selected > 0.0]
        result.update({
            "minus35_sentinel_count": int(np.count_nonzero(selected == -35.0)),
            "positive_dbz_count": int(positive.size),
            "positive_dbz_min": float(positive.min()) if positive.size else None,
            "positive_dbz_p99": float(np.percentile(positive, 99)) if positive.size else None,
        })
    return result


def transition_comparison(enabled_path: Path, control_path: Path) -> dict[str, object]:
    enabled = json.loads(enabled_path.read_text())
    control = json.loads(control_path.read_text())
    validate_transition_bounds(enabled)
    validate_transition_bounds(control)
    if enabled["counts"]["exact_global_overlap"] != control["counts"]["exact_global_overlap"]:
        raise ValueError("patchless and shared-NC transition bounds or runtime QMIN differ")
    enabled_records = enabled["stage_text"]["records"]
    control_records = control["stage_text"]["records"]
    return {
        "active_overlap_counts": {
            "patchless_kdm6_entry": control["counts"]["kdm6_entry"],
            "shared_nc_kdm6_entry": enabled["counts"]["kdm6_entry"],
            "patchless_kdm6_return": control["counts"]["kdm6_return"],
            "shared_nc_kdm6_return": enabled["counts"]["kdm6_return"],
            "patchless_mask_full_tile": control["counts"]["mask_full_tile"],
            "shared_nc_mask_full_tile": enabled["counts"]["mask_full_tile"],
        },
        "selected_pre_microphysics": {
            "patchless": {k: control_records[-2][k] for k in ("selected_qc", "selected_nc", "selected_qg", "selected_bg")},
            "shared_nc": {k: enabled_records[-2][k] for k in ("selected_qc", "selected_nc", "selected_qg", "selected_bg")},
        },
        "selected_post_microphysics": {
            "patchless": {k: control_records[-1][k] for k in ("selected_qc", "selected_nc", "selected_qg", "selected_bg")},
            "shared_nc": {k: enabled_records[-1][k] for k in ("selected_qc", "selected_nc", "selected_qg", "selected_bg")},
        },
        "qualification": "Matched patchless research baseline; aggregates do not identify per-cell causes. The KDM-return zero-QG/positive-BG count is unchanged.",
    }


def validate_transition_binding(pre: dict, post: dict, transition: dict) -> tuple[tuple[slice, slice, slice], float]:
    if pre["stage"] != 1 or post["stage"] != 2 or pre["itimestep"] != post["itimestep"]:
        raise ValueError("same-call KDM6 stages or timesteps do not match")
    if pre["itimestep"] != 1:
        raise ValueError(f"expected first KDM6 timestep 1, got {pre['itimestep']}")
    if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
        raise ValueError("same-call KDM6 pre/post bounds or parameters differ")
    bounds = pre["bounds"]
    slices = crop_slices(bounds)
    exact = transition["counts"]["exact_global_overlap"]
    for axis in ("i", "j", "k"):
        if tuple(exact[axis]) != ACTIVE_BOUNDS[axis]:
            raise ValueError(f"transition {axis} bounds do not match KDM active bounds")
    if pre["active_shape_xyz"] != [232, 280, 39] or post["active_shape_xyz"] != [232, 280, 39]:
        raise ValueError("KDM capture active shape does not match the selected overlap")
    raw_hashes = transition["counts"]["sha256"]
    if raw_hashes["pre"] != pre["sha256"] or raw_hashes["post"] != post["sha256"]:
        raise ValueError("transition capture hashes do not bind the KDM pre/post raws")
    qmin = float(exact["runtime_epsilon"])
    if not np.isfinite(qmin) or qmin <= 0.0:
        raise ValueError("transition capture has invalid runtime QMIN")
    return slices, qmin


def validate_transition_bounds(transition: dict) -> None:
    exact = transition["counts"]["exact_global_overlap"]
    for axis in ("i", "j", "k"):
        if tuple(exact[axis]) != ACTIVE_BOUNDS[axis]:
            raise ValueError(f"transition {axis} bounds do not match selected active bounds")
    qmin = float(exact["runtime_epsilon"])
    if not np.isfinite(qmin) or qmin <= 0.0:
        raise ValueError("transition capture has invalid runtime QMIN")


def validate_transition_replay_artifacts(run: Path, transition_path: Path,
                                        receipt: dict,
                                        require_mask_receipt_bound: bool) -> dict[str, object]:
    transition = json.loads(transition_path.read_text())
    stage_path = run / "pr63_transition_stages.raw"
    mask_path = run / "pr63_transition_masks.bin"
    if sha256(stage_path) != transition["stage_text"]["sha256"]:
        raise ValueError(f"{run}: transition stage raw hash mismatch")
    mask_hash = transition["counts"]["sha256"]["masks"]
    if not mask_path.is_file() or sha256(mask_path) != mask_hash:
        raise ValueError(f"{run}: transition mask raw hash mismatch")
    verified = set(receipt["verified_outputs"])
    stage_receipt_bound = "pr63_transition_stages.raw" in verified
    mask_receipt_bound = "pr63_transition_masks.bin" in verified
    if not stage_receipt_bound:
        raise ValueError(f"{run}: transition stage raw is not receipt-bound")
    if require_mask_receipt_bound and not mask_receipt_bound:
        raise ValueError(f"{run}: transition mask is not receipt-bound")
    return {
        "transition_replay_sha256": sha256(transition_path),
        "stage_raw_sha256": sha256(stage_path),
        "stage_raw_receipt_bound": stage_receipt_bound,
        "mask_raw_sha256": sha256(mask_path),
        "mask_raw_receipt_bound": mask_receipt_bound,
    }


def same_call_moment_metrics(run: Path, transition_path: Path, pre: dict | None = None,
                             post: dict | None = None) -> dict[str, object]:
    pre_path = run / "kdm6_first_call_pre.raw"
    post_path = run / "kdm6_first_call_post.raw"
    transition = json.loads(transition_path.read_text())
    pre = pre if pre is not None else read_dump(pre_path)
    post = post if post is not None else read_dump(post_path)
    _, qmin = validate_transition_binding(pre, post, transition)

    pairs = {"QC": "NC", "QI": "NI", "QR": "NR", "QG": "BG"}
    pair_results = {}
    for phase, state in (("pre", pre), ("post", post)):
        fields = state["fields"]
        for mass_name, moment_name in pairs.items():
            mass = fields[mass_name]
            moment = fields[moment_name]
            if mass.shape != moment.shape:
                raise ValueError(f"{phase} {mass_name}/{moment_name} shapes differ")
            key = f"{phase}_{mass_name}_{moment_name}"
            pair_results[key] = {
                "cells": int(mass.size),
                "mass_min": finite_min(mass, f"{phase} {mass_name}"),
                "mass_max": finite_max(mass, f"{phase} {mass_name}"),
                "mass_nonfinite": int((~np.isfinite(mass)).sum()),
                "moment_min": finite_min(moment, f"{phase} {moment_name}"),
                "moment_max": finite_max(moment, f"{phase} {moment_name}"),
                "moment_nonfinite": int((~np.isfinite(moment)).sum()),
                "mass_negative": int((mass < 0.0).sum()),
                "mass_zero": int((mass == 0.0).sum()),
                "mass_gt_source_qmin_moment_zero": int(((mass > qmin) & (moment == 0.0)).sum()),
                "mass_gt_strict_zero_moment_zero": int(((mass > 0.0) & (moment == 0.0)).sum()),
                "moment_negative": int((moment < 0.0).sum()),
                "moment_zero": int((moment == 0.0).sum()),
            }
        number = fields["NN"]
        pair_results[f"{phase}_NN"] = {
            "cells": int(number.size),
            "min": finite_min(number, f"{phase} NN"),
            "max": finite_max(number, f"{phase} NN"),
            "negative": int((number < 0.0).sum()),
            "zero": int((number == 0.0).sum()),
            "nonfinite": int((~np.isfinite(number)).sum()),
        }
    return {
        "capture_hashes": {
            "pre": sha256(pre_path),
            "post": sha256(post_path),
            "transition": sha256(transition_path),
        },
        "scope": "full active tile of the captured first KDM6 call; not a whole-domain or PSD closure",
        "active_shape_xyz": pre["active_shape_xyz"],
        "qmin": qmin,
        "moment_pairs_and_nn": pair_results,
        "threshold_basis": "source QMIN is bound to the runtime epsilon recorded from the guarded transition mask; strict-zero counts are separate",
    }


def finite_min(values: np.ndarray, label: str) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError(f"{label} has no finite values")
    return float(np.min(finite))


def finite_max(values: np.ndarray, label: str) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise ValueError(f"{label} has no finite values")
    return float(np.max(finite))


def compare_fields(enabled_path: Path, control_path: Path,
                   slices: tuple[slice, slice, slice]) -> dict[str, object]:
    changed = {}
    with netCDF4.Dataset(enabled_path) as enabled, netCDF4.Dataset(control_path) as control:
        validate_dataset(enabled, str(enabled_path))
        validate_dataset(control, str(control_path))
        for name in VARIABLES:
            left = active_field(control.variables[name], 1, slices)
            right = active_field(enabled.variables[name], 1, slices)
            delta = right - left
            if not np.isfinite(delta).all():
                raise ValueError(f"nonfinite {name} difference between shared and patchless runs")
            max_abs_change = float(np.max(np.abs(delta)))
            sum_change = float(np.sum(delta, dtype=np.float64))
            if not np.isfinite((max_abs_change, sum_change)).all():
                raise ValueError(f"nonfinite {name} comparison reduction")
            entry: dict[str, object] = {
                "changed_cells": int(np.count_nonzero(delta)),
                "max_abs_change": max_abs_change,
                "sum_change": sum_change,
                "baseline_min": float(left.min()),
                "baseline_max": float(left.max()),
                "shared_nc_min": float(right.min()),
                "shared_nc_max": float(right.max()),
            }
            if name == "REFL_10CM":
                entry["baseline_positive_dbz_cells"] = int(np.count_nonzero(left > 0.0))
                entry["shared_nc_positive_dbz_cells"] = int(np.count_nonzero(right > 0.0))
            changed[name] = entry
    return changed


def summarize(
    enabled_run: Path,
    patchless_run: Path,
    earlier_enabled_run: Path,
    enabled_transition: Path,
    patchless_transition: Path,
) -> dict[str, object]:
    wrfout = enabled_run / "wrfout_d01_2026-08-16_12:00:00"
    baseline_wrfout = patchless_run / wrfout.name
    enabled_pre = read_dump(enabled_run / "kdm6_first_call_pre.raw")
    enabled_post = read_dump(enabled_run / "kdm6_first_call_post.raw")
    enabled_transition_data = json.loads(enabled_transition.read_text())
    enabled_slices, _ = validate_transition_binding(enabled_pre, enabled_post, enabled_transition_data)
    control_pre = read_dump(patchless_run / "kdm6_first_call_pre.raw")
    control_post = read_dump(patchless_run / "kdm6_first_call_post.raw")
    control_transition_data = json.loads(patchless_transition.read_text())
    control_slices, _ = validate_transition_binding(control_pre, control_post, control_transition_data)
    if control_slices != enabled_slices:
        raise ValueError("patchless and shared-NC KDM crops differ")
    with netCDF4.Dataset(wrfout) as dataset, netCDF4.Dataset(baseline_wrfout) as baseline:
        times = validate_dataset(dataset, str(wrfout))
        validate_dataset(baseline, str(baseline_wrfout))
        fields = {}
        for name in VARIABLES:
            variable = dataset.variables[name]
            fields[name] = [
                field_summary(active_field(variable, ti, enabled_slices), times[ti], name == "REFL_10CM")
                for ti in range(len(times))
            ]
        target = {name: float(active_field(dataset.variables[name], 1, enabled_slices)[0, 74, 170])
                  for name in VARIABLES}
        baseline_target = {
            name: float(active_field(baseline.variables[name], 1, control_slices)[0, 74, 170])
            for name in VARIABLES
        }
    artifact_names = (
        "pr65_pbl_operator.raw",
        "pr64_qc_channels.raw",
        "pr63_kdm_stages.raw",
        "pr63_transition_stages.raw",
        "kdm6_first_call_pre.raw",
        "kdm6_first_call_post.raw",
        wrfout.name,
    )
    receipt_validation = {
        "shared_nc": validate_run_receipt(
            enabled_run, artifact_names + ("pr65_pbl_nc.raw", "pr63_transition_masks.bin")),
        "patchless": validate_run_receipt(
            patchless_run, artifact_names + ("pr65_pbl_nc.raw",)),
        "earlier_enabled_observer_control": validate_run_receipt(
            earlier_enabled_run, artifact_names + ("pr65_pbl_nc.raw",)),
    }
    transition_artifact_bindings = {
        "shared_nc": validate_transition_replay_artifacts(
            enabled_run, enabled_transition, receipt_validation["shared_nc"], True),
        "patchless": validate_transition_replay_artifacts(
            patchless_run, patchless_transition, receipt_validation["patchless"], False),
    }
    neutrality = {
        name: {
            "earlier_enabled_sha256": sha256(earlier_enabled_run / name),
            "final_pinned_run_sha256": sha256(enabled_run / name),
            "byte_identical": (earlier_enabled_run / name).read_bytes() == (enabled_run / name).read_bytes(),
        }
        for name in artifact_names
    }
    def nc_inputs(path: Path) -> list[str]:
        return [line for line in (path / "pr65_pbl_nc.raw").read_text().splitlines()
                if line.startswith(("CALL,", "NC,"))]
    return {
        "schema": "pr65_pbl_shared_nc_domain_metrics_v1",
        "source_sha256": sha256(Path(__file__)),
        "run_roots": {
            "shared_nc": str(enabled_run),
            "patchless": str(patchless_run),
            "earlier_enabled_observer_control": str(earlier_enabled_run),
        },
        "input_hashes": {
            "shared_nc_wrfout": sha256(wrfout),
            "patchless_wrfout": sha256(baseline_wrfout),
            "shared_nc_transition": sha256(enabled_transition),
            "patchless_transition": sha256(patchless_transition),
        },
        "active_overlap": {
            "global_i": [2, 233],
            "global_j": [2, 281],
            "global_k": [1, 39],
            "array_order": "k,j,i",
            "shape_kji": list(ACTIVE_SHAPE_KJI),
            "cells": int(np.prod(ACTIVE_SHAPE_KJI)),
        },
        "netcdf_times": list(EXPECTED_TIMES),
        "netcdf_active_overlap_fields": fields,
        "20_second_shared_nc_minus_patchless_active_overlap": compare_fields(
            wrfout, baseline_wrfout, enabled_slices),
        "20_second_selected_target_172_76_k1": {
            "patchless": baseline_target,
            "shared_nc": target,
        },
        "transition_metrics": transition_comparison(enabled_transition, patchless_transition),
        "same_call_moment_metrics": same_call_moment_metrics(
            enabled_run, enabled_transition, enabled_pre, enabled_post),
        "patchless_same_call_moment_metrics": same_call_moment_metrics(
            patchless_run, patchless_transition, control_pre, control_post),
        "postcapture_observer_neutrality": neutrality,
        "run_receipt_validation": receipt_validation,
        "transition_artifact_bindings": transition_artifact_bindings,
        "transition_comparison_provenance": {
            "status": ("PARTIAL_BASELINE_MASK_RECEIPT_GAP"
                       if not transition_artifact_bindings["patchless"]["mask_raw_receipt_bound"]
                       else "BOTH_RUNS_RECEIPT_BOUND"),
            "reason": ("Patchless mask bytes hash-match the replay but are absent from the retained patchless run receipt output list; no historical receipt was rewritten."
                       if not transition_artifact_bindings["patchless"]["mask_raw_receipt_bound"]
                       else "Both masks and stage outputs are bound by their run receipts."),
        },
        "nc_donor_capture_unchanged": nc_inputs(earlier_enabled_run) == nc_inputs(enabled_run),
        "scope": [
            "KDM-stage aggregates do not identify each eventual negative-QC cell cause.",
            "REFL_10CM is model-generated output, not an observed reflectivity fit.",
            "The NetCDF crop is validated against KDM global bounds and k,j,i array order.",
            "Same-call all-moment statistics cover only the captured KDM6 active tile and do not establish PSD or domain-wide closure.",
            "Local run receipts bind inputs and selected outputs; no external receipt attestation or executable/compiler authority is claimed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-nc-run", required=True, type=Path)
    parser.add_argument("--patchless-run", required=True, type=Path)
    parser.add_argument("--earlier-enabled-run", required=True, type=Path)
    parser.add_argument("--shared-nc-transition", required=True, type=Path)
    parser.add_argument("--patchless-transition", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = summarize(
            args.shared_nc_run,
            args.patchless_run,
            args.earlier_enabled_run,
            args.shared_nc_transition,
            args.patchless_transition,
        )
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (OSError, KeyError, ValueError) as exc:
        print(f"pr65-pbl-domain-metrics: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
