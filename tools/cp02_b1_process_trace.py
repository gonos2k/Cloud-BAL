#!/usr/bin/env python3
"""Stream and audit CP02 B1 process-trace records for one model arm.

Each invocation handles exactly one arm. The tool verifies the candidate
phase schemas, retains raw transfer bitwords, joins the four per-step update
phases in SQLite, and reports local cell-step checks. It does not infer
column budgets, replay the incomplete PREVP formula, or pool points/arms.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


KEY = ("rank", "call_id", "itimestep", "loop", "j", "i", "k")
ENTRY_FIELDS = (
    "q", "t", "den", "qci1", "qci2", "qrs1", "qrs2", "qrs3",
    "nci1", "nci2", "nci3", "nrs1", "nrs2", "nrs3", "brs",
)
SCHEMAS = {
    "ENTRY_RAW": (KEY, ENTRY_FIELDS, "f32"),
    "ENTRY_CLAMPED": (KEY, ENTRY_FIELDS, "f32"),
    "SATURATION": (KEY, ("q", "t", "den", "qs1", "qs2", "rh1", "rh2", "sw"), "f32"),
    "SATDT": (KEY, ("dtcld", "satdt", "q", "qs", "rh"), "f32"),
    "PREVP_FORMULA": (KEY, ("prevp", "nrs", "qrs", "den", "rh", "n0r", "fac_evap"), "prevp64"),
    "PREVP_RAW": (KEY, ("prevp", "qrs", "satdt", "dtcld"), "f32"),
    "PREVP_QR_CAP": (KEY, ("prevp",), "f32"),
    "PREVP_SAT_CAP": (KEY, ("prevp",), "f32"),
    "PROCESS_RATES": (KEY, (
        "praut", "pracw", "prevp", "piacr", "pgacr", "psacr", "pmulrs", "pmulrg",
        "pseml", "pgeml", "psevp", "pgevp", "psdep", "pgdep", "pinud", "pidep",
    ), "f32"),
    "PRE_UPDATE": (KEY, ENTRY_FIELDS + ("work2", "dtcld"), "f32"),
    "LATENT_INPUT": (KEY, ("work2", "xlwork2", "cpm", "dtcld", "xl", "xlf"), "f32"),
    "POST_STEP": (KEY, ENTRY_FIELDS, "f32"),
    "SURFACE_RETURN": (("rank", "call_id", "itimestep", "j", "i"),
                        ("rainncv", "rain", "sr"), "f32"),
    "SNOW_RETURN": (("rank", "call_id", "itimestep", "j", "i"), ("snow",), "f32"),
    "GRAUPEL_RETURN": (("rank", "call_id", "itimestep", "j", "i"), ("graupel",), "f32"),
}
UPDATE_PHASES = ("PROCESS_RATES", "PRE_UPDATE", "LATENT_INPUT", "POST_STEP")
PREVP_PHASES = ("PREVP_FORMULA", "PREVP_RAW", "PREVP_QR_CAP", "PREVP_SAT_CAP")
JOIN_PHASES = (*PREVP_PHASES, *UPDATE_PHASES)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def decode_word(token: str, kind: str, where: str) -> tuple[str, float | int]:
    """Validate signed transfer integer and return canonical word and value."""
    word = int(token, 10)
    if kind == "f32":
        require(-(1 << 31) <= word < (1 << 31), f"{where}: REAL32 transfer outside signed INTEGER*4")
        raw = struct.pack("<i", word)
        value = struct.unpack("<f", raw)[0]
    else:
        require(-(1 << 63) <= word < (1 << 63), f"{where}: REAL64 transfer outside signed INTEGER*8")
        raw = struct.pack("<q", word)
        value = struct.unpack("<d", raw)[0]
    require(math.isfinite(value), f"{where}: non-finite transferred value")
    return raw.hex(), value


def parse_record(line: str, source: str, line_number: int) -> dict | None:
    fields = line.split()
    if not fields or fields[0] not in SCHEMAS:
        return None
    phase = fields[0]
    key_fields, value_fields, value_kind = SCHEMAS[phase]
    expected = 1 + len(key_fields) + len(value_fields)
    require(len(fields) == expected,
            f"{source}:{line_number}: {phase} has {len(fields) - 1} values; expected {expected - 1}")
    key = tuple(int(value, 10) for value in fields[1:1 + len(key_fields)])
    raw_words, values = {}, {}
    for name, token in zip(value_fields, fields[1 + len(key_fields):]):
        kind = "f64" if phase == "PREVP_FORMULA" and name == "n0r" else "f32"
        raw, value = decode_word(token, kind, f"{source}:{line_number}:{phase}.{name}")
        raw_words[name] = raw
        values[name] = value
    return {"phase": phase, "key": key, "key_fields": key_fields,
            "value_fields": value_fields, "raw": raw_words, "values": values,
            "source": source, "line_number": line_number}


def iter_fortran_records(lines, source: str):
    """Join list-directed continuations by schema length without buffering a file."""
    pending = None
    start_line = None
    expected = 0
    for line_number, line in enumerate(lines, 1):
        tokens = line.split()
        if not tokens:
            continue
        if tokens[0] in SCHEMAS:
            require(pending is None,
                    f"{source}:{line_number}: new phase starts before prior wrapped record completed")
            phase = tokens[0]
            key_fields, value_fields, _ = SCHEMAS[phase]
            expected = len(key_fields) + len(value_fields)
            pending = [phase, *tokens[1:]]
            start_line = line_number
        elif pending is not None:
            pending.extend(tokens)
        else:
            raise ValueError(f"{source}:{line_number}: unrecognized trace record {tokens[0]!r}")
        actual = len(pending) - 1
        require(actual <= expected,
                f"{source}:{start_line}: wrapped record has {actual} values; expected {expected}")
        if actual == expected:
            yield parse_record(" ".join(pending), source, start_line)
            pending = None
            start_line = None
    require(pending is None, f"{source}:{start_line}: truncated wrapped Fortran record")


def f32(value: float) -> float:
    """Round one REAL32 operation result, matching default Fortran REAL."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def read_prefix_receipt(path: Path) -> dict:
    """Read the external gate without opening any native trace file."""
    receipt_bytes = path.read_bytes()
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    require(receipt.get("receipt_schema_version") == 1,
            f"{path}: unsupported or missing receipt_schema_version=1")
    require(receipt.get("status") == "PASS_FULL_PREFIX" and receipt.get("full_prefix_pass") is True,
            f"{path}: full-prefix validation is not PASS; refusing to open trace files")
    step_seconds = float(receipt["time_step_seconds"])
    require(math.isfinite(step_seconds) and step_seconds > 0,
            f"{path}: invalid time_step_seconds")
    times = receipt.get("times_utc_hours", receipt.get("times"))
    require(times == [12, 13, 14],
            f"{path}: full-prefix gate must identify ordered hours [12, 13, 14]")
    receipt["times"] = times
    require(sha256_file(path) == receipt_sha256, f"{path}: receipt changed while being read")
    receipt["_receipt_sha256"] = receipt_sha256
    require(isinstance(receipt.get("trace_files"), list) and receipt["trace_files"],
            f"{path}: missing trace_files inventory")
    require(receipt.get("case") in {"OLD", "FIX"}, f"{path}: receipt case must be OLD or FIX")
    return receipt


def validate_trace_pins(receipt_path: Path, receipt: dict, traces: list[Path]) -> tuple[dict, list[dict]]:
    """Hash exact supplied bytes only after both per-arm gates have passed."""
    pinned = {}
    for entry in receipt["trace_files"]:
        name = Path(entry["path"]).name
        require(name not in pinned, f"{receipt_path}: duplicate trace basename {name}")
        pinned[name] = entry["sha256"]
    actual = []
    for trace in traces:
        actual_hash, actual_bytes = sha256_and_size(trace)
        expected_hash = pinned.get(trace.name)
        require(expected_hash == actual_hash,
                f"{trace}: trace SHA-256 is absent from or differs from prefix receipt")
        expected_bytes = next(item.get("bytes") for item in receipt["trace_files"]
                              if Path(item["path"]).name == trace.name)
        require(expected_bytes is None or int(expected_bytes) == actual_bytes,
                f"{trace}: byte size differs from prefix receipt")
        actual.append({"path": str(trace), "sha256": actual_hash, "bytes": actual_bytes})
    require(set(pinned) == {trace.name for trace in traces},
            f"{receipt_path}: supplied trace inventory differs from prefix receipt")
    return receipt, actual


def read_corner_map(path: Path) -> dict[tuple[int, int], list[dict]]:
    by_native = defaultdict(list)
    by_point = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            native_j, native_i = int(row["wrf_j_1based"]), int(row["wrf_i_1based"])
            weight = float(row["weight"])
            entry = {"point_id": row["point_id"], "corner": row["corner"], "weight": weight}
            by_native[(native_j, native_i)].append(entry)
            by_point[row["point_id"]].append(weight)
    require(by_point, f"{path}: no selected corners")
    for point_id, weights in by_point.items():
        require(len(weights) == 4, f"{path}: {point_id} has {len(weights)} corners, expected four")
        require(abs(sum(weights) - 1.0) <= 1e-12, f"{path}: {point_id} corner weights do not sum to one")
    return dict(by_native)


def hour_label(itimestep: int, step_seconds: float) -> int:
    elapsed = itimestep * step_seconds
    return max(1, math.ceil(elapsed / 3600.0))


def update_checks(joined: dict[str, dict[str, float]]) -> dict[str, float]:
    before = joined["PRE_UPDATE"]
    latent = joined["LATENT_INPUT"]
    after = joined["POST_STEP"]

    q_delta = f32(after["q"] - before["q"])
    q_step = f32(f32(before["work2"] * before["dtcld"]))
    q_expected = f32(before["q"] + q_step)
    q_residual = f32(after["q"] - q_expected)
    q_equation_residual = f32(q_delta - q_step)

    t_delta = f32(after["t"] - before["t"])
    t_div = f32(latent["xlwork2"] / latent["cpm"])
    t_step = f32(t_div * latent["dtcld"])
    t_expected = f32(before["t"] - t_step)
    t_residual = f32(after["t"] - t_expected)
    t_equation_residual = f32(t_delta + t_step)
    return {
        "q_expected": q_expected, "q_residual": q_residual,
        "q_equation_residual": q_equation_residual,
        "t_expected": t_expected, "t_residual": t_residual,
        "t_equation_residual": t_equation_residual,
    }


def optional_value(values: dict, phase: str, field: str):
    record = values.get(phase)
    return None if record is None else record.get(field)


def optional_word(words: dict, phase: str, field: str):
    record = words.get(phase)
    return None if record is None else record.get(field)


def zero_sign_class(value: float, raw_word_hex: str) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "negative_zero" if int.from_bytes(bytes.fromhex(raw_word_hex), "little") & 0x80000000 else "positive_zero"


def open_database(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("""CREATE TABLE records (
        phase TEXT NOT NULL, key TEXT NOT NULL, key_values TEXT NOT NULL,
        line_number INTEGER NOT NULL, source TEXT NOT NULL, file_ordinal INTEGER NOT NULL,
        values_json TEXT NOT NULL, raw_json TEXT NOT NULL,
        PRIMARY KEY (phase, key))""")
    db.execute("CREATE INDEX records_by_key ON records(key, phase)")
    return db


def load_trace(db: sqlite3.Connection, paths: list[Path]) -> list[dict]:
    pins = []
    for file_ordinal, path in enumerate(paths):
        count = 0
        opener = gzip.open if path.suffix == ".gz" else open
        raw_hash = sha256_file(path)
        with opener(path, "rt", encoding="ascii") as stream:
            for record in iter_fortran_records(stream, str(path)):
                count += 1
                key_json = json.dumps(record["key"], separators=(",", ":"))
                db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                    record["phase"], key_json, key_json, record["line_number"], str(path), file_ordinal,
                    json.dumps(record["values"], separators=(",", ":")),
                    json.dumps(record["raw"], separators=(",", ":")),
                ))
        require(sha256_file(path) == raw_hash, f"{path}: trace changed while it was being parsed")
        db.commit()
        pins.append({"path": str(path), "sha256": raw_hash, "recognized_records": count})
    return pins


def joined_updates(db: sqlite3.Connection):
    phase_select = ", ".join(
        f"MAX(CASE WHEN phase='{phase}' THEN line_number END) AS line_{phase}, "
        f"MAX(CASE WHEN phase='{phase}' THEN values_json END) AS values_{phase}, "
        f"MAX(CASE WHEN phase='{phase}' THEN raw_json END) AS raw_{phase}, "
        f"MAX(CASE WHEN phase='{phase}' THEN source END) AS source_{phase}, "
        f"MAX(CASE WHEN phase='{phase}' THEN file_ordinal END) AS ordinal_{phase}"
        for phase in JOIN_PHASES
    )
    query = f"SELECT key, {phase_select} FROM records WHERE phase IN ({','.join('?' for _ in JOIN_PHASES)}) GROUP BY key ORDER BY MIN(file_ordinal), MIN(line_number)"
    for row in db.execute(query, JOIN_PHASES):
        key = tuple(json.loads(row[0]))
        line_numbers, values, raw_values, sources, ordinals = {}, {}, {}, {}, {}
        for index, phase in enumerate(JOIN_PHASES):
            offset = 1 + index * 5
            line_numbers[phase] = row[offset]
            payload = row[offset + 1]
            raw_payload = row[offset + 2]
            sources[phase] = row[offset + 3]
            ordinals[phase] = row[offset + 4]
            if payload is not None:
                values[phase] = json.loads(payload)
                raw_values[phase] = json.loads(raw_payload)
        present_updates = [phase for phase in UPDATE_PHASES if line_numbers[phase] is not None]
        require(present_updates == list(UPDATE_PHASES),
                f"incomplete update transaction key={key}: phases={present_updates}")
        present = [phase for phase in JOIN_PHASES if line_numbers[phase] is not None]
        require(len({sources[phase] for phase in present}) == 1 and
                len({ordinals[phase] for phase in present}) == 1,
                f"transaction key={key} spans source files: {sources}")
        formula_present = line_numbers["PREVP_FORMULA"] is not None
        require(formula_present == (line_numbers["PREVP_RAW"] is not None),
                f"PREVP_FORMULA/PREVP_RAW presence differs at key={key}")
        raw_present = line_numbers["PREVP_RAW"] is not None
        require(not any(line_numbers[phase] is not None for phase in PREVP_PHASES[2:]) or raw_present,
                f"PREVP cap without PREVP_RAW at key={key}")
        chronology = [phase for phase in PREVP_PHASES if line_numbers[phase] is not None]
        chronology.extend(UPDATE_PHASES)
        chronology_lines = [line_numbers[phase] for phase in chronology]
        require(chronology_lines == sorted(chronology_lines),
                f"reordered update transaction key={key}: source={next(iter(sources.values()))} "
                f"lines={line_numbers}")
        yield key, values, raw_values, line_numbers, next(iter(sources[phase] for phase in present))


def write_outputs(db: sqlite3.Connection, output_dir: Path, arm: str, source_pins: list[dict],
                  corners: dict[tuple[int, int], list[dict]], step_seconds: float) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / f"{arm.lower()}_cell_steps.csv"
    totals_path = output_dir / f"{arm.lower()}_point_hour_process_sums.csv"
    event_path = output_dir / f"{arm.lower()}_prevp_phase_events.csv"
    zero_path = output_dir / f"{arm.lower()}_zero_rate_events.csv"
    event_counts_path = output_dir / f"{arm.lower()}_prevp_phase_counts.csv"
    phase_path = output_dir / f"{arm.lower()}_phase_records.csv"
    phase_counts = {phase: 0 for phase in SCHEMAS}
    transaction_count = 0
    max_abs_q_residual = max_abs_t_residual = 0.0
    max_abs_q_equation_residual = max_abs_t_equation_residual = 0.0

    totals = defaultdict(lambda: {"count": 0, **{name: 0.0 for name in SCHEMAS["PROCESS_RATES"][1]}})
    event_counts = defaultdict(lambda: {
        "update_count": 0, "qrain_branch_count": 0, "raw_positive": 0, "raw_negative": 0,
        "raw_positive_zero": 0, "raw_negative_zero": 0, "qr_cap_count": 0,
        "sat_cap_count": 0, "process_positive": 0, "process_negative": 0,
        "process_positive_zero": 0, "process_negative_zero": 0,
    })
    event_columns = (
        "point_id", "corner", "weight", "source_file", "rank", "call_id", "itimestep", "hour", "loop", "j", "i", "k",
        "formula_prev", "formula_nrs", "formula_qrs", "formula_den", "formula_rh", "formula_n0r", "formula_fac_evap",
        "raw_prev", "raw_qrs", "raw_satdt", "raw_dtcld", "qr_cap_prev", "sat_cap_prev", "process_prev",
        "formula_prev_word_hex", "formula_nrs_word_hex", "formula_qrs_word_hex", "formula_den_word_hex",
        "formula_rh_word_hex", "formula_n0r_word_hex", "formula_fac_evap_word_hex", "raw_prev_word_hex",
        "raw_qrs_word_hex", "raw_satdt_word_hex", "raw_dtcld_word_hex", "qr_cap_prev_word_hex",
        "sat_cap_prev_word_hex", "process_prev_word_hex", "raw_class", "raw_to_process_delta",
        "formula_to_raw_delta", "raw_to_last_cap_delta", "last_cap_to_process_delta",
        "formula_line", "raw_line", "qr_cap_line", "sat_cap_line", "process_rates_line",
        "pre_update_line", "latent_input_line", "post_step_line",
    )
    with (samples_path.open("w", newline="", encoding="utf-8") as stream,
          event_path.open("w", newline="", encoding="utf-8") as event_stream,
          zero_path.open("w", newline="", encoding="utf-8") as zero_stream):
        writer = csv.DictWriter(stream, fieldnames=(
            "point_id", "corner", "weight", "source_file", "rank", "call_id", "itimestep", "hour", "loop", "j", "i", "k", "arm",
            "q_pre", "q_post", "t_pre", "t_post", "qr_pre", "qr_post", "nrs_pre", "nrs_post",
            "prevp", "dtcld", "xlwork2", "cpm", "q_expected", "q_residual",
            "q_equation_residual", "t_expected", "t_residual", "t_equation_residual",
            "formula_prev", "formula_nrs", "formula_qrs", "formula_den", "formula_rh", "formula_n0r", "formula_fac_evap",
            "raw_prev", "raw_qrs", "raw_satdt", "raw_dtcld", "qr_cap_prev", "sat_cap_prev",
            "formula_prev_word_hex", "formula_nrs_word_hex", "formula_qrs_word_hex", "formula_den_word_hex",
            "formula_rh_word_hex", "formula_n0r_word_hex", "formula_fac_evap_word_hex", "raw_prev_word_hex",
            "raw_qrs_word_hex", "raw_satdt_word_hex", "raw_dtcld_word_hex", "qr_cap_prev_word_hex", "sat_cap_prev_word_hex",
            "formula_line", "raw_line", "qr_cap_line", "sat_cap_line", "process_rates_line",
            "pre_update_line", "latent_input_line", "post_step_line",
        ))
        event_writer = csv.DictWriter(event_stream, fieldnames=event_columns)
        zero_writer = csv.DictWriter(zero_stream, fieldnames=event_columns)
        writer.writeheader()
        event_writer.writeheader()
        zero_writer.writeheader()
        for key, phases, phase_words, phase_lines, source_file in joined_updates(db):
            rates, before, latent, after = (phases[name] for name in UPDATE_PHASES)
            checks = update_checks(phases)
            rank, call_id, timestep, loop, j, i, k = key
            hour = hour_label(timestep, step_seconds)
            native_corners = corners.get((j, i), [])
            require(native_corners, f"process transaction key={key} is outside the frozen native-corner map")
            formula_fields = ("prevp", "nrs", "qrs", "den", "rh", "n0r", "fac_evap")
            raw_fields = ("prevp", "qrs", "satdt", "dtcld")
            early_values = {f"formula_{'prev' if name == 'prevp' else name}": optional_value(phases, "PREVP_FORMULA", name)
                            for name in formula_fields}
            early_values.update({f"raw_{'prev' if name == 'prevp' else name}": optional_value(phases, "PREVP_RAW", name)
                                 for name in raw_fields})
            early_values["qr_cap_prev"] = optional_value(phases, "PREVP_QR_CAP", "prevp")
            early_values["sat_cap_prev"] = optional_value(phases, "PREVP_SAT_CAP", "prevp")
            early_words = {f"formula_{'prev' if name == 'prevp' else name}_word_hex": optional_word(phase_words, "PREVP_FORMULA", name)
                           for name in formula_fields}
            early_words.update({f"raw_{'prev' if name == 'prevp' else name}_word_hex": optional_word(phase_words, "PREVP_RAW", name)
                                for name in raw_fields})
            early_words["qr_cap_prev_word_hex"] = optional_word(phase_words, "PREVP_QR_CAP", "prevp")
            early_words["sat_cap_prev_word_hex"] = optional_word(phase_words, "PREVP_SAT_CAP", "prevp")
            line_names = {"formula_line": "PREVP_FORMULA", "raw_line": "PREVP_RAW",
                          "qr_cap_line": "PREVP_QR_CAP", "sat_cap_line": "PREVP_SAT_CAP",
                          "process_rates_line": "PROCESS_RATES", "pre_update_line": "PRE_UPDATE",
                          "latent_input_line": "LATENT_INPUT", "post_step_line": "POST_STEP"}
            early_lines = {name: phase_lines[phase] for name, phase in line_names.items()}
            for corner in native_corners:
                row = {"point_id": corner["point_id"], "corner": corner["corner"],
                       "weight": corner["weight"], "source_file": source_file,
                       "rank": rank, "call_id": call_id,
                       "itimestep": timestep, "hour": hour, "loop": loop, "j": j, "i": i, "k": k,
                       "arm": arm, "q_pre": before["q"], "q_post": after["q"],
                       "t_pre": before["t"], "t_post": after["t"],
                       "qr_pre": before["qrs1"], "qr_post": after["qrs1"],
                       "nrs_pre": before["nrs1"], "nrs_post": after["nrs1"],
                       "prevp": rates["prevp"], "dtcld": before["dtcld"],
                       "xlwork2": latent["xlwork2"], "cpm": latent["cpm"], **checks, **early_lines,
                       **early_values, **early_words}
                writer.writerow(row)
                group = event_counts[(corner["point_id"], corner["corner"], k, hour)]
                group["update_count"] += 1
                if phases.get("PREVP_RAW") is not None:
                    formula = phases["PREVP_FORMULA"]
                    raw = phases["PREVP_RAW"]
                    raw_word = phase_words["PREVP_RAW"]["prevp"]
                    raw_class = zero_sign_class(raw["prevp"], raw_word)
                    last_cap = phases.get("PREVP_SAT_CAP") or phases.get("PREVP_QR_CAP")
                    event = {
                        "point_id": corner["point_id"], "corner": corner["corner"], "weight": corner["weight"],
                        "source_file": source_file, "rank": rank, "call_id": call_id,
                        "itimestep": timestep, "hour": hour,
                        "loop": loop, "j": j, "i": i, "k": k,
                        **early_values, **early_words, "process_prev": rates["prevp"],
                        "process_prev_word_hex": phase_words["PROCESS_RATES"]["prevp"],
                        **early_lines,
                        "raw_class": raw_class,
                        "formula_to_raw_delta": raw["prevp"] - formula["prevp"],
                        "raw_to_process_delta": rates["prevp"] - raw["prevp"],
                        "raw_to_last_cap_delta": None if last_cap is None else last_cap["prevp"] - raw["prevp"],
                        "last_cap_to_process_delta": None if last_cap is None else rates["prevp"] - last_cap["prevp"],
                    }
                    event_writer.writerow(event)
                    if raw["prevp"] == 0.0:
                        zero_writer.writerow(event)
                    group["qrain_branch_count"] += 1
                    group[f"raw_{raw_class}"] += 1
                    if "PREVP_QR_CAP" in phases:
                        group["qr_cap_count"] += 1
                    if "PREVP_SAT_CAP" in phases:
                        group["sat_cap_count"] += 1
                    process_class = zero_sign_class(rates["prevp"], phase_words["PROCESS_RATES"]["prevp"])
                    group[f"process_{process_class}"] += 1
                group = totals[(corner["point_id"], corner["corner"], k, hour)]
                group["count"] += 1
                for name in SCHEMAS["PROCESS_RATES"][1]:
                    group[name] += rates[name] * before["dtcld"]
            max_abs_q_residual = max(max_abs_q_residual, abs(checks["q_residual"]))
            max_abs_t_residual = max(max_abs_t_residual, abs(checks["t_residual"]))
            max_abs_q_equation_residual = max(max_abs_q_equation_residual,
                                              abs(checks["q_equation_residual"]))
            max_abs_t_equation_residual = max(max_abs_t_equation_residual,
                                              abs(checks["t_equation_residual"]))
            transaction_count += 1

    with totals_path.open("w", newline="", encoding="utf-8") as stream:
        columns = ("point_id", "corner", "k", "hour", "cell_step_count",
                   *SCHEMAS["PROCESS_RATES"][1])
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for (point_id, corner, k, hour), values in sorted(totals.items()):
            writer.writerow({"point_id": point_id, "corner": corner, "k": k, "hour": hour,
                             "cell_step_count": values["count"],
                             **{name: values[name] for name in SCHEMAS["PROCESS_RATES"][1]}})

    with event_counts_path.open("w", newline="", encoding="utf-8") as stream:
        count_fields = ("point_id", "corner", "k", "hour", "update_count", "qrain_branch_count",
                        "raw_positive", "raw_negative", "raw_positive_zero", "raw_negative_zero",
                        "qr_cap_count", "sat_cap_count", "process_positive", "process_negative",
                        "process_positive_zero", "process_negative_zero")
        writer = csv.DictWriter(stream, fieldnames=count_fields)
        writer.writeheader()
        for (point_id, corner, k, hour), values in sorted(event_counts.items()):
            writer.writerow({"point_id": point_id, "corner": corner, "k": k, "hour": hour, **values})

    with phase_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("phase", "key_json", "values_json", "raw_words_json", "source",
                         "file_ordinal", "line_number"))
        for phase, key_json, source, file_ordinal, line, values_json, raw_json in db.execute(
                "SELECT phase,key,source,file_ordinal,line_number,values_json,raw_json FROM records "
                "ORDER BY file_ordinal,line_number"):
            values, raw = json.loads(values_json), json.loads(raw_json)
            phase_counts[phase] += 1
            writer.writerow((phase, key_json, json.dumps(values, sort_keys=True, separators=(",", ":")),
                             json.dumps(raw, sort_keys=True, separators=(",", ":")), source,
                             file_ordinal, line))

    missing_or_extra = db.execute("""SELECT phase, COUNT(*) FROM records
        WHERE phase IN ('PROCESS_RATES','PRE_UPDATE','LATENT_INPUT','POST_STEP')
        GROUP BY phase ORDER BY phase""").fetchall()
    require(transaction_count > 0, "no complete process/update transactions found")
    observed_corners = {(point_id, corner) for point_id, corner, _, _ in totals}
    expected_corners = {(entry["point_id"], entry["corner"])
                        for entries in corners.values() for entry in entries}
    require(observed_corners == expected_corners,
            f"observed process corners differ from frozen map: missing={sorted(expected_corners - observed_corners)}, "
            f"extra={sorted(observed_corners - expected_corners)}")
    summary = {
        "status": "PASS_SCHEMA_AND_JOIN_VALIDATION",
        "arm": arm,
        "transaction_count": transaction_count,
        "phase_record_counts": dict(sorted(phase_counts.items())),
        "update_phase_record_counts": {phase: count for phase, count in missing_or_extra},
        "max_abs_q_residual": max_abs_q_residual,
        "max_abs_t_residual": max_abs_t_residual,
        "max_abs_q_equation_residual": max_abs_q_equation_residual,
        "max_abs_t_equation_residual": max_abs_t_equation_residual,
        "residual_interpretation": "unthresholded REAL32 source-order diagnostics only; pass status validates schemas and joins, not arithmetic closure",
        "claim_scope": "local q/T update diagnostics only; no full process budget, column budget, pooled score, or uncapped PREVP formula replay",
        "source_pins": source_pins,
        "outputs": {"cell_steps_csv": samples_path.name, "phase_records_csv": phase_path.name,
                    "point_hour_process_sums_csv": totals_path.name,
                    "prevp_phase_events_csv": event_path.name,
                    "zero_rate_events_csv": zero_path.name,
                    "prevp_phase_counts_csv": event_counts_path.name},
        "process_sum_scope": "sum(rate*dtcld) over observed timesteps and loops, kept separate by point, native corner, model level k, and hour; not a mass-column or area budget",
    }
    (output_dir / f"{arm.lower()}_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def analyze_gated_arm(paths: list[Path], output_dir: Path, arm: str, gate_path: Path,
                      gate: dict, cohort_path: Path, source_pins: list[dict],
                      scratch_dir: Path,
                      verified_trace_pins: list[dict] | None = None) -> dict:
    require(gate.get("case") == arm, f"{gate_path}: expected {arm} receipt")
    require(sha256_file(gate_path) == gate["_receipt_sha256"],
            f"{gate_path}: receipt changed since its status fields were read")
    if verified_trace_pins is None:
        _, trace_pins = validate_trace_pins(gate_path, gate, paths)
    else:
        trace_pins = verified_trace_pins
    corners = read_corner_map(cohort_path)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cp02-b1-process-", dir=scratch_dir) as temp_dir:
        db = open_database(Path(temp_dir) / "trace.sqlite")
        try:
            # Verify the trace bytes again after decoding to catch concurrent replacement.
            streamed_pins = load_trace(db, paths)
            require([pin["sha256"] for pin in streamed_pins] ==
                    [pin["sha256"] for pin in trace_pins], "trace changed between gate check and parse")
            require(sha256_file(gate_path) == gate["_receipt_sha256"],
                    f"{gate_path}: receipt changed while trace was parsed")
            pins = [*source_pins, {"path": str(gate_path), "sha256": gate["_receipt_sha256"]},
                    {"path": str(cohort_path), "sha256": sha256_file(cohort_path)}, *streamed_pins]
            return write_outputs(db, output_dir, arm, pins, corners,
                                 float(gate["time_step_seconds"]))
        finally:
            db.close()


def named_file_pin(value: str) -> dict:
    name, separator, path_text = value.partition("=")
    require(separator and name and path_text, f"invalid --source-pin {value!r}; expected NAME=PATH")
    path = Path(path_text)
    return {"name": name, "path": str(path), "sha256": sha256_file(path)}


def analyze_pair(old_paths: list[Path], fix_paths: list[Path], gate_paths: tuple[Path, Path],
                 cohort_path: Path, source_pin_values: list[str], scratch_dir: Path,
                 output_dir: Path) -> dict:
    require(not os.path.lexists(output_dir),
            f"output path already exists; refusing to overwrite: {output_dir}")
    require(output_dir.parent.is_dir(),
            f"output parent must already exist for same-filesystem staging: {output_dir.parent}")
    # Read both status gates before hashing or opening any native data.
    old_gate = read_prefix_receipt(gate_paths[0])
    fix_gate = read_prefix_receipt(gate_paths[1])
    require(old_gate["case"] == "OLD" and fix_gate["case"] == "FIX",
            "prefix receipt case identity does not match the requested OLD/FIX pair")
    require(old_gate["time_step_seconds"] == fix_gate["time_step_seconds"] and
            old_gate["times"] == fix_gate["times"],
            "OLD and FIX strict-prefix receipts differ in timestep or hourly history times")
    scratch_dir.mkdir(parents=True, exist_ok=True)
    require(scratch_dir.stat().st_dev == output_dir.parent.stat().st_dev,
            "--scratch and --out parent must share the same runtime-capacity filesystem")
    # Bind both arm inventories before parsing either trace.
    _, old_trace_pins = validate_trace_pins(gate_paths[0], old_gate, old_paths)
    _, fix_trace_pins = validate_trace_pins(gate_paths[1], fix_gate, fix_paths)
    source_pins = [named_file_pin(value) for value in source_pin_values]
    tool_path = Path(__file__).resolve()
    if not any(pin.get("path") == str(tool_path) for pin in source_pins):
        source_pins.append({"name": "analysis_tool", "path": str(tool_path),
                            "sha256": sha256_file(tool_path)})
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent) as temp:
        stage = Path(temp) / "result"
        stage.mkdir()
        old_summary = analyze_gated_arm(old_paths, stage / "OLD", "OLD", gate_paths[0], old_gate,
                                        cohort_path, source_pins, scratch_dir, old_trace_pins)
        fix_summary = analyze_gated_arm(fix_paths, stage / "FIX", "FIX", gate_paths[1], fix_gate,
                                        cohort_path, source_pins, scratch_dir, fix_trace_pins)
        summary = {"status": "PASS_BOTH_ARMS", "OLD": old_summary, "FIX": fix_summary,
                   "comparison_scope": "arms are summarized independently; no pooled score or cross-arm mean"}
        (stage / "pair_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        require(sha256_file(gate_paths[0]) == old_gate["_receipt_sha256"] and
                sha256_file(gate_paths[1]) == fix_gate["_receipt_sha256"],
                "prefix receipt changed during paired analysis")
        require(not os.path.lexists(output_dir),
                f"output path appeared during analysis; refusing to publish: {output_dir}")
        os.rename(stage, output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", nargs="+", type=Path, required=True)
    parser.add_argument("--fix", nargs="+", type=Path, required=True)
    parser.add_argument("--prefix-receipts", nargs=2, type=Path, required=True,
                        metavar=("OLD_JSON", "FIX_JSON"))
    parser.add_argument("--cohorts", type=Path, required=True,
                        help="frozen corners.csv with 1-based WRF global j/i")
    parser.add_argument("--source-pin", action="append", default=[], metavar="NAME=PATH",
                        help="record immutable source/receipt file hashes")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True,
                        help="database scratch directory; must share a filesystem with --out parent")
    args = parser.parse_args(argv)
    try:
        summary = analyze_pair(args.old, args.fix, tuple(args.prefix_receipts), args.cohorts,
                               args.source_pin, args.scratch, args.out)
    except (OSError, UnicodeError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
