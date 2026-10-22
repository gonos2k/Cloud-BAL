from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr99_native_mass_effect import column_mass_rate


def test_rate_matches_full_hybrid_endpoint_mass_difference():
    mu0 = np.array([[100., 200.]])
    mu1 = np.array([[102., 196.]])
    c1, c2, dnw = np.array([.5, .25]), np.array([4., 2.]), np.array([-.25, -.75])
    area = np.array([[20., 40.]])
    mass = lambda mu: area / 10 * np.sum(
        -(c1[:, None, None] * mu + c2[:, None, None]) * dnw[:, None, None], axis=0)
    rate, beta = column_mass_rate(mu0, mu1, 2., c1, dnw, area, 10.)
    np.testing.assert_array_equal(rate, (mass(mu1) - mass(mu0)) / 2)
    assert beta == .3125  # A nonunit beta prevents silently assuming a pressure coordinate.


def test_r32_operands_are_promoted_before_subtraction():
    before = np.array([[2.**24]], dtype=np.float32)
    after = np.array([[-1.]], dtype=np.float32)
    rate, _ = column_mass_rate(before, after, 1., [1.], [-1.], [[1.]], 1.)
    assert rate[0, 0] == -16777217.


@pytest.mark.parametrize("seconds,c1,dnw,area", [(0., [1.], [-1.], [[1.]]),
                          (1., [0.], [-1.], [[1.]]), (1., [1.], [1.], [[1.]]),
                          (1., [1.], [-1.], [[np.nan]])])
def test_bad_measure_is_rejected(seconds, c1, dnw, area):
    with pytest.raises(ValueError, match="measure|sensitivity"):
        column_mass_rate([[0.]], [[1.]], seconds, c1, dnw, area, 1.)
