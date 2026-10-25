#!/usr/bin/env python3
"""Solve a research-only smooth native wind increment trust-region problem.

This module contains the numerical core only. It does not read or write case
files, and intentionally cannot generate an operational or actual-case input.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csc_matrix, eye
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import LinearOperator, cg, factorized, lsmr


@dataclass(frozen=True)
class SmoothSolution:
    increment: np.ndarray
    multiplier: float
    displacement: float
    roughness_squared: float
    equality_residual: float
    stationarity_residual: float
    stationarity_residual_scaled: float


def _independent_rows(matrix: csc_matrix) -> csc_matrix:
    """Drop one dependent mass-cell balance per connected flux component."""
    if not matrix.shape[0]:
        return matrix[:0]
    counts = np.diff(matrix.tocsc().indptr)
    column_sums = np.asarray(matrix.sum(axis=0)).ravel()
    column_scales = np.asarray(abs(matrix).sum(axis=0)).ravel()
    if (np.any(counts != 2) or np.any(column_scales == 0)
            or np.any(np.abs(column_sums) > 64 * np.finfo(float).eps * column_scales)):
        raise ValueError("dry-flux operator must be oriented two-cell face incidence")
    adjacency = matrix @ matrix.T
    adjacency.setdiag(0)
    adjacency.eliminate_zeros()
    _, labels = connected_components(adjacency, directed=False)
    keep = np.ones(matrix.shape[0], dtype=bool)
    for component in np.unique(labels):
        keep[np.flatnonzero(labels == component)[0]] = False
    return matrix[keep].tocsc()


def solve_smooth_increment(
    divergence,
    roughness,
    raw_increment,
    projected_increment,
    *,
    radius: float,
    tolerance: float = 1e-9,
    max_iterations: int = 100,
) -> SmoothSolution:
    """Minimize ``||G b||²`` subject to ``A b=0`` and ``||b-bP||<=radius``.

    ``radius`` must be the precomputed ``||d-bP|| - storage_margin``. ``bP``
    must be the verified feasible nearest projection of raw increment ``d``.
    The trust-region multiplier is found by a bracketed dual root solve; it is
    not a fitted smoothing weight.
    """
    a = csc_matrix(divergence, dtype=np.float64)
    g = csc_matrix(roughness, dtype=np.float64)
    raw = np.asarray(raw_increment, dtype=np.float64)
    projected = np.asarray(projected_increment, dtype=np.float64)
    if (raw.ndim != 1 or projected.shape != raw.shape or a.shape[1] != len(raw)
            or g.shape[1] != len(raw) or not np.isfinite(raw).all()
            or not np.isfinite(projected).all() or not np.isfinite(a.data).all()
            or not np.isfinite(g.data).all() or tolerance <= 0 or max_iterations <= 0):
        raise ValueError("invalid native smoother inputs")
    computed_radius = float(np.linalg.norm(raw - projected))
    limit = float(radius)
    if not np.isfinite(limit) or limit < 0 or limit > computed_radius:
        raise ValueError("trust radius must be finite and no larger than the PR99 adjustment")
    if limit >= np.linalg.norm(projected):
        raise ValueError("trust radius does not exclude the zero increment")
    eq = _independent_rows(a)
    eq_scale = max(1.0, float(np.linalg.norm(a.data)) * max(1.0, np.linalg.norm(projected)))
    if np.linalg.norm(a @ projected) > tolerance * eq_scale:
        raise ValueError("projected center does not satisfy the fixed-carrier constraint")
    correction = raw - projected
    normal = lsmr(a.T, correction, atol=1e-13, btol=1e-13,
                   maxiter=max(100, 2 * a.shape[0]))[0]
    normal_residual = float(np.linalg.norm(a.T @ normal - correction))
    if normal_residual > tolerance * max(1.0, float(np.linalg.norm(correction))):
        raise ValueError("projected center is not the nearest Euclidean projection")
    if limit == 0:
        raise ValueError("zero trust radius leaves no spatially regularized candidate")

    hessian = (g.T @ g).tocsc()
    row_gram = (eq @ eq.T).tocsc()
    solve_row_gram = factorized(row_gram) if row_gram.shape[0] else None

    def project(vector):
        if solve_row_gram is None:
            return vector.copy()
        return vector - eq.T @ solve_row_gram(eq @ vector)

    center_roughness_gradient = np.asarray(hessian @ projected).ravel()
    rhs = -project(center_roughness_gradient)

    def solve_dual(multiplier: float):
        def apply(vector):
            tangent = project(vector)
            return project(hessian @ tangent) + multiplier * vector

        operator = LinearOperator((len(raw), len(raw)), matvec=apply, dtype=np.float64)
        correction, status = cg(operator, rhs, rtol=tolerance * 0.1, atol=0.0,
                                maxiter=max(100, 4 * len(raw)))
        if status != 0 or not np.isfinite(correction).all():
            raise ValueError(f"projected conjugate-gradient solve failed: {status}")
        candidate = projected + project(correction)
        return candidate

    # Find a dual bracket around the active trust constraint. The initial scale
    # only brackets the root; the accepted multiplier is determined by radius.
    low, high = 0.0, 1.0
    high_x = solve_dual(high)
    high_distance = float(np.linalg.norm(high_x - projected))
    while high_distance > limit:
        high *= 2.0
        if not np.isfinite(high):
            raise ValueError("could not bracket trust-region dual root")
        high_x = solve_dual(high)
        high_distance = float(np.linalg.norm(high_x - projected))

    low_x = solve_dual(max(np.finfo(float).tiny, high * 1e-12))
    low_distance = float(np.linalg.norm(low_x - projected))
    if low_distance <= limit:
        raise ValueError("roughness minimizer is interior or degenerate; active trust root unavailable")
    low = high * 1e-12
    for _ in range(max_iterations):
        middle = (low + high) / 2.0
        middle_x = solve_dual(middle)
        distance = float(np.linalg.norm(middle_x - projected))
        if distance <= limit:
            high = middle
            if abs(distance - limit) <= tolerance * max(1.0, limit):
                break
        else:
            low = middle
    else:
        raise ValueError("trust-region dual root did not converge")

    multiplier = high
    increment = solve_dual(multiplier)
    displacement = float(np.linalg.norm(increment - projected))
    residual = float(np.linalg.norm(a @ increment))
    gradient = np.asarray(hessian @ increment + multiplier * (increment - projected)).ravel()
    stationarity = float(np.linalg.norm(project(gradient)))
    stationarity_scale = max(
        1.0, float(np.linalg.norm(rhs)), multiplier * displacement
    )
    stationarity_scaled = stationarity / stationarity_scale
    if displacement > limit + tolerance * max(1.0, limit):
        raise ValueError("trust-region radius exceeded")
    if residual > tolerance * max(1.0, np.linalg.norm(a.data) * np.linalg.norm(increment)):
        raise ValueError("fixed-carrier constraint residual exceeded")
    if stationarity_scaled > max(10 * tolerance, 1e-10):
        raise ValueError("normalized projected KKT stationarity residual exceeded")
    return SmoothSolution(
        increment=increment,
        multiplier=float(multiplier),
        displacement=displacement,
        roughness_squared=float(np.linalg.norm(g @ increment) ** 2),
        equality_residual=residual,
        stationarity_residual=stationarity,
        stationarity_residual_scaled=stationarity_scaled,
    )
