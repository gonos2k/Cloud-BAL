#!/usr/bin/env python3
"""Independently decode and compare raw REAL32 CP02 KDM6 captures.

This standard-library-only review reads gzip capture records, decodes four-byte
values from raw_hex, and writes independent_capture_review.json beside itself.
It does not call the production analyzer or infer process eligibility.
"""

import csv
import gzip
import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
PR125 = ROOT / "docs/evidence/cp02_wrf_first_call_20261029/capture"
ARMS = ("OFF", "HYDRO", "LIQUID")
PAIR_FIELDS = {
    "qc_nc": ("qc", "nc", "QCLOUD", "QNCLOUD"),
    "qr_nr": ("qr", "nr", "QRAIN", "QNRAIN"),
    "qi_ni": ("qi", "ni", "QICE", "QNICE"),
}
CORE_3D = (
    "th", "q", "qc", "qr", "qi", "qs", "qg", "nn", "nc", "ni", "nr",
    "bg", "diag_rhog", "den", "pii", "p", "delz",
)
PRECIP_2D = ("xland", "rain", "rainncv", "snow", "snowncv", "sr", "graupel", "graupelncv")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_capture(path):
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    return json.loads(raw), hashlib.sha256(compressed).hexdigest(), hashlib.sha256(raw).hexdigest()


def decode_f32(record):
    raw = bytes.fromhex(record["raw_hex"])
    if len(raw) != 4:
        raise ValueError("expected a four-byte REAL32 raw_hex value")
    return struct.unpack("<f", raw)[0]


def sample_map(samples):
    result = {}
    for sample in samples:
        if sample["status"] != "owned_tile":
            continue
        key = (sample["label"], sample["i"], sample["j"], sample["k"])
        if key in result:
            raise ValueError("duplicate owned sample: " + repr(key))
        result[key] = sample["values"]
    return result


def load_arm(arm):
    folder = EVIDENCE / "captures" / arm
    receipt_path = folder / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt["status"] != "TWO_CALLS_CAPTURED_INTENTIONAL_STOP":
        raise ValueError(f"{arm}: unexpected receipt status {receipt['status']}")
    expected_files = {str((ROOT / row["path"]).resolve()): row for row in receipt["captures"] if Path(row["path"]).name.startswith("capture_rank") and row["path"].endswith(".json.gz")}
    actual_paths = sorted(folder.glob("capture_rank*.json.gz"))
    if set(map(str, actual_paths)) != set(expected_files):
        raise ValueError(f"{arm}: capture file set differs from receipt")
    all_samples = {}
    file_hashes = []
    rank_rows = []
    for path in actual_paths:
        data, compressed_sha, raw_sha = read_capture(path)
        manifest_row = expected_files[str(path)]
        if (compressed_sha != manifest_row["sha256"] or raw_sha != manifest_row["uncompressed_sha256"]):
            raise ValueError(f"{arm}: receipt hash mismatch for {path}")
        if data.get("status") != "two_calls_returned" or len(data.get("calls", [])) != 2:
            raise ValueError(f"{arm}: incomplete rank record {path}")
        calls = data["calls"]
        if [call["entry"]["call_number"] for call in calls] != [1, 2]:
            raise ValueError(f"{arm}: unexpected call ordinals in {path}")
        if any(call["return"] is None or call["return"]["pc"] != call["entry"]["return_pc"] for call in calls):
            raise ValueError(f"{arm}: entry/return mismatch in {path}")
        rank = str(data["rank"])
        rank_rows.append({
            "rank": int(rank),
            "call_numbers": [call["entry"]["call_number"] for call in calls],
            "observed_itimestep": [call["entry"]["observed_itimestep"] for call in calls],
            "observed_dt": [call["entry"]["observed_dt"] for call in calls],
            "return_pc_matches_entry": [call["return"]["pc"] == call["entry"]["return_pc"] for call in calls],
        })
        file_hashes.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": compressed_sha,
            "uncompressed_sha256": raw_sha,
        })
        for call in calls:
            for endpoint in ("entry", "return"):
                values_by_key = sample_map(call[endpoint]["samples"])
                for key, values in values_by_key.items():
                    existing = all_samples.setdefault(key, {"owner_rank": rank, "calls": {}})
                    if existing["owner_rank"] != rank:
                        raise ValueError(f"{arm}: multiple owners for {key}")
                    existing["calls"].setdefault(call["entry"]["call_number"], {})[endpoint] = values
    if len(all_samples) != 624:
        raise ValueError(f"{arm}: expected 624 unique owned samples, found {len(all_samples)}")
    if len(rank_rows) != 8:
        raise ValueError(f"{arm}: expected 8 rank captures")
    return receipt, receipt_path, all_samples, file_hashes, sorted(rank_rows, key=lambda row: row["rank"])


def load_pr125():
    receipt_path = PR125 / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    expected_files = {str((ROOT / row["path"]).resolve()): row for row in receipt["captures"] if Path(row["path"]).name.startswith("capture_rank") and row["path"].endswith(".json.gz")}
    records = {}
    file_hashes = []
    paths = sorted(PR125.glob("capture_rank*.json.gz"))
    if set(map(str, paths)) != set(expected_files):
        raise ValueError("PR125 capture file set differs from receipt")
    for path in paths:
        data, compressed_sha, raw_sha = read_capture(path)
        row = expected_files[str(path)]
        if compressed_sha != row["sha256"] or raw_sha != row["uncompressed_sha256"]:
            raise ValueError(f"PR125 receipt hash mismatch for {path}")
        for endpoint in ("entry", "return"):
            for key, values in sample_map(data[endpoint]["samples"]).items():
                existing = records.setdefault(key, {"owner_rank": str(data["entry"]["rank"]), "entry": None, "return": None})
                if existing["owner_rank"] != str(data["entry"]["rank"]):
                    raise ValueError("PR125 has multiple owners for " + repr(key))
                existing[endpoint] = values
        file_hashes.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": compressed_sha,
            "uncompressed_sha256": raw_sha,
        })
    if len(records) != 624:
        raise ValueError(f"PR125 expected 624 unique owned samples, found {len(records)}")
    return receipt_path, receipt, records, file_hashes


def field_match(reference, candidate, field, dimensions):
    keys = sorted(reference.keys() & candidate.keys())
    if dimensions == 2:
        keys = sorted({key[:3] for key in keys})
        ref_values = {}
        cand_values = {}
        for key in keys:
            full = next(k for k in reference if k[:3] == key)
            ref_values[key] = reference[full][field]["raw_hex"]
            full2 = next(k for k in candidate if k[:3] == key)
            cand_values[key] = candidate[full2][field]["raw_hex"]
    else:
        ref_values = {key: reference[key][field]["raw_hex"] for key in keys}
        cand_values = {key: candidate[key][field]["raw_hex"] for key in keys}
    mismatches = [key for key in keys if ref_values[key] != cand_values[key]]
    return {
        "unique_point_samples": len(keys),
        "raw_bytes_equal": len(keys) - len(mismatches),
        "raw_bytes_mismatch": len(mismatches),
        "mismatch_examples": [list(key) for key in mismatches[:5]],
    }


def summarize_transition(start, end, mass_field, aux_field):
    keys = sorted(start.keys() & end.keys())
    rows = []
    for key in keys:
        mass0 = decode_f32(start[key][mass_field])
        mass1 = decode_f32(end[key][mass_field])
        aux0 = decode_f32(start[key][aux_field])
        aux1 = decode_f32(end[key][aux_field])
        rows.append((mass0, mass1, aux0, aux1,
                     start[key][mass_field]["raw_hex"] == end[key][mass_field]["raw_hex"],
                     start[key][aux_field]["raw_hex"] == end[key][aux_field]["raw_hex"]))

    def counts(index):
        values = [row[index] for row in rows]
        return {
            "n": len(values),
            "strictly_positive_gt_0": sum(value > 0 for value in values),
            "exact_zero": sum(value == 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "nonfinite": sum(not math.isfinite(value) for value in values),
        }

    mass_delta = [row[1] - row[0] for row in rows]
    aux_delta = [row[3] - row[2] for row in rows]
    return {
        "samples": len(rows),
        "mass_start": counts(0),
        "mass_end": counts(1),
        "aux_start": counts(2),
        "aux_end": counts(3),
        "mass_raw_changed": sum(not row[4] for row in rows),
        "aux_raw_changed": sum(not row[5] for row in rows),
        "mass_strict_increases": sum(delta > 0 for delta in mass_delta),
        "mass_strict_decreases": sum(delta < 0 for delta in mass_delta),
        "mass_numeric_unchanged": sum(delta == 0 for delta in mass_delta),
        "aux_strict_increases": sum(delta > 0 for delta in aux_delta),
        "aux_strict_decreases": sum(delta < 0 for delta in aux_delta),
        "aux_numeric_unchanged": sum(delta == 0 for delta in aux_delta),
        "unweighted_mass_delta_sum_mixing_ratio_units": sum(mass_delta),
        "unweighted_aux_delta_sum_native_units": sum(aux_delta),
        "mass_positive_and_aux_zero_start": sum(row[0] > 0 and row[2] == 0 for row in rows),
        "mass_positive_and_aux_zero_end": sum(row[1] > 0 and row[3] == 0 for row in rows),
    }


def load_initial_fields():
    path = EVIDENCE / "inputs/selected_initial_fields.csv"
    result = {}
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (
                row["arm"], f"{row['point_id']}_{row['corner']}",
                int(row["native_i0"]) + 1, int(row["native_j0"]) + 1,
                int(row["level_k0"]) + 1,
            )
            if key in result:
                raise ValueError("duplicate initial row " + repr(key))
            result[key] = row
    return path, result


def main():
    initial_path, initial = load_initial_fields()
    arm_data = {arm: load_arm(arm) for arm in ARMS}
    pr125_receipt_path, pr125_receipt, pr125, pr125_hashes = load_pr125()
    transitions = {}
    input_counts = {}
    for arm in ARMS:
        samples = arm_data[arm][2]
        initial_rows = {
            key[1:]: row for key, row in initial.items() if key[0] == arm
        }
        if len(initial_rows) != 624:
            raise ValueError(f"{arm}: expected 624 selected initial rows")
        transitions[arm] = {}
        input_counts[arm] = {}
        for pair, (mass_field, aux, mass_input, aux_input) in PAIR_FIELDS.items():
            endpoints = {
                "call1_entry_to_return": (
                    {key: value["calls"][1]["entry"] for key, value in samples.items()},
                    {key: value["calls"][1]["return"] for key, value in samples.items()},
                ),
                "call2_entry_to_return": (
                    {key: value["calls"][2]["entry"] for key, value in samples.items()},
                    {key: value["calls"][2]["return"] for key, value in samples.items()},
                ),
                "call1_return_to_call2_entry": (
                    {key: value["calls"][1]["return"] for key, value in samples.items()},
                    {key: value["calls"][2]["entry"] for key, value in samples.items()},
                ),
            }
            start = {}
            for key, row in initial_rows.items():
                start[key] = {
                    mass_field: {"raw_hex": struct.pack("<f", float(row[mass_input])).hex()},
                    aux: {"raw_hex": struct.pack("<f", float(row[aux_input])).hex()},
                }
            first_entry = {key: value["calls"][1]["entry"] for key, value in samples.items()}
            endpoints["initial_input_to_call1_entry"] = (start, first_entry)
            transitions[arm][pair] = {
                name: summarize_transition(a, b, mass_field, aux)
                for name, (a, b) in endpoints.items()
            }
            aux_values = [decode_f32(start[key][aux]) for key in start]
            mass_values = [decode_f32(start[key][mass_field]) for key in start]
            pre_aux = [decode_f32(first_entry[key][aux]) for key in first_entry]
            pre_mass = [decode_f32(first_entry[key][mass_field]) for key in first_entry]
            input_counts[arm][pair] = {
                "samples": len(start),
                "input_aux_all_zero": all(value == 0 for value in aux_values),
                "call1_entry_aux_all_zero": all(value == 0 for value in pre_aux),
                "input_mass_positive_aux_zero": sum(m > 0 and a == 0 for m, a in zip(mass_values, aux_values)),
                "input_mass_positive_aux_positive": sum(m > 0 and a > 0 for m, a in zip(mass_values, aux_values)),
                "input_mass_zero_aux_zero": sum(m == 0 and a == 0 for m, a in zip(mass_values, aux_values)),
                "call1_entry_mass_positive_aux_zero": sum(m > 0 and a == 0 for m, a in zip(pre_mass, pre_aux)),
                "among_input_mass_positive_aux_zero_cells_call1_entry_aux_became_positive": sum(
                    mass0 > 0 and aux0 == 0 and aux1 > 0
                    for mass0, aux0, aux1 in zip(mass_values, aux_values, pre_aux)
                ),
            }

    hydro = arm_data["HYDRO"][2]
    pr125_match = {}
    for endpoint, pr_endpoint in (("entry", "entry"), ("return", "return")):
        curr_endpoint = {
            key: value["calls"][1][endpoint]
            for key, value in hydro.items()
        }
        ref_endpoint = {key: value[pr_endpoint] for key, value in pr125.items()}
        pr125_match[endpoint] = {
            "3d_core": {
                field: field_match(ref_endpoint, curr_endpoint, field, 3)
                for field in CORE_3D
            },
            "2d_precipitation_and_surface": {
                field: field_match(ref_endpoint, curr_endpoint, field, 2)
                for field in PRECIP_2D
            },
        }

    receipts = {}
    capture_hashes = {}
    rank_sequences = {}
    for arm in ARMS:
        receipt, receipt_path, _, hashes, ranks = arm_data[arm]
        receipts[arm] = {
            "path": str(receipt_path.relative_to(ROOT)),
            "sha256": sha256(receipt_path),
            "status": receipt["status"],
            "launcher_exit": receipt["launcher_exit"],
            "binary_sha256": receipt["binary"]["sha256"],
            "script_sha256": receipt["script_sha256"],
            "selection_sha256": receipt["selection_sha256"],
            "copy_manifest_sha256": receipt["copy_manifest_sha256"],
            "initial_history_sha256": receipt["initial_history"]["sha256"],
            "input_files_unchanged": receipt["input_files_unchanged"],
        }
        capture_hashes[arm] = hashes
        rank_sequences[arm] = ranks

    aux_presence = {
        arm: {
            pair: {
                "input_positive_count": transitions[arm][pair]["initial_input_to_call1_entry"]["aux_start"]["strictly_positive_gt_0"],
                "call1_entry_positive_count": transitions[arm][pair]["initial_input_to_call1_entry"]["aux_end"]["strictly_positive_gt_0"],
                "call1_return_positive_count": transitions[arm][pair]["call1_entry_to_return"]["aux_end"]["strictly_positive_gt_0"],
                "scope": "first captured nonzero endpoint only; not the exact internal initialization operation",
            }
            for pair in PAIR_FIELDS
        }
        for arm in ARMS
    }

    result = {
        "schema": "cp02-kdm6-independent-raw-review-v1",
        "status": "PASS_SCOPED_RAW_RECOMPUTATION",
        "scope": "Independent raw IEEE-754 REAL32 decoding for OFF/HYDRO/LIQUID at the 624 selected native point-level samples (P01/P05/P09/P13, four mapped corners each, 39 levels). Computes mass/aux transitions for QC/NC, QR/NR, QI/NI at each call and the gap between calls. Compares both HYDRO call-1 endpoints against PR125. No scheme-eligibility filter, causal attribution, full-domain budget, or forecast validation.",
        "provenance": {
            "review_script": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha256(Path(__file__))},
            "capture_receipts": receipts,
            "new_capture_hashes": capture_hashes,
            "pr125_receipt": {"path": str(pr125_receipt_path.relative_to(ROOT)), "sha256": sha256(pr125_receipt_path), "status": pr125_receipt["status"]},
            "pr125_capture_hashes": pr125_hashes,
            "initial_fields_csv": {"path": str(initial_path.relative_to(ROOT)), "sha256": sha256(initial_path)},
            "input_copy_manifest_sha256": sha256(EVIDENCE / "inputs/copy_manifest.json"),
            "source_verification_sha256": sha256(EVIDENCE / "inputs/source_verification.json"),
        },
        "coverage": {
            "owned_samples_per_arm": {arm: len(arm_data[arm][2]) for arm in ARMS},
            "pr125_owned_samples": len(pr125),
            "rank_call_sequences": rank_sequences,
            "comparison_key": "label, 1-based global i/j/k; only owned_tile samples counted; duplicate owner/sample keys rejected.",
            "strict_positive_definition": "numeric value > 0; scheme eligibility is not applied.",
        },
        "field_mapping": {
            "qc_nc": {"runtime_candidate": ["qc", "nc"], "initial_input_fields": ["QCLOUD", "QNCLOUD"]},
            "qr_nr": {"runtime_candidate": ["qr", "nr"], "initial_input_fields": ["QRAIN", "QNRAIN"]},
            "qi_ni": {"runtime_candidate": ["qi", "ni"], "initial_input_fields": ["QICE", "QNICE"]},
            "abi_and_units_limit": "Names/units are candidate mappings from the prior call-boundary/registry evidence; the historical executable has no DWARF, and source identity with the binary is unproven.",
            "qib": "Excluded; QIB is rime-ice volume, not a number concentration.",
        },
        "hydro_call1_vs_pr125_raw": pr125_match,
        "mass_aux_transitions": transitions,
        "initial_positive_mass_zero_aux": input_counts,
        "first_captured_auxiliary_positivity": aux_presence,
        "interpretation_limits": [
            "Capture values describe sampled call-boundary state only.",
            "Input-to-call-1-entry value/count differences are numeric observations over selected cells. They are not attributed to driver initialization or another internal operation; exact binary field semantics are not independently established.",
            "Auxiliaries are zero in the selected input and call-1 entry samples; positive auxiliary values first appear at call-1 return among captured endpoints. This does not locate the exact internal operation that initialized them.",
            "Call-1 return-to-call-2 entry is an intervening interval and is not assigned to a specific operation.",
            "Call 2 happened to report itimestep 2 in all ranks here; invocation ordinal is not generally identified with timestep.",
            "Unweighted sums are descriptive across the selected stencil, not mass or water budgets.",
            "Inactive optional reflectivity buffer values are excluded; no diagnostic-buffer equality is assumed.",
            "The report does not infer causal effect or forecast performance from control-arm differences.",
        ],
    }
    output = EVIDENCE / "independent_capture_review.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
