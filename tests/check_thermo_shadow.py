#!/usr/bin/env python3
"""Check schema-7/8 thermo diagnostics and reject damaged copies."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import validate


ERROR_GROUP_VARIABLES = (
    "omega_target_sigma",
    "omega_target_sigma_valid",
    "omega_target_sigma_quality",
    "omega_target_sigma_source",
)


def copy_without_error_group(source_path: Path, destination: Path) -> None:
    """Create a schema-3 fixture without the newer sigma and surface groups."""
    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(
        destination, "w", format=source.file_format
    ) as target:
        for name, dimension in source.dimensions.items():
            target.createDimension(name, None if dimension.isunlimited() else len(dimension))
        target.setncatts(
            {
                name: source.getncattr(name)
                for name in source.ncattrs()
                if name not in ("omega_target_error_contract", "surface_boundary_contract")
            }
        )
        target.setncattr("cloud_bal_schema_version", np.int32(3))
        for name, variable in source.variables.items():
            if name in ERROR_GROUP_VARIABLES or name.startswith((
                "background_surface_", "candidate_surface_"
            )):
                continue
            output = target.createVariable(
                name,
                variable.datatype,
                variable.dimensions,
                zlib=False,
                fill_value=False,
            )
            output.setncatts(
                {
                    attribute: variable.getncattr(attribute)
                    for attribute in variable.ncattrs()
                    if attribute != "_FillValue"
                }
            )
            output[...] = variable[...]


def check_omega_target_error_group(path: Path, damaged: Path) -> int:
    """Exercise optional-group compatibility, metadata, and authority gates."""
    checks = 0
    with netCDF4.Dataset(path) as source:
        has_group = (
            "omega_target_error_contract" in source.ncattrs()
            or any(name in source.variables for name in ERROR_GROUP_VARIABLES)
        )
        expected_canonical = 5 if "surface_boundary_contract" in source.ncattrs() else (4 if has_group else 3)
        assert source.getncattr("cloud_bal_schema_version") == expected_canonical

    for label, value in (
        ("unknown-low", np.int32(2)),
        ("unknown-high", np.int32(6)),
        ("wrong-type", np.float64(expected_canonical)),
        ("missing", None),
    ):
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            if value is None:
                dataset.delncattr("cloud_bal_schema_version")
            else:
                dataset.setncattr("cloud_bal_schema_version", value)
        _, failures = validate(damaged)
        assert failures, f"accepted {label} canonical schema version"
        checks += 1

    with netCDF4.Dataset(path) as source:
        if not has_group:
            summary, failures = validate(path)
            assert not failures, failures
            assert summary["canonical_schema_version"] == expected_canonical
            assert summary["omega_target_error_contract_present"] is False
            assert summary["omega_target_error_contract_validated"] is False
            return checks

        assert "omega_target_error_contract" in source.ncattrs()
        assert set(ERROR_GROUP_VARIABLES) <= set(source.variables)
        assert source.getncattr("cloud_bal_schema_version") == expected_canonical
        assert source.getncattr("omega_target_error_contract") == "diagonal_pressure_omega_v1"
        summary, failures = validate(path)
        assert not failures, failures
        assert summary["omega_target_error_contract_present"] is True
        assert summary["omega_target_error_contract_validated"] is True
        checks += 1

    # A complete removal is a readable historical artifact, but it cannot
    # claim that the calibrated target-error contract was validated.
    copy_without_error_group(path, damaged)
    summary, failures = validate(damaged)
    assert not failures, failures
    assert summary["omega_target_error_contract_present"] is False
    assert summary["omega_target_error_contract_validated"] is False
    checks += 1

    mutations = (
        ("omega_target_error_contract", "forged"),
        ("omega_target_sigma", "units", "m s-1"),
        ("omega_target_sigma", "valid_time", -1),
    )
    for mutation in mutations:
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            if len(mutation) == 2:
                dataset.setncattr(mutation[0], mutation[1])
            else:
                dataset[mutation[0]].setncattr(mutation[1], mutation[2])
        _, failures = validate(damaged)
        assert failures, f"accepted omega target error metadata mutation {mutation}"
        checks += 1

    with netCDF4.Dataset(path) as source:
        sigma_valid = np.asarray(source["omega_target_sigma_valid"][:], dtype=np.int32)
        cells = np.argwhere(np.asarray(source["above_ground"][:], dtype=np.int32) == 1)
        assert cells.size
        cell = tuple(cells[0])
        valid_cells = np.argwhere(sigma_valid == 1)
        valid_cell = tuple(valid_cells[0]) if valid_cells.size else cell
        authority = np.asarray(source["omega_target_authority"][:], dtype=np.int32)
        zero_authority = np.argwhere(authority == 0)
        authority_cell = tuple(zero_authority[0]) if zero_authority.size else cell
        authority_value = np.int32(1 if zero_authority.size else 0)

    # Valid sigma must be finite and strictly positive, and its provenance
    # must be known/usable.  These mutations exercise zero/NaN and source/QC
    # fail-closed behavior even when the normal fixture has no target cells.
    for name, value in (
        ("omega_target_sigma", np.float32(0.0)),
        ("omega_target_sigma", np.float32(np.nan)),
    ):
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            dataset["omega_target_sigma_valid"][valid_cell] = np.int32(1)
            dataset[name][valid_cell] = value
        _, failures = validate(damaged)
        assert failures, f"accepted malformed sigma value {value}"
        checks += 1

    for name, value in (
        ("omega_target_sigma_source", np.int32(1 << 20)),
        ("omega_target_sigma_quality", np.int32(1)),
    ):
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            dataset["omega_target_sigma_valid"][valid_cell] = np.int32(1)
            dataset["omega_target_sigma"][valid_cell] = np.float32(1.0)
            dataset[name][valid_cell] = value
        _, failures = validate(damaged)
        assert failures, f"accepted malformed sigma metadata {name}"
        checks += 1

    shutil.copyfile(path, damaged)
    with netCDF4.Dataset(damaged, "r+") as dataset:
        dataset["omega_target_source"][cell] = np.int32(1 << 20)
    _, failures = validate(damaged)
    assert failures, "accepted tampered omega target source mask"
    checks += 1

    shutil.copyfile(path, damaged)
    with netCDF4.Dataset(damaged, "r+") as dataset:
        dataset["omega_target_authority"][authority_cell] = authority_value
    _, failures = validate(damaged)
    assert failures, "accepted tampered omega target authority"
    checks += 1
    return checks


def check(path: Path) -> None:
    summary, failures = validate(path)
    assert not failures, failures
    with netCDF4.Dataset(path) as dataset:
        schema_version = int(dataset.getncattr("diagnostic_schema_version"))
        assert schema_version in (7, 8)
        assert summary["outer_lineage_validated"] is (schema_version == 8)
        assert summary["outer_fixed_point_independently_validated"] is False
        assert summary["outer_validation_scope"] == (
            "METADATA_ONLY_PRODUCER_REPLAY_NOT_REEXECUTED"
            if schema_version == 8 else "NONE"
        )
        reconstruction_present = (
            "radar_reconstruction_contract" in dataset.ncattrs()
            or "column_minimum_dbz" in dataset.ncattrs()
            or any(
                name in dataset.variables
                for name in (
                    "background_precipitation_phase",
                    "background_precipitation_phase_valid",
                    "background_precipitation_phase_quality",
                    "background_precipitation_phase_source",
                )
            )
        )
        assert summary["radar_reconstruction_independently_validated"] is (
            schema_version == 8 and reconstruction_present
        )
        selected = tuple(np.argwhere(dataset["thermo_support"][:] == 1)[0])
        outside = tuple(np.argwhere(dataset["thermo_support"][:] == 0)[0])

    mutations = [
        ("candidate_temperature", selected, 1.0),
        ("candidate_vapor", selected, 0.001),
        ("candidate_cloud_water", selected, 0.001),
        ("candidate_cloud_ice", selected, 0.001),
        ("candidate_temperature", outside, 1.0),
        ("candidate_temperature_source", selected, 1 << 10),
        ("candidate_temperature_source", selected, -(1 << 7)),
        ("candidate_vapor_quality", selected, 1),
        ("candidate_rain_quality", outside, 1),
        ("background_cloud_water_valid", selected, -1),
        ("thermo_support", selected, -1),
        ("thermo_surface", selected, 9),
        ("candidate_dry_air_mass_measure", selected, 1.0e6),
        ("candidate_rain_valid", selected, -1),
        ("background_vapor_valid", selected, -1),
    ]
    with tempfile.TemporaryDirectory(prefix="thermo-shadow-mutations-") as directory:
        damaged = Path(directory) / "candidate.nc"
        checks = check_omega_target_error_group(path, damaged)
        for name, cell, increment in mutations:
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset[name][cell] += increment
            _, failures = validate(damaged)
            assert failures, f"accepted corrupted {name}"
            checks += 1
        for attribute in (
            "thermo_target_rh", "thermo_sensible_change_j", "thermo_phase_change_j",
            "thermo_water_error_kg", "thermo_enthalpy_error_j",
        ):
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.setncattr(attribute, np.nan)
            _, failures = validate(damaged)
            assert failures, f"accepted nonfinite {attribute}"
            checks += 1
        for species in range(6):
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                budget = dataset.getncattr("thermo_species_change_kg").copy()
                budget[species] += 1.0e6
                dataset.setncattr("thermo_species_change_kg", budget)
            _, failures = validate(damaged)
            assert failures, f"accepted corrupted species budget {species}"
            checks += 1

        for attribute in (
            "analysis_species_change_kg", "analysis_mixing_ratio_change_kg",
            "analysis_dry_mass_redistribution_kg",
        ):
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                budget = dataset.getncattr(attribute).copy()
                budget[0] += 1.0e6
                dataset.setncattr(attribute, budget)
            _, failures = validate(damaged)
            assert failures, f"accepted corrupted {attribute}"
            checks += 1
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.delncattr(attribute)
            _, failures = validate(damaged)
            assert failures, f"accepted missing {attribute}"
            checks += 1

        for attribute in (
            "analysis_dry_air_change_kg", "analysis_enthalpy_change_j",
            "analysis_total_mass_error_kg", "analysis_max_cell_mass_error_kg",
        ):
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.setncattr(attribute, np.nan)
            _, failures = validate(damaged)
            assert failures, f"accepted nonfinite {attribute}"
            checks += 1
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.delncattr(attribute)
            _, failures = validate(damaged)
            assert failures, f"accepted missing {attribute}"
            checks += 1

        for attribute in (
            "analysis_accounted_cells", "analysis_incomplete_background_cells",
            "analysis_incomplete_candidate_cells",
        ):
            with netCDF4.Dataset(path) as source:
                count = int(source.getncattr(attribute))
            count_mutations = (
                ("increment", np.int64(count + 1)),
                ("fractional", np.float64(count + 0.5)),
                ("wrong-type", np.int32(count)),
                ("vector", np.asarray((count, count), dtype=np.int64)),
                ("missing", None),
            )
            for label, value in count_mutations:
                shutil.copyfile(path, damaged)
                with netCDF4.Dataset(damaged, "r+") as dataset:
                    if label == "missing":
                        dataset.delncattr(attribute)
                    else:
                        dataset.setncattr(attribute, value)
                _, failures = validate(damaged)
                assert failures, f"accepted {label} {attribute} mutation"
                checks += 1

        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            dataset.setncattr("analysis_contract", "forged")
        _, failures = validate(damaged)
        assert failures, "accepted forged analysis contract"
        checks += 1
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            dataset.delncattr("analysis_contract")
        _, failures = validate(damaged)
        assert failures, "accepted missing analysis contract"
        checks += 1

        if schema_version == 8:
            with netCDF4.Dataset(path) as source:
                outer_iterations = int(source.getncattr("outer_iterations"))
                outer_delta = np.asarray(
                    source.getncattr("outer_max_abs_delta"), dtype=np.float64
                )
            assert outer_delta.shape == (5 * outer_iterations,)
            assert np.all(np.isfinite(outer_delta))
            assert np.all(outer_delta >= 0.0)
            assert np.all(outer_delta[-5:] == 0.0)
            assert summary["outer_lineage_validated"] is True

            outer_mutations = [
                ("outer_maximum_iterations", np.int32(1)),
                ("outer_iterations", np.int32(0)),
                ("outer_converged", np.int32(0)),
                ("outer_feedback_fields", "forged"),
                ("outer_feedback_units", "forged"),
                ("outer_max_abs_delta", np.asarray((np.nan,), dtype=np.float64)),
                ("outer_max_abs_delta", np.asarray((-1.0,), dtype=np.float64)),
                ("outer_max_abs_delta", np.zeros(1, dtype=np.float64)),
            ]
            for attribute, value in outer_mutations:
                shutil.copyfile(path, damaged)
                with netCDF4.Dataset(damaged, "r+") as dataset:
                    dataset.setncattr(attribute, value)
                _, failures = validate(damaged)
                assert failures, f"accepted corrupted {attribute}"
                checks += 1

            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                values = np.asarray(dataset.getncattr("outer_max_abs_delta"))
                values[-1] = 1.0
                dataset.setncattr("outer_max_abs_delta", values)
            _, failures = validate(damaged)
            assert failures, "accepted nonconverged final outer trial"
            checks += 1

            if outer_iterations > 1:
                shutil.copyfile(path, damaged)
                with netCDF4.Dataset(damaged, "r+") as dataset:
                    values = np.asarray(dataset.getncattr("outer_max_abs_delta"))
                    values[:5] = 0.0
                    dataset.setncattr("outer_max_abs_delta", values)
                _, failures = validate(damaged)
                assert failures, "accepted outer trial without progress"
                checks += 1

            # Schema-8 lineage attributes are reserved and cannot survive a
            # downgrade to an otherwise valid schema-7 identity.
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.setncattr("diagnostic_schema_version", np.int32(7))
                dataset.setncattr("contract", "real_radar_thermo_shadow_v2")
                dataset.setncattr("configuration_id", "pressure-thermo-shadow-v2")
                dataset.setncattr(
                    "schema_extensions",
                    "verified_operational_identity_v1,radar_no_echo_masks_v1,"
                    "pressure_geometry_v2,omega_boundary_contract_v2,"
                    "pressure_thermo_v1,pressure_analysis_v1",
                )
            _, failures = validate(damaged)
            assert failures, "accepted schema-7 file with reserved outer attributes"
            checks += 1

        # A schema-7 file partially downgraded to the strict legacy identity
        # must not silently carry the reserved analysis ledger attributes.
        shutil.copyfile(path, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            dataset.setncattr("diagnostic_schema_version", np.int32(6))
            dataset.setncattr("contract", "real_radar_thermo_shadow_v1")
            dataset.setncattr("configuration_id", "pressure-thermo-shadow-v1")
            dataset.setncattr(
                "schema_extensions",
                "verified_operational_identity_v1,radar_no_echo_masks_v1,"
                "pressure_geometry_v2,omega_boundary_contract_v2,pressure_thermo_v1",
            )
        _, failures = validate(damaged)
        assert failures, "accepted partial schema-7 downgrade"
        checks += 1
        for name, attribute, value in (
            ("candidate_temperature_source", "scale_factor", 0.5),
            ("candidate_vapor", "units", "kg kg-1 moistair"),
            ("thermo_support", "units", "Pa"),
            ("candidate_temperature", "valid_time", -1),
            ("candidate_temperature", "valid_time", 1788224400.5),
        ):
            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset[name].setncattr(attribute, value)
            _, failures = validate(damaged)
            assert failures, f"accepted corrupted {name} {attribute}"
            checks += 1

        if reconstruction_present:
            # The optional radar replay group is self-identifying and must be
            # checked independently of the thermo/continuity ledgers.
            with netCDF4.Dataset(path) as source:
                phase_valid = np.asarray(
                    source["background_precipitation_phase_valid"][:], dtype=np.int32
                )
                phase_cells = np.argwhere(phase_valid == 1)
                radar_phase_cells = np.argwhere(
                    (phase_valid == 1) & (np.asarray(source["radar_valid"][:]) == 1)
                )
                phase_cell = (
                    tuple((radar_phase_cells if radar_phase_cells.size else phase_cells)[0])
                    if phase_cells.size else None
                )

            if phase_cell is not None:
                reference_mutations = [
                    ("background_precipitation_phase", phase_cell, np.int32(99)),
                    ("background_precipitation_phase_quality", phase_cell, np.int32(-1)),
                ]
                for name, cell, value in reference_mutations:
                    shutil.copyfile(path, damaged)
                    with netCDF4.Dataset(damaged, "r+") as dataset:
                        dataset[name][cell] = value
                    _, failures = validate(damaged)
                    assert failures, f"accepted radar replay mutation {name}"
                    checks += 1

            with netCDF4.Dataset(path) as source:
                precip_mutation = None
                for species in ("rain", "snow", "graupel"):
                    values = np.asarray(source[f"candidate_{species}"][:], dtype=np.float32)
                    cells = np.argwhere(values > 0.0)
                    if cells.size:
                        precip_mutation = (f"candidate_{species}", tuple(cells[0]))
                        break
            if precip_mutation is not None:
                name, cell = precip_mutation
                shutil.copyfile(path, damaged)
                with netCDF4.Dataset(damaged, "r+") as dataset:
                    dataset[name][cell] *= np.float32(1.01)
                _, failures = validate(damaged)
                assert failures, f"accepted 1% radar precipitation mutation {name}"
                checks += 1

            for attribute, value in (
                ("radar_reconstruction_contract", "pressure_radar_reconstruction_v1"),
                ("column_minimum_dbz", np.float64(np.nan)),
                ("flux_input", np.float64(float("nan"))),
            ):
                shutil.copyfile(path, damaged)
                with netCDF4.Dataset(damaged, "r+") as dataset:
                    dataset.setncattr(attribute, value)
                _, failures = validate(damaged)
                assert failures, f"accepted radar replay mutation {attribute}"
                checks += 1

            shutil.copyfile(path, damaged)
            with netCDF4.Dataset(damaged, "r+") as dataset:
                dataset.setncattr(
                    "flux_input",
                    np.float64(float(dataset.getncattr("flux_input")) + 1.0),
                )
                dataset.setncattr(
                    "flux_deposited",
                    np.float64(float(dataset.getncattr("flux_deposited")) + 1.0),
                )
            _, failures = validate(damaged)
            assert failures, "accepted balanced-total radar ledger tamper"
            checks += 1
    print(f"Thermo SHADOW round-trip and {checks} mutation checks passed")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
