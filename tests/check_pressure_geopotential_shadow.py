#!/usr/bin/env python3
"""Exercise stored pressure-geopotential replay and reject isolated mutations."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

from check_pressure_candidate_shadow import reject, rewrite_without, validate


ATTRIBUTES = {
    "pressure_geopotential_contract",
    "pressure_geopotential_reference",
    "pressure_geopotential_native_assessed",
}
SURFACE_ATTRIBUTES = ATTRIBUTES | {
    "pressure_geopotential_surface_condensate_convention",
}
VARIABLES = {
    f"{state}_geopotential{suffix}"
    for state in ("background", "candidate")
    for suffix in ("", "_valid", "_quality", "_source")
} | {"geopotential_support", "geopotential_reference_level"}


def set_attribute(path, name, value, field=None):
    with netCDF4.Dataset(path, "r+") as dataset:
        target = dataset if field is None else dataset[field]
        target.setncattr(name, value)


def set_cell(path, field, index, value):
    with netCDF4.Dataset(path, "r+") as dataset:
        dataset[field][index] = value


def add_manufactured_source(path):
    with netCDF4.Dataset(path, "r+") as dataset:
        for state in ("background", "candidate"):
            field = dataset[f"{state}_geopotential_source"]
            field[...] = np.asarray(field[:], dtype=np.int32) | (1 << 12)


def check(path: Path) -> None:
    summary, failures = validate(path)
    assert not failures, failures
    assert summary["pressure_geopotential_independently_validated"] is True
    assert summary["pressure_geopotential_native_assessed"] is False
    assert summary["pressure_analysis_candidate_promotion_eligible"] is False
    with netCDF4.Dataset(path) as dataset:
        contract = str(dataset.getncattr("pressure_geopotential_contract"))
        surface_variant = contract == "pressure_hydrostatic_surface_increment_v1"
        assert contract in {
            "pressure_hydrostatic_increment_v1",
            "pressure_hydrostatic_surface_increment_v1",
        }
        assert dataset.getncattr("pressure_geopotential_reference") == (
            "fixed_terrain_surface" if surface_variant else "lowest_represented_center"
        )
        if surface_variant:
            assert dataset.getncattr(
                "pressure_geopotential_surface_condensate_convention"
            ) == "WPS_SURFACE_ZERO_CONDENSATE"
            assert int(dataset.getncattr("cloud_bal_schema_version")) == 5
        before = np.asarray(dataset["background_geopotential"][:])
        after = np.asarray(dataset["candidate_geopotential"][:])
        support = np.asarray(dataset["geopotential_support"][:]) == 1
        reference = np.asarray(dataset["geopotential_reference_level"][:])
        selected = tuple(np.argwhere(after != before)[0])
        outside = tuple(np.argwhere(~support)[0])
        thermo = np.asarray(dataset["thermo_support"][:]) == 1
        propagated = tuple(np.argwhere((after != before) & ~thermo)[0])
        column_changed = np.asarray(dataset["column_changed"][:]) == 1
        assert np.any((after != before) & ~column_changed), "fixture needs a Phi-only stage change"
        column = selected[1:]
        above = np.asarray(dataset["above_ground"][:], dtype=bool)
        bottom = int(np.flatnonzero(above[:, column[0], column[1]])[0])
        anchor = ((bottom if surface_variant else int(reference[column]) - 1), *column)
        assert support[selected]
        if surface_variant:
            assert before[anchor] != after[anchor], (
                "surface-anchor fixture must exercise the nonzero first-layer response"
            )
            assert int(reference[column]) == 0
        else:
            assert before[anchor] == after[anchor]
        assert np.array_equal(before[~support], after[~support])
        assert np.all(reference[~support.any(axis=0)] == 0)
        assert dataset["candidate_geopotential"].dtype == np.dtype("float32")
        assert dataset["geopotential_reference_level"].dimensions == ("y", "x")
        for name in VARIABLES:
            assert name in dataset.variables, name

    with tempfile.TemporaryDirectory(prefix="pressure-phi-mutations-") as directory:
        damaged = Path(directory) / "mutated.nc"
        reject(path, damaged, add_manufactured_source, "manufactured Phi source on both states")
        attributes = SURFACE_ATTRIBUTES if surface_variant else ATTRIBUTES
        for name in sorted(attributes | VARIABLES):
            rewrite_without(path, damaged, {name})
            _, failures = validate(damaged)
            assert failures, f"accepted incomplete Phi extension: {name}"

        if surface_variant:
            # Canonical-5 boundary values are part of the physical replay, not
            # decorative metadata.  Omitting one member or changing one state
            # must invalidate the artifact independently of Phi payloads.
            rewrite_without(path, damaged, {"candidate_surface_vapor"})
            _, failures = validate(damaged)
            assert failures, "accepted missing canonical-5 surface boundary value"
            reject(
                path,
                damaged,
                lambda output: set_cell(
                    output, "candidate_surface_temperature", column, 1.0
                ),
                "changed surface boundary value",
            )
            reject(
                path,
                damaged,
                lambda output: set_attribute(
                    output,
                    "pressure_geopotential_surface_condensate_convention",
                    "forged",
                ),
                "wrong surface condensate convention",
            )

        mutations = [
            ("candidate Phi", "candidate_geopotential", selected, after[selected] + 1.0),
            ("background Phi", "background_geopotential", selected, before[selected] + 1.0),
            ("NaN Phi", "candidate_geopotential", selected, np.nan),
            ("anchor change", "candidate_geopotential", anchor, after[anchor] + 1.0),
            ("outside change", "candidate_geopotential", outside, after[outside] + 1.0),
            ("truncated support", "geopotential_support", selected, 0),
            ("nonbinary support", "geopotential_support", selected, 2),
            (
                "wrong reference",
                "geopotential_reference_level",
                column,
                1 if surface_variant else 0,
            ),
            ("invalid Phi", "candidate_geopotential_valid", selected, 0),
            ("missing source", "candidate_geopotential_source", selected, 0),
            ("missing derived source", "candidate_geopotential_source", selected, 1),
            ("bad quality", "candidate_geopotential_quality", selected, 1),
            ("propagated change mask", "overall_changed", propagated, 0),
        ]
        if surface_variant:
            mutations.append(
                (
                    "fixed-lowest first layer",
                    "candidate_geopotential",
                    anchor,
                    before[anchor],
                )
            )
        for label, field, index, value in mutations:
            reject(path, damaged, lambda output, f=field, i=index, v=value:
                   set_cell(output, f, i, v), label)

        attribute_mutations = [
            ("pressure_geopotential_contract", "forged", None),
            ("pressure_geopotential_reference", "physical_surface", None),
            ("pressure_geopotential_native_assessed", np.int32(1), None),
            ("pressure_geopotential_native_assessed", np.float64(0), None),
            ("pressure_geopotential_unknown", "forged", None),
            ("units", "m", "candidate_geopotential"),
            ("valid_time", "190001010000", "candidate_geopotential"),
            ("scale_factor", np.float32(1), "candidate_geopotential"),
            ("index_base", np.int32(0), "geopotential_reference_level"),
            ("index_base", np.float64(1), "geopotential_reference_level"),
            ("inactive_value", np.int32(-1), "geopotential_reference_level"),
            ("semantics", "physical_surface", "geopotential_reference_level"),
        ]
        if surface_variant:
            attribute_mutations.append(
                (
                    "pressure_geopotential_surface_condensate_convention",
                    "forged",
                    None,
                )
            )
        for name, value, field in attribute_mutations:
            reject(path, damaged, lambda output, n=name, v=value, f=field:
                   set_attribute(output, n, v, f), f"{field or 'global'} {name}")

        # Same values with the wrong storage contract are not interchangeable.
        for dtype, dimensions in (("i2", ("z", "y", "x")),
                                  ("i4", ("z", "x", "y"))):
            rewrite_without(path, damaged, {"geopotential_support"})
            with netCDF4.Dataset(damaged, "r+") as dataset:
                variable = dataset.createVariable("geopotential_support", dtype, dimensions)
                variable.setncattr("units", "1")
                variable[...] = support.astype(np.int32)
            _, failures = validate(damaged)
            assert failures, f"accepted malformed support storage: {dtype}, {dimensions}"

        # Stripping the extension cannot gain a Phi claim; overall changes
        # unsupported by the remaining fields may also reject the artifact.
        rewrite_without(path, damaged, attributes | VARIABLES)
        historical, failures = validate(damaged)
        assert historical["pressure_geopotential_independently_validated"] is False
        assert historical["pressure_geopotential_native_assessed"] is False
    print(f"PASS pressure geopotential independent replay/mutations: {path.name}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
