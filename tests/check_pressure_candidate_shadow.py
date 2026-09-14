#!/usr/bin/env python3
"""Check the pressure-analysis candidate SHADOW contract and its lineage gates."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import validate, dry_air_flux_divergence


CANDIDATE_VARIABLES = (
    "original_omega_target",
    "original_omega_target_valid",
    "original_omega_target_quality",
    "original_omega_target_source",
)


def check_partial_dry_flux_oracle() -> None:
    """A two-column terrain cut has one cross-level shared face."""
    gravity = 9.80665
    interface = np.array([[[100000., 94000.]], [[92500., 94000.]], [[87500., 87500.]]])
    cell_dp = interface[:-1] - interface[1:]
    above = cell_dp > 0.0
    fraction = np.array([[[0.8, 0.0]], [[0.7, 0.6]]])
    u = np.array([[[2., 0.]], [[4., 1.]]])
    zeros = np.zeros_like(u)
    boundary = np.zeros((1, 2))
    mass = cell_dp / gravity
    actual = dry_air_flux_divergence(
        u, zeros, zeros, boundary, boundary, above, above, 1.0, 1.0,
        np.array([95000., 90000.]), interface, cell_dp, fraction * mass, mass,
    )
    # Shared fluxes: 1650/g across levels and 8500/g within level 2.
    # External fluxes: -12000/g, -14000/g and +3900/g.
    expected = np.array([[[-10350., 0.]], [[-5500., -6250.]]]) / gravity
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-10)
    np.testing.assert_allclose(actual.sum(), -22100.0 / gravity, rtol=1e-12)


def check_dry_flux_cancellation_bound() -> None:
    """Roundoff follows transported mass, not the small signed remainder."""
    shape = (1, 1, 2)
    above = np.ones(shape, dtype=bool)
    interface = np.array([[[100000., 100000.]], [[90000., 90000.]]])
    cell_dp = interface[:-1] - interface[1:]
    mass = 2000.0 * 2200.0 * cell_dp / 9.80665
    zeros = np.zeros(shape)
    boundary = np.zeros((1, 2))

    def evaluate(speed: float):
        return dry_air_flux_divergence(
            np.full(shape, speed), zeros, zeros, boundary, boundary,
            above, above, 2000.0, 2200.0, np.array([95000.]), interface,
            cell_dp, 0.99 * mass, mass, return_roundoff=True,
        )

    residual, bound = evaluate(7.0)
    np.testing.assert_array_less(np.abs(residual), bound)
    assert np.all(bound > 1e-10), "large through-flow needs a cancellation bound"
    assert np.all(bound < 1e-4), "roundoff must not hide a 1 kg/s mutation"
    doubled, doubled_bound = evaluate(14.0)
    np.testing.assert_allclose(doubled, 2.0 * residual, atol=1e-10)
    np.testing.assert_allclose(doubled_bound, 2.0 * bound, rtol=1e-12, atol=0.0)
    still, still_bound = evaluate(0.0)
    assert np.all(still == 0.0)
    assert np.all(still_bound == 0.0)


def rewrite_without(source_path: Path, destination: Path, omitted: set[str]) -> None:
    """Copy a NetCDF file while omitting selected variables/attributes."""
    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(
        destination, "w", format=source.file_format
    ) as target:
        for name, dimension in source.dimensions.items():
            target.createDimension(name, None if dimension.isunlimited() else len(dimension))
        target.setncatts(
            {
                name: source.getncattr(name)
                for name in source.ncattrs()
                if name not in omitted
            }
        )
        for name, variable in source.variables.items():
            if name in omitted:
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
            output[...] = variable[:]


def reject(path: Path, damaged: Path, edit, label: str) -> None:
    """Apply one isolated mutation and require independent rejection."""
    shutil.copyfile(path, damaged)
    edit(damaged)
    _, failures = validate(damaged)
    assert failures, f"accepted malformed pressure candidate mutation: {label}"


def _mutate_vector_attribute(path: Path, name: str, index: int = 0) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        values = np.asarray(dataset.getncattr(name), dtype=np.float64).copy()
        values[index] += 1.0e6
        dataset.setncattr(name, values)


def _mutate_scalar_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.setncattr(name, np.float64(dataset.getncattr(name)) + 1.0e6)


def _mutate_flux_field(path: Path, name: str, replacement: float) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        values = np.asarray(dataset[name][:], dtype=np.float64)
        values.flat[0] = (
            replacement if np.isnan(replacement) else values.flat[0] + replacement
        )
        dataset[name][...] = values


def check_joint_thermo_analysis(
    path: Path,
    damaged: Path,
    summary: dict[str, object],
    schema_version: int,
) -> None:
    """Check joint pressure/thermo fixtures and their independent ledgers."""
    assert summary["analysis_ledger_validated"] is True
    assert summary["pressure_analysis_candidate_contract_validated"] is True
    assert summary["pressure_analysis_candidate_science_assessed"] is False
    assert summary["pressure_analysis_candidate_promotion_eligible"] is False
    assert summary["pressure_analysis_candidate_full_fixedpoint_independently_validated"] is False
    assert summary["outer_lineage_validated"] is (schema_version == 8)
    assert summary["outer_fixed_point_independently_validated"] is False
    assert summary["dry_air_flux_independently_validated"] is True
    assert summary["dry_air_mass_continuity_assessed"] is False

    with netCDF4.Dataset(path) as dataset:
        assert dataset.getncattr("thermo_contract") == (
            "explicit_cloud_saturation_mixture_v1"
        )
        assert dataset.getncattr("analysis_contract") == (
            "pressure_fixed_represented_mixture_v1"
        )
        support = np.asarray(dataset["thermo_support"][:], dtype=np.int32) == 1
        assert np.any(support), "joint candidate has no active thermo support"

        changes = []
        for species in ("temperature", "vapor", "cloud_water"):
            before = np.asarray(dataset[f"background_{species}"][:])
            after = np.asarray(dataset[f"candidate_{species}"][:])
            changed = before != after
            assert np.any(changed), f"joint candidate has no {species} change"
            assert np.any(changed & support), (
                f"joint candidate {species} change is outside thermo support"
            )
            changes.append(changed)
        assert np.any(np.logical_and.reduce(changes) & support), (
            "joint candidate does not change T, qv, and cloud water together"
        )

        wind_changed = np.zeros(support.shape, dtype=bool)
        for component in ("u", "v", "omega"):
            wind_changed |= (
                np.asarray(dataset[f"candidate_{component}"][:])
                != np.asarray(dataset[f"background_{component}"][:])
            )
        assert np.any(wind_changed), "joint candidate has no actual wind change"

        assert dataset.getncattr("dry_air_flux_contract") == (
            "pressure_fixed_dry_advection_v1"
        )
        assert dataset.getncattr("dry_air_flux_boundary") == (
            "nearest_interior_composition"
        )
        assert int(dataset.getncattr("dry_air_mass_tendency_assessed")) == 0
        dry_air_fluxes = {}
        for name in (
            "background_dry_air_flux_divergence",
            "candidate_dry_air_flux_divergence",
        ):
            variable = dataset[name]
            assert np.dtype(variable.dtype) == np.dtype(np.float64)
            assert variable.dimensions == ("z", "y", "x")
            assert variable.getncattr("units") == "kg s-1"
            dry_air_fluxes[name] = np.asarray(variable[:], dtype=np.float64)
        assert np.all(np.isfinite(dry_air_fluxes["background_dry_air_flux_divergence"]))
        assert np.all(np.isfinite(dry_air_fluxes["candidate_dry_air_flux_divergence"]))
        assert np.any(
            dry_air_fluxes["candidate_dry_air_flux_divergence"]
            != dry_air_fluxes["background_dry_air_flux_divergence"]
        ), "joint candidate has no actual dry-air flux divergence change"

        if schema_version == 8:
            assert int(dataset.getncattr("outer_maximum_iterations")) == 16
            outer_iterations = int(dataset.getncattr("outer_iterations"))
            assert 2 <= outer_iterations <= 16
            outer_history = np.asarray(
                dataset.getncattr("outer_max_abs_delta"), dtype=np.float64
            )
            assert outer_history.shape == (5 * outer_iterations,)
            assert np.any(outer_history[:5] != 0.0)
            assert np.all(outer_history[-5:] == 0.0)

    # These are intentionally bounded mutations: one independent thermo
    # budget, one analysis ledger, one false contract, and one outer history.
    reject(
        path,
        damaged,
        lambda output: _mutate_vector_attribute(
            output, "thermo_species_change_kg"
        ),
        "thermo species budget",
    )
    reject(
        path,
        damaged,
        lambda output: _mutate_vector_attribute(
            output, "analysis_species_change_kg"
        ),
        "analysis species ledger",
    )
    reject(
        path,
        damaged,
        lambda output: _mutate_scalar_attribute(
            output, "analysis_enthalpy_change_j"
        ),
        "analysis enthalpy ledger",
    )
    reject(
        path,
        damaged,
        lambda output: _set_attribute(
            output, "thermo_contract", "forged"
        ),
        "false thermo metadata",
    )
    reject(
        path,
        damaged,
        lambda output: _set_attribute(
            output, "analysis_contract", "forged"
        ),
        "false analysis metadata",
    )

    for name in (
        "background_dry_air_flux_divergence",
        "candidate_dry_air_flux_divergence",
    ):
        reject(
            path,
            damaged,
            lambda output, field=name: _mutate_flux_field(output, field, 1.0),
            f"{name} bounded mutation",
        )
        reject(
            path,
            damaged,
            lambda output, field=name: _mutate_flux_field(output, field, np.nan),
            f"{name} NaN mutation",
        )
        rewrite_without(path, damaged, {name})
        _, failures = validate(damaged)
        assert failures, f"accepted missing dry-air flux variable: {name}"

    reject(
        path,
        damaged,
        lambda output: _set_attribute(
            output, "dry_air_flux_boundary", "forged"
        ),
        "false dry-air flux boundary metadata",
    )
    reject(
        path,
        damaged,
        lambda output: _set_attribute(
            output, "dry_air_flux_contract", "forged"
        ),
        "false dry-air flux contract metadata",
    )
    reject(
        path,
        damaged,
        lambda output: _set_attribute(
            output, "dry_air_mass_tendency_assessed", np.int32(1)
        ),
        "false dry-air mass tendency claim",
    )

    # Historical joint artifacts remain readable, but cannot gain a new
    # independent flux claim without the complete persisted extension.
    rewrite_without(path, damaged, {
        "background_dry_air_flux_divergence", "candidate_dry_air_flux_divergence",
        "dry_air_flux_contract", "dry_air_flux_boundary",
        "dry_air_mass_tendency_assessed",
    })
    historical_summary, failures = validate(damaged)
    assert not failures, failures
    assert historical_summary["dry_air_flux_independently_validated"] is False
    assert historical_summary["dry_air_mass_continuity_assessed"] is False

    if schema_version == 8:
        def mutate_outer_history(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                values = np.asarray(
                    dataset.getncattr("outer_max_abs_delta"), dtype=np.float64
                ).copy()
                values[-1] = 1.0
                dataset.setncattr("outer_max_abs_delta", values)

        reject(path, damaged, mutate_outer_history, "outer history")
        reject(
            path,
            damaged,
            lambda output: _set_attribute(output, "outer_converged", np.int32(0)),
            "false outer convergence metadata",
        )


def check(path: Path) -> None:
    check_partial_dry_flux_oracle()
    check_dry_flux_cancellation_bound()
    summary, failures = validate(path)
    assert not failures, failures
    assert summary["pressure_geopotential_independently_validated"] is False
    assert summary["pressure_geopotential_native_assessed"] is False

    with netCDF4.Dataset(path) as dataset:
        assert int(dataset.getncattr("cloud_bal_schema_version")) == 5
        schema_version = int(dataset.getncattr("diagnostic_schema_version"))
        assert schema_version in (5, 7, 8)
        assert dataset.getncattr("pressure_analysis_candidate_contract") == (
            "pressure_analysis_candidate_v1"
        )
        assert dataset.getncattr("contract") == "pressure_analysis_shadow_v1"
        assert dataset.getncattr("evidence_class") == "PRESSURE_ANALYSIS_SHADOW_PROPOSAL"
        assert dataset.getncattr("configuration_id") == "pressure-analysis-shadow-v1"
        assert dataset.getncattr("omega_boundary_provenance") == (
            "PHYSICAL_INPUT_DIAGNOSTIC_ONLY"
        )
        assert dataset.getncattr("result_authority") == "DIAGNOSTIC_PROPOSAL_ONLY"
        # The dedicated contract attribute versions this opt-in extension;
        # schema_extensions still describes the unchanged base schema.
        assert dataset.getncattr("omega_target_error_contract") == (
            "diagonal_pressure_omega_v1"
        )
        assert summary["omega_target_error_contract_present"] is True
        assert summary["omega_target_error_contract_validated"] is True

        for attribute in ("promotion_eligible", "operational_state_changed", "science_assessed"):
            assert int(dataset.getncattr(attribute)) == 0

        background_u = np.asarray(dataset["background_u"][:], dtype=np.float32)
        background_v = np.asarray(dataset["background_v"][:], dtype=np.float32)
        background_omega = np.asarray(dataset["background_omega"][:], dtype=np.float32)
        candidate_u = np.asarray(dataset["candidate_u"][:], dtype=np.float32)
        candidate_v = np.asarray(dataset["candidate_v"][:], dtype=np.float32)
        candidate_omega = np.asarray(dataset["candidate_omega"][:], dtype=np.float32)
        balance_changed = np.asarray(dataset["balance_changed"][:], dtype=np.int32)
        delta = (
            (candidate_u != background_u)
            | (candidate_v != background_v)
            | (candidate_omega != background_omega)
        )
        assert np.any(delta), "candidate fixture has no actual balance delta"
        assert np.any(balance_changed), "candidate fixture has no balance-change evidence"

        for side in ("top", "bottom"):
            assert np.all(dataset[f"omega_{side}_boundary_valid"][:] == 1)
            assert np.all(dataset[f"omega_{side}_boundary_quality"][:] == 0)
            assert np.all(
                dataset[f"omega_{side}_boundary_source"][:] == np.int32(1 << 11)
            )

        sigma_valid = np.asarray(dataset["omega_target_sigma_valid"][:], dtype=np.int32)
        sigma_value = np.asarray(dataset["omega_target_sigma"][:], dtype=np.float32)
        sigma_cells = np.argwhere(sigma_valid == 1)
        assert sigma_cells.size, "candidate fixture has no usable sigma cell"
        assert np.all(np.isfinite(sigma_value[sigma_valid == 1]))
        assert np.all(sigma_value[sigma_valid == 1] > 0.0)

        original_valid = np.asarray(
            dataset["original_omega_target_valid"][:], dtype=np.int32
        )
        target_cells = np.argwhere(original_valid == 1)
        assert target_cells.size, "candidate fixture has no immutable target cell"
        target_cell = tuple(target_cells[0])
        sigma_cell = tuple(sigma_cells[0])
        boundary_cell = (0, 0)

        for name in CANDIDATE_VARIABLES:
            variable = dataset[name]
            expected_dtype = np.dtype(np.float32 if name == "original_omega_target" else np.int32)
            expected_units = "Pa s-1" if name == "original_omega_target" else "1"
            assert np.dtype(variable.dtype) == expected_dtype
            assert variable.dimensions == ("z", "y", "x")
            assert variable.getncattr("units") == expected_units
            assert np.array_equal(
                np.asarray(dataset[name][:]),
                np.asarray(dataset[name[len("original_") :]][:]),
            ), f"{name} is not an immutable copy of the input"
        assert np.asarray(dataset["original_omega_target"].getncattr("valid_time")).dtype == np.dtype(np.int64)

    with tempfile.TemporaryDirectory(prefix="pressure-candidate-shadow-mutations-") as directory:
        damaged = Path(directory) / "candidate.nc"

        # Candidate extension identity, completeness, versioning, and removal.
        reject(
            path,
            damaged,
            lambda output: _delete_attribute(output, "pressure_analysis_candidate_contract"),
            "missing candidate contract",
        )
        rewrite_without(path, damaged, {"original_omega_target_source"})
        _, failures = validate(damaged)
        assert failures, "accepted partial candidate extension"

        def mutate_extension_version(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset.setncattr("pressure_analysis_candidate_contract", "pressure_analysis_candidate_v0")

        reject(path, damaged, mutate_extension_version, "candidate extension version")
        rewrite_without(path, damaged, {"schema_extensions"})
        _, failures = validate(damaged)
        assert failures, "accepted candidate without extension version"
        rewrite_without(path, damaged, set(CANDIDATE_VARIABLES) | {"pressure_analysis_candidate_contract"})
        _, failures = validate(damaged)
        assert failures, "accepted pressure candidate with stripped extension"

        # Immutable original target payload and provenance.
        def mutate_original_value(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["original_omega_target"][target_cell] += np.float32(1.0)

        def mutate_original_valid(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["original_omega_target_valid"][target_cell] = np.int32(0)

        def mutate_original_quality(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["original_omega_target_quality"][target_cell] = np.int32(1)

        def mutate_original_source(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["original_omega_target_source"][target_cell] = np.int32(1 << 20)

        for label, edit in (
            ("original target value", mutate_original_value),
            ("original target valid", mutate_original_valid),
            ("original target quality", mutate_original_quality),
            ("original target source", mutate_original_source),
        ):
            reject(path, damaged, edit, label)

        # Sigma must be positive, finite, and have usable provenance when valid.
        for label, value in (("sigma zero", np.float32(0.0)), ("sigma NaN", np.float32(np.nan))):
            def mutate_sigma(output: Path, replacement=value) -> None:
                with netCDF4.Dataset(output, "r+") as dataset:
                    dataset["omega_target_sigma"][sigma_cell] = replacement

            reject(path, damaged, mutate_sigma, label)

        def mutate_sigma_source(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["omega_target_sigma_source"][sigma_cell] = np.int32(1 << 20)

        reject(path, damaged, mutate_sigma_source, "sigma provenance")

        # Physical input boundaries are complete and must retain physical lineage.
        for name, value, label in (
            ("omega_top_boundary_valid", np.int32(0), "physical boundary valid"),
            ("omega_top_boundary_source", np.int32(0), "physical boundary source"),
            ("omega_top_boundary_quality", np.int32(1), "physical boundary quality"),
            ("omega_top_boundary", np.float32(np.nan), "physical boundary value"),
            ("omega_top_boundary", np.float32(0.1), "physical boundary finite flux"),
        ):
            def mutate_boundary(output: Path, field=name, replacement=value) -> None:
                with netCDF4.Dataset(output, "r+") as dataset:
                    dataset[field][boundary_cell] = replacement

            reject(path, damaged, mutate_boundary, label)

        reject(
            path,
            damaged,
            lambda output: _set_attribute(
                output, "omega_boundary_provenance", "COPIED_INTERIOR_DIAGNOSTIC_ONLY"
            ),
            "boundary provenance mismatch",
        )

        def mutate_residual(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                dataset["continuity_candidate"][target_cell] += np.float64(1.0)

        reject(path, damaged, mutate_residual, "continuity residual")

        def mutate_acceptance_bits(output: Path) -> None:
            with netCDF4.Dataset(output, "r+") as dataset:
                current = int(dataset.getncattr("acceptance_failures"))
                dataset.setncattr("acceptance_failures", np.int32(current ^ 1))

        reject(path, damaged, mutate_acceptance_bits, "acceptance failure bits")
        for attribute in ("promotion_eligible", "operational_state_changed", "science_assessed"):
            reject(
                path,
                damaged,
                lambda output, name=attribute: _set_attribute(output, name, np.int32(1)),
                attribute,
            )

        if schema_version in (7, 8):
            check_joint_thermo_analysis(path, damaged, summary, schema_version)

    print("Pressure-analysis candidate SHADOW round-trip and mutation checks passed")


def _delete_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.delncattr(name)


def _set_attribute(path: Path, name: str, value: object) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.setncattr(name, value)


if __name__ == "__main__":
    check(Path(sys.argv[1]))
