from __future__ import annotations

import hashlib
import json
import sys
import gzip
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_source_representation import summarize_file, summarize_source_representation  # noqa: E402


FIXTURE = """ SOURCE_REPRESENTATION_META           1           3
 pressure carrier amounts: original dt*S, represented W*(stage-old), delta, L1_delta, max_abs_delta; Q,N
 SOURCE_COLUMN           1           3           1           2           2
           1           1           1 -6.118037276792165E-006
  -1459772000.00000      -6.117885393064348E-006  -1459810673.94531
  1.518837278169372E-010  -38673.9453125000       1.518837278169372E-010
   38673.9453125000       1.518837278169372E-010   38673.9453125000
 SOURCE_COLUMN           1           3           1           3           2
           1           1           1 -6.118037276792165E-006
  -1459772000.00000      -6.117885393064348E-006  -1459810673.94531
  1.518837278169372E-010  -38673.9453125000       1.518837278169372E-010
   38673.9453125000       1.518837278169372E-010   38673.9453125000
 SOURCE_TOTAL           1           3           1           2           2
 -1.223607455358433E-005  -2919544000.00000      -1.223577078612870E-005
  -2919621347.89062       3.037674556338743E-010  -77347.8906250000
   3.037674556338743E-010   77347.8906250000       1.518837278169372E-010
   38673.9453125000
"""


def test_summarizes_wrapped_records_and_binds_source_hash(tmp_path: Path) -> None:
    ledger = tmp_path / "pr87_source_representation.raw"
    ledger.write_text(FIXTURE, encoding="utf-8")
    summary = summarize_file(ledger)

    assert summary["status"] == "PASS"
    assert summary["source_ledger_sha256"] == hashlib.sha256(FIXTURE.encode()).hexdigest()
    assert summary["physical_mass_or_energy_claim"] is False
    assert summary["quantity_basis"] == "pressure_carrier_amounts"
    group = summary["groups"][0]
    assert (group["timestep"], group["rk"], group["pair"]) == (1, 3, 1)
    assert group["cells"] == 2
    assert group["changed_cells"] == 2
    assert group["signed_delta"] == pytest.approx([3.037674556338743e-10, -77347.890625])
    assert group["l1_delta"] == pytest.approx([3.037674556338743e-10, 77347.890625])
    assert group["max_abs_delta"] == pytest.approx([1.518837278169372e-10, 38673.9453125])
    assert "kg" not in json.dumps(summary).lower()


def test_supports_gzip_and_records_both_hashes(tmp_path: Path) -> None:
    ledger = tmp_path / "pr87_source_representation.raw.gz"
    compressed = gzip.compress(FIXTURE.encode())
    ledger.write_bytes(compressed)
    summary = summarize_file(ledger)
    assert summary["source_ledger_is_gzip"] is True
    assert summary["source_ledger_sha256"] == hashlib.sha256(compressed).hexdigest()
    assert summary["source_ledger_decoded_sha256"] == hashlib.sha256(FIXTURE.encode()).hexdigest()


def test_parses_optional_later_source_record_without_aggregation_claim() -> None:
    later = "SOURCE_LATER_TOTAL 1 3 1 4.0E-6 -2.0E+3 1.0E-20 2.0E-14\n"
    summary = summarize_source_representation(FIXTURE + later)
    group = summary["groups"][0]
    assert group["later_source"]["dt_later_source_amount"] == [4.0e-6, -2.0e3]
    assert group["later_source"]["max_abs_r64_identity_residual"] == [1.0e-20, 2.0e-14]
    assert group["later_source"]["aggregation_claim"] is False
    assert summary["later_source_amounts_are_separately_reported_not_aggregated"] is True


def test_rejects_duplicate_or_unmatched_later_source_record() -> None:
    later = "SOURCE_LATER_TOTAL 1 3 1 4.0E-6 -2.0E+3 1.0E-20 2.0E-14\n"
    with pytest.raises(ValueError, match="duplicate SOURCE_LATER_TOTAL"):
        summarize_source_representation(FIXTURE + later + later)
    with pytest.raises(ValueError, match="SOURCE_LATER_TOTAL groups lack source totals"):
        summarize_source_representation(FIXTURE + later.replace(" 1 4.0E-6", " 2 4.0E-6"))


def test_rejects_metadata_scope_without_a_completed_total() -> None:
    truncated_after_meta = FIXTURE + "SOURCE_REPRESENTATION_META 2 3 'trailing incomplete scope'\n"
    with pytest.raises(ValueError, match="metadata scopes do not match completed total scopes"):
        summarize_source_representation(truncated_after_meta)


def test_accepts_equal_nonzero_source_amounts_from_omitted_unchanged_columns() -> None:
    old_total = (
        "-1.223607455358433E-005  -2919544000.00000      -1.223577078612870E-005\n"
        "  -2919621347.89062"
    )
    total_with_omitted_column = (
        "1.249877639254464E-001  -2919544002.50000      1.249877642292139E-001\n"
        "  -2919621350.39062"
    )
    fixture = FIXTURE.replace(old_total, total_with_omitted_column)
    summary = summarize_source_representation(fixture)
    group = summary["groups"][0]
    assert group["column_rows"] == 2
    assert group["unreported_amounts_equal_within_roundoff"] is True
    assert group["unreported_equal_source_amount"] == pytest.approx([0.125, -2.5])


def test_uses_operand_scale_for_large_cancelling_amounts_with_small_delta() -> None:
    fixture = """SOURCE_REPRESENTATION_META 9 3 'pressure carrier amounts'
SOURCE_COLUMN 9 3 1 4 6 1 2 2 1.0E+16 0.0 1.0E+16 0.0 1.0 0.0 1.0 0.0 1.0 0.0
SOURCE_TOTAL 9 3 1 1 1 1.0E+16 0.0 1.0E+16 0.0 1.0 0.0 1.0 0.0 1.0 0.0
"""
    group = summarize_source_representation(fixture)["groups"][0]
    assert group["signed_delta"] == [1.0, 0.0]
    assert group["invariants_verified"] is True


def test_rejects_column_with_wrong_timestep_or_pair_identity() -> None:
    wrong_step = FIXTURE.replace("SOURCE_COLUMN           1           3           1           2", 
                                 "SOURCE_COLUMN           2           3           1           2", 1)
    with pytest.raises(ValueError, match="lack totals|does not match metadata"):
        summarize_source_representation(wrong_step)

    wrong_pair = FIXTURE.replace("SOURCE_COLUMN           1           3           1           2", 
                                  "SOURCE_COLUMN           1           3           2           2", 1)
    with pytest.raises(ValueError, match="lack totals|does not match metadata"):
        summarize_source_representation(wrong_pair)


def test_rejects_duplicate_totals() -> None:
    total = FIXTURE[FIXTURE.index(" SOURCE_TOTAL"):]
    with pytest.raises(ValueError, match="duplicate SOURCE_TOTAL"):
        summarize_source_representation(FIXTURE + total)


def test_rejects_inconsistent_aggregate_and_nonfinite_values() -> None:
    bad_total = FIXTURE.replace("3.037674556338743E-010  -77347.8906250000",
                                "4.037674556338743E-010  -77347.8906250000")
    with pytest.raises(ValueError):
        summarize_source_representation(bad_total)

    nonfinite = FIXTURE.replace("1.518837278169372E-010", "NaN", 1)
    with pytest.raises(ValueError, match="nonfinite"):
        summarize_source_representation(nonfinite)
