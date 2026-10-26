#!/usr/bin/env python3
"""Build the six-arm PR103 fixed-mask readback after a closed A640 run."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np

import pr86_compare_response as history
import pr101_projected_c2_response as pr101
import pr102_response as pr102
import pr103_time_response as time_response
import pr86_time_response as runner

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
RUN_ROOTS = {
    "OFF": ROOT / "pr99_c2_matched640_20261022/OFF",
    "HYDRO": ROOT / "pr99_c2_matched640_20261022/HYDRO",
    "COUPLED": ROOT / "pr99_c2_matched640_20261022/COUPLED",
    "P": ROOT / "pr101_projected_c2_640_20261023",
    "STRUCTURED": ROOT / "pr102_native_structure640_20261025/STRUCTURED640_RUN",
}
PR102_PREFLIGHT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL/docs/evidence/pr102_execution_20261025/preflight.json")
PR102_PREFLIGHT_SHA256 = "c58feba119b7c774dc2b37e416bb6a46d49cdadfba104c7ef5c469faf5592dea"
FIVEARM_READBACK = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json")
FIVEARM_READBACK_SHA256 = "d10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2"
FIVEARM_EXECUTION = FIVEARM_READBACK.parent / "execution.json"
FIVEARM_EXECUTION_SHA256 = "cfb54c75dfd6d6b6e101a98a7f24e7ecd3b3cd1beba1d949c03ec7d5a7ddcd9d"
FIVEARM_PUBLICATION = FIVEARM_READBACK.parent / "publication.json"
FIVEARM_PUBLICATION_SHA256 = "cfa3dc8084b1d6366e93e6a55e37df981ee11466e66384c73f8a6b65b4fdacdd"
FIVEARM_RESPONSE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr103_time_response_20261026/allsavedtime_response.json")
FIVEARM_RESPONSE_SHA256 = "5b7550bbde89d1cbe1182295167ad80c36fc7e95843f3683a2226ddf38bc8f6b"
COMPOSITION_SHA256 = "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64"
FIELDS = {"pressure": ("pressure", "Pa"), "Phi": ("geopotential", "m2/s2"),
          "W": ("W", "m/s"), "QC": ("QCLOUD", "kg/kg dry")}
TIMES = tuple(range(0, 601, 60))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_pin(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"{label} pin changed: {path}")


def _read_fivearm() -> dict:
    _require_pin(FIVEARM_READBACK, FIVEARM_READBACK_SHA256, "frozen five-arm readback")
    _require_pin(FIVEARM_EXECUTION, FIVEARM_EXECUTION_SHA256, "frozen five-arm execution receipt")
    _require_pin(FIVEARM_PUBLICATION, FIVEARM_PUBLICATION_SHA256, "frozen five-arm publication")
    publication = json.loads(FIVEARM_PUBLICATION.read_text())
    if (publication.get("status") != "COMPLETE" or not any(
            row.get("published") == "docs/evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json"
            and row.get("sha256") == FIVEARM_READBACK_SHA256
            for row in publication.get("artifacts", []))):
        raise ValueError("frozen five-arm publication does not bind the retained readback")
    receipt = json.loads(FIVEARM_EXECUTION.read_text())
    if (receipt.get("status") != "COMPLETE" or receipt.get("task") != "fivearm"
            or receipt.get("returncode") != 0
            or receipt.get("products", {}).get("products/fivearm_history_readback.json")
            != FIVEARM_READBACK_SHA256):
        raise ValueError("frozen five-arm execution receipt does not close the readback")
    readback = json.loads(FIVEARM_READBACK.read_text())
    if (readback.get("status") != "DESCRIPTIVE_ONLY"
            or readback.get("physical_approval") != "FAIL_OPEN"
            or readback.get("observation_skill") != "NOT_EVALUATED"
            or readback.get("times_seconds") != list(TIMES)
            or set(readback.get("fields", {})) != set(FIELDS)):
        raise ValueError("frozen five-arm readback differs from the fixed descriptive contract")
    return readback


def _closed_cohort() -> tuple[dict, dict, dict]:
    _require_pin(PR102_PREFLIGHT, PR102_PREFLIGHT_SHA256, "PR102 candidate preflight")
    preflight = json.loads(PR102_PREFLIGHT.read_text())
    pr102._verify_execution_preflight(preflight)
    n_receipt, _ = pr102._closed_structured_run(RUN_ROOTS["STRUCTURED"], preflight)
    receipts = {"STRUCTURED": n_receipt}
    control_pins = pr102.preflight._controls()
    control_names = {"OFF": "OFF", "HYDRO": "HYDRO", "COUPLED": "COUPLED", "P": "PROJECTED"}
    for alias, name in control_names.items():
        root = RUN_ROOTS[alias]
        receipts[alias] = pr102._receipt(root, name)
        candidate_sha = control_pins[name]["candidate_wrfinput_sha256"]
        if receipts[alias].get("candidate_wrfinput_sha256") != candidate_sha:
            raise ValueError(f"{alias} input does not match the closed PR102 reference")
        for key in ("executed_executable_sha256", "candidate_wrfbdy_sha256",
                    "candidate_namelist_sha256", "launch_environment"):
            if receipts[alias].get(key) != n_receipt.get(key):
                raise ValueError(f"{alias} does not match the closed N C2 run for {key}")
    expected_inputs = {"OFF": control_pins["OFF"]["candidate_wrfinput_sha256"],
                       "HYDRO": control_pins["HYDRO"]["candidate_wrfinput_sha256"],
                       "COUPLED": control_pins["COUPLED"]["candidate_wrfinput_sha256"],
                       "P": control_pins["PROJECTED"]["candidate_wrfinput_sha256"],
                       "STRUCTURED": preflight["candidate_wrfinput_sha256"]}
    for arm, expected in expected_inputs.items():
        if receipts[arm].get("candidate_wrfinput_sha256") != expected:
            raise ValueError(f"{arm} run receipt input differs from the fixed C2 cohort")
    return preflight, receipts, control_pins


def _closed_a_run(run_root: Path) -> tuple[dict, dict, dict, dict]:
    receipt_path = run_root / "receipt.json"
    run_preflight_path = run_root / "preflight.json"
    receipt = json.loads(receipt_path.read_text())
    run_preflight = json.loads(run_preflight_path.read_text())
    expected_a = {
        "arm": "AMPLITUDE", "status": "COMPLETE", "returncode": 0,
        "timestep_count": 32, "final_completed_step": 32, "maximum_seen_timestep": 32,
        "candidate_wrfinput_sha256": time_response.A_CANDIDATE_SHA256,
        "executed_executable_sha256": time_response.A_EXECUTABLE_SHA256,
        "candidate_wrfbdy_sha256": time_response.A_BOUNDARY_SHA256,
        "candidate_namelist_sha256": time_response.A_NAMELIST_SHA256,
    }
    if any(receipt.get(key) != value for key, value in expected_a.items()):
        raise ValueError("A model receipt does not close the pinned 640-second candidate run")
    if (receipt.get("earliest_fatal") is not None or receipt.get("fatal_lines")
            or receipt.get("processing_errors") or receipt.get("changed_staged_inputs")
            or receipt.get("changed_original_inputs") or receipt.get("duplicate_post_kdm6_timesteps")
            or receipt.get("candidate_build_unchanged") is not True
            or receipt.get("candidate_input_unchanged") is not True):
        raise ValueError("A model receipt records errors, input changes, or incomplete candidate bindings")
    expected_model_times = [(history.START + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                            for step in range(1, 33)]
    if [row.get("timestamp") for row in receipt.get("model_timestamps", [])] != expected_model_times:
        raise ValueError("A model timestamps differ from the fixed 32-step C2 schedule")
    if (run_preflight.get("arm") != "AMPLITUDE" or run_preflight.get("duration_seconds") != 640
            or run_preflight.get("expected_timesteps") != 32
            or run_preflight.get("candidate_wrfinput_sha256") != time_response.A_CANDIDATE_SHA256
            or run_preflight.get("candidate_build", {}).get("executable_sha256") != time_response.A_EXECUTABLE_SHA256
            or run_preflight.get("candidate_wrfbdy_sha256") != time_response.A_BOUNDARY_SHA256
            or run_preflight.get("candidate_namelist_sha256") != time_response.A_NAMELIST_SHA256):
        raise ValueError("A run-local preflight differs from the closed 640-second candidate")
    input_binding = receipt.get("candidate_input_binding", {})
    if (input_binding.get("receipt_path") != str(time_response.A_PROPOSAL_PATH)
            or input_binding.get("receipt_sha256") != time_response.A_PROPOSAL_SHA256):
        raise ValueError("A model receipt does not bind the frozen proposal")
    expected_gate = receipt.get("pr103_execution_preflight", {})
    gate_path = Path(expected_gate.get("path", ""))
    _require_pin(gate_path, expected_gate.get("sha256", ""), "PR103 640 preflight")
    gate = runner._validate_pr103_preflight(gate_path, input_binding, receipt.get("candidate_build", {}))
    if gate != expected_gate:
        raise ValueError("A model receipt is not bound to its frozen PR103 preflight")
    return receipt, run_preflight, gate, {
        "path": str(receipt_path.resolve()), "sha256": sha256(receipt_path),
        "preflight_path": str(gate_path.resolve()), "preflight_sha256": expected_gate["sha256"]}


def _history_indexes(roots: dict[str, Path], receipts: dict[str, dict]) -> tuple[dict, dict]:
    indexes, identities = {}, {}
    expected = [(history.START + dt.timedelta(seconds=s)).strftime("%Y-%m-%d_%H:%M:%S")
                for s in TIMES]
    for arm, root in roots.items():
        indexes[arm], identities[arm] = pr101._closed_history_index(root, receipts[arm])
        if sorted(indexes[arm]) != expected:
            raise ValueError(f"{arm} closed history does not contain exactly 0..600s at 60s cadence")
    return indexes, identities


def _metrics(current: np.ndarray, reference: np.ndarray) -> dict:
    current = np.asarray(current, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if current.shape != reference.shape or current.size == 0 or not np.isfinite(current).all() or not np.isfinite(reference).all():
        raise ValueError("fixed-mask history arrays must have identical finite support")
    delta = current - reference
    return {"count": int(delta.size), "signed_sum": float(delta.sum(dtype=np.float64)),
            "l2": float(np.linalg.norm(delta)), "rms": float(np.sqrt(np.mean(delta * delta))),
            "max_abs": float(np.max(np.abs(delta)))}


def _check_baseline_metrics(readback: dict, seconds: int, field: str, arm: str,
                            region: str, metrics: dict) -> None:
    old = readback["metrics"][str(seconds)][field]["minus_OFF"][arm][region]
    for key in ("count", "signed_sum", "l2", "rms", "max_abs"):
        if old.get(key) != metrics[key]:
            raise ValueError(f"recomputed frozen five-arm metric differs: {seconds}s/{field}/{arm}/{region}/{key}")


def _append_frame_metrics(readback: dict, seconds: int, arrays: dict, masks: dict) -> None:
    regions = {"support": masks["support"], "buffer": masks["buffer"]}
    for field in FIELDS:
        for arm in ("HYDRO", "COUPLED", "P", "STRUCTURED"):
            for region, mask in regions.items():
                actual = _metrics(arrays[arm][field][mask], arrays["OFF"][field][mask])
                _check_baseline_metrics(readback, seconds, field, arm, region, actual)
        off_rows = {}
        for region, mask in regions.items():
            off_rows[region] = {key: _metrics(arrays["A"][field][mask], arrays["OFF"][field][mask])[key]
                                for key in ("count", "rms")}
        readback["metrics"][str(seconds)][field]["minus_OFF"]["A"] = off_rows
        for reference, raw_reference in (("P", "P"), ("N", "STRUCTURED"), ("H", "HYDRO")):
            pair_key = f"A_minus_{reference}"
            pair = {"unit": FIELDS[field][1]}
            for region, mask in regions.items():
                actual = _metrics(arrays["A"][field][mask], arrays[raw_reference][field][mask])
                pair[region] = {key: actual[key] for key in ("count", "rms")}
            readback.setdefault("paired_metrics", {}).setdefault(pair_key, {}).setdefault(str(seconds), {})[field] = pair


def _append_amplitude(readback: dict, indexes: dict, masks: dict) -> dict:
    field_sources = {label: source for label, (source, _) in FIELDS.items()}
    for seconds in TIMES:
        stamp = (history.START + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d_%H:%M:%S")
        arrays = {}
        for arm, index in indexes.items():
            path, frame = index[stamp]
            loaded_time, loaded, _ = history.load_history(path, frame)
            if loaded_time != stamp:
                raise ValueError(f"{arm} history frame differs from the fixed timestamp {stamp}")
            arrays[arm] = {}
            for label, source in field_sources.items():
                values = loaded[source]
                if values.shape != (39, 280, 232) or not np.isfinite(values).all():
                    raise ValueError(f"{arm}/{source} history has unexpected shape or nonfinite values")
                arrays[arm][label] = values
        _append_frame_metrics(readback, seconds, arrays, masks)
        del arrays
    return readback


def _write_fresh(path: Path, value: dict, owned_files: list[Path] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("x") as stream:
            created = True
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        if owned_files is not None:
            owned_files.append(path)
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def _analyze(a_run_root: Path, output_dir: Path, owned_files: list[Path]) -> dict:
    baseline = _read_fivearm()
    pr102_preflight, reference_receipts, _ = _closed_cohort()
    a_receipt, _, a_gate, a_run_pin = _closed_a_run(a_run_root)
    roots = {**RUN_ROOTS, "A": a_run_root}
    receipts = {**reference_receipts, "A": a_receipt}
    for arm, receipt in receipts.items():
        if receipt.get("executed_executable_sha256") != a_receipt.get("executed_executable_sha256") or \
                receipt.get("candidate_wrfbdy_sha256") != a_receipt.get("candidate_wrfbdy_sha256") or \
                receipt.get("candidate_namelist_sha256") != a_receipt.get("candidate_namelist_sha256") or \
                receipt.get("launch_environment") != a_receipt.get("launch_environment"):
            raise ValueError(f"{arm} is not matched to the A C2 executable/boundary/namelist/launch")
    masks, composition_sha = pr102._fixed_masks(pr102.native.COMPOSITION)
    if composition_sha != COMPOSITION_SHA256:
        raise ValueError("frozen PR99 fixed-mask composition changed")
    source_paths = {
        FIVEARM_READBACK, FIVEARM_EXECUTION, FIVEARM_PUBLICATION, FIVEARM_RESPONSE,
        PR102_PREFLIGHT,
        pr102.native.COMPOSITION, time_response.A_CANDIDATE_PATH,
        time_response.A_PROPOSAL_PATH, a_run_root / "receipt.json", a_run_root / "preflight.json",
        Path(a_gate["path"]),
        Path(__file__).resolve(), Path(history.__file__).resolve(), Path(pr101.__file__).resolve(),
        Path(pr102.__file__).resolve(), Path(pr102.cloud.__file__).resolve(),
        Path(time_response.__file__).resolve(), Path(runner.__file__).resolve(),
    }
    reader_path = Path(json.loads(FIVEARM_EXECUTION.read_text())["command"][1])
    source_paths.add(reader_path)
    source_paths.update((Path(a_receipt["candidate_build"]["executable_path"]),
                         Path(a_receipt["candidate_build"]["profile_path"]),
                         Path(a_receipt["candidate_build"]["receipt_path"])))
    for arm, receipt in receipts.items():
        root = roots[arm]
        source_paths.update((root / "receipt.json", root / "preflight.json"))
    for receipt in receipts.values():
        build = receipt.get("candidate_build")
        if isinstance(build, dict) and build.get("receipt_path"):
            source_paths.add(Path(build["receipt_path"]))
    source_pins_before = {str(path.resolve()): sha256(path) for path in sorted(source_paths)}
    indexes, identities = _history_indexes(roots, receipts)
    history_pins_before = {arm: {path: identity["sha256"] for path, identity in rows.items()}
                           for arm, rows in identities.items()}
    readback = _append_amplitude(baseline, indexes, masks)
    readback["schema"] = "pr103_sixarm_fixed_history_readback_v1"
    readback["source_scope"] = "Actual saved host arrays at predeclared 0..600 seconds, 60s cadence; H/C/P/N five-arm values preserved from the immutable PR102 reader output and independently checked against receipt-bound arrays; A−OFF and A−P/N/H calculated from native history arrays."
    readback["amplitude_source"] = {"run_receipt": a_run_pin,
                                    "execution_preflight": {"path": str(a_gate.get("path", "")),
                                                            "sha256": a_gate.get("sha256")},
                                    "candidate_wrfinput_sha256": a_receipt["candidate_wrfinput_sha256"],
                                    "proposal_sha256": time_response.A_PROPOSAL_SHA256,
                                    "executed_executable_sha256": a_receipt["executed_executable_sha256"],
                                    "candidate_wrfbdy_sha256": a_receipt["candidate_wrfbdy_sha256"],
                                    "candidate_namelist_sha256": a_receipt["candidate_namelist_sha256"],
                                    "baseline_fivearm_readback_sha256": FIVEARM_READBACK_SHA256}
    readback["sixarm_history_artifacts"] = identities
    readback_path = output_dir / "history_readback.json"
    _write_fresh(readback_path, readback, owned_files)
    a_run_path = Path(a_run_pin["path"])
    gate_pin = a_receipt["pr103_execution_preflight"]
    history_snapshots = []
    for index, seconds in enumerate(TIMES):
        stamp = (history.START + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d_%H:%M:%S")
        history_path, frame = indexes["A"][stamp]
        identity = identities["A"][str(history_path)]
        history_snapshots.append({"path": str(history_path), "sha256": identity["sha256"],
                                  "time_seconds": seconds, "record_index": frame})
    closure = {
        "schema": "pr103_closed_history_readback_receipt_v1", "status": "CLOSED", "arm": "A",
        "readback_path": str(readback_path.resolve()), "readback_sha256": sha256(readback_path),
        "times_seconds": list(TIMES), "paired_comparisons": ["A_minus_P", "A_minus_N", "A_minus_H"],
        "model_run_receipt": {"path": str(a_run_path), "sha256": a_run_pin["sha256"]},
        "execution_preflight": {"path": gate_pin["path"], "sha256": gate_pin["sha256"]},
        "history_snapshots": history_snapshots,
        "candidate_wrfinput_path": str(time_response.A_CANDIDATE_PATH),
        "candidate_wrfinput_sha256": time_response.A_CANDIDATE_SHA256,
        "proposal_path": str(time_response.A_PROPOSAL_PATH), "proposal_sha256": time_response.A_PROPOSAL_SHA256,
        "executed_executable_sha256": time_response.A_EXECUTABLE_SHA256,
        "candidate_wrfbdy_sha256": time_response.A_BOUNDARY_SHA256,
        "candidate_namelist_sha256": time_response.A_NAMELIST_SHA256,
    }
    closure_path = output_dir / "closed_history_readback_receipt.json"
    _write_fresh(closure_path, closure, owned_files)
    response = time_response.build_response(json.loads(readback_path.read_text()),
                                            input_path=readback_path,
                                            new_arm_receipt=closure_path)
    _require_pin(FIVEARM_RESPONSE, FIVEARM_RESPONSE_SHA256, "frozen five-arm integrated response")
    baseline_response = json.loads(FIVEARM_RESPONSE.read_text())
    for field in FIELDS:
        for arm in ("H", "C", "P", "N", "OFF"):
            for region in ("support", "buffer"):
                if response["metrics"][field][arm][region] != baseline_response["metrics"][field][arm][region]:
                    raise ValueError(f"integrated frozen five-arm metric changed: {field}/{arm}/{region}")
    response["baseline_fivearm_source"] = {
        "readback_path": str(FIVEARM_READBACK), "readback_sha256": FIVEARM_READBACK_SHA256,
        "execution_receipt_path": str(FIVEARM_EXECUTION),
        "execution_receipt_sha256": FIVEARM_EXECUTION_SHA256,
        "integrated_response_path": str(FIVEARM_RESPONSE),
        "integrated_response_sha256": FIVEARM_RESPONSE_SHA256,
        "existing_metrics_preserved_and_array_checked": True,
    }
    response["history_readback_receipt"] = {"path": str(closure_path), "sha256": sha256(closure_path)}
    response["source_scope"] = readback["source_scope"]
    response_path = output_dir / "allsavedtime_response.json"
    _write_fresh(response_path, response, owned_files)
    source_pins_after = {path: sha256(Path(path)) for path in source_pins_before}
    history_pins_after = {arm: {path: sha256(Path(path)) for path in rows}
                          for arm, rows in history_pins_before.items()}
    if source_pins_after != source_pins_before or history_pins_after != history_pins_before:
        raise ValueError("one or more source, receipt, input, or history artifacts changed during postprocessing")
    return {"status": "DESCRIPTIVE_ONLY", "readback_path": str(readback_path),
            "readback_sha256": sha256(readback_path), "closure_receipt_path": str(closure_path),
            "closure_receipt_sha256": sha256(closure_path), "response_path": str(response_path),
            "response_sha256": sha256(response_path), "composition_sha256": composition_sha,
            "fivearm_readback_sha256": FIVEARM_READBACK_SHA256,
            "fivearm_execution_receipt_sha256": FIVEARM_EXECUTION_SHA256,
            "PR102_preflight_sha256": sha256(PR102_PREFLIGHT),
            "A_run_receipt_sha256": a_run_pin["sha256"],
            "A_preflight_sha256": a_run_pin["preflight_sha256"],
            "source_pins_before": source_pins_before,
            "source_pins_after": source_pins_after,
            "history_pins_before": history_pins_before,
            "history_pins_after": history_pins_after,
            "times_seconds": list(TIMES), "physical_approval": "FAIL_OPEN",
            "observation_skill": "NOT_EVALUATED"}


def analyze(a_run_root: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise ValueError(f"output directory must be fresh: {output_dir}")
    output_dir.mkdir(parents=True)
    owned_files: list[Path] = []
    try:
        result = _analyze(a_run_root, output_dir, owned_files)
        _write_fresh(output_dir / "execution_receipt.json", {
            "schema": "pr103_sixarm_history_response_execution_v1",
            **result, "status": "COMPLETE"}, owned_files)
        return result
    except Exception as exc:
        for path in reversed(owned_files):
            path.unlink(missing_ok=True)
        failed = {"schema": "pr103_sixarm_history_response_execution_v1",
                  "status": "FAILED", "error": f"{type(exc).__name__}: {exc}",
                  "a_run_root": str(a_run_root), "output_dir": str(output_dir),
                  "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}
        receipt_path = output_dir / "execution_receipt.json"
        if not receipt_path.exists():
            _write_fresh(receipt_path, failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-run-root", type=Path, required=True,
                        help="closed AMPLITUDE 640-second run with receipt.json, preflight.json, and run/")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="fresh directory for A-aware readback, receipt, and integrated response")
    args = parser.parse_args()
    print(json.dumps(analyze(args.a_run_root, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
