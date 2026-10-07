#!/usr/bin/env python3
"""Replay the captured Shinhong cloud-water tridiagonal operator on QC and NC."""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path


TARGET = (172, 76)
FLOAT32_UNIT_ROUNDOFF = 2.0**-24
FLOAT32_MIN_NORMAL = 2.0**-126
FLOAT32_MAX = (2.0 - 2.0**-23) * 2.0**127


def gamma32(operations: int) -> float:
    product = operations * FLOAT32_UNIT_ROUNDOFF
    return product / (1.0 - product)


def f32(value: float) -> float:
    if not math.isfinite(value) or abs(value) > FLOAT32_MAX:
        raise ValueError("binary32 operation produced a non-finite or out-of-range value")
    try:
        rounded = struct.unpack("=f", struct.pack("=f", value))[0]
    except OverflowError as exc:
        raise ValueError("binary32 operation overflowed") from exc
    if not math.isfinite(rounded):
        raise ValueError("binary32 operation produced a non-finite value")
    return rounded


def require_finite(values: list[float], description: str) -> None:
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"non-finite {description}")


def require_binary32(values: list[float], description: str) -> None:
    require_finite(values, description)
    if any(abs(value) > FLOAT32_MAX for value in values):
        raise ValueError(f"out-of-binary32-range {description}")


def solve_f32(lower: list[float], diagonal: list[float], upper: list[float], rhs: list[float]) -> list[float]:
    """Mirror tridin_ysu's reciprocal-multiply Thomas operations in binary32."""
    if not rhs or any(len(values) != len(rhs) for values in (lower, diagonal, upper)):
        raise ValueError("Thomas solver arrays must have the same nonzero length")
    require_binary32(lower + diagonal + upper + rhs, "Thomas solver inputs")
    cprime = [f32(0.0)] * len(rhs)
    dprime = [f32(0.0)] * len(rhs)
    denom = f32(diagonal[0])
    if denom == 0.0:
        raise ValueError("zero matrix pivot")
    reciprocal = f32(1.0 / denom)
    cprime[0] = f32(reciprocal * upper[0])
    dprime[0] = f32(reciprocal * rhs[0])
    for k in range(1, len(rhs)):
        product = f32(lower[k] * cprime[k - 1])
        denom = f32(diagonal[k] - product)
        if denom == 0.0:
            raise ValueError("zero matrix pivot")
        reciprocal = f32(1.0 / denom)
        cprime[k] = f32(reciprocal * upper[k]) if k + 1 < len(rhs) else f32(0.0)
        product = f32(lower[k] * dprime[k - 1])
        residual = f32(rhs[k] - product)
        dprime[k] = f32(reciprocal * residual)
    result = [f32(0.0)] * len(rhs)
    result[-1] = dprime[-1]
    for k in range(len(rhs) - 2, -1, -1):
        result[k] = f32(dprime[k] - f32(cprime[k] * result[k + 1]))
    return result


def parse_operator(path: Path) -> tuple[dict[str, object], list[dict[str, float]]]:
    calls: list[dict[str, object]] = []
    active: dict[str, object] | None = None
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split(",")
        if not fields or not fields[0]:
            continue
        if fields[0] == "CALL":
            if active is not None:
                raise ValueError(f"nested operator call at line {lineno}")
            if len(fields) != 9:
                raise ValueError(f"malformed CALL at line {lineno}")
            i, j, kts, kte = map(int, fields[1:5])
            dt2, rdt = map(float, fields[5:7])
            kpbl = int(fields[7])
            pblflg = fields[8].strip().upper() == "T"
            if (i, j) != TARGET or dt2 <= 0.0 or rdt <= 0.0 or not pblflg:
                raise ValueError("unexpected selected column or inactive PBL call")
            require_binary32([dt2, rdt], "operator timestep")
            active = {"i": i, "j": j, "kts": kts, "kte": kte, "dt2": dt2, "rdt": rdt,
                      "kpbl": kpbl, "pblflg": pblflg, "rows": [], "solution": {}}
            calls.append(active)
        elif fields[0] == "ROW" and active is not None:
            if len(fields) != 8:
                raise ValueError(f"malformed ROW at line {lineno}")
            k = int(fields[1])
            vals = list(map(float, fields[2:]))
            if k != int(active["kts"]) + len(active["rows"]):
                raise ValueError("operator rows are missing or out of order")
            require_binary32(vals, f"operator row at line {lineno}")
            active["rows"].append(dict(zip(("del", "input", "rhs", "lower", "diagonal", "upper"), vals)))
        elif fields[0] == "SOL" and active is not None:
            if len(fields) != 3:
                raise ValueError(f"malformed SOL at line {lineno}")
            level = int(fields[1])
            if level in active["solution"]:
                raise ValueError(f"duplicate SOL row at line {lineno}")
            solution = float(fields[2])
            require_binary32([solution], f"SOL value at line {lineno}")
            active["solution"][level] = solution
    if len(calls) != 1:
        raise ValueError(f"expected one selected operator call, found {len(calls)}")
    call = calls[0]
    rows = call["rows"]
    expected_levels = int(call["kte"]) - int(call["kts"]) + 1
    if len(rows) != expected_levels or set(call["solution"]) != set(range(int(call["kts"]), int(call["kte"]) + 1)):
        raise ValueError("operator capture does not include the full selected column")
    return call, rows


def parse_nc(path: Path, call: dict[str, object]) -> tuple[float, list[float], list[float], dict[str, object], list[dict[str, float]] | None]:
    call_rows: list[list[str]] = []
    output_rows: list[list[str]] = []
    metadata: list[str] | None = None
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split(",")
        if fields[0] == "CALL":
            if metadata is not None:
                raise ValueError("multiple NC driver captures")
            if len(fields) not in (8, 11):
                raise ValueError(f"malformed NC CALL at line {lineno}")
            i, j, kts, kte = map(int, fields[1:5])
            dtbl, p_qnc, num_scalar = float(fields[5]), int(fields[6]), int(fields[7])
            if (i, j, kts, kte) != (call["i"], call["j"], call["kts"], call["kte"]):
                raise ValueError("QC operator and NC donor columns do not match")
            require_binary32([dtbl], "NC driver timestep")
            if dtbl <= 0.0 or not 1 <= p_qnc <= num_scalar:
                raise ValueError("invalid NC timestep or scalar identity")
            if len(fields) == 11:
                qnc_enabled_text = fields[8].strip().upper()
                scalar_pblmix = int(fields[9])
                qnc_flag_text = fields[10].strip().upper()
                if qnc_enabled_text not in {"T", "F"} or qnc_flag_text not in {"T", "F"}:
                    raise ValueError("invalid NC activation flag in driver capture")
                if qnc_enabled_text != "T" or qnc_flag_text != "T" or scalar_pblmix != 0:
                    raise ValueError("NC shared-A activation requires enabled=T, qnc_flag=T, scalar_pblmix=0")
                gate_metadata = {
                    "schema": "native_11_field",
                    "qnc_enabled": True,
                    "qnc_flag": True,
                    "scalar_pblmix": scalar_pblmix,
                    "activation_gates_verified": True,
                }
            else:
                gate_metadata = {
                    "schema": "legacy_8_field",
                    "qnc_enabled": None,
                    "qnc_flag": None,
                    "scalar_pblmix": None,
                    "activation_gates_verified": False,
                }
            metadata = fields
        elif fields[0] == "NC":
            call_rows.append(fields)
        elif fields[0] == "NC_OUT":
            output_rows.append(fields)
    if metadata is None:
        raise ValueError("missing NC driver capture")
    expected = int(call["kte"]) - int(call["kts"]) + 1
    if len(call_rows) != expected:
        raise ValueError("NC driver capture is not a full column")
    qc: list[float] = []
    nc: list[float] = []
    for offset, fields in enumerate(call_rows):
        if len(fields) != 4 or int(fields[1]) != int(call["kts"]) + offset:
            raise ValueError("NC donor levels are missing or out of order")
        qc.append(float(fields[2]))
        nc.append(float(fields[3]))
    dtbl = float(metadata[5])
    require_binary32([dtbl, *qc, *nc], "driver donor data")
    native_output = None
    if output_rows:
        if len(output_rows) != expected:
            raise ValueError("native NC output capture is not a full column")
        native_output = []
        for offset, fields in enumerate(output_rows):
            if len(fields) != 5 or int(fields[1]) != int(call["kts"]) + offset:
                raise ValueError("native NC output levels are missing or out of order")
            values = [float(value) for value in fields[2:]]
            require_binary32(values, "native NC output capture")
            native_output.append({
                "tendency": values[0],
                "scalar_tend_before": values[1],
                "scalar_tend_after": values[2],
            })
    return dtbl, qc, nc, gate_metadata, native_output


def validate(operator_path: Path, nc_path: Path) -> dict[str, object]:
    call, rows = parse_operator(operator_path)
    dtbl, qc_donors, nc_donors, activation_gates, native_output = parse_nc(nc_path, call)
    levels = list(range(int(call["kts"]), int(call["kte"]) + 1))
    for description, values in (("matrix", [x for row in rows for x in row.values()]),
                                ("QC/NC donors", qc_donors + nc_donors)):
        require_binary32(values, description)
    if any(row["del"] <= 0.0 for row in rows):
        raise ValueError("DEL must be positive and finite")
    if any(not math.isfinite(value) for value in [x for row in rows for x in row.values()]):
        raise ValueError("non-finite matrix record")
    lower = [row["lower"] for row in rows]
    diagonal = [row["diagonal"] for row in rows]
    upper = [row["upper"] for row in rows]
    if lower[0] != 0.0 or upper[-1] != 0.0:
        raise ValueError("closed matrix endpoints must have zero inactive off-diagonals")
    if any(value > 0.0 for value in lower + upper):
        raise ValueError("matrix has a positive off-diagonal")
    if any(value == 0.0 for value in diagonal):
        raise ValueError("matrix has a zero diagonal")
    row_sums = [lower[k] + diagonal[k] + upper[k] for k in range(len(rows))]
    if any(diagonal[k] < abs(lower[k]) + abs(upper[k]) for k in range(len(rows))):
        raise ValueError("matrix is not weakly diagonally dominant")
    dominance_margins = [diagonal[k] - abs(lower[k]) - abs(upper[k]) for k in range(len(rows))]
    min_dominance_margin = min(dominance_margins)
    if min_dominance_margin <= 0.0:
        raise ValueError("matrix lacks a strict row-dominance margin for the replay error bound")
    weighted_left_residual = []
    for column in range(len(rows)):
        total = rows[column]["del"] * diagonal[column]
        if column > 0:
            total += rows[column - 1]["del"] * upper[column - 1]
        if column + 1 < len(rows):
            total += rows[column + 1]["del"] * lower[column + 1]
        weighted_left_residual.append(total - rows[column]["del"])
    require_finite(row_sums + dominance_margins + weighted_left_residual, "derived matrix diagnostics")

    dt2_expected = f32(f32(2.0) * f32(dtbl))
    rdt_expected = f32(1.0 / f32(call["dt2"]))
    if f32(call["dt2"]) != dt2_expected or f32(call["rdt"]) != rdt_expected:
        raise ValueError("PBL dt2/rdt do not match the captured driver timestep")
    if any(row["input"] != row["rhs"] for row in rows):
        raise ValueError("cloud-water RHS does not equal its full-column input")
    if any(f32(rows[k]["input"]) != f32(qc_donors[k]) for k in range(len(rows))):
        raise ValueError("operator QC inputs do not match the paired PBL-driver QC capture")
    matrix_replay: dict[str, object] = {}
    nc_replay_output: list[float] = []
    for label, input_values in (("QC", [row["rhs"] for row in rows]), ("NC", nc_donors)):
        solved = solve_f32(lower, diagonal, upper, input_values)
        before = sum(rows[k]["del"] * input_values[k] for k in range(len(rows)))
        after = sum(rows[k]["del"] * solved[k] for k in range(len(rows)))
        require_binary32(solved, f"{label} replay result")
        require_finite([before, after], f"{label} DEL-weighted aggregate")
        replay_difference = None
        replay_bound = None
        if label == "QC":
            replay_difference = max(abs(solved[k] - call["solution"][levels[k]]) for k in range(len(rows)))
            operation_scale = max(
                abs(input_values[k])
                + abs(diagonal[k] * solved[k])
                + abs(lower[k] * (solved[k - 1] if k else 0.0))
                + abs(upper[k] * (solved[k + 1] if k + 1 < len(rows) else 0.0))
                for k in range(len(rows))
            )
            require_finite([operation_scale], "QC replay operation scale")
            # Each Thomas row uses at most six rounded operations; the small
            # normal term admits a runtime that flushes subnormal results.
            # Strict diagonal dominance bounds ||A^-1||_inf by 1/min_margin.
            replay_bound = (gamma32(24) * operation_scale + 24.0 * FLOAT32_MIN_NORMAL) / min_dominance_margin
            require_finite([replay_difference, replay_bound], "QC replay error bound")
            if replay_difference > replay_bound:
                raise ValueError("QC replay exceeds its binary32 operation-based error bound")
        if label == "NC":
            nc_replay_output = solved
        matrix_replay[label] = {
            "input_min": min(input_values),
            "output_min": min(solved),
            "max_abs_difference_from_captured_solution": replay_difference,
            "captured_solution_error_bound": replay_bound,
            "del_weighted_before": before,
            "del_weighted_after": after,
            "del_weighted_change": after - before,
            "del_weighted_relative_change": (after - before) / max(abs(before), 1.0e-300),
            "output": solved,
        }
        if min(input_values) >= 0.0 and min(solved) < 0.0:
            raise ValueError(f"{label} shared-A transport lost nonnegativity")
    native_nc_check = None
    if native_output is not None:
        if not activation_gates["activation_gates_verified"]:
            raise ValueError("native NC output requires verified 11-field activation gates")
        dt2 = f32(call["dt2"])
        rdt = f32(call["rdt"])
        native_rates = [
            f32(f32(nc_replay_output[k] - nc_donors[k]) * rdt)
            for k in range(len(rows))
        ]
        # The pinned WRF Intel profile uses -ftz; native subnormal rates
        # therefore become zero even when the binary32 replay retains them.
        native_rates = [0.0 if 0.0 < abs(value) < FLOAT32_MIN_NORMAL else value for value in native_rates]
        max_tendency_difference = max(
            abs(native_output[k]["tendency"] - native_rates[k])
            for k in range(len(rows))
        )
        if any(native_output[k]["tendency"] != native_rates[k] for k in range(len(rows))):
            raise ValueError("native NC tendency differs from same-A source-arithmetic replay")
        for k, observed in enumerate(native_output):
            expected_after = f32(observed["scalar_tend_before"] + observed["tendency"])
            if observed["scalar_tend_after"] != expected_after:
                raise ValueError("native scalar_tend did not capture exactly one NC tendency addition")
        native_nc_check = {
            "levels": len(native_output),
            "max_abs_tendency_difference_from_same_a_replay": max_tendency_difference,
            "tendency_units": "number/(kg dry air*s); module_em applies the native carrier later",
            "scalar_tend_accumulation": "each selected level records before and after one addition",
        }
    return {
        "target": {"i": call["i"], "j": call["j"], "kts": call["kts"], "kte": call["kte"]},
        "operator": {"dt2_seconds": call["dt2"], "rdt_per_second": call["rdt"], "kpbl": call["kpbl"], "pblflg": call["pblflg"]},
        "nc_driver_timestep_seconds": dtbl,
        "nc_activation_gates": activation_gates,
        "matrix": {
            "row_sum_min": min(row_sums), "row_sum_max": max(row_sums),
            "max_abs_row_sum_error": max(abs(value - 1.0) for value in row_sums),
            "minimum_diagonal_dominance_margin": min_dominance_margin,
            "inverse_infinity_norm_bound": 1.0 / min_dominance_margin,
            "max_abs_del_weighted_left_residual_pa": max(abs(value) for value in weighted_left_residual),
            "del_sum_pa": sum(row["del"] for row in rows),
            "lower_indexing": "row k lower = stored al(k-1); row k upper = stored au(k); endpoints closed",
        },
        "donors": {"qc_min": min(qc_donors), "nc_min": min(nc_donors), "nc_nonnegative": min(nc_donors) >= 0.0},
        "same_matrix_replay": matrix_replay,
        "native_nc_validation": native_nc_check,
        "scope": {
            "operator_is_actual_current_source_capture": "not_attested_by_replay_tool; see guarded_run_receipt_and_source_hashes",
            "nc_is_same_matrix_research_counterfactual": True,
            "native_call_observed": bool(activation_gates["activation_gates_verified"]),
            "native_solution_captured": False,
            "native_returned_tendency_captured": native_output is not None,
            "native_scalar_tend_accumulation_captured": native_output is not None,
            "del_equals_native_hybrid_dry_carrier": False,
            "activation_or_sedimentation_included": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operator", type=Path)
    parser.add_argument("nc", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.operator, args.nc)
    except (OSError, ValueError) as exc:
        print(f"pr65-pbl-operator-replay: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
