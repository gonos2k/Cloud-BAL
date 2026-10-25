#!/usr/bin/env python3
"""Source-order binary64 reference and bounded REAL32 gates for calc_ww_cp."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import pr94_cloud_response as cloud


CONSUMER = "module_big_step_utilities_em_mp_calc_ww_cp_"
ARCHIVE_MEMBER_SHA256 = "8f7a0666664bdccb45c414cb9e6ec481f7daaad3fa6170f0d51f524515572343"
COMPILER_PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
MASS_LEVELS = 39
VERTICAL_FACES = MASS_LEVELS + 1
ACTIVE_SHAPE = (VERTICAL_FACES, 280, 232)
UNIT_ROUNDOFF = 2.0 ** -24
REFERENCE_UNIT_ROUNDOFF = 2.0 ** -53
HALF_SUBNORMAL = 2.0 ** -150


@dataclass(frozen=True)
class BoundedValue:
    value: np.ndarray
    error: np.ndarray


def gamma(count: int) -> float:
    """Standard forward factor for ``count`` REAL32 roundings."""
    product = count * UNIT_ROUNDOFF
    if count < 0 or product >= 1:
        raise ValueError("invalid REAL32 operation count")
    return float(np.nextafter(product / (1.0 - product), np.inf))


def _gamma64(count: int) -> float:
    product = count * REFERENCE_UNIT_ROUNDOFF
    if count < 0 or product >= 1:
        raise ValueError("invalid binary64 operation count")
    return float(np.nextafter(product / (1.0 - product), np.inf))


def _up_add(left, right):
    return np.nextafter(np.asarray(left, dtype=np.float64) + np.asarray(right, dtype=np.float64), np.inf)


def _up_mul(left, right):
    return np.nextafter(np.asarray(left, dtype=np.float64) * np.asarray(right, dtype=np.float64), np.inf)


def _up_div(left, right):
    return np.nextafter(np.asarray(left, dtype=np.float64) / np.asarray(right, dtype=np.float64), np.inf)


def _down_sub(left, right):
    return np.nextafter(np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64), -np.inf)


def _down_mul(left, right):
    return np.nextafter(np.asarray(left, dtype=np.float64) * np.asarray(right, dtype=np.float64), -np.inf)


def _norm_upper(values: np.ndarray) -> float:
    squares = [float(np.nextafter(value * value, np.inf))
              for value in np.asarray(values, dtype=np.float64).ravel()]
    return float(np.nextafter(math.sqrt(math.fsum(squares)), np.inf))


def _term(value) -> BoundedValue:
    array = np.asarray(value, dtype=np.float64)
    return BoundedValue(array, np.zeros(array.shape, dtype=np.float64))


def _check_result(value: np.ndarray, error: np.ndarray) -> None:
    if not np.isfinite(value).all() or not np.isfinite(error).all() or np.any(error < 0):
        raise ValueError("calc_ww arithmetic reference or error bound is non-finite")


def _add(left: BoundedValue, right: BoundedValue) -> BoundedValue:
    value = left.value + right.value
    mag = _up_add(_up_add(np.abs(left.value), left.error), _up_add(np.abs(right.value), right.error))
    error = _up_add(_up_add(left.error, right.error),
                    _up_add(_up_mul(UNIT_ROUNDOFF + REFERENCE_UNIT_ROUNDOFF, mag), HALF_SUBNORMAL))
    _check_result(value, error)
    return BoundedValue(value, error)


def _sub(left: BoundedValue, right: BoundedValue) -> BoundedValue:
    return _add(left, BoundedValue(-right.value, right.error))


def _mul(left: BoundedValue, right: BoundedValue) -> BoundedValue:
    value = left.value * right.value
    av, bv = np.abs(left.value), np.abs(right.value)
    propagation = _up_add(_up_add(_up_mul(av, right.error), _up_mul(bv, left.error)), _up_mul(left.error, right.error))
    mag = _up_mul(_up_add(av, left.error), _up_add(bv, right.error))
    error = _up_add(propagation, _up_add(_up_mul(UNIT_ROUNDOFF + REFERENCE_UNIT_ROUNDOFF, mag), HALF_SUBNORMAL))
    _check_result(value, error)
    return BoundedValue(value, error)


def _div(numerator: BoundedValue, denominator: BoundedValue) -> BoundedValue:
    value = numerator.value / denominator.value
    numerator_abs, denominator_abs = np.abs(numerator.value), np.abs(denominator.value)
    denominator_lower = _down_sub(denominator_abs, denominator.error)
    if np.any(denominator_lower <= 0):
        raise ValueError("calc_ww denominator is not separated from zero")
    numerator_bound = _up_add(_up_mul(denominator_abs, numerator.error), _up_mul(numerator_abs, denominator.error))
    denominator_bound = _down_mul(denominator_abs, denominator_lower)
    if np.any(denominator_bound <= 0):
        raise ValueError("calc_ww denominator bound underflowed")
    propagated = _up_div(numerator_bound, denominator_bound)
    quotient_bound = _up_div(_up_add(numerator_abs, numerator.error), denominator_lower)
    error = _up_add(propagated, _up_add(_up_mul(UNIT_ROUNDOFF + REFERENCE_UNIT_ROUNDOFF, quotient_bound), HALF_SUBNORMAL))
    _check_result(value, error)
    return BoundedValue(value, error)


def _sum_terms(terms: list[BoundedValue]) -> BoundedValue:
    """Source-order sum with a gamma_(n-1) roundoff bound."""
    if not terms:
        raise ValueError("empty calc_ww sum")
    value = np.zeros_like(terms[0].value, dtype=np.float64)
    absolute_sum = np.zeros(value.shape, dtype=np.float64)
    input_error = np.zeros_like(absolute_sum)
    for term in terms:
        value = value + term.value
        absolute_sum = _up_add(absolute_sum, np.abs(term.value))
        input_error = _up_add(input_error, term.error)
    count = len(terms) - 1
    growth = float(np.nextafter((1.0 + UNIT_ROUNDOFF + REFERENCE_UNIT_ROUNDOFF) ** count, np.inf))
    combined_gamma = float(_up_add(gamma(count), _gamma64(count)))
    error = _up_add(_up_mul(combined_gamma, absolute_sum),
                    _up_mul(growth, input_error))
    error = _up_add(error, _up_mul(count * HALF_SUBNORMAL, growth))
    _check_result(value, error)
    return BoundedValue(value, error)


def _validate_native_arrays(arrays: dict[str, np.ndarray]) -> None:
    required = {"U", "V", "MU", "MUB", "C1H", "C2H", "DNW", "RDX", "RDY",
                "MSFTX", "MSFTY", "MSFUX", "MSFUY", "MSFVX", "MSFVX_INV", "MSFVY"}
    if set(arrays) != required:
        raise ValueError("native arrays differ from the PR99 consumer input contract")
    if arrays["U"].shape != (235, 40, 283) or arrays["V"].shape != (235, 40, 283):
        raise ValueError("native U/V arrays differ from the archived consumer dimensions")
    for name, value in arrays.items():
        array = np.asarray(value)
        if array.dtype != np.dtype("float32") or not np.isfinite(array).all():
            raise ValueError(f"{name} must be finite REAL32 consumer input")


def _same_frozen_carrier(candidate: dict[str, np.ndarray], hydro: dict[str, np.ndarray]) -> None:
    _validate_native_arrays(candidate)
    _validate_native_arrays(hydro)
    for name in candidate:
        if name not in {"U", "V"} and candidate[name].tobytes() != hydro[name].tobytes():
            raise ValueError(f"candidate and HYDRO consumer carrier differs: {name}")


def _calc_ww(arrays: dict[str, np.ndarray], *, x_start: int = 1,
             x_stop: int = 233, y_start: int = 1, y_stop: int = 281
             ) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate source expressions and forward bounds in consumer array order."""
    _validate_native_arrays(arrays)
    x = np.arange(x_start, x_stop)
    y = np.arange(y_start, y_stop)
    if not x.size or not y.size or x_start < 1 or x_stop > 233 or y_start < 1 or y_stop > 281:
        raise ValueError("calc_ww active region exceeds the archived consumer tile")
    xx, yy = x[:, None], y[None, :]

    mu, mub = _term(arrays["MU"]), _term(arrays["MUB"])
    muu_left = _mul(_sum_terms([BoundedValue(a, e) for a, e in (
        (mu.value[1:234], mu.error[1:234]), (mub.value[1:234], mub.error[1:234]),
        (mu.value[0:233], mu.error[0:233]), (mub.value[0:233], mub.error[0:233]))]), _term(0.5))
    muu = BoundedValue(np.zeros((235, 283)), np.zeros((235, 283)))
    muu.value[1:234], muu.error[1:234] = muu_left.value, muu_left.error

    muv = BoundedValue(np.zeros((235, 283)), np.zeros((235, 283)))
    muv_center = _mul(_sum_terms([BoundedValue(a, e) for a, e in (
        (mu.value[:, 1:282], mu.error[:, 1:282]), (mub.value[:, 1:282], mub.error[:, 1:282]),
        (mu.value[:, 0:281], mu.error[:, 0:281]), (mub.value[:, 0:281], mub.error[:, 0:281]))]), _term(0.5))
    muv.value[:, 1:282], muv.error[:, 1:282] = muv_center.value, muv_center.error

    c1 = _term(arrays["C1H"])
    c2 = _term(arrays["C2H"])
    dnw = _term(arrays["DNW"])
    rdx, rdy = _term(arrays["RDX"]), _term(arrays["RDY"])
    msftx = _term(arrays["MSFTX"])
    msfuy, msfvx_inv = _term(arrays["MSFUY"]), _term(arrays["MSFVX_INV"])
    u, v = _term(arrays["U"]), _term(arrays["V"])

    div_values, div_errors = [], []
    for k in range(MASS_LEVELS):
        c1k, c2k = _term(c1.value[k]), _term(c2.value[k])
        coef_u_e = _add(_mul(c1k, BoundedValue(muu.value[xx + 1, yy], muu.error[xx + 1, yy])), c2k)
        coef_u_w = _add(_mul(c1k, BoundedValue(muu.value[xx, yy], muu.error[xx, yy])), c2k)
        flux_u_e = _div(_mul(coef_u_e, BoundedValue(u.value[xx + 1, k, yy], u.error[xx + 1, k, yy])), BoundedValue(msfuy.value[xx + 1, yy], msfuy.error[xx + 1, yy]))
        flux_u_w = _div(_mul(coef_u_w, BoundedValue(u.value[xx, k, yy], u.error[xx, k, yy])), BoundedValue(msfuy.value[xx, yy], msfuy.error[xx, yy]))
        x_tendency = _mul(rdx, _sub(flux_u_e, flux_u_w))

        coef_v_n = _add(_mul(c1k, BoundedValue(muv.value[xx, yy + 1], muv.error[xx, yy + 1])), c2k)
        coef_v_s = _add(_mul(c1k, BoundedValue(muv.value[xx, yy], muv.error[xx, yy])), c2k)
        flux_v_n = _mul(_mul(coef_v_n, BoundedValue(v.value[xx, k, yy + 1], v.error[xx, k, yy + 1])), BoundedValue(msfvx_inv.value[xx, yy + 1], msfvx_inv.error[xx, yy + 1]))
        flux_v_s = _mul(_mul(coef_v_s, BoundedValue(v.value[xx, k, yy], v.error[xx, k, yy])), BoundedValue(msfvx_inv.value[xx, yy], msfvx_inv.error[xx, yy]))
        y_tendency = _mul(rdy, _sub(flux_v_n, flux_v_s))
        horizontal = _add(x_tendency, y_tendency)
        source_scale = _mul(BoundedValue(msftx.value[xx, yy], msftx.error[xx, yy]),
                            BoundedValue(dnw.value[k], dnw.error[k]))
        divv = _mul(source_scale, horizontal)
        div_values.append(divv.value)
        div_errors.append(divv.error)

    dmdt_value = np.zeros((x.size, y.size), dtype=np.float64)
    dmdt_absolute_sum = np.zeros(dmdt_value.shape, dtype=np.float64)
    dmdt_input_error = np.zeros_like(dmdt_absolute_sum)
    for value, error in zip(div_values, div_errors):
        dmdt_value += value
        dmdt_absolute_sum = _up_add(dmdt_absolute_sum, np.abs(value))
        dmdt_input_error = _up_add(dmdt_input_error, error)
    dmdt_growth = float(np.nextafter(
        (1.0 + UNIT_ROUNDOFF + REFERENCE_UNIT_ROUNDOFF) ** MASS_LEVELS, np.inf))
    dmdt_gamma = float(_up_add(gamma(MASS_LEVELS), _gamma64(MASS_LEVELS)))
    dmdt_error = _up_add(_up_mul(dmdt_gamma, dmdt_absolute_sum),
                         _up_mul(dmdt_growth, dmdt_input_error))
    dmdt_error = _up_add(dmdt_error,
                         _up_mul(MASS_LEVELS * HALF_SUBNORMAL, dmdt_growth))

    ww_value = np.zeros((VERTICAL_FACES, x.size, y.size), dtype=np.float64)
    ww_error = np.zeros_like(ww_value)
    for face in range(1, MASS_LEVELS):
        level = face - 1
        tendency = _mul(_mul(_term(dnw.value[level]), _term(c1.value[level])),
                        BoundedValue(dmdt_value, dmdt_error))
        previous = BoundedValue(ww_value[face - 1], ww_error[face - 1])
        next_ww = _sub(_sub(previous, tendency), BoundedValue(div_values[level], div_errors[level]))
        ww_value[face], ww_error[face] = next_ww.value, next_ww.error
    return ww_value.transpose(0, 2, 1), ww_error.transpose(0, 2, 1)


def calc_ww_reference(arrays: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Return binary64 source-order ``ww`` and pointwise arithmetic bound.

    Both outputs have ``read_ww`` layout: vertical face, active mass j, active
    mass i. Half a least-subnormal quantum is included for every REAL32
    operation, covering gradual underflow under the pinned ``-no-ftz`` profile.
    """
    reference, error = _calc_ww(arrays)
    return reference, np.nextafter(error.astype(np.float64), np.inf)


def fixed_buffer_vertical_faces(composition_path: Path) -> tuple[np.ndarray, str]:
    digest = hashlib.sha256(composition_path.read_bytes()).hexdigest()
    composition = json.loads(composition_path.read_text())
    masks = cloud.make_masks(composition["composed_qc_vertical_influence"], (39, 280, 232))
    support = masks["original_613_native_support"]
    buffer = masks["fixed_5_cell_chebyshev_buffer"]
    if (int(support.sum()) != 613 or int(support.any(axis=0).sum()) != 16
            or int(buffer.any(axis=0).sum()) != 196):
        raise ValueError("native ww comparison support differs from frozen 613/16/196 contract")
    faces = np.zeros((VERTICAL_FACES, 280, 232), dtype=bool)
    faces[:-1] |= buffer
    faces[1:] |= buffer
    return faces, digest


def _gate_metrics(measured: np.ndarray, allowed: np.ndarray, mask: np.ndarray) -> dict:
    measured = np.asarray(measured, dtype=np.float64)
    allowed = np.nextafter(np.asarray(allowed, dtype=np.float64), np.inf)
    observed_abs = np.abs(measured[mask])
    selected_allowed = allowed[mask]
    observed_l2, allowed_l2 = _norm_upper(observed_abs), _norm_upper(selected_allowed)
    observed_max, allowed_max = float(np.max(observed_abs)), float(np.max(selected_allowed))
    exceedances = int(np.count_nonzero(observed_abs > selected_allowed))
    passed = exceedances == 0 and observed_l2 <= allowed_l2 and observed_max <= allowed_max
    return {"observed_l2_pa_s": observed_l2, "allowed_l2_pa_s": allowed_l2,
            "observed_max_abs_pa_s": observed_max, "allowed_max_abs_pa_s": allowed_max,
            "pointwise_exceedances": exceedances, "status": "PASS" if passed else "FAIL"}


def _compare_fields(actual_delta: np.ndarray, predicted_delta: np.ndarray,
                    reference_error: np.ndarray, residual_error: np.ndarray,
                    mask: np.ndarray) -> dict:
    actual_delta = np.asarray(actual_delta, dtype=np.float64)
    predicted_delta = np.asarray(predicted_delta, dtype=np.float64)
    reference_error = np.asarray(reference_error, dtype=np.float64)
    residual_error = np.asarray(residual_error, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if (actual_delta.shape != predicted_delta.shape or reference_error.shape != actual_delta.shape
            or residual_error.shape != actual_delta.shape
            or mask.shape != actual_delta.shape or not np.isfinite(actual_delta).all()
            or not np.isfinite(predicted_delta).all() or not np.isfinite(reference_error).all()
            or not np.isfinite(residual_error).all() or np.any(reference_error < 0)
            or np.any(residual_error < 0) or not mask.any()):
        raise ValueError("actual, predicted, error, and fixed support arrays must be finite and aligned")
    reference_gate = _gate_metrics(predicted_delta, reference_error, mask)
    residual = actual_delta - predicted_delta
    source_gate = _gate_metrics(residual, residual_error, mask)
    return {"status": "PASS" if reference_gate["status"] == "PASS"
            and source_gate["status"] == "PASS" else "FAIL",
            "source_arithmetic": source_gate,
            "reference_constraint": reference_gate,
            "support_count": int(mask.sum()),
            "reference_delta_l2_pa_s": _norm_upper(predicted_delta[mask]),
            "arithmetic_bound_l2_pa_s": _norm_upper(reference_error[mask])}


def compare_actual(candidate_arrays: dict[str, np.ndarray], hydro_arrays: dict[str, np.ndarray],
                   candidate_ww: np.ndarray, hydro_ww: np.ndarray,
                   composition_path: Path) -> dict:
    """Assess archived actual output against source-derived pointwise bounds."""
    _same_frozen_carrier(candidate_arrays, hydro_arrays)
    candidate_ref, candidate_error = calc_ww_reference(candidate_arrays)
    hydro_ref, hydro_error = calc_ww_reference(hydro_arrays)
    candidate_ww = np.asarray(candidate_ww, dtype=np.float64)
    hydro_ww = np.asarray(hydro_ww, dtype=np.float64)
    if candidate_ww.shape != ACTIVE_SHAPE or hydro_ww.shape != ACTIVE_SHAPE:
        raise ValueError("actual calc_ww output differs from fixed active native shape")
    if not np.isfinite(candidate_ww).all() or not np.isfinite(hydro_ww).all():
        raise ValueError("actual calc_ww output contains non-finite values")
    mask, composition_sha = fixed_buffer_vertical_faces(composition_path)
    predicted = candidate_ref - hydro_ref
    reference_difference_error = _up_add(
        _up_mul(REFERENCE_UNIT_ROUNDOFF,
                _up_add(np.abs(candidate_ref), np.abs(hydro_ref))), HALF_SUBNORMAL)
    forward_error = _up_add(_up_add(candidate_error, hydro_error), reference_difference_error)
    actual = candidate_ww - hydro_ww
    actual_contrast_error = _up_add(
        _up_mul(REFERENCE_UNIT_ROUNDOFF,
                _up_add(np.abs(candidate_ww), np.abs(hydro_ww))), HALF_SUBNORMAL)
    residual_arithmetic_error = _up_add(
        _up_mul(REFERENCE_UNIT_ROUNDOFF, _up_add(np.abs(actual), np.abs(predicted))),
        HALF_SUBNORMAL)
    source_error = _up_add(_up_add(forward_error, actual_contrast_error), residual_arithmetic_error)
    comparison = _compare_fields(actual, predicted, forward_error, source_error, mask)
    arithmetic = comparison["source_arithmetic"]
    return {"schema": "pr102_native_drymass_constraint_v1", "status": comparison["status"],
            "consumer": CONSUMER, "archive_member_sha256": ARCHIVE_MEMBER_SHA256,
            "required_compiler_profile_sha256": COMPILER_PROFILE_SHA256,
            "comparison": "candidate_minus_HYDRO", "units": "Pa/s", "composition_sha256": composition_sha,
            "support_contract": {"mass_support_cells": 613, "mass_support_columns": 16,
                                 "fixed_buffer_mass_columns": 196,
                                 "vertical_faces": "union of two faces adjacent to each fixed-buffer mass level"},
            "finite": True, "support_count": comparison["support_count"],
            "observed_l2_pa_s": arithmetic["observed_l2_pa_s"], "allowed_l2_pa_s": arithmetic["allowed_l2_pa_s"],
            "observed_max_abs_pa_s": arithmetic["observed_max_abs_pa_s"],
            "allowed_max_abs_pa_s": arithmetic["allowed_max_abs_pa_s"],
            "pointwise_exceedances": arithmetic["pointwise_exceedances"],
            "source_arithmetic": arithmetic, "reference_constraint": comparison["reference_constraint"],
            "reference_delta_l2_pa_s": comparison["reference_delta_l2_pa_s"],
            "arithmetic_bound_l2_pa_s": comparison["arithmetic_bound_l2_pa_s"],
            "bound_method": "source-order binary64 reference; REAL32 gamma_n errors plus half-subnormal quantum per operation",
            "unit_roundoff": UNIT_ROUNDOFF, "gamma_39": gamma(MASS_LEVELS),
            "gamma_39_binary64": _gamma64(MASS_LEVELS),
            "operation_counts": {"face_average": 4, "coefficient": 2, "u_flux": 2, "v_flux": 2,
                                 "divv": 7, "dmdt_additions": MASS_LEVELS, "ww_update": 4},
            "input_semantics": "Final stored REAL32 winds and shared REAL32 carriers are exact reference inputs; their storage effects remain in the reference response",
            "arithmetic_profile": "Strict round-to-nearest; gradual underflow (-no-ftz); no fast-math reassociation"}
