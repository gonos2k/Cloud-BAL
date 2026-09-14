#!/usr/bin/env python3
"""Regression checks for cancellation-aware independent radar-ledger replay."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    radar_ledger_operand_tolerance,
    radar_ledger_residual_tolerance,
    validate,
)


LEDGER_OPERANDS = (
    "flux_input",
    "flux_deposited",
    "flux_suspended",
    "flux_boundary_exit",
    "flux_terrain_intercept",
    "flux_observation_blocked",
    "flux_no_echo_blocked",
    "flux_microphysical_loss",
)


def mutate_balanced_ledger(path: Path, damaged: Path) -> None:
    """Shift input and one terminal term equally, preserving same-artifact closure."""
    shutil.copyfile(path, damaged)
    with netCDF4.Dataset(damaged, "r+") as dataset:
        for name in ("flux_input", "flux_terrain_intercept"):
            dataset.setncattr(name, float(dataset.getncattr(name)) + 1.0)


def check(path: Path) -> None:
    summary, failures = validate(path)
    assert not failures, failures
    assert summary["radar_reconstruction_independently_validated"] is True

    with netCDF4.Dataset(path) as dataset:
        expected = {
            name: float(dataset.getncattr(name)) for name in LEDGER_OPERANDS
        }
    residual_budget = radar_ledger_residual_tolerance(expected)
    assert residual_budget == sum(
        radar_ledger_operand_tolerance(expected[name])
        for name in LEDGER_OPERANDS
    )
    assert residual_budget > radar_ledger_operand_tolerance(expected["flux_input"])

    with tempfile.TemporaryDirectory(prefix="radar-ledger-validator-") as directory:
        damaged = Path(directory) / "balanced-ledger-mutation.nc"
        mutate_balanced_ledger(path, damaged)
        _, mutation_failures = validate(damaged)

    # The paired mutation preserves the artifact's own closure exactly.  It
    # must nevertheless be rejected by the independent replay for both terms.
    assert "flux_input independent radar ledger" in mutation_failures
    assert "flux_terrain_intercept independent radar ledger" in mutation_failures
    assert "independent flux ledger gate" not in mutation_failures
    assert "reported flux ledger gate" not in mutation_failures

    print(f"PASS radar ledger cancellation tolerance/mutation: {path.name}")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
