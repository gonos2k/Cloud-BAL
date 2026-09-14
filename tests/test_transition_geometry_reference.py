#!/usr/bin/env python3
"""Focused geometry-reference tests for pressure-domain transitions."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_shadow_diagnostics as validator  # noqa: E402


SHAPE = (4, 1, 1)
PRESSURE = np.asarray([101000.0, 100000.0, 99000.0, 98000.0], dtype=np.float64)
GRID_DX = 5000.0
GRID_DY = 5000.0


class FakeVariable:
    def __init__(self, data, dimensions, units):
        self._data = np.asarray(data)
        self.dimensions = dimensions
        self.dtype = self._data.dtype
        self.units = units

    def __getitem__(self, key):
        return self._data[key]

    def ncattrs(self):
        return ["units"]


class FakeDataset:
    def __init__(self, attributes, variables):
        self._attributes = attributes
        self.variables = variables

    def __getitem__(self, name):
        return self.variables[name]

    def ncattrs(self):
        return list(self._attributes)

    def __getattr__(self, name):
        try:
            return self._attributes[name]
        except KeyError as error:
            raise AttributeError(name) from error


def expected_geometry(pressure, surface, active):
    active_bottom = np.argmax(active, axis=0)
    interfaces = np.empty((pressure.size + 1, 1, 1), dtype=np.float64)
    interfaces[0] = surface
    for index in range(1, pressure.size):
        midpoint = 0.5 * (pressure[index - 1] + pressure[index])
        interfaces[index] = np.where(index <= active_bottom, surface, midpoint)
    interfaces[-1] = np.minimum(surface, pressure[-1] - 0.5 * (pressure[-2] - pressure[-1]))
    cell_dp = interfaces[:-1] - interfaces[1:]
    cell_dp = np.where(active, cell_dp, 0.0)
    pressure_mass = GRID_DX * GRID_DY * cell_dp / 9.80665
    return interfaces, cell_dp, pressure_mass


def make_dataset(
    *,
    pressure=PRESSURE,
    background_surface=99990.0,
    candidate_surface=100010.0,
    requested_surface=None,
    background_active=None,
    candidate_active=None,
    support=None,
):
    pressure = np.asarray(pressure, dtype=np.float64)
    shape = (pressure.size, 1, 1)
    background_surface = np.full((1, 1), background_surface, dtype=np.float32)
    candidate_surface = np.full((1, 1), candidate_surface, dtype=np.float32)
    if requested_surface is None:
        requested_surface = candidate_surface.astype(np.float64)
    else:
        requested_surface = np.full((1, 1), requested_surface, dtype=np.float64)

    pressure_background_domain = pressure[:, None, None] <= background_surface
    pressure_candidate_domain = pressure[:, None, None] <= candidate_surface
    if background_active is None:
        background_active = pressure_background_domain
    if candidate_active is None:
        candidate_active = pressure_candidate_domain
    background_active = np.asarray(background_active, dtype=bool)
    candidate_active = np.asarray(candidate_active, dtype=bool)
    if support is None:
        support = candidate_active.copy()
    support = np.asarray(support, dtype=np.int32)

    base_interface, base_cell_dp, base_pressure_mass = expected_geometry(
        pressure, background_surface, background_active
    )
    candidate_interface, candidate_cell_dp, candidate_pressure_mass = expected_geometry(
        pressure, candidate_surface, candidate_active
    )

    changed = background_surface.view(np.uint32) != candidate_surface.view(np.uint32)
    source = np.where(changed, 1 | validator.SOURCE_COLUMN_PHYSICS, 1).astype(np.int32)
    surface_inputs = {
        "background_surface_pressure": background_surface,
        "candidate_surface_pressure": candidate_surface,
        "background_surface_pressure_valid": np.ones((1, 1), dtype=np.int32),
        "candidate_surface_pressure_valid": np.ones((1, 1), dtype=np.int32),
        "background_surface_pressure_quality": np.zeros((1, 1), dtype=np.int32),
        "candidate_surface_pressure_quality": np.zeros((1, 1), dtype=np.int32),
        "background_surface_pressure_source": np.ones((1, 1), dtype=np.int32),
        "candidate_surface_pressure_source": source,
    }

    attributes = {
        "pressure_geometry_contract": validator.PRESSURE_GEOMETRY_CONTRACT,
        "continuity_geometry_scope": validator.PRESSURE_GEOMETRY_CONTINUITY_SCOPE,
        "grid_dx_m": np.float64(GRID_DX),
        "grid_dy_m": np.float64(GRID_DY),
    }
    attributes.update(
        {name: np.zeros(6, dtype=np.float64) for name in validator.GEOMETRY_ANALYSIS_VECTOR_ATTRIBUTES}
    )
    attributes.update(
        {name: np.float64(0.0) for name in validator.GEOMETRY_ANALYSIS_FLOAT_ATTRIBUTES}
    )
    attributes.update(
        {name: np.int64(0) for name in validator.GEOMETRY_ANALYSIS_COUNT_ATTRIBUTES}
    )

    variables = {
        "requested_surface_pressure": FakeVariable(requested_surface, ("y", "x"), "Pa"),
        "candidate_pressure_interface": FakeVariable(
            candidate_interface, ("z_interface", "y", "x"), "Pa"
        ),
        "candidate_cell_dp": FakeVariable(candidate_cell_dp, ("z", "y", "x"), "Pa"),
        "candidate_pressure_mass_measure": FakeVariable(
            candidate_pressure_mass, ("z", "y", "x"), "kg"
        ),
        "candidate_dry_air_mass_measure": FakeVariable(
            np.where(candidate_active, 1.0, 0.0), ("z", "y", "x"), "kg dryair"
        ),
        "geopotential_support": FakeVariable(support, ("z", "y", "x"), "1"),
        "geopotential_reference_level": FakeVariable(
            np.zeros((1, 1), dtype=np.int32), ("y", "x"), "1"
        ),
        "continuity_original_background": FakeVariable(
            np.zeros(shape, dtype=np.float64), ("z", "y", "x"), "s-1"
        ),
    }
    return (
        FakeDataset(attributes, variables),
        base_interface,
        base_cell_dp,
        base_pressure_mass,
        np.where(background_active, 1.0, 0.0),
        surface_inputs,
        background_active,
        candidate_active,
    )


def read_fixture(dataset, base_interface, base_cell_dp, base_pressure_mass, base_dry_mass,
                 surface_inputs, above, candidate_above=None, pressure=PRESSURE):
    failures = []

    def require(condition, message):
        if not condition:
            failures.append(message)

    result = validator.read_pressure_geometry_extension(
        dataset,
        above.shape,
        pressure,
        above,
        base_interface,
        base_cell_dp,
        base_pressure_mass,
        base_dry_mass,
        True,
        True,
        surface_inputs,
        7,
        require,
        candidate_above=candidate_above,
    )
    return result, failures


def test_nontransition_positive_request_keeps_domain_and_rebuilds_interfaces():
    fixture = make_dataset(background_surface=100010.0, candidate_surface=100080.0)
    (present, clean, arrays), failures = read_fixture(*fixture[:-1], None)
    assert present and clean, failures
    expected, _, _ = expected_geometry(PRESSURE, np.asarray([[100080.0]], dtype=np.float32), fixture[-1])
    np.testing.assert_allclose(
        arrays["candidate_pressure_interface"], expected, rtol=0.0, atol=1.0e-10
    )


def test_transition_one_center_uses_candidate_mask_and_pressure_crossing():
    fixture = make_dataset()
    dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate = fixture
    (present, clean, arrays), failures = read_fixture(
        dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate
    )
    assert present and clean, failures
    expected_interface = np.asarray(
        [100010.0, 100010.0, 99500.0, 98500.0, 97500.0], dtype=np.float64
    ).reshape(5, 1, 1)
    np.testing.assert_allclose(
        arrays["candidate_pressure_interface"], expected_interface,
        rtol=0.0, atol=1.0e-10
    )


def test_same_domain_terrain_exclusion_is_preserved():
    above = np.asarray([[[False]], [[False]], [[True]], [[True]]])
    fixture = make_dataset(
        background_surface=100060.0,
        candidate_surface=100080.0,
        background_active=above,
        candidate_active=above,
        support=above,
    )
    dataset, base_interface, base_dp, base_mass, base_dry, surfaces, _, candidate = fixture
    (present, clean, arrays), failures = read_fixture(
        dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate
    )
    assert present and clean, failures
    expected_interface = np.asarray(
        [100080.0, 100080.0, 100080.0, 98500.0, 97500.0], dtype=np.float64
    ).reshape(5, 1, 1)
    np.testing.assert_allclose(
        arrays["candidate_pressure_interface"], expected_interface,
        rtol=0.0, atol=1.0e-10
    )
    assert arrays["candidate_cell_dp"][1, 0, 0] == 0.0


def test_crossing_without_candidate_mask_is_rejected():
    fixture = make_dataset()
    (present, clean, _), failures = read_fixture(*fixture[:-1], None)
    assert present and not clean
    assert any("stored candidate pressure domain classification" in message for message in failures)


def test_transition_rejects_invalid_masks_and_requests():
    fixture = make_dataset()
    dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate = fixture

    cases = []
    excluded = candidate.copy()
    excluded[1, 0, 0] = False
    cases.append((excluded, "candidate domain preserves terrain exclusions"))

    removed = candidate.copy()
    removed[2, 0, 0] = False
    cases.append((removed, "candidate domain preserves terrain exclusions"))

    too_many_pressure = np.asarray([101000.0, 100000.0, 99000.0, 98000.0, 97000.0])
    too_many_fixture = make_dataset(
        pressure=too_many_pressure,
        background_surface=97990.0,
        candidate_surface=100010.0,
    )
    too_many = too_many_fixture[-1]
    cases.append((too_many, "at most one added pressure center"))

    wide_pressure = PRESSURE
    wide = make_dataset(background_surface=99990.0, candidate_surface=100110.0)
    cases.append((wide[-1], "positive pressure transition within 100 Pa"))

    for candidate_mask, expected_message in cases[:2]:
        (present, clean, _), failures = read_fixture(
            dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate_mask
        )
        assert present and not clean
        assert any(expected_message in message for message in failures)

    unsupported = make_dataset(support=np.asarray(
        [[[True]], [[False]], [[True]], [[True]]], dtype=bool
    ))
    (present, clean, _), failures = read_fixture(
        *unsupported[:-1], unsupported[-1]
    )
    assert present and not clean
    assert any("new cells have geometry support" in message for message in failures)

    removal_fixture = make_dataset(
        background_surface=100010.0, candidate_surface=99990.0
    )
    (present, clean, _), failures = read_fixture(
        *removal_fixture[:-1], removal_fixture[-1]
    )
    assert present and not clean
    assert any(
        "pressure transition does not remove pressure-accessible centers" in message
        for message in failures
    )

    (present, clean, _), failures = read_fixture(
        *wide[:-1], wide[-1], pressure=wide_pressure
    )
    assert present and not clean
    assert any("within 100 Pa" in message for message in failures)

    (present, clean, _), failures = read_fixture(
        *too_many_fixture[:-1], too_many, pressure=too_many_pressure
    )
    assert present and not clean
    assert any("at most one added pressure center" in message for message in failures)


def test_transition_rejects_shape_type_and_raw_stored_request_mismatch():
    fixture = make_dataset()
    dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above, candidate = fixture

    (present, clean, _), failures = read_fixture(
        dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above,
        np.ones((3, 1, 1), dtype=bool),
    )
    assert present and not clean
    assert any("candidate active-domain shape" in message for message in failures)

    (present, clean, _), failures = read_fixture(
        dataset, base_interface, base_dp, base_mass, base_dry, surfaces, above,
        candidate.astype(np.int32),
    )
    assert present and not clean
    assert any("candidate active-domain shape and boolean type" in message for message in failures)

    mismatch = make_dataset(requested_surface=100010.0, candidate_surface=100011.0)
    (present, clean, _), failures = read_fixture(
        *mismatch[:-1], mismatch[-1]
    )
    assert present and not clean
    assert any("requested pressure rounds to stored candidate" in message for message in failures)

    raw_request_mismatch = make_dataset(
        background_surface=99990.0,
        candidate_surface=100000.0,
        requested_surface=99999.999,
    )
    (present, clean, _), failures = read_fixture(
        *raw_request_mismatch[:-1], raw_request_mismatch[-1]
    )
    assert present and not clean
    assert any(
        "requested and stored pressure domain classification" in message
        for message in failures
    )


if __name__ == "__main__":
    for test in (
        test_nontransition_positive_request_keeps_domain_and_rebuilds_interfaces,
        test_transition_one_center_uses_candidate_mask_and_pressure_crossing,
        test_same_domain_terrain_exclusion_is_preserved,
        test_crossing_without_candidate_mask_is_rejected,
        test_transition_rejects_invalid_masks_and_requests,
        test_transition_rejects_shape_type_and_raw_stored_request_mismatch,
    ):
        test()
    print("PASS test_transition_geometry_reference")
