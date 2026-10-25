#!/usr/bin/env python3
"""Prepare a fixed-mask five-arm PR102 C2 history readback; run only after closure."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np

TOOLS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL/tools")
sys.path.insert(0, str(TOOLS))
import pr86_compare_response as history
import pr101_projected_c2_response as pr101
import pr102_response as response
import pr102_native_wind_candidate as candidate_builder

EXPECTED_CODE = {
    "pr102_response.py": "9e30de564c85b5cfdbb8c9141d3f86f68d2958582892c62ad7578c77affe866e",
    "pr86_compare_response.py": "64b2f97f452035cae328576d26216c54877fa778b3eeabe17cdb9980103aaa5c",
    "pr101_projected_c2_response.py": "1bc24af37f04427d10be6ca3620ec0df8c0cb190a9983f3c7ef5caa70612c8ba",
    "pr94_cloud_response.py": "a626b22f234b3095202982a4fe32d89d9ab6c200e4a9547f6a06a8b109536537",
    "pr87_native_history.py": "d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71",
    "pr95_call_budget.py": "b7ca2a0d4c5f56ecd9c2628c1d8f47b8131d8a0bbb4e12ce047281673159961f",
    "pr102_execution_preflight.py": "e80f5fc69e4b8cc7ee4dbe0281265faa7f1a97c9856c1be52e02a42ab9900277",
    "pr102_native_wind_candidate.py": "f044c57605942504a0c8ece22b915e8bd64bc2ddacb46a9cecd6920081f15b85",
}
ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee")
CONTROL_ROOT = ROOT / "pr99_c2_matched640_20261022"
P_ROOT = ROOT / "pr101_projected_c2_640_20261023"
ROLES = {"OFF": CONTROL_ROOT / "OFF", "HYDRO": CONTROL_ROOT / "HYDRO",
         "COUPLED": CONTROL_ROOT / "COUPLED", "P": P_ROOT}
FIELDS = {"pressure": "pressure", "Phi": "geopotential", "W": "W", "QC": "QCLOUD"}
REGIONS = ("support", "buffer")
ARMS = ("HYDRO", "COUPLED", "P", "STRUCTURED")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_pins() -> dict[str, str]:
    paths = {name: TOOLS / name for name in EXPECTED_CODE}
    actual = {name: sha(path) for name, path in paths.items()}
    if actual != EXPECTED_CODE:
        raise RuntimeError("a reviewed reader/source dependency hash changed")
    actual[Path(__file__).name] = sha(Path(__file__))
    return actual


def _metrics(values: np.ndarray) -> dict:
    delta = np.asarray(values, dtype=np.float64).ravel()
    if delta.size == 0 or not np.isfinite(delta).all():
        raise ValueError("fixed-mask response contains no finite values")
    return {"count": int(delta.size), "signed_sum": float(delta.sum(dtype=np.float64)),
            "l2": float(np.linalg.norm(delta)), "rms": float(np.sqrt(np.mean(delta * delta))),
            "max_abs": float(np.max(np.abs(delta)))}


def _receipt_artifacts(run_root: Path, receipt: dict, receipt_path: Path,
                       preflight_path: Path) -> tuple[dict, dict]:
    receipt_hashes = {str(receipt_path): sha(receipt_path), str(preflight_path): sha(preflight_path)}
    index, identities = pr101._closed_history_index(run_root, receipt)
    if set(identities) != {str(run_root / "run" / Path(p).name) for p in identities}:
        raise RuntimeError("history artifact paths are not rooted in the closed run")
    return index, identities


def _closed_cohort(run_root: Path, execution_path: Path) -> tuple[dict, dict, dict, dict]:
    execution = json.loads(execution_path.read_text())
    response._verify_execution_preflight(execution)
    structured, run_pre = response._closed_structured_run(run_root, execution)
    run_pre_path = run_root / "preflight.json"
    execution_pin = run_pre.get("pr102_execution_preflight", {})
    if (Path(execution_pin.get("path", "")).resolve() != execution_path.resolve()
            or execution_pin.get("sha256") != sha(execution_path)
            or structured.get("candidate_wrfinput_sha256") != execution.get("candidate_wrfinput_sha256")):
        raise ValueError("closed STRUCTURED run does not bind this candidate preflight")
    controls = response.preflight._controls()
    roots = {"STRUCTURED": run_root, **ROLES}
    receipts = {"STRUCTURED": structured}
    for role, root in ROLES.items():
        receipts[role] = response._receipt(root, role if role != "P" else "PROJECTED")
        row = receipts[role]
        if any(row.get(name) != structured.get(name) for name in
               ("executed_executable_sha256", "candidate_wrfbdy_sha256", "candidate_namelist_sha256", "launch_environment")):
            raise ValueError(f"{role} is not a matched C2 control for STRUCTURED")
    if {role: receipts[role]["candidate_wrfinput_sha256"] for role in ("OFF", "HYDRO", "COUPLED", "P")} != {
            role: controls[name]["candidate_wrfinput_sha256"] for role, name in
            (("OFF", "OFF"), ("HYDRO", "HYDRO"), ("COUPLED", "COUPLED"), ("P", "PROJECTED"))}:
        raise ValueError("C2 control inputs differ from pinned execution preflight")
    masks, composition_sha = response._fixed_masks(response.native.COMPOSITION)
    if composition_sha != "331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64":
        raise ValueError("frozen support composition hash changed")
    if structured.get("candidate_wrfinput_sha256") != execution.get("candidate_wrfinput_sha256"):
        raise ValueError("candidate input hash differs from preflight")
    candidate_builder.verify_only_wind_changed(run_root / "run/wrfinput_d01",
                                               P_ROOT / "run/wrfinput_d01")
    source_roots, _ = response._source_capture_roots(execution)
    if any(sha(source_roots[alias] / "wrfinput_d01") != expected for alias, expected in
           (("H", controls["HYDRO"]["candidate_wrfinput_sha256"],),
            ("P", controls["PROJECTED"]["candidate_wrfinput_sha256"],),
            ("N", execution["candidate_wrfinput_sha256"],))):
        raise ValueError("source-capture control/candidate input binding changed")
    return execution, structured, receipts, masks


def readback(run_root: Path, execution_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    before_code = code_pins()
    execution, structured, receipts, masks = _closed_cohort(run_root, execution_path)
    roots = {"STRUCTURED": run_root, **ROLES}
    indexes, identities = {}, {}
    artifact_pins = {str(execution_path): sha(execution_path),
                     str(response.native.COMPOSITION): sha(response.native.COMPOSITION)}
    for role, root in roots.items():
        receipt_path, run_pre_path = root / "receipt.json", root / "preflight.json"
        indexes[role], identities[role] = _receipt_artifacts(root, receipts[role], receipt_path, run_pre_path)
        artifact_pins[str(receipt_path)] = sha(receipt_path)
        artifact_pins[str(run_pre_path)] = sha(run_pre_path)
        artifact_pins.update({path: row["sha256"] for path, row in identities[role].items()})
        timestamps = sorted(indexes[role])
        if timestamps != response.EXPECTED_TIMESTAMPS:
            raise ValueError(f"{role} does not have the exact shared 0..600 s/60 s history schedule")
    regions = {"support": masks["support"], "buffer": masks["buffer"]}
    records, plot_values = {}, {name: {region: {arm: [] for arm in ARMS} for region in REGIONS}
                               for name in FIELDS}
    for sec, stamp in zip(range(0, 601, 60), response.EXPECTED_TIMESTAMPS):
        fields = {}
        for role, index in indexes.items():
            timestamp, values, _ = history.load_history(*index[stamp])
            if timestamp != stamp:
                raise ValueError(f"{role} history timestamp mismatch")
            fields[role] = values
        records[str(sec)] = {}
        for label, field in FIELDS.items():
            records[str(sec)][label] = {"unit": history.UNITS[field], "minus_OFF": {}}
            for arm in ARMS:
                row = {}
                delta = fields[arm][field].astype(np.float64) - fields["OFF"][field].astype(np.float64)
                for region, mask in regions.items():
                    metric = _metrics(delta[mask])
                    row[region] = metric
                    plot_values[label][region][arm].append(metric["rms"])
                records[str(sec)][label]["minus_OFF"][arm] = row
    for identity in artifact_pins:
        if sha(Path(identity)) != artifact_pins[identity]:
            raise ValueError(f"receipt/history artifact changed during readback: {identity}")
    after_code = code_pins()
    if before_code != after_code:
        raise RuntimeError("reviewed code or this script changed during readback")

    output_dir.mkdir(parents=True)
    report = {"schema": "pr102_fivearm_fixed_history_readback_v1", "status": "DESCRIPTIVE_ONLY",
              "source_scope": "Matched C2 saved host history, five arms at 0..600 s/60 s; all four fields compared with actual C2 OFF.",
              "fixed_support": {"composition_sha256": sha(response.native.COMPOSITION),
                                "support_cells": 613, "support_columns": 16,
                                "buffer_columns": 196, "buffer_levels": 39},
              "candidate_receipt_sha256": sha(run_root / "receipt.json"),
              "execution_preflight_sha256": sha(execution_path),
              "controls": {role: {"receipt_sha256": sha(root / "receipt.json"),
                                  "input_sha256": receipts[role]["candidate_wrfinput_sha256"]}
                           for role, root in roots.items()},
              "fields": {name: {"source_field": field, "unit": history.UNITS[field]} for name, field in FIELDS.items()},
              "times_seconds": list(range(0, 601, 60)), "references": "actual C2 OFF arm",
              "metrics": records, "artifact_pins_before_after": artifact_pins,
              "code_pins_before_after": {"before": before_code, "after": after_code},
              "runtime": {"numpy": np.__version__, "netCDF4": netCDF4.__version__,
                          "matplotlib": matplotlib.__version__},
              "limits": ["RMS panels are descriptive response plots, not observation scores.",
                         "No post-response mask, timestamp, or threshold selection is performed.",
                         "Pressure, geopotential, W, and QCLOUD keep their native fields/units; no causal or forecast-skill claim is inferred."],
              "observation_skill": "NOT_EVALUATED", "physical_approval": "FAIL_OPEN"}
    with (output_dir / "fivearm_history_readback.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    seconds = np.arange(0, 601, 60)
    for ax, (label, field) in zip(axes.flat, FIELDS.items()):
        for arm in ARMS:
            line, = ax.plot(seconds, plot_values[label]["support"][arm], label=f"{arm} support")
            ax.plot(seconds, plot_values[label]["buffer"][arm], linestyle="--", color=line.get_color(),
                    label=f"{arm} buffer")
        ax.set_title(f"{label}: RMS(arm − OFF) [{history.UNITS[field]}]")
        ax.set_xlabel("model seconds")
        ax.set_ylabel("RMS difference")
        ax.grid(True, alpha=0.25)
    axes.flat[0].legend(fontsize=7, ncol=2)
    fig.suptitle("PR102 matched C2 history response on frozen support and buffer")
    fig.savefig(output_dir / "fivearm_history_response.png", dpi=180)
    fig.savefig(output_dir / "fivearm_history_response.pdf")
    plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True, help="closed STRUCTURED C2 640 s run")
    parser.add_argument("--execution-preflight", type=Path, required=True, help="closed candidate-bound execution preflight")
    parser.add_argument("--output-dir", type=Path, required=True, help="fresh directory for JSON, PNG, and PDF")
    args = parser.parse_args()
    readback(args.run_root, args.execution_preflight, args.output_dir)


if __name__ == "__main__":
    main()
