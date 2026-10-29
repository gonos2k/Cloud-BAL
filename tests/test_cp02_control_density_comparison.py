import csv
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/cp02_control_density_comparison.py"
SPEC = importlib.util.spec_from_file_location("cp02_control_density_comparison", TOOL_PATH)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def profile():
    return {
        "fortran_i": 12, "fortran_j": 34, "fortran_k": 5,
        "point_id": "P01", "role": "lost_hit",
        "actual_observation.radar_reflectivity.valid": True,
        "actual_observation.radar_reflectivity.value": 25.0,
        "actual_observation.radar_reflectivity.quality": 32,
        "diagnose_radar_cells_post.radar_observed": True,
        "diagnose_radar_cells_post.phase": 1,
        "density_entry.status": "CAPTURED", "density_entry.pressure": 80000.0,
        "density_entry.temperature": 280.0,
        "density_return.status": "CAPTURED", "density_return.rho_d": 1.0,
        "phase_allocation_return.status": "CAPTURED", "phase_allocation_return.rho_d": 1.0,
        "phase_allocation_return.total": 0.005,
        "background_rain": 0.01, "actual_input.rain": 0.01,
        "publish_hydrometeor_candidate_post.rain": 0.005, "final.rain": 0.005,
        "background_snow": 0.002, "actual_input.snow": 0.002,
        "publish_hydrometeor_candidate_post.snow": 0.0, "final.snow": 0.0,
        "publish_hydrometeor_candidate_post.graupel": 0.0, "final.graupel": 0.0,
    }


def test_same_density_concentrations_differences_and_undefined_zero_background():
    row = TOOL.build_sample(profile())
    assert row["raw_sample_key"] == "12,34,5"
    assert row["Cdiag_rain_kg_m3"] == 0.005
    assert row["Cbg_eq_rain_kg_m3"] == 0.01
    assert row["Cdiag_minus_Cbg_eq_rain_kg_m3"] == -0.005
    assert row["ratio_Cdiag_over_Cbg_eq_rain"] == 0.5
    assert row["ratio_Cdiag_over_Cbg_eq_snow"] == 0.0

    empty = profile()
    empty["background_rain"] = empty["actual_input.rain"] = 0.0
    assert TOOL.build_sample(empty)["ratio_Cdiag_over_Cbg_eq_rain"] is None


@pytest.mark.parametrize("field,value", [
    ("density_return.rho_d", 0.0),
    ("phase_allocation_return.rho_d", 0.99),
    ("actual_observation.radar_reflectivity.value", float("nan")),
    ("density_entry.status", "NOT_CAPTURED"),
    ("actual_observation.radar_reflectivity.valid", False),
])
def test_bad_or_unavailable_sample_operands_fail_closed(field, value):
    row = profile()
    row[field] = value
    with pytest.raises(ValueError):
        TOOL.build_sample(row)


def test_canonical_outputs_have_hashes_group_rows_and_plot(tmp_path):
    expected_role_ratios = {
        "lost_hit": {"rain": 0.71483525, "snow": 0.15373328},
        "retained_hit": {"rain": 0.66200347, "snow": 0.13595266},
        "removed_false_alarm": {"rain": 0.77467255, "snow": 0.17119439},
        "RN1_positive_reference_all_forecasts_below5mm": {"rain": 0.65361220, "snow": 0.11551995},
    }
    expected_active_counts = {
        "lost_hit": {"rain": 33, "snow": 3},
        "retained_hit": {"rain": 34, "snow": 17},
        "removed_false_alarm": {"rain": 25, "snow": 6},
        "RN1_positive_reference_all_forecasts_below5mm": {"rain": 22, "snow": 1},
    }
    report = TOOL.run(tmp_path)
    assert report["status"] == "PASS_SCOPED_VALIDATED_CONTROL_SAMPLES"
    assert report["sample_count"] == 141
    assert report["provenance"]["input_sha256"]["docs/evidence/cp02_density_controls_20261029/capture/hydro_capture.json.gz"] == TOOL.EXPECTED_CAPTURE_SHA256
    indexed = {(row["role"], row["species"]): row for row in report["grouped_role_species_stats"]}
    for role, species_ratios in expected_role_ratios.items():
        for species, ratio in species_ratios.items():
            row = indexed[(role, species)]
            assert row[f"ratio_of_sums_Cdiag_over_Cbg_eq_{species}"] == pytest.approx(ratio, abs=5e-9)
            assert row["sample_count"] == expected_active_counts[role][species]
            assert row["phase"] == species
    qc32 = {(row["role"], row["species"]): row
            for row in report["grouped_role_species_quality_stats"]
            if row["quality"] == 32 and row["species"] == "rain"}
    assert qc32[("lost_hit", "rain")]["ratio_of_sums_Cdiag_over_Cbg_eq_rain"] == pytest.approx(0.71335931, abs=5e-9)
    assert qc32[("retained_hit", "rain")]["ratio_of_sums_Cdiag_over_Cbg_eq_rain"] == pytest.approx(0.66200347, abs=5e-9)
    assert qc32[("lost_hit", "rain")]["sample_count"] == 31
    assert qc32[("retained_hit", "rain")]["sample_count"] == 34

    with (tmp_path / "control_density_samples.csv").open(newline="", encoding="utf-8") as stream:
        samples = list(csv.DictReader(stream))
    with (tmp_path / "control_density_groups.csv").open(newline="", encoding="utf-8") as stream:
        groups = list(csv.DictReader(stream))
    saved = json.loads((tmp_path / "control_density_comparison.json").read_text(encoding="utf-8"))
    assert len(samples) == 141
    assert len(groups) == len(report["grouped_role_species_stats"]) + len(report["grouped_role_species_quality_stats"])
    assert saved["provenance"]["input_sha256"]["tools/cp02_control_capture_analysis.py"]
    assert saved["provenance"]["input_sha256"]["tests/test_cp02_control_density_comparison.py"]
    assert (tmp_path / "control_density_comparison.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_report_refuses_missing_capture_validation():
    with pytest.raises(ValueError, match="scoped pass"):
        TOOL.build_report({"status": "FAILED"}, [])
