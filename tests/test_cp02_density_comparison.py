import csv
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools/cp02_density_comparison.py"
SPEC = importlib.util.spec_from_file_location("cp02_density_comparison", SCRIPT)
density = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(density)


def sample_profile():
    return {
        "fortran_i": 10, "fortran_j": 20, "fortran_k": 5,
        "density_entry.status": "CAPTURED", "density_entry.pressure": 80000.0,
        "density_entry.temperature": 280.0,
        "density_return.status": "CAPTURED", "density_return.rho_d": 1.0,
        "phase_allocation_return.status": "CAPTURED",
        "phase_allocation_return.rho_d": 1.0, "phase_allocation_return.total": 0.005,
        "diagnose_radar_cells_post.phase": 1,
        "diagnose_radar_cells_post.radar_observed": True,
        "actual_observation.radar_reflectivity.valid": True,
        "actual_observation.radar_reflectivity.quality": 32,
        "actual_observation.radar_reflectivity.value": 20.0,
        "actual_input.rain": 0.01, "actual_input.snow": 0.0,
        "final.rain": 0.005, "final.snow": 0.0, "final.graupel": 0.0,
        "publish_hydrometeor_candidate_post.rain": 0.005,
        "publish_hydrometeor_candidate_post.snow": 0.0,
        "publish_hydrometeor_candidate_post.graupel": 0.0,
        "background_rain": 0.01, "background_snow": 0.0,
        "publish_hydrometeor_candidate_post.rain": 0.005,
        "publish_hydrometeor_candidate_post.snow": 0.0,
        "publish_hydrometeor_candidate_post.graupel": 0.0,
    }


def test_same_captured_density_forms_both_concentrations_and_ratio():
    row = density.build_sample(sample_profile())
    assert row["raw_sample_key"] == "10,20,5"
    assert row["Cdiag_rain_kg_m3"] == 0.005
    assert row["Cbg_eq_rain_kg_m3"] == 0.01
    assert row["ratio_rain_Cdiag_over_Cbg_eq"] == 0.5
    assert row["active_diag_concentration_ratio"] == 0.5


@pytest.mark.parametrize("field", [
    "density_entry.pressure", "actual_observation.radar_reflectivity.value",
    "final.rain",
])
def test_missing_required_numeric_value_fails_closed(field):
    profile = sample_profile()
    del profile[field]
    with pytest.raises(ValueError, match="missing or invalid"):
        density.build_sample(profile)


@pytest.mark.parametrize("field,value", [
    ("density_return.rho_d", 0.0),
    ("phase_allocation_return.rho_d", float("nan")),
])
def test_invalid_or_nonpositive_density_fails_closed(field, value):
    profile = sample_profile()
    profile[field] = value
    with pytest.raises(ValueError):
        density.build_sample(profile)


def test_density_mismatch_between_helper_return_and_allocation_fails_closed():
    profile = sample_profile()
    profile["phase_allocation_return.rho_d"] = 0.99
    with pytest.raises(ValueError, match="density return and allocation density differ"):
        density.build_sample(profile)


def test_invalid_key_and_observation_are_rejected():
    profile = sample_profile()
    profile["fortran_k"] = 0
    with pytest.raises(ValueError, match="sample key"):
        density.build_sample(profile)
    profile = sample_profile()
    profile["actual_observation.radar_reflectivity.valid"] = False
    with pytest.raises(ValueError, match="lacks valid reflectivity"):
        density.build_sample(profile)


def test_background_must_match_captured_actual_input():
    profile = sample_profile()
    profile["actual_input.rain"] = 0.009
    with pytest.raises(ValueError, match="canonical background rain differs"):
        density.build_sample(profile)


def test_final_species_must_match_total_and_have_inactive_species_zero():
    profile = sample_profile()
    profile["phase_allocation_return.total"] = 0.006
    with pytest.raises(ValueError, match="total differs from active REAL64"):
        density.build_sample(profile)
    profile = sample_profile()
    profile["final.snow"] = 0.001
    with pytest.raises(ValueError, match="inactive phase or graupel"):
        density.build_sample(profile)


def test_duplicate_canonical_key_fails_closed():
    profile = sample_profile()
    profiles = [profile] * density.EXPECTED_PROFILE_COUNT
    with pytest.raises(ValueError, match="duplicate canonical profile sample key"):
        density.build_comparison(profiles)


def test_canonical_regeneration_uses_190_validated_archived_observations(tmp_path):
    report = density.run(tmp_path)
    assert report["status"] == "PASS_SCOPED_ARCHIVED_SAMPLES"
    assert report["sample_count"] == 190
    assert sum(group["count"] for group in report["grouped_phase_quality_stats"]) == 190
    with (tmp_path / "density_comparison.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 190
    assert rows[0]["raw_sample_key"] == f'{rows[0]["fortran_i"]},{rows[0]["fortran_j"]},{rows[0]["fortran_k"]}'
    saved = json.loads((tmp_path / "density_comparison.json").read_text(encoding="utf-8"))
    assert saved["validated_capture_sha256"] == report["validated_capture_sha256"]
    assert (tmp_path / "density_comparison.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

