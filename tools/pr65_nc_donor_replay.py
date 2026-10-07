#!/usr/bin/env python3
"""Reconstruct the target NC advection tendency from the PR65 face observer."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


TARGET = (172, 76, 1)
FLOAT32_UNIT_ROUNDOFF = 2.0**-24
FLOAT32_MIN_NORMAL = 2.0**-126
FLOAT32_MAX = (2.0 - 2.0**-23) * 2.0**127


def gamma32(operation_count: int) -> float:
    return operation_count * FLOAT32_UNIT_ROUNDOFF / (1.0 - operation_count * FLOAT32_UNIT_ROUNDOFF)


def float32_half_ulp(value: float) -> float:
    if value == 0.0:
        return 2.0**-150
    if abs(value) < FLOAT32_MIN_NORMAL:
        return 2.0**-150
    return 2.0 ** (math.floor(math.log2(abs(value))) - 24)


def require_finite(values: list[float], description: str) -> None:
    if not all(math.isfinite(value) and abs(value) <= FLOAT32_MAX for value in values):
        raise ValueError(f"non-finite {description}")


def flux5(donors: list[float], velocity: float, time_step: float) -> tuple[float, float]:
    q_im3, q_im2, q_im1, q_i, q_ip1, q_ip2 = donors
    flux6 = (37.0 * (q_i + q_im1) - 8.0 * (q_ip1 + q_im2) + (q_ip2 + q_im3)) / 60.0
    correction = (
        (q_ip2 - q_im3) - 5.0 * (q_ip1 - q_im2) + 10.0 * (q_i - q_im1)
    ) / 60.0
    upwind_sign = (1.0 if time_step > 0.0 else -1.0) * (1.0 if velocity >= 0.0 else -1.0)
    reconstructed = velocity * (flux6 - upwind_sign * correction)
    absolute_intermediates = (
        37.0 * (abs(q_i) + abs(q_im1))
        + 8.0 * (abs(q_ip1) + abs(q_im2))
        + abs(q_ip2) + abs(q_im3)
        + abs(q_ip2) + abs(q_im3)
        + 5.0 * (abs(q_ip1) + abs(q_im2))
        + 10.0 * (abs(q_i) + abs(q_im1))
    ) / 60.0
    error_bound = gamma32(32) * abs(velocity) * absolute_intermediates + float32_half_ulp(reconstructed)
    require_finite([flux6, correction, reconstructed, absolute_intermediates, error_bound], "flux5 donor reconstruction")
    return reconstructed, error_bound


def read_faces(path: Path) -> dict[int, list[dict[str, object]]]:
    stages: dict[int, list[dict[str, object]]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        kind = fields[0]
        expected_payload = {"FACE_X": 18, "FACE_Y": 13, "FACE_Z": 9}.get(kind)
        if expected_payload is None or len(fields) != 6 + expected_payload:
            raise ValueError(f"malformed face row at line {line_number}")
        try:
            rk, species, i, j, k = map(int, fields[1:6])
            values = [float(value) for value in fields[6:]]
        except ValueError as exc:
            raise ValueError(f"invalid face number at line {line_number}") from exc
        if (i, j, k) != TARGET or species != 3 or rk not in (1, 2):
            raise ValueError(f"unexpected face target or stage at line {line_number}")
        try:
            require_finite(values, f"face value at line {line_number}")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        stages.setdefault(rk, []).append({"kind": kind, "values": values})
    if set(stages) != {1, 2} or any(len(rows) != 6 for rows in stages.values()):
        raise ValueError("expected two RK stages with six face rows each")
    for rk, rows in stages.items():
        if [row["kind"] for row in rows] != ["FACE_Y", "FACE_X", "FACE_Z"] * 2:
            raise ValueError(f"unexpected face-call order at RK{rk}")
    return stages


def reconstruct(rows: list[dict[str, object]], label: str, time_step: float) -> dict[str, object]:
    y, x, z = rows
    yv = y["values"]
    xv = x["values"]
    zv = z["values"]
    # FACE_X/Y write their two target bounding-face fluxes first and the
    # direction metric plus map factor last. FACE_Z has an explicit schema.
    y_flux = -yv[-1] * yv[-2] * (yv[1] - yv[0])
    x_flux = -xv[-1] * xv[-2] * (xv[1] - xv[0])
    vertical = -zv[8] * (zv[1] - zv[0])
    x_scale = xv[-1] * xv[-2]
    y_scale = yv[-1] * yv[-2]
    x_error = gamma32(4) * abs(x_scale) * (abs(xv[0]) + abs(xv[1])) + float32_half_ulp(x_flux)
    y_error = gamma32(4) * abs(y_scale) * (abs(yv[0]) + abs(yv[1])) + float32_half_ulp(y_flux)
    z_error = gamma32(3) * abs(zv[8]) * (abs(zv[0]) + abs(zv[1])) + float32_half_ulp(vertical)
    sum_error = gamma32(4) * (abs(x_flux) + abs(y_flux) + abs(vertical)) + x_error + y_error + z_error
    require_finite([x_flux, y_flux, vertical, x_flux + y_flux + vertical, x_scale, y_scale, x_error, y_error, z_error, sum_error], "face tendency reconstruction")
    result: dict[str, object] = {
        "call": label,
        "x_tendency": x_flux,
        "y_tendency": y_flux,
        "z_tendency": vertical,
        "sum_tendency": x_flux + y_flux + vertical,
        "x_tendency_binary32_roundoff_bound": x_error,
        "y_tendency_binary32_roundoff_bound": y_error,
        "z_tendency_binary32_roundoff_bound": z_error,
        "sum_tendency_binary32_roundoff_bound": sum_error,
        "x_face_fluxes": [xv[0], xv[1]],
        "y_face_fluxes": [yv[0], yv[1]],
        "vertical_face_fluxes": [zv[0], zv[1]],
        "vertical_rom": [zv[2], zv[3]],
        "vertical_field": [zv[4], zv[5]],
        "vertical_weights": [zv[6], zv[7]],
        "rdzw": zv[8],
    }
    if label == "NC":
        x_expected = [flux5(xv[4:10], xv[2], time_step), flux5(xv[10:16], xv[3], time_step)]
        y_expected = [flux5(yv[4:10], yv[2], time_step), flux5(yv[5:11], yv[3], time_step)]
        for direction, actual, expected in (
            ("x", [xv[0], xv[1]], x_expected),
            ("y", [yv[0], yv[1]], y_expected),
        ):
            for face, (captured, (calculated, bound)) in enumerate(zip(actual, expected), 1):
                if abs(captured - calculated) > bound:
                    raise ValueError(f"NC {direction} face {face} disagrees with flux5 donor reconstruction")
        result["x_flux5_from_donors"] = [value[0] for value in x_expected]
        result["y_flux5_from_donors"] = [value[0] for value in y_expected]
        result["x_face_flux_error_bounds"] = [value[1] for value in x_expected]
        result["y_face_flux_error_bounds"] = [value[1] for value in y_expected]
    if label == "NC":
        reconstructed_interface = zv[3] * (zv[6] * zv[5] + zv[7] * zv[4])
        interface_error = (
            gamma32(4) * abs(zv[3]) * (abs(zv[6] * zv[5]) + abs(zv[7] * zv[4]))
            + float32_half_ulp(reconstructed_interface)
        )
        require_finite([reconstructed_interface, interface_error], "vertical interface reconstruction")
        if abs(reconstructed_interface - zv[1]) > interface_error:
            raise ValueError("NC vertical upper face disagrees with source linear interpolation")
        result["upper_interface_flux_from_linear_face"] = reconstructed_interface
        result["upper_interface_flux_error_bound"] = interface_error
    return result


def read_host(path: Path) -> dict[tuple[str, int], dict[str, float | int]]:
    columns = (
        "field", "partner", "old", "new", "sc_tend", "advect_tend", "msfty",
        "c1", "c2", "muold", "munew", "mub", "dt", "den_old", "den_new",
    )
    target_rows: dict[tuple[str, int], dict[str, float | int]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split()
        if len(fields) < 3 or fields[0] != "HOST" or fields[1] not in {"QC_AFTER", "NC_AFTER"}:
            continue
        if len(fields) != 23:
            raise ValueError(f"unexpected host row schema at line {line_number}")
        try:
            rk, i, j, k, species, partner_id = map(int, fields[2:8])
            values = [float(value) for value in fields[8:]]
        except ValueError as exc:
            raise ValueError(f"invalid host number at line {line_number}") from exc
        if (i, j, k) != TARGET:
            continue
        if rk not in (1, 2, 3):
            raise ValueError(f"unexpected host RK step at line {line_number}")
        require_finite(values, f"host value at line {line_number}")
        if species != 3 or partner_id not in (3,):
            raise ValueError("unexpected target species indices")
        key = (fields[1], rk)
        if key in target_rows:
            raise ValueError(f"duplicate target host row: {key}")
        target_rows[key] = {"rk": rk, "species": species, **dict(zip(columns, values))}
    required = {(f"{species}_AFTER", rk) for species in ("QC", "NC") for rk in (1, 2, 3)}
    if target_rows.keys() != required:
        raise ValueError("host capture must contain one completed QC and NC target row for RK1, RK2, and RK3")
    return target_rows


def validate(face_path: Path, host_path: Path, time_step: float = 20.0) -> dict[str, object]:
    if not math.isfinite(time_step) or time_step <= 0.0:
        raise ValueError("namelist time_step must be finite and positive")
    stages = read_faces(face_path)
    host = read_host(host_path)
    reconstruction: dict[str, object] = {}
    for rk, rows in stages.items():
        # The caller instruments the same species index for the moist and
        # scalar arrays. solve_em calls the QC moist loop before the NC scalar
        # loop; the two consecutive Y/X/Z triplets preserve that call order.
        qc = reconstruct(rows[:3], "QC", time_step)
        nc = reconstruct(rows[3:], "NC", time_step)
        qc_host = host[("QC_AFTER", rk)]
        nc_host = host[("NC_AFTER", rk)]
        for reconstruction_row, host_row in ((qc, qc_host), (nc, nc_host)):
            expected = float(host_row["advect_tend"])
            actual = float(reconstruction_row["sum_tendency"])
            roundoff_bound = float(reconstruction_row["sum_tendency_binary32_roundoff_bound"]) + float32_half_ulp(expected)
            require_finite([expected, actual, roundoff_bound], f"RK{rk} {reconstruction_row['call']} tendency comparison")
            tolerance = roundoff_bound
            if abs(actual - expected) > tolerance:
                raise ValueError(f"RK{rk} {reconstruction_row['call']} face sum does not match native advect tendency")
        if nc_host["sc_tend"] != 0.0:
            raise ValueError(f"RK{rk} NC has a nonzero non-advection tendency")
        nc["advect_tendency_binary32_roundoff_bound"] = roundoff_bound
        reconstruction[f"rk{rk}"] = {"qc": qc, "nc": nc}

    completed_updates: dict[str, object] = {}
    for rk in (1, 2, 3):
        qc = host[("QC_AFTER", rk)]
        nc = host[("NC_AFTER", rk)]
        for key in ("den_old", "den_new", "msfty", "c1", "c2", "muold", "munew", "mub", "dt"):
            if qc[key] != nc[key]:
                raise ValueError(f"RK{rk} QC and NC do not share carrier field {key}")
        for species, row in (("QC", qc), ("NC", nc)):
            c1 = float(row["c1"])
            c2 = float(row["c2"])
            muold = float(row["muold"])
            munew = float(row["munew"])
            mub = float(row["mub"])
            dt = float(row["dt"])
            den_old = float(row["den_old"])
            den_new = float(row["den_new"])
            old = float(row["old"])
            msfty = float(row["msfty"])
            advect = float(row["advect_tend"])
            sc_tend = float(row["sc_tend"])
            new = float(row["new"])
            require_finite([c1, c2, muold, munew, mub, dt, den_old, den_new, old, msfty, advect, sc_tend, new], f"RK{rk} {species} update inputs")
            if dt <= 0.0 or den_old <= 0.0 or den_new <= 0.0:
                raise ValueError(f"RK{rk} {species} update has a nonpositive dt or carrier denominator")
            for name, observed, predicted, scale in (
                ("old", den_old, c1 * (muold + mub) + c2, abs(c1) * (abs(muold) + abs(mub)) + abs(c2)),
                ("new", den_new, c1 * (munew + mub) + c2, abs(c1) * (abs(munew) + abs(mub)) + abs(c2)),
            ):
                bound = gamma32(4) * scale + float32_half_ulp(observed)
                require_finite([predicted, scale, bound], f"RK{rk} {species} {name} carrier reconstruction")
                if abs(observed - predicted) > bound:
                    raise ValueError(f"RK{rk} {species} {name} carrier denominator does not match c1*mu+c2")

            combined_tendency = msfty * advect + sc_tend
            predicted_new = (den_old * old + dt * combined_tendency) / den_new
            update_bound = (
                gamma32(8) * (
                    abs(den_old * old)
                    + abs(dt) * (abs(msfty * advect) + abs(sc_tend))
                ) / den_new
                + float32_half_ulp(new)
            )
            require_finite([combined_tendency, predicted_new, update_bound], f"RK{rk} {species} native update reconstruction")
            if abs(new - predicted_new) > update_bound:
                raise ValueError(f"RK{rk} {species} completed update does not match the native carrier equation")
            row["predicted_new_from_logged_float32_fields"] = predicted_new
            row["completed_update_binary32_roundoff_bound"] = update_bound
        completed_updates[f"rk{rk}"] = {
            "qc": qc,
            "nc": nc,
            "shared_carrier_fields_match": True,
        }
        if rk == 1 and not (float(nc["old"]) == 0.0 and float(nc["new"]) < 0.0):
            raise ValueError("RK1 completed NC update is not the observed zero-to-negative transition")
    if float(host[("NC_AFTER", 3)]["new"]) != 0.0:
        raise ValueError("RK3 completed NC target is not zero")

    return {
        "target": list(TARGET),
        "face_row_count": sum(map(len, stages.values())),
        "face_call_order_per_stage": ["QC moist scalar", "NC scalar"],
        "flux_reconstruction": "source flux5 donor stencil and vertical linear face interpolation; comparison tolerances are binary32 forward-error bounds",
        "observer_source_authentication": "not performed by replay; bind capture to recorded patched source hash and run evidence",
        "tendency_reconstruction": reconstruction,
        "completed_host_updates": completed_updates,
        "global_minimum_assessed": False,
        "interpretation": "The first completed target NC negativity is the RK1 regular scalar-advection update; RK1/RK2 do not invoke the final-stage positive-definite scalar path.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("face_capture", type=Path)
    parser.add_argument("host_capture", type=Path)
    parser.add_argument("--time-step-seconds", type=float, default=20.0)
    args = parser.parse_args()
    try:
        result = validate(args.face_capture, args.host_capture, args.time_step_seconds)
    except (OSError, ValueError, IndexError) as exc:
        print(f"pr65_nc_donor_replay: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
