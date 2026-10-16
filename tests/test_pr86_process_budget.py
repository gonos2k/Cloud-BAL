from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr86_process_budget import (  # noqa: E402
    LedgerError,
    METRICS,
    _add_stage,
    _cold_stage,
    _new_totals,
    _ratio,
    _record_values,
    _warm_stage,
)


def test_cold_record_parser_keeps_source_coordinates_and_numeric_columns() -> None:
    ids = "1 2 3 4 0 0 0 0"
    reals = " ".join(["1.0"] * 207)
    parsed_ids, values = _record_values(
        f"PR85_KDM6_COLD {ids} F {reals}", "PR85_KDM6_COLD", 217, 7)

    assert parsed_ids == [1, 2, 3, 4, 0, 0, 0, 0]
    assert len(values) == 207
    assert values[0] == 1.0


def test_record_parser_rejects_changed_token_contract() -> None:
    with pytest.raises(LedgerError, match="expected 217 tokens"):
        _record_values("PR85_KDM6_COLD 1 2", "PR85_KDM6_COLD", 217, 1)


def test_cold_activity_uses_same_cell_mass_and_volume_weights() -> None:
    packet = [0.0] * 33
    packet[0] = -2.0e-3
    packet[1] = 2.0e-3
    packet[15] = -3.0
    packet[27] = -0.5
    packet[30] = 2.0e-3

    values = _cold_stage("NG", packet, 0, dry_mass=10.0, cell_volume=4.0)

    assert values["mass_kg"] == pytest.approx(0.03)
    assert values["count_number"] == pytest.approx(12.0)
    assert values["heat_abs"] == pytest.approx(5.0)
    assert values["heat_signed"] == pytest.approx(-5.0)


def test_spatial_mass_map_does_not_mix_count_or_heat_units() -> None:
    totals = _new_totals()
    spatial = np.zeros((1, 1))
    values = {metric: value for metric, value in zip(METRICS, (2.0, 100.0, 1000.0, -500.0))}

    _add_stage(totals["NG"]["proposed"], values, spatial, 0, 0)

    assert spatial[0, 0] == pytest.approx(2.0)
    assert totals["NG"]["proposed"] == values


def test_warm_deferred_vector_is_request_minus_admitted() -> None:
    data = [0.0] * 107
    data[2] = 1000.0
    data[63] = -2.0e-3
    data[64] = 2.0e-3
    data[68] = -4.0
    data[72] = -0.5
    data[73] = 2.0e-3
    data[74] = -1.0e-3
    data[75] = 1.0e-3
    data[79] = -2.0
    data[83] = -0.25
    data[84] = 1.0e-3

    values = _warm_stage(data, 2, dry_mass=10.0, cell_volume=4.0, cpm=1000.0)

    assert values["mass_kg"] == pytest.approx(0.015)
    assert values["count_number"] == pytest.approx(8.0)
    assert values["heat_abs"] == pytest.approx(2500.0)
    assert values["heat_signed"] == pytest.approx(-2500.0)


def test_ratios_use_proposed_process_activity() -> None:
    assert _ratio(2.0, 8.0) == pytest.approx(0.25)
    assert _ratio(1.0, 0.0) is None
