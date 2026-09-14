#!/usr/bin/env python3
"""Focused tests for original-input pressure-transition replay residuals."""

from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_shadow_diagnostics as validator  # noqa: E402
from pressure_transition_reference import (  # noqa: E402
    reconstruct_thermo_state_reference,
    remap_pressure_state_reference,
)


SHAPE = (3, 1, 1)
SPECIES = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
PHASE_SPECIES = SPECIES[:3]
PRECIP_SPECIES = SPECIES[3:]
GRAVITY = 9.80665


def make_fixture(path: Path):
    old_surface_pressure = 99999.125
    new_surface_pressure = 100000.125
    old_interfaces = np.array(
        [old_surface_pressure, old_surface_pressure, 92500.0, 87500.0]
    )[:, None, None]
    new_interfaces = np.array(
        [new_surface_pressure, 97500.0, 92500.0, 87500.0]
    )[:, None, None]
    old_above = np.array([False, True, True], dtype=bool)[:, None, None]
    new_above = np.ones(SHAPE, dtype=bool)
    pressure = np.array([100000.0, 95000.0, 90000.0])
    background_temperature = np.array([279.0, 280.0, 282.0])[:, None, None]
    proposal_species = np.zeros((6, *SHAPE), dtype=np.float64)
    proposal_species[:, 1, 0, 0] = [0.01, 0.002, 0.0, 0.001, 0.0, 0.0]
    proposal_species[:, 2, 0, 0] = [0.008, 0.001, 0.0, 0.0, 0.0005, 0.0]
    # This is the pressure metric dp/g; thermo derives dry mass from q.
    pressure_mass = np.where(
        old_above, (old_interfaces[:-1] - old_interfaces[1:]) / GRAVITY, 0.0
    )
    support = np.zeros(SHAPE, dtype=bool)
    surface = np.zeros(SHAPE, dtype=np.int32)
    post_temperature, post_species, post_mass = reconstruct_thermo_state_reference(
        np.broadcast_to(pressure[:, None, None], SHAPE), pressure_mass, background_temperature,
        np.where(old_above, proposal_species, 0.0), support, surface, 0.8,
    )
    seed_temperature = post_temperature.copy()
    seed_species = post_species.copy()
    seed_species[:, 0, 0, 0] = [0.012, 0.003, 0.0, 0.0, 0.0, 0.0]
    final_mass, final_temperature, final_species = remap_pressure_state_reference(
        old_interfaces, post_mass, post_temperature, post_species, old_above,
        new_interfaces, new_above, np.ones((1, 1)), seed_temperature, seed_species,
    )
    candidate_pressure_mass = (
        new_interfaces[:-1] - new_interfaces[1:]
    ) / GRAVITY
    seed_dry_mass = candidate_pressure_mass / (
        1.0 + np.sum(seed_species, axis=0)
    )
    seed_dry_mass[~new_above] = 0.0

    with netCDF4.Dataset(path, "w") as dataset:
        for name, length in zip(("z", "y", "x"), SHAPE):
            dataset.createDimension(name, length)
        dataset.setncattr("column_minimum_dbz", np.float64(10.0))
        dataset.setncattr("thermo_target_rh", np.float64(0.8))
        dataset.setncattr("thermo_species_change_kg", np.zeros(6, dtype=np.float64))
        for name in ("thermo_sensible_change_j", "thermo_phase_change_j",
                     "thermo_water_error_kg", "thermo_enthalpy_error_j"):
            dataset.setncattr(name, np.float64(0.0))
        dataset.setncattr("grid_dx_m", np.float64(1.0))
        dataset.setncattr("grid_dy_m", np.float64(1.0))
        for name, values in (
            ("dry_air_mass_measure", post_mass),
            ("candidate_pressure_mass_measure", candidate_pressure_mass),
        ):
            variable = dataset.createVariable(name, "f8", ("z", "y", "x"))
            variable[:] = values
        for name, values in (
            ("thermo_support", support.astype(np.int32)),
            ("thermo_surface", surface),
        ):
            variable = dataset.createVariable(name, "i4", ("z", "y", "x"))
            variable[:] = values
        for name in PHASE_SPECIES:
            for suffix, values in (
                ("valid", np.ones(SHAPE, dtype=np.int32)),
                ("source", np.ones(SHAPE, dtype=np.int32)),
                ("quality", np.zeros(SHAPE, dtype=np.int32)),
            ):
                variable = dataset.createVariable(
                    f"background_{name}_{suffix}", "i4", ("z", "y", "x")
                )
                variable[:] = values

    fields = {"background_temperature": background_temperature.copy(),
              "candidate_temperature": final_temperature.copy()}
    for index, name in enumerate(PHASE_SPECIES):
        fields[f"background_{name}"] = proposal_species[index].copy()
    for index, name in enumerate(SPECIES):
        fields[f"candidate_{name}"] = final_species[index].copy()
    masks = {"above_ground": old_above.copy()}
    transition = {
        "candidate_above_ground": new_above.copy(),
        "transition_seed_above_ground": new_above.copy(),
        "transition_seed_pressure": np.broadcast_to(
            pressure[:, None, None], SHAPE
        ).copy(),
        "transition_seed_surface_pressure": np.full(
            (1, 1), new_surface_pressure
        ),
        "transition_seed_dry_air_mass_measure": seed_dry_mass.copy(),
        "transition_seed_temperature": seed_temperature.copy(),
    }
    for index, name in enumerate(SPECIES):
        transition[f"transition_seed_{name}"] = seed_species[index].copy()
    geometry = {
        "candidate_pressure_interface": new_interfaces.copy(),
        "candidate_pressure_mass_measure": candidate_pressure_mass.copy(),
        "candidate_dry_air_mass_measure": final_mass.copy(),
    }
    expected = {
        "pressure": pressure,
        "pressure_mass": pressure_mass,
        "pressure_interface": old_interfaces,
        "background_temperature": background_temperature,
        "proposal_species": proposal_species,
        "proposal_source": np.ones((6, *SHAPE), dtype=np.int32),
        "post_temperature": post_temperature,
        "post_species": post_species,
        "post_mass": post_mass,
        "post_valid": np.ones((6, *SHAPE), dtype=bool),
        "seed_dry_mass": seed_dry_mass,
        "old_surface_pressure": old_surface_pressure,
        "new_surface_pressure": new_surface_pressure,
    }
    return fields, masks, expected, geometry, transition


def run_replay(dataset, fields, masks, expected, geometry, transition, failures, capture):
    def fake_proposal(*args, **kwargs):
        capture.update(kwargs)
        proposal = {
            name: expected["proposal_species"][index].copy()
            for index, name in enumerate(PRECIP_SPECIES, start=3)
        }
        validity = {name: np.ones(SHAPE, dtype=bool) for name in PRECIP_SPECIES}
        source = {
            name: expected["proposal_source"][index].copy()
            for index, name in enumerate(PRECIP_SPECIES, start=3)
        }
        return proposal, validity, source

    def fake_geometry_ledger(*args, **kwargs):
        replay = kwargs["transition_replay"]
        capture["geometry_ledger"] = {
            name: np.array(value, copy=True)
            for name, value in replay.items()
        }
        return True

    with patch.object(validator, "reconstruct_radar_proposal", fake_proposal), \
         patch.object(validator, "validate_pressure_geometry_ledger", fake_geometry_ledger):
        return validator.pressure_transition_replay_errors(
            dataset, fields, masks, expected["pressure"], expected["pressure_mass"],
            expected["pressure_interface"], geometry, transition, {},
            lambda ok, message: failures.append(message) if not ok else None,
        )


def test_original_input_transition_replay_errors() -> None:
    with tempfile.TemporaryDirectory(prefix="transition-state-validator-") as directory:
        path = Path(directory) / "state.nc"
        fields, masks, expected, geometry, transition = make_fixture(path)
        with netCDF4.Dataset(path) as dataset:
            failures: list[str] = []
            capture: dict[str, object] = {}
            errors = run_replay(
                dataset, fields, masks, expected, geometry, transition, failures, capture
            )
            assert not failures, failures
            assert capture["evaluation_prefix"] == "background"
            assert capture["represented_only"] is True
            assert errors and max(errors.values()) < 1.0e-12
            replay_capture = capture["geometry_ledger"]
            with patch.object(validator, "build_pressure_transition_replay",
                              side_effect=AssertionError("replay must be reused")), \
                 patch.object(validator, "validate_pressure_geometry_ledger", return_value=True):
                reused = validator.pressure_transition_replay_errors(
                    dataset, fields, masks, expected["pressure"], expected["pressure_mass"],
                    expected["pressure_interface"], geometry, transition, {},
                    lambda ok, message: failures.append(message) if not ok else None,
                    replay=replay_capture,
                )
            assert reused == errors
            assert not failures, failures
            np.testing.assert_array_equal(
                replay_capture["proposal_species"], expected["proposal_species"]
            )
            np.testing.assert_array_equal(
                replay_capture["proposal_source"], expected["proposal_source"]
            )
            np.testing.assert_array_equal(
                replay_capture["post_temperature"], expected["post_temperature"]
            )
            np.testing.assert_array_equal(
                replay_capture["post_species"], expected["post_species"]
            )
            np.testing.assert_array_equal(
                replay_capture["post_mass"], expected["post_mass"]
            )
            np.testing.assert_array_equal(
                replay_capture["post_valid"], expected["post_valid"]
            )
            np.testing.assert_array_equal(
                replay_capture["candidate_above_ground"],
                transition["candidate_above_ground"],
            )

            mutated = {name: value.copy() for name, value in fields.items()}
            mutated["candidate_temperature"][2, 0, 0] += 0.25
            mutated["candidate_vapor"][1, 0, 0] += 0.01
            mutated_geometry = {
                name: value.copy() for name, value in geometry.items()
            }
            mutated_geometry["candidate_dry_air_mass_measure"][1, 0, 0] += 1.0
            mutated_failures: list[str] = []
            mutated_capture: dict[str, object] = {}
            mutated_errors = run_replay(
                dataset, mutated, masks, expected, mutated_geometry, transition,
                mutated_failures, mutated_capture,
            )
            assert not mutated_failures, mutated_failures
            assert mutated_errors["temperature"] >= 0.25
            assert mutated_errors["vapor"] >= 0.01
            assert mutated_errors["dry_air_mass"] >= 1.0
            mutated_replay = mutated_capture["geometry_ledger"]
            for name in ("proposal_species", "post_temperature", "post_species",
                         "proposal_source", "post_mass", "post_valid",
                         "candidate_above_ground"):
                np.testing.assert_array_equal(mutated_replay[name], replay_capture[name])
            assert not np.array_equal(
                mutated_replay["post_temperature"], mutated["candidate_temperature"]
            )
            assert not np.array_equal(
                mutated_replay["post_species"],
                np.stack(tuple(mutated[f"candidate_{name}"] for name in SPECIES)),
            )

            # The seed's new full cell is 2,500.125 Pa thick; the explicit
            # pressure-increase donor strip is only 1 Pa thick.
            added_cell = (0, 0, 0)
            seed_q = np.stack(
                tuple(transition[f"transition_seed_{name}"] for name in SPECIES)
            )
            full_cell_pressure_width = (
                geometry["candidate_pressure_interface"][0, 0, 0]
                - geometry["candidate_pressure_interface"][1, 0, 0]
            )
            boundary_pressure_width = (
                expected["new_surface_pressure"]
                - expected["old_surface_pressure"]
            )
            expected_seed_mass = (
                full_cell_pressure_width / GRAVITY
                / (1.0 + np.sum(seed_q[:, added_cell[0], added_cell[1], added_cell[2]]))
            )
            boundary_strip_mass = (
                boundary_pressure_width / GRAVITY
                / (1.0 + np.sum(seed_q[:, added_cell[0], added_cell[1], added_cell[2]]))
            )
            np.testing.assert_allclose(
                transition["transition_seed_dry_air_mass_measure"][added_cell],
                expected_seed_mass,
                rtol=0.0,
                atol=1.0e-12,
            )
            assert full_cell_pressure_width == 2500.125
            assert boundary_pressure_width == 1.0
            assert expected_seed_mass > 1000.0 * boundary_strip_mass
            assert replay_capture["final_mass"][added_cell] > 1000.0 * boundary_strip_mass

            forged = {
                name: value.copy() for name, value in transition.items()
            }
            forged["transition_seed_dry_air_mass_measure"][added_cell] += 1.0
            rejected: list[str] = []
            assert run_replay(
                dataset, fields, masks, expected, geometry, forged, rejected, {},
            ) == {}
            assert any("seed" in message and "mass" in message for message in rejected), rejected

            malformed = dict(transition)
            malformed.pop("transition_seed_vapor")
            malformed_failures: list[str] = []
            assert run_replay(
                dataset, fields, masks, expected, geometry, malformed,
                malformed_failures, {},
            ) == {}
            assert any("pressure transition physical replay" in message
                       for message in malformed_failures)

            none_failures: list[str] = []
            with patch.object(validator, "reconstruct_radar_proposal", return_value=None):
                assert validator.pressure_transition_replay_errors(
                    dataset, fields, masks, expected["pressure"], expected["pressure_mass"],
                    expected["pressure_interface"], geometry, transition, {},
                    lambda ok, message: none_failures.append(message) if not ok else None,
                ) == {}
            assert not none_failures


def test_exact_stored_state_criterion():
    errors = {name: 0.0 for name in ("temperature", "dry_air_mass", *SPECIES)}
    assert validator.transition_replay_is_exact(errors)
    assert not validator.transition_replay_is_exact({})
    for name in errors:
        missing = dict(errors)
        del missing[name]
        assert not validator.transition_replay_is_exact(missing)
        for value in (np.nan, np.inf, -1.0, 1.0e-30, False, "0", [0.0]):
            assert not validator.transition_replay_is_exact({**errors, name: value})
    assert not validator.transition_replay_is_exact({**errors, "unknown": 0.0})


if __name__ == "__main__":
    test_original_input_transition_replay_errors()
    test_exact_stored_state_criterion()
    print("Transition state validator tests passed")
