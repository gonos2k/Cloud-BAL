"""Focused arithmetic and parser checks for the V42 budget diagnostic."""
from __future__ import annotations

import gzip
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr87_v42_budget as budget  # noqa: E402


def test_total_water_l1_sums_species_before_absolute_value() -> None:
    species_deltas = [np.array([[5.0, 2.0]]), np.array([[-5.0, -1.0]])]

    total, stats = budget._sum_species_delta(species_deltas)

    np.testing.assert_array_equal(total, [[0.0, 1.0]])
    assert stats["signed"] == 1.0
    assert stats["l1"] == 1.0
    assert sum(np.sum(np.abs(delta)) for delta in species_deltas) == 13.0


def test_inventory_delta_applies_cellwise_dry_mass_and_preserves_signs() -> None:
    before = np.array([[1.0, 2.0]])
    after = np.array([[3.0, 1.0]])
    dry_mass = np.array([[10.0, 2.0]])

    delta = budget._inventory_delta(before, after, dry_mass)

    np.testing.assert_array_equal(delta, [[20.0, -2.0]])
    assert budget._weighted_stats(delta) == {
        "signed": 18.0,
        "l1": 22.0,
        "max_abs_cell": 20.0,
        "max_abs_column": 18.0,
    }
    with pytest.raises(ValueError, match="matching shapes"):
        budget._inventory_delta(before, after[:, :1], dry_mass)


def _row(i: int, j: int, substep: int, ground_q: float, residual_q: float,
         nlevels: int = 2) -> str:
    values = [0.0] * 12
    values[6] = ground_q
    values[10] = residual_q
    return "PR87_RAIN_SED {} {} {} {} {}".format(
        i, j, substep, nlevels, " ".join(str(value) for value in values))


def _rain_fixture(path: Path, *, duplicate_call: bool = False,
                  bad_nlevels: bool = False) -> dict:
    lines = [
        "PR87_RAIN_CALL 1 1 20.0",
        _row(1, 1, 1, 1.0, 0.1),
        _row(1, 1, 2, 2.0, 0.2),
        _row(2, 1, 1, 3.0, 0.3),
        "PR87_RAIN_CALL 1 1 20.0" if duplicate_call else "PR87_RAIN_CALL 1 2 20.0",
        _row(1, 2, 1, 4.0, 0.4, 3 if bad_nlevels else 2),
        _row(2, 2, 1, 5.0, 0.5),
        "PR87_RAIN_CALL 2 1 20.0",
        _row(1, 1, 1, 100.0, 10.0),
        "PR87_RAIN_CALL 2 2 20.0",
        _row(2, 2, 1, 200.0, 20.0),
    ]
    with gzip.open(path, "wt", encoding="ascii") as stream:
        stream.write("\n".join(lines) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"compressed_outputs": [{"compressed_path": path.name,
                                    "compressed_sha256": digest}]}


def test_rain_ledger_uses_first_step_and_maps_heterogeneous_substeps(tmp_path: Path) -> None:
    ledger = tmp_path / "pr87_rain_sedimentation_budget.raw.gz"
    receipt = _rain_fixture(ledger)
    area = np.array([[10.0, 20.0], [30.0, 40.0]])
    public_rain = np.array([[5.0, 1.0], [0.0, 2.0]])

    result, identity, difference = budget._rain_ground_comparison(
        tmp_path, receipt, {"jts": 1, "its": 1, "kte": 2, "kts": 1},
        area, public_rain)

    assert result["timestep"] == 1
    assert result["call_marker_rows"] == 2
    assert result["selected_sedimentation_rows"] == 5
    assert result["helper_ground_approved_rain_Q_kg"] == pytest.approx(410.0)
    assert result["captured_public_fall_phase1_rain_kg"] == pytest.approx(8.0)
    assert result["helper_minus_public_rain_difference_kg"]["signed"] == pytest.approx(402.0)
    assert result["helper_internal_column_residual_mapped_kg"] == pytest.approx(41.0)
    assert identity["sha256"] == receipt["compressed_outputs"][0]["compressed_sha256"]
    np.testing.assert_array_equal(difference, [[25.0, 59.0], [120.0, 198.0]])


def test_rain_ledger_rejects_duplicate_markers_and_bad_geometry(tmp_path: Path) -> None:
    area = np.ones((2, 2))
    public_rain = np.zeros((2, 2))
    bounds = {"jts": 1, "its": 1, "kte": 2, "kts": 1}
    for name, options, message in (
            ("duplicate.gz", {"duplicate_call": True}, "markers do not cover"),
            ("geometry.gz", {"bad_nlevels": True}, "invalid values or geometry")):
        ledger = tmp_path / name
        receipt = _rain_fixture(ledger, **options)
        receipt["compressed_outputs"][0]["compressed_path"] = "pr87_rain_sedimentation_budget.raw.gz"
        ledger.rename(tmp_path / "pr87_rain_sedimentation_budget.raw.gz")
        with pytest.raises(ValueError, match=message):
            budget._rain_ground_comparison(
                tmp_path, receipt, bounds, area, public_rain)
        (tmp_path / "pr87_rain_sedimentation_budget.raw.gz").unlink()


def test_rain_ledger_rejects_receipt_hash_mismatch(tmp_path: Path) -> None:
    ledger = tmp_path / "pr87_rain_sedimentation_budget.raw.gz"
    receipt = _rain_fixture(ledger)
    receipt["compressed_outputs"][0]["compressed_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="receipt hash mismatch"):
        budget._rain_ground_comparison(
            tmp_path, receipt, {"jts": 1, "its": 1, "kte": 2, "kts": 1},
            np.ones((2, 2)), np.zeros((2, 2)))


def test_column_map_archive_contains_only_hash_bound_2d_maps(tmp_path: Path) -> None:
    shape = (2, 3)
    sample = np.arange(6, dtype=np.float64).reshape(shape)
    identity = budget._save_column_maps(
        "OFF", {"its": 7, "jts": 11}, tmp_path, area=sample + 1.0,
        water_delta=sample, bottom_map=sample + 2.0,
        residual_before=sample + 3.0, residual_after=sample + 4.0,
        rain_difference=sample + 5.0, number_delta=sample + 6.0,
        bg_delta=sample + 7.0)

    archive_path = Path(identity["path"])
    assert identity["shape_j_i"] == list(shape)
    assert identity["sha256"] == budget.sha256(archive_path)
    assert identity["units"]["cell_area_m2"] == "m2"
    with np.load(archive_path) as archive:
        assert all(archive[name].ndim == 2 for name in archive.files)
        assert all(archive[name].shape == shape for name in archive.files)
        np.testing.assert_array_equal(archive["i_index"], [[7, 8, 9], [7, 8, 9]])
        np.testing.assert_array_equal(archive["j_index"], [[11, 11, 11], [12, 12, 12]])


def test_single_cutoff_sweep_requires_explicit_incomplete_window_mode(tmp_path: Path) -> None:
    cutoff = tmp_path / "pr85_kdm6_cutoff_budget.raw.gz"
    row_values = [1.0] + [0.0] * 24
    cutoff_rows = []
    for j in (1, 2):
        cutoff_rows.append(" ".join(["PR85_KDM6_CUTOFF", "1", str(j), "1", "1", "1",
                                     *(str(value) for value in row_values), "0", "0"]))
    with gzip.open(cutoff, "wt", encoding="ascii") as stream:
        stream.write("\n".join(cutoff_rows) + "\n")
    transition = tmp_path / "pr85_ice_transition_branch.raw.gz"
    with gzip.open(transition, "wt", encoding="ascii") as stream:
        stream.write("PR85_ICE_TRANSITION_LOOP 1 1 1 1 1 1 1\n")

    def binding(path: Path) -> dict:
        return {"compressed_path": path.name,
                "compressed_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    receipt = {"compressed_outputs": [binding(cutoff), binding(transition)]}
    pre = {"bounds": {"its": 1, "ite": 1, "jts": 1, "jte": 2,
                       "kts": 1, "kte": 1},
           "fields": {"DEN": np.ones((2, 1, 1))}}
    dry_mass = np.ones((2, 1, 1))

    with pytest.raises(ValueError, match="required complete ordered call sweep"):
        budget._recorded_numerical_terms(tmp_path, receipt, pre, dry_mass)

    summary, cutoff_map, transition_map, _ = budget._recorded_numerical_terms(
        tmp_path, receipt, pre, dry_mass, allow_single_cutoff_sweep=True)
    assert "only one complete sweep" in summary["cutoff_sweep_assignment"]
    assert summary["cutoff_rows_first_sweep"] == 2
    assert summary["cutoff_rows_second_sweep_geometry_mismatches"] == 0
    assert np.count_nonzero(cutoff_map) == 0
    assert np.count_nonzero(transition_map) == 0
