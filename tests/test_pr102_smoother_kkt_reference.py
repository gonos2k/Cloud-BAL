"""Independent small-grid SVD/eigenvalue oracle for the projected solver."""
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.linalg import null_space
from scipy.optimize import brentq
from scipy.sparse import csr_matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr102_native_uv_smoother import solve_smooth_increment


def weighted_incidence(ny, nx, random):
    pairs = [(j * nx + i, j * nx + i + 1)
             for j in range(ny) for i in range(nx - 1)]
    pairs += [(j * nx + i, (j + 1) * nx + i)
              for j in range(ny - 1) for i in range(nx)]
    matrix = np.zeros((ny * nx, len(pairs)))
    for face, (left, right) in enumerate(pairs):
        coefficient = random.uniform(0.5, 2.0)
        matrix[left, face], matrix[right, face] = coefficient, -coefficient
    return matrix


@pytest.mark.parametrize("case", range(12))
def test_native_incidence_solver_matches_independent_spectral_kkt(case):
    random = np.random.default_rng(10200 + case)
    ny, nx = ((2, 2), (2, 3), (3, 3))[case % 3]
    matrix = weighted_incidence(ny, nx, random)
    basis = null_space(matrix)
    center = basis @ random.normal(size=basis.shape[1])
    normal = matrix.T @ random.normal(size=matrix.shape[0])
    normal *= (0.15 + 0.02 * case) * np.linalg.norm(center) / np.linalg.norm(normal)
    raw = center + normal
    radius = np.linalg.norm(normal) * 0.999  # a caller's explicit storage reserve
    nfaces = matrix.shape[1]
    gradient = np.vstack((np.eye(nfaces), np.diff(np.eye(nfaces), axis=0)))
    gradient *= random.uniform(0.5, 1.5, size=gradient.shape[0])[:, None]

    # This reference eliminates the constraints using dense SVD only on these
    # small manufactured grids. It uses an eigenbasis and a scalar secular
    # equation, independently of the production projector and CG iterations.
    reduced = basis.T @ gradient.T @ gradient @ basis
    eigenvalues, eigenvectors = np.linalg.eigh(reduced)
    coordinates = eigenvectors.T @ basis.T @ center

    def reference(multiplier):
        return basis @ eigenvectors @ (multiplier * coordinates / (eigenvalues + multiplier))

    def secular(multiplier):
        return np.linalg.norm(reference(multiplier) - center) - radius

    high = 1.0
    while secular(high) > 0:
        high *= 2
    multiplier = brentq(secular, 0, high, xtol=1e-13, rtol=1e-13)
    expected = reference(multiplier)
    actual = solve_smooth_increment(csr_matrix(matrix), csr_matrix(gradient), raw,
                                    center, radius=radius, tolerance=1e-10)

    np.testing.assert_allclose(actual.increment, expected, rtol=3e-8, atol=1e-9)
    assert np.linalg.norm(matrix @ actual.increment) < 1e-9
    assert actual.displacement <= radius
    assert np.linalg.norm(gradient @ actual.increment) < np.linalg.norm(gradient @ center)
    assert np.linalg.norm(actual.increment) > 0
    assert actual.stationarity_residual_scaled < 1e-9
