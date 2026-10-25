from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr102_native_uv_smoother import solve_smooth_increment  # noqa: E402


def projection(matrix, raw):
    return raw - matrix.T @ np.linalg.solve(matrix @ matrix.T, matrix @ raw)


def test_smoother_satisfies_independent_active_kkt_system():
    # The first two rows are deliberately dependent to exercise rank reduction.
    divergence = np.array([[1.0, -1.0, 1.0], [-1.0, 1.0, -1.0]])
    roughness = np.array([[1.0, -1.0, 0.0], [0.0, 1.0, -1.0]])
    raw = np.array([11.0, 9.0, 1.0])
    center = projection(divergence[:1], raw)
    radius = np.linalg.norm(raw - center)

    result = solve_smooth_increment(
        csr_matrix(divergence), csr_matrix(roughness), raw, center,
        radius=radius,
        tolerance=1e-10,
    )

    x = result.increment
    # Independent KKT reconstruction for min ||Gx||^2 on the equality plane
    # and trust sphere. The reported multiplier uses the half-gradient form.
    q = roughness.T @ roughness
    grad = q @ x + result.multiplier * (x - center)
    nu = np.linalg.lstsq(divergence.T, -grad, rcond=None)[0]
    assert np.linalg.norm(grad + divergence.T @ nu) < 1e-8
    assert np.linalg.norm(divergence @ x) < 1e-9
    assert abs(np.linalg.norm(x - center) - radius) < 1e-8
    assert np.linalg.norm(x) > 0
    assert np.linalg.norm(roughness @ x) < np.linalg.norm(roughness @ center)
    assert result.stationarity_residual < 1e-8
    assert result.stationarity_residual_scaled < 1e-9


def test_rejects_trust_region_that_can_reach_zero():
    divergence = csr_matrix([[1.0, -1.0], [-1.0, 1.0]])
    roughness = csr_matrix([[1.0, -1.0]])
    raw = np.array([1.1, -0.9])
    center = projection(divergence.toarray()[:1], raw)
    with pytest.raises(ValueError, match="exclude the zero"):
        solve_smooth_increment(
            divergence, roughness, raw, center, radius=np.linalg.norm(raw-center)
        )


def test_rejects_infeasible_center_and_radius_beyond_pr99_adjustment():
    divergence = csr_matrix([[1.0, -1.0], [-1.0, 1.0]])
    roughness = csr_matrix([[1.0, -1.0]])
    raw = np.array([2.0, -1.0])
    center = projection(divergence.toarray()[:1], raw)
    with pytest.raises(ValueError, match="fixed-carrier"):
        solve_smooth_increment(divergence, roughness, raw, raw, radius=0.0)
    with pytest.raises(ValueError, match="nearest Euclidean projection"):
        solve_smooth_increment(
            divergence, roughness, raw, np.array([1.5, 1.5]), radius=0.5
        )
    with pytest.raises(ValueError, match="no larger than the PR99 adjustment"):
        solve_smooth_increment(
            divergence, roughness, raw, center,
            radius=1.01 * np.linalg.norm(raw-center),
        )
