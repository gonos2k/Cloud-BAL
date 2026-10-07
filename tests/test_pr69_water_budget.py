#!/usr/bin/env python3
"""Contract tests for the PR69 native-water checkpoint decoder."""
from __future__ import annotations

import struct
import sys
import tempfile
import hashlib
import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from pr67_kdm6_process_budget import CaptureError  # noqa: E402
from pr69_water_budget import (MAGIC, STAGES, audit_build_provenance,
                               audit_process_alignment, parse_water_capture)  # noqa: E402


def _row(*, bad_stage: int | None = None, invalid_bounds: bool = False,
         nonfinite_water: bool = False) -> bytes:
    records = bytearray()
    for stage, _name in enumerate(STAGES):
        records += MAGIC
        its, ite = (2, 1) if invalid_bounds and stage == 0 else (1, 1)
        records += struct.pack(">6i", bad_stage if stage == 2 and bad_stage is not None else stage,
                               7, its, ite, 1, 1)
        records += struct.pack(">2f", (20.0 if stage >= 2 else 0.0),
                              (1000.0 if stage >= 2 else 0.0))
        water = np.arange(1, 7, dtype=np.float64).reshape((1, 6)) + stage
        if nonfinite_water and stage == 1:
            water[0, 0] = np.inf
        fall = np.full((1, 4), stage - 1 if stage >= 2 else 0, dtype=np.float64)
        delz = np.array([100.0 if stage >= 2 else 0.0], dtype=np.float64)
        records += np.asarray(water, dtype=">f8").tobytes(order="F")
        records += np.asarray(fall, dtype=">f8").tobytes(order="F")
        records += np.asarray(delz, dtype=">f8").tobytes(order="F")
    return bytes(records)


def test_decodes_ordered_stages_and_fortran_columns() -> None:
    with tempfile.TemporaryDirectory() as directory:
        capture = Path(directory) / "capture.raw"
        capture.write_bytes(_row())
        records = parse_water_capture(capture)
    assert [record["stage"] for record in records] == list(range(5))
    assert records[0]["water_kg_m2"][:, 0].tolist() == [1., 2., 3., 4., 5., 6.]
    assert records[2]["bottom_fall_kg_m2_s"][:, 0].tolist() == [1., 1., 1., 1.]
    assert records[2]["bottom_delz_m"].tolist() == [100.]


def test_rejects_stage_reordering() -> None:
    with tempfile.TemporaryDirectory() as directory:
        capture = Path(directory) / "capture.raw"
        capture.write_bytes(_row(bad_stage=3))
        try:
            parse_water_capture(capture)
        except CaptureError as error:
            assert "expected stage 2" in str(error)
        else:
            raise AssertionError("stage reordering must fail closed")


def test_rejects_truncated_record() -> None:
    with tempfile.TemporaryDirectory() as directory:
        capture = Path(directory) / "capture.raw"
        capture.write_bytes(_row()[:-1])
        try:
            parse_water_capture(capture)
        except CaptureError as error:
            assert "truncated" in str(error) or "complete" in str(error)
        else:
            raise AssertionError("truncated record must fail closed")


def test_rejects_nonfinite_water_and_invalid_bounds() -> None:
    for kwargs, expected in (({"nonfinite_water": True}, "nonfinite"),
                             ({"invalid_bounds": True}, "bounds")):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "capture.raw"
            capture.write_bytes(_row(**kwargs))
            try:
                parse_water_capture(capture)
            except CaptureError as error:
                assert expected in str(error)
            else:
                raise AssertionError(f"invalid capture ({expected}) must fail closed")


def test_source_build_receipt_binding_rejects_executable_mismatch() -> None:
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        link = folder / "link_argv.json"
        link.write_text('{"argv":["ifx"]}\n')
        link_hash = hashlib.sha256(link.read_bytes()).hexdigest()
        receipt_path = folder / "run_receipt.json"
        receipt_path.write_text('{"receipt":"bound"}\n')
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        provenance = folder / "build.json"
        provenance.write_text(json.dumps({
            "observer_source_sha256": "a" * 64,
            "selected_source_sha256": "b" * 64,
            "member_matches_object": True,
            "object_sha256": "c" * 64,
            "archive_member_sha256": "c" * 64,
            "executable_sha256": "d" * 64,
            "link_argv_file": link.name,
            "link_argv_sha256": link_hash,
            "run_receipt_sha256": receipt_hash,
        }))
        receipt = {"executable": {"sha256_before": "d" * 64, "sha256_after": "d" * 64}}
        audit_build_provenance(provenance, "a" * 64, "b" * 64, receipt, "d" * 64, receipt_path)
        try:
            audit_build_provenance(provenance, "a" * 64, "b" * 64, receipt, "e" * 64, receipt_path)
        except CaptureError as error:
            assert "executable" in str(error)
        else:
            raise AssertionError("unmatched executable must fail provenance audit")
        try:
            audit_build_provenance(provenance, "a" * 64, "f" * 64, receipt, "d" * 64, receipt_path)
        except CaptureError as error:
            assert "selected source" in str(error)
        else:
            raise AssertionError("missing/wrong selected source identity must fail")
        receipt_path.write_text('{"receipt":"changed"}\n')
        try:
            audit_build_provenance(provenance, "a" * 64, "b" * 64, receipt, "d" * 64, receipt_path)
        except CaptureError as error:
            assert "receipt hash" in str(error)
        else:
            raise AssertionError("unmatched receipt hash must fail provenance audit")


def test_process_alignment_checks_stages_and_native_carrier() -> None:
    bounds = (1, 1, 1, 1)
    water_row = []
    for stage in range(5):
        water = np.zeros((6, 1), dtype=np.float64)
        if stage == 2:
            water[3, 0] = 0.5
        elif stage >= 3:
            water[3, 0] = 0.4
        water_row.append({"stage": stage, "j": 7, "dtcld": 20.,
                          "water_kg_m2": water,
                          "denr": 1000.,
                          "bottom_fall_kg_m2_s": np.full((4, 1), 0.25),
                          "bottom_delz_m": np.array([100.])})
    base = {"its": 1, "ite": 1, "kts": 1, "kte": 1,
            "lat": 7, "dtcld": 20.}
    process_row = [
        {**base, "stage": 0, "qice": np.array([[0.5]]),
         "density": np.array([[1.]]), "delz": np.array([[1.]])},
        {**base, "stage": 1, "qice": np.array([[0.4]])},
        {**base, "stage": 2, "denr": 1000., "fall": np.full((4, 1), 0.25),
         "delz": np.array([100.]), "density": np.array([1.])},
    ]
    result = audit_process_alignment([process_row], [water_row], bounds)
    assert result["status"] == "PASS" and result["rows"] == 1
    process_row[2]["lat"] = 8
    try:
        audit_process_alignment([process_row], [water_row], bounds)
    except CaptureError as error:
        assert "j" in str(error)
    else:
        raise AssertionError("misaligned process row must fail")


if __name__ == "__main__":
    test_decodes_ordered_stages_and_fortran_columns()
    test_rejects_stage_reordering()
    test_rejects_truncated_record()
    test_rejects_nonfinite_water_and_invalid_bounds()
    test_source_build_receipt_binding_rejects_executable_mismatch()
    test_process_alignment_checks_stages_and_native_carrier()
    print("PR69 native-water contract tests passed")
