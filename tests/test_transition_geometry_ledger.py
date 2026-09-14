#!/usr/bin/env python3
"""Focused tests for post-thermo transition geometry ledger replay."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_shadow_diagnostics as validator  # noqa: E402


SPECIES = validator.THERMO_SPECIES
SHAPE = (2, 1, 1)
ABOVE = np.asarray([True, False], dtype=bool).reshape(SHAPE)
CANDIDATE_ABOVE = np.ones(SHAPE, dtype=bool)
T0 = validator.THERMO_T0


def _mixture_enthalpy(temperature: np.ndarray, species: np.ndarray) -> np.ndarray:
    capacity = validator.THERMO_CP_DRY + np.sum(
        validator.THERMO_SPECIES_CP.reshape((6,) + (1,) * temperature.ndim)
        * species,
        axis=0,
    )
    reference = np.sum(
        validator.THERMO_SPECIES_H0.reshape((6,) + (1,) * temperature.ndim)
        * species,
        axis=0,
    )
    return capacity * (temperature - T0) + reference


def _independent_geometry_ledger(
    post_mass: np.ndarray,
    post_temperature: np.ndarray,
    post_species: np.ndarray,
    pressure_mass: np.ndarray,
    candidate_mass: np.ndarray,
    candidate_temperature: np.ndarray,
    candidate_species: np.ndarray,
    candidate_pressure_mass: np.ndarray,
) -> dict[str, np.ndarray | float]:
    """Compute the post-thermo -> final ledger without validator helpers."""
    old = ABOVE
    new = CANDIDATE_ABOVE
    before_mass = np.where(old, post_mass, 0.0)
    after_mass = np.where(new, candidate_mass, 0.0)
    before_temperature = np.where(old, post_temperature, T0)
    after_temperature = np.where(new, candidate_temperature, T0)
    before_species = np.where(old[None, ...], post_species, 0.0)
    after_species = np.where(new[None, ...], candidate_species, 0.0)
    before_pressure_mass = np.where(old, pressure_mass, 0.0)
    after_pressure_mass = np.where(new, candidate_pressure_mass, 0.0)

    before_h = _mixture_enthalpy(before_temperature, before_species)
    after_h = _mixture_enthalpy(after_temperature, after_species)
    dry_change = after_mass - before_mass
    geometry_change = after_pressure_mass - before_pressure_mass
    species_terms = after_mass[None, ...] * after_species - before_mass[None, ...] * before_species
    cell_error = dry_change + np.sum(species_terms, axis=0) - geometry_change
    return {
        "geometry_analysis_species_change_kg": np.sum(species_terms, axis=(1, 2, 3)),
        "geometry_analysis_mixing_ratio_change_kg": np.sum(
            before_mass[None, ...] * (after_species - before_species), axis=(1, 2, 3)
        ),
        "geometry_analysis_dry_mass_redistribution_kg": np.sum(
            dry_change[None, ...] * after_species, axis=(1, 2, 3)
        ),
        "geometry_analysis_dry_air_change_kg": float(np.sum(dry_change)),
        "geometry_analysis_enthalpy_change_j": float(
            np.sum(after_mass * after_h - before_mass * before_h)
        ),
        "geometry_analysis_geometry_mass_change_kg": float(np.sum(geometry_change)),
        "geometry_analysis_enthalpy_composition_change_j": float(
            np.sum(before_mass * (after_h - before_h))
        ),
        "geometry_analysis_enthalpy_mass_metric_change_j": float(
            np.sum(dry_change * after_h)
        ),
        "geometry_analysis_total_mass_error_kg": float(
            np.sum(dry_change) + np.sum(species_terms) - np.sum(geometry_change)
        ),
        "geometry_analysis_max_cell_mass_error_kg": float(
            np.max(np.abs(cell_error), initial=0.0)
        ),
    }


def _write_metadata(dataset: netCDF4.Dataset, prefix: str, valid: np.ndarray) -> None:
    quality = np.where(valid, 0, validator.QUALITY_EXCLUDED_BITS).astype(np.int32)
    source = valid.astype(np.int32)
    for name in SPECIES:
        for suffix, values in (
            ("valid", valid),
            ("quality", quality),
            ("source", source),
        ):
            variable = dataset.createVariable(
                f"{prefix}_{name}_{suffix}", "i4", ("z", "y", "x")
            )
            variable[:] = values


def _make_fixture(path: Path) -> dict[str, object]:
    # The pressure/dry-mass arrays deliberately contain garbage in the old
    # absent cell.  That cell becomes active only in candidate geometry.
    pressure_mass = np.asarray([100.0, np.nan], dtype=np.float64).reshape(SHAPE)
    candidate_pressure_mass = np.asarray([102.0, 8.0], dtype=np.float64).reshape(SHAPE)
    candidate_dry_air_mass = np.asarray([82.0, 6.5], dtype=np.float64).reshape(SHAPE)

    proposal_species = np.asarray(
        [
            [0.0100, 0.0500],
            [0.0030, 0.0040],
            [0.0010, 0.0020],
            [0.0020, 0.0030],
            [0.0005, 0.0010],
            [0.0002, 0.0004],
        ],
        dtype=np.float64,
    ).reshape((6,) + SHAPE)
    post_temperature = np.asarray([280.5, np.nan], dtype=np.float64).reshape(SHAPE)
    post_species = np.asarray(
        [
            [0.0120, np.nan],
            [0.0025, np.nan],
            [0.0015, np.nan],
            [0.0022, np.nan],
            [0.0004, np.nan],
            [0.0003, np.nan],
        ],
        dtype=np.float64,
    ).reshape((6,) + SHAPE)
    # The retained post-thermo mass is the proposal denominator on the old
    # cell.  The added cell's nonzero value is absent-side garbage and must be
    # masked by the original above-ground domain.
    post_mass = np.full(SHAPE, 6.0, dtype=np.float64)
    post_mass[ABOVE] = pressure_mass[ABOVE] / (1.0 + np.sum(proposal_species, axis=0)[ABOVE])
    dry_air_mass = np.where(ABOVE, post_mass, np.nan)

    candidate_temperature = np.asarray([282.0, 277.0], dtype=np.float64).reshape(SHAPE)
    candidate_species = np.asarray(
        [
            [0.0110, 0.0420],
            [0.0020, 0.0055],
            [0.0010, 0.0024],
            [0.0025, 0.0020],
            [0.0007, 0.0013],
            [0.0002, 0.0007],
        ],
        dtype=np.float64,
    ).reshape((6,) + SHAPE)
    background_temperature = np.asarray([279.0, np.nan], dtype=np.float64).reshape(SHAPE)
    background_species = np.asarray(
        [
            [0.0100, np.nan],
            [0.0030, np.nan],
            [0.0010, np.nan],
            [0.0020, np.nan],
            [0.0005, np.nan],
            [0.0002, np.nan],
        ],
        dtype=np.float64,
    ).reshape((6,) + SHAPE)

    fields: dict[str, np.ndarray] = {
        "background_temperature": background_temperature,
        "candidate_temperature": candidate_temperature,
    }
    for index, name in enumerate(SPECIES):
        fields[f"background_{name}"] = background_species[index]
        fields[f"candidate_{name}"] = candidate_species[index]

    transition_replay = {
        "proposal_species": proposal_species,
        "proposal_source": np.broadcast_to(
            ABOVE, (6,) + SHAPE
        ).astype(np.int32),
        "post_temperature": post_temperature,
        "post_species": post_species,
        "post_mass": post_mass,
        # The replay metadata retains the original valid proposal only on the
        # old cell; the added cell has no pre-transition background support.
        "post_valid": np.broadcast_to(ABOVE, (6,) + SHAPE).copy(),
        "candidate_above_ground": CANDIDATE_ABOVE.copy(),
    }

    geometry = _independent_geometry_ledger(
        post_mass,
        post_temperature,
        post_species,
        pressure_mass,
        candidate_dry_air_mass,
        candidate_temperature,
        candidate_species,
        candidate_pressure_mass,
    )
    # This is the independent thermo-stage species telescope on retained
    # cells, not a residual solved from the geometry ledger.
    thermo_species_change = np.sum(
        np.where(
            ABOVE[None, ...],
            post_mass[None, ...] * (post_species - proposal_species),
            0.0,
        ),
        axis=(1, 2, 3),
    )

    with netCDF4.Dataset(path, "w") as dataset:
        for name, length in zip(("z", "y", "x"), SHAPE):
            dataset.createDimension(name, length)
        dataset.setncattr("pressure_geometry_contract", validator.PRESSURE_GEOMETRY_CONTRACT)
        dataset.setncattr(
            "continuity_geometry_scope", validator.PRESSURE_GEOMETRY_CONTINUITY_SCOPE
        )
        dataset.setncattr("thermo_species_change_kg", thermo_species_change)
        for name, value in geometry.items():
            dataset.setncattr(name, np.asarray(value, dtype=np.float64))
        dataset.setncattr("geometry_analysis_accounted_cells", np.int64(2))
        dataset.setncattr("geometry_analysis_incomplete_background_cells", np.int64(0))
        dataset.setncattr("geometry_analysis_incomplete_candidate_cells", np.int64(0))
        _write_metadata(dataset, "background", ABOVE)
        _write_metadata(dataset, "candidate", CANDIDATE_ABOVE)

    return {
        "above": ABOVE,
        "pressure_mass": pressure_mass,
        "dry_air_mass": dry_air_mass,
        "candidate_pressure_mass": candidate_pressure_mass,
        "candidate_dry_air_mass": candidate_dry_air_mass,
        "fields": fields,
        "transition_replay": transition_replay,
    }


def _validate(path: Path, fixture: dict[str, object]) -> tuple[bool, list[str]]:
    failures: list[str] = []

    def require(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        result = validator.validate_pressure_geometry_ledger(
            dataset,
            fixture["above"],
            fixture["pressure_mass"],
            fixture["dry_air_mass"],
            fixture["candidate_pressure_mass"],
            fixture["candidate_dry_air_mass"],
            fixture["fields"],
            require,
            transition_replay=fixture["transition_replay"],
        )
    return result, failures


def test_transition_geometry_ledger_positive() -> None:
    with tempfile.TemporaryDirectory(prefix="transition-geometry-ledger-") as directory:
        path = Path(directory) / "positive.nc"
        fixture = _make_fixture(path)
        result, failures = _validate(path, fixture)
        assert result, failures
        assert not failures


def test_transition_geometry_ledger_rejects_forged_values_and_counts() -> None:
    mutations = (
        ("geometry_analysis_species_change_kg", lambda value: value + 1.0),
        ("geometry_analysis_enthalpy_change_j", lambda value: value + 1.0),
        ("geometry_analysis_accounted_cells", lambda value: value + 1),
        ("geometry_analysis_incomplete_candidate_cells", lambda value: value + 1),
    )
    for name, mutate in mutations:
        with tempfile.TemporaryDirectory(prefix="transition-geometry-ledger-") as directory:
            path = Path(directory) / "mutated.nc"
            fixture = _make_fixture(path)
            with netCDF4.Dataset(path, "r+") as dataset:
                value = np.asarray(dataset.getncattr(name)).copy()
                dataset.setncattr(name, mutate(value))
            result, failures = _validate(path, fixture)
            assert not result, name
            assert failures, name


def test_transition_geometry_ledger_rejects_remap_before_substitution() -> None:
    with tempfile.TemporaryDirectory(prefix="transition-geometry-ledger-") as directory:
        path = Path(directory) / "remap-before.nc"
        fixture = _make_fixture(path)
        # Forge the ledger by remapping before the geometry stage: use final
        # T/q as the old donor instead of the supplied post-thermo state.
        replay = fixture["transition_replay"]
        forged = _independent_geometry_ledger(
            replay["post_mass"],
            fixture["fields"]["candidate_temperature"],
            np.stack(tuple(fixture["fields"][f"candidate_{name}"] for name in SPECIES)),
            fixture["pressure_mass"],
            fixture["candidate_dry_air_mass"],
            fixture["fields"]["candidate_temperature"],
            np.stack(tuple(fixture["fields"][f"candidate_{name}"] for name in SPECIES)),
            fixture["candidate_pressure_mass"],
        )
        with netCDF4.Dataset(path, "r+") as dataset:
            for name, value in forged.items():
                dataset.setncattr(name, np.asarray(value, dtype=np.float64))
        result, failures = _validate(path, fixture)
        assert not result
        assert failures


def test_transition_geometry_ledger_requires_complete_donor() -> None:
    with tempfile.TemporaryDirectory(prefix="transition-geometry-ledger-") as directory:
        path = Path(directory) / "incomplete.nc"
        fixture = _make_fixture(path)
        fixture["transition_replay"]["post_valid"][3, 0, 0, 0] = False
        with netCDF4.Dataset(path, "r+") as dataset:
            dataset.setncattr("geometry_analysis_incomplete_background_cells", np.int64(1))
        result, failures = _validate(path, fixture)
        assert not result
        assert "geometry_analysis_incomplete_background_cells count" not in failures
        assert "pressure transition geometry species coverage" in failures


def main() -> None:
    test_transition_geometry_ledger_positive()
    test_transition_geometry_ledger_rejects_forged_values_and_counts()
    test_transition_geometry_ledger_rejects_remap_before_substitution()
    test_transition_geometry_ledger_requires_complete_donor()
    print("Transition geometry ledger tests passed")


if __name__ == "__main__":
    main()
