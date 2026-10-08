#!/usr/bin/env python3
"""Solve a small declared linear analysis trial with explicit process accounting.

This is an algorithm fixture, not a Cloud-BAL physical candidate evaluator.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any


COMPONENT_INDEX = {
    "dry_mass_metric": 1, "vapor": 2, "cloud_water": 3, "cloud_ice": 4,
    "rain": 5, "snow": 6, "graupel": 7, "enthalpy": 8,
}
SPECIES_CP = (1846.4, 4190.0, 2106.0, 4190.0, 2106.0, 2106.0)
SPECIES_H0 = (2.50e6, 0.0, -3.50e5, 0.0, -3.50e5, -3.50e5)
DRY_CP = 1004.5
REFERENCE_TEMPERATURE = 273.15


def _matrix(value: Any, name: str, rows: int | None = None,
            columns: int | None = None) -> list[list[float]]:
    if not isinstance(value, list) or not value or any(not isinstance(row, list) for row in value):
        raise ValueError(f"{name} must be a nonempty matrix")
    result = []
    width = len(value[0])
    if width == 0 or any(len(row) != width for row in value):
        raise ValueError(f"{name} must be rectangular")
    if rows is not None and len(value) != rows:
        raise ValueError(f"{name} has the wrong row count")
    if columns is not None and width != columns:
        raise ValueError(f"{name} has the wrong column count")
    for row in value:
        converted = [_number(item, name) for item in row]
        result.append(converted)
    return result


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} values must be numbers")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} values must be finite")
    return result


def _vector(value: Any, name: str, length: int | None = None) -> list[float]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        raise ValueError(f"{name} must be a vector of length {length or 'n'}")
    return [_number(item, name) for item in value]


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(rhs)
    if len(matrix) != n or any(len(row) != n for row in matrix):
        raise ValueError("internal linear system is not square")
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    scale = max((abs(item) for row in matrix for item in row), default=0.0)
    if scale == 0.0:
        raise ValueError("singular objective or constraint system")
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1.0e-13 * scale:
            raise ValueError("singular objective or dependent constraints")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [item / divisor for item in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [a - factor * b for a, b in zip(augmented[row], augmented[column])]
    return [augmented[i][-1] for i in range(n)]


def _cholesky(matrix: list[list[float]], name: str) -> list[list[float]]:
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError(f"{name} must be square")
    for i in range(n):
        for j in range(n):
            if abs(matrix[i][j] - matrix[j][i]) > 64.0 * sys.float_info.epsilon * max(
                abs(matrix[i][j]), abs(matrix[j][i]), sys.float_info.min
            ):
                raise ValueError(f"{name} must be symmetric")
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = matrix[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if value <= 0.0:
                    raise ValueError(f"{name} must be positive definite")
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = value / lower[j][j]
    return lower


def _forward_solve(lower: list[list[float]], rhs: list[float]) -> list[float]:
    result = []
    for i, row in enumerate(lower):
        result.append((rhs[i] - _dot(row[:i], result)) / row[i])
    return result


def _backward_solve(lower: list[list[float]], rhs: list[float]) -> list[float]:
    result = [0.0] * len(rhs)
    for i in range(len(rhs) - 1, -1, -1):
        result[i] = (rhs[i] - sum(lower[j][i] * result[j]
                                  for j in range(i + 1, len(rhs)))) / lower[i][i]
    return result


def _cholesky_solve(lower: list[list[float]], rhs: list[float]) -> list[float]:
    return _backward_solve(lower, _forward_solve(lower, rhs))


def _factor_covariance(matrix: list[list[float]], name: str) -> tuple[list[float], list[list[float]], list[list[float]]]:
    """Normalize covariance units, factor it, and form precision by factor solves."""
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError(f"{name} must be square")
    if any(matrix[i][i] <= 0.0 for i in range(n)):
        raise ValueError(f"{name} must be positive definite")
    scales = [math.sqrt(matrix[i][i]) for i in range(n)]
    normalized = [[matrix[i][j] / scales[i] / scales[j] for j in range(n)]
                  for i in range(n)]
    if any(not math.isfinite(value) for row in normalized for value in row):
        raise ValueError(f"NUMERICAL_FAILURE: {name} normalization overflowed")
    lower = _cholesky(normalized, name)
    columns = [_cholesky_solve(lower, [1.0 if i == j else 0.0 for i in range(n)])
               for j in range(n)]
    precision = [[columns[j][i] for j in range(n)] for i in range(n)]
    if any(not math.isfinite(value) for row in precision for value in row):
        raise ValueError(f"NUMERICAL_FAILURE: {name} factor solve overflowed")
    return scales, lower, precision


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [_dot(row, vector) for row in matrix]


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [list(column) for column in zip(*matrix)]


def _add(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[a + b for a, b in zip(row_a, row_b)] for row_a, row_b in zip(left, right)]


def _multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    right_t = _transpose(right)
    return [[_dot(row, column) for column in right_t] for row in left]


def _quadratic(matrix: list[list[float]], vector: list[float]) -> float:
    return _dot(vector, _matvec(matrix, vector))


def _independent_constraint_indices(rows: list[list[float]], targets: list[float]) -> list[int]:
    """Select original independent rows, rejecting inconsistent dependencies."""
    if not rows:
        return []
    tolerance = 128.0 * sys.float_info.epsilon
    chosen: list[int] = []
    for index, (row, target) in enumerate(zip(rows, targets)):
        trial_rows = [rows[item] for item in chosen] + [row]
        trial_targets = [targets[item] for item in chosen] + [target]
        augmented = [item[:] + [value] for item, value in zip(trial_rows, trial_targets)]
        row_count = len(augmented)
        variable_count = len(row)
        pivot_row = 0
        rank = 0
        for column in range(variable_count):
            selected = max(range(pivot_row, row_count),
                           key=lambda item: abs(augmented[item][column]), default=pivot_row)
            if pivot_row == row_count or abs(augmented[selected][column]) <= tolerance:
                continue
            augmented[pivot_row], augmented[selected] = augmented[selected], augmented[pivot_row]
            divisor = augmented[pivot_row][column]
            augmented[pivot_row] = [value / divisor for value in augmented[pivot_row]]
            for item in range(row_count):
                if item != pivot_row:
                    factor = augmented[item][column]
                    if factor:
                        augmented[item] = [left - factor * right
                                           for left, right in zip(augmented[item], augmented[pivot_row])]
            pivot_row += 1
            rank += 1
            if pivot_row == row_count:
                break
        target_scale = max(1.0, *(abs(value) for value in trial_targets))
        for residual in augmented[rank:]:
            if max((abs(value) for value in residual[:variable_count]), default=0.0) <= tolerance and \
                    abs(residual[-1]) > tolerance * target_scale:
                raise ValueError("declared linear constraints are inconsistent")
        if rank > len(chosen):
            chosen.append(index)
    return chosen


def _independent_constraints(rows: list[list[float]], targets: list[float]) -> tuple[list[list[float]], list[float]]:
    indices = _independent_constraint_indices(rows, targets)
    return [rows[index] for index in indices], [targets[index] for index in indices]


def _float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def _float32_spacing(value: float) -> float:
    value = abs(_float32(value))
    if value == 0.0:
        return 2.0 ** -149
    return 2.0 ** (math.floor(math.log2(value)) - 23)


def _specific_enthalpy(temperature: float, species: list[float]) -> float:
    return ((DRY_CP + _dot(list(SPECIES_CP), species)) *
            (temperature - REFERENCE_TEMPERATURE) + _dot(list(SPECIES_H0), species))


def _physical_contract_adapter(declaration: dict[str, Any], background: list[float],
                              candidate: list[float], analysis: list[float]) -> tuple[list[float], list[float]]:
    reference = declaration.get("physical_reference")
    fields = declaration["state_fields"]
    if not isinstance(reference, dict):
        raise ValueError("physical_reference is required for the Cloud-BAL fixture adapter")
    for name in ("phase", "external_source", "physical_boundary"):
        if any(value != 0.0 for value in declaration["process_increments"][name]):
            raise ValueError("manufactured Cloud-BAL contract adapter requires separate process increments to be zero")
    pressure_mass = _number(reference.get("pressure_mass_measure_kg"),
                            "physical_reference.pressure_mass_measure_kg")
    if pressure_mass <= 0.0:
        raise ValueError("physical pressure mass measure must be positive")
    q_names = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
    before_species = [background[fields.index(name)] if name in fields else 0.0 for name in q_names]
    after_species = [candidate[fields.index(name)] if name in fields else 0.0 for name in q_names]
    before_species = [_float32(value) for value in before_species]
    after_species = [_float32(value) for value in after_species]
    before_t = _float32(background[fields.index("temperature")])
    after_t = _float32(candidate[fields.index("temperature")])
    before_mass = pressure_mass / (1.0 + sum(before_species))
    after_mass = pressure_mass / (1.0 + sum(after_species))
    before = [before_mass] + [before_mass * value for value in before_species] + [
        before_mass * _specific_enthalpy(before_t, before_species)
    ]
    after = [after_mass] + [after_mass * value for value in after_species] + [
        after_mass * _specific_enthalpy(after_t, after_species)
    ]
    estimated = [after[i] - before[i] for i in range(8)]
    # Dry-mass changes are constrained by the canonical pressure/water state,
    # never assigned to the analysis term. Its float32 reconciliation is covered
    # by the same predeclared storage-roundoff tolerance as the physical contract.
    estimated[0] = 0.0
    species_ulp = [
        _float32_spacing(before_species[i]) + _float32_spacing(after_species[i])
        for i in range(6)
    ]
    tolerance = [0.0] * 8
    tolerance[0] = 2.0 * pressure_mass * sum(species_ulp)
    for i in range(6):
        tolerance[i + 1] = 2.0 * max(before_mass, after_mass) * species_ulp[i]
    capacity = DRY_CP + _dot(list(SPECIES_CP), after_species)
    enthalpy_roundoff = max(before_mass, after_mass) * (
        capacity * _float32_spacing(after_t)
        + sum(abs(SPECIES_H0[i] + SPECIES_CP[i] * (before_t - REFERENCE_TEMPERATURE)) *
              species_ulp[i] for i in range(6))
        + sum(SPECIES_CP[i] * species_ulp[i] for i in range(6)) *
          _float32_spacing(after_t)
    )
    tolerance[7] = 4.0 * enthalpy_roundoff
    return estimated, tolerance


def _validate_declaration(data: Any) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("expected a schema_version 1 JSON object")
    if data.get("evidence_class") != "MANUFACTURED_ALGORITHM_FIXTURE":
        raise ValueError("evidence_class must be MANUFACTURED_ALGORITHM_FIXTURE")
    fields = data.get("state_fields")
    if not isinstance(fields, list) or not fields or any(not isinstance(item, str) or not item for item in fields):
        raise ValueError("state_fields must be nonempty strings")
    if len(set(fields)) != len(fields) or len(fields) > 8:
        raise ValueError("state_fields must be unique and limited to eight variables")
    return fields, data


def evaluate(data: Any) -> dict[str, Any]:
    fields, declaration = _validate_declaration(data)
    n = len(fields)
    background = _vector(declaration.get("background_state"), "background_state", n)
    B = _matrix(declaration.get("B"), "B", n, n)
    observation = declaration.get("observation")
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    H = _matrix(observation.get("H"), "observation.H", columns=n)
    m = len(H)
    y = _vector(observation.get("value"), "observation.value", m)
    R = _matrix(observation.get("R"), "observation.R", m, m)
    authorities = declaration.get("authorities")
    if not isinstance(authorities, dict):
        raise ValueError("authorities must declare H, B, R, and prior/change provenance")
    for name in ("H", "B", "R", "background_prior", "analysis_change"):
        value = authorities.get(name)
        if not isinstance(value, dict) or not isinstance(value.get("evidence_id"), str) or not value["evidence_id"].strip():
            raise ValueError(f"authorities.{name}.evidence_id must be a nonempty string")

    process = declaration.get("process_increments")
    if not isinstance(process, dict):
        raise ValueError("process_increments must separate phase, source, and boundary vectors")
    phase = _vector(process.get("phase"), "process_increments.phase", n)
    source = _vector(process.get("external_source"), "process_increments.external_source", n)
    boundary = _vector(process.get("physical_boundary"), "process_increments.physical_boundary", n)
    known = [phase[i] + source[i] + boundary[i] for i in range(n)]
    if any(not math.isfinite(value) for value in known):
        raise ValueError("NUMERICAL_FAILURE: process increments overflowed during accumulation")
    background_with_process = [background[i] + known[i] for i in range(n)]
    if any(not math.isfinite(value) for value in background_with_process):
        raise ValueError("NUMERICAL_FAILURE: background plus process increments overflowed")
    prior_delta = [0.0] * n

    constraints = declaration.get("constraints", [])
    if not isinstance(constraints, list):
        raise ValueError("constraints must be a list")
    C: list[list[float]] = []
    d: list[float] = []
    for row in constraints:
        if not isinstance(row, dict) or not isinstance(row.get("evidence_id"), str) or not row["evidence_id"].strip():
            raise ValueError("each constraint needs an independent evidence_id")
        coefficients = _vector(row.get("coefficients"), "constraint.coefficients", n)
        rhs = _number(row.get("rhs"), "constraint.rhs")
        adjusted_rhs = rhs - _dot(coefficients, known)
        if not math.isfinite(adjusted_rhs):
            raise ValueError("NUMERICAL_FAILURE: adjusted equality target overflowed")
        C.append(coefficients)
        d.append(adjusted_rhs)

    bounds = declaration.get("state_bounds", [])
    if not isinstance(bounds, list):
        raise ValueError("state_bounds must be a list")
    bound_map: dict[int, tuple[float | None, float | None]] = {}
    for row in bounds:
        if not isinstance(row, dict):
            raise ValueError("each state bound must be an object")
        field = row.get("field")
        if field not in fields:
            raise ValueError(f"state bound references unknown field {field!r}")
        index = fields.index(field)
        if index in bound_map:
            raise ValueError(f"duplicate state bound for {field}")
        lower = None if row.get("lower") is None else _number(row["lower"], f"{field}.lower")
        upper = None if row.get("upper") is None else _number(row["upper"], f"{field}.upper")
        if lower is None and upper is None or (lower is not None and upper is not None and lower > upper):
            raise ValueError(f"invalid state bound for {field}")
        bound_map[index] = (lower, upper)

    for row, target in zip(C, d):
        minimum = 0.0
        maximum = 0.0
        for i, coefficient in enumerate(row):
            if coefficient == 0.0:
                continue
            lower, upper = bound_map.get(i, (None, None))
            delta_lower = -math.inf
            if lower is not None:
                delta_lower = lower - background_with_process[i]
                if not math.isfinite(delta_lower):
                    raise ValueError("NUMERICAL_FAILURE: box feasibility range overflowed")
                delta_lower = math.nextafter(delta_lower, -math.inf)
            delta_upper = math.inf
            if upper is not None:
                delta_upper = upper - background_with_process[i]
                if not math.isfinite(delta_upper):
                    raise ValueError("NUMERICAL_FAILURE: box feasibility range overflowed")
                delta_upper = math.nextafter(delta_upper, math.inf)
            low_delta = delta_lower if coefficient >= 0.0 else delta_upper
            high_delta = delta_upper if coefficient >= 0.0 else delta_lower
            low_term = coefficient * low_delta
            high_term = coefficient * high_delta
            if math.isnan(low_term) or math.isnan(high_term):
                raise ValueError("NUMERICAL_FAILURE: box feasibility range is indeterminate")
            if (math.isfinite(low_delta) and not math.isfinite(low_term)) or \
                    (math.isfinite(high_delta) and not math.isfinite(high_term)):
                raise ValueError("NUMERICAL_FAILURE: box feasibility range overflowed")
            if math.isfinite(low_term):
                low_term = math.nextafter(low_term, -math.inf)
            if math.isfinite(high_term):
                high_term = math.nextafter(high_term, math.inf)
            next_minimum = minimum + low_term
            next_maximum = maximum + high_term
            if math.isnan(next_minimum) or math.isnan(next_maximum):
                raise ValueError("NUMERICAL_FAILURE: box feasibility range is indeterminate")
            if (math.isfinite(minimum) and math.isfinite(low_term) and not math.isfinite(next_minimum)) or \
                    (math.isfinite(maximum) and math.isfinite(high_term) and not math.isfinite(next_maximum)):
                raise ValueError("NUMERICAL_FAILURE: box feasibility range overflowed")
            if math.isfinite(next_minimum):
                next_minimum = math.nextafter(next_minimum, -math.inf)
            if math.isfinite(next_maximum):
                next_maximum = math.nextafter(next_maximum, math.inf)
            minimum, maximum = next_minimum, next_maximum
        if target < minimum or target > maximum:
            raise ValueError("INFEASIBLE: equality target is infeasible under its declared box range")

    state_scale, _, Binv = _factor_covariance(B, "B")
    observation_scale, _, Rinv = _factor_covariance(R, "R")
    Hscaled = [[H[i][j] * state_scale[j] / observation_scale[i] for j in range(n)]
               for i in range(m)]
    innovation = [(y[i] - value) / observation_scale[i]
                  for i, value in enumerate(_matvec(H, background_with_process))]
    HtRinv = _multiply(_transpose(Hscaled), Rinv)
    Qscaled = _add(Binv, _multiply(HtRinv, Hscaled))
    rhs_scaled = _matvec(HtRinv, innovation)
    Cscaled = [[row[i] * state_scale[i] for i in range(n)] for row in C]
    if any(not math.isfinite(value) for matrix in (Hscaled, Qscaled, Cscaled)
           for row in matrix for value in row) or any(
               not math.isfinite(value) for vector in (innovation, rhs_scaled)
               for value in vector):
        raise ValueError("NUMERICAL_FAILURE: covariance normalization or objective assembly overflowed")
    normalized_constraints = []
    normalized_rhs = []
    for row, target in zip(Cscaled, d):
        scale = max((abs(value) for value in row), default=0.0)
        if scale == 0.0:
            if target != 0.0:
                raise ValueError("declared linear constraints and state bounds are infeasible")
            continue
        normalized_constraints.append([value / scale for value in row])
        normalized_rhs.append(target / scale)
    Cscaled, dscaled = normalized_constraints, normalized_rhs
    Cscaled, dscaled = _independent_constraints(Cscaled, dscaled)

    # Enumerate the faces of the declared box. For this deliberately small
    # fixture, this is simple and deterministic; it is not an operational solver.
    options = []
    for index in range(n):
        lower, upper = bound_map.get(index, (None, None))
        choices = [0]
        if lower is not None:
            choices.append(-1)
        if upper is not None and upper != lower:
            choices.append(1)
        options.append(choices)
    best: tuple[float, list[float], list[float], tuple[int, ...], list[float], list[list[float]]] | None = None
    solved_faces = 0
    for face in itertools.product(*options):
        active = [i for i, side in enumerate(face) if side]
        free = [i for i in range(n) if not face[i]]
        fixed_z = [0.0] * n
        for i in active:
            lower, upper = bound_map[i]
            bound = lower if face[i] == -1 else upper
            fixed_z[i] = (bound - background_with_process[i]) / state_scale[i]
        reduced_rhs = [dscaled[k] - sum(Cscaled[k][i] * fixed_z[i] for i in active)
                       for k in range(len(Cscaled))]
        rows = [[row[i] for i in free] for row in Cscaled]
        try:
            basis_indices = _independent_constraint_indices(rows, reduced_rhs)
        except ValueError:
            continue
        basis_full = [Cscaled[index] for index in basis_indices]
        rows = [rows[index] for index in basis_indices]
        reduced_rhs = [reduced_rhs[index] for index in basis_indices]
        k = len(rows)
        if free:
            kkt = [[0.0] * (len(free) + k) for _ in range(len(free) + k)]
            target = [rhs_scaled[i] - sum(Qscaled[i][j] * fixed_z[j] for j in active)
                      for i in free] + reduced_rhs
            for a, i in enumerate(free):
                for b, j in enumerate(free):
                    kkt[a][b] = Qscaled[i][j]
                for b in range(k):
                    kkt[a][len(free) + b] = rows[b][a]
                    kkt[len(free) + b][a] = rows[b][a]
            try:
                solution = _solve(kkt, target)
            except ValueError:
                continue
            z = fixed_z[:]
            for a, i in enumerate(free):
                z[i] = solution[a]
            equality_multipliers = solution[len(free):]
        else:
            if any(abs(value) > 128.0 * sys.float_info.epsilon * max(1.0, abs(value))
                   for value in reduced_rhs):
                continue
            z = fixed_z[:]
            equality_multipliers = []
        solved_faces += 1
        delta = [state_scale[i] * z[i] for i in range(n)]
        state = background_with_process[:]
        for i in range(n):
            state[i] += delta[i]
        # Fixed coordinates are assigned from their declared bound after solving
        # the reduced system, preserving exact equality without a final clip.
        for i in active:
            lower, upper = bound_map[i]
            state[i] = lower if face[i] == -1 else upper
            delta[i] = state[i] - background_with_process[i]
            z[i] = delta[i] / state_scale[i]
        equality_error = max((abs(_dot(row, delta) - target_value) /
                              max(abs(target_value), sum(abs(a * b) for a, b in zip(row, delta)),
                                  sys.float_info.min)
                              for row, target_value in zip(C, d)), default=0.0)
        if equality_error > 4096.0 * sys.float_info.epsilon:
            continue
        if any((bound_map[i][0] is not None and state[i] < bound_map[i][0]) or
               (bound_map[i][1] is not None and state[i] > bound_map[i][1])
               for i in bound_map):
            continue
        residual_scaled = [(value - target_value) / observation_scale[i]
                           for i, (value, target_value) in enumerate(zip(_matvec(H, state), y))]
        cost = 0.5 * _quadratic(Binv, z) + 0.5 * _quadratic(Rinv, residual_scaled)
        if best is None or cost < best[0]:
            best = (cost, delta, z, tuple(face), equality_multipliers, basis_full)
    if best is None:
        raise ValueError("NUMERICAL_FAILURE: declared linear constraints and state bounds have no certified face")

    analysis = best[1]
    candidate = [background_with_process[i] + analysis[i] for i in range(n)]
    active = [i for i, side in enumerate(best[3]) if side]
    for i in active:
        lower, upper = bound_map[i]
        candidate[i] = lower if best[3][i] == -1 else upper
        analysis[i] = candidate[i] - background_with_process[i]
    z = [analysis[i] / state_scale[i] for i in range(n)]
    residual_scaled = [(value - target_value) / observation_scale[i]
                       for i, (value, target_value) in enumerate(zip(_matvec(H, candidate), y))]
    gradient = [value + term for value, term in zip(
        _matvec(Binv, z), _matvec(_multiply(_transpose(Hscaled), Rinv), residual_scaled))]
    lagrangian_gradient = gradient[:]
    for row, multiplier in zip(best[5], best[4]):
        for i in range(n):
            lagrangian_gradient[i] += row[i] * multiplier
    lower_duals = [0.0] * n
    upper_duals = [0.0] * n
    fixed_duals = [0.0] * n
    for i in active:
        if bound_map[i][0] == bound_map[i][1]:
            fixed_duals[i] = -lagrangian_gradient[i]
            lagrangian_gradient[i] = 0.0
            continue
        if best[3][i] == -1:
            lower_duals[i] = lagrangian_gradient[i]
        else:
            upper_duals[i] = -lagrangian_gradient[i]
        lagrangian_gradient[i] = 0.0
    equality_residuals = [abs(_dot(row, analysis) - target) /
                          max(abs(target), sum(abs(a * b) for a, b in zip(row, analysis)),
                              sys.float_info.min) for row, target in zip(C, d)]
    bound_violations = [max(0.0, lower - candidate[i]) if lower is not None else 0.0
                        for i, (lower, _) in bound_map.items()]
    bound_violations += [max(0.0, candidate[i] - upper) if upper is not None else 0.0
                         for i, (_, upper) in bound_map.items()]
    stationarity_scale = max((abs(value) + sum(abs(row[i] * multiplier)
                                                for row, multiplier in zip(best[5], best[4]))
                             for i, value in enumerate(gradient)), default=1.0)
    dual_scale = max(stationarity_scale, sys.float_info.min)
    dual_violation = max([0.0] + [max(0.0, -value) / dual_scale
                                  for value in lower_duals + upper_duals])
    complementarity = max([0.0] + [abs(lower_duals[i] * (candidate[i] - bound_map[i][0])) /
                                    dual_scale for i in active if bound_map[i][0] is not None] +
                          [abs(upper_duals[i] * (bound_map[i][1] - candidate[i])) /
                           dual_scale for i in active if bound_map[i][1] is not None])
    kkt_diagnostics = {
        "status": "PASS",
        "stationarity_coordinates": "normalized_control",
        "equality_coordinates": "original_state_increment",
        "primal_equality_residual": max(equality_residuals, default=0.0),
        "primal_bound_violation": max(bound_violations, default=0.0),
        "stationarity_residual": max((abs(value) for value in lagrangian_gradient), default=0.0) /
        dual_scale,
        "dual_sign_violation": dual_violation,
        "complementarity_residual": complementarity,
        "active_bounds": [
            {"field": fields[i], "side": "fixed" if bound_map[i][0] == bound_map[i][1] else
             "lower" if best[3][i] == -1 else "upper",
             "multiplier": fixed_duals[i] if bound_map[i][0] == bound_map[i][1] else
             lower_duals[i] if best[3][i] == -1 else upper_duals[i]}
            for i in active
        ],
        "normalized_covariance_scales": {"state": state_scale, "observation": observation_scale},
        "face_solves": solved_faces,
    }
    if max(kkt_diagnostics[key] for key in (
            "primal_equality_residual", "primal_bound_violation", "stationarity_residual",
            "dual_sign_violation", "complementarity_residual")) > 4096.0 * sys.float_info.epsilon:
        kkt_diagnostics["status"] = "NUMERICAL_FAILURE"
        raise ValueError("NUMERICAL_FAILURE: normalized-coordinate KKT certificate did not pass")
    if any(not math.isfinite(value) for value in
           (best[0], *candidate, *analysis, *gradient, *lagrangian_gradient,
            *lower_duals, *upper_duals, *fixed_duals, *best[4],
            *(item["multiplier"] for item in kkt_diagnostics["active_bounds"]),
            kkt_diagnostics["primal_equality_residual"], kkt_diagnostics["stationarity_residual"],
            kkt_diagnostics["dual_sign_violation"], kkt_diagnostics["complementarity_residual"])):
        raise ValueError("NUMERICAL_FAILURE: nonfinite value in the original-coordinate KKT certificate")
    state_changes = [candidate[i] - background[i] for i in range(n)]
    # Preserve the names and units of the existing physical component contract.
    physical_components = {}
    for field in ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel"):
        if field not in fields:
            continue
        i = fields.index(field)
        physical_components[field] = {
            "component_index": COMPONENT_INDEX[field],
            "state_change_kg_per_kg": state_changes[i],
            "analysis_change_kg_per_kg": analysis[i],
            "phase_change_kg_per_kg": phase[i],
            "external_source_change_kg_per_kg": source[i],
            "physical_boundary_change_kg_per_kg": boundary[i],
            "physical_contract_status": "NOT_EVALUATED_BY_PYTHON_SOLVER",
        }
    result = {
        "status": "MANUFACTURED_ALGORITHM_TRIAL",
        "kkt_diagnostics": kkt_diagnostics,
        "evidence_class": declaration["evidence_class"],
        "scope": "linear H/B/R objective with declared equality and box constraints",
        "objective_value": best[0],
        "state_fields": fields,
        "background_state": background,
        "analysis_increment": analysis,
        "phase_increment": phase,
        "external_source_increment": source,
        "physical_boundary_increment": boundary,
        "candidate_state": candidate,
        "observation_operator": H,
        "observation_fit": _matvec(H, candidate),
        "physical_components": physical_components,
        "cloud_bal_component_contract": {
            "component_order": COMPONENT_INDEX,
            "status": "NOT_PIPELINE_GENERATED_CANDIDATE",
            "reason": "this estimator trial was not generated by run_cloud_bal_pipeline",
            "analysis_increment_retained_separately": True,
        },
        "scientific_approval": False,
    }
    if declaration.get("physical_reference") is not None:
        physical, tolerance = _physical_contract_adapter(declaration, background, candidate, analysis)
        result["physical_analysis_increment"] = physical
        result["physical_tolerance"] = tolerance
        result["cloud_bal_component_contract"] = {
            "component_order": COMPONENT_INDEX,
            "status": "READY_FOR_ENDPOINT_EVALUATION",
            "analysis_increment_retained_separately": True,
            "identity": authorities["analysis_change"]["evidence_id"],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("declaration", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--physical-control", type=Path)
    args = parser.parse_args()
    try:
        declaration = json.loads(args.declaration.read_text(encoding="utf-8"))
        result = evaluate(declaration)
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        control_rendered = None
        if args.physical_control:
            control_rendered = "\n".join((
                " ".join(format(value, ".17g") for value in result["background_state"]),
                " ".join(format(value, ".17g") for value in result["candidate_state"]),
                " ".join(format(value, ".17g") for value in result["physical_analysis_increment"]),
                " ".join(format(value, ".17g") for value in result["physical_tolerance"]),
            )) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name(args.output.name + ".tmp")
            temporary.write_text(rendered, encoding="utf-8")
            os.replace(temporary, args.output)
        if args.physical_control:
            args.physical_control.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.physical_control.with_name(args.physical_control.name + ".tmp")
            temporary.write_text(control_rendered, encoding="utf-8")
            os.replace(temporary, args.physical_control)
        print(rendered, end="")
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        message = str(error)
        status = "NUMERICAL_FAILURE" if message.startswith("NUMERICAL_FAILURE:") else \
            "INFEASIBLE" if "infeasible" in message.lower() or "inconsistent" in message.lower() else \
            "INVALID_TRIAL"
        print(json.dumps({"status": status, "error": message}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
