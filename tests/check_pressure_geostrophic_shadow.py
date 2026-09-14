#!/usr/bin/env python3
"""Exercise the immutable-original/final pressure-geostrophic contract."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

from check_pressure_candidate_shadow import reject, rewrite_without, validate


BASE_ATTRIBUTES = {
    "pressure_geostrophic_contract",
    "pressure_geostrophic_scope",
    "pressure_geostrophic_units",
    "pressure_geostrophic_science_assessed",
    "original_full_geostrophic_rms",
    "candidate_full_geostrophic_rms",
}
V2_ATTRIBUTES = BASE_ATTRIBUTES | {
    "pressure_geostrophic_requested_cells",
    "pressure_geostrophic_evaluated_cells",
    "pressure_geostrophic_partial_coverage",
}
V1_VARIABLES = {"geostrophic_validation_support"}
V2_VARIABLES = V1_VARIABLES | {"geostrophic_stencil_support"}


def set_attribute(path: Path, name: str, value, field: str | None = None) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        target = dataset if field is None else dataset[field]
        target.setncattr(name, value)


def alter_scalar_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.setncattr(name, np.float64(dataset.getncattr(name)) + 1.0)


def set_cell(path: Path, field: str, index, value) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset[field][index] = value


def increment_int32_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.setncattr(name, np.int32(int(dataset.getncattr(name)) + 1))


def flip_int32_attribute(path: Path, name: str) -> None:
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset.setncattr(name, np.int32(1 - int(dataset.getncattr(name))))


def horizontal_cross_halo(mask: np.ndarray) -> np.ndarray:
    """Expand a z/y/x mask to itself plus its four horizontal neighbors."""
    expanded = mask.copy()
    expanded[:, 1:, :] |= mask[:, :-1, :]
    expanded[:, :-1, :] |= mask[:, 1:, :]
    expanded[:, :, 1:] |= mask[:, :, :-1]
    expanded[:, :, :-1] |= mask[:, :, 1:]
    return expanded


def expected_stencil(requested: np.ndarray, above: np.ndarray) -> np.ndarray:
    """Return requested cells with an above-ground x and y neighbor."""
    x_neighbor = np.zeros_like(above, dtype=bool)
    y_neighbor = np.zeros_like(above, dtype=bool)
    if above.shape[2] > 1:
        x_neighbor[:, :, 1:] |= above[:, :, :-1]
        x_neighbor[:, :, :-1] |= above[:, :, 1:]
    if above.shape[1] > 1:
        y_neighbor[:, 1:, :] |= above[:, :-1, :]
        y_neighbor[:, :-1, :] |= above[:, 1:, :]
    return requested & x_neighbor & y_neighbor


def check(path: Path) -> None:
    summary, failures = validate(path)
    assert not failures, failures
    assert summary["pressure_geostrophic_independently_validated"] is True
    assert summary["pressure_geostrophic_science_assessed"] is False

    with netCDF4.Dataset(path) as dataset:
        contract = dataset.getncattr("pressure_geostrophic_contract")
        assert contract in {
            "pressure_geostrophic_original_final_v1",
            "pressure_geostrophic_original_final_v2",
        }
        assert dataset.getncattr("pressure_geostrophic_scope") == (
            "balance_support_union_phi_support_horizontal_cross_halo_v1"
        )
        assert dataset.getncattr("pressure_geostrophic_units") == "m s-2"
        assert np.asarray(
            dataset.getncattr("pressure_geostrophic_science_assessed")
        ).dtype == np.dtype(np.int32)
        assert int(dataset.getncattr("pressure_geostrophic_science_assessed")) == 0

        full_rms = np.array(
            [
                dataset.getncattr("original_full_geostrophic_rms"),
                dataset.getncattr("candidate_full_geostrophic_rms"),
            ]
        )
        stage_rms = np.array(
            [
                dataset.getncattr("geostrophic_background_rms"),
                dataset.getncattr("geostrophic_candidate_rms"),
            ]
        )
        assert full_rms.dtype == np.dtype(np.float64)
        assert np.all(np.isfinite(full_rms)) and np.all(full_rms >= 0.0)
        if contract.endswith("_v1"):
            assert not np.array_equal(
                full_rms, stage_rms
            ), "fixture must distinguish original/final RMS from stage-local RMS"

        support_variable = dataset["geostrophic_validation_support"]
        assert np.dtype(support_variable.dtype) == np.dtype(np.int32)
        assert support_variable.dimensions == ("z", "y", "x")
        assert support_variable.getncattr("units") == "1"
        support = np.asarray(support_variable[:], dtype=np.int32)
        assert np.all((support == 0) | (support == 1))
        assert np.any(support == 1)

        above = np.asarray(dataset["above_ground"][:], dtype=np.int32) == 1
        base = np.asarray(dataset["candidate_balance_support"][:], dtype=np.int32) == 1
        phi = np.asarray(dataset["geopotential_support"][:], dtype=np.int32) == 1
        expected = horizontal_cross_halo(base | phi)
        expected &= above
        assert np.array_equal(support == 1, expected), (
            "geostrophic support must be balance|Phi plus one horizontal halo"
        )
        if contract.endswith("_v1"):
            assert not ((V2_ATTRIBUTES - BASE_ATTRIBUTES) & set(dataset.ncattrs()))
            assert set(dataset.variables) & V2_VARIABLES == V1_VARIABLES
            evaluation = expected
            assert summary["pressure_geostrophic_requested_cells"] == int(
                np.count_nonzero(expected)
            )
            assert summary["pressure_geostrophic_evaluated_cells"] == int(
                np.count_nonzero(expected)
            )
            assert summary["pressure_geostrophic_partial_coverage"] is False
        else:
            assert V2_ATTRIBUTES <= set(dataset.ncattrs())
            assert V2_VARIABLES <= set(dataset.variables)
            stencil_variable = dataset["geostrophic_stencil_support"]
            assert np.dtype(stencil_variable.dtype) == np.dtype(np.int32)
            assert stencil_variable.dimensions == ("z", "y", "x")
            assert stencil_variable.getncattr("units") == "1"
            stencil = np.asarray(stencil_variable[:], dtype=np.int32)
            assert np.all((stencil == 0) | (stencil == 1))
            evaluation = expected_stencil(expected, above)
            assert np.array_equal(stencil == 1, evaluation)
            requested_count = int(np.count_nonzero(expected))
            evaluated_count = int(np.count_nonzero(evaluation))
            partial = requested_count != evaluated_count
            assert int(dataset.getncattr("pressure_geostrophic_requested_cells")) == requested_count
            assert int(dataset.getncattr("pressure_geostrophic_evaluated_cells")) == evaluated_count
            assert int(dataset.getncattr("pressure_geostrophic_partial_coverage")) == int(partial)
            assert summary["pressure_geostrophic_requested_cells"] == requested_count
            assert summary["pressure_geostrophic_evaluated_cells"] == evaluated_count
            assert summary["pressure_geostrophic_partial_coverage"] is partial
            assert evaluated_count > 0, "empty stencil must be rejected"
        active = tuple(np.argwhere(support == 1)[0])
        evaluated = np.argwhere(evaluation)
        assert evaluated.size, "geostrophic evaluation mask must be nonempty"
        evaluated_active = tuple(evaluated[0])
        inactive_cells = np.argwhere(support == 0)
        inactive = tuple(inactive_cells[0]) if inactive_cells.size else None

    with tempfile.TemporaryDirectory(prefix="pressure-geostrophic-mutations-") as directory:
        damaged = Path(directory) / "mutated.nc"

        attributes = BASE_ATTRIBUTES if contract.endswith("_v1") else V2_ATTRIBUTES
        variables = V1_VARIABLES if contract.endswith("_v1") else V2_VARIABLES
        for name in sorted(attributes | variables):
            rewrite_without(path, damaged, {name})
            _, failures = validate(damaged)
            assert failures, f"accepted incomplete geostrophic extension: {name}"

        if contract.endswith("_v1"):
            # v1 remains a strict historical contract; v2 bookkeeping is not
            # an ignorable addition to a fully covered v1 result.
            for name in sorted(V2_ATTRIBUTES - BASE_ATTRIBUTES):
                reject(
                    path,
                    damaged,
                    lambda output, n=name: set_attribute(output, n, np.int32(0)),
                    f"v1 accepted new attribute {name}",
                )
        else:
            for name in (
                "pressure_geostrophic_requested_cells",
                "pressure_geostrophic_evaluated_cells",
            ):
                reject(
                    path,
                    damaged,
                    lambda output, n=name: increment_int32_attribute(output, n),
                    f"altered {name}",
                )
            reject(
                path,
                damaged,
                lambda output: flip_int32_attribute(
                    output, "pressure_geostrophic_partial_coverage"
                ),
                "altered partial coverage",
            )

        for name in ("original_full_geostrophic_rms", "candidate_full_geostrophic_rms"):
            reject(
                path,
                damaged,
                lambda output, field=name: alter_scalar_attribute(output, field),
                f"altered {name}",
            )
        reject(
            path,
            damaged,
            lambda output: set_attribute(
                output, "original_full_geostrophic_rms", np.float64(np.nan)
            ),
            "NaN original RMS",
        )
        reject(
            path,
            damaged,
            lambda output: set_attribute(
                output, "original_full_geostrophic_rms", np.float32(0.0)
            ),
            "wrong RMS type",
        )
        reject(
            path,
            damaged,
            lambda output: set_cell(output, "geostrophic_validation_support", active, 0),
            "truncated geostrophic support",
        )
        if inactive is not None:
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "geostrophic_validation_support", inactive, 1
                ),
                "expanded geostrophic support",
            )
        reject(
            path,
            damaged,
            lambda output: set_cell(output, "geostrophic_validation_support", active, 2),
            "nonbinary geostrophic support",
        )
        if contract.endswith("_v2"):
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "geostrophic_stencil_support", evaluated_active, 0
                ),
                "truncated geostrophic stencil support",
            )
            stencil_inactive = np.argwhere(~evaluation)
            if stencil_inactive.size:
                reject(
                    path,
                    damaged,
                    lambda output: set_cell(
                        output, "geostrophic_stencil_support", tuple(stencil_inactive[0]), 1
                    ),
                    "expanded geostrophic stencil support",
                )
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "geostrophic_stencil_support", evaluated_active, 2
                ),
                "nonbinary geostrophic stencil support",
            )
            bad_phi = active
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "background_geopotential_valid", bad_phi, 0
                ),
                "missing requested Phi input",
            )
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "candidate_u", evaluated_active, np.nan
                ),
                "missing evaluated wind input",
            )

        for name, value, label in (
            ("pressure_geostrophic_contract", "forged", "wrong geostrophic claim"),
            ("pressure_geostrophic_scope", "forged", "wrong geostrophic context"),
            ("pressure_geostrophic_units", "m s-1", "wrong geostrophic units"),
            ("pressure_geostrophic_science_assessed", np.int32(1), "false science claim"),
            (
                "pressure_geostrophic_science_assessed",
                np.float64(0),
                "wrong science-claim type",
            ),
        ):
            reject(
                path,
                damaged,
                lambda output, n=name, v=value: set_attribute(output, n, v),
                label,
            )
        reject(
            path,
            damaged,
            lambda output: set_attribute(output, "units", "m", "geostrophic_validation_support"),
            "wrong support units",
        )

        # Removing the optional historical group must preserve the independent
        # Phi result while withdrawing only the geostrophic claim.
        rewrite_without(path, damaged, attributes | variables)
        historical, failures = validate(damaged)
        assert not failures, failures
        assert historical["pressure_geopotential_independently_validated"] is True
        assert historical["pressure_geostrophic_independently_validated"] is False
        assert historical["pressure_geostrophic_science_assessed"] is False

    print(f"PASS pressure geostrophic independent replay/mutations: {path.name}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
