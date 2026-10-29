import csv
import gzip
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/cp02_kdm6_controls.py"
SPEC = importlib.util.spec_from_file_location("cp02_kdm6_controls", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
CAPTURE_ROOT = EVIDENCE / "captures"
SELECTION = EVIDENCE / "selection.json"


def rank_capture(arm="HYDRO", rank=1, call=1):
    path = next((CAPTURE_ROOT / arm).glob(f"capture_rank{rank}_pid*.json.gz"))
    capture = json.loads(gzip.decompress(path.read_bytes()))
    return capture, path, capture["calls"][call - 1]["entry"]


def rank_receipt(arm, rank):
    receipt = json.loads((CAPTURE_ROOT / arm / "receipt.json").read_text())
    return next(row for row in receipt["rank_status"] if row["rank"] == rank)


def test_frozen_selection_is_624_points_and_16_horizontal_columns():
    selected = TOOL.selection_map(SELECTION)

    assert len(selected) == 624
    assert len({(i, j) for i, j, _ in selected}) == 16
    assert {k for _, _, k in selected} == set(range(1, 40))


def test_actual_three_arm_capture_cli_and_tables(tmp_path):
    output = tmp_path / "analysis"
    report = TOOL.analyze(CAPTURE_ROOT, output)

    assert report["status"] == "PASS_SCOPED_CAPTURE_COMPLETE"
    assert {arm["arm"] for arm in report["arms"]} == set(TOOL.ARMS)
    for arm in report["arms"]:
        assert arm["rank_count"] == 8
        assert arm["calls_per_rank"] == 2
        assert arm["selected_3d_keys_per_endpoint"] == 624
        assert arm["deduplicated_horizontal_columns"] == 16
        assert arm["event_sequence_complete"]
        assert len(arm["observed_rank_steps_and_dt"]) == 8
    with (output / "per_arm_call.csv").open(newline="", encoding="utf-8") as source:
        calls = list(csv.DictReader(source))
    assert len(calls) == 6
    assert all(row["entry_keys_owned_once"] == "624" and row["return_keys_owned_once"] == "624"
               for row in calls)
    with (output / "field_deltas.csv").open(newline="", encoding="utf-8") as source:
        deltas = list(csv.DictReader(source))
    assert deltas
    assert {int(row["sample_count"]) for row in deltas if row["field"] in TOOL.ARRAY_2D} == {16}
    with (output / "mass_aux_ratios.csv").open(newline="", encoding="utf-8") as source:
        pairs = list(csv.DictReader(source))
    assert len(pairs) == 36
    assert not any(row["aux_field"] == "bg" for row in pairs)
    assert all(row["source_label_limit"].startswith("Candidate") for row in pairs)
    pair = next(row for row in pairs if row["arm"] == "OFF" and row["call_ordinal"] == "1" and
                row["endpoint"] == "entry" and row["pair"] == "cloud_water")
    assert pair["mass_positive_count"] == "440"
    assert pair["mass_positive_aux_zero_count"] == "440"
    with (output / "selected_profiles.csv").open(newline="", encoding="utf-8") as source:
        profiles = list(csv.DictReader(source))
    assert len(profiles) == 3 * 2 * 2 * 624
    assert {row["endpoint"] for row in profiles} == {"entry", "return"}


def test_pointer_vector_is_bound_to_raw_stack_bytes():
    _, _, entry = rank_capture()
    entry = json.loads(json.dumps(entry))
    entry["arguments"][6]["pointer_hex"] = "0x1"

    with pytest.raises(ValueError, match="raw stack pointer mismatch"):
        TOOL.validate_bounds_and_arguments(entry, "HYDRO", 1, 1)


def test_bool_call_ordinal_and_bool_timestep_are_rejected():
    _, _, entry = rank_capture()
    entry = json.loads(json.dumps(entry))
    entry["call_number"] = True
    with pytest.raises(ValueError, match="call ordinal"):
        TOOL.validate_bounds_and_arguments(entry, "HYDRO", 1, 1)

    _, _, entry = rank_capture()
    entry = json.loads(json.dumps(entry))
    entry["scalar_raw4"]["itimestep"]["decoded"] = True
    entry["observed_itimestep"] = True
    with pytest.raises(ValueError, match="decoded scalar has wrong type"):
        TOOL.validate_bounds_and_arguments(entry, "HYDRO", 1, 1)


def test_missing_or_misordered_call_is_rejected(monkeypatch):
    capture, path, _ = rank_capture("HYDRO", 1)
    selected = TOOL.selection_map(SELECTION)
    capture["calls"].reverse()
    monkeypatch.setattr(TOOL, "read_json", lambda _: capture)
    with pytest.raises(ValueError, match="call ordinal"):
        TOOL.load_capture(path, capture["pid"], "HYDRO", 1, selected, rank_receipt("HYDRO", 1))


def test_sample_owned_by_wrong_tile_is_rejected(monkeypatch):
    capture, path, _ = rank_capture("HYDRO", 1)
    selected = TOOL.selection_map(SELECTION)
    sample = next(row for row in capture["calls"][0]["entry"]["samples"]
                  if row["status"] == "owned_tile")
    sample["status"] = "halo_or_not_owned"
    monkeypatch.setattr(TOOL, "read_json", lambda _: capture)
    with pytest.raises(ValueError, match="ownership contradicts"):
        TOOL.load_capture(path, capture["pid"], "HYDRO", 1, selected, rank_receipt("HYDRO", 1))


def test_nonfinite_core_sample_is_rejected_at_capture_boundary(monkeypatch):
    capture, path, _ = rank_capture("HYDRO", 1)
    selected = TOOL.selection_map(SELECTION)
    sample = next(row for row in capture["calls"][0]["entry"]["samples"]
                  if row["status"] == "owned_tile")
    sample["values"]["qc"].update({"raw_hex": "0000c07f", "value_f32": None, "finite": False})
    monkeypatch.setattr(TOOL, "read_json", lambda _: capture)
    with pytest.raises(ValueError, match="nonfinite core/active"):
        TOOL.load_capture(path, capture["pid"], "HYDRO", 1, selected, rank_receipt("HYDRO", 1))


def test_nonfinite_core_is_rejected_but_inactive_optional_null_is_retained():
    nan_record = {"raw_hex": "0000c07f", "value_f32": None, "finite": False}
    with pytest.raises(ValueError, match="nonfinite core/active"):
        TOOL.real4(nan_record, "qc")
    value, raw = TOOL.real4(nan_record, "inactive refl", allow_nonfinite=True)
    assert value != value
    assert raw.hex() == "0000c07f"


def test_timeout_receipt_fails_without_creating_pass_output(tmp_path):
    captures = tmp_path / "captures"
    (captures / "OFF").mkdir(parents=True)
    receipt = json.loads((CAPTURE_ROOT / "OFF/receipt.json").read_text())
    receipt["launcher_exit"] = 124
    (captures / "OFF/receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    output = tmp_path / "analysis"

    with pytest.raises(ValueError, match="timeout or forced-kill"):
        TOOL.analyze(captures, output)
    assert not output.exists()


def test_manifest_hash_mismatch_fails_before_output(tmp_path):
    captures = tmp_path / "captures"
    (captures / "OFF").mkdir(parents=True)
    receipt = json.loads((CAPTURE_ROOT / "OFF/receipt.json").read_text())
    receipt["copy_manifest_sha256"] = "0" * 64
    (captures / "OFF/receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    output = tmp_path / "analysis"

    with pytest.raises(ValueError, match="copy_manifest_sha256 mismatch"):
        TOOL.analyze(captures, output)
    assert not output.exists()

