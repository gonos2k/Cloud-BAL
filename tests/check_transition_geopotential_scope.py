#!/usr/bin/env python3
"""Focused direct checks for transition-scoped pressure geopotential replay."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))
sys.path.insert(0, str(TESTS))
import validate_shadow_diagnostics as validator  # noqa: E402
from check_pressure_candidate_shadow import validate as validate_file  # noqa: E402
from check_transition_thermo_scope import _probe_inputs  # noqa: E402
from pressure_transition_reference import (  # noqa: E402
    surface_geopotential_profile_reference,
    transition_geopotential_reference,
)


def _surface_inputs(dataset: netCDF4.Dataset) -> dict[str, np.ndarray]:
    names = (
        "surface_pressure", "surface_temperature", "surface_vapor", "surface_height",
    )
    result: dict[str, np.ndarray] = {}
    for prefix in ("background", "candidate"):
        for name in names:
            value_name = f"{prefix}_{name}"
            for suffix in ("", "_valid", "_quality", "_source"):
                variable = f"{value_name}{suffix}"
                if variable in dataset.variables:
                    result[variable] = validator.values(dataset[variable])
    return result


def _context(path: Path) -> dict[str, object]:
    with netCDF4.Dataset(path) as dataset:
        inputs = _probe_inputs(dataset)
        replay_failures: list[str] = []

        def require(condition: object, message: str) -> None:
            if not condition:
                replay_failures.append(message)

        replay = validator.build_pressure_transition_replay(
            dataset,
            inputs["fields"],
            inputs["masks"],
            inputs["pressure"],
            inputs["pressure_mass"],
            inputs["pressure_interface"],
            inputs["geometry"],
            inputs["transition"],
            inputs["phase_inputs"],
            require,
        )
        assert replay is not None, replay_failures
        assert not replay_failures, replay_failures
        return {
            "inputs": inputs,
            "replay": replay,
            "transition_inputs": inputs["transition"],
            "surface_inputs": _surface_inputs(dataset),
            "schema_version": int(dataset.diagnostic_schema_version),
            "canonical_schema_version": int(dataset.cloud_bal_schema_version),
            "valid_time_epoch": validator.exact_scalar_int64(
                getattr(dataset, "valid_time_epoch", None)
            ),
            "pressure_candidate": (
                "pressure_analysis_candidate_contract" in dataset.ncattrs()
                or "original_omega_target" in dataset.variables
            ),
        }


def _call(
    path: Path,
    context: dict[str, object],
    *,
    above: np.ndarray,
    replay: dict[str, np.ndarray] | None,
    transition_inputs: dict[str, np.ndarray] | None,
) -> tuple[tuple[bool, bool, np.ndarray], list[str]]:
    failures: list[str] = []

    def require(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    try:
        with netCDF4.Dataset(path) as dataset:
            result = validator.validate_pressure_geopotential_extension(
                dataset,
                above.shape,
                above,
                context["inputs"]["pressure"],
                context["pressure_candidate"],
                context["schema_version"],
                context["valid_time_epoch"],
                context["canonical_schema_version"],
                True,
                True,
                context["surface_inputs"],
                require,
                transition_replay=replay,
                transition_inputs=transition_inputs,
            )
    except Exception as error:  # malformed scoped inputs must become a clean rejection
        failures.append(f"unexpected validator exception: {error}")
        result = (True, False, np.zeros(above.shape, dtype=bool))
    return result, failures


def _mutate(source: Path, target: Path, mutation) -> None:
    shutil.copyfile(source, target)
    with netCDF4.Dataset(target, "r+") as dataset:
        mutation(dataset)


def _analytic_surface_phi_stages(
    dataset: netCDF4.Dataset,
    above: np.ndarray,
    support: np.ndarray,
    background_phi: np.ndarray,
    replay: dict[str, np.ndarray],
    transition_inputs: dict[str, np.ndarray] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Independent profile reconstruction; never calls the validator."""
    pressure = validator.values(dataset["pressure"]).astype(np.float64)
    fields = {
        name: validator.values(dataset[name]).astype(np.float64)
        for name in ("background_temperature", "candidate_temperature")
    }
    for species in validator.THERMO_SPECIES:
        fields[f"background_{species}"] = validator.values(
            dataset[f"background_{species}"]
        ).astype(np.float64)
    surface = {
        name: validator.values(dataset[name]).astype(np.float64)
        for name in (
            "background_surface_pressure", "candidate_surface_pressure",
            "background_surface_temperature", "candidate_surface_temperature",
            "background_surface_vapor", "candidate_surface_vapor",
            "background_surface_height", "candidate_surface_height",
        )
    }
    staged_expected = background_phi.copy()
    expected = background_phi.copy()
    for y, x in np.argwhere(np.any(support, axis=0)):
        y, x = int(y), int(x)
        bottom = int(np.argmax(above[:, y, x]))
        levels = np.flatnonzero(above[:, y, x])
        old_species = np.stack(
            [fields[f"background_{name}"][levels, y, x]
             for name in validator.THERMO_SPECIES]
        )
        post_species = replay["post_species"][:, levels, y, x].astype(np.float64)
        old_profile = surface_geopotential_profile_reference(
            pressure[levels], fields["background_temperature"][levels, y, x],
            old_species, surface["background_surface_pressure"][y, x],
            surface["background_surface_temperature"][y, x],
            surface["background_surface_vapor"][y, x],
            surface["background_surface_height"][y, x],
        )
        post_profile = surface_geopotential_profile_reference(
            pressure[levels], replay["post_temperature"][levels, y, x],
            post_species,
            min(
                surface["candidate_surface_pressure"][y, x],
                surface["background_surface_pressure"][y, x],
            ),
            surface["candidate_surface_temperature"][y, x],
            surface["candidate_surface_vapor"][y, x],
            surface["candidate_surface_height"][y, x],
        )
        staged = (
            background_phi[levels, y, x].astype(np.float64)
            + post_profile - old_profile
        ).astype(np.float32)
        staged_expected[levels, y, x] = staged
        candidate_pressure = surface["candidate_surface_pressure"][y, x]
        background_pressure = surface["background_surface_pressure"][y, x]
        if candidate_pressure > background_pressure:
            final_species = replay["final_species"][:, levels, y, x].astype(np.float64)
            candidate_levels = np.flatnonzero(
                replay["candidate_above_ground"][:, y, x].astype(bool)
            )
            added = candidate_levels.size - levels.size
            seed_kwargs = {}
            if added:
                if transition_inputs is None:
                    raise AssertionError("added domain requires transition inputs")
                new_level = int(candidate_levels[0])
                seed_kwargs = {
                    "seed_geopotential": float(
                        transition_inputs["transition_seed_geopotential"][new_level, y, x]
                    ),
                    "seed_temperature": float(
                        transition_inputs["transition_seed_temperature"][new_level, y, x]
                    ),
                    "seed_species": np.asarray([
                        transition_inputs[f"transition_seed_{name}"][new_level, y, x]
                        for name in validator.THERMO_SPECIES
                    ], dtype=np.float64),
                }
            expected[candidate_levels, y, x] = transition_geopotential_reference(
                pressure[candidate_levels], staged,
                replay["post_temperature"][levels, y, x], post_species,
                replay["final_temperature"][candidate_levels, y, x],
                replay["final_species"][:, candidate_levels, y, x].astype(np.float64),
                background_pressure, candidate_pressure,
                surface["candidate_surface_temperature"][y, x],
                surface["candidate_surface_vapor"][y, x],
                surface["candidate_surface_height"][y, x],
                **seed_kwargs,
            ).astype(np.float32)
        else:
            expected[levels, y, x] = staged
    return staged_expected, expected


def _analytic_surface_phi(
    dataset: netCDF4.Dataset,
    above: np.ndarray,
    support: np.ndarray,
    background_phi: np.ndarray,
    replay: dict[str, np.ndarray],
    transition_inputs: dict[str, np.ndarray] | None = None,
) -> np.ndarray:
    return _analytic_surface_phi_stages(
        dataset, above, support, background_phi, replay, transition_inputs
    )[1]


def _same_domain(path: Path, context: dict[str, object]) -> None:
    inputs = context["inputs"]
    above = inputs["masks"]["above_ground"].copy()
    with netCDF4.Dataset(path) as dataset:
        support = validator.values(dataset["geopotential_support"]).astype(bool)
        background_phi = validator.values(dataset["background_geopotential"])
        candidate_phi = validator.values(dataset["candidate_geopotential"])
        staged, expected = _analytic_surface_phi_stages(
            dataset, above, support, background_phi, context["replay"]
        )
    assert np.array_equal(candidate_phi, expected), "probe Phi is not the independent profile result"

    result, failures = _call(
        path, context, above=above, replay=context["replay"],
        transition_inputs=context["transition_inputs"],
    )
    present, clean, changed = result
    assert present and clean, failures
    pressure_changed = (
        context["surface_inputs"]["candidate_surface_pressure"]
        != context["surface_inputs"]["background_surface_pressure"]
    )
    candidate_domain = context["replay"]["candidate_above_ground"].astype(bool)
    stage_changed = (
        validator.changed_bits(background_phi, staged)
        | validator.changed_bits(staged, expected)
    )
    expected_changed = stage_changed | (candidate_domain & pressure_changed[None, :, :])
    assert np.array_equal(changed, expected_changed)
    assert np.any(changed), "same-domain fixture must contain a Phi change"

    with netCDF4.Dataset(path) as dataset:
        positive_surface = (
            validator.values(dataset["candidate_surface_pressure"])
            > validator.values(dataset["background_surface_pressure"])
        )
    positive_cells = np.argwhere(changed & positive_surface[None, :, :])
    changed_cell = tuple(
        positive_cells[0] if positive_cells.size else np.argwhere(changed)[0]
    )
    with tempfile.TemporaryDirectory(prefix="transition-phi-scope-") as directory:
        damaged = Path(directory) / "damaged.nc"
        mutations = (
            ("candidate Phi", lambda ds: ds["candidate_geopotential"].__setitem__(
                changed_cell, np.float32(ds["candidate_geopotential"][changed_cell] + 1.0)
            )),
            ("NaN Phi", lambda ds: ds["candidate_geopotential"].__setitem__(changed_cell, np.nan)),
            ("missing source", lambda ds: ds["candidate_geopotential_source"].__setitem__(
                changed_cell, np.int32(0)
            )),
            ("bad quality", lambda ds: ds["candidate_geopotential_quality"].__setitem__(
                changed_cell, np.int32(1)
            )),
            ("wrong units", lambda ds: ds["candidate_geopotential"].setncattr("units", "m")),
        )
        for label, mutation in mutations:
            _mutate(path, damaged, mutation)
            result, failures = _call(
                damaged, context, above=above, replay=context["replay"],
                transition_inputs=context["transition_inputs"],
            )
            assert result[0] and not result[1] and failures, label

        missing = dict(context["replay"])
        missing.pop("final_temperature")
        result, failures = _call(
            path, context, above=above, replay=missing,
            transition_inputs=context["transition_inputs"],
        )
        assert result[0] and not result[1] and failures, "missing replay key"

        for replay, transition_inputs, label in (
            (context["replay"], None, "missing transition inputs"),
            (None, context["transition_inputs"], "missing transition replay"),
        ):
            result, failures = _call(
                path, context, above=above, replay=replay,
                transition_inputs=transition_inputs,
            )
            assert result[0] and not result[1] and failures, label

        # Forge Phi from mutated final T/q.  A validator that reconstructs from
        # the mutable candidate fields instead of the retained replay accepts
        # this; the scoped replay must reject it.
        def forge_final_state(dataset: netCDF4.Dataset) -> None:
            dataset["candidate_temperature"][changed_cell] += np.float32(1.0)
            dataset["candidate_vapor"][changed_cell] += np.float32(0.01)
            expected_forged = _analytic_surface_phi(
                dataset, above,
                validator.values(dataset["geopotential_support"]).astype(bool),
                validator.values(dataset["background_geopotential"]),
                context["replay"],
            )
            # The helper intentionally uses retained replay T/q, so recompute
            # only this cell with the mutated candidate fields for the forged
            # alternate that a bad implementation could accept.
            pressure = validator.values(dataset["pressure"]).astype(np.float64)
            y, x = changed_cell[1:]
            levels = np.arange(int(np.argmax(above[:, y, x])), pressure.size)
            post_species = context["replay"]["post_species"][:, levels, y, x].astype(np.float64)
            species_old = np.stack([
                validator.values(dataset[f"background_{name}"])[levels, y, x]
                for name in validator.THERMO_SPECIES
            ]).astype(np.float64)
            species_new = np.stack([
                validator.values(dataset[f"candidate_{name}"])[levels, y, x]
                for name in validator.THERMO_SPECIES
            ]).astype(np.float64)
            surface = lambda name: float(validator.values(dataset[name])[y, x])
            old_profile = surface_geopotential_profile_reference(
                pressure[levels], validator.values(dataset["background_temperature"])[levels, y, x],
                species_old, surface("background_surface_pressure"),
                surface("background_surface_temperature"), surface("background_surface_vapor"),
                surface("background_surface_height"),
            )
            post_profile = surface_geopotential_profile_reference(
                pressure[levels], context["replay"]["post_temperature"][levels, y, x],
                post_species, surface("background_surface_pressure"),
                surface("background_surface_temperature"), surface("background_surface_vapor"),
                surface("background_surface_height"),
            )
            staged = (
                validator.values(dataset["background_geopotential"])[levels, y, x]
                + post_profile - old_profile
            ).astype(np.float32)
            new_profile = surface_geopotential_profile_reference(
                pressure[levels], validator.values(dataset["candidate_temperature"])[levels, y, x],
                species_new, surface("candidate_surface_pressure"),
                surface("candidate_surface_temperature"), surface("candidate_surface_vapor"),
                surface("candidate_surface_height"),
            )
            expected_forged[levels, y, x] = transition_geopotential_reference(
                pressure[levels], staged,
                context["replay"]["post_temperature"][levels, y, x], post_species,
                validator.values(dataset["candidate_temperature"])[levels, y, x], species_new,
                surface("background_surface_pressure"), surface("candidate_surface_pressure"),
                surface("candidate_surface_temperature"), surface("candidate_surface_vapor"),
                surface("candidate_surface_height"),
            ).astype(np.float32) if surface("candidate_surface_pressure") > surface(
                "background_surface_pressure"
            ) else staged
            dataset["candidate_geopotential"][:, y, x] = expected_forged[:, y, x]

        _mutate(path, damaged, forge_final_state)
        result, failures = _call(
            damaged, context, above=above, replay=context["replay"],
            transition_inputs=context["transition_inputs"],
        )
        assert result[0] and not result[1] and failures, "candidate T/q redefined Phi"


def _same_domain_pressure_rounding_receipt(path: Path, context: dict[str, object]) -> None:
    """A pressure receipt survives when float32 Phi rounds at both stages."""
    inputs = context["inputs"]
    above = inputs["masks"]["above_ground"].copy()
    with netCDF4.Dataset(path) as dataset:
        support = validator.values(dataset["geopotential_support"]).astype(bool)
        background_phi = validator.values(dataset["background_geopotential"])
        candidate_domain = context["replay"]["candidate_above_ground"].astype(bool)
        pressure_changed = (
            context["surface_inputs"]["candidate_surface_pressure"]
            != context["surface_inputs"]["background_surface_pressure"]
        )
        _, unshifted_expected = _analytic_surface_phi_stages(
            dataset, above, support, background_phi, context["replay"]
        )
        columns = np.argwhere(pressure_changed & np.any(candidate_domain, axis=0))
        assert columns.size, "probe has no active pressure-changed column"
        y, x = min(
            ((int(y), int(x)) for y, x in columns),
            key=lambda cell: float(np.max(np.abs(
                unshifted_expected[candidate_domain[:, cell[0], cell[1]], cell[0], cell[1]]
                - background_phi[candidate_domain[:, cell[0], cell[1]], cell[0], cell[1]]
            ))),
        )

    with tempfile.TemporaryDirectory(prefix="transition-phi-mask-") as directory:
        rounded = Path(directory) / "rounded.nc"

        def make_rounded(dataset: netCDF4.Dataset) -> None:
            shifted_background = validator.values(
                dataset["background_geopotential"]
            ).copy()
            shifted_background[:, y, x] += np.float32(1.0e9)
            dataset["background_geopotential"][:] = shifted_background
            staged, expected = _analytic_surface_phi_stages(
                dataset, above, support, shifted_background, context["replay"]
            )
            dataset["candidate_geopotential"][:, y, x] = expected[:, y, x]
            changed_stages = (
                validator.changed_bits(shifted_background, staged)
                | validator.changed_bits(staged, expected)
            )
            background_source = validator.values(
                dataset["background_geopotential_source"]
            )
            candidate_source = validator.values(
                dataset["candidate_geopotential_source"]
            ).copy()
            candidate_source[:, y, x] = np.where(
                changed_stages[:, y, x],
                background_source[:, y, x] | validator.SOURCE_COLUMN_PHYSICS,
                background_source[:, y, x],
            )
            dataset["candidate_geopotential_source"][:, y, x] = candidate_source[:, y, x]

        _mutate(path, rounded, make_rounded)
        result, failures = _call(
            rounded,
            context,
            above=above,
            replay=context["replay"],
            transition_inputs=context["transition_inputs"],
        )
        present, clean, changed = result
        assert present and clean, failures
        with netCDF4.Dataset(rounded) as dataset:
            shifted_background = validator.values(dataset["background_geopotential"])
            candidate_phi = validator.values(dataset["candidate_geopotential"])
        endpoint_changed = validator.changed_bits(shifted_background, candidate_phi)
        receipt = candidate_domain & pressure_changed[None, :, :]
        unchanged_receipt = receipt & ~endpoint_changed
        assert np.any(unchanged_receipt), "fixture lost float32 Phi rounding case"
        assert np.all(changed[receipt]), "PS-changed active cells must be receipted"


def _signed_surface_pressure_seed(path: Path, context: dict[str, object]) -> None:
    """Negative requests use a max(background, candidate) transition seed."""
    inputs = context["inputs"]
    above = inputs["masks"]["above_ground"].copy()
    background_surface_pressure = context["surface_inputs"][
        "background_surface_pressure"
    ]
    candidate_surface_pressure = context["surface_inputs"][
        "candidate_surface_pressure"
    ]
    assert np.any(
        candidate_surface_pressure > background_surface_pressure
    ), "probe has no positive pressure column for mixed-sign check"
    candidate_domain = context["replay"]["candidate_above_ground"].astype(bool)
    untouched_columns = np.argwhere(
        np.any(candidate_domain, axis=0)
        & (candidate_surface_pressure == background_surface_pressure)
    )
    assert untouched_columns.size, "probe has no untouched candidate column"
    y, x = (int(value) for value in untouched_columns[0])
    negative_pressure = np.float32(background_surface_pressure[y, x] - 20.0)

    signed_surface_inputs = {
        name: np.asarray(value).copy()
        for name, value in context["surface_inputs"].items()
    }
    signed_surface_inputs["candidate_surface_pressure"][y, x] = negative_pressure
    signed_context = dict(context)
    signed_context["surface_inputs"] = signed_surface_inputs
    signed_transition_inputs = {
        name: np.asarray(value).copy()
        for name, value in context["transition_inputs"].items()
    }
    signed_transition_inputs["transition_seed_surface_pressure"][y, x] = (
        background_surface_pressure[y, x]
    )

    with tempfile.TemporaryDirectory(prefix="transition-phi-signed-") as directory:
        signed = Path(directory) / "negative.nc"

        def make_signed(dataset: netCDF4.Dataset) -> None:
            dataset["candidate_surface_pressure"][y, x] = negative_pressure
            dataset["transition_seed_surface_pressure"][y, x] = (
                background_surface_pressure[y, x]
            )
            support = validator.values(dataset["geopotential_support"]).astype(bool)
            background_phi = validator.values(dataset["background_geopotential"])
            staged, expected = _analytic_surface_phi_stages(
                dataset, above, support, background_phi, context["replay"]
            )
            dataset["candidate_geopotential"][:, y, x] = expected[:, y, x]
            changed_stages = (
                validator.changed_bits(background_phi, staged)
                | validator.changed_bits(staged, expected)
            )
            background_source = validator.values(
                dataset["background_geopotential_source"]
            )
            candidate_source = validator.values(
                dataset["candidate_geopotential_source"]
            ).copy()
            candidate_source[:, y, x] = np.where(
                changed_stages[:, y, x],
                background_source[:, y, x] | validator.SOURCE_COLUMN_PHYSICS,
                background_source[:, y, x],
            )
            dataset["candidate_geopotential_source"][:, y, x] = candidate_source[:, y, x]

        _mutate(path, signed, make_signed)
        result, failures = _call(
            signed,
            signed_context,
            above=above,
            replay=context["replay"],
            transition_inputs=signed_transition_inputs,
        )
        present, clean, changed = result
        assert present and clean, failures
        with netCDF4.Dataset(signed) as dataset:
            background_phi = validator.values(dataset["background_geopotential"])
            candidate_phi = validator.values(dataset["candidate_geopotential"])
        pressure_changed = (
            signed_surface_inputs["candidate_surface_pressure"]
            != signed_surface_inputs["background_surface_pressure"]
        )
        receipt = candidate_domain & pressure_changed[None, :, :]
        assert np.all(changed[receipt]), "signed PS columns must be receipted"
        assert np.any(
            validator.changed_bits(background_phi, candidate_phi)[receipt]
        ), "signed request did not produce a physical Phi change"

        forged_seed = {
            name: np.asarray(value).copy()
            for name, value in signed_transition_inputs.items()
        }
        forged_seed["transition_seed_surface_pressure"][y, x] = negative_pressure
        result, failures = _call(
            signed,
            signed_context,
            above=above,
            replay=context["replay"],
            transition_inputs=forged_seed,
        )
        assert result[0] and not result[1] and failures, "accepted signed seed forgery"
        assert "transition seed surface pressure identity" in failures


def _added_bottom(path: Path, context: dict[str, object]) -> None:
    inputs = context["inputs"]
    old_above = inputs["masks"]["above_ground"].copy()
    with netCDF4.Dataset(path) as dataset:
        support = validator.values(dataset["geopotential_support"]).astype(bool)
        background_phi = validator.values(dataset["background_geopotential"])
        cell = None
        for y, x in np.argwhere(np.any(old_above, axis=0)):
            bottom = int(np.argmax(old_above[:, y, x]))
            if bottom > 0:
                cell = (bottom - 1, int(y), int(x))
                break
        # The generated probe is all represented; turn one existing bottom
        # center into an old inactive placeholder for this bounded scope case.
        if cell is None:
            cell = (0, 1, 1)
        seed_phi = np.float32(1030.0)
        seed_temperature = np.float32(280.0)
        seed_species = np.asarray(
            [validator.values(dataset[f"background_{name}"])[cell]
             for name in validator.THERMO_SPECIES], dtype=np.float32
        )
        pressure0 = float(validator.values(dataset["pressure"])[0])
        old_surface_pressure = np.float32(pressure0 - 10.0)
        candidate_surface_pressure = np.float32(pressure0 + 10.0)

    added_above = old_above.copy()
    added_above[cell] = True
    old_domain = old_above.copy()
    old_domain[cell] = False
    transition_inputs = {
        name: np.asarray(value).copy()
        for name, value in context["transition_inputs"].items()
    }
    transition_inputs["transition_seed_geopotential"][cell] = seed_phi
    transition_inputs["transition_seed_temperature"][cell] = seed_temperature
    transition_inputs["transition_seed_vapor"][cell] = seed_species[0]
    for index, species in enumerate(validator.THERMO_SPECIES[1:], start=1):
        transition_inputs[f"transition_seed_{species}"][cell] = seed_species[index]
    transition_inputs["transition_seed_surface_pressure"][cell[1:]] = (
        candidate_surface_pressure
    )
    added_context = dict(context)
    added_context["transition_inputs"] = transition_inputs
    added_surface_inputs = {
        name: np.asarray(value).copy()
        for name, value in context["surface_inputs"].items()
    }
    for name, value in (
        ("background_surface_pressure", old_surface_pressure),
        ("candidate_surface_pressure", candidate_surface_pressure),
    ):
        added_surface_inputs[name][cell[1:]] = value
    added_context["surface_inputs"] = added_surface_inputs

    with tempfile.TemporaryDirectory(prefix="transition-phi-added-") as directory:
        added = Path(directory) / "added-bottom.nc"

        def make_added(dataset: netCDF4.Dataset) -> None:
            dataset["above_ground"][cell] = np.int32(0)
            dataset["background_surface_pressure"][cell[1:]] = old_surface_pressure
            dataset["candidate_surface_pressure"][cell[1:]] = candidate_surface_pressure
            dataset["transition_seed_surface_pressure"][cell[1:]] = (
                candidate_surface_pressure
            )
            dataset["transition_seed_geopotential"][cell] = seed_phi
            dataset["transition_seed_temperature"][cell] = seed_temperature
            for index, species in enumerate(validator.THERMO_SPECIES):
                dataset[f"transition_seed_{species}"][cell] = seed_species[index]
            for name in validator.THERMO_FIELDS:
                dataset[f"background_{name}"][cell] = np.float32(np.nan)
                dataset[f"background_{name}_valid"][cell] = np.int32(0)
                dataset[f"background_{name}_quality"][cell] = np.int32(0)
                dataset[f"background_{name}_source"][cell] = np.int32(0)
            dataset["background_geopotential"][cell] = np.float32(np.nan)
            dataset["background_geopotential_valid"][cell] = np.int32(0)
            dataset["background_geopotential_quality"][cell] = np.int32(0)
            dataset["background_geopotential_source"][cell] = np.int32(0)

            expected = _analytic_surface_phi(
                dataset, old_domain, support, background_phi,
                added_context["replay"], transition_inputs,
            )
            y, x = cell[1:]
            dataset["candidate_geopotential"][:, y, x] = expected[:, y, x]
            dataset["candidate_geopotential_valid"][cell] = np.int32(1)
            dataset["candidate_geopotential_quality"][cell] = np.int32(0)
            dataset["candidate_geopotential_source"][cell] = np.int32(
                validator.SOURCE_COLUMN_PHYSICS
            )

        _mutate(path, added, make_added)
        result, failures = _call(
            added, added_context, above=old_domain, replay=added_context["replay"],
            transition_inputs=transition_inputs,
        )
        present, clean, changed = result
        assert present and clean, failures
        with netCDF4.Dataset(added) as dataset:
            candidate = validator.values(dataset["candidate_geopotential"])
        assert changed[cell]
        assert candidate[cell] > seed_phi, "transition Phi must be a positive float32 increment"

        damaged = Path(directory) / "damaged.nc"
        for name, value in (("candidate_geopotential", candidate[cell] + 1.0),
                            ("geopotential_support", 0)):
            _mutate(added, damaged, lambda ds, n=name, v=value: ds[n].__setitem__(cell, v))
            result, failures = _call(
                damaged, added_context, above=old_domain, replay=added_context["replay"],
                transition_inputs=transition_inputs,
            )
            assert not result[1] and failures, f"accepted new-cell {name} mutation"

        invalid_seed = dict(transition_inputs)
        invalid_seed["transition_seed_geopotential_quality"] = np.asarray(
            transition_inputs["transition_seed_geopotential_quality"], dtype=np.float64
        ) + 0.5
        result, failures = _call(
            added, added_context, above=old_domain, replay=added_context["replay"],
            transition_inputs=invalid_seed,
        )
        assert not result[1] and failures, "accepted fractional seed quality"

        invalid_replay = dict(added_context["replay"])
        invalid_replay["post_temperature"] = np.full(old_domain.shape, "invalid")
        result, failures = _call(
            added, added_context, above=old_domain, replay=invalid_replay,
            transition_inputs=transition_inputs,
        )
        assert not result[1] and failures, "accepted nonnumeric replay"

        low_seed = {name: np.asarray(value).copy() for name, value in transition_inputs.items()}
        low_seed["transition_seed_geopotential"][cell] = np.float32(-100000.0)
        shutil.copyfile(added, damaged)
        with netCDF4.Dataset(damaged, "r+") as dataset:
            below_terrain_phi = _analytic_surface_phi(
                dataset, old_domain, support, validator.values(dataset["background_geopotential"]),
                added_context["replay"], low_seed,
            )
            dataset["candidate_geopotential"][:] = below_terrain_phi
        result, failures = _call(
            damaged, added_context, above=old_domain, replay=added_context["replay"],
            transition_inputs=low_seed,
        )
        assert not result[1], "accepted a matching but below-terrain seed/Phi pair"
        assert "transition new-cell geopotential above terrain" in failures


def _double_rounding(path: Path, context: dict[str, object]) -> None:
    """A fixed Phi offset makes the intermediate REAL32 store observable."""
    inputs, replay = context["inputs"], context["replay"]
    with tempfile.TemporaryDirectory(prefix="transition-phi-rounding-") as directory:
        staged_path = Path(directory) / "staged.nc"
        shutil.copyfile(path, staged_path)
        with netCDF4.Dataset(staged_path, "r+") as dataset:
            background_phi = validator.values(dataset["background_geopotential"]).copy()
            background_phi[:, 1, 1] += np.float32(1000.0)
            dataset["background_geopotential"][:] = background_phi
            staged_phi = _analytic_surface_phi(
                dataset, inputs["masks"]["above_ground"],
                validator.values(dataset["geopotential_support"]).astype(bool),
                background_phi, replay, context["transition_inputs"],
            )
            dataset["candidate_geopotential"][:] = staged_phi
            profiles = []
            for prefix in ("background", "candidate"):
                temperature = (validator.values(dataset["background_temperature"])[:, 1, 1]
                               if prefix == "background" else replay["final_temperature"][:, 1, 1])
                species = (np.stack([validator.values(dataset[f"background_{name}"])[:, 1, 1]
                                     for name in validator.THERMO_SPECIES])
                           if prefix == "background" else replay["final_species"][:, :, 1, 1])
                profiles.append(surface_geopotential_profile_reference(
                    inputs["pressure"], temperature, species,
                    *(float(dataset[f"{prefix}_{name}"][1, 1]) for name in (
                        "surface_pressure", "surface_temperature", "surface_vapor", "surface_height")),
                ))
            collapsed = (background_phi[:, 1, 1].astype(np.float64)
                         + profiles[1] - profiles[0]).astype(np.float32)
            assert np.any(collapsed != staged_phi[:, 1, 1]), "fixture lost its double-rounding case"
        arguments = dict(above=inputs["masks"]["above_ground"], replay=replay,
                         transition_inputs=context["transition_inputs"])
        result, failures = _call(staged_path, context, **arguments)
        assert result[1], failures
        with netCDF4.Dataset(staged_path, "r+") as dataset:
            dataset["candidate_geopotential"][:, 1, 1] = collapsed
        result, failures = _call(staged_path, context, **arguments)
        assert not result[1], "accepted collapsed Phi instead of two stored stages"
        assert "independent pressure transition geopotential replay" in failures


def check(path: Path) -> None:
    context = _context(path)
    _same_domain(path, context)
    _same_domain_pressure_rounding_receipt(path, context)
    _signed_surface_pressure_seed(path, context)
    _added_bottom(path, context)
    _double_rounding(path, context)

    # Scoped direct cleanliness must not lift the file-level transition gate.
    summary, failures = validate_file(path)
    assert "pressure transition requires complete exact stored-state replay" in failures
    assert summary["promotion_eligible"] is False
    print(f"PASS transition geopotential scope checks: {path.name}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
