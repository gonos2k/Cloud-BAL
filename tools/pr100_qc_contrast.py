#!/usr/bin/env python3
"""Project source-ordered QC increments onto fixed-support arm contrasts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from pr100_qc_process_reducer import parse_event, reduce_events
from native_kdm6_trace import read_dump

ROOT = Path(__file__).resolve().parents[1]
HYDROMETEOR_REDUCER = ROOT / "docs/evidence/pr99_hydrometeor_response_20261022/reduce.py"


def _initial_loader():
    spec = importlib.util.spec_from_file_location("pr99_hydrometeor_response", HYDROMETEOR_REDUCER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the already-reviewed hydrometeor T0 reader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_initial_fields


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _events(path: Path, points: list[tuple[int, int, int]]) -> dict:
    index = {point: n for n, point in enumerate(points)}
    vectors: dict[str, list[list[float]]] = defaultdict(lambda: [[] for _ in points])
    cold = {name: [0.0, 0.0, 0.0] for name in ("NG", "AUT", "G")}
    warm = {"WARM": [0.0, 0.0, 0.0]}
    stored = defaultdict(float)
    with path.open(encoding="ascii") as stream:
        if stream.readline().strip() != "PR100_QC_V1 613 fixed_source_support":
            raise ValueError("event header does not declare fixed 613-cell support")
        for line in stream:
            event = parse_event(line)
            if event["label"] in ("ENTRY", "EXIT"):
                continue
            cell = (event["i"], event["j"], event["k"])
            if cell not in index:
                raise ValueError(f"event outside support: {cell}")
            category = event["label"]
            if category == "CONDENSATION":
                category = ("CONDENSATION_QC_POSITIVE" if event["delta"] > 0.0 else
                            "CONDENSATION_QC_NEGATIVE" if event["delta"] < 0.0 else
                            "CONDENSATION_QC_ZERO")
            vectors[category][index[cell]].append(event["delta"])
            stored[category] += event["delta"]
            if event["label"] == "COLD_COMMIT":
                for n, name in enumerate(("NG", "AUT", "G")):
                    cold[name][0] += event["proposal"][n]
                    cold[name][1] += event["approved"][n]
                    cold[name][2] += event["deferred"][n]
            elif event["label"] == "WARM_COMMIT":
                warm["WARM"][0] += event["proposal"][3]
                warm["WARM"][1] += event["approved"][3]
                warm["WARM"][2] += event["deferred"][3]
    dense = {label: np.array([math.fsum(cell) for cell in values], dtype=np.float64)
             for label, values in vectors.items()}
    return dense, dict(stored), {"cold": cold, "warm": warm}


def _qc(path: Path, points: list[tuple[int, int, int]]) -> np.ndarray:
    dump = read_dump(path)
    b = dump["bounds"]
    return np.array([float(dump["fields"]["QC"][j-b["jts"], k-b["kts"], i-b["its"]])
                     for i, j, k in points], dtype=np.float64)


def analyze(arms: dict[str, dict], mask_path: Path, initial_c1_path: Path,
            initial_off_path: Path) -> dict:
    points = [tuple(map(int, row.split())) for row in mask_path.read_text().splitlines()]
    if len(points) != 613 or len(set(points)) != 613:
        raise ValueError("expected 613 unique fixed support cells")
    load_initial_fields = _initial_loader()
    initial_c1, initial_c1_identity = load_initial_fields(initial_c1_path)
    initial_off, initial_off_identity = load_initial_fields(initial_off_path)
    t0_contrast = np.array([
        initial_c1["QC"][k-1, j-2, i-2] - initial_off["QC"][k-1, j-2, i-2]
        for i, j, k in points], dtype=np.float64)
    t0_denominator = math.fsum(float(x*x) for x in t0_contrast)
    loaded = {}
    for name, paths in arms.items():
        pre, post = paths["pre"], paths["post"]
        reduce_events(paths["events"], mask_path, pre, post)
        loaded[name] = {
            "pre": _qc(pre, points), "post": _qc(post, points),
            "labels": _events(paths["events"], points),
            "pins": {field: _sha(path) for field, path in paths.items()},
        }
    if "OFF" not in loaded:
        raise ValueError("OFF is required as the shared reference arm")
    results = {}
    for arm in (name for name in loaded if name != "OFF"):
        ref, current = loaded["OFF"], loaded[arm]
        initial = current["pre"] - ref["pre"]
        final = current["post"] - ref["post"]
        observed = final - initial
        pre_denominator = math.fsum(float(x*x) for x in initial)
        labels = sorted(set(ref["labels"][0]) | set(current["labels"][0]))
        attribution = {}
        reconstructed = np.zeros(len(points), dtype=np.float64)
        for label in labels:
            dv = current["labels"][0].get(label, np.zeros(len(points))) - \
                 ref["labels"][0].get(label, np.zeros(len(points)))
            reconstructed += dv
            attribution[label] = {
                "projection_on_T0_C1_COUPLED_minus_OFF": (
                    math.fsum(float(a*b) for a, b in zip(t0_contrast, dv, strict=True)) / t0_denominator
                    if t0_denominator else None),
                "projection_on_call_PRE_arm_minus_OFF": (
                    math.fsum(float(a*b) for a, b in zip(initial, dv, strict=True)) / pre_denominator
                    if pre_denominator else None),
                "delta_vector_l2": math.sqrt(math.fsum(float(x*x) for x in dv)),
                "delta_vector_signed_sum": math.fsum(float(x) for x in dv),
                "max_abs_cell_delta": float(np.max(np.abs(dv))),
                "arm_stored_increment_sum": current["labels"][1].get(label, 0.0),
                "OFF_stored_increment_sum": ref["labels"][1].get(label, 0.0),
                "source_record_label": ("CONDENSATION" if label.startswith("CONDENSATION_QC_") else label),
                "stored_qc_delta_interpretation": (
                    "positive QC store delta in the condensation source branch" if label == "CONDENSATION_QC_POSITIVE" else
                    "negative QC store delta in the condensation source branch (partial evaporation)" if label == "CONDENSATION_QC_NEGATIVE" else
                    "zero QC store delta in the condensation source branch; E/request is not captured" if label == "CONDENSATION_QC_ZERO" else
                    "source label identifies the write site; packet fields are N/A unless a commit block captures them"),
            }
        error = reconstructed - observed
        if float(np.max(np.abs(error))) > 2e-12:
            raise ValueError(f"source-event contrast does not reconstruct {arm}-OFF")
        g = current["labels"][2]
        results[f"{arm}-OFF"] = {
            "T0_C1_COUPLED_minus_OFF_l2": math.sqrt(t0_denominator),
            "call_PRE_arm_minus_OFF_l2": math.sqrt(pre_denominator),
            "post_contrast_l2": math.sqrt(math.fsum(float(x*x) for x in final)),
            "contrast_change_l2": math.sqrt(math.fsum(float(x*x) for x in observed)),
            "contrast_change_projection_on_T0_C1_COUPLED_minus_OFF": (
                math.fsum(float(a*b) for a, b in zip(t0_contrast, observed, strict=True)) / t0_denominator
                if t0_denominator else None),
            "contrast_change_projection_on_call_PRE_arm_minus_OFF": (
                math.fsum(float(a*b) for a, b in zip(initial, observed, strict=True)) / pre_denominator
                if pre_denominator else None),
            "event_reconstruction_max_abs_error": float(np.max(np.abs(error))),
            "label_contributions": attribution,
            "cold_commit_signed_proposed_approved_deferred": g["cold"],
            "warm_commit_signed_proposed_approved_deferred": g["warm"],
            "interpretation": "source-record attribution on fixed support; not causal, not a total-water account",
        }
    return {
        "schema": "pr100_qc_contrast_v1", "mask_sha256": _sha(mask_path),
        "T0_C1_COUPLED_input": {"path": str(initial_c1_path), "sha256": _sha(initial_c1_path),
                                 "QCLOUD_identity": initial_c1_identity["QC"]},
        "T0_OFF_input": {"path": str(initial_off_path), "sha256": _sha(initial_off_path),
                         "QCLOUD_identity": initial_off_identity["QC"]},
        "T0_reader_source_sha256": _sha(HYDROMETEOR_REDUCER),
        "T0_pattern_metric_note": "primary projections use fixed source-composed support T0 C1_COUPLED−OFF; call PRE projection is reported separately because arms already differ at entry",
        "ordinary_write_packet_columns": "proposal/alpha/approved/deferred are zero-filled N/A sentinels for ordinary direct writes, not measured zero rates; only cold/warm commit blocks capture those packet terms",
        "arm_input_sha256": {name: data["pins"] for name, data in loaded.items()},
        "contrasts": results,
        "fixed_support_cells": len(points),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--initial-c1-input", type=Path, required=True)
    parser.add_argument("--initial-off-input", type=Path, required=True)
    parser.add_argument("--arm", action="append", required=True,
                        help="NAME,EVENTS,PRE,POST")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arms = {}
    for item in args.arm:
        name, event, pre, post = item.split(",", 3)
        if name in arms:
            raise ValueError(f"duplicate arm {name}")
        arms[name] = {"events": Path(event), "pre": Path(pre), "post": Path(post)}
    output = analyze(arms, args.mask, args.initial_c1_input, args.initial_off_input)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
