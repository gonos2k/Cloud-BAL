#!/usr/bin/env python3
"""Plot weighted selected qr profiles from analyzer-validated KDM6 endpoints."""

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
ARMS = ("OFF", "HYDRO", "LIQUID")
ROLES = ("P01", "P05", "P09", "P13")
CORNERS = ("00", "10", "01", "11")
EXPECTED_INITIAL_SHA256 = "522fc8600eb32e7c96baed296f57342fbfb51c5c5bad40e81dbd11aae2147c32"
EXPECTED_PROFILES_SHA256 = "d07ccf07dddcccd285bddb9cd77d475deb5c8773142a4edaa466c6e9d184860d"
EXPECTED_SUMMARY_SHA256 = "776a90a8f8de2946f0ca25feb68f010e44009e72c10468efb6684f67f4191524"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_path(path):
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def validate_frozen_tables(initial_path, profiles_path, summary_path):
    expected = {
        "initial_selected_fields": (initial_path, EXPECTED_INITIAL_SHA256),
        "analyzer_selected_profiles": (profiles_path, EXPECTED_PROFILES_SHA256),
        "analyzer_summary": (summary_path, EXPECTED_SUMMARY_SHA256),
    }
    for label, (path, expected_hash) in expected.items():
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"{label} SHA-256 differs from frozen plot input: {actual_hash}")


def load_initial_profiles(path):
    weighted = defaultdict(float)
    weights = defaultdict(float)
    corners = defaultdict(set)
    for row in read_csv(path):
        arm, role, corner = row["arm"], row["point_id"], row["corner"]
        k = int(row["level_k0"]) + 1
        weight = float(row["weight"])
        value = float(row["QRAIN"])
        key = (arm, role, k)
        weighted[key] += weight * value
        weights[key] += weight
        corners[key].add(corner)
    expected = {(arm, role, k) for arm in ARMS for role in ROLES for k in range(1, 40)}
    if set(weighted) != expected:
        raise ValueError("initial input table does not contain all arm/role/native-k profiles")
    for key in expected:
        if corners[key] != set(CORNERS) or not math.isclose(weights[key], 1.0, abs_tol=1e-12):
            raise ValueError(f"initial four-corner weights are incomplete or do not sum to one: {key}")
    return {key: weighted[key] for key in expected}


def load_capture_profiles(path, summary, capture_script, selection_path):
    if summary.get("status") != "PASS_SCOPED_CAPTURE_COMPLETE":
        raise ValueError("analyzer summary is not a complete scoped capture pass")
    summary_inputs = summary.get("inputs", {})
    if summary_inputs.get("capture_script_sha256") != sha256(capture_script):
        raise ValueError("analyzer summary does not bind the current frozen GDB helper")
    if summary_inputs.get("selection_sha256") != sha256(selection_path):
        raise ValueError("analyzer summary does not bind the selected corner mapping")
    if {row.get("arm") for row in summary.get("arms", [])} != set(ARMS):
        raise ValueError("analyzer summary does not contain all three control arms")
    profiles = defaultdict(dict)
    seen_corners = defaultdict(set)
    rows = read_csv(path)
    expected_rows = len(ARMS) * 2 * 2 * len(ROLES) * len(CORNERS) * 39
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} validated endpoint rows, got {len(rows)}")
    for row in rows:
        arm = row["arm"]
        call = int(row["call_ordinal"])
        endpoint = row["endpoint"]
        role, corner = row["label"].split("_", 1)
        k = int(row["k"])
        if (arm not in ARMS or role not in ROLES or corner not in CORNERS or
                call not in (1, 2) or k not in range(1, 40)):
            raise ValueError("validated profile CSV has an unexpected arm/role/corner/call key")
        if endpoint not in ("entry", "return") or row["qr_finite"] != "True":
            raise ValueError(f"qr value is not a finite entry/return sample: {row}")
        if not math.isfinite(float(row["qr"])):
            raise ValueError(f"qr value is nonfinite: {row}")
        key = (arm, call, endpoint, role, corner, k)
        if key in profiles:
            raise ValueError(f"duplicate analyzer profile row: {key}")
        profiles[key] = float(row["qr"])
        seen_corners[(arm, call, endpoint, role, k)].add(corner)
    for arm in ARMS:
        for call in (1, 2):
            for endpoint in ("entry", "return"):
                for role in ROLES:
                    for k in range(1, 40):
                        key = (arm, call, endpoint, role, k)
                        if seen_corners[key] != set(CORNERS):
                            raise ValueError(f"capture lacks the four selected corners: {key}")
    return rows, profiles


def weighted_capture_profiles(profiles, initial_rows):
    weights = {}
    for row in initial_rows:
        key = (row["arm"], row["point_id"], row["corner"], int(row["level_k0"]) + 1)
        weight = float(row["weight"])
        if key in weights and not math.isclose(weights[key], weight, abs_tol=1e-15):
            raise ValueError(f"corner weight changed across levels: {key}")
        weights[key] = weight
    result = defaultdict(dict)
    for arm in ARMS:
        for call in (1, 2):
            for endpoint in ("entry", "return"):
                for role in ROLES:
                    for k in range(1, 40):
                        key = (arm, call, endpoint, role, k)
                        total_weight = sum(weights[(arm, role, corner, k)] for corner in CORNERS)
                        if not math.isclose(total_weight, 1.0, abs_tol=1e-12):
                            raise ValueError(f"capture corner weights do not sum to one: {key}")
                        result[(arm, role)][(call, endpoint, k)] = sum(
                            weights[(arm, role, corner, k)] * profiles[(arm, call, endpoint, role, corner, k)]
                            for corner in CORNERS
                        )
    return result


def plot_profiles(initial, captured, output):
    fig, axes = plt.subplots(len(ROLES), len(ARMS), figsize=(15, 13), sharex=True, sharey="row")
    colors = {"initial": "#30343b", 1: "#2369a8", 2: "#db7b19"}
    styles = {
        "initial": ("--", "Initial wrfinput_d01"),
        (1, "entry"): ("-", "Call 1 entry (PRE)"),
        (1, "return"): (":", "Call 1 return (POST)"),
        (2, "entry"): ("-", "Call 2 entry (PRE)"),
        (2, "return"): (":", "Call 2 return (POST)"),
    }
    native_k = list(range(1, 40))
    for row_index, role in enumerate(ROLES):
        for column_index, arm in enumerate(ARMS):
            axis = axes[row_index][column_index]
            axis.plot(native_k, [initial[(arm, role, k)] for k in native_k],
                      color=colors["initial"], linestyle=styles["initial"][0], linewidth=1.8,
                      label=styles["initial"][1])
            for call in (1, 2):
                for endpoint in ("entry", "return"):
                    linestyle, label = styles[(call, endpoint)]
                    axis.plot(native_k,
                              [captured[(arm, role)][(call, endpoint, k)] for k in native_k],
                              color=colors[call], linestyle=linestyle, linewidth=1.45,
                              label=label)
            axis.set_title(f"{arm} · {role}")
            axis.grid(True, alpha=0.25)
            if column_index == 0:
                axis.set_ylabel("Four-corner weighted qr\n(captured field values)")
            if row_index == len(ROLES) - 1:
                axis.set_xlabel("Native WRF k index")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False, fontsize=9)
    fig.suptitle("CP02 KDM6 selected qr profiles at two call boundaries", fontsize=14)
    fig.text(0.5, 0.025,
             "Each role is the same four mapped horizontal corners and weights at native k=1–39. "
             "PRE/POST denote KDM6 entry/return samples. Input QRAIN metadata gives kg/kg; "
             "runtime candidate qr units are not independently proven. No mass integration is implied.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0.02, 0.07, 1, 0.96))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def atomic_json(path, record):
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(record, target, indent=2, sort_keys=True, allow_nan=False)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=EVIDENCE / "analysis")
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    evidence = args.evidence_dir
    analysis = args.analysis_dir
    summary_path = analysis / "summary.json"
    profiles_path = analysis / "selected_profiles.csv"
    initial_path = evidence / "inputs/selected_initial_fields.csv"
    capture_script_path = evidence / "capture_kdm6.gdb"
    selection_path = evidence / "selection.json"
    validate_frozen_tables(initial_path, profiles_path, summary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    initial_rows = read_csv(initial_path)
    initial = load_initial_profiles(initial_path)
    capture_rows, raw_profiles = load_capture_profiles(
        profiles_path, summary, capture_script_path, selection_path
    )
    captured = weighted_capture_profiles(raw_profiles, initial_rows)
    plot_path = evidence / "kdm6_qr_weighted_profiles.png"
    plot_profiles(initial, captured, plot_path)

    input_paths = {
        "analyzer": ROOT / "tools/cp02_kdm6_controls.py",
        "analyzer_summary": summary_path,
        "analyzer_selected_profiles": profiles_path,
        "initial_selected_fields": initial_path,
        "selection": selection_path,
        "capture_script": capture_script_path,
        "input_extractor": evidence / "inputs/extract_inputs.py",
        "copy_manifest": evidence / "inputs/copy_manifest.json",
        "provenance": evidence / "inputs/provenance.json",
        "source_verification": evidence / "inputs/source_verification.json",
    }
    for arm in ARMS:
        input_paths[f"{arm.lower()}_runtime_receipt"] = evidence / f"captures/{arm}/receipt.json"
    capture_paths = sorted((evidence / "captures").glob("*/capture_rank*_pid*.json.gz"))
    for path in capture_paths:
        input_paths[f"capture:{path.relative_to(evidence).as_posix()}"] = path
    metadata = {
        "schema": "cp02-kdm6-weighted-qr-plot-v1",
        "status": "PASS_PLOT_FROM_VALIDATED_CAPTURE_PROFILES",
        "plot": {"path": plot_path.relative_to(evidence).as_posix(), "sha256": sha256(plot_path)},
        "inputs": {key: {"path": display_path(path), "sha256": sha256(path)}
                   for key, path in sorted(input_paths.items())},
        "selection": {"roles": list(ROLES), "corners": list(CORNERS),
                      "native_k": [1, 39], "selected_keys_per_arm_call_endpoint": 624,
                      "selected_endpoint_rows": len(capture_rows)},
        "method": {
            "field": "qr",
            "initial": "four-corner weighted retained wrfinput_d01 values",
            "capture": "four-corner weighted REAL32 values from analyzer-validated KDM6 entry/return records",
            "arms": list(ARMS), "calls": [1, 2], "endpoints": ["entry", "return"],
            "weighting": "sum of four native WRF corner values times their recorded bilinear weights at each native k",
            "vertical_axis": "native WRF k index; no mass-coordinate conversion",
            "input_source_units": "kg kg-1 (input QRAIN NetCDF metadata)",
            "runtime_candidate_units": "not independently established",
            "scope": "selected profiles only; no column mass integration, conservation, or causal attribution",
        },
    }
    metadata_path = evidence / "kdm6_qr_weighted_profiles.metadata.json"
    atomic_json(metadata_path, metadata)
    print(json.dumps({"plot": str(plot_path), "metadata": str(metadata_path),
                      "profiles": len(captured), "analyzer_rows": len(capture_rows)}, indent=2))


if __name__ == "__main__":
    main()
