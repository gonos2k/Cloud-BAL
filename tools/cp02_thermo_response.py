#!/usr/bin/env python3
"""Compare frozen initial thermodynamics with captured first-call KDM6 states."""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import struct
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
CAPTURES = EVIDENCE / "captures"
DEFAULT_INITIAL = EVIDENCE / "inputs/selected_initial_fields.csv"
DEFAULT_SELECTION = EVIDENCE / "selection.json"
DEFAULT_BINARY_INITIAL = ROOT / "docs/evidence/cp02_thermo_response_20261029/binary/initial_thermo.csv"
DEFAULT_BINARY_RECEIPT = ROOT / "docs/evidence/cp02_thermo_response_20261029/binary/initial_thermo_receipt.json"
VALIDATOR = ROOT / "tools/cp02_kdm6_controls.py"
OUTPUT = ROOT / "docs/evidence/cp02_thermo_response_20261029/analysis/thermo_response"
INITIAL_SHA256 = "522fc8600eb32e7c96baed296f57342fbfb51c5c5bad40e81dbd11aae2147c32"
SELECTION_SHA256 = "38602c67768d0836c5f911c43ff4bcced57073f6f222f1c91a63499c16956c6e"
BINARY_INITIAL_SHA256 = "789b1e2e0701ececc607631c05edb77e7b60c0eb09b11b117cb2bc49bc59be57"
BINARY_RECEIPT_SHA256 = "07af1b08b46f8d397f9a06d742c1b4e1df13d1bc861445182ddca34097af804b"
BINARY_EXTRACTOR_SHA256 = "feeaded9b0b7ea8adf4bae56ed1b3acbb598547b948a20c125682be1f69c3ab9"
COPY_MANIFEST_SHA256 = "01e00d732b1f983f55247e3ce97568a536a3aa6465059c864a0f292b93ca2f7e"
ARMS = ("OFF", "HYDRO", "LIQUID")
POINTS = ("P01", "P05")
INITIAL_FIELDS = {"QVAPOR": "q", "QCLOUD": "qc", "QRAIN": "qr"}
CAPTURE_FIELDS = ("q", "qc", "qr", "th", "pii", "p", "den", "nc", "nr")
SELECTED_FIELDS = {"q": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN"}
BINARY_INITIAL_FIELDS = ("QVAPOR", "QCLOUD", "QRAIN", "T", "THM", "P", "PB")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_validator():
    spec = importlib.util.spec_from_file_location("cp02_kdm6_controls", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_selection(path, validator):
    require(file_sha256(path) == SELECTION_SHA256,
            "selection.json differs from the frozen 624-key mapping")
    selected = validator.selection_map(Path(path))
    return selected


def finite_number(text, label):
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: expected numeric value") from exc
    require(math.isfinite(value), f"{label}: non-finite value")
    return value


def load_initial(path, selection_path, selected):
    path = Path(path)
    require(path.is_file(), f"initial fields CSV is missing: {path}")
    require(file_sha256(path) == INITIAL_SHA256,
            "initial fields CSV SHA-256 differs from frozen provenance")
    expected = {}
    for (i, j, k), label in selected.items():
        point, corner = label.split("_")
        if point in POINTS:
            expected[(point, corner, k)] = (i, j)
    require(len(expected) == len(POINTS) * 4 * 39,
            "selection does not identify four weighted corners at all 39 levels for P01/P05")
    selection_raw = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    selection_weights = {(item["label"], item["k"]): item["weight"]
                         for item in selection_raw["points"]}
    data = {}
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required = {"arm", "point_id", "corner", "native_j0", "native_i0", "level_k0", "weight", *INITIAL_FIELDS}
            require(reader.fieldnames is not None and required <= set(reader.fieldnames),
                    "initial fields CSV header is incomplete")
            for row in reader:
                arm, point, corner = row["arm"], row["point_id"], row["corner"]
                if point not in POINTS:
                    continue
                require(arm in ARMS, f"initial CSV has unexpected arm {arm!r}")
                try:
                    i0, j0, k0 = (int(row[name]) for name in ("native_i0", "native_j0", "level_k0"))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"initial CSV has invalid integer coordinates at {point}/{corner}") from exc
                k = k0 + 1
                key = (point, corner, k)
                require(key in expected, f"initial CSV has key absent from frozen selection: {key}")
                require(expected[key] == (i0 + 1, j0 + 1),
                        f"initial CSV coordinate is not bound to selection for {key}")
                label = f"{point}_{corner}"
                selected_weight = selection_weights[(label, k)]
                weight = finite_number(row["weight"], f"{key} weight")
                require(weight == selected_weight,
                        f"initial CSV weight does not match frozen selection for {key}")
                record_key = (arm, point, corner, k)
                require(record_key not in data, f"duplicate initial CSV key {record_key}")
                record = {"weight": weight, "csv_native_i0": i0, "csv_native_j0": j0,
                          "csv_level_k0": k0}
                for source_name in INITIAL_FIELDS:
                    record[source_name] = finite_number(row[source_name], f"{record_key} {source_name}")
                    record[source_name + "_raw_decimal"] = row[source_name]
                data[record_key] = record
    except (OSError, csv.Error) as exc:
        raise ValueError(f"cannot read initial fields CSV: {exc}") from exc
    require(len(data) == len(ARMS) * len(expected),
            f"initial CSV must contain exactly {len(ARMS) * len(expected)} selected P01/P05 rows")
    for arm in ARMS:
        for point in POINTS:
            for k in range(1, 40):
                corners = [data[(arm, point, corner, k)] for corner in ("00", "01", "10", "11")]
                require(abs(sum(item["weight"] for item in corners) - 1.0) <= 1e-12,
                        f"initial CSV corner weights do not sum to one for {arm}/{point}/k{k}")
    return data


def load_binary_initial(path, receipt_path, selection_path, selected, initial):
    path, receipt_path = Path(path), Path(receipt_path)
    require(path.is_file() and file_sha256(path) == BINARY_INITIAL_SHA256,
            "binary initial thermodynamic CSV is missing or differs from the frozen hash")
    require(receipt_path.is_file() and file_sha256(receipt_path) == BINARY_RECEIPT_SHA256,
            "binary initial thermodynamic receipt is missing or differs from the frozen hash")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt.get("extraction", {}).get("output_sha256") == BINARY_INITIAL_SHA256 and
            receipt["extraction"].get("row_count") == 1872 and
            receipt["extraction"].get("rows_per_arm") == {arm: 624 for arm in ARMS},
            "binary initial extraction receipt does not bind the selected CSV rows")
    require(receipt.get("extractor", {}).get("sha256") == BINARY_EXTRACTOR_SHA256,
            "binary initial extractor bytes differ from the frozen extraction")
    inputs_dir = Path(DEFAULT_INITIAL).parent
    copy_manifest_path = inputs_dir / "copy_manifest.json"
    require(file_sha256(copy_manifest_path) == COPY_MANIFEST_SHA256 and
            receipt["source_evidence"]["copy_manifest"]["sha256"] == COPY_MANIFEST_SHA256,
            "binary initial input lineage does not match the frozen copy manifest")
    require(receipt["source_evidence"]["selected_initial_fields"]["sha256"] == INITIAL_SHA256,
            "binary initial input lineage does not match the pinned selected-fields CSV")
    copy_manifest = json.loads(copy_manifest_path.read_text(encoding="utf-8"))
    source_receipts = receipt["source_evidence"]["wrfinput_files_before_after"]
    require(len(source_receipts) == len(ARMS), "binary initial receipt must bind all three wrfinput files")
    for arm in ARMS:
        expected_source = copy_manifest["arms"][arm]["netcdf_sources"]["wrfinput_d01"]["file"]
        matching = [item for source_path, item in source_receipts.items()
                    if source_path == expected_source["path"]]
        require(len(matching) == 1 and matching[0]["sha256"] == expected_source["sha256"] and
                matching[0]["size_bytes"] == expected_source["size_bytes"],
                f"{arm}: extracted initial fields are not bound to the frozen wrfinput file")

    selected_weights = {}
    selected_by_label = {}
    for (i, j, k), label in selected.items():
        selected_by_label[(label, k)] = (i, j)
    selection_raw = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    selected_weights = {(item["label"], item["k"]): item["weight"]
                        for item in selection_raw["points"]}
    data = {}
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"arm", "point_id", "corner", "weight", "i_wrf_1based", "j_wrf_1based",
                    "k_wrf_1based", "T00_K_metadata_only", *BINARY_INITIAL_FIELDS}
        require(reader.fieldnames is not None and required <= set(reader.fieldnames),
                "binary initial CSV header is incomplete")
        for row in reader:
            arm, point, corner = row["arm"], row["point_id"], row["corner"]
            require(arm in ARMS and point in {label.split("_")[0] for label in selected.values()},
                    f"unexpected binary initial CSV arm/point: {arm}/{point}")
            try:
                i, j, k = (int(row[name]) for name in
                           ("i_wrf_1based", "j_wrf_1based", "k_wrf_1based"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"binary initial CSV has invalid coordinates at {arm}/{point}/{corner}") from exc
            label = f"{point}_{corner}"
            key = (label, k)
            require(key in selected_by_label and selected_by_label[key] == (i, j),
                    f"binary initial CSV coordinate is not bound to selection for {arm}/{key}")
            weight = finite_number(row["weight"], f"binary initial {arm}/{key} weight")
            require(weight == selected_weights[key],
                    f"binary initial CSV weight does not match selection for {arm}/{key}")
            data_key = (arm, point, corner, k)
            require(data_key not in data, f"duplicate binary initial CSV key {data_key}")
            record = {"weight": weight}
            for field in BINARY_INITIAL_FIELDS:
                record[field] = finite_number(row[field], f"binary initial {data_key} {field}")
                record[field + "_raw_decimal"] = row[field]
            record["T00_K_metadata_only"] = finite_number(
                row["T00_K_metadata_only"], f"binary initial {data_key} T00 metadata")
            if point in POINTS:
                selected_record = initial[(arm, point, corner, k)]
                for binary_field, initial_field in (("QVAPOR", "QVAPOR"),
                                                    ("QCLOUD", "QCLOUD"),
                                                    ("QRAIN", "QRAIN")):
                    require(record[binary_field] == selected_record[initial_field],
                            f"binary initial {binary_field} differs from pinned selected initial CSV at {data_key}")
            data[data_key] = record
    expected_count = len(ARMS) * len(selected)
    require(len(data) == expected_count,
            f"binary initial CSV must contain exactly {expected_count} selected arm/key rows")
    for arm in ARMS:
        t00 = receipt["extraction"]["T00_K"][arm]
        for point in ("P01", "P05", "P09", "P13"):
            for k in range(1, 40):
                corners = [data[(arm, point, corner, k)] for corner in ("00", "01", "10", "11")]
                require(abs(sum(item["weight"] for item in corners) - 1.0) <= 1e-12,
                        f"binary initial corner weights do not sum to one for {arm}/{point}/k{k}")
                require(all(item["T00_K_metadata_only"] == t00 for item in corners),
                        f"binary initial T00 metadata differs from its receipt for {arm}/{point}/k{k}")
    return data


def weighted_state(arm, point, k, values_by_corner):
    weights = {}
    for corner in ("00", "01", "10", "11"):
        item = values_by_corner[corner]
        weights[corner] = item["weight"]
    weight_sum = sum(weights.values())
    require(abs(weight_sum - 1.0) <= 1e-12,
            f"corner weights do not sum to one for {arm}/{point}/k{k}")
    result = {}
    for field in CAPTURE_FIELDS:
        values = {corner: values_by_corner[corner][field] for corner in weights}
        require(all(math.isfinite(value) for value in values.values()),
                f"non-finite captured {field} at {arm}/{point}/k{k}")
        result[field] = sum(weights[corner] * values[corner] for corner in weights)
        result[field + "_corner_values"] = values
    result["weight_sum"] = weight_sum
    return result


def weighted_initial(arm, point, k, initial):
    corners = {corner: initial[(arm, point, corner, k)] for corner in ("00", "01", "10", "11")}
    result = {"weight_sum": sum(item["weight"] for item in corners.values())}
    for source, target in INITIAL_FIELDS.items():
        result[target] = sum(corners[corner]["weight"] * corners[corner][source]
                             for corner in corners)
        result[target + "_corner_values"] = {
            corner: {"value": corners[corner][source],
                     "source_csv_decimal": corners[corner][source + "_raw_decimal"],
                     "weight": corners[corner]["weight"]}
            for corner in corners}
    return result


def weighted_binary_initial(arm, point, k, binary_initial):
    corners = {corner: binary_initial[(arm, point, corner, k)]
               for corner in ("00", "01", "10", "11")}
    weights = {corner: item["weight"] for corner, item in corners.items()}
    result = {"weight_sum": sum(weights.values())}
    require(abs(result["weight_sum"] - 1.0) <= 1e-12,
            f"binary initial corner weights do not sum to one for {arm}/{point}/k{k}")
    for field in BINARY_INITIAL_FIELDS:
        result[field] = sum(weights[corner] * corners[corner][field] for corner in corners)
        result[field + "_corner_values"] = {
            corner: {"value": corners[corner][field],
                     "source_csv_decimal": corners[corner][field + "_raw_decimal"],
                     "weight": weights[corner]}
            for corner in corners}
    return result


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "q25": None, "median": None,
                "q75": None, "max": None}
    return {"count": len(ordered), "min": ordered[0], "q25": percentile(ordered, .25),
            "median": percentile(ordered, .5), "q75": percentile(ordered, .75), "max": ordered[-1]}


def transition_summary(rows, expected_samples=624, arms=ARMS):
    transitions = {}
    for arm in arms:
        require(sum(row_arm == arm for row_arm, _, _ in rows) == expected_samples,
                f"{arm}: expected {expected_samples} selected keys for inter-call transition")
        comparisons = []
        for (row_arm, label, k), states in rows.items():
            if row_arm != arm:
                continue
            pre, post = states["call1_return"], states["call2_entry"]
            if pre["qr"] <= 0.0 and post["qr"] > 0.0:
                comparisons.append({"label": label, "k": k,
                                    "qr": post["qr"], "nr": post["nr"]})
        amplitudes = [row["qr"] for row in comparisons]
        nr_zero_amplitudes = [row["qr"] for row in comparisons if row["nr"] == 0.0]
        transitions[arm] = {
            "transition": "call1 return to call2 entry; newly positive iff prior qr <= 0 and current qr > 0",
            "sample_count": expected_samples,
            "newly_positive_qr_count": len(comparisons),
            "newly_positive_qr_amplitude": distribution(amplitudes),
            "newly_positive_qr_with_nr_exact_zero_count": len(nr_zero_amplitudes),
            "newly_positive_qr_amplitude_where_nr_zero": distribution(nr_zero_amplitudes),
            "newly_positive_samples": comparisons,
        }
    return transitions


def build_analysis(initial, binary_initial, selected_profiles_path, validator_summary,
                   initial_path, binary_initial_path, binary_receipt_path, selection_path):
    selected = {}
    full_profiles = {}
    with Path(selected_profiles_path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            point_corner = row["label"]
            point, corner = point_corner.split("_")
            k = int(row["k"])
            values = {}
            for field in CAPTURE_FIELDS:
                raw = row[field + "_raw_hex"]
                require(len(raw) == 8 and all(ch in "0123456789abcdef" for ch in raw),
                        f"malformed captured REAL*4 bytes for {field}/{point_corner}/k{k}")
                value = struct.unpack("<f", bytes.fromhex(raw))[0]
                require(math.isfinite(value), f"non-finite captured {field}/{point_corner}/k{k}")
                values[field] = value
                values[field + "_raw_hex"] = raw
            state = f"call{row['call_ordinal']}_{row['endpoint']}"
            full_profiles.setdefault((row["arm"], point_corner, k), {})[state] = values
            if point not in POINTS:
                continue
            values["weight"] = initial[(row["arm"], point, corner, k)]["weight"]
            key = (row["arm"], point, corner, k, state)
            require(key not in selected, f"duplicate captured selected point {key}")
            selected[key] = values
    expected_rows = len(ARMS) * len(POINTS) * 4 * 39 * 4
    require(len(selected) == expected_rows,
            f"strict capture output must contain {expected_rows} P01/P05 endpoint rows")
    require(len(full_profiles) == len(ARMS) * 624,
            "strict capture output must contain all 624 selected keys for each arm")
    for key, states in full_profiles.items():
        require(set(states) == {"call1_entry", "call1_return", "call2_entry", "call2_return"},
                f"incomplete captured endpoints for {key}")
    records, profile_rows = {}, []
    for arm in ARMS:
        for point in POINTS:
            for k in range(1, 40):
                init_values = weighted_initial(arm, point, k, initial)
                states = {"initial": init_values,
                          "initial_wrfinput": weighted_binary_initial(arm, point, k, binary_initial)}
                endpoints = ("call1_entry", "call1_return", "call2_entry", "call2_return")
                for endpoint in endpoints:
                    corner_values = {corner: selected[(arm, point, corner, k, endpoint)]
                                     for corner in ("00", "01", "10", "11")}
                    states[endpoint] = weighted_state(arm, point, k, corner_values)
                    for field in CAPTURE_FIELDS:
                        states[endpoint][field + "_corner_raw_hex"] = {
                            corner: corner_values[corner][field + "_raw_hex"] for corner in corner_values}
                for state, fields in states.items():
                    records[(arm, point, k, state)] = fields
                    for field, value in fields.items():
                        if field.endswith("_corner_values") or field.endswith("_corner_raw_hex") or field == "weight_sum":
                            continue
                        row = {"arm": arm, "point": point, "level_k1": k, "state": state,
                               "field": field, "weighted_value": value,
                               "numeric_unit": "captured/source native numeric value; unit meaning not assigned"}
                        if state == "initial" and field in INITIAL_FIELDS.values():
                            source = next(name for name, target in INITIAL_FIELDS.items() if target == field)
                            row["source_numeric_unit_candidate"] = f"initial CSV {source} numeric value"
                            row["corner_source_values"] = json.dumps(
                                fields[field + "_corner_values"], sort_keys=True)
                        elif state == "initial_wrfinput" and field in BINARY_INITIAL_FIELDS:
                            row["source_numeric_unit_candidate"] = f"initial wrfinput variable label {field}; unit unassigned"
                            row["corner_source_values"] = json.dumps(
                                fields[field + "_corner_values"], sort_keys=True)
                        elif state != "initial" and field in CAPTURE_FIELDS:
                            row["source_numeric_unit_candidate"] = f"KDM6 argument candidate {field} REAL*4"
                            row["corner_raw_hex"] = json.dumps(fields[field + "_corner_raw_hex"], sort_keys=True)
                        profile_rows.append(row)
    intercall_rows = {}
    for (arm, label, k), states in full_profiles.items():
        intercall_rows[(arm, label, k)] = {
            "call1_return": states["call1_return"],
            "call2_entry": states["call2_entry"],
        }
    intercall = transition_summary(intercall_rows)
    amplitude_summaries = {}
    for arm in ARMS:
        by_state = {}
        for call in (1, 2):
            for endpoint in ("entry", "return"):
                values = []
                state = f"call{call}_{endpoint}"
                for (row_arm, _, _), states in full_profiles.items():
                    if row_arm == arm:
                        sample = states[state]
                        if sample["qr"] > 0.0 and sample["nr"] == 0.0:
                            values.append(sample["qr"])
                by_state[state] = {"qr_positive_nr_exact_zero_count": len(values),
                                   "qr_amplitude": distribution(values)}
        amplitude_summaries[arm] = by_state
    checkpoint_profiles = {
        arm: {state: {field: records[(arm, "P05", 8, state)][field]
                      for field in ("q", "qc", "qr", "th")}
              for state in ("call1_entry", "call1_return")}
        for arm in ("HYDRO", "LIQUID")
    }
    summary = {
        "schema": "cp02-thermo-response-v1",
        "status": "PASS_SCOPED_CAPTURE_AND_INITIAL_SELECTION",
        "scope": "Weighted P01/P05 initial and captured KDM6 states across 39 levels for the three retained arms. Captured values preserve REAL*4 bytes alongside the weighted numeric summaries.",
        "limits": [
            "No runtime unit or actual temperature interpretation is assigned to captured arguments.",
            "The initial CSV source-unit attributes are not used to infer captured argument units.",
            "Initial wrfinput labels T, THM, P, and PB are kept distinct; no field transform or actual-temperature inference is applied.",
            "No mass closure, process causality, or threshold claim is made.",
            "Inter-call transition means call 1 return to call 2 entry; newly positive means prior qr <= 0 and current qr > 0.",
        ],
        "inputs": {"initial_csv_sha256": file_sha256(initial_path),
                   "binary_initial_csv_sha256": file_sha256(binary_initial_path),
                   "binary_initial_receipt_sha256": file_sha256(binary_receipt_path),
                   "binary_initial_extractor_sha256": BINARY_EXTRACTOR_SHA256,
                   "binary_initial_copy_manifest_sha256": COPY_MANIFEST_SHA256,
                   "selection_sha256": file_sha256(selection_path),
                   "strict_validator": "tools/cp02_kdm6_controls.py",
                   "strict_validator_status": validator_summary["status"],
                   "strict_validator_output_summary": validator_summary["summary_sha256"],
                   "strict_validator_selected_profiles": validator_summary["profiles_sha256"]},
        "binary_initial_selection_binding": "Each arm/point/corner/k coordinate and recorded weight matches frozen selection.json; QVAPOR/QCLOUD/QRAIN also match selected_initial_fields.csv for P01/P05. Receipt binds all three input wrfinput hashes to the frozen copy manifest.",
        "point_count": 2, "levels_per_point": 39, "arms": list(ARMS),
        "full_capture_endpoint_sample_count": 3 * 624 * 4,
        "intercall_newly_positive_qr": intercall,
        "mass_positive_nr_zero_amplitude_by_call": amplitude_summaries,
        "P05_k8_HYDRO_LIQUID_call1_weighted_profiles": checkpoint_profiles,
        "supplied_user_checkpoints": {
            "P05_k8_HYDRO_call1_entry_qr": 2.718877e-4,
            "P05_k8_HYDRO_call1_return_qr": 0.0,
            "P05_k8_LIQUID_call1_entry_qr": 2.710023e-4,
            "P05_k8_LIQUID_call1_return_qr": 2.615346e-4,
            "checkpoint_scope": "Values are weighted four-corner states; q, qc, and th are retained separately in profiles.csv for comparison. Checkpoints do not establish units or causes.",
        },
        "profiles": {"row_count": len(profile_rows), "path": "profiles.csv",
                     "weighted_point_state_count": len(records)},
    }
    return summary, profile_rows, records


def write_csv(path, rows):
    require(rows, f"refusing to write empty CSV: {path}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def analyze(capture_dir=CAPTURES, output_dir=OUTPUT, *, initial_path=DEFAULT_INITIAL,
            binary_initial_path=DEFAULT_BINARY_INITIAL,
            binary_receipt_path=DEFAULT_BINARY_RECEIPT, selection_path=DEFAULT_SELECTION):
    capture_dir, output_dir = Path(capture_dir), Path(output_dir)
    initial_path, binary_initial_path = Path(initial_path), Path(binary_initial_path)
    binary_receipt_path, selection_path = Path(binary_receipt_path), Path(selection_path)
    require(not output_dir.exists() and not output_dir.is_symlink(),
            f"output path already exists: {output_dir}")
    require(capture_dir.is_dir(), f"capture root is not a directory: {capture_dir}")
    validator = load_validator()
    selected = read_selection(selection_path, validator)
    initial = load_initial(initial_path, selection_path, selected)
    binary_initial = load_binary_initial(binary_initial_path, binary_receipt_path,
                                         selection_path, selected, initial)
    staging_root = Path(tempfile.mkdtemp(prefix="cp02-thermo-response-"))
    try:
        validated_dir = staging_root / "strict_capture"
        validator_result = validator.analyze(capture_dir, validated_dir,
                                             inputs_dir=validator.INPUTS,
                                             selection_path=selection_path,
                                             capture_script=validator.CAPTURE_SCRIPT,
                                             profile=validator.PROFILE)
        summary_path = validated_dir / "summary.json"
        profiles_path = validated_dir / "selected_profiles.csv"
        summary, profiles, records = build_analysis(initial, binary_initial, profiles_path,
                                                   {"status": validator_result["status"],
                                                    "summary_sha256": file_sha256(summary_path),
                                                    "profiles_sha256": file_sha256(profiles_path)},
                                                   initial_path, binary_initial_path,
                                                   binary_receipt_path, selection_path)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="." + output_dir.name + ".", dir=output_dir.parent))
        try:
            write_csv(staging / "profiles.csv", profiles)
            summary["profiles"]["sha256"] = file_sha256(staging / "profiles.csv")
            (staging / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True,
                                                               allow_nan=False) + "\n", encoding="utf-8")
            os.replace(staging, output_dir)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
        return summary
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, default=CAPTURES)
    parser.add_argument("--initial-csv", type=Path, default=DEFAULT_INITIAL)
    parser.add_argument("--binary-initial-csv", type=Path, default=DEFAULT_BINARY_INITIAL)
    parser.add_argument("--binary-receipt", type=Path, default=DEFAULT_BINARY_RECEIPT)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = analyze(args.capture_dir, args.output_dir, initial_path=args.initial_csv,
                         binary_initial_path=args.binary_initial_csv,
                         binary_receipt_path=args.binary_receipt, selection_path=args.selection)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
