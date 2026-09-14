#!/usr/bin/env python3
"""Focused tests for the manifest-bound derived COM/LCO evidence contract."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import netCDF4
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools/check_qbal_real_inputs.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("qbal_lco_checker", CHECKER_PATH)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)

LT1_PATH = Path(__file__).with_name("test_lt1_candidate.py")
LT1_SPEC = importlib.util.spec_from_file_location("lt1_lco_fixtures", LT1_PATH)
assert LT1_SPEC is not None and LT1_SPEC.loader is not None
LT1 = importlib.util.module_from_spec(LT1_SPEC)
LT1_SPEC.loader.exec_module(LT1)

LSX_PATH = Path(__file__).with_name("test_lsx_candidate.py")
LSX_SPEC = importlib.util.spec_from_file_location("lsx_lco_fixtures", LSX_PATH)
assert LSX_SPEC is not None and LSX_SPEC.loader is not None
LSX = importlib.util.module_from_spec(LSX_SPEC)
LSX_SPEC.loader.exec_module(LSX)


VALID_TIME = "2026-08-16T12:00:00Z"
REFERENCE_TIME = "2026-08-16T06:00:00Z"
LCO_NAME = "262281200.lco"
REAL_INDEX = REPO_ROOT / "scratch/cp02_final_logging_cases_n74wlcn1/case_index.json"
FILL = np.float32(1.0e37)
LEVELS = np.arange(50.0, 1100.1, 50.0, dtype=np.float32)
SHAPE = (1, 22, 283, 235)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_lco(
    path: Path,
    *,
    include_com: bool = True,
    valtime: str = VALID_TIME,
    reftime: str = VALID_TIME,
) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        LT1.write_common_dimensions(dataset, z=22)
        options = {"zlib": True, "complevel": 1, "fill_value": FILL}
        if include_com:
            com = dataset.createVariable(
                "com", "f4", ("record", "z", "y", "x"), **options
            )
            com.units = "Pascals / second"
            com.valid_range = np.asarray((-200.0, 200.0), dtype=np.float32)
            com.LAPS_var = "COM"
            com.LAPS_units = "PA/S"
            com.lvl_coord = "HPA"
            values = np.full(SHAPE, FILL, dtype=np.float32)
            values[:, 4:, 20:40, 20:40] = np.float32(-1.0)
            com[:] = values
            inventory = dataset.createVariable(
                "com_fcinv", "i2", ("record", "z"), fill_value=np.int16(0)
            )
            inventory[:] = np.int16(1)

        level = dataset.createVariable("level", "f4", ("z",))
        level.units = "hectopascals"
        level[:] = LEVELS
        for name, value in (
            ("imax", 235),
            ("jmax", 283),
            ("kmax", 22),
            ("kdim", 22),
        ):
            scalar = dataset.createVariable(name, "i4", ())
            scalar.assignValue(value)
        LT1.write_navigation(dataset)
        LT1.write_times(dataset, valtime, reftime)


def rows() -> list[dict[str, str]]:
    with (REPO_ROOT / "tests/qbal_real_cases_20260816.tsv").open(
        newline="", encoding="utf-8"
    ) as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_lco_content_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lco-content-") as directory:
        root = Path(directory)
        lco = root / LCO_NAME
        fsf = root / "reference.fsf"
        write_lco(lco)
        LT1.write_fsf(fsf, reftime=REFERENCE_TIME)

        before = (digest(lco), digest(fsf))
        result = CHECKER.inspect_lco_candidate(
            lco, fsf, VALID_TIME, REFERENCE_TIME
        )
        assert result["status"] == "PASS", result
        assert result["sparse_missing_allowed_above_ground"] is True
        assert result["above_ground_missing_cells"] > 0
        assert result["above_ground_active_cells"] > 0
        assert result["cloud_omega_authority"] == "EVIDENCE_ONLY"
        assert result["omega_target_authority"] == "NO_AUTHORITY"
        assert result["omega_target_sigma_provided"] is False
        assert result["dynamic_authority"] is False
        assert before == (digest(lco), digest(fsf))

        lsx = root / "262281200.lsx"
        LSX.write_lsx(lsx, valtime=VALID_TIME, reftime=VALID_TIME)
        analysis_result = CHECKER.inspect_lco_candidate(
            lco, fsf, VALID_TIME, REFERENCE_TIME, lsx
        )
        assert analysis_result["status"] == "PASS", analysis_result
        assert analysis_result["analysis_mask_reference"] == "LSX_PS_ANALYSIS"
        assert analysis_result["analysis_mask_reference_hash"] == digest(lsx)
        assert analysis_result["analysis_above_ground_active_cells"] > 0

        variants: list[tuple[str, object]] = [
            ("bad_units", lambda ds: setattr(ds.variables["com"], "units", "percent")),
            (
                "stale_valtime",
                lambda ds: ds.variables["valtime"].__setitem__(
                    0, LT1._epoch("2026-08-16T13:00:00Z")
                ),
            ),
            (
                "reversed_pressure",
                lambda ds: ds.variables["level"].__setitem__(slice(None), LEVELS[::-1]),
            ),
            (
                "wrong_navigation",
                lambda ds: ds.variables["Nx"].__setitem__(0, np.int16(234)),
            ),
            (
                "unmasked_nan",
                lambda ds: _set_raw(ds.variables["com"], np.float32(np.nan)),
            ),
        ]
        for label, mutate in variants:
            candidate = root / f"{label}.lco"
            shutil.copy2(lco, candidate)
            with netCDF4.Dataset(candidate, "r+") as dataset:
                mutate(dataset)
            result = CHECKER.inspect_lco_candidate(
                candidate, fsf, VALID_TIME, REFERENCE_TIME
            )
            assert result["status"] == "FAIL", (label, result)

        missing_com = root / "missing_com.lco"
        write_lco(missing_com, include_com=False)
        result = CHECKER.inspect_lco_candidate(
            missing_com, fsf, VALID_TIME, REFERENCE_TIME
        )
        assert result["status"] == "FAIL", result


def _set_raw(variable: netCDF4.Variable, value: np.float32) -> None:
    variable.set_auto_maskandscale(False)
    variable[0, 4, 20, 20] = value


def run_final_four_lco_lineage_and_forged_receipt(
    index_path: Path | None = None,
) -> None:
    index = Path(index_path) if index_path is not None else REAL_INDEX
    assert index.is_file(), f"final four-case index is missing: {index}"
    result = CHECKER.validate_lco_evidence(
        index,
        REPO_ROOT.parent,
        rows(),
        CHECKER.LCO_EVIDENCE_INDEX_SHA256,
    )
    assert result["status"] == "PASS", result
    assert len(result["cases"]) == 4
    assert all(item["status"] == "PASS" for item in result["cases"])
    assert all(
        item["cloud_omega_authority"] == "EVIDENCE_ONLY"
        and item["omega_target_authority"] == "NO_AUTHORITY"
        and item["omega_target_sigma_provided"] is False
        and item["dynamic_authority"] is False
        and item["analysis_mask_reference"] == "LSX_PS_ANALYSIS"
        and item["analysis_mask_reference_hash"] == item["lsx_sha256"]
        and item["analysis_above_ground_active_cells"] > 0
        for item in result["cases"]
    )

    document = json.loads(index.read_text(encoding="utf-8"))
    forged = copy.deepcopy(document)
    lco = next(
        item for item in forged[0]["netcdf_products"] if item["role"] == "lco"
    )
    lco["sha256"] = "0" * 64
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lco-lineage-") as directory:
        forged_index = Path(directory) / "case_index.json"
        forged_index.write_text(json.dumps(forged) + "\n", encoding="utf-8")
        forged_result = CHECKER.validate_lco_evidence(
            forged_index,
            REPO_ROOT.parent,
            rows(),
            digest(forged_index),
        )
        assert forged_result["status"] == "FAIL", forged_result
        assert any(
            "indexed LCO SHA-256 does not match final output bytes" in item
            for item in forged_result["cases"][0]["findings"]
        )

    # The accepted index hash must bind the bytes parsed for identity.  This
    # sabotage mutates only a temporary copy if an implementation reopens the
    # index path after hashing; the detached-byte implementation never calls
    # _read_json_file for the index.
    with tempfile.TemporaryDirectory(prefix="cloud-bal-lco-index-snapshot-") as directory:
        snapshot_index = Path(directory) / "case_index.json"
        shutil.copy2(index, snapshot_index)
        original_reader = CHECKER._read_json_file

        def replace_index(path: Path) -> tuple[object | None, str | None]:
            if Path(path).absolute() == snapshot_index.absolute():
                mutated = json.loads(snapshot_index.read_text(encoding="utf-8"))
                mutated[0]["hour"] = 99
                snapshot_index.write_text(
                    json.dumps(mutated) + "\n", encoding="utf-8"
                )
            return original_reader(path)

        CHECKER._read_json_file = replace_index
        try:
            snapshot_result = CHECKER.validate_lco_evidence(
                snapshot_index,
                REPO_ROOT.parent,
                rows(),
                digest(snapshot_index),
            )
        finally:
            CHECKER._read_json_file = original_reader
        assert snapshot_result["status"] == "PASS", snapshot_result

    # Content validation must consume detached LCO/FSF/LSX snapshots directly;
    # calling the old path-based helper would leave a replacement-before-open
    # race and is therefore an adversarial failure.
    document = json.loads(index.read_text(encoding="utf-8"))
    original_inspector = CHECKER.inspect_lco_candidate

    def forbidden_path_inspection(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("path-based LCO inspection was reopened")

    CHECKER.inspect_lco_candidate = forbidden_path_inspection
    try:
        direct_case = CHECKER._validate_lco_case(
            document[0], rows()[0], REPO_ROOT.parent, []
        )
    finally:
        CHECKER.inspect_lco_candidate = original_inspector
    assert direct_case["status"] == "PASS", direct_case


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real-evidence",
        action="store_true",
        help="run the retained four-case evidence test explicitly",
    )
    parser.add_argument(
        "--real-evidence-index",
        type=Path,
        help="run retained evidence using this explicitly supplied index",
    )
    args = parser.parse_args()
    test_lco_content_contract()
    if args.real_evidence or args.real_evidence_index is not None:
        run_final_four_lco_lineage_and_forged_receipt(args.real_evidence_index)
        print("LCO content and explicit four-case lineage tests passed")
    else:
        print("LCO portable content tests passed; retained evidence test skipped")


if __name__ == "__main__":
    raise SystemExit(main())
