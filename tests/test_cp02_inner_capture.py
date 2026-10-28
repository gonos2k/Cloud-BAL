import copy
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "docs/evidence/cp02_inner_capture_20261028/analyze_inner.py"
SPEC = importlib.util.spec_from_file_location(
    "analyze_inner", SCRIPT
)
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)
EVIDENCE = ROOT / "docs/evidence/cp02_inner_capture_20261028"
OUTER = ROOT / "docs/evidence/cp02_call_boundary_20261028"


@pytest.fixture(scope="module")
def hydro_receipt():
    return analyzer.read_capture(EVIDENCE / "hydro_capture.json.gz")


@pytest.fixture(scope="module")
def liquid_receipt():
    return analyzer.read_capture(EVIDENCE / "liquid_capture.json.gz")


def test_archived_hydro_receipt_analyzes_end_to_end():
    report = analyzer.analyze(EVIDENCE / "hydro_capture.json.gz", "HYDRO", OUTER / "hydro_capture.json.gz")
    assert report["status"] == "SCOPED_PASS"
    assert report["primary_writer_outer_state8_raw32_bitwise_differences"] == {
        field: 0 for field in analyzer.FIELDS
    }
    assert report["stages"]["diagnose_radar_cells"]["changed_samples"] == {
        "rain": 154, "snow": 36, "graupel": 0
    }
    assert report["stages"]["publish_hydrometeor_candidate"]["workarray_to_published_state_conversion"]["rain"]["exact"]
    assert all(row["changed_count"] is None for row in report["species_profiles"]
               if not row["stage"].endswith("_post"))


def test_archived_liquid_receipt_analyzes_end_to_end():
    report = analyzer.analyze(EVIDENCE / "liquid_capture.json.gz", "LIQUID_RADAR_RH1", OUTER / "liquid_capture.json.gz")
    assert report["status"] == "SCOPED_PASS"
    assert report["primary_writer_outer_state8_raw32_bitwise_differences"] == {
        field: 0 for field in analyzer.FIELDS
    }
    assert report["evaluation_state_differences"]["eval2_vs_eval1"]["vapor"] == 153


def test_unknown_stage_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    capture["records"].append({"stage": "surprise"})
    with pytest.raises(ValueError, match="unknown or missing stages"):
        analyzer.record_index(capture, "HYDRO")


def test_orphan_boundary_pair_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    capture["records"] = [r for r in capture["records"] if r["stage"] != "transport_precipitation_flux_post"]
    with pytest.raises(ValueError):
        analyzer.record_index(capture, "HYDRO")


def test_declared_false_event_count_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    capture["counts"]["candidate_boundary_counts"]["diagnose_radar_cells"]["entries"] = 2
    with pytest.raises(ValueError, match="balanced pairs"):
        analyzer.record_index(capture, "HYDRO")


def test_invalid_caller_address_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    event = next(r for r in capture["records"] if r["stage"] == "diagnose_radar_cells_pre")
    event["caller_frame_address"] = None
    with pytest.raises(ValueError, match="caller frame address"):
        analyzer.record_index(capture, "HYDRO")


def test_invalid_sample_level_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    event = next(r for r in capture["records"] if r["stage"] == "transport_precipitation_flux_pre")
    event["arrays"]["rain"]["points"][0]["levels"][0]["fortran_k"] = 0
    with pytest.raises(ValueError, match="level order"):
        analyzer.record_index(capture, "HYDRO")


def test_stage_order_swap_rejected(hydro_receipt):
    capture = copy.deepcopy(hydro_receipt)
    stages = [r["stage"] for r in capture["records"]]
    first, second = stages.index("diagnose_radar_cells_pre"), stages.index("diagnose_radar_cells_post")
    capture["records"][first], capture["records"][second] = capture["records"][second], capture["records"][first]
    with pytest.raises(ValueError, match="event order"):
        analyzer.record_index(capture, "HYDRO")


def test_liquid_missing_derive_return_rejected(liquid_receipt):
    capture = copy.deepcopy(liquid_receipt)
    capture["records"] = [r for r in capture["records"] if not (r["stage"] == "derive_return_state_out" and r["call_number"] == 5)]
    with pytest.raises(ValueError, match="stage event counts"):
        analyzer.record_index(capture, "LIQUID_RADAR_RH1")


def test_liquid_call_number_swap_rejected(liquid_receipt):
    capture = copy.deepcopy(liquid_receipt)
    for stage in ("derive_preprologue_abi_pointers", "derive_entry_state_in", "derive_arguments", "derive_return_state_out"):
        pair = [r for r in capture["records"] if r["stage"] == stage and r["call_number"] in (1, 2)]
        pair[0]["call_number"], pair[1]["call_number"] = pair[1]["call_number"], pair[0]["call_number"]
    with pytest.raises(ValueError, match="out of order"):
        analyzer.record_index(capture, "LIQUID_RADAR_RH1")


def test_prior_outer_mismatch_rejected(tmp_path):
    prior = analyzer.read_capture(OUTER / "hydro_capture.json.gz")
    output = next(r for r in prior["records"] if r["stage"] == "pipeline_return_candidate_out" and r["call_number"] == 1)
    output["points"][0]["levels"][0]["temperature"]["raw_bytes_le_hex"] = "01000000"
    prior_path = tmp_path / "changed_outer.json.gz"
    with gzip.open(prior_path, "wt", encoding="utf-8") as stream:
        json.dump(prior, stream)
    with pytest.raises(ValueError, match="differs from prior original capture"):
        analyzer.analyze(EVIDENCE / "hydro_capture.json.gz", "HYDRO", prior_path)


def test_cli_does_not_write_pass_outputs_for_prior_mismatch(tmp_path):
    prior = analyzer.read_capture(OUTER / "hydro_capture.json.gz")
    output = next(r for r in prior["records"] if r["stage"] == "pipeline_return_candidate_out" and r["call_number"] == 1)
    output["points"][0]["levels"][0]["temperature"]["raw_bytes_le_hex"] = "01000000"
    prior_path = tmp_path / "changed_outer.json.gz"
    with gzip.open(prior_path, "wt", encoding="utf-8") as stream:
        json.dump(prior, stream)
    report_path, profiles_path = tmp_path / "report.json", tmp_path / "profiles.csv"
    result = subprocess.run([sys.executable, str(SCRIPT), str(EVIDENCE / "hydro_capture.json.gz"),
                             "--arm", "HYDRO", "--prior-outer", str(prior_path),
                             "--output", str(report_path), "--profiles", str(profiles_path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "SCOPED_PASS" not in result.stdout
    assert not report_path.exists() and not profiles_path.exists()


@pytest.mark.parametrize("stage", [
    "refresh_dry_air_mass_measure_entry",
    "refresh_dry_air_mass_measure_return",
    "both_refresh_states",
])
@pytest.mark.parametrize("defect", ["empty", "partial", "missing_layer", "different_keys"])
def test_cli_rejects_invalid_refresh_state_before_outputs(tmp_path, hydro_receipt, stage, defect):
    capture = copy.deepcopy(hydro_receipt)
    stages = ("refresh_dry_air_mass_measure_entry", "refresh_dry_air_mass_measure_return") if stage == "both_refresh_states" else (stage,)
    for target_stage in stages:
        event = next(record for record in capture["records"] if record["stage"] == target_stage)
        state = event["state"]
        if defect == "empty":
            state["points"] = []
        elif defect == "partial":
            state["points"] = state["points"][:19]
        elif defect == "missing_layer":
            del state["points"][0]["levels"][0]["pressure"]
        else:
            used = {(point["fortran_i"], point["fortran_j"]) for point in state["points"]}
            point = state["points"][0]
            point["fortran_i"], point["fortran_j"] = next(
                (i, j) for i in range(1, 236) for j in range(1, 284)
                if (i, j) not in used
            )
            point["shadow_i_zero_based"] = point["fortran_i"] - 1
            point["shadow_j_zero_based"] = point["fortran_j"] - 1

    capture_path = tmp_path / "mutated_hydro.json.gz"
    with gzip.open(capture_path, "wt", encoding="utf-8") as stream:
        json.dump(capture, stream)
    report_path, profiles_path = tmp_path / "report.json", tmp_path / "profiles.csv"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(capture_path), "--arm", "HYDRO",
         "--output", str(report_path), "--profiles", str(profiles_path)],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode != 0
    assert "SCOPED_PASS" not in result.stdout
    assert not report_path.exists() and not profiles_path.exists()
