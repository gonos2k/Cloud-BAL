#!/usr/bin/env python3
"""Focused replay tests for the independent radar proposal helper."""

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pressure_radar_reference  # noqa: E402
from validate_shadow_diagnostics import (  # noqa: E402
    QUALITY_EXCLUDED_BITS,
    SOURCE_COLUMN_PHYSICS,
    SOURCE_RADAR_DBZ,
    reconstruct_radar_proposal,
    validate_radar_reconstruction_reference,
)


SHAPE = (3, 1, 1)
SPECIES = ("rain", "snow", "graupel")


def make_dataset(path: Path) -> netCDF4.Dataset:
    dataset = netCDF4.Dataset(path, "w")
    for name, length in (("z", SHAPE[0]), ("y", SHAPE[1]), ("x", SHAPE[2])):
        dataset.createDimension(name, length)
    for name, value in {
        "configured_assumed_radar_wavelength_m": 0.1,
        "maximum_usable_dbz": 80.0,
        "reference_mass_concentration": 1.0e-4,
        "minimum_relative_fall_speed": 0.3,
        "maximum_horizontal_substep": 0.75,
        "precipitation_loading_efficiency": 0.08,
        "maximum_downdraft_ms": 3.0,
        "maximum_downdraft_innovation_ms": 2.0,
        "ledger_relative_tolerance": 1.0e-11,
        "ledger_absolute_tolerance": 1.0e-13,
        "grid_dx_m": 5000.0,
        "grid_dy_m": 5000.0,
        "flux_input": 0.0,
        "flux_deposited": 0.0,
        "flux_suspended": 0.0,
        "flux_boundary_exit": 0.0,
        "flux_terrain_intercept": 0.0,
        "flux_observation_blocked": 0.0,
        "flux_no_echo_blocked": 0.0,
        "flux_microphysical_loss": 0.0,
        "flux_ledger_error": 0.0,
    }.items():
        dataset.setncattr(name, np.float64(value))
    dataset.setncattr("maximum_transport_substeps", np.int32(4))
    dataset.setncattr("transport_required_substeps", np.int32(2))
    backgrounds = {
        "rain": [0.1, 0.2, 0.3],
        "snow": [0.01, 0.02, 0.03],
        "graupel": [0.001, 0.002, 0.003],
    }
    valid = {"rain": [1, 1, 1], "snow": [1, 0, 1], "graupel": [1, 1, 1]}
    for species in SPECIES:
        value = dataset.createVariable(f"background_{species}_valid", "i4", ("z", "y", "x"))
        value[:] = np.asarray(valid[species], dtype=np.int32)[:, None, None]
        value.setncattr("units", "1")
        source = dataset.createVariable(f"background_{species}_source", "i4", ("z", "y", "x"))
        source[:] = np.ones(SHAPE, dtype=np.int32)
        quality = dataset.createVariable(f"background_{species}_quality", "i4", ("z", "y", "x"))
        quality[:] = np.zeros(SHAPE, dtype=np.int32)
        background = dataset.createVariable(f"background_{species}", "f4", ("z", "y", "x"))
        background[:] = np.asarray(backgrounds[species], dtype=np.float32)[:, None, None]
    return dataset


def make_inputs():
    fields = {
        "radar_dbz": np.asarray([[[30.0]], [[0.0]], [[0.0]]], dtype=np.float32),
        "background_temperature": np.asarray([[[250.0]], [[251.0]], [[252.0]]], dtype=np.float32),
        "background_vapor": np.asarray([[[0.001]], [[0.002]], [[0.003]]], dtype=np.float32),
        "background_u": np.asarray([[[1.0]], [[2.0]], [[3.0]]], dtype=np.float32),
        "background_v": np.asarray([[[4.0]], [[5.0]], [[6.0]]], dtype=np.float32),
        "background_omega": np.asarray([[[0.1]], [[0.2]], [[0.3]]], dtype=np.float32),
        "candidate_temperature": np.asarray([[[310.0]], [[311.0]], [[312.0]]], dtype=np.float32),
        "candidate_vapor": np.asarray([[[0.05]], [[0.06]], [[0.07]]], dtype=np.float32),
        "candidate_u": np.asarray([[[100.0]], [[101.0]], [[102.0]]], dtype=np.float32),
        "candidate_v": np.asarray([[[-100.0]], [[-101.0]], [[-102.0]]], dtype=np.float32),
        "candidate_omega": np.asarray([[[9.0]], [[9.1]], [[9.2]]], dtype=np.float32),
    }
    for species in SPECIES:
        fields[f"background_{species}"] = np.asarray(
            {"rain": [0.1, 0.2, 0.3], "snow": [0.01, 0.02, 0.03],
             "graupel": [0.001, 0.002, 0.003]}[species], dtype=np.float32
        )[:, None, None]
        fields[f"candidate_{species}"] = np.full(SHAPE, 9.0, dtype=np.float32)
    masks = {
        "above_ground": np.ones(SHAPE, dtype=bool),
        "radar_valid": np.asarray([[[True]], [[False]], [[False]]], dtype=bool),
        "radar_no_echo": np.zeros(SHAPE, dtype=bool),
    }
    phase_inputs = {
        "background_precipitation_phase": np.zeros(SHAPE, dtype=np.int32),
        "background_precipitation_phase_valid": np.zeros(SHAPE, dtype=np.int32),
        "background_precipitation_phase_quality": np.zeros(SHAPE, dtype=np.int32),
        "background_precipitation_phase_source": np.zeros(SHAPE, dtype=np.int32),
    }
    return fields, masks, phase_inputs


def test_replay_proposal_uses_selected_state_and_immutable_background():
    fresh = {
        "rain": np.asarray([[[0.4]], [[0.3]], [[0.0]]], dtype=np.float32),
        "snow": np.zeros(SHAPE, dtype=np.float32),
        "graupel": np.zeros(SHAPE, dtype=np.float32),
    }
    captured = []

    def fake_reconstruct(**kwargs):
        captured.append({name: np.array(kwargs[name], copy=True) for name in (
            "temperature", "vapor", "u", "v", "omega")})
        ledger = SimpleNamespace(
            input=0.0, deposited=0.0, suspended=0.0, boundary_exit=0.0,
            terrain_intercept=0.0, observation_blocked=0.0,
            no_echo_blocked=0.0, microphysical_loss=0.0,
            maximum_required_substeps=2,
        )
        return SimpleNamespace(**fresh, ledger=ledger)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "proposal.nc"
        with make_dataset(path) as dataset, patch.object(
            pressure_radar_reference,
            "reconstruct_radar_precipitation",
            fake_reconstruct,
        ):
            fields, masks, phase_inputs = make_inputs()
            pressure = np.asarray([100000.0, 95000.0, 90000.0], dtype=np.float32)
            surface_pressure = np.asarray([[100000.0]], dtype=np.float32)
            failures = []
            background_before = {
                species: fields[f"background_{species}"].copy() for species in SPECIES
            }
            background_replay = reconstruct_radar_proposal(
                dataset, fields, masks, pressure, surface_pressure, phase_inputs,
                10.0, lambda ok, message: failures.append(message) if not ok else None,
                evaluation_prefix="background",
            )
            assert not failures, failures
            assert background_replay is not None
            background_proposal, background_validity, background_source = background_replay
            radar_source = SOURCE_RADAR_DBZ | SOURCE_COLUMN_PHYSICS
            expected_source = np.asarray([radar_source, 1 | radar_source, 1], dtype=np.int32)
            expected_source = expected_source[:, None, None]
            for species in SPECIES:
                np.testing.assert_array_equal(background_source[species], expected_source)
                assert background_source[species].dtype == np.dtype(np.int32)
            np.testing.assert_array_equal(
                captured[0]["temperature"], fields["background_temperature"]
            )
            np.testing.assert_array_equal(captured[0]["vapor"], fields["background_vapor"])
            np.testing.assert_array_equal(captured[0]["u"], fields["background_u"])
            np.testing.assert_array_equal(captured[0]["v"], fields["background_v"])
            np.testing.assert_array_equal(captured[0]["omega"], fields["background_omega"])
            np.testing.assert_array_equal(
                background_proposal["rain"],
                np.asarray([0.4, 0.5, 0.3], dtype=np.float32)[:, None, None].astype(np.float64),
            )
            np.testing.assert_array_equal(
                background_proposal["snow"],
                np.asarray([0.0, 0.0, 0.03], dtype=np.float32)[:, None, None].astype(np.float64),
            )
            np.testing.assert_array_equal(
                background_proposal["graupel"],
                np.asarray([0.0, 0.002, 0.003], dtype=np.float32)[:, None, None].astype(np.float64),
            )
            # The default replay keeps the raw descendant value even when its
            # metadata will later make it unrepresented for thermodynamics.
            assert background_proposal["graupel"][1, 0, 0] != 0.0
            # Existing background validity, including an old value, is retained;
            # the independently derived descendant cell is valid for every species.
            np.testing.assert_array_equal(
                background_validity["rain"],
                np.asarray([True, True, True])[:, None, None],
            )
            np.testing.assert_array_equal(
                background_validity["snow"],
                np.asarray([True, True, True])[:, None, None],
            )
            np.testing.assert_array_equal(
                background_validity["graupel"],
                np.asarray([True, True, True])[:, None, None],
            )
            assert background_validity["rain"][2, 0, 0]  # old background value
            assert background_validity["snow"][1, 0, 0]  # derived descendant
            for value in background_proposal.values():
                assert value.dtype == np.dtype(np.float64)
            for species in SPECIES:
                np.testing.assert_array_equal(
                    fields[f"background_{species}"], background_before[species]
                )

            candidate_failures = []
            candidate_replay = reconstruct_radar_proposal(
                dataset, fields, masks, pressure, surface_pressure, phase_inputs,
                10.0,
                lambda ok, message: candidate_failures.append(message) if not ok else None,
                evaluation_prefix="candidate",
            )
            assert not candidate_failures, candidate_failures
            assert candidate_replay is not None
            candidate_proposal, candidate_validity, candidate_source = candidate_replay
            for species in SPECIES:
                np.testing.assert_array_equal(candidate_validity[species], background_validity[species])
                np.testing.assert_array_equal(candidate_source[species], expected_source)
                assert candidate_source[species].dtype == np.dtype(np.int32)
            np.testing.assert_array_equal(
                captured[1]["temperature"], fields["candidate_temperature"]
            )
            np.testing.assert_array_equal(captured[1]["vapor"], fields["candidate_vapor"])
            np.testing.assert_array_equal(captured[1]["u"], fields["candidate_u"])
            np.testing.assert_array_equal(captured[1]["v"], fields["candidate_v"])
            np.testing.assert_array_equal(captured[1]["omega"], fields["candidate_omega"])

            fields["candidate_rain"][:] = 99.0
            rejected = []
            assert not validate_radar_reconstruction_reference(
                dataset, fields, masks, pressure, surface_pressure, phase_inputs,
                10.0, lambda ok, message: rejected.append(message) if not ok else None,
            )
            assert any("independent radar rain reconstruction" in message for message in rejected)

            for species in SPECIES:
                fields[f"candidate_{species}"][:] = candidate_proposal[species].astype(np.float32)
            accepted = []
            assert validate_radar_reconstruction_reference(
                dataset, fields, masks, pressure, surface_pressure, phase_inputs,
                10.0, lambda ok, message: accepted.append(message) if not ok else None,
            )
            assert not accepted, accepted

            # Unrepresented stored values must not contribute to proposal mass.
            # Observed derived cells clear old quality; valid nonobserved
            # descendants inherit it; invalid priors clear it; and derived
            # source=0 is repaired by the radar+column publication source.
            dataset["background_snow_valid"][2, 0, 0] = 0
            dataset["background_rain_quality"][0, 0, 0] = QUALITY_EXCLUDED_BITS
            dataset["background_rain_valid"][1, 0, 0] = 0
            dataset["background_rain_quality"][1, 0, 0] = QUALITY_EXCLUDED_BITS
            dataset["background_graupel_quality"][1, 0, 0] = QUALITY_EXCLUDED_BITS
            dataset["background_graupel_quality"][2, 0, 0] = QUALITY_EXCLUDED_BITS
            dataset["background_snow_valid"][1, 0, 0] = 1
            dataset["background_snow_source"][1, 0, 0] = 0
            represented_replay = reconstruct_radar_proposal(
                dataset, fields, masks, pressure, surface_pressure, phase_inputs,
                10.0, lambda ok, message: failures.append(message) if not ok else None,
                evaluation_prefix="background", represented_only=True,
            )
            assert not failures, failures
            assert represented_replay is not None
            represented, represented_validity, represented_source = represented_replay
            for species in SPECIES:
                # Observed replacement, descendant OR with the immutable
                # background source, and untouched background provenance.
                represented_expected_source = expected_source.copy()
                if species == "snow":
                    # The descendant's old source was deliberately cleared;
                    # radar publication repairs it without retaining zero.
                    represented_expected_source[1, 0, 0] = radar_source
                np.testing.assert_array_equal(
                    represented_source[species], represented_expected_source
                )
            expected_rain = background_proposal["rain"].copy()
            expected_rain[1, 0, 0] = np.float64(np.float32(0.3))
            np.testing.assert_array_equal(represented["rain"], expected_rain)
            assert represented["rain"][0, 0, 0] == background_proposal["rain"][0, 0, 0]
            expected_graupel = background_proposal["graupel"].copy()
            expected_graupel[1, 0, 0] = 0.0
            expected_graupel[2, 0, 0] = 0.0
            np.testing.assert_array_equal(represented["graupel"], expected_graupel)
            expected_snow = background_proposal["snow"].copy()
            expected_snow[1, 0, 0] = background_before["snow"][1, 0, 0]
            np.testing.assert_array_equal(represented["snow"][:2], expected_snow[:2])
            assert represented["snow"][2, 0, 0] == 0.0
            np.testing.assert_array_equal(
                represented_validity["snow"],
                np.asarray([True, True, False])[:, None, None],
            )
            np.testing.assert_array_equal(represented_validity["rain"], background_validity["rain"])
            np.testing.assert_array_equal(
                represented_validity["graupel"], background_validity["graupel"]
            )
            assert represented_validity["graupel"][2, 0, 0]
            assert fields["background_snow"][2, 0, 0] == background_before["snow"][2, 0, 0]


if __name__ == "__main__":
    test_replay_proposal_uses_selected_state_and_immutable_background()
    print("Radar proposal replay tests passed")
