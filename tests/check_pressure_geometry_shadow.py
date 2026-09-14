#!/usr/bin/env python3
"""Check a real writer's prescribed-pressure geometry and isolated mutations."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

from check_pressure_candidate_shadow import reject, rewrite_without, validate


GEOMETRY_FIELDS = (
    "requested_surface_pressure",
    "candidate_pressure_interface",
    "candidate_cell_dp",
    "candidate_pressure_mass_measure",
    "candidate_dry_air_mass_measure",
    "continuity_original_background",
)


def corrupt_field(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        field = dataset[name]
        index = (0,) * field.ndim
        field[index] = float(field[index]) + 100.0


def corrupt_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        value = np.asarray(dataset.getncattr(name)).copy()
        value.flat[0] += 1000000
        dataset.setncattr(name, value)


def set_attribute(path: Path, name: str, value, field: str | None = None) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        target = dataset if field is None else dataset[field]
        target.setncattr(name, value)


def replace_upper_cell_mass_with_prethermo(path: Path) -> None:
    """Use the pre-thermo denominator in the changed-PS column's upper cell."""
    with netCDF4.Dataset(path, "r+") as dataset:
        species = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
        # Fortran (i,j,k)=(2,2,2) is (z,y,x)=(1,1,1) in this netCDF file.
        index = (1, 1, 1)
        pre_thermo = 0.0
        for species_index, name in enumerate(species):
            role = "background" if species_index < 3 else "candidate"
            pre_thermo += float(dataset[f"{role}_{name}"][index])
        pressure_mass = float(dataset["candidate_pressure_mass_measure"][index])
        dataset["candidate_dry_air_mass_measure"][index] = pressure_mass / (1.0 + pre_thermo)


def check(path: Path) -> None:
    summary, failures = validate(path)
    assert not failures, failures
    assert summary["pressure_analysis_candidate_promotion_eligible"] is False
    with netCDF4.Dataset(path) as dataset:
        assert dataset.getncattr("pressure_geometry_contract") == "prescribed_surface_pressure_v1"
        assert dataset.getncattr("continuity_geometry_scope") == "candidate_balance_stage_geometry_v1"
        before = np.asarray(dataset["surface_pressure"][:], dtype=np.float64)
        after = np.asarray(dataset["candidate_surface_pressure"][:], dtype=np.float64)
        requested = np.asarray(dataset["requested_surface_pressure"][:])
        assert requested.dtype == np.dtype("float64")
        np.testing.assert_array_equal(requested.astype(np.float32), after.astype(np.float32))
        assert np.any(before != after), "fixture must exercise a nonzero stored pressure increment"
        assert np.any(before == after), "fixture must retain untouched pressure columns"
        assert np.any(requested != after), "fixture must exercise request storage rounding"
        original_residual = np.asarray(dataset["continuity_original_background"][:])
        stage_residual = np.asarray(dataset["continuity_background"][:])
        assert np.any(original_residual != stage_residual), (
            "fixture must expose original-geometry versus balance-stage residuals"
        )
        species = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
        pre_thermo = np.zeros_like(original_residual)
        post_thermo = np.zeros_like(original_residual)
        for index, name in enumerate(species):
            role = "background" if index < 3 else "candidate"
            pre_thermo += np.asarray(dataset[f"{role}_{name}"][:], dtype=np.float64)
            post_thermo += np.asarray(dataset[f"candidate_{name}"][:], dtype=np.float64)
        rounded = pre_thermo != post_thermo
        assert np.any(rounded & (before != after)[None, :, :]), "changed-PS thermo storage roundoff"
        assert np.any(rounded & (before == after)[None, :, :]), "unchanged-PS thermo storage roundoff"
        original_mass = np.asarray(dataset["pressure_mass_measure"][:])
        candidate_mass = np.asarray(dataset["candidate_pressure_mass_measure"][:])
        candidate_dry_mass = np.asarray(dataset["candidate_dry_air_mass_measure"][:])
        changed_column = (1, 1)  # Fortran (i,j)=(2,2), where thermo k=2 was added.
        upper_cell = (1, *changed_column)
        assert candidate_mass[upper_cell] == original_mass[upper_cell], (
            "upper changed-PS cell must retain its pressure mass"
        )
        assert pre_thermo[upper_cell] != post_thermo[upper_cell], (
            "fixture must expose pre/post-thermo water rounding in the upper cell"
        )
        expected_dry_mass = candidate_mass[upper_cell] / (1.0 + post_thermo[upper_cell])
        np.testing.assert_allclose(
            candidate_dry_mass[upper_cell],
            expected_dry_mass,
            rtol=0.0,
            atol=128.0 * np.finfo(np.float64).eps * max(1.0, abs(expected_dry_mass)),
        )
        area = float(dataset.grid_dx_m) * float(dataset.grid_dy_m)
        # With unchanged top and represented levels, the column total change
        # is A * delta(PSFC) / g, independently of the species denominator.
        np.testing.assert_allclose(
            (candidate_mass - original_mass).sum(axis=0),
            area * (after - before) / 9.80665,
            rtol=2.0e-12,
            atol=1.0e-5,
        )
        ledger = {name for name in dataset.ncattrs() if name.startswith("geometry_analysis_")}
        assert ledger, "geometry ledger must be present"

    with tempfile.TemporaryDirectory(prefix="pressure-geometry-mutations-") as directory:
        damaged = Path(directory) / "mutated.nc"
        for name in (*GEOMETRY_FIELDS, "pressure_geometry_contract", "continuity_geometry_scope", *sorted(ledger)):
            rewrite_without(path, damaged, {name})
            _, failures = validate(damaged)
            assert failures, f"accepted missing geometry contract member: {name}"
        for name in GEOMETRY_FIELDS:
            reject(path, damaged, lambda output, key=name: corrupt_field(output, key), name)
        for name in sorted(ledger):
            reject(path, damaged, lambda output, key=name: corrupt_attribute(output, key), name)
        reject(
            path, damaged,
            lambda output: corrupt_field(output, "candidate_surface_pressure"),
            "stored PSFC differs from the exact request",
        )
        shutil.copyfile(path, damaged)
        replace_upper_cell_mass_with_prethermo(damaged)
        _, failures = validate(damaged)
        assert "candidate dry-air mass identity" in failures, failures
        reject(
            path, damaged,
            lambda output: set_attribute(output, "pressure_geometry_contract", "unknown"),
            "unknown geometry contract",
        )
        reject(
            path, damaged,
            lambda output: set_attribute(output, "pressure_transition_contract", "pressure_transition_seed_v1"),
            "transition payload cannot inherit same-domain validation",
        )
        _, failures = validate(damaged)
        assert "pressure transition requires complete exact stored-state replay" in failures
        reject(
            path, damaged,
            lambda output: set_attribute(output, "units", "hPa", "requested_surface_pressure"),
            "request units",
        )
        extension = set(GEOMETRY_FIELDS) | ledger | {"pressure_geometry_contract", "continuity_geometry_scope"}
        rewrite_without(path, damaged, extension)
        _, failures = validate(damaged)
        assert failures, "variable pressure must not pass as a legacy fixed-geometry artifact"
    print("Prescribed-pressure geometry, column-mass oracle and mutations passed")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
