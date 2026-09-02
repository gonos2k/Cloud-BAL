#!/usr/bin/env python3
"""Tests for the fail-closed original pre-QBAL receipt parser."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import check_qbal_real_inputs as checker  # noqa: E402


def make_manifest() -> dict[str, object]:
    cases = []
    for case_id, valid_time, stamp in checker.EXPECTED_CASES:
        products = {}
        for kind in checker.PRE_QBAL_PRODUCTS:
            stage, executable = checker.PRE_QBAL_PRODUCERS[kind]
            products[kind] = {
                "path": f"{kind}/{stamp}.{kind}",
                "sha256": "4" * 64,
                "source_class": "pre_qbal_intermediate",
                "valid_time_utc": valid_time,
                "producer_stage": stage,
                "producer_executable": executable,
            }
        cases.append(
            {
                "case_id": case_id,
                "valid_time_utc": valid_time,
                "laps_stamp": stamp,
                "status": "COMPLETE",
                "input_closure_sha256": "3" * 64,
                "products": products,
            }
        )
    return {
        "contract": checker.PRE_QBAL_MANIFEST_CONTRACT,
        "authority": "original_klaps_source",
        "source_tree": "klaps-v5.0_",
        "source_tree_sha256": "1" * 64,
        "configuration_sha256": "2" * 64,
        "compiler_family": "Intel",
        "generation_status": "COMPLETE",
        "cases": cases,
    }


def write_manifest(root: Path, document: dict[str, object]) -> str:
    path = root / checker.PRE_QBAL_MANIFEST_NAME
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    return checker.sha256(path)


def test_pre_qbal_generation_manifest_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-pre-qbal-") as directory:
        root = Path(directory)
        complete = make_manifest()

        context = checker.load_pre_qbal_manifest(
            root, write_manifest(root, complete)
        )
        assert context["status"] == "FAIL"
        assert any(
            "COMPLETE generation receipts are unsupported" in item
            for item in context["findings"]
        )

        actual_root = root / "actual-generation"
        actual_root.mkdir()
        manifest_hash = write_manifest(actual_root, complete)
        alias_root = root / "generation-alias"
        alias_root.symlink_to(actual_root, target_is_directory=True)
        context = checker.load_pre_qbal_manifest(alias_root, manifest_hash)
        assert context["status"] == "FAIL"
        assert "no symlink components" in context["findings"][0]

        blocked = copy.deepcopy(complete)
        blocked["generation_status"] = "BLOCKED"
        for case in blocked["cases"]:
            case["status"] = "BLOCKED"
            case["input_closure_sha256"] = None
            for product in case["products"].values():
                product.update(status="NOT_PRODUCED", sha256=None)
        context = checker.load_pre_qbal_manifest(
            root, write_manifest(root, blocked)
        )
        assert context["status"] == "BLOCKED"

        missing = copy.deepcopy(complete)
        del missing["cases"][0]["products"]["lco"]
        context = checker.load_pre_qbal_manifest(root, write_manifest(root, missing))
        assert context["status"] == "FAIL"
        assert any("products must be exactly" in item for item in context["findings"])

        manifest_hash = write_manifest(root, complete)
        manifest_path = root / checker.PRE_QBAL_MANIFEST_NAME
        manifest_path.write_text("{}\n", encoding="utf-8")
        context = checker.load_pre_qbal_manifest(root, manifest_hash)
        assert context["status"] == "FAIL"
        assert context["findings"] == ["generation manifest SHA-256 mismatch"]

        forbidden = copy.deepcopy(complete)
        forbidden["cases"][0]["products"]["lco"][
            "producer_executable"
        ] = "klps_anal_qbal.exe"
        context = checker.load_pre_qbal_manifest(
            root, write_manifest(root, forbidden)
        )
        assert context["status"] == "FAIL"
        assert any("producer_executable" in item for item in context["findings"])

        forbidden = copy.deepcopy(complete)
        forbidden["cases"][0]["products"]["lw3"][
            "path"
        ] = "balance/lw3/262281200.lw3"
        context = checker.load_pre_qbal_manifest(
            root, write_manifest(root, forbidden)
        )
        assert context["status"] == "FAIL"
        assert any("downstream/final product path" in item for item in context["findings"])

        for path in (
            "/isolated/bigfile/input.nc",
            "/isolated/LAPS:final/lt1/file",
            "/isolated/KLBG:final/lsx/file",
            "/isolated/met_em.d01.nc",
            "/isolated/lapsprep/wps/file",
        ):
            assert checker.forbidden_reason(Path(path)) is not None


def main() -> None:
    test_pre_qbal_generation_manifest_contract()
    print("Pre-QBAL receipt parser tests passed")


if __name__ == "__main__":
    main()
