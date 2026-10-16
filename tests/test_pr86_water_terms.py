import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr86_water_terms import remaining_after_storage_changes  # noqa: E402


def test_remainder_subtracts_signed_creation_and_loss_terms():
    # Creation is positive C and lowers R; loss is negative C and raises R.
    remaining = remaining_after_storage_changes(10.0, [("creation", 3.0), ("loss", -2.0)])
    assert remaining == {"creation": 7.0, "loss": 9.0}
