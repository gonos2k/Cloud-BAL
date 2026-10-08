#!/usr/bin/env python3
"""Independently replay serialized joint component contracts and one mutation."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (
    THERMO_CP_DRY,
    THERMO_SPECIES_CP,
    THERMO_SPECIES_H0,
    THERMO_T0,
    validate_physical_joint_contract,
)


def replay(path: Path) -> list[str]:
    failures: list[str] = []
    with netCDF4.Dataset(path) as dataset:
        above = dataset["above_ground"][:].astype(bool)
        validate_physical_joint_contract(
            dataset, above,
            lambda condition, message: failures.append(message) if not condition else None,
        )
    return failures


def physical_components(dataset, prefix: str, cell: tuple[int, int, int]) -> np.ndarray:
    mass = float(dataset[f"{prefix}_dry_air_mass_measure"][cell])
    temperature = float(dataset[f"{prefix}_temperature"][cell])
    species = np.array([dataset[f"{prefix}_{name}"][cell]
                        for name in ("vapor", "cloud_water", "cloud_ice",
                                     "rain", "snow", "graupel")], dtype=np.float64)
    enthalpy = ((THERMO_CP_DRY + np.sum(THERMO_SPECIES_CP * species))
                * (temperature - THERMO_T0)
                + np.sum(THERMO_SPECIES_H0 * species))
    return np.concatenate(([mass], mass * species, [mass * enthalpy]))


def analysis_components(dataset, cell: tuple[int, int, int]) -> np.ndarray:
    if "physical_analysis_increment" not in dataset.variables:
        return np.zeros(8, dtype=np.float64)
    return np.asarray(dataset["physical_analysis_increment"][(*cell, slice(None))],
                      dtype=np.float64)


source = Path(sys.argv[1])
failures = replay(source)
assert failures == [], failures

with tempfile.TemporaryDirectory(prefix="physical-contract-readback-") as directory:
    def reject_mutation(name, mutate, expected):
        altered = Path(directory) / f"{name}.nc"
        shutil.copyfile(source, altered)
        with netCDF4.Dataset(altered, "r+") as dataset:
            mutate(dataset)
        failures = replay(altered)
        assert any(expected in failure for failure in failures), (name, failures)

    def first_active(dataset):
        z, y, x = np.argwhere(dataset["above_ground"][:].astype(bool))[0]
        return int(z), int(y), int(x)

    reject_mutation(
        "forged-source",
        lambda dataset: dataset["physical_source_increment"].__setitem__(
            (*first_active(dataset), 0), 1000.0
        ),
        "independent eight-component local contract replay",
    )
    reject_mutation(
        "coverage-gap",
        lambda dataset: dataset["physical_contract_coverage"].__setitem__(
            first_active(dataset), 0
        ),
        "physical contract full atmospheric coverage",
    )
    reject_mutation(
        "nan-source",
        lambda dataset: dataset["physical_source_increment"].__setitem__(
            (*first_active(dataset), 0), np.nan
        ),
        "physical contract increments finite",
    )
    reject_mutation(
        "negative-tolerance",
        lambda dataset: dataset["physical_tolerance"].__setitem__(
            (*first_active(dataset), 0), -1.0
        ),
        "physical tolerance nonnegative",
    )

    def wrong_coverage_shape(dataset):
        dataset.renameVariable("physical_contract_coverage", "old_contract_coverage")
        malformed = dataset.createVariable("physical_contract_coverage", "i4", ("z", "y"))
        malformed.units = "1"
        malformed[:] = 0

    reject_mutation("wrong-coverage-shape", wrong_coverage_shape,
                    "physical contract coverage structure")

    def wrong_source_type(dataset):
        original = dataset["physical_source_increment"]
        dims = original.dimensions
        units = original.units
        dataset.renameVariable("physical_source_increment", "old_source_increment")
        malformed = dataset.createVariable("physical_source_increment", "i4", dims)
        malformed.units = units
        malformed[:] = 0

    reject_mutation("wrong-source-type", wrong_source_type,
                    "physical_source_increment structure")

    def packed_tolerance(dataset):
        dataset["physical_tolerance"].scale_factor = 0.5

    reject_mutation("packed-tolerance", packed_tolerance,
                    "physical_tolerance structure")

    def packed_candidate_mass(dataset):
        dataset["physical_candidate_dry_air_mass_measure"].add_offset = 1.0

    reject_mutation("packed-candidate-mass", packed_candidate_mass,
                    "physical_candidate dry mass structure")

    def missing_bundle(dataset):
        dataset.renameVariable("physical_tolerance", "missing_physical_tolerance")

    reject_mutation("missing-bundle", missing_bundle,
                    "physical contract increment bundle")

    with netCDF4.Dataset(source) as dataset:
        has_phase = "physical_internal_phase_increment" in dataset.variables

    if has_phase:
        def missing_phase_variable(dataset):
            dataset.renameVariable("physical_internal_phase_increment", "detached_phase_increment")

        reject_mutation("missing-phase-variable", missing_phase_variable,
                        "complete physical internal phase contract")

        def missing_phase_attribute(dataset):
            dataset.delncattr("physical_internal_phase_contract")

        reject_mutation("missing-phase-attribute", missing_phase_attribute,
                        "complete physical internal phase contract")

        def missing_phase_extension(dataset):
            extensions = dataset.getncattr("schema_extensions").split(",")
            dataset.setncattr("schema_extensions", ",".join(
                token for token in extensions if token != "physical_internal_phase_v1"
            ))

        reject_mutation("missing-phase-extension", missing_phase_extension,
                        "complete physical internal phase contract")

        def duplicate_phase_extension(dataset):
            dataset.setncattr("schema_extensions", dataset.getncattr("schema_extensions")
                              + ",physical_internal_phase_v1")

        reject_mutation("duplicate-phase-extension", duplicate_phase_extension,
                        "physical internal phase extension uniqueness")

        def nonstoichiometric_phase(dataset):
            cell = first_active(dataset)
            dataset["physical_internal_phase_increment"][(*cell, 2)] += 1.0

        reject_mutation("phase-water-defect", nonstoichiometric_phase,
                        "physical internal phase water stoichiometry")

        def nonfinite_phase(dataset):
            cell = first_active(dataset)
            dataset["physical_internal_phase_increment"][(*cell, 1)] = np.inf

        reject_mutation("nonfinite-phase", nonfinite_phase,
                        "physical contract increments finite")

        def phase_outside_coverage(dataset):
            cell = first_active(dataset)
            dataset["physical_contract_coverage"][cell] = 0

        reject_mutation("phase-outside-coverage", phase_outside_coverage,
                        "physical contract full atmospheric coverage")

    with netCDF4.Dataset(source) as dataset:
        has_analysis = "physical_analysis_increment" in dataset.variables
        if has_analysis:
            assert dataset.getncattr("pipeline_status") == -10
            assert dataset.getncattr("pipeline_reason") == 9
            for name in ("column_status", "balance_status"):
                assert dataset.getncattr(name) == -10, name

    if has_analysis:
        def legacy_without_analysis(dataset):
            # Recreate the pre-analysis endpoint so the old contract's zero
            # analysis contribution remains a valid complete artifact.
            for name in ("temperature", "vapor", "cloud_water", "cloud_ice",
                         "rain", "snow", "graupel", "dry_air_mass_measure"):
                background_name = f"physical_background_{name}"
                candidate_name = f"physical_candidate_{name}"
                if background_name in dataset.variables and candidate_name in dataset.variables:
                    dataset[candidate_name][:] = dataset[background_name][:]
                endpoint_name = f"candidate_{name}"
                background_endpoint_name = f"background_{name}"
                if endpoint_name in dataset.variables and background_endpoint_name in dataset.variables:
                    dataset[endpoint_name][:] = dataset[background_endpoint_name][:]
                valid_name = f"candidate_{name}_valid"
                background_valid_name = f"background_{name}_valid"
                if valid_name in dataset.variables and background_valid_name in dataset.variables:
                    dataset[valid_name][:] = dataset[background_valid_name][:]
            dataset.renameVariable("physical_analysis_increment", "detached_analysis_increment")
            dataset.delncattr("physical_analysis_increment_identity")
            extensions = dataset.getncattr("schema_extensions").split(",")
            dataset.setncattr("schema_extensions", ",".join(
                token for token in extensions if token != "physical_analysis_increment_v1"
            ))

        legacy = Path(directory) / "legacy-without-analysis.nc"
        shutil.copyfile(source, legacy)
        with netCDF4.Dataset(legacy, "r+") as dataset:
            legacy_without_analysis(dataset)
        failures = replay(legacy)
        assert failures == [], ("legacy-without-analysis", failures)

        def missing_analysis_variable(dataset):
            dataset.renameVariable("physical_analysis_increment", "detached_analysis_increment")

        reject_mutation("missing-analysis-variable", missing_analysis_variable,
                        "complete physical analysis increment contract")

        def missing_analysis_identity(dataset):
            dataset.delncattr("physical_analysis_increment_identity")

        reject_mutation("missing-analysis-identity", missing_analysis_identity,
                        "complete physical analysis increment contract")

        def missing_analysis_extension(dataset):
            extensions = dataset.getncattr("schema_extensions").split(",")
            dataset.setncattr("schema_extensions", ",".join(
                token for token in extensions if token != "physical_analysis_increment_v1"
            ))

        reject_mutation("missing-analysis-extension", missing_analysis_extension,
                        "complete physical analysis increment contract")

        def nonfinite_analysis(dataset):
            cell = first_active(dataset)
            dataset["physical_analysis_increment"][(*cell, 1)] = np.inf

        reject_mutation("nonfinite-analysis", nonfinite_analysis,
                        "physical contract increments finite")

        def dry_mass_analysis(dataset):
            cell = first_active(dataset)
            dataset["physical_analysis_increment"][(*cell, 0)] = 1.0

        reject_mutation("analysis-dry-mass", dry_mass_analysis,
                        "physical analysis dry-mass increment is zero")

        def changed_analysis(dataset):
            cell = first_active(dataset)
            dataset["physical_analysis_increment"][(*cell, 1)] += 1.0e6

        reject_mutation("changed-analysis", changed_analysis,
                        "independent eight-component local contract replay")

        def malformed_analysis_shape(dataset):
            original = dataset["physical_analysis_increment"]
            units = original.units
            dataset.renameVariable("physical_analysis_increment", "old_analysis_increment")
            malformed = dataset.createVariable(
                "physical_analysis_increment", "d", ("z", "y", "x")
            )
            malformed.units = units
            malformed[:] = 0.0

        reject_mutation("malformed-analysis-shape", malformed_analysis_shape,
                        "physical analysis increment structure")

    def detach_candidate_cloud_water(dataset):
        cell = first_active(dataset)
        before = physical_components(dataset, "physical_candidate", cell)
        old = np.float32(dataset["physical_candidate_cloud_water"][cell])
        new = np.nextafter(old, np.float32(np.inf))
        dataset["physical_candidate_cloud_water"][cell] = new
        after = physical_components(dataset, "physical_candidate", cell)
        source = after - before
        if "physical_internal_phase_increment" in dataset.variables:
            source -= np.asarray(dataset["physical_internal_phase_increment"][:], dtype=np.float64)[
                (*cell, slice(None))
            ]
        source -= analysis_components(dataset, cell)
        dataset["physical_source_increment"][(*cell, slice(None))] = source

    reject_mutation("detached-candidate-bundle", detach_candidate_cloud_water,
                    "physical_candidate snapshot matches candidate_cloud_water")

    def negative_vapor_with_coherent_source(dataset):
        cell = first_active(dataset)
        before = physical_components(dataset, "physical_candidate", cell)
        dataset["physical_candidate_vapor"][cell] = np.float32(-1.0e-4)
        species = np.array([dataset[f"physical_candidate_{name}"][cell]
                            for name in ("vapor", "cloud_water", "cloud_ice",
                                         "rain", "snow", "graupel")], dtype=np.float64)
        pressure_mass = float(dataset["pressure_mass_measure"][cell])
        reconciled_mass = pressure_mass / (1.0 + np.sum(species))
        dataset["physical_candidate_dry_air_mass_measure"][cell] = reconciled_mass
        after = physical_components(dataset, "physical_candidate", cell)
        source = after - before
        if "physical_internal_phase_increment" in dataset.variables:
            source -= np.asarray(dataset["physical_internal_phase_increment"][:], dtype=np.float64)[
                (*cell, slice(None))
            ]
        source -= analysis_components(dataset, cell)
        dataset["physical_source_increment"][(*cell, slice(None))] = source

    reject_mutation("negative-vapor-candidate", negative_vapor_with_coherent_source,
                    "physical_candidate vapor range for physical contract")

    def coherent_candidate_species_change(dataset):
        cell = first_active(dataset)
        names = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
        before = physical_components(dataset, "physical_background", cell)
        old = np.float32(dataset["physical_candidate_cloud_water"][cell])
        new = np.float32(old + np.float32(1.0e-5))
        dataset["physical_candidate_cloud_water"][cell] = new
        dataset["candidate_cloud_water"][cell] = new
        species = np.array([dataset[f"physical_candidate_{name}"][cell]
                            for name in names], dtype=np.float64)
        pressure_mass = float(dataset["pressure_mass_measure"][cell])
        reconciled_mass = pressure_mass / (1.0 + np.sum(species))
        dataset["physical_candidate_dry_air_mass_measure"][cell] = reconciled_mass
        if "candidate_dry_air_mass_measure" in dataset.variables:
            dataset["candidate_dry_air_mass_measure"][cell] = reconciled_mass
        after = physical_components(dataset, "physical_candidate", cell)
        source = after - before
        if "physical_internal_phase_increment" in dataset.variables:
            source -= np.asarray(dataset["physical_internal_phase_increment"][:], dtype=np.float64)[
                (*cell, slice(None))
            ]
        source -= analysis_components(dataset, cell)
        dataset["physical_source_increment"][(*cell, slice(None))] = source

    coherent = Path(directory) / "coherent-candidate-species-change.nc"
    shutil.copyfile(source, coherent)
    with netCDF4.Dataset(coherent, "r+") as dataset:
        coherent_candidate_species_change(dataset)
    failures = replay(coherent)
    assert failures == [], ("coherent candidate species change", failures)

    def prescribed_half_kelvin_temperature_change(dataset):
        cell = first_active(dataset)
        species = np.array([
            dataset[f"physical_candidate_{name}"][cell]
            for name in ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
        ], dtype=np.float64)
        mass = float(dataset["physical_candidate_dry_air_mass_measure"][cell])
        capacity = THERMO_CP_DRY + np.sum(THERMO_SPECIES_CP * species)
        old_temperature = np.float32(dataset["physical_candidate_temperature"][cell])
        new_temperature = old_temperature + np.float32(0.5)
        dataset["physical_candidate_temperature"][cell] = new_temperature
        if "candidate_temperature" in dataset.variables:
            dataset["candidate_temperature"][cell] = new_temperature
        dataset.setncattr("physical_contract_adjustable_variables", np.int32(1))
        dataset["physical_source_increment"][(*cell, 7)] = mass * capacity * 0.5

    half_kelvin = Path(directory) / "prescribed-half-kelvin-reader-control.nc"
    shutil.copyfile(source, half_kelvin)
    with netCDF4.Dataset(half_kelvin, "r+") as dataset:
        prescribed_half_kelvin_temperature_change(dataset)
    failures = replay(half_kelvin)
    assert failures == [], ("prescribed +0.5 K reader control", failures)

print("Physical SHADOW contract readback and corruption checks passed")
