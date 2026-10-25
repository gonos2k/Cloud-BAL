from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr102_native_ww_bound as bound  # noqa: E402


def consumer_arrays():
    shape3 = (235, 40, 283)
    shape2 = (235, 283)
    arrays = {
        "U": np.ones(shape3, dtype=np.float32),
        "V": np.ones(shape3, dtype=np.float32),
        "MU": np.ones(shape2, dtype=np.float32),
        "MUB": np.ones(shape2, dtype=np.float32),
        "C1H": np.ones(40, dtype=np.float32),
        "C2H": np.zeros(40, dtype=np.float32),
        "DNW": np.r_[np.full(39, -1.0 / 39, dtype=np.float32), np.float32(0)],
        "RDX": np.asarray(0.25, dtype=np.float32),
        "RDY": np.asarray(0.25, dtype=np.float32),
        "MSFTX": np.ones(shape2, dtype=np.float32),
        "MSFTY": np.ones(shape2, dtype=np.float32),
        "MSFUX": np.ones(shape2, dtype=np.float32),
        "MSFUY": np.ones(shape2, dtype=np.float32),
        "MSFVX": np.ones(shape2, dtype=np.float32),
        "MSFVX_INV": np.ones(shape2, dtype=np.float32),
        "MSFVY": np.ones(shape2, dtype=np.float32),
    }
    return arrays


def r32_consumer_cell(arrays, i=1, j=1):
    f = np.float32
    add = lambda a, b: f(f(a) + f(b))
    sub = lambda a, b: f(f(a) - f(b))
    mul = lambda a, b: f(f(a) * f(b))
    div = lambda a, b: f(f(a) / f(b))
    def avg_u(face_i):
        return mul(f(0.5), add(add(add(arrays["MU"][face_i, j], arrays["MUB"][face_i, j]),
                                   arrays["MU"][face_i - 1, j]), arrays["MUB"][face_i - 1, j]))

    def avg_v(face_j):
        return mul(f(0.5), add(add(add(arrays["MU"][i, face_j], arrays["MUB"][i, face_j]),
                                   arrays["MU"][i, face_j - 1]), arrays["MUB"][i, face_j - 1]))

    muu_e, muu_w = avg_u(i + 1), avg_u(i)
    muv_n, muv_s = avg_v(j + 1), avg_v(j)
    divv = []
    dmdt = f(0)
    for k in range(39):
        coef_ue = add(mul(arrays["C1H"][k], muu_e), arrays["C2H"][k])
        coef_uw = add(mul(arrays["C1H"][k], muu_w), arrays["C2H"][k])
        coef_vn = add(mul(arrays["C1H"][k], muv_n), arrays["C2H"][k])
        coef_vs = add(mul(arrays["C1H"][k], muv_s), arrays["C2H"][k])
        flux_ue = div(mul(coef_ue, arrays["U"][i + 1, k, j]), arrays["MSFUY"][i + 1, j])
        flux_uw = div(mul(coef_uw, arrays["U"][i, k, j]), arrays["MSFUY"][i, j])
        flux_vn = mul(mul(coef_vn, arrays["V"][i, k, j + 1]), arrays["MSFVX_INV"][i, j + 1])
        flux_vs = mul(mul(coef_vs, arrays["V"][i, k, j]), arrays["MSFVX_INV"][i, j])
        x_term = mul(arrays["RDX"], sub(flux_ue, flux_uw))
        y_term = mul(arrays["RDY"], sub(flux_vn, flux_vs))
        horizontal = add(x_term, y_term)
        value = mul(mul(arrays["MSFTX"][i, j], arrays["DNW"][k]), horizontal)
        divv.append(value)
        dmdt = add(dmdt, value)
    ww = [f(0)]
    for level in range(38):
        tendency = mul(mul(arrays["DNW"][level], arrays["C1H"][level]), dmdt)
        ww.append(sub(sub(ww[-1], tendency), divv[level]))
    return np.asarray([0, *ww[1:], 0], dtype=np.float32)


def test_constant_source_state_has_zero_reference_and_nonnegative_bound():
    arrays = consumer_arrays()
    reference, error = bound._calc_ww(arrays, x_start=1, x_stop=3, y_start=1, y_stop=3)
    assert reference.shape == (40, 2, 2)
    np.testing.assert_array_equal(reference, 0.0)
    assert np.isfinite(error).all()
    assert np.all(error >= 0)
    assert bound.gamma(39) > bound.gamma(3) > 0
    actual = r32_consumer_cell(arrays)
    mask = np.ones(actual.shape, dtype=bool)
    check = bound._compare_fields(actual, reference[:, 0, 0], error[:, 0, 0],
                                  error[:, 0, 0], mask)
    assert check["status"] == "PASS"
    assert check["reference_constraint"]["status"] == "PASS"


def test_linear_source_state_matches_source_order_formula_and_sign():
    arrays = consumer_arrays()
    x = np.arange(235, dtype=np.float32)[:, None, None]
    y = np.arange(283, dtype=np.float32)[None, None, :]
    arrays["U"][:] = np.broadcast_to(2.0 * x, arrays["U"].shape)
    arrays["V"][:] = np.broadcast_to(3.0 * y, arrays["V"].shape)
    arrays["C1H"][:39] = np.linspace(0.8, 1.4, 39, dtype=np.float32)
    arrays["C2H"][:39] = 0.1

    reference, error = bound._calc_ww(arrays, x_start=1, x_stop=2, y_start=1, y_stop=2)
    divv = []
    for k in range(39):
        coefficient = float(arrays["C1H"][k]) * 2.0 + float(arrays["C2H"][k])
        divv.append(float(arrays["DNW"][k])
                     * (0.25 * coefficient * 2.0 + 0.25 * coefficient * 3.0))
    dmdt = 0.0
    for value in divv:
        dmdt += value
    expected_face2 = -(float(arrays["DNW"][0]) * float(arrays["C1H"][0]) * dmdt) - divv[0]
    assert reference[1, 0, 0] == pytest.approx(expected_face2, abs=2e-14)
    assert reference[1, 0, 0] < 0
    assert error[1, 0, 0] > 0


def test_forward_gamma_bound_contains_sequential_real32_source_replay():
    arrays = consumer_arrays()
    rng = np.random.default_rng(19)
    arrays["U"][:] = rng.normal(0.0, 8.0, arrays["U"].shape).astype(np.float32)
    arrays["V"][:] = rng.normal(0.0, 7.0, arrays["V"].shape).astype(np.float32)
    arrays["MU"][:] = rng.uniform(1.0e4, 2.0e4, arrays["MU"].shape).astype(np.float32)
    arrays["MUB"][:] = rng.uniform(1.0e4, 2.0e4, arrays["MUB"].shape).astype(np.float32)
    arrays["MSFUY"][:] = rng.uniform(0.9, 1.1, arrays["MSFUY"].shape).astype(np.float32)
    arrays["MSFVX_INV"][:] = rng.uniform(0.9, 1.1, arrays["MSFVX_INV"].shape).astype(np.float32)
    arrays["C1H"][:39] = rng.uniform(0.5, 1.5, 39).astype(np.float32)
    arrays["C2H"][:39] = rng.uniform(-0.2, 0.2, 39).astype(np.float32)
    arrays["MSFTX"][:] = rng.uniform(0.9, 1.1, arrays["MSFTX"].shape).astype(np.float32)
    arrays["RDX"] = np.asarray(1.0 / 3000.0, dtype=np.float32)
    arrays["RDY"] = np.asarray(1.0 / 3000.0, dtype=np.float32)

    reference, error = bound._calc_ww(arrays, x_start=1, x_stop=2, y_start=1, y_stop=2)
    actual = r32_consumer_cell(arrays)
    difference = np.abs(actual.astype(np.float64) - reference[:, 0, 0])
    assert np.all(difference <= error[:, 0, 0])


def test_divergent_candidate_fails_reference_gate_even_when_real32_output_matches():
    hydro = consumer_arrays()
    candidate = {name: value.copy() for name, value in hydro.items()}
    candidate["U"][2, 0, 1] += np.float32(0.5)
    hydro_ref, hydro_error = bound._calc_ww(hydro, x_start=1, x_stop=2, y_start=1, y_stop=2)
    candidate_ref, candidate_error = bound._calc_ww(
        candidate, x_start=1, x_stop=2, y_start=1, y_stop=2)
    predicted = candidate_ref - hydro_ref
    error = np.nextafter(candidate_error + hydro_error
                         + bound.REFERENCE_UNIT_ROUNDOFF
                         * (np.abs(candidate_ref) + np.abs(hydro_ref))
                         + bound.HALF_SUBNORMAL, np.inf)
    assert np.linalg.norm(predicted) > 0
    actual_candidate = r32_consumer_cell(candidate).astype(np.float64)
    actual_hydro = r32_consumer_cell(hydro).astype(np.float64)
    actual_delta = actual_candidate - actual_hydro
    predicted_delta = predicted[:, 0, 0]
    arithmetic_bound = error[:, 0, 0]
    actual_delta_error = bound.REFERENCE_UNIT_ROUNDOFF * (
        np.abs(actual_candidate) + np.abs(actual_hydro)) + bound.HALF_SUBNORMAL
    residual_error = bound.REFERENCE_UNIT_ROUNDOFF * (
        np.abs(actual_delta) + np.abs(predicted_delta)) + bound.HALF_SUBNORMAL
    arithmetic_bound = np.nextafter(arithmetic_bound + actual_delta_error + residual_error, np.inf)
    mask = np.ones(predicted_delta.shape, dtype=bool)
    check = bound._compare_fields(actual_delta, predicted_delta,
                                  error[:, 0, 0], arithmetic_bound, mask)
    assert check["source_arithmetic"]["status"] == "PASS"
    assert check["reference_constraint"]["status"] == "FAIL"
    assert check["status"] == "FAIL"

    altered_actual = actual_delta.copy()
    altered_actual[1] += 1.0e-5
    rejected = bound._compare_fields(altered_actual, predicted_delta,
                                     error[:, 0, 0], arithmetic_bound, mask)
    assert rejected["source_arithmetic"]["status"] == "FAIL"


def test_candidate_and_hydro_must_share_every_nonwind_consumer_input():
    hydro = consumer_arrays()
    candidate = {name: value.copy() for name, value in hydro.items()}
    candidate["U"][0, 0, 0] += np.float32(1)
    bound._same_frozen_carrier(candidate, hydro)
    candidate["MU"][0, 0] += np.float32(1)
    with pytest.raises(ValueError, match="carrier differs: MU"):
        bound._same_frozen_carrier(candidate, hydro)
