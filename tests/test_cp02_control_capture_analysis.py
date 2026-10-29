import csv
import importlib.util
import struct
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/cp02_control_capture_analysis.py"
SPEC = importlib.util.spec_from_file_location("cp02_control_capture_analysis", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
CAPTURE_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/capture/hydro_capture.json.gz"
POINTS_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/capture/shadow_points.csv"
SELECTION_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/controls/capture_points.csv"


@pytest.fixture(scope="module")
def capture():
    return TOOL.INNER.read_capture(CAPTURE_PATH)


def test_controls_use_frozen_20_by_22_capture(capture):
    summary, profiles = TOOL.summarize(capture, POINTS_PATH, SELECTION_PATH)

    assert summary["status"] == "PASS_SCOPED_AVAILABLE_ENDPOINTS"
    assert summary["sample_count"] == 440
    assert summary["role_counts"]["lost_hit"] == 4
    assert summary["role_counts"]["retained_hit"] == 4
    assert summary["role_counts"]["removed_false_alarm"] == 4
    assert summary["role_counts"]["RN1_positive_reference_all_forecasts_below5mm"] == 4
    for role in ("payload_positive_rain_reflectivity_invalid_proxy", "payload_positive_snow_reflectivity_invalid_proxy"):
        assert summary["role_counts"][role] == 2
        assert summary["observed_counts_by_role"][role]["observed_post_true_levels"] == 0
        assert not any(summary["observed_counts_by_role"][role]["captured_local_levels"].values())
    assert summary["radar_status"]["diagnose_radar_cells"]["raw_bytes_le_hex"] == "14000000"
    assert summary["radar_status"]["publish_hydrometeor_candidate"]["raw_bytes_le_hex"] == "14000000"
    assert len(profiles) == 440


def test_role_swap_preserving_counts_is_rejected(capture, tmp_path):
    with SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    rows[0]["role"], rows[4]["role"] = rows[4]["role"], rows[0]["role"]
    path = tmp_path / "swapped.csv"
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="selection SHA-256"):
        TOOL.summarize(capture, POINTS_PATH, path)


def test_empty_and_duplicate_selections_are_rejected(tmp_path, monkeypatch):
    empty = tmp_path / "empty.csv"
    empty.write_text("point_id,role\n", encoding="utf-8")
    monkeypatch.setattr(TOOL, "EXPECTED_SELECTION_SHA256", hashlib.sha256(empty.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="expected 20"):
        TOOL.read_selection(empty)

    with SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    rows[1]["shadow_i_zero_based"] = rows[0]["shadow_i_zero_based"]
    rows[1]["shadow_j_zero_based"] = rows[0]["shadow_j_zero_based"]
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(TOOL, "EXPECTED_SELECTION_SHA256", hashlib.sha256(duplicate.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="duplicate shadow columns"):
        TOOL.read_selection(duplicate)


def test_capture_state_key_loss_is_rejected(capture):
    changed = dict(capture)
    changed["records"] = list(capture["records"])
    index = next(i for i, row in enumerate(changed["records"])
                 if row.get("stage") == "derive_entry_state_in" and row.get("call_number") == 1)
    state_record = dict(changed["records"][index])
    state_record["points"] = list(state_record["points"][:-1])
    changed["records"][index] = state_record
    with pytest.raises(ValueError, match="point|points|state"):
        TOOL.summarize(changed, POINTS_PATH, SELECTION_PATH)


def test_selected_point_coordinate_mismatch_is_rejected():
    meta = TOOL.read_selection(SELECTION_PATH)[0]
    key = (int(meta["shadow_i_zero_based"]) + 1, int(meta["shadow_j_zero_based"]) + 1, 1)
    profile = {"losthit_rank": meta["point_id"], "lat": str(float(meta["latitude"]) + 0.1),
               "lon": meta["longitude"]}
    background = {"background_rain": "0.0", "background_snow": "0.0"}
    state = {key: {"rain": {"raw_bytes_le_hex": "00000000"},
                   "snow": {"raw_bytes_le_hex": "00000000"}}}
    with pytest.raises(ValueError, match="coordinates"):
        TOOL.validate_selected_row(profile, background, meta, key, state)


def test_selected_point_id_mismatch_is_rejected():
    meta = TOOL.read_selection(SELECTION_PATH)[0]
    key = (int(meta["shadow_i_zero_based"]) + 1, int(meta["shadow_j_zero_based"]) + 1, 1)
    profile = {"losthit_rank": "P99", "lat": meta["latitude"], "lon": meta["longitude"]}
    background = {"background_rain": "0.0", "background_snow": "0.0"}
    state = {key: {"rain": {"raw_bytes_le_hex": "00000000"},
                   "snow": {"raw_bytes_le_hex": "00000000"}}}
    with pytest.raises(ValueError, match="point ID"):
        TOOL.validate_selected_row(profile, background, meta, key, state)


def test_background_to_captured_input_raw32_mismatch_is_rejected():
    meta = TOOL.read_selection(SELECTION_PATH)[0]
    key = (int(meta["shadow_i_zero_based"]) + 1, int(meta["shadow_j_zero_based"]) + 1, 1)
    profile = {"losthit_rank": meta["point_id"], "lat": meta["latitude"], "lon": meta["longitude"]}
    background = {"background_rain": "0.001", "background_snow": "0.0"}
    state = {key: {"rain": {"raw_bytes_le_hex": struct.pack("<f", 0.0).hex()},
                   "snow": {"raw_bytes_le_hex": struct.pack("<f", 0.0).hex()}}}
    with pytest.raises(ValueError, match="background"):
        TOOL.validate_selected_row(profile, background, meta, key, state)
