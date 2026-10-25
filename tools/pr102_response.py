#!/usr/bin/env python3
"""Receipt-bound descriptive response for the PR102 STRUCTURED C2 run."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import netCDF4

import pr86_compare_response as history
import pr94_cloud_response as cloud
import pr98_native_effect as native
import pr101_projected_c2_response as pr101
import pr102_execution_preflight as preflight
import pr102_native_wind_candidate as candidate_builder
import pr99_native_mass_effect as mass_effect
from pr87_native_history import _constants, _finite
from pr95_call_budget import _read_map_geometry

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
CONTROL_ROOT = ROOT / "pr99_c2_matched640_20261022"
P_ROOT = ROOT / "pr101_projected_c2_640_20261023"
EXPECTED_TIMESTAMPS = [
    (history.START + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d_%H:%M:%S")
    for seconds in range(0, 601, 60)]
HISTORY_FIELDS = ("pressure", "geopotential", "T", "QVAPOR", "QCLOUD", "QICE",
                  "QRAIN", "QSNOW", "QGRAUP", "U", "V", "W")
TRACE_STEPS = {1, 3, 15, 16, 24, 25, 30, 32}
TRACE_FIELDS = ("Q", "QC", "QI", "QR", "QS", "QG")
MODEL_TIMESTAMPS = [(history.START + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                    for step in range(1, 33)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def response_metrics(current: np.ndarray, reference: np.ndarray) -> dict:
    current = np.asarray(current, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if current.shape != reference.shape or not np.isfinite(current).all() or not np.isfinite(reference).all():
        raise ValueError("response arrays must have identical finite support")
    delta = current - reference
    return {"n": int(delta.size), "signed_sum": float(np.sum(delta, dtype=np.float64)),
            "rms": float(np.sqrt(np.mean(delta * delta))),
            "l1": float(np.sum(np.abs(delta), dtype=np.float64)),
            "max_abs": float(np.max(np.abs(delta))),
            "candidate_rms": float(np.sqrt(np.mean(current * current))),
            "reference_rms": float(np.sqrt(np.mean(reference * reference)))}


def _closed_structured_run(run_root: Path, execution_preflight: dict) -> tuple[dict, dict]:
    receipt_path, preflight_path = run_root / "receipt.json", run_root / "preflight.json"
    receipt, run_preflight = json.loads(receipt_path.read_text()), json.loads(preflight_path.read_text())
    times = [row.get("timestamp") for row in receipt.get("model_timestamps", [])]
    if (receipt.get("arm") != "STRUCTURED" or run_preflight.get("arm") != "STRUCTURED"
            or receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0
            or receipt.get("timestep_count") != 32 or receipt.get("final_completed_step") != 32
            or receipt.get("maximum_seen_timestep") != 32 or receipt.get("earliest_fatal") is not None
            or receipt.get("processing_errors") != [] or receipt.get("fatal_lines") != []
            or receipt.get("changed_staged_inputs") != [] or receipt.get("changed_original_inputs") != []
            or receipt.get("duplicate_post_kdm6_timesteps") != []
            or receipt.get("candidate_build_unchanged") is not True
            or receipt.get("candidate_input_unchanged") is not True):
        raise ValueError("STRUCTURED receipt is not a clean closed 640-second run")
    if (run_preflight.get("duration_seconds") != 640 or run_preflight.get("expected_timesteps") != 32
            or run_preflight.get("candidate_wrfinput_sha256") != receipt.get("candidate_wrfinput_sha256")
            or execution_preflight.get("schema") != "pr102_execution_preflight_v1"
            or execution_preflight.get("arm") != "STRUCTURED"):
        raise ValueError("STRUCTURED receipt does not match its PR102 execution preflight")
    if times != MODEL_TIMESTAMPS:
        raise ValueError("STRUCTURED receipt timestamps differ from the 32-step C2 schedule")
    if (receipt.get("executed_executable_sha256") != preflight.EXPECTED_EXECUTABLE
            or receipt.get("candidate_wrfbdy_sha256") != preflight.EXPECTED_BOUNDARY
            or receipt.get("candidate_namelist_sha256") != preflight.EXPECTED_NAMELIST):
        raise ValueError("STRUCTURED receipt differs from the pinned C2 executable or inputs")
    return receipt, run_preflight


def _receipt(root: Path, expected_arm: str) -> dict:
    receipt = json.loads((root / "receipt.json").read_text())
    pre = json.loads((root / "preflight.json").read_text())
    pr101.validate_closed_receipt(receipt, pre, expected_arm)
    return receipt


def _verify_execution_preflight(record: dict) -> None:
    if (record.get("schema") != "pr102_execution_preflight_v1"
            or record.get("status") != "READY_FOR_ROOT_REVIEW_NO_LAUNCH"
            or record.get("arm") != "STRUCTURED"):
        raise ValueError("PR102 execution preflight is not a closed candidate-bound receipt")
    artifacts = record.get("evidence_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("PR102 execution preflight has no evidence artifact pins")
    for item in artifacts:
        path = Path(item["path"])
        if sha256(path) != item["sha256"]:
            raise ValueError(f"PR102 preflight artifact changed: {path}")


def _fixed_masks(composition_path: Path) -> tuple[dict, str]:
    digest = sha256(composition_path)
    composition = json.loads(composition_path.read_text())
    masks = cloud.make_masks(composition["composed_qc_vertical_influence"], (39, 280, 232))
    support, buffer = masks["original_613_native_support"], masks["fixed_5_cell_chebyshev_buffer"]
    if int(support.sum()) != 613 or int(support.any(axis=0).sum()) != 16 \
            or int(buffer.any(axis=0).sum()) != 196 or int(buffer.sum()) != 39 * 196:
        raise ValueError("fixed PR99 support or buffer differs from its frozen dimensions")
    return {"support": support, "buffer": buffer}, digest


def _history_comparisons(roots: dict[str, Path], receipts: dict[str, dict], masks: dict) -> dict:
    indexes, identities = {}, {}
    for role, root in roots.items():
        indexes[role], identities[role] = pr101._closed_history_index(root, receipts[role])
        stamps = sorted(indexes[role])
        if stamps != EXPECTED_TIMESTAMPS:
            raise ValueError(f"{role} history does not contain the common 0..600-second schedule")
    regions = {"support": masks["support"], "buffer": masks["buffer"]}
    records = {}
    for seconds, stamp in enumerate(EXPECTED_TIMESTAMPS):
        sec = seconds * 60
        fields = {}
        for role, index in indexes.items():
            time, values, _ = history.load_history(*index[stamp])
            if time != stamp:
                raise ValueError(f"{role} history timestamp mismatch at {stamp}")
            fields[role] = values
        records[sec] = {}
        for control in ("OFF", "HYDRO", "COUPLED", "P"):
            rows = {}
            for name in HISTORY_FIELDS:
                pair = {}
                for region, mask in regions.items():
                    pair[region] = {"unit": history.UNITS.get(name, "unknown"),
                                    **response_metrics(fields["STRUCTURED"][name][mask], fields[control][name][mask])}
                rows[name] = pair
            records[sec][f"STRUCTURED_minus_{control}"] = rows
    for role, artifacts in identities.items():
        for path, identity in artifacts.items():
            if sha256(Path(path)) != identity["sha256"]:
                raise ValueError(f"{role} history changed during comparison")
    return {"times_seconds": list(range(0, 601, 60)), "fields": list(HISTORY_FIELDS),
            "comparisons": records, "artifact_identities": identities,
            "scope": "Saved host histories at 0..600 seconds; destaggered history winds and reconstructed pressure/geopotential."}


def _trace_response(roots: dict[str, Path], receipts: dict[str, dict], masks: dict) -> dict:
    traces = {}
    for role, root in roots.items():
        path, row = pr101._trace_row(root, receipts[role])
        traces[role] = pr101._read_fixed_trace(path, row, TRACE_STEPS, masks["support"], masks["buffer"])
    comparisons = {}
    for control in ("OFF", "HYDRO", "COUPLED", "P"):
        steps = {}
        for step in sorted(TRACE_STEPS):
            steps[step * 20] = {region: {
                field: response_metrics(traces["STRUCTURED"][step][field][region],
                                        traces[control][step][field][region])
                for field in TRACE_FIELDS} for region in ("support", "buffer")}
        comparisons[f"STRUCTURED_minus_{control}"] = steps
    return {"trace_steps_seconds": [step * 20 for step in sorted(TRACE_STEPS)],
            "fields": list(TRACE_FIELDS), "comparisons": comparisons,
            "scope": "PR85 POST_KDM6 source-stage trace at selected steps through 640 seconds; separate from saved host history."}


def _source_capture_roots(execution_preflight: dict) -> tuple[dict[str, Path], dict]:
    captures = execution_preflight.get("native_source_capture_cohort", {}).get("captures", {})
    if set(captures) != {"HYDRO", "ORIGINAL_P", "CANDIDATE"}:
        raise ValueError("PR102 preflight lacks the closed H/P/N one-step capture cohort")
    roots, receipt_rows = {}, {}
    role_aliases = {"HYDRO": "H", "ORIGINAL_P": "P", "CANDIDATE": "N"}
    for label, item in captures.items():
        receipt_ref = item["receipt"]
        path = Path(receipt_ref["path"])
        if sha256(path) != receipt_ref["sha256"]:
            raise ValueError(f"{label} source capture receipt changed")
        capture = json.loads(path.read_text())
        if (capture.get("schema") != "pr102_native_source_capture_v1"
                or capture.get("status") != "COMPLETE" or capture.get("candidate_wrfinput_sha256") != item["input_sha256"]
                or capture.get("noninterference", {}).get("status") != "PASS"
                or set(capture.get("captured_sources", [])) != {"RU", "RV", "MUDF"}
                or capture.get("completed_steps") != 1):
            raise ValueError(f"{label} source capture lacks its one-step H/P/N binding")
        artifacts = capture.get("artifacts", [])
        files = []
        for artifact in artifacts:
            artifact_path = Path(artifact["path"])
            if sha256(artifact_path) != artifact["sha256"]:
                raise ValueError(f"{label} source artifact changed: {artifact_path}")
            if artifact_path.name.startswith("pr98_") and artifact_path.suffix == ".bin":
                files.append(artifact_path)
        if len(files) != 57 or not files:
            raise ValueError(f"{label} does not bind all 57 PR98 source snapshots")
        parents = {path.parent for path in files}
        if len(parents) != 1:
            raise ValueError(f"{label} PR98 snapshots are split across directories")
        roots[role_aliases[label]] = parents.pop()
        receipt_rows[role_aliases[label]] = {"receipt": receipt_ref, "input_sha256": item["input_sha256"],
                                             "snapshot_count": len(files),
                                             "diagnostic_executable_sha256": capture.get("diagnostic_executable_sha256"),
                                             "noninterference": capture["noninterference"]}
    exes = {row["diagnostic_executable_sha256"] for row in receipt_rows.values()}
    expected_exe = execution_preflight["native_source_capture_cohort"].get("diagnostic_executable_sha256")
    if len(exes) != 1 or None in exes or exes != {expected_exe}:
        raise ValueError("H/P/N source captures do not share one diagnostic executable")
    return roots, receipt_rows


def _dry_column_rates(source_roots: dict[str, Path], source_receipts: dict,
                      support_kji: np.ndarray) -> dict:
    gravity, gravity_pin = _constants(mass_effect.CONSTANTS)
    support_columns = support_kji.any(axis=0)
    rates, rows, geometry, step_sizes, reference_coords = {}, {}, {}, {}, None
    for role in ("H", "P", "N"):
        root = source_roots[role]
        input_path = root / "wrfinput_d01"
        input_sha = sha256(input_path)
        if input_sha != source_receipts[role]["input_sha256"]:
            raise ValueError(f"{role} dry-column input differs from its source-capture receipt")
        with netCDF4.Dataset(input_path) as ds:
            ds.set_auto_mask(False)
            area, _, _ = _read_map_geometry(ds, slice(None), slice(None))
            c1h, dnw = (_finite(ds, name, 0) for name in ("C1H", "DNW"))
        current_geometry = {"area": area, "C1H": c1h, "DNW": dnw}
        if geometry and any(not np.array_equal(current_geometry[name], geometry[name])
                            for name in current_geometry):
            raise ValueError("H/P/N dry-column area or hybrid coefficients differ")
        geometry = current_geometry
        if (c1h.shape != dnw.shape or c1h.size != support_kji.shape[0]
                or area.shape != (support_kji.shape[1] + 2, support_kji.shape[2] + 2)):
            raise ValueError(f"{role} dry-column geometry differs from fixed QC support")
        in_meta, before = native.native_capture_file(root, "pr98_mu_small_in_", 2)
        out_meta, after = native.native_capture_file(root, "pr98_mu_small_out_", 2)
        dt_meta, seconds = native.native_capture_file(root, "pr98_dts_small", 0)
        c1_meta, captured_c1h = native.native_capture_file(root, "pr98_geom_c1h", 1)
        mudf_meta, mudf = native.native_capture_file(root, "pr98_mudf_small_out_", 2)
        if (in_meta["fortran_bounds"] != out_meta["fortran_bounds"]
                or in_meta["fortran_bounds"] != mudf_meta["fortran_bounds"]
                or not np.array_equal(captured_c1h[:c1h.size], c1h)):
            raise ValueError(f"{role} captured MU, MUDF, or C1H does not match its input geometry")
        mask = native.support_column_mask(in_meta, before.shape, support_columns)
        if int(mask.sum()) != 16:
            raise ValueError(f"{role} dry-column support is not the fixed 16 columns")
        ims, _, jms = in_meta["fortran_bounds"][:3]
        coords = [(int(i + ims), int(j + jms)) for i, j in np.argwhere(mask)]
        if reference_coords is not None and coords != reference_coords:
            raise ValueError("H/P/N dry-column support coordinates differ")
        reference_coords = coords
        if any(not (1 <= i <= area.shape[1] and 1 <= j <= area.shape[0]) for i, j in coords):
            raise ValueError(f"{role} native support lies outside stored map area")
        weights = np.ones_like(before, dtype=np.float64)
        weights[mask] = [area[j - 1, i - 1] for i, j in coords]
        rate, beta = mass_effect.column_mass_rate(before, after, float(seconds), c1h,
                                                  dnw, weights, gravity)
        step_sizes[role] = float(seconds)
        rates[role] = rate[mask]
        update = (after.astype(np.float64) - before.astype(np.float64)) / float(seconds)
        mudf_delta = update[mask] - mudf.astype(np.float64)[mask]
        rows[role] = {"input_sha256": input_sha, "native_columns_ij": coords,
                      "hybrid_beta": beta, "seconds": float(seconds),
                      "dry_column_rate_kg_s_per_column": _vector_stats(rates[role]),
                      "area_m2_range": [float(weights[mask].min()), float(weights[mask].max())],
                      "mu_update_minus_mudf": {"unit": "native MU units/s",
                                                **_vector_stats(mudf_delta)},
                      "capture_sha256": {"mu_before": in_meta["sha256"],
                                         "mu_after": out_meta["sha256"], "dts": dt_meta["sha256"],
                                         "c1h": c1_meta["sha256"], "mudf": mudf_meta["sha256"]}}
        if sha256(input_path) != input_sha:
            raise ValueError(f"{role} dry-column input changed during analysis")
    if len(set(step_sizes.values())) != 1:
        raise ValueError("H/P/N captured dry-column timesteps differ")
    geometry_hashes = {name: hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
                       for name, values in geometry.items()}
    return {"units": "kg/s per native support column", "support_columns": 16,
            "gravity": gravity_pin, "shared_geometry_sha256": geometry_hashes,
            "arms": rows,
            "paired_increments": {"P_minus_H": response_metrics(rates["P"], rates["H"]),
                                  "N_minus_P": response_metrics(rates["N"], rates["P"]),
                                  "N_minus_H": response_metrics(rates["N"], rates["H"])},
            "hydro_baseline_nonzero": bool(np.linalg.norm(rates["H"]) > 0),
            "mudf_check": "Descriptive ΔMU/dts minus combined native MUDF; reported in native MU units/s with no invented pass tolerance. This is a source consistency diagnostic, not continuity closure."}


def _vector_stats(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("fixed-column vector must be nonempty and finite")
    return {"count": int(values.size), "signed_sum": float(np.sum(values, dtype=np.float64)),
            "l1": float(np.sum(np.abs(values), dtype=np.float64)),
            "l2": float(np.linalg.norm(values)), "rms": float(np.sqrt(np.mean(values * values))),
            "max_abs": float(np.max(np.abs(values)))}


def _rename_source_roles(value):
    aliases = {"OFF": "H", "HYDRO": "P", "COUPLED": "N",
               "HYDRO_minus_OFF": "P_minus_H", "COUPLED_minus_HYDRO": "N_minus_P",
               "COUPLED_minus_OFF": "N_minus_H", "h_H_minus_O": "P_minus_H",
               "b_C_minus_H": "N_minus_P", "net_C_minus_O": "N_minus_H"}
    if isinstance(value, dict):
        return {aliases.get(key, key): _rename_source_roles(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename_source_roles(item) for item in value]
    return value


def analyze(run_root: Path, execution_preflight_path: Path) -> dict:
    execution_preflight = json.loads(execution_preflight_path.read_text())
    _verify_execution_preflight(execution_preflight)
    structured, run_preflight = _closed_structured_run(run_root, execution_preflight)
    preflight_pin = run_preflight.get("pr102_execution_preflight", {})
    if (Path(preflight_pin.get("path", "")).resolve() != execution_preflight_path.resolve()
            or preflight_pin.get("sha256") != sha256(execution_preflight_path)):
        raise ValueError("STRUCTURED run preflight does not bind this PR102 execution preflight")
    controls_record = preflight._controls()
    roots = {"STRUCTURED": run_root}
    receipts = {"STRUCTURED": structured}
    for role, control_name in (("OFF", "OFF"), ("HYDRO", "HYDRO"), ("COUPLED", "COUPLED"), ("P", "PROJECTED")):
        root = P_ROOT if control_name == "PROJECTED" else CONTROL_ROOT / control_name
        receipts[role] = _receipt(root, control_name)
        roots[role] = root
        if (receipts[role].get("executed_executable_sha256") != structured.get("executed_executable_sha256")
                or receipts[role].get("candidate_wrfbdy_sha256") != structured.get("candidate_wrfbdy_sha256")
                or receipts[role].get("candidate_namelist_sha256") != structured.get("candidate_namelist_sha256")
                or receipts[role].get("launch_environment") != structured.get("launch_environment")):
            raise ValueError(f"{role} control does not match STRUCTURED C2 launch controls")
    if {role: receipts[role]["candidate_wrfinput_sha256"] for role in ("OFF", "HYDRO", "COUPLED", "P")} != {
            role: controls_record[control]["candidate_wrfinput_sha256"]
            for role, control in (("OFF", "OFF"), ("HYDRO", "HYDRO"), ("COUPLED", "COUPLED"), ("P", "PROJECTED"))}:
        raise ValueError("closed control input hashes differ from the PR102 preflight pins")
    if structured.get("candidate_wrfinput_sha256") != execution_preflight.get("candidate_wrfinput_sha256"):
        raise ValueError("STRUCTURED candidate input differs from the closed PR102 preflight")
    candidate_builder.verify_only_wind_changed(roots["STRUCTURED"] / "run/wrfinput_d01",
                                               roots["P"] / "run/wrfinput_d01")
    composition_path = native.COMPOSITION
    masks, composition_sha = _fixed_masks(composition_path)
    if execution_preflight.get("candidate_input_receipt_sha256") is None:
        raise ValueError("PR102 preflight does not bind the candidate proposal receipt")
    source_roots, source_receipts = _source_capture_roots(execution_preflight)
    expected_source_inputs = {"H": controls_record["HYDRO"]["candidate_wrfinput_sha256"],
                              "P": controls_record["PROJECTED"]["candidate_wrfinput_sha256"],
                              "N": execution_preflight["candidate_wrfinput_sha256"]}
    if {role: row["input_sha256"] for role, row in source_receipts.items()} != expected_source_inputs:
        raise ValueError("H/P/N source-capture inputs differ from the pinned controls/candidate")
    source_raw = native.analyze_native_capture(
        {"OFF": source_roots["H"], "HYDRO": source_roots["P"], "COUPLED": source_roots["N"]}, masks["support"])
    source_report = _rename_source_roles(source_raw)
    source_report["source_capture_role_mapping"] = {"H": "HYDRO", "P": "original P", "N": "candidate"}
    dry_column_rates = _dry_column_rates(source_roots, source_receipts, masks["support"])
    history_report = _history_comparisons(roots, receipts, masks)
    trace_report = _trace_response(roots, receipts, masks)
    return {"schema": "pr102_structured_response_v1", "status": "DESCRIPTIVE_ONLY",
            "candidate": {"arm": "STRUCTURED", "receipt": str(run_root / "receipt.json"),
                          "receipt_sha256": sha256(run_root / "receipt.json"),
                          "candidate_input_sha256": structured["candidate_wrfinput_sha256"],
                          "run_preflight_sha256": sha256(run_root / "preflight.json")},
            "fixed_support": {"composition_path": str(composition_path), "composition_sha256": composition_sha,
                              "mass_support_cells": 613, "support_columns": 16,
                              "buffer_columns": 196, "buffer_levels": 39},
            "controls": {role: {"receipt": str(roots[role] / "receipt.json"),
                                "receipt_sha256": sha256(roots[role] / "receipt.json"),
                                "input_sha256": receipts[role]["candidate_wrfinput_sha256"]}
                         for role in ("OFF", "HYDRO", "COUPLED", "P")},
            "candidate_vs_P_input": "All dimensions, global and variable metadata and non-U/V values byte-identical; only U/V may differ.",
            "first_source_capture": {"role_mapping": {"H": "HYDRO source capture", "P": "original P source capture",
                                                           "N": "new candidate source capture"},
                                     "captures": source_receipts,
                                     "native_source_coordinate_response": source_report,
                                     "physical_dry_column_rate": dry_column_rates,
                                     "units_note": "Raw RU/RV source-coordinate responses and MUDF/MU native mass diagnostics remain separate units/stages; no energy, acceleration, or continuity closure is claimed."},
            "saved_history_0_600_seconds": history_report,
            "post_kdm6_trace_640_seconds": trace_report,
            "limits": ["Norms and differences are descriptive; no response-derived cutoff or favorable mask is used.",
                       "Saved history and POST_KDM6 source-stage trace are separate measurements.",
                       "Observation skill is NOT_EVALUATED; no matched authorized Y/H/error authority is bound.",
                       "Physical approval remains FAIL_OPEN; this report is not a forecast approval."],
            "observation_skill": "NOT_EVALUATED", "physical_approval": "FAIL_OPEN"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path,
                        help="closed STRUCTURED run directory containing receipt.json, preflight.json, and run/")
    parser.add_argument("--execution-preflight", required=True, type=Path,
                        help="candidate-bound PR102 preflight that pins H/P/N captures and controls")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.run_root, args.execution_preflight)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
