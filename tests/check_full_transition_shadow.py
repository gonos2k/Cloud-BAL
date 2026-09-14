#!/usr/bin/env python3
"""Check real transition serialization without granting publication authority."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (
    SOURCE_BOUNDARY_CONDITION,
    SOURCE_COLUMN_PHYSICS,
    SOURCE_DYNAMIC_TARGET,
    validate,
)


PRECIPITATION_SPECIES = ("rain", "snow", "graupel")
SOURCE_INJECTIONS = (
    ("dynamic-target", SOURCE_DYNAMIC_TARGET),
    ("boundary-condition", SOURCE_BOUNDARY_CONDITION),
)


def _source_mutation_cells(dataset):
    """Return at most one retained and one remapped/added cell for probes."""
    original = np.asarray(dataset["above_ground"][:], dtype=bool)
    candidate = np.asarray(dataset["candidate_above_ground"][:], dtype=bool)
    remapped_columns = np.any(candidate != original, axis=0)
    if "pressure_mass_measure" in dataset.variables and (
        "candidate_pressure_mass_measure" in dataset.variables
    ):
        remapped_columns |= np.any(
            np.asarray(dataset["candidate_pressure_mass_measure"][:])
            != np.asarray(dataset["pressure_mass_measure"][:]),
            axis=0,
        )

    retained = original & candidate & ~remapped_columns[None, :, :]
    retained_cells = np.argwhere(retained)
    cells = []
    if retained_cells.size:
        cells.append(("retained", tuple(int(index) for index in retained_cells[0])))

    remapped_or_added = candidate & (
        remapped_columns[None, :, :] | ~original
    )
    remapped_cells = np.argwhere(remapped_or_added)
    if remapped_cells.size:
        cells.append((
            "remapped-or-added",
            tuple(int(index) for index in remapped_cells[0]),
        ))
    return cells


def check(path):
    summary, failures = validate(path)
    assert failures == [], (str(path), failures)
    assert summary["validation_scope"] == "NUMERICAL_CONTENT_ONLY"
    assert summary["numerical_decision"] == "VALID"
    assert summary["pressure_transition_replay_criterion"] == "exact_stored_state_v1"
    assert summary["pressure_transition_physics_independently_validated"] is True
    assert summary["artifact_decision"] == "UNBOUND"
    assert summary["science_assessed"] is False
    assert summary["promotion_eligible"] is False
    errors = summary["pressure_transition_replay_max_abs_errors"]
    assert set(errors) == {
        "temperature", "dry_air_mass", "vapor", "cloud_water",
        "cloud_ice", "rain", "snow", "graupel",
    }, errors
    assert all(np.isfinite(value) and value == 0.0 for value in errors.values()), errors
    with netCDF4.Dataset(path) as dataset:
        assert "numerical_test_probe" not in dataset.ncattrs()

    with tempfile.TemporaryDirectory(prefix="full-transition-mutation-") as directory:
        changed = Path(directory) / "changed.nc"
        for mutation in (
            "candidate_temperature", "candidate_vapor",
            "candidate_dry_air_mass_measure", "candidate_geopotential",
            "column_changed", "candidate_surface_pressure_source",
            "corruptledger", "seedmutation", "numerical_test_probe",
        ):
            shutil.copyfile(path, changed)
            with netCDF4.Dataset(changed, "r+") as dataset:
                cell = tuple(np.argwhere(dataset["candidate_above_ground"][:] == 1)[0])
                if mutation == "corruptledger":
                    ledger = np.asarray(
                        dataset.getncattr("geometry_analysis_species_change_kg"),
                        dtype=np.float64,
                    )
                    ledger[0] += 1.0e6
                    dataset.setncattr("geometry_analysis_species_change_kg", ledger)
                elif mutation == "seedmutation":
                    seed_cell = tuple(np.argwhere(
                        dataset["transition_seed_above_ground"][:] == 1
                    )[0])
                    dataset["transition_seed_dry_air_mass_measure"][seed_cell] *= 1.01
                elif mutation == "numerical_test_probe":
                    dataset.setncattr("numerical_test_probe", 1)
                elif mutation == "candidate_surface_pressure_source":
                    surface_cell = tuple(np.argwhere(
                        dataset["candidate_surface_pressure"][:]
                        > dataset["background_surface_pressure"][:])[0])
                    dataset[mutation][surface_cell] = (
                        int(dataset["background_surface_pressure_source"][surface_cell])
                        | SOURCE_COLUMN_PHYSICS)
                elif mutation == "column_changed":
                    dataset[mutation][cell] = 1 - int(dataset[mutation][cell])
                else:
                    increment = {
                        "candidate_temperature": 0.25,
                        "candidate_vapor": 0.001,
                        "candidate_dry_air_mass_measure": 1.0e6,
                        "candidate_geopotential": 100.0,
                    }[mutation]
                    dataset[mutation][cell] += increment
            altered, rejected = validate(changed)
            assert rejected, (mutation, rejected)
            assert altered["numerical_decision"] == "INVALID"
            assert altered["promotion_eligible"] is False
            assert altered["pressure_transition_physics_independently_validated"] is False

        # A precipitation source must not acquire a known source class merely
        # because the column-physics bit is present.  Probe one untouched
        # original cell, plus one remapped/added cell when the fixture has one.
        with netCDF4.Dataset(path) as dataset:
            source_cells = _source_mutation_cells(dataset)
        assert source_cells, f"{path} has no source-provenance probe cell"
        for scope, cell in source_cells:
            for species in PRECIPITATION_SPECIES:
                source_name = f"candidate_{species}_source"
                for injection_name, injection in SOURCE_INJECTIONS:
                    shutil.copyfile(path, changed)
                    with netCDF4.Dataset(changed, "r+") as dataset:
                        dataset[source_name][cell] = (
                            injection | SOURCE_COLUMN_PHYSICS
                        )
                    altered, rejected = validate(changed)
                    label = f"{scope} {source_name} {injection_name}"
                    assert rejected, (label, rejected)
                    assert altered["numerical_decision"] == "INVALID"
                    assert altered["promotion_eligible"] is False
                    assert altered[
                        "pressure_transition_physics_independently_validated"
                    ] is False
    print(f"Full transition SHADOW independently checked; publication blocked: {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_full_transition_shadow.py FILE [FILE ...]")
    for filename in sys.argv[1:]:
        check(Path(filename))
