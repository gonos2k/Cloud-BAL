#!/usr/bin/env python3
"""Pressure-state remap orchestration: signed PS, seed use and identity."""
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pressure_transition_reference import remap_pressure_state_reference


def fixture():
    shape = (3, 1, 4)
    old_i = np.broadcast_to(np.array([100000., 100000., 90000., 80000.])[:, None, None],
                            (4, 1, 4)).copy()
    old = np.broadcast_to(np.array([False, True, True])[:, None, None], shape).copy()
    new_i, new = old_i.copy(), old.copy()
    new_i[:2, 0, 1] -= 20.0
    new_i[:2, 0, 2] += 20.0
    new_i[:, 0, 3] = [100020., 95000., 90000., 80000.]
    new[0, 0, 3] = True
    area = np.full((1, 4), 2.0)
    temperature = np.where(old, 280.0, np.nan)
    species = np.zeros((6, *shape))
    species[:, ~old] = np.nan
    species[0, old] = float(np.float32(.01))
    mass = np.where(old, area * (old_i[:-1] - old_i[1:]) / 9.80665
                    / (1.0 + np.nansum(species, axis=0)), 0.0)
    # Untouched columns must retain the supplied post-thermo measure, even
    # when it differs from mass recomputed using rounded species.
    mass[:, 0, 0] *= 1.0 + 1.0e-9
    seed_t = np.full(shape, np.nan)
    seed_q = np.full((6, *shape), np.nan)
    seed_t[0, 0, 3] = 280.0
    seed_q[:, 0, 0, 3] = [float(np.float32(.02)), 0., 0., 0., 0., 0.]
    return [old_i, mass, temperature, species, old, new_i, new, area, seed_t, seed_q]


def test_signed_columns_and_boundary_strip():
    inputs = fixture()
    old_i, mb, tb, qb, old, new_i, new, area, seed_t, seed_q = inputs
    saved = [array.copy() for array in inputs]
    ma, ta, qa = remap_pressure_state_reference(*inputs)
    for original, snapshot in zip(inputs, saved):
        np.testing.assert_array_equal(original, snapshot)
    for actual, original in ((ma, mb), (ta, tb), (qa, qb)):
        np.testing.assert_array_equal(actual[..., 0], original[..., 0])
    np.testing.assert_array_equal(ta[old], tb[old])
    np.testing.assert_array_equal(qa[:, :, :, :3], qb[:, :, :, :3])
    # New bottom cell consists of the 20 Pa strip plus half the old bottom.
    strip_mass = 2.0 * 20.0 / 9.80665 / (1.0 + seed_q[0, 0, 0, 3])
    half_donor = .5 * mb[1, 0, 3]
    expected_vapor = np.float32((strip_mass * seed_q[0, 0, 0, 3]
                                + half_donor * qb[0, 1, 0, 3]) / (strip_mass + half_donor))
    assert qa[0, 0, 0, 3] == float(expected_vapor)
    assert ta[0, 0, 3] == 280.0
    for column in (1, 2, 3):
        active = new[:, 0, column]
        expected_mass = area[0, column] * np.diff(-new_i[:, 0, column])[active] / 9.80665
        expected_mass /= 1.0 + np.sum(qa[:, active, 0, column], axis=0)
        np.testing.assert_allclose(ma[active, 0, column], expected_mass, rtol=2e-15, atol=0.)
    assert np.all(ma[~new] == 0.)


def test_rejects_invalid_transition_atomically():
    for defect in ("missing_seed", "removal", "hole", "pressure_limit", "seed_nan",
                   "shape", "top_moved", "surface_offset", "inactive_face_changed"):
        inputs = fixture()
        if defect == "missing_seed":
            inputs[8:] = [None, None]
        elif defect == "removal":
            inputs[6][1, 0, 1] = False
        elif defect == "hole":
            inputs[4][1, 0, 0] = False
            inputs[4][0, 0, 0] = True
        elif defect == "pressure_limit":
            inputs[5][0, 0, 3] += 101.
        elif defect == "seed_nan":
            inputs[8][0, 0, 3] = np.nan
        elif defect == "shape":
            inputs[7] = np.ones((4,))
        elif defect == "top_moved":
            inputs[5][-1, 0, 1] -= 1.
        elif defect == "surface_offset":
            inputs[0][1, 0, 0] -= 1.
            inputs[5][1, 0, 0] -= 1.
        else:
            inputs[4][:, 0, 0] = inputs[6][:, 0, 0] = [False, False, True]
            inputs[0][:3, 0, 0] = inputs[5][:3, 0, 0] = 100000.
            inputs[5][1, 0, 0] -= 1.
        saved = [None if array is None else array.copy() for array in inputs]
        try:
            remap_pressure_state_reference(*inputs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted {defect}")
        for original, snapshot in zip(inputs, saved):
            np.testing.assert_array_equal(original, snapshot)


def check_fortran_fixture(path):
    from check_surface_pressure_reference import _read_fixture, _assert_storage_match

    cases = _read_fixture(Path(path))
    assert tuple(cases) == ("same_domain", "one_center")
    for name, case in cases.items():
        assert case["status"] == 20
        nz = case["new_interfaces"].size - 1
        offset = nz - case["old_mass"].size
        shape = (nz, 1, 1)
        old = np.arange(nz)[:, None, None] >= offset
        new = np.ones(shape, dtype=bool)
        old_i = np.concatenate((np.repeat(case["old_interfaces"][0], offset),
                                case["old_interfaces"]))[:, None, None]
        new_i = case["new_interfaces"][:, None, None]
        mb = np.zeros(shape)
        tb = np.full(shape, np.nan)
        qb = np.full((6, *shape), np.nan)
        mb[offset:, 0, 0] = case["old_mass"]
        tb[offset:, 0, 0] = case["old_temperature"]
        qb[:, offset:, 0, 0] = case["old_species"]
        seed_t, seed_q = tb.copy(), qb.copy()
        seed_t[0, 0, 0] = case["boundary_temperature"]
        seed_q[:, 0, 0, 0] = case["boundary_species"]
        md, temperature, species = remap_pressure_state_reference(
            old_i, mb, tb, qb, old, new_i, new, np.array([[case["area"]]]), seed_t, seed_q,
        )
        _assert_storage_match(case["final_temperature"], temperature[:, 0, 0], name)
        _assert_storage_match(case["final_species"], species[:, :, 0, 0], name)
        expected_q = species[:, :, 0, 0]
        pressure_mass = case["area"] * np.diff(-case["new_interfaces"]) / 9.80665
        q_error = np.sum(np.abs(case["final_species"] - expected_q), axis=0)
        mass_bound = pressure_mass * q_error / (
            (1.0 + expected_q.sum(axis=0)) * (1.0 + case["final_species"].sum(axis=0)))
        assert np.all(np.abs(case["final_mass"] - md[:, 0, 0])
                      <= mass_bound + 1e-13 * np.abs(md[:, 0, 0])), name
    print("Whole-state replay matches both Fortran transition fixtures")


if __name__ == "__main__":
    test_signed_columns_and_boundary_strip()
    test_rejects_invalid_transition_atomically()
    if len(sys.argv) == 2:
        check_fortran_fixture(sys.argv[1])
    print("Pressure-state replay tests passed")
