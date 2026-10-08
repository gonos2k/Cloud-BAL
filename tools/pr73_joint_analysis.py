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


def _inverse(matrix: list[list[float]], name: str) -> list[list[float]]:
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError(f"{name} must be square")
    for i in range(n):
        for j in range(n):
            if abs(matrix[i][j] - matrix[j][i]) > 64.0 * sys.float_info.epsilon * max(
                abs(matrix[i][j]), abs(matrix[j][i]), sys.float_info.min
            ):
                raise ValueError(f"{name} must be symmetric")
    # Cholesky makes positive definiteness an explicit input requirement.
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
    columns = [_solve(matrix, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[columns[j][i] for j in range(n)] for i in range(n)]


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


def _independent_constraints(rows: list[list[float]], targets: list[float]) -> tuple[list[list[float]], list[float]]:
    """Drop consistent dependent rows and reject inconsistent equalities."""
    if not rows:
        return [], []
    augmented = [row[:] + [target] for row, target in zip(rows, targets)]
    row_count = len(augmented)
    variable_count = len(rows[0])
    tolerance = 128.0 * sys.float_info.epsilon
    pivot_row = 0
    pivot_rows: list[int] = []
    for column in range(variable_count):
        selected = max(range(pivot_row, row_count),
                       key=lambda index: abs(augmented[index][column]),
                       default=pivot_row)
        if pivot_row == row_count or abs(augmented[selected][column]) <= tolerance:
            continue
        augmented[pivot_row], augmented[selected] = augmented[selected], augmented[pivot_row]
        divisor = augmented[pivot_row][column]
        augmented[pivot_row] = [value / divisor for value in augmented[pivot_row]]
        for index in range(row_count):
            if index == pivot_row:
                continue
            factor = augmented[index][column]
            if factor:
                augmented[index] = [left - factor * right
                                    for left, right in zip(augmented[index], augmented[pivot_row])]
        pivot_rows.append(pivot_row)
        pivot_row += 1
        if pivot_row == row_count:
            break
    target_scale = max(1.0, *(abs(target) for target in targets))
    for row in augmented[pivot_row:]:
        if max(abs(value) for value in row[:variable_count]) <= tolerance and \
                abs(row[-1]) > tolerance * target_scale:
            raise ValueError("declared linear constraints are inconsistent")
    return ([augmented[index][:variable_count] for index in pivot_rows],
            [augmented[index][-1] for index in pivot_rows])


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
        C.append(coefficients)
        d.append(rhs - _dot(coefficients, known))

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

    Binv = _inverse(B, "B")
    Rinv = _inverse(R, "R")
    Ht = _transpose(H)
    Q = _add(Binv, _multiply(_multiply(Ht, Rinv), H))
    background_with_process = [background[i] + known[i] for i in range(n)]
    innovation = [y[i] - value for i, value in enumerate(_matvec(H, background_with_process))]
    qrhs = _matvec(_multiply(Ht, Rinv), innovation)
    # Scale the mixed-unit control vector by its prior standard deviation.
    control_scale = [math.sqrt(B[i][i]) for i in range(n)]
    Qscaled = [[Q[i][j] * control_scale[i] * control_scale[j] for j in range(n)]
               for i in range(n)]
    rhs_scaled = [qrhs[i] * control_scale[i] for i in range(n)]
    Cscaled = [[row[i] * control_scale[i] for i in range(n)] for row in C]
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
    best: tuple[float, list[float]] | None = None
    for face in itertools.product(*options):
        rows = [row[:] for row in Cscaled]
        rhs = dscaled[:]
        for i, side in enumerate(face):
            if side:
                lower, upper = bound_map[i]
                row = [0.0] * n
                row[i] = 1.0
                rows.append(row)
                rhs.append(((lower if side == -1 else upper) - background[i] - known[i]) /
                           control_scale[i])
        try:
            rows, rhs = _independent_constraints(rows, rhs)
        except ValueError:
            continue
        k = len(rows)
        kkt = [[0.0] * (n + k) for _ in range(n + k)]
        target = rhs_scaled + rhs
        for i in range(n):
            for j in range(n):
                kkt[i][j] = Qscaled[i][j]
            for j in range(k):
                kkt[i][n + j] = rows[j][i]
                kkt[n + j][i] = rows[j][i]
        try:
            solution = _solve(kkt, target)
        except ValueError:
            continue
        delta = [control_scale[i] * solution[i] for i in range(n)]
        state = [background[i] + known[i] + delta[i] for i in range(n)]
        if any(abs(_dot(row, delta) - target_value) > 64.0 * sys.float_info.epsilon *
               (abs(target_value) + sum(abs(a * b) for a, b in zip(row, delta)))
               for row, target_value in zip(C, d)):
            continue
        if any((bound_map[i][0] is not None and state[i] < bound_map[i][0]) or
               (bound_map[i][1] is not None and state[i] > bound_map[i][1])
               for i in bound_map):
            continue
        cost = 0.5 * _quadratic(Binv, delta) + 0.5 * _quadratic(
            Rinv, [value - target_value for value, target_value in zip(_matvec(H, state), y)])
        if best is None or cost < best[0]:
            best = (cost, delta)
    if best is None:
        raise ValueError("declared linear constraints and state bounds are infeasible")

    analysis = best[1]
    candidate = [background[i] + known[i] + analysis[i] for i in range(n)]
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
        print(json.dumps({"status": "INVALID_TRIAL", "error": str(error)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
