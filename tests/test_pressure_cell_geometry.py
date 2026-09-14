"""Bounded tests for the pressure-cell geometry reference helper."""

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import (  # noqa: E402
    pressure_cell_geometry,
)


GRAVITY = 9.80665
PRESSURE_CENTERS = np.array([100000.0, 95000.0, 90000.0])
TOP_INTERFACE = 87500.0


def test_analytic_centers_and_column_mass_closure() -> None:
    surface_pressure = np.array([[99999.125, 100000.125]])
    area = np.array([[2.5, 3.75]])
    above = np.array(
        [
            [[False, True]],
            [[True, True]],
            [[True, True]],
        ],
        dtype=bool,
    )

    interfaces, pressure_mass = pressure_cell_geometry(
        PRESSURE_CENTERS, surface_pressure, above, area
    )

    expected_interfaces = np.array(
        [
            [[99999.125, 100000.125]],
            [[99999.125, 97500.0]],
            [[92500.0, 92500.0]],
            [[TOP_INTERFACE, TOP_INTERFACE]],
        ]
    )
    expected_dp = np.array(
        [
            [[0.0, 2500.125]],
            [[7499.125, 5000.0]],
            [[5000.0, 5000.0]],
        ]
    )
    expected_mass = area[None, ...] * expected_dp / GRAVITY

    np.testing.assert_array_equal(interfaces, expected_interfaces)
    np.testing.assert_allclose(pressure_mass, expected_mass, rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(
        pressure_mass.sum(axis=0),
        area * (surface_pressure - TOP_INTERFACE) / GRAVITY,
        rtol=0.0,
        atol=1.0e-12,
    )


def test_one_level_terrain_clip_is_allowed() -> None:
    surface_pressure = np.array([[100000.125]])
    area = np.array([[2.5]])
    # The pressure-domain first center is level 0.  Terrain may clip that
    # center, leaving a contiguous active suffix beginning one level lower.
    above = np.array([[[False]], [[True]], [[True]]], dtype=bool)

    interfaces, pressure_mass = pressure_cell_geometry(
        PRESSURE_CENTERS, surface_pressure, above, area
    )

    expected_interfaces = np.array(
        [
            [[100000.125]],
            [[100000.125]],
            [[92500.0]],
            [[TOP_INTERFACE]],
        ]
    )
    expected_dp = np.array([[[0.0]], [[7500.125]], [[5000.0]]])
    np.testing.assert_array_equal(interfaces, expected_interfaces)
    np.testing.assert_allclose(
        pressure_mass, area[None, ...] * expected_dp / GRAVITY,
        rtol=0.0,
        atol=1.0e-12,
    )


def invalid_pressure_cell_geometry_cases() -> list[
    tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
]:
    return [
        (
            "empty domain",
            PRESSURE_CENTERS,
            np.array([[100000.125]]),
            np.zeros((3, 1, 1), dtype=bool),
            np.ones((1, 1)),
        ),
        (
            "center above surface",
            PRESSURE_CENTERS,
            np.array([[99999.125]]),
            np.ones((3, 1, 1), dtype=bool),
            np.ones((1, 1)),
        ),
        (
            "hole in domain",
            PRESSURE_CENTERS,
            np.array([[100000.125]]),
            np.array([[[True]], [[False]], [[True]]], dtype=bool),
            np.ones((1, 1)),
        ),
        (
            "terrain clip exceeds one center",
            PRESSURE_CENTERS,
            np.array([[100000.125]]),
            np.array([[[False]], [[False]], [[True]]], dtype=bool),
            np.ones((1, 1)),
        ),
        (
            "negative area",
            PRESSURE_CENTERS,
            np.array([[100000.125]]),
            np.ones((3, 1, 1), dtype=bool),
            np.array([[-1.0]]),
        ),
        (
            "non-positive top interface",
            np.array([120000.0, 100.0]),
            np.array([[120000.0]]),
            np.ones((2, 1, 1), dtype=bool),
            np.ones((1, 1)),
        ),
    ]


def test_invalid_pressure_cell_geometry_is_rejected() -> None:
    for label, pressure, surface_pressure, above, area in (
        invalid_pressure_cell_geometry_cases()
    ):
        try:
            pressure_cell_geometry(pressure, surface_pressure, above, area)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid pressure geometry: {label}")


def test_masked_above_domain_is_rejected() -> None:
    above = np.ma.array(
        np.ones((3, 1, 1), dtype=bool),
        mask=np.array([[[False]], [[True]], [[False]]]),
    )

    try:
        pressure_cell_geometry(
            PRESSURE_CENTERS,
            np.array([[100000.125]]),
            above,
            np.ones((1, 1)),
        )
    except ValueError:
        return
    raise AssertionError("accepted masked pressure geometry domain")


def main() -> None:
    test_analytic_centers_and_column_mass_closure()
    test_one_level_terrain_clip_is_allowed()
    test_invalid_pressure_cell_geometry_is_rejected()
    test_masked_above_domain_is_rejected()


if __name__ == "__main__":
    main()
