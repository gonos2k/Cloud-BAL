#!/usr/bin/env python3
"""Audit the same-call Shinhong carrier using the source-bound runtime capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import stat
import sys
from pathlib import Path

from netCDF4 import Dataset

from pr65_pbl_operator_replay import parse_nc, parse_operator, solve_f32


def _records(path: Path) -> tuple[dict[str, object], list[dict[str, float]], list[float], list[float]]:
    call = None
    rows = []
    qc_pbl = []
    qc_settled = []
    qc_pbl_levels = []
    qc_settled_levels = []
    allowed_markers = {"GRID_STATIC_INPUT_LINKED"}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = [field.strip() for field in line.split(",")]
        if fields and fields[-1] == "":
            fields.pop()
        if not fields or not fields[0]:
            continue
        if fields[0] == "RUNTIME_CALL":
            if call is not None or len(fields) != 14:
                raise ValueError(f"malformed or repeated RUNTIME_CALL at line {line_number}")
            call = {
                "i": int(fields[1]), "j": int(fields[2]), "itimestep": int(fields[3]),
                "dtbl": float(fields[4]), "kts": int(fields[5]), "kte": int(fields[6]),
                "mut": float(fields[7]), "g": float(fields[8]), "dx": float(fields[9]),
                "dy": float(fields[10]), "area2d": float(fields[11]),
                "dx2d": float(fields[12]), "p_top": float(fields[13]),
            }
        elif fields[0] == "RUNTIME_ROW":
            if len(fields) != 8:
                raise ValueError(f"malformed RUNTIME_ROW at line {line_number}")
            rows.append({
                "k": int(fields[1]), "p8w_lower": float(fields[2]),
                "p8w_upper": float(fields[3]), "znw_lower": float(fields[4]),
                "znw_upper": float(fields[5]), "znu": float(fields[6]),
                "area2d": float(fields[7]),
            })
        elif fields[0] == "QC_PBL":
            if len(fields) != 3:
                raise ValueError(f"malformed QC_PBL at line {line_number}")
            qc_pbl.append(float(fields[2]))
            qc_pbl_levels.append(int(fields[1]))
        elif fields[0] == "QC_SETTLED":
            if len(fields) != 3:
                raise ValueError(f"malformed QC_SETTLED at line {line_number}")
            qc_settled.append(float(fields[2]))
            qc_settled_levels.append(int(fields[1]))
        elif fields[0] not in allowed_markers:
            raise ValueError(f"unknown PR67 carrier record {fields[0]!r} at line {line_number}")
    if call is None:
        raise ValueError("missing actual PBL RUNTIME_CALL")
    expected = call["kte"] - call["kts"] + 1
    if len(rows) != expected or len(qc_pbl) != expected or len(qc_settled) != expected:
        raise ValueError("runtime geometry and returned QC records must cover the full column")
    if [row["k"] for row in rows] != list(range(call["kts"], call["kte"] + 1)):
        raise ValueError("runtime geometry rows are missing or out of order")
    expected_levels = list(range(call["kts"], call["kte"] + 1))
    if qc_pbl_levels != expected_levels or qc_settled_levels != expected_levels:
        raise ValueError("returned QC records are missing or out of order")
    if not all(math.isfinite(value) for value in qc_pbl + qc_settled):
        raise ValueError("returned QC rates must be finite")
    runtime_numbers = [float(value) for key, value in call.items() if key not in {"i", "j", "itimestep", "kts", "kte"}]
    row_numbers = [float(value) for row in rows for key, value in row.items() if key != "k"]
    if not all(math.isfinite(value) for value in runtime_numbers + row_numbers):
        raise ValueError("same-call runtime carrier and geometry values must be finite")
    if call["mut"] <= 0.0 or call["g"] <= 0.0 or call["area2d"] <= 0.0:
        raise ValueError("same-call MUT, gravity, and area must be positive")
    return call, rows, qc_pbl, qc_settled


def _solve_tridiagonal64(lower: list[float], diagonal: list[float], upper: list[float], rhs: list[float]) -> list[float]:
    """Solve a tridiagonal system in float64 for the dry left invariant."""
    n = len(rhs)
    c = upper.copy()
    d = rhs.copy()
    b = diagonal.copy()
    for row in range(1, n):
        if b[row - 1] == 0.0:
            raise ValueError("zero pivot in float64 transpose solve")
        factor = lower[row] / b[row - 1]
        b[row] -= factor * c[row - 1]
        d[row] -= factor * d[row - 1]
    if b[-1] == 0.0:
        raise ValueError("zero final pivot in float64 transpose solve")
    result = [0.0] * n
    result[-1] = d[-1] / b[-1]
    for row in range(n - 2, -1, -1):
        result[row] = (d[row] - c[row] * result[row + 1]) / b[row]
    return result


def _transpose_weights(lower: list[float], diagonal: list[float], upper: list[float],
                       weights: list[float]) -> list[float]:
    """Return z for A^T z=weights with row-indexed off-diagonals."""
    lower_transpose = [0.0] + upper[:-1]
    upper_transpose = lower[1:] + [0.0]
    return _solve_tridiagonal64(lower_transpose, diagonal, upper_transpose, weights)


def audit(carrier_path: Path, operator_path: Path, nc_path: Path, wrfinput_path: Path,
          run_receipt_path: Path, exe_path: Path, source_path: Path,
          base_source_path: Path, object_path: Path, archive_path: Path) -> dict[str, object]:
    runtime, runtime_rows, qc_pbl, qc_settled = _records(carrier_path)
    call, operator_rows = parse_operator(operator_path)
    dtbl_nc, qc_donors, nc_donors, activation, native_nc = parse_nc(nc_path, call)
    if (runtime["i"], runtime["j"], runtime["kts"], runtime["kte"]) != (
        call["i"], call["j"], call["kts"], call["kte"]
    ):
        raise ValueError("runtime carrier and Shinhong operator identify different columns")
    if runtime["dtbl"] != dtbl_nc or call["dt2"] != 2.0 * runtime["dtbl"]:
        raise ValueError("runtime timestep does not match the captured Shinhong solve")
    if any(row["area2d"] != runtime["area2d"] for row in runtime_rows):
        raise ValueError("runtime area2d changed inside the selected PBL column")
    if len(operator_rows) != len(runtime_rows):
        raise ValueError("operator and runtime carrier column sizes differ")

    i, j = int(runtime["i"]), int(runtime["j"])
    kts = int(runtime["kts"])
    with Dataset(wrfinput_path) as source:
        x, y = i - 1, j - 1
        mu = float(source.variables["MU"][0, y, x])
        mub = float(source.variables["MUB"][0, y, x])
        if not math.isclose(runtime["mut"], mu + mub, rel_tol=0.0, abs_tol=1.0e-5):
            raise ValueError("same-call MUT does not equal immutable input MU+MUB at the selected cell")
        c1h = [float(value) for value in source.variables["C1H"][0, :]]
        c2h = [float(value) for value in source.variables["C2H"][0, :]]
        dnw = [float(value) for value in source.variables["DNW"][0, :]]
        c3f = [float(value) for value in source.variables["C3F"][0, :]]
        c4f = [float(value) for value in source.variables["C4F"][0, :]]
        znu = [float(value) for value in source.variables["ZNU"][0, :]]
        znw = [float(value) for value in source.variables["ZNW"][0, :]]
        msftx = float(source.variables["MAPFAC_MX"][0, y, x])
        msfty = float(source.variables["MAPFAC_MY"][0, y, x])
        input_hash = hashlib.sha256(wrfinput_path.read_bytes()).hexdigest()

    n = len(operator_rows)
    if len(c1h) != n or len(c2h) != n or len(dnw) != n or len(c3f) != n + 1 or len(c4f) != n + 1:
        raise ValueError("input hybrid grid coefficient dimensions do not match the runtime column")
    if len(znw) != n + 1 or len(znu) != n:
        raise ValueError("input vertical coordinates do not match the runtime column")
    if not all(math.isfinite(value) for value in c1h + c2h + dnw + c3f + c4f + znu + znw):
        raise ValueError("static hybrid coefficients and coordinates must be finite")

    coordinate_error = max(
        [abs(runtime_rows[k]["znw_lower"] - znw[k]) for k in range(n)]
        + [abs(runtime_rows[k]["znw_upper"] - znw[k + 1]) for k in range(n)]
        + [abs(runtime_rows[k]["znu"] - znu[k]) for k in range(n)]
    )
    if coordinate_error > 2.0e-7:
        raise ValueError("runtime ZNW/ZNU differ from the immutable hybrid input grid")

    # The retained source has the map-factor formula under #if 0 and executes
    # area2d=dx*dy, dx2d=dx in the active branch.
    area2d_expected = runtime["dx"] * runtime["dy"]
    if not math.isfinite(msftx) or not math.isfinite(msfty) or msftx <= 0.0 or msfty <= 0.0:
        raise ValueError("input map factors must be positive and finite")
    area_physical = runtime["dx"] * runtime["dy"] / (msftx * msfty)
    if not math.isclose(runtime["area2d"], area2d_expected, rel_tol=2.0e-6, abs_tol=0.1):
        raise ValueError("same-call area2d does not match its active DX*DY source formula")

    dry_dp = [-(c1h[k] * runtime["mut"] + c2h[k]) * dnw[k] for k in range(n)]
    if runtime["g"] <= 0.0 or msftx <= 0.0 or msfty <= 0.0 or area_physical <= 0.0:
        raise ValueError("gravity, map factors, and physical area must be positive")
    if any(not math.isfinite(value) or value <= 0.0 for value in dry_dp):
        raise ValueError("dry layer pressure thickness must be positive and finite")
    dry_interfaces = [c3f[k] * runtime["mut"] + c4f[k] + runtime["p_top"] for k in range(n + 1)]
    dry_dp_interface = [dry_interfaces[k] - dry_interfaces[k + 1] for k in range(n)]
    interface_formula_error = max(abs(dry_dp[k] - dry_dp_interface[k]) for k in range(n))
    if interface_formula_error > 0.2:
        raise ValueError("C1H/C2H/DNW layer pressure does not match C3F/C4F dry interfaces")
    del_total = [row["del"] for row in operator_rows]
    p8w_delta = [row["p8w_lower"] - row["p8w_upper"] for row in runtime_rows]
    max_del_p8w_error = max(abs(del_total[k] - p8w_delta[k]) for k in range(n))
    if max_del_p8w_error > 0.02:
        raise ValueError("captured Shinhong DEL does not match actual total P8W interface thickness")

    dry_mass = [value * area_physical / runtime["g"] for value in dry_dp]
    lower = [row["lower"] for row in operator_rows]
    diagonal = [row["diagonal"] for row in operator_rows]
    upper = [row["upper"] for row in operator_rows]
    # (A^T)[i,i-1]=upper[i-1] and (A^T)[i,i+1]=lower[i+1].
    transpose_solution = _transpose_weights(lower, diagonal, upper, dry_mass)
    left_residual = [transpose_solution[k] - dry_mass[k] for k in range(n)]
    total_mass = [value * area_physical / runtime["g"] for value in del_total]
    total_transpose_solution = _transpose_weights(lower, diagonal, upper, total_mass)
    total_left_residual = [total_transpose_solution[k] - total_mass[k] for k in range(n)]

    qc_solution = [float(call["solution"][k + kts]) for k in range(n)]
    nc_solution = solve_f32(lower, diagonal, upper, nc_donors)
    native_nc_tendency = [item["tendency"] for item in native_nc] if native_nc is not None else []
    if not activation["activation_gates_verified"] or len(native_nc_tendency) != n:
        raise ValueError("same-call native NC returned tendency capture is incomplete")

    def weighted(values: list[float]) -> float:
        return sum(dry_mass[k] * values[k] for k in range(n))

    qc_change = weighted(qc_solution) - weighted(qc_donors)
    nc_change = weighted(nc_solution) - weighted(nc_donors)
    qc_rate_pbl = weighted(qc_pbl)
    qc_rate_settled = weighted(qc_settled)
    nc_rate_native = weighted(native_nc_tendency)
    dt2 = float(call["dt2"])

    receipt = json.loads(run_receipt_path.read_text())
    if receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or receipt.get("output_isolation") != "PASS":
        raise ValueError("guarded run receipt is not PASS/PASS/returncode 0")
    receipt_inputs = receipt.get("inputs", [])
    input_record = next((item for item in receipt_inputs if Path(item["path"]).resolve() == wrfinput_path.resolve()), None)
    if input_record is None or input_record.get("sha256_before") != input_hash or input_record.get("sha256_after") != input_hash:
        raise ValueError("guarded run receipt does not bind the unchanged wrfinput_d01 hash")
    run_root = Path(receipt["run_root"])
    if exe_path.resolve() != (run_root / "wrf.exe").resolve():
        raise ValueError("captured executable is not the guarded run-root wrf.exe")
    exe_stat = exe_path.lstat()
    if not stat.S_ISREG(exe_stat.st_mode) or exe_stat.st_nlink != 1:
        raise ValueError("guarded executable must be a single-link regular file")
    exe_input_record = next((item for item in receipt_inputs if Path(item["path"]).resolve() == exe_path.resolve()), None)
    if exe_input_record is None or exe_input_record.get("sha256_before") != hashlib.sha256(exe_path.read_bytes()).hexdigest() or exe_input_record.get("sha256_after") != exe_input_record.get("sha256_before"):
        raise ValueError("guarded receipt does not bind the live run-root executable bytes")
    receipt_outputs = {item["path"]: item for item in receipt.get("outputs", [])}
    for name, path in (("pr67_pbl_carrier.raw", carrier_path),
                       ("pr65_pbl_operator.raw", operator_path), ("pr65_pbl_nc.raw", nc_path)):
        record = receipt_outputs.get(name)
        path_stat = path.lstat()
        if not stat.S_ISREG(path_stat.st_mode) or path_stat.st_nlink != 1:
            raise ValueError(f"guarded output is not a single-link regular file: {name}")
        if path.resolve() != (run_root / name).resolve() or record is None or record.get("nlink") != 1 or record.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"guarded run receipt does not bind single-link output {name}")
    if not all(path.is_file() for path in (source_path, base_source_path, exe_path, object_path, archive_path)):
        raise ValueError("source, object, archive, or executable identity path is unavailable")
    exe_hash = hashlib.sha256(exe_path.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    base_source_hash = hashlib.sha256(base_source_path.read_bytes()).hexdigest()
    object_hash = hashlib.sha256(object_path.read_bytes()).hexdigest()
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    for path in (source_path, base_source_path, object_path, archive_path):
        file_stat = path.lstat()
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise ValueError(f"build identity artifact must be a single-link regular file: {path}")
    return {
        "schema": "pr67_pbl_samecall_carrier_audit_v1",
        "capture": {
            "kind": "same_call_runtime_mut_with_static_input_linked_hybrid_coefficients",
            "input_wrfinput_sha256": input_hash,
            "guarded_run_receipt": str(run_receipt_path),
            "guarded_executable_sha256": exe_hash,
            "instrumented_source_sha256": source_hash,
            "source_bound_baseline_sha256": base_source_hash,
            "instrumented_object_sha256": object_hash,
            "linked_archive_sha256": archive_hash,
            "run_target": {"i": i, "j": j, "itimestep": runtime["itimestep"], "kts": kts, "kte": runtime["kte"]},
            "runtime_mut_matches_input_mu_plus_mub": True,
            "runtime_vertical_coordinates_match_input": True,
            "runtime_mut_slot_source": "module_first_rk_step_part1.F calls pbl_driver MUT=grid%mut",
            "captured_runtime_fields": ["MUT", "P8W", "ZNW", "ZNU", "DX", "DY", "AREA2D", "DX2D", "G", "P_TOP"],
            "static_input_fields": ["C1H", "C2H", "DNW", "C3F", "C4F", "MAPFAC_MX", "MAPFAC_MY"],
            "head_grid_live_coefficients": "not_captured; retained module/archive type metadata failed grid-id/dx sanity checks",
            "input_integrity": "PASS",
        },
        "carrier": {
            "dry_layer_formula_pa": "-(C1H*MUT+C2H)*DNW",
            "dry_interface_formula_pa": "C3F*MUT+C4F+P_TOP",
            "dry_interface_layer_formula_max_abs_error_pa": interface_formula_error,
            "total_interface_formula_source": "P8W(k)-P8W(k+1), as passed to Shinhong P3DI; DEL is total moist/interface thickness",
            "max_abs_operator_del_vs_runtime_p8w_difference_pa": max_del_p8w_error,
            "dry_dp_min_pa": min(dry_dp),
            "dry_dp_max_pa": max(dry_dp),
            "total_del_min_pa": min(del_total),
            "total_del_max_pa": max(del_total),
            "max_abs_total_del_minus_dry_dp_pa": max(abs(del_total[k] - dry_dp[k]) for k in range(n)),
            "max_abs_total_del_minus_dry_dp_relative": max(abs(del_total[k] - dry_dp[k]) / dry_dp[k] for k in range(n)),
            "pbl_area2d_argument_m2": runtime["area2d"],
            "pbl_area2d_active_source_formula_m2": area2d_expected,
            "physical_area_from_dxdy_map_factors_m2": area_physical,
            "dry_mass_min_kg_per_layer": min(dry_mass),
            "dry_mass_max_kg_per_layer": max(dry_mass),
            "dry_column_mass_kg": sum(dry_mass),
            "map_factor_x_input_metadata": msftx,
            "map_factor_y_input_metadata": msfty,
            "map_factor_area_usage": "area2d passed into PBL is DX*DY; physical dry mass uses DX*DY/(MAPFAC_MX*MAPFAC_MY)",
        },
        "same_matrix_dry_left_invariant": {
            "method": "float64 solve A^T z=m_d using captured A; report z-m_d",
            "max_abs_residual_kg": max(abs(value) for value in left_residual),
            "max_abs_residual_relative_to_layer_mass": max(abs(left_residual[k]) / dry_mass[k] for k in range(n)),
            "max_abs_residual_relative_to_column_mass": max(abs(value) for value in left_residual) / sum(dry_mass),
            "residual_by_layer_kg": left_residual,
        },
        "same_matrix_total_del_left_invariant": {
            "method": "float64 solve A^T z=m_DEL using same captured A; report z-m_DEL",
            "max_abs_residual_kg": max(abs(value) for value in total_left_residual),
            "max_abs_residual_relative_to_total_column_mass": max(abs(value) for value in total_left_residual) / sum(total_mass),
        },
        "weighted_column_results": {
            "qc_solver_donor_to_captured_solution_change_kg": qc_change,
            "qc_returned_pbl_rate_kg_per_s": qc_rate_pbl,
            "qc_returned_pbl_rate_times_dt2_kg": qc_rate_pbl * dt2,
            "qc_pbl_rate_integrated_minus_solution_change_kg": qc_rate_pbl * dt2 - qc_change,
            "nc_solver_donor_to_same_matrix_replay_solution_change_number": nc_change,
            "nc_solver_change_l1_number": sum(dry_mass[k] * abs(nc_solution[k] - nc_donors[k]) for k in range(n)),
            "nc_native_returned_rate_number_per_s": nc_rate_native,
            "nc_native_rate_times_dt2_number": nc_rate_native * dt2,
            "nc_native_rate_integrated_minus_solution_change_number": nc_rate_native * dt2 - nc_change,
            "nc_integrated_difference_fraction_of_l1_change": abs(nc_rate_native * dt2 - nc_change) / max(sum(dry_mass[k] * abs(nc_solution[k] - nc_donors[k]) for k in range(n)), 1.0e-300),
            "nc_integrated_difference_fraction_of_signed_net_change": abs(nc_rate_native * dt2 - nc_change) / max(abs(nc_change), 1.0e-300),
            "qc_settling_added_returned_rate_kg_per_s": qc_rate_settled - qc_rate_pbl,
            "qc_returned_rate_after_settling_kg_per_s": qc_rate_settled,
            "settling_increment_included_in_shinhong_matrix": False,
            "boundary_flux_in_closed_cloud_qc_solve": "none; cloud ic=2 donor endpoint equals qx and matrix endpoints are closed",
        },
        "layer_records": [
            {
                "k": k + kts,
                "dry_dp_pa": dry_dp[k],
                "dry_mass_kg": dry_mass[k],
                "total_del_pa": del_total[k],
                "qc_donor_kg_per_kg": qc_donors[k],
                "qc_solution_captured_kg_per_kg": qc_solution[k],
                "qc_returned_pbl_tendency_kg_per_kg_s": qc_pbl[k],
                "qc_returned_after_settling_tendency_kg_per_kg_s": qc_settled[k],
                "nc_donor_number_per_kg": nc_donors[k],
                "nc_same_matrix_replay_solution_number_per_kg": nc_solution[k],
                "nc_returned_tendency_number_per_kg_s": native_nc_tendency[k],
            }
            for k in range(n)
        ],
        "status": {
            "same_call_runtime_carrier": "PASS",
            "dry_coefficients": "STATIC_INPUT_LINKED",
            "dry_left_invariant": "MEASURED_FLOAT64",
            "full_physical_input_gate": "OPEN",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carrier", type=Path, required=True)
    parser.add_argument("--operator", type=Path, required=True)
    parser.add_argument("--nc", type=Path, required=True)
    parser.add_argument("--wrfinput", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--object", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.carrier, args.operator, args.nc, args.wrfinput,
                       args.run_receipt, args.exe, args.source, args.base_source,
                       args.object, args.archive)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"pr67-pbl-carrier-audit: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
