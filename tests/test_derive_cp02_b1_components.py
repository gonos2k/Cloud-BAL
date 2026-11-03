import csv
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/derive_cp02_b1_components.py"
SPEC = importlib.util.spec_from_file_location("derive_cp02_b1_components", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def sha_size(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def key_values(timestep):
    return [0, 7, timestep, 1, 10, 20, 1]


def make_inputs(tmp_path, omit_latent=False, duplicate_latent=False, duplicate_cell=False):
    analysis = tmp_path / "analysis"
    old_dir, fix_dir = analysis / "OLD", analysis / "FIX"
    old_dir.mkdir(parents=True)
    fix_dir.mkdir()
    cell_fields = (
        "point_id", "corner", "weight", "source_file", "rank", "call_id", "itimestep", "hour", "loop", "j", "i", "k",
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
    )
    phase_fields = ("phase", "key_json", "values_json", "raw_words_json", "source", "file_ordinal", "line_number")
    outputs = []
    for arm, directory in (("OLD", old_dir), ("FIX", fix_dir)):
        cell_path = directory / f"{arm.lower()}_cell_steps.csv"
        phase_path = directory / f"{arm.lower()}_phase_records.csv"
        rows, phases = [], []
        for timestep in (1, 2):
            key = key_values(timestep)
            row = {name: "" for name in cell_fields}
            row.update({
                "point_id": "P01", "corner": "00", "weight": "1.0", "source_file": "rank3.bits",
                "rank": "0", "call_id": "7", "itimestep": str(timestep), "hour": "1", "loop": "1",
                "j": "10", "i": "20", "k": "1", "q_pre": "0.001", "q_post": "0.0009",
                "t_pre": "280.0", "t_post": "280.5", "qr_pre": "0.01", "qr_post": "0.0101",
                "nrs_pre": "100", "nrs_post": "101", "prevp": "0.00001", "dtcld": "20",
                "xlwork2": "-25", "cpm": "1000", "q_expected": "0.0009", "q_residual": "0",
                "q_equation_residual": "0", "t_expected": "280.5", "t_residual": "0",
                "t_equation_residual": "0", "raw_prev": "-0.0", "raw_prev_word_hex": "00000080",
                "qr_cap_prev": "", "sat_cap_prev": "-0.000001",
            })
            rows.append(row)
            values = {"work2": -0.00001, "xlwork2": -25.0, "cpm": 1000.0,
                      "dtcld": 20.0, "xl": 2500000.0, "xlf": 334000.0}
            phases.append({"phase": "LATENT_INPUT", "key_json": json.dumps(key),
                           "values_json": json.dumps(values), "raw_words_json": "{}",
                           "source": "rank3.bits", "file_ordinal": "0", "line_number": str(timestep)})
        if duplicate_cell:
            rows.append(dict(rows[0]))
        if duplicate_latent:
            phases.append(dict(phases[0]))
        if omit_latent:
            phases = phases[:1]
        with cell_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=cell_fields)
            writer.writeheader()
            writer.writerows(rows)
        with phase_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=phase_fields)
            writer.writeheader()
            writer.writerows(phases)
        outputs.extend((cell_path, phase_path))

    corners = tmp_path / "corners.csv"
    with corners.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("point_id", "corner", "weight", "diagnostic_group"))
        writer.writeheader()
        writer.writerow({"point_id": "P01", "corner": "00", "weight": "1.0", "diagnostic_group": "weak"})
    pins = [{"path": str(path), "sha256": sha_size(path)[0], "bytes": sha_size(path)[1]}
            for path in outputs]
    run_receipt = tmp_path / "run_receipt.json"
    run_receipt.write_text(json.dumps({"status": "PASS_BOTH_ARMS", "analysis_outputs": pins}), encoding="utf-8")
    return analysis, run_receipt, corners


def test_derives_time_integrals_and_signed_zero_caps_by_arm_corner_level_hour(tmp_path):
    analysis, run_receipt, corners = make_inputs(tmp_path)
    output = tmp_path / "integrated.csv"
    receipt = tmp_path / "receipt.json"

    result = TOOL.derive(analysis, run_receipt, corners, output, receipt)

    assert result["status"] == "PASS_KEYED_LATENT_COMPONENT_DERIVATION"
    assert result["groups"] == 2
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["arm"] for row in rows] == ["FIX", "OLD"]
    for row in rows:
        assert row["point_id"] == "P01"
        assert row["diagnostic_group"] == "weak"
        assert row["corner"] == "00" and row["k"] == "1" and row["hour"] == "1"
        assert row["cell_step_count"] == "2"
        assert row["zero_raw_negative_zero_count"] == "2"
        assert row["zero_raw_sat_cap_present_count"] == "2"
        assert row["zero_raw_sat_cap_negative_count"] == "2"
        assert float(row["integrated_prevp_rate_dt"]) == pytest.approx(0.0004)
        assert float(row["delta_qv_prevp"]) == pytest.approx(-0.0004)
        assert float(row["delta_qr_prevp"]) == pytest.approx(0.0004)
        assert float(row["delta_t_prevp"]) == pytest.approx(1.0)
        assert float(row["delta_t_latent_total"]) == pytest.approx(1.0)
        assert float(row["delta_qv_state"]) == pytest.approx(-0.0002)


def test_missing_latent_input_key_fails_closed(tmp_path):
    analysis, run_receipt, corners = make_inputs(tmp_path, omit_latent=True)
    with pytest.raises(ValueError, match="missing key-matched LATENT_INPUT"):
        TOOL.derive(analysis, run_receipt, corners, tmp_path / "out.csv", tmp_path / "receipt.json")


def test_duplicate_latent_or_cell_step_key_fails_closed(tmp_path):
    analysis, run_receipt, corners = make_inputs(tmp_path, duplicate_latent=True)
    with pytest.raises(ValueError, match="duplicate LATENT_INPUT key"):
        TOOL.derive(analysis, run_receipt, corners, tmp_path / "out.csv", tmp_path / "receipt.json")

    analysis, run_receipt, corners = make_inputs(tmp_path / "cells", duplicate_cell=True)
    with pytest.raises(ValueError, match="duplicate cell-step identity"):
        TOOL.derive(analysis, run_receipt, corners, tmp_path / "out2.csv", tmp_path / "receipt2.json")
