"""Regression checks for the archived CP02 boundary event contract."""

import gzip
import json
from pathlib import Path

import pytest

from docs.evidence.cp02_call_boundary_20261028 import analyze_boundaries as analyzer


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/cp02_call_boundary_20261028"
CAPTURES = {
    "HYDRO": EVIDENCE / "hydro_capture.json.gz",
    "LIQUID_RADAR_RH1": EVIDENCE / "liquid_capture.json.gz",
}


def read_capture(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


@pytest.mark.parametrize("arm", ["HYDRO", "LIQUID_RADAR_RH1"])
def test_archived_capture_has_expected_events(arm):
    capture = analyzer.validate_capture(CAPTURES[arm], arm)
    indexed = analyzer.index_records(capture)

    assert set(indexed) == analyzer.STAGES
    assert set(indexed["pipeline_entry_state_in"]) == {("primary", 1), ("replay", 2)}
    assert set(indexed["pipeline_return_candidate_out"]) == {("primary", 1), ("replay", 2)}
    assert set(indexed["derive_entry_state_in"]) == analyzer.DERIVE_CALLS[arm]
    assert set(indexed["derive_return_state_out"]) == analyzer.DERIVE_CALLS[arm]


def assert_capture_rejected(capture, arm, message, tmp_path):
    path = tmp_path / "mutated-capture.json"
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        analyzer.validate_capture(path, arm)


def test_unknown_renamed_stage_is_rejected(tmp_path):
    capture = read_capture(CAPTURES["HYDRO"])
    declared_counts = capture["counts"].copy()
    record_count = len(capture["records"])
    record = next(
        event for event in capture["records"]
        if event["stage"] == "derive_entry_state_in" and event["call_number"] == 1
    )
    record["stage"] = "unrecognized_derive_entry_state_in"
    assert capture["counts"] == declared_counts
    assert len(capture["records"]) == record_count

    assert_capture_rejected(capture, "HYDRO", "exactly four known event stages", tmp_path)
    with pytest.raises(ValueError, match="exactly four known event stages"):
        analyzer.index_records(capture)


def test_wrong_role_is_rejected():
    capture = read_capture(CAPTURES["HYDRO"])
    record = next(
        event for event in capture["records"]
        if event["stage"] == "derive_entry_state_in" and event["call_number"] == 2
    )
    record["stack"] = [frame for frame in record["stack"] if "pipeline_result_replays" not in frame]

    with pytest.raises(ValueError, match="derive_entry_state_in role/call keys"):
        analyzer.index_records(capture)


def test_orphaned_return_is_rejected():
    capture = read_capture(CAPTURES["HYDRO"])
    record = next(
        event for event in capture["records"]
        if event["stage"] == "derive_return_state_out" and event["call_number"] == 2
    )
    record["call_number"] = 99

    with pytest.raises(ValueError, match="derive_return_state_out role/call keys"):
        analyzer.index_records(capture)


def swap_primary_derive_calls(capture, stages):
    for stage in stages:
        for event in capture["records"]:
            if event["stage"] == stage and event["call_number"] in (1, 2):
                event["call_number"] = 3 - event["call_number"]


def test_same_role_derive_call_permutation_is_rejected():
    capture = read_capture(CAPTURES["LIQUID_RADAR_RH1"])
    swap_primary_derive_calls(
        capture, ("derive_entry_state_in", "derive_return_state_out")
    )

    with pytest.raises(ValueError, match="event order differs from expected call chronology"):
        analyzer.index_records(capture)


def test_derive_entry_return_misassignment_is_rejected():
    capture = read_capture(CAPTURES["LIQUID_RADAR_RH1"])
    swap_primary_derive_calls(capture, ("derive_entry_state_in",))

    with pytest.raises(ValueError, match="event order differs from expected call chronology"):
        analyzer.index_records(capture)


def test_observed_stage_count_must_match_declared_count(tmp_path):
    capture = read_capture(CAPTURES["HYDRO"])
    declared_counts = capture["counts"].copy()
    record_count = len(capture["records"])
    record = next(
        event for event in capture["records"]
        if event["stage"] == "derive_return_state_out" and event["call_number"] == 1
    )
    record["stage"] = "derive_entry_state_in"
    assert capture["counts"] == declared_counts
    assert len(capture["records"]) == record_count

    assert_capture_rejected(
        capture, "HYDRO", "observed stage counts differ from declared counts", tmp_path
    )
