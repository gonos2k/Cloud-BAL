#!/usr/bin/env python3
"""Exercise full-file replay telemetry without approving a transition file."""
from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

from check_pressure_candidate_shadow import validate


def check(path):
    summary, failures = validate(path)
    assert "pressure transition requires complete exact stored-state replay" in failures
    assert summary["pressure_transition_physics_independently_validated"] is False
    assert summary["promotion_eligible"] is False
    assert summary["pressure_transition_replay_criterion"] == "exact_stored_state_v1"
    errors = summary["pressure_transition_replay_max_abs_errors"]
    assert set(errors) == {"temperature", "dry_air_mass", "vapor", "cloud_water",
                           "cloud_ice", "rain", "snow", "graupel"}, failures
    assert all(np.isfinite(value) and value == 0.0 for value in errors.values())
    assert not any("pressure transition physical replay:" in failure for failure in failures)
    assert not any(failure.startswith("geometry_analysis_") for failure in failures), failures
    assert "analysis plus thermo plus geometry species identity" not in failures
    assert not any(failure in failures for failure in (
        "species budget", "thermo_sensible_change_j budget", "thermo_phase_change_j budget",
        "thermo_water_error_kg budget", "thermo_enthalpy_error_j budget",
    )), failures
    with netCDF4.Dataset(path) as dataset:
        assert dataset.numerical_test_probe == 1
        cell = tuple(np.argwhere(np.asarray(dataset["candidate_above_ground"][:], dtype=bool))[0])
    with tempfile.TemporaryDirectory(prefix="transition-replay-probe-") as directory:
        changed = Path(directory) / "changed.nc"
        for name, increment in (("temperature", .25), ("rain", .001), ("dry_air_mass", 1e6)):
            shutil.copyfile(path, changed)
            with netCDF4.Dataset(changed, "r+") as dataset:
                variable = "candidate_dry_air_mass_measure" if name == "dry_air_mass" else f"candidate_{name}"
                dataset[variable][cell] += increment
            altered, rejected = validate(changed)
            assert "pressure transition requires complete exact stored-state replay" in rejected
            assert altered["pressure_transition_physics_independently_validated"] is False
            assert altered["pressure_transition_replay_max_abs_errors"][name] >= .9 * increment
        shutil.copyfile(path, changed)
        with netCDF4.Dataset(changed, "r+") as dataset:
            dataset["transition_seed_dry_air_mass_measure"][cell] *= 1.01
        altered, rejected = validate(changed)
        assert any("seed" in failure and "mass" in failure for failure in rejected), rejected
        assert altered["pressure_transition_replay_max_abs_errors"] == {}
        assert altered["pressure_transition_physics_independently_validated"] is False

        shutil.copyfile(path, changed)
        with netCDF4.Dataset(changed, "r+") as dataset:
            budget = np.array(dataset.geometry_analysis_species_change_kg)
            budget[0] += 1e6
            dataset.setncattr("geometry_analysis_species_change_kg", budget)
        _, rejected = validate(changed)
        assert "geometry_analysis_species_change_kg ledger" in rejected
        assert "analysis plus thermo plus geometry species identity" in rejected
        shutil.copyfile(path, changed)
        with netCDF4.Dataset(changed, "r+") as dataset:
            dataset.setncattr("thermo_phase_change_j", dataset.thermo_phase_change_j + 1e6)
        _, rejected = validate(changed)
        assert "thermo_phase_change_j budget" in rejected
    print(f"Transition full-file replay measured (not approved): {errors}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
