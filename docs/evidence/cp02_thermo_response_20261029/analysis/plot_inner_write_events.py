#!/usr/bin/env python3
"""Plot accepted selected inner-call buffer writes against local event ordinal."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import struct
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs/evidence/cp02_thermo_response_20261029"
CAPTURES = EVIDENCE / "captures"
COMPARISON_JSON = EVIDENCE / "binary/arm_qrs_branch_comparison.json"
COMPARISON_CSV = EVIDENCE / "binary/arm_qrs_branch_comparison.csv"
SELECTION = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/selection.json"
DEFAULT_OUTPUT = EVIDENCE / "analysis/inner_write_events"

ARMS = ("OFF", "HYDRO", "LIQUID")
TARGETS = ("P05_00", "P01_00")
FIELDS = ("qrs", "qci", "q", "t")
FIELD_TITLES = {"qrs": "candidate qrs buffer", "qci": "candidate qci buffer",
                "q": "candidate q buffer", "t": "candidate t buffer"}
ARM_COLORS = {"OFF": "#3366a6", "HYDRO": "#d05a35", "LIQUID": "#25855a"}

EXPECTED = {
    "comparison_json_sha256": "041a0617d32bb5496ea13e157abe36897eaa91e7b398d12dc34fc4d66bda0f2c",
    "comparison_csv_sha256": "943006253c811b441b568ef52c19466cc5000b361a3868a2f2c6d3e60539bcca",
    "comparison_script_sha256": "ccf3438973645f63fe48bfdaa3a4ccc142db360b7889e683aaa753f8b2bf3f21",
    "selection_sha256": "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e",
    "binary_sha256": "de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168",
    "helper_sha256": "e6b9f5395a847fb3c475e9dd9d5b648cce0b224c5bd76562278df3e23f91c38b",
    "receipt_sha256": {
        "OFF": "2ffac722f061478385edf436be9a3180c34f6bc81d0138db0342e759d970528b",
        "HYDRO": "055d9bcaef006b496cfb737207a4dd21cb524185b2af47b3979f7707f1ffa39d",
        "LIQUID": "9c1cb2b693651a20f16615516ab196ea824684de07ef580e363775892ca06223",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source)


def f32_from_hex(raw_hex, label):
    require(type(raw_hex) is str and len(raw_hex) == 8 and
            all(char in "0123456789abcdef" for char in raw_hex),
            f"{label}: malformed REAL*4 bytes")
    value = struct.unpack("<f", bytes.fromhex(raw_hex))[0]
    require(math.isfinite(value), f"{label}: non-finite REAL*4 value")
    return value


def check_pins():
    pins = ((COMPARISON_JSON, "comparison_json_sha256"),
            (COMPARISON_CSV, "comparison_csv_sha256"),
            (EVIDENCE / "binary/compare_write_events.py", "comparison_script_sha256"),
            (SELECTION, "selection_sha256"))
    hashes = {}
    for path, key in pins:
        observed = sha256(path)
        require(observed == EXPECTED[key], f"frozen {key} mismatch: {path}")
        hashes[key] = observed
    return hashes


def load_comparison_rows():
    comparison = read_json(COMPARISON_JSON)
    require(comparison.get("status") == "REPRODUCED_ACCEPTED_SELECTED_WRITE_EVENTS",
            "write comparison JSON is not the accepted scoped result")
    require(comparison.get("binary_sha256") == EXPECTED["binary_sha256"] and
            comparison.get("helper_sha256") == EXPECTED["helper_sha256"] and
            comparison.get("selection_sha256") == EXPECTED["selection_sha256"] and
            comparison.get("event_csv_sha256") == EXPECTED["comparison_csv_sha256"],
            "write comparison provenance does not match frozen inputs")
    with COMPARISON_CSV.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    json_events = [event for summary in comparison.get("summaries", [])
                   for event in summary.get("all_events", [])]
    require(len(csv_rows) == len(json_events) and csv_rows,
            "write comparison CSV/JSON row counts differ or are empty")
    for row, event in zip(csv_rows, json_events):
        for name in ("arm", "target", "rank", "ordinal", "field",
                     "raw_before_hex", "raw_after_hex"):
            require(str(row[name]) == str(event[name]),
                    f"write comparison CSV/JSON mismatch at {name}")
        require(row["pc_after_write"] == event["pc_after_write"],
                "write comparison CSV/JSON PC mismatch")
        f32_from_hex(row["raw_before_hex"], "comparison CSV before")
        f32_from_hex(row["raw_after_hex"], "comparison CSV after")
    require(len(comparison.get("capture_inputs", [])) == 6,
            "comparison JSON must bind exactly six selected raw captures")
    inputs = {(item["arm"], item["target"]): item
              for item in comparison["capture_inputs"]}
    require(set(inputs) == {(arm, target) for arm in ARMS for target in TARGETS},
            "comparison capture list does not cover all six arm/target pairs")
    return comparison, csv_rows, inputs


def load_capture(arm, target, input_record, csv_rows):
    receipt_path = CAPTURES / arm / "receipt.json"
    require(sha256(receipt_path) == EXPECTED["receipt_sha256"][arm],
            f"{arm}: accepted capture receipt hash mismatch")
    receipt = read_json(receipt_path)
    require(receipt.get("status") == "FIRST_INNER_CAPTURED_INTENTIONAL_STOP" and
            receipt.get("forecast_status") == "NOT_COMPLETED" and
            receipt.get("arm") == arm and receipt.get("ranks") == 8 and
            receipt.get("selection_sha256") == EXPECTED["selection_sha256"] and
            receipt.get("binary", {}).get("sha256") == EXPECTED["binary_sha256"] and
            receipt.get("helper_sha256") == EXPECTED["helper_sha256"],
            f"{arm}: accepted capture receipt fields are inconsistent")
    require(input_record.get("status") == "all_ranks_settled" and
            input_record.get("target") == target and
            str(input_record.get("rank")) in {"1", "3"},
            f"{arm}/{target}: comparison capture selection is malformed")
    rank = int(input_record["rank"])
    # Comparison JSON binds the selected capture bytes; the accepted receipt has
    # the same digest and size record for the local capture path.
    capture_rows = [row for row in receipt.get("captures", [])
                    if row.get("sha256") == input_record["sha256"]]
    require(len(capture_rows) == 1, f"{arm}/{target}: selected raw capture is absent from receipt")
    capture_record = capture_rows[0]
    capture_path = CAPTURES / arm / Path(capture_record["path"]).name
    require(capture_path.is_file() and capture_path.stat().st_size == capture_record["size_bytes"] and
            sha256(capture_path) == input_record["sha256"] == capture_record["sha256"],
            f"{arm}/{target}: selected raw capture hash/size mismatch")
    compressed = capture_path.read_bytes()
    raw_bytes = gzip.decompress(compressed)
    require(hashlib.sha256(raw_bytes).hexdigest() == capture_record["uncompressed_sha256"] and
            len(raw_bytes) == capture_record["uncompressed_size_bytes"],
            f"{arm}/{target}: selected raw capture uncompressed hash/size mismatch")
    capture = json.loads(raw_bytes)
    require(capture.get("arm") == arm and str(capture.get("rank")) == str(rank) and
            capture.get("status") == "all_ranks_settled" and
            capture.get("binary_sha256") == EXPECTED["binary_sha256"] and
            capture.get("selection_sha256") == EXPECTED["selection_sha256"] and
            capture.get("settled_rank_count") == 8,
            f"{arm}/{target}: selected capture identity/scope mismatch")

    matching_inner = [event for event in capture.get("inner", [])
                      if event.get("watch_target") == target and
                      any(point.get("label") == target for point in event.get("points", []))]
    require(len(matching_inner) == 1, f"{arm}/{target}: expected one watched inner-call record")
    inner = matching_inner[0]
    entry_points = {point["label"]: point for point in inner.get("points", [])}
    return_points = {point["label"]: point for point in inner.get("return", {}).get("points", [])}
    require(target in entry_points and target in return_points,
            f"{arm}/{target}: inner entry/return point is missing")
    entry = entry_points[target]["entry"]
    final = return_points[target]["values"]
    values = {}
    target_events = [event for event in capture.get("write_events", [])
                     if event.get("target") == target]
    require(target_events, f"{arm}/{target}: no selected write events")
    target_events.sort(key=lambda event: event["ordinal"])
    comparison_target = [row for row in csv_rows if row["arm"] == arm and row["target"] == target]
    raw_fields = [(event["ordinal"], event["field"], event["pc_after_write_hex"],
                   event["raw_before_hex"], event["raw_after_hex"]) for event in target_events]
    csv_fields = [(int(row["ordinal"]), row["field"], row["pc_after_write"],
                   row["raw_before_hex"], row["raw_after_hex"]) for row in comparison_target]
    require(raw_fields == csv_fields,
            f"{arm}/{target}: raw write events disagree with pinned comparison CSV")

    for field in FIELDS:
        require(field in entry and field in final,
                f"{arm}/{target}: missing {field} entry/return value")
        current_hex = entry[field]["raw_hex"]
        f32_from_hex(current_hex, f"{arm}/{target}/{field} entry")
        series = [{"ordinal": 0, "kind": "inner_entry", "raw_hex": current_hex,
                   "value": f32_from_hex(current_hex, f"{arm}/{target}/{field} entry")}]
        field_events = [event for event in target_events if event["field"] == field]
        require(field_events, f"{arm}/{target}: no {field} writes in selected inner call")
        for event in field_events:
            require(event["raw_before_hex"] == current_hex,
                    f"{arm}/{target}/{field}: write-before bytes do not continue the captured state")
            f32_from_hex(event["raw_before_hex"], f"{arm}/{target}/{field} before write")
            after = f32_from_hex(event["raw_after_hex"], f"{arm}/{target}/{field} after write")
            require(event["ordinal"] > series[-1]["ordinal"],
                    f"{arm}/{target}/{field}: write ordinals are not increasing")
            if event["raw_before_hex"] != event["raw_after_hex"]:
                series.append({"ordinal": int(event["ordinal"]), "kind": "changing_write",
                               "raw_hex": event["raw_after_hex"], "value": after,
                               "pc_after_write": event["pc_after_write_hex"]})
            current_hex = event["raw_after_hex"]
        return_hex = final[field]["raw_hex"]
        require(current_hex == return_hex,
                f"{arm}/{target}/{field}: last selected write differs from inner-return bytes")
        last_ordinal = max(event["ordinal"] for event in target_events)
        series.append({"ordinal": int(last_ordinal) + 1, "kind": "inner_return",
                       "raw_hex": return_hex,
                       "value": f32_from_hex(return_hex, f"{arm}/{target}/{field} return")})
        values[field] = series
    return {"arm": arm, "target": target, "rank": rank,
            "capture_path": str(capture_path.relative_to(ROOT)),
            "capture_sha256": sha256(capture_path),
            "values": values}


def make_figures(records, output_dir):
    created = []
    for field in FIELDS:
        fig, axes = plt.subplots(2, 3, figsize=(15, 8.5), sharex=False,
                                 sharey="row", constrained_layout=False)
        fig.subplots_adjust(left=0.115, right=0.985, bottom=0.09, top=0.87,
                            wspace=0.10, hspace=0.27)
        for row_index, target in enumerate(TARGETS):
            for col_index, arm in enumerate(ARMS):
                ax = axes[row_index][col_index]
                series = records[(arm, target)]["values"][field]
                xs = [item["ordinal"] for item in series]
                ys = [item["value"] for item in series]
                ax.step(xs, ys, where="post", color=ARM_COLORS[arm], linewidth=1.8, alpha=0.9)
                entry = series[0]
                changes = [item for item in series if item["kind"] == "changing_write"]
                returned = series[-1]
                ax.scatter([entry["ordinal"]], [entry["value"]], s=55, color="#263238",
                           marker="o", zorder=3, label="inner entry")
                if changes:
                    ax.scatter([item["ordinal"] for item in changes],
                               [item["value"] for item in changes], s=38,
                               color=ARM_COLORS[arm], edgecolor="white", linewidth=0.6,
                               marker="D", zorder=3, label="value-changing write")
                ax.scatter([returned["ordinal"]], [returned["value"]], s=62,
                           color="#c33d3d", marker="s", zorder=4, label="inner return")
                ax.set_title(f"{target} · {arm} · rank {records[(arm, target)]['rank']}")
                ax.set_xlabel("local write-event ordinal (per capture)")
                ax.set_ylabel("captured numeric value (unit unassigned)" if col_index == 0 else "")
                ax.grid(True, alpha=0.22)
                max_ordinal = int(returned["ordinal"])
                ax.set_xlim(-0.5, max_ordinal + 0.5)
                ax.set_xticks(range(0, max_ordinal + 1, max(1, math.ceil(max_ordinal / 10))))
                if row_index == 0 and col_index == 0:
                    ax.legend(fontsize=8, loc="best")
        if field in ("qrs", "qci"):
            for row_index in range(len(TARGETS)):
                axes[row_index][0].set_ylim(bottom=0.0)
        fig.suptitle(f"{FIELD_TITLES[field]} · selected inner-call write sequence\n"
                     "Ordinals are local to each capture; panels are not time-aligned",
                     fontsize=15, y=0.975)
        destination = Path(output_dir) / f"{field}_inner_write_events.png"
        descriptor, temporary = tempfile.mkstemp(prefix=f".{field}.", suffix=".png", dir=output_dir)
        os.close(descriptor)
        try:
            fig.savefig(temporary, dpi=190, bbox_inches="tight", pad_inches=0.12)
            os.replace(temporary, destination)
        finally:
            plt.close(fig)
            Path(temporary).unlink(missing_ok=True)
        created.append(destination)
    return created


def generate(output_dir=DEFAULT_OUTPUT):
    output_dir = Path(output_dir)
    require(not output_dir.exists() and not output_dir.is_symlink(),
            f"output path already exists: {output_dir}")
    pins = check_pins()
    comparison, csv_rows, capture_inputs = load_comparison_rows()
    selection = read_json(SELECTION)
    selected_coords = {(point["label"], point["k"]): (point["i"], point["j"])
                       for point in selection["points"]}
    for label, coords in (("P05_00", (163, 70)), ("P01_00", (163, 73))):
        require(selected_coords.get((label, 8)) == coords,
                f"frozen selection coordinates differ for {label} at k=8")

    records = {}
    for arm in ARMS:
        for target in TARGETS:
            records[(arm, target)] = load_capture(arm, target, capture_inputs[(arm, target)], csv_rows)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + output_dir.name + ".", dir=output_dir.parent))
    try:
        figures = make_figures(records, staging)
        source_records = [records[(arm, target)] for arm in ARMS for target in TARGETS]
        metadata = {
            "schema": "cp02-inner-write-event-figures-v1",
            "status": "PASS_VERIFIED_SELECTED_CAPTURE_WRITES",
            "scope": "Captured entry, value-changing selected buffer writes, and inner return for qrs/qci/q/t at P05_00 and P01_00 across the three accepted arms.",
            "interpretation_limits": [
                "Field names are candidate buffer labels; numeric units are unassigned.",
                "No source-level physical process or causal interpretation is asserted.",
                "The x-axis is each capture's local write-event ordinal. Arm panels are not synchronized in time.",
            ],
            "inputs": {**pins,
                       "plot_script_sha256": sha256(Path(__file__).resolve()),
                       "comparison_script_sha256": EXPECTED["comparison_script_sha256"],
                       "capture_receipt_sha256": EXPECTED["receipt_sha256"],
                       "binary_sha256": comparison["binary_sha256"],
                       "helper_sha256": comparison["helper_sha256"]},
            "capture_records": source_records,
            "event_point_counts": {
                f"{arm}/{target}/{field}": sum(item["kind"] == "changing_write"
                                                   for item in records[(arm, target)]["values"][field])
                for arm in ARMS for target in TARGETS for field in FIELDS
            },
            "figures": [{"path": path.name, "sha256": sha256(path)} for path in figures],
        }
        (staging / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                                                  encoding="utf-8")
        os.rename(staging, output_dir)
        staging = None
    finally:
        if staging is not None:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        metadata = generate(args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": metadata["status"], "output_dir": str(args.output_dir),
                      "figures": [item["path"] for item in metadata["figures"]]}, sort_keys=True))


if __name__ == "__main__":
    main()
