from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_cold_reasons import _bin_index  # noqa: E402
from pr86_process_budget import LedgerError  # noqa: E402


@pytest.mark.parametrize("fraction, expected", [
    (0.0, 0), (0.01, 0), (0.05, 1), (0.1, 2), (0.25, 3),
    (0.5, 4), (0.75, 5), (0.9, 6), (0.99, 7), (1.0, 8),
])
def test_approval_fraction_bins(fraction: float, expected: int) -> None:
    assert _bin_index(fraction) == expected


@pytest.mark.parametrize("fraction", [-0.01, 1.01, float("nan")])
def test_approval_fraction_bins_reject_invalid_values(fraction: float) -> None:
    with pytest.raises(LedgerError, match="invalid approval fraction"):
        _bin_index(fraction)
