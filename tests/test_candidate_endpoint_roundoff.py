#!/usr/bin/env python3
"""Regression for endpoint arithmetic evidence across cancellation scales."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import endpoint_roundoff_bound


def test_large_endpoint_cancellation() -> None:
    direct = 23030673.5
    composition = 23509678.6089521
    metric = -479005.0682200
    scale = 2.0 * 1.0e10 * 3.0e5 + abs(composition) + abs(metric)
    error = abs(direct - composition - metric)
    old_tolerance = 1.0e-10 * (abs(direct) + abs(composition) + abs(metric))
    bound = endpoint_roundoff_bound(scale, 1)
    assert error > old_tolerance
    assert bound is not None and error <= bound
    assert abs((direct + 100000.0) - composition - metric) > bound


def test_invalid_evidence() -> None:
    assert endpoint_roundoff_bound(-1.0, 1) is None
    assert endpoint_roundoff_bound(float("nan"), 1) is None
    assert endpoint_roundoff_bound(1.0, -1) is None
    assert endpoint_roundoff_bound(1.0, 2**54) is None


def test_species_split_cancellation() -> None:
    ma, mb = 117741550818.24843, 117741549850.86249
    ra, rb = 0.014501546509563923, 0.014501545578241348
    species = ma * ra - mb * rb
    mixing = mb * (ra - rb)
    redistribution = (ma - mb) * ra
    scale = (abs(ma * ra) + abs(mb * rb) + abs(mixing)
             + abs(redistribution))
    old_tolerance = 1e-8 + 1e-12 * max(abs(species), abs(mixing + redistribution))
    error = abs(species - mixing - redistribution)
    bound = endpoint_roundoff_bound(scale, 1)
    assert error > old_tolerance
    assert bound is not None and error <= bound
    assert abs((species + 100.0) - mixing - redistribution) > bound


if __name__ == "__main__":
    test_large_endpoint_cancellation()
    test_invalid_evidence()
    test_species_split_cancellation()
    print("candidate endpoint arithmetic contract passed")
