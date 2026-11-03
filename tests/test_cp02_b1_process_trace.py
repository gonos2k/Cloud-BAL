import csv
import gzip
import hashlib
import importlib.util
import json
import struct
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/cp02_b1_process_trace.py"
SPEC = importlib.util.spec_from_file_location("cp02_b1_process_trace", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def word32(value):
    return struct.unpack("<i", struct.pack("<f", value))[0]


def record(phase, key, values):
    return " ".join((phase, *(str(value) for value in key), *(str(word32(value)) for value in values)))


def process_transaction(key, final_prevp=-1.0e-7):
    entry = [0.001, 280.0, 0.8, 0.0, 0.0, 0.001, 0.0, 0.0,
             0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0]
    rates = [0.0] * 16
    rates[2] = final_prevp
    pre = [*entry, -1.0e-7, 20.0]
    latent = [-1.0e-7, 0.1, 1004.0, 20.0, 2.5e6, 3.34e5]
    pre[-2] = -final_prevp
    latent[0] = -final_prevp
    post = list(entry)
    post[0] = TOOL.f32(entry[0] + TOOL.f32(pre[-2] * pre[-1]))
    post[1] = TOOL.f32(entry[1] - TOOL.f32(TOOL.f32(latent[1] / latent[2]) * latent[3]))
    return [record("PROCESS_RATES", key, rates), record("PRE_UPDATE", key, pre),
            record("LATENT_INPUT", key, latent), record("POST_STEP", key, post)]


def formula_record(key, prevp, n0r=1.23456789012345e13):
    key_text = " ".join(str(value) for value in key)
    fields = [prevp, 100.0, 0.001, 0.8, 0.9]
    words = [str(word32(value)) for value in fields]
    n0r_word = struct.unpack("<q", struct.pack("<d", n0r))[0]
    return f"PREVP_FORMULA {key_text} {' '.join(words)} {n0r_word} {word32(0.0)}"


def make_corners(path):
    rows = [
        {"point_id": "P01", "corner": f"0{i}", "wrf_j_1based": str(10 + i),
         "wrf_i_1based": str(20 + i), "weight": "0.25"}
        for i in range(4)
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return rows


def make_gate(path, trace, case="OLD", hours=(12, 13, 14)):
    raw = trace.read_bytes()
    gate = {"receipt_schema_version": 1, "case": case,
            "status": "PASS_FULL_PREFIX", "full_prefix_pass": True,
            "time_step_seconds": 20, "times_utc_hours": list(hours),
            "trace_files": [{"path": trace.name, "sha256": hashlib.sha256(raw).hexdigest()}]}
    path.write_text(json.dumps(gate), encoding="utf-8")
    return TOOL.read_prefix_receipt(path)


def fixture_trace(path, transaction_groups=None):
    rows = []
    for number in range(4):
        key = (0, 7, 1, 1, 10 + number, 20 + number, 1)
        rows.extend(process_transaction(key))
    if transaction_groups is not None:
        rows = transaction_groups(rows)
    path.write_text("\n".join(rows) + "\n", encoding="ascii")
    return path


def test_decode_keeps_real64_n0r_word():
    values = [0.0, 1.0, 0.001, 0.8, 0.9, 2.5e12, 1.0]
    tokens = [str(word32(value)) for value in values]
    n0r = 1.23456789012345e13
    n0r_word = struct.unpack("<q", struct.pack("<d", n0r))[0]
    tokens[5] = str(n0r_word)
    parsed = TOOL.parse_record("PREVP_FORMULA 0 7 1 1 10 20 1 " + " ".join(tokens), "fixture", 1)
    assert parsed["values"]["n0r"] == n0r
    assert parsed["raw"]["n0r"] == struct.pack("<d", n0r).hex()


def test_gated_gzip_stream_emits_per_corner_hour_and_source_order_checks(tmp_path):
    plain = fixture_trace(tmp_path / "rank0.bits")
    compressed = tmp_path / "rank0.bits.gz"
    with gzip.open(compressed, "wb") as stream:
        stream.write(plain.read_bytes())
    gate_path = tmp_path / "gate.json"
    gate = make_gate(gate_path, compressed)
    cohorts = tmp_path / "corners.csv"
    make_corners(cohorts)

    summary = TOOL.analyze_gated_arm([compressed], tmp_path / "out", "OLD", gate_path,
                                     gate, cohorts, [], tmp_path)
    assert summary["status"] == "PASS_SCHEMA_AND_JOIN_VALIDATION"
    assert summary["transaction_count"] == 4
    assert summary["phase_record_counts"]["POST_STEP"] == 4
    assert summary["residual_interpretation"].startswith("unthresholded")
    assert set(summary["phase_record_counts"]) == set(TOOL.SCHEMAS)
    with (tmp_path / "out/old_point_hour_process_sums.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    assert {row["hour"] for row in rows} == {"1"}
    assert all(row["cell_step_count"] == "1" for row in rows)


def test_optional_prevp_phases_keep_signed_zero_and_absence_distinct(tmp_path):
    rows = []
    raw_signs = (-0.0, 0.0, -1.0e-5, 1.0e-5)
    final_rates = (-1.0e-7, 0.0, 0.0, 0.0)
    for number, (raw_value, final_rate) in enumerate(zip(raw_signs, final_rates)):
        key = (0, 7, 1, 1, 10 + number, 20 + number, 1)
        rows.append(formula_record(key, -1.0e-5 if number in (0, 2) else 1.0e-5))
        rows.append(record("PREVP_RAW", key, [raw_value, 0.001, 0.0, 20.0]))
        if number == 2:
            rows.append(record("PREVP_QR_CAP", key, [-2.0e-6]))
            rows.append(record("PREVP_SAT_CAP", key, [0.0]))
        elif number == 3:
            rows.append(record("PREVP_SAT_CAP", key, [0.0]))
        rows.extend(process_transaction(key, final_rate))
    trace = tmp_path / "events.bits"
    trace.write_text("\n".join(rows) + "\n", encoding="ascii")
    gate_path = tmp_path / "events_gate.json"
    gate = make_gate(gate_path, trace)
    corners = tmp_path / "corners.csv"
    make_corners(corners)
    TOOL.analyze_gated_arm([trace], tmp_path / "out", "OLD", gate_path, gate,
                           corners, [], tmp_path)

    with (tmp_path / "out/old_cell_steps.csv").open(newline="") as stream:
        cell_rows = list(csv.DictReader(stream))
    assert len(cell_rows) == 4
    assert cell_rows[0]["raw_prev"] == "-0.0"
    assert cell_rows[0]["raw_prev_word_hex"] == "00000080"
    assert cell_rows[1]["raw_prev"] == "0.0"
    assert cell_rows[1]["raw_prev_word_hex"] == "00000000"
    assert float(cell_rows[2]["qr_cap_prev"]) == pytest.approx(-2.0e-6)
    assert cell_rows[2]["sat_cap_prev"] == "0.0"
    with (tmp_path / "out/old_zero_rate_events.csv").open(newline="") as stream:
        zeros = list(csv.DictReader(stream))
    assert [row["raw_class"] for row in zeros] == ["negative_zero", "positive_zero"]
    with (tmp_path / "out/old_prevp_phase_counts.csv").open(newline="") as stream:
        count_rows = list(csv.DictReader(stream))
    assert len(count_rows) == 4
    assert {row["qrain_branch_count"] for row in count_rows} == {"1"}


def test_pair_failure_in_second_arm_publishes_nothing(tmp_path):
    old_trace = fixture_trace(tmp_path / "old.bits")
    fix_trace = tmp_path / "fix.bits"
    fix_trace.write_text("UNRECOGNIZED_PHASE 0 1\n", encoding="ascii")
    old_gate, fix_gate = tmp_path / "old_gate.json", tmp_path / "fix_gate.json"
    make_gate(old_gate, old_trace)
    make_gate(fix_gate, fix_trace, case="FIX")
    cohorts = tmp_path / "corners.csv"
    make_corners(cohorts)
    output = tmp_path / "final"

    with pytest.raises(ValueError, match="unrecognized trace record"):
        TOOL.analyze_pair([old_trace], [fix_trace], (old_gate, fix_gate), cohorts, [],
                          tmp_path / "scratch", output)
    assert not output.exists()
    assert not list(tmp_path.glob(".final.stage-*"))


def test_existing_output_is_preserved_without_analysis(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_text("keep", encoding="utf-8")
    invalid_gate = tmp_path / "invalid_gate.json"
    invalid_gate.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="output path already exists"):
        TOOL.analyze_pair([], [], (invalid_gate, invalid_gate), tmp_path / "missing.csv", [],
                          tmp_path / "scratch", output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_full_prefix_gate_rejected_before_trace_open(tmp_path):
    gate = tmp_path / "not_passed.json"
    gate.write_text(json.dumps({"receipt_schema_version": 1, "case": "OLD", "status": "RUNNING",
                                "full_prefix_pass": False, "time_step_seconds": 20,
                                "times_utc_hours": [12, 13, 14],
                                "trace_files": [{"path": "missing", "sha256": "0"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="full-prefix validation"):
        TOOL.read_prefix_receipt(gate)


def test_bad_gate_schema_and_wrong_hour_order_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    gate = {"receipt_schema_version": 1, "case": "OLD", "status": "PASS_FULL_PREFIX",
            "full_prefix_pass": True, "time_step_seconds": 20,
            "times_utc_hours": [12, 14, 13], "trace_files": [{"path": "unused", "sha256": "0"}]}
    path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(ValueError, match="ordered hours"):
        TOOL.read_prefix_receipt(path)
    gate["receipt_schema_version"] = 2
    gate["times_utc_hours"] = [12, 13, 14]
    path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        TOOL.read_prefix_receipt(path)


def test_truncated_phase_scalar_count_is_rejected(tmp_path):
    path = tmp_path / "bad.bits"
    path.write_text("PROCESS_RATES 0 7 1 1 10 20 1 0 0\n", encoding="ascii")
    db = TOOL.open_database(tmp_path / "db.sqlite")
    try:
        with pytest.raises(ValueError, match="truncated wrapped"):
            TOOL.load_trace(db, [path])
    finally:
        db.close()


def test_overlong_phase_scalar_count_is_rejected(tmp_path):
    path = tmp_path / "overlong.bits"
    path.write_text("PROCESS_RATES " + " ".join(["0"] * 24) + "\n", encoding="ascii")
    db = TOOL.open_database(tmp_path / "overlong.sqlite")
    try:
        with pytest.raises(ValueError, match="wrapped record has"):
            TOOL.load_trace(db, [path])
    finally:
        db.close()


def test_unrecognized_phase_is_not_silently_skipped(tmp_path):
    path = tmp_path / "unknown.bits"
    path.write_text("SOME_NEW_PHASE 0 1 2\n", encoding="ascii")
    db = TOOL.open_database(tmp_path / "db.sqlite")
    try:
        with pytest.raises(ValueError, match="unrecognized trace record"):
            TOOL.load_trace(db, [path])
    finally:
        db.close()


def test_wrapped_fortran_record_is_streamed_and_truncation_fails():
    key = (0, 7, 1, 1, 10, 20, 1)
    line = process_transaction(key)[0]
    tokens = line.split()
    wrapped = "\n  ".join((" ".join(tokens[:11]), " ".join(tokens[11:])))
    parsed = list(TOOL.iter_fortran_records(wrapped.splitlines(), "fixture"))
    assert len(parsed) == 1 and parsed[0]["phase"] == "PROCESS_RATES"
    with pytest.raises(ValueError, match="truncated wrapped"):
        list(TOOL.iter_fortran_records(wrapped.splitlines()[:1], "fixture"))


def test_duplicate_phase_key_is_rejected(tmp_path):
    path = fixture_trace(tmp_path / "duplicate.bits",
                         lambda rows: [*rows, rows[0]])
    db = TOOL.open_database(tmp_path / "db.sqlite")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            TOOL.load_trace(db, [path])
    finally:
        db.close()


def test_missing_and_reordered_update_phases_are_rejected(tmp_path):
    original = fixture_trace(tmp_path / "good.bits")
    rows = original.read_text(encoding="ascii").splitlines()

    missing = tmp_path / "missing.bits"
    missing.write_text("\n".join(row for row in rows if not row.startswith("LATENT_INPUT ")) + "\n",
                       encoding="ascii")
    db = TOOL.open_database(tmp_path / "missing.sqlite")
    try:
        TOOL.load_trace(db, [missing])
        with pytest.raises(ValueError, match="incomplete update transaction"):
            list(TOOL.joined_updates(db))
    finally:
        db.close()


def test_update_transaction_may_not_span_trace_files(tmp_path):
    key = (0, 7, 1, 1, 10, 20, 1)
    rows = process_transaction(key)
    first, second = tmp_path / "rank0_a.bits", tmp_path / "rank0_b.bits"
    first.write_text("\n".join(rows[:2]) + "\n", encoding="ascii")
    second.write_text("\n".join(rows[2:]) + "\n", encoding="ascii")
    db = TOOL.open_database(tmp_path / "split.sqlite")
    try:
        TOOL.load_trace(db, [first, second])
        with pytest.raises(ValueError, match="spans source files"):
            list(TOOL.joined_updates(db))
    finally:
        db.close()

    reordered = tmp_path / "reordered.bits"
    rowset = list(rows)
    rowset[1], rowset[3] = rowset[3], rowset[1]
    reordered.write_text("\n".join(rowset) + "\n", encoding="ascii")
    db = TOOL.open_database(tmp_path / "reordered.sqlite")
    try:
        TOOL.load_trace(db, [reordered])
        with pytest.raises(ValueError, match="reordered update transaction"):
            list(TOOL.joined_updates(db))
    finally:
        db.close()
