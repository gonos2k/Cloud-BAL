#!/usr/bin/env python3
"""Focused tests for the not-yet-authoritative pressure-transition payload."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    PRESSURE_TRANSITION_FIELDS,
    PRESSURE_TRANSITION_VALUE_UNITS,
    SOURCE_COLUMN_PHYSICS,
    pressure_transition_payload_signalled,
    read_pressure_transition_seed_payload,
)
from pressure_transition_reference import (  # noqa: E402
    pressure_cell_geometry,
    reconstruct_thermo_state_reference,
    remap_pressure_state_reference,
    validate_transition_seed_mass_reference,
)


SHAPE = (3, 2, 2)  # z, y, x as exposed by netCDF4 for Fortran z,y,x fields
SURFACE_SHAPE = SHAPE[1:]
EPOCH = 1_725_000_000


def _field_values(field: str) -> np.ndarray:
    values = np.full(SHAPE, 1.0, dtype=np.float32)
    if field == "pressure":
        values = np.asarray(
            [[[100000.0, 100000.0], [100000.0, np.nan]],
             [[95000.0, 95000.0], [95000.0, np.nan]],
             [[90000.0, 90000.0], [90000.0, np.nan]]],
            dtype=np.float32,
        )
    elif field == "temperature":
        values.fill(290.0)
    elif field == "vapor":
        values.fill(0.01)
    elif field in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"):
        values.fill(0.001)
    elif field in ("u", "v"):
        values.fill(2.0)
    elif field == "omega":
        values.fill(0.0)
    elif field == "geopotential":
        values.fill(1000.0)
    else:
        raise AssertionError(field)
    values[:, 1, 1] = np.nan
    return values


def _metadata() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.ones(SHAPE, dtype=np.int32)
    valid[:, 1, 1] = 0
    quality = np.zeros(SHAPE, dtype=np.int32)
    quality[:, 1, 1] = 1  # opaque raw-missing metadata outside the seed domain
    source = np.ones(SHAPE, dtype=np.int32)
    source[:, 1, 1] = 0
    return valid, quality, source


def write_fixture(
    path: Path,
    *,
    omit: str | None = None,
    value_dtype: dict[str, str] | None = None,
    mask_dtype: str = "i4",
    v2: bool = False,
) -> None:
    value_dtype = {} if value_dtype is None else value_dtype
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("z", SHAPE[0])
        dataset.createDimension("y", SHAPE[1])
        dataset.createDimension("x", SHAPE[2])
        dataset.setncattr("pressure_transition_contract", "pressure_transition_seed_v1")
        dataset.setncattr(
            "pressure_transition_support_semantics",
            "background_support_plus_candidate_new_cells_v1",
        )

        domain = np.ones(SHAPE, dtype=np.int32)
        domain[:, 1, 1] = 0
        for name in ("candidate_above_ground", "transition_seed_above_ground"):
            if name == omit:
                continue
            variable = dataset.createVariable(name, mask_dtype, ("z", "y", "x"))
            variable.units = "1"
            variable[:] = domain

        if v2:
            original_domain = domain.copy()
            original_domain[0, 0, 0] = 0  # one newly represented bottom cell
            above = dataset.createVariable("above_ground", mask_dtype, ("z", "y", "x"))
            above.units = "1"
            above[:] = original_domain
            pressure = dataset.createVariable("pressure", "f4", ("z",))
            pressure.units = "Pa"
            pressure[:] = np.asarray([100000.0, 95000.0, 90000.0], dtype=np.float32)

        dry_mass = dataset.createVariable(
            "transition_seed_dry_air_mass_measure", "f8", ("z", "y", "x")
        )
        dry_mass.units = "kg dryair"
        dry_mass[:] = np.where(domain, 1000.0, 0.0)

        surface = dataset.createVariable(
            "transition_seed_surface_pressure", "f4", ("y", "x")
        )
        surface.units = "Pa"
        surface.valid_time = np.int64(EPOCH)
        surface[:] = np.full(SURFACE_SHAPE, 100000.0, dtype=np.float32)
        surface_valid = dataset.createVariable(
            "transition_seed_surface_pressure_valid", "i4", ("y", "x")
        )
        surface_quality = dataset.createVariable(
            "transition_seed_surface_pressure_quality", "i4", ("y", "x")
        )
        surface_source = dataset.createVariable(
            "transition_seed_surface_pressure_source", "i4", ("y", "x")
        )
        for variable in (surface_valid, surface_quality, surface_source):
            variable.units = "1"
        surface_valid[:] = np.ones(SURFACE_SHAPE, dtype=np.int32)
        surface_quality[:] = np.zeros(SURFACE_SHAPE, dtype=np.int32)
        surface_source[:] = np.ones(SURFACE_SHAPE, dtype=np.int32)

        for field in PRESSURE_TRANSITION_FIELDS:
            name = f"transition_seed_{field}"
            if name == omit:
                continue
            value = dataset.createVariable(
                name,
                value_dtype.get(name, "f4"),
                ("z", "y", "x"),
            )
            value.units = PRESSURE_TRANSITION_VALUE_UNITS[field]
            value.valid_time = np.int64(EPOCH)
            value[:] = _field_values(field)
            valid, quality, source = _metadata()
            for suffix, metadata in (
                ("_valid", valid),
                ("_quality", quality),
                ("_source", source),
            ):
                metadata_name = f"{name}{suffix}"
                if metadata_name == omit:
                    continue
                variable = dataset.createVariable(metadata_name, "i4", ("z", "y", "x"))
                variable.units = "1"
                variable[:] = metadata

        if v2:
            pressure_centers = np.asarray(
                dataset["pressure"][:], dtype=np.float32
            )[:, None, None]
            # v2 carries complete pressure centers; the legacy seed metadata
            # still records which old cells were usable.
            dataset["transition_seed_pressure"][:] = np.broadcast_to(
                pressure_centers, SHAPE
            )
            background_valid, background_quality, background_source = _metadata()
            background_valid[0, 0, 0] = 0
            background_quality[0, 0, 0] = 1
            background_source[0, 0, 0] = 0
            seed_valid = np.asarray(dataset["transition_seed_pressure_valid"][:])
            seed_quality = np.asarray(dataset["transition_seed_pressure_quality"][:])
            seed_source = np.asarray(dataset["transition_seed_pressure_source"][:])
            added = domain.astype(bool) & ~original_domain.astype(bool)
            candidate_source = np.where(
                added, seed_source | SOURCE_COLUMN_PHYSICS, background_source
            ).astype(np.int32)
            for name, valid, quality, source in (
                (
                    "transition_background_pressure",
                    background_valid,
                    background_quality,
                    background_source,
                ),
                (
                    "transition_candidate_pressure",
                    seed_valid,
                    seed_quality,
                    candidate_source,
                ),
            ):
                if name == omit:
                    continue
                value = dataset.createVariable(
                    name, value_dtype.get(name, "f4"), ("z", "y", "x")
                )
                value.units = "Pa"
                value.valid_time = np.int64(EPOCH)
                value[:] = np.broadcast_to(pressure_centers, SHAPE)
                for suffix, metadata in (
                    ("_valid", valid),
                    ("_quality", quality),
                    ("_source", source),
                ):
                    metadata_name = f"{name}{suffix}"
                    if metadata_name == omit:
                        continue
                    variable = dataset.createVariable(metadata_name, "i4", ("z", "y", "x"))
                    variable.units = "1"
                    variable[:] = metadata
            dataset.pressure_transition_contract = "pressure_transition_seed_v2"


def read(path: Path):
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        result = read_pressure_transition_seed_payload(
            dataset, SHAPE, EPOCH, require
        )
    return result, failures


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)

    positive = root / "positive.nc"
    write_fixture(positive)
    (present, clean, arrays), failures = read(positive)
    assert present and clean and not failures
    with netCDF4.Dataset(positive) as dataset:
        assert pressure_transition_payload_signalled(dataset)
    assert arrays["transition_seed_temperature"].shape == SHAPE
    assert arrays["transition_seed_surface_pressure"].shape == SURFACE_SHAPE
    shape_failures = []
    with netCDF4.Dataset(positive) as dataset:
        present, clean, _ = read_pressure_transition_seed_payload(
            dataset, (3, 2, 3), EPOCH,
            lambda ok, message: shape_failures.append(message) if not ok else None,
        )
    assert present and not clean and shape_failures

    absent = root / "absent.nc"
    with netCDF4.Dataset(absent, "w") as dataset:
        dataset.createDimension("z", SHAPE[0])
        dataset.createDimension("y", SHAPE[1])
        dataset.createDimension("x", SHAPE[2])
    (present, clean, arrays), failures = read(absent)
    assert not present and not clean and not arrays and not failures

    malformed = {
        "missing_member.nc": lambda path: write_fixture(
            path, omit="transition_seed_omega_source"
        ),
        "bad_mask_type.nc": lambda path: write_fixture(
            path, mask_dtype="i2"
        ),
        "bad_value_type.nc": lambda path: write_fixture(
            path, value_dtype={"transition_seed_u": "f8"}
        ),
    }
    for name, build in malformed.items():
        path = root / name
        build(path)
        (present, clean, _), failures = read(path)
        assert present and not clean and failures, name

    wrong_time = root / "wrong_time.nc"
    write_fixture(wrong_time)
    with netCDF4.Dataset(wrong_time, "r+") as dataset:
        dataset["transition_seed_u"].valid_time = np.int64(EPOCH + 1)
    (present, clean, _), failures = read(wrong_time)
    assert present and not clean and failures

    bad_source = root / "bad_source.nc"
    write_fixture(bad_source)
    with netCDF4.Dataset(bad_source, "r+") as dataset:
        dataset["transition_seed_u_source"][0, 0, 0] = np.int32(1 << 13)
    (present, clean, _), failures = read(bad_source)
    assert present and not clean and failures

    bad_units = root / "bad_units.nc"
    write_fixture(bad_units)
    with netCDF4.Dataset(bad_units, "r+") as dataset:
        dataset["transition_seed_omega"].units = "m s-1"
    (present, clean, _), failures = read(bad_units)
    assert present and not clean and failures

    v2 = root / "v2.nc"
    write_fixture(v2, v2=True)
    (present, clean, arrays), failures = read(v2)
    assert present and clean and not failures
    with netCDF4.Dataset(v2) as dataset:
        assert pressure_transition_payload_signalled(dataset)
        pressure = np.asarray(dataset["pressure"][:], dtype=np.float32)
        above = np.asarray(dataset["above_ground"][:], dtype=bool)
        candidate = np.asarray(dataset["candidate_above_ground"][:], dtype=bool)
    expected_pressure = np.broadcast_to(pressure[:, None, None], SHAPE)
    added = candidate & ~above
    assert np.count_nonzero(added) == 1
    for name in ("transition_background_pressure", "transition_candidate_pressure"):
        np.testing.assert_array_equal(arrays[name], expected_pressure)
    # The old/background pressure group is intentionally invalid on the new
    # bottom, while the candidate group has complete new-cell coverage.
    assert arrays["transition_background_pressure_valid"][added].tolist() == [0]
    assert arrays["transition_candidate_pressure_valid"][added].tolist() == [1]
    assert arrays["transition_seed_pressure_valid"][0, 1, 1] == 0
    for suffix in ("_valid", "_quality", "_source"):
        expected_metadata = np.where(
            added,
            arrays[f"transition_seed_pressure{suffix}"],
            arrays[f"transition_background_pressure{suffix}"],
        )
        if suffix == "_source":
            expected_metadata = np.where(
                added,
                arrays["transition_seed_pressure_source"] | SOURCE_COLUMN_PHYSICS,
                arrays["transition_background_pressure_source"],
            )
        np.testing.assert_array_equal(
            arrays[f"transition_candidate_pressure{suffix}"],
            expected_metadata,
        )

    for missing in (
        "transition_background_pressure",
        "transition_candidate_pressure",
        "transition_candidate_pressure_source",
    ):
        path = root / f"v2_missing_{missing}.nc"
        write_fixture(path, v2=True, omit=missing)
        (present, clean, _), failures = read(path)
        assert present and not clean and failures, missing

    v2_bad_type = root / "v2_bad_type.nc"
    write_fixture(
        v2_bad_type,
        v2=True,
        value_dtype={"transition_background_pressure": "f8"},
    )
    (present, clean, _), failures = read(v2_bad_type)
    assert present and not clean and failures

    v2_bad_time = root / "v2_bad_time.nc"
    write_fixture(v2_bad_time, v2=True)
    with netCDF4.Dataset(v2_bad_time, "r+") as dataset:
        dataset["transition_candidate_pressure"].valid_time = np.int64(EPOCH + 1)
    (present, clean, _), failures = read(v2_bad_time)
    assert present and not clean and failures

    v2_bad_units = root / "v2_bad_units.nc"
    write_fixture(v2_bad_units, v2=True)
    with netCDF4.Dataset(v2_bad_units, "r+") as dataset:
        dataset["transition_background_pressure"].units = "hPa"
    (present, clean, _), failures = read(v2_bad_units)
    assert present and not clean and failures

    for bad_name in (
        "transition_background_pressure", "transition_candidate_pressure"
    ):
        v2_bad_values = root / f"v2_bad_{bad_name}_values.nc"
        write_fixture(v2_bad_values, v2=True)
        with netCDF4.Dataset(v2_bad_values, "r+") as dataset:
            dataset[bad_name][0, 0, 0] += np.float32(1.0)
        (present, clean, _), failures = read(v2_bad_values)
        assert present and not clean and failures, bad_name

    # Candidate pressure provenance is copied from background on every
    # retained cell, including the old inactive placeholder, and from the
    # seed only on the newly added cell.
    metadata_mutations = (
        ((1, 0, 0), "_valid", 0),
        ((1, 0, 0), "_quality", 8),
        ((1, 0, 0), "_source", 2),
        ((1, 1, 1), "_valid", 1),
        ((1, 1, 1), "_quality", 9),
        ((1, 1, 1), "_source", 1),
    )
    for cell, suffix, value in metadata_mutations:
        path = root / f"v2_bad_candidate_metadata{suffix}_{cell[0]}_{cell[1]}_{cell[2]}.nc"
        write_fixture(path, v2=True)
        with netCDF4.Dataset(path, "r+") as dataset:
            dataset[f"transition_candidate_pressure{suffix}"][cell] = np.int32(value)
        (present, clean, _), failures = read(path)
        assert present and not clean and failures, (cell, suffix)

    v2_bad_added_seed = root / "v2_bad_added_seed.nc"
    write_fixture(v2_bad_added_seed, v2=True)
    with netCDF4.Dataset(v2_bad_added_seed, "r+") as dataset:
        # Seed provenance without the producer's column-physics bit is not a
        # valid candidate source on an added cell.
        dataset["transition_candidate_pressure_source"][0, 0, 0] = np.int32(1)
    (present, clean, _), failures = read(v2_bad_added_seed)
    assert present and not clean and failures

def check_physical_replay(dataset):
    """Compare the actual Fortran thermo/remap result with independent equations."""
    assert dataset.numerical_test_probe == 1 and dataset.science_authority == 0
    names = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
    old_domain = np.asarray(dataset["above_ground"][:], dtype=bool)
    final_domain = np.asarray(dataset["candidate_above_ground"][:], dtype=bool)
    pressure = np.asarray(dataset["pressure"][:], dtype=np.float64)
    area = np.full(old_domain.shape[1:], dataset.grid_dx_m * dataset.grid_dy_m)
    old_interfaces, old_pressure_mass = pressure_cell_geometry(
        pressure, dataset["background_surface_pressure"][:], old_domain, area,
    )
    new_interfaces, _ = pressure_cell_geometry(
        pressure, dataset["candidate_surface_pressure"][:], final_domain, area,
    )
    seed_domain = np.asarray(dataset["transition_seed_above_ground"][:], dtype=bool)
    _, seed_pressure_mass = pressure_cell_geometry(
        pressure, dataset["transition_seed_surface_pressure"][:], seed_domain, area,
    )
    old_species = np.stack([dataset[f"background_{name}"][:] for name in names]).astype(np.float64)
    old_species = np.where(old_domain, old_species, 0.0)
    np.testing.assert_allclose(
        dataset["dry_air_mass_measure"][:],
        old_pressure_mass / (1.0 + old_species.sum(axis=0)),
        rtol=128 * np.finfo(np.float64).eps, atol=0.0,
        err_msg="original donor mass",
    )
    seed_species = np.stack([dataset[f"transition_seed_{name}"][:] for name in names]).astype(np.float64)
    validate_transition_seed_mass_reference(
        seed_pressure_mass, seed_species, seed_domain,
        dataset["transition_seed_dry_air_mass_measure"][:],
    )
    post_t, post_q, post_mass = reconstruct_thermo_state_reference(
        np.broadcast_to(pressure[:, None, None], old_domain.shape), old_pressure_mass,
        dataset["background_temperature"][:], old_species,
        np.asarray(dataset["thermo_support"][:], dtype=bool),
        dataset["thermo_surface"][:], float(dataset.thermo_target_rh),
    )
    assert np.any(post_q[:, old_domain] != old_species[:, old_domain]), "thermo must execute"
    assert np.any(new_interfaces[0] != old_interfaces[0]), "pressure remap must execute"
    final_mass, final_t, final_q = remap_pressure_state_reference(
        old_interfaces, post_mass, post_t, post_q, old_domain,
        new_interfaces, final_domain, area,
        dataset["transition_seed_temperature"][:], seed_species,
    )
    np.testing.assert_array_equal(
        dataset["candidate_temperature"][:][final_domain], final_t[final_domain],
        err_msg="independent final temperature",
    )
    for index, name in enumerate(names):
        np.testing.assert_array_equal(
            dataset[f"candidate_{name}"][:][final_domain], final_q[index][final_domain],
            err_msg=f"independent final {name}",
        )
    np.testing.assert_allclose(
        dataset["candidate_dry_air_mass_measure"][:][final_domain], final_mass[final_domain],
        rtol=128 * np.finfo(np.float64).eps, atol=0.0,
        err_msg="independent final dry mass",
    )


for filename in sys.argv[1:]:
    failures = []
    with netCDF4.Dataset(filename) as dataset:
        shape = tuple(len(dataset.dimensions[name]) for name in ("z", "y", "x"))
        epoch = int(dataset["transition_seed_pressure"].valid_time)
        present, clean, arrays = read_pressure_transition_seed_payload(
            dataset, shape, epoch,
            lambda ok, message: failures.append(message) if not ok else None,
        )
        check_physical_replay(dataset)
    assert present and clean and not failures, (filename, failures)
    with tempfile.TemporaryDirectory(prefix="transition-physical-mutation-") as directory:
        changed = Path(directory) / "changed.nc"
        for name, increment in (("temperature", 0.25), ("vapor", 0.001),
                                ("dry_air_mass_measure", 1.0e6)):
            shutil.copyfile(filename, changed)
            with netCDF4.Dataset(changed, "r+") as dataset:
                cell = tuple(np.argwhere(dataset["candidate_above_ground"][:] == 1)[0])
                dataset[f"candidate_{name}"][cell] += increment
            with netCDF4.Dataset(changed) as dataset:
                try:
                    check_physical_replay(dataset)
                except AssertionError:
                    pass
                else:
                    raise AssertionError(f"mutated final {name} accepted")
    print(f"Fortran coupled thermo/pressure replay and mutations passed: {filename}")

print("Pressure-transition payload validator tests passed")
