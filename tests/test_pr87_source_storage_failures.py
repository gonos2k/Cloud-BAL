"""Focused tests for the retained PR87 source-storage diagnostic parser."""
from __future__ import annotations

import gzip
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr87_source_storage_failures as audit  # noqa: E402


def test_list_directed_source_record_can_wrap_and_preserves_count(tmp_path):
    ledger = tmp_path / "source.raw.gz"
    with gzip.open(ledger, "wt") as stream:
        stream.write(
            " SOURCE 1 1 216 2 16\n"
            " 94309.77 94264.38 0.0 0.0 1.1462621E-42\n"
            " 9.6782889E-31 8.106718411126022E-47 6.844783533007300E-35\n"
            " 0.0 6.8447836E-35 0.7694050\n"
            " SOURCE_FAILURE_COUNT 1\n"
        )

    rows, declared, markers = audit.read_source_rows(ledger)

    assert declared == 1
    assert markers == {}
    assert len(rows) == 1
    assert audit.classify_row(rows[0])["classification"] == "q_underflow_pair_loss"


def test_positive_real32_pair_ratio_exception_stays_distinct_from_underflow():
    row = [1.0, 1.0, 164.0, 135.0, 10.0, 95000.0, 95000.0,
           0.0, 0.0, 0.0, 0.0,
           2.48244613949798808e-41, 5.92636478401649534e-27,
           2.4824002e-41, 5.9263649e-27, 0.9615738]

    result = audit.classify_row(row)

    assert result["continuous_valid_with_coded_8ulp_tolerance"]
    assert result["continuous_exact_pair_bounds"]
    assert result["real32_q_logged"] > 0.0
    assert result["real32_n_logged"] > 0.0
    assert result["classification"] == "stored_below_min_ratio"


def test_full_candidate_record_classifies_continuous_and_storage_gates(tmp_path):
    ledger = tmp_path / "full.raw.gz"
    # Values follow the native FULL record: identifiers, old/new carrier,
    # base/source/transport pairs, REAL64 candidate, stored sentinels, density, dt.
    with gzip.open(ledger, "wt") as stream:
        stream.write(
            " FULL 2 3 1 71 32 6 94698.82 94806.12\n"
            " 6.9814268E-7 1.6666926E8 -3.9944612E-6 -9.5285613E8\n"
            " -1.6415092E-5 -3.9188137E9 6.930470266511906E-7\n"
            " 165452923.840876 -1.0 -1.0 1.152048 6.6666667\n"
            " FULL_FAILURE_COUNT 1\n"
        )

    rows, count = audit.read_full_rows(ledger)
    result = audit.classify_full_row(rows[0])

    assert count == 1
    assert result["continuous_valid_with_coded_8ulp_tolerance"]
    assert not result["independently_rounded_valid_with_coded_8ulp_tolerance"]
    assert result["classification"] == "continuous_valid_real32_rounding_crosses_gate"
    assert result["logged_full_stored_q"] == -1.0


def test_full_candidate_continuous_gate_is_not_repaired_by_rounding():
    # One retained v3 row has a continuous ratio below the exact tolerance while
    # independent binary32 rounding lands inside it; the native store rejects it
    # at its earlier continuous gate.
    row = [2.0, 3.0, 1.0, 167.0, 120.0, 5.0,
           87227.73, 87308.45, 4.7907124e-6, 1.1436982e9,
           -2.0010560e-4, -4.7767085e10, -1.0253732e-3, -2.4478977e11,
           4.505559299949756e-6, 1075623953.84519, -1.0, -1.0, 1.095296, 6.6666667]

    result = audit.classify_full_row(row)

    assert not result["continuous_valid_with_coded_8ulp_tolerance"]
    assert result["independently_rounded_valid_with_coded_8ulp_tolerance"]
    assert result["classification"] == "continuous_candidate_outside_coded_8ulp_gate"
