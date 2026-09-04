#!/usr/bin/env python3
"""Adversarial tests for diagnostic-patch input provenance."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from compare_operational_shadow import (  # noqa: E402
    AUTHORITATIVE_HOURS,
    DIAGNOSTIC_PATCH_VALID,
    archive_receipt,
    paths_overlap,
    plot_field_specs,
    require_independent_inputs,
    render_status,
    status_values,
    strict_root_path,
    validate_hours,
)


def expect_rejected(action, text: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert text in str(exc)
    else:
        raise AssertionError(f"expected rejection containing {text!r}")


def _run_provenance_tests() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-patch-provenance-") as directory:
        root = Path(directory)
        archive = root / "archive"
        live = root / "live"
        archive.mkdir()
        live.mkdir()
        original = archive / "product"
        current = live / "product"
        original.write_bytes(b"original")
        current.write_bytes(b"original")
        require_independent_inputs(original, current)
        assert not paths_overlap(archive, live)
        assert paths_overlap(root, archive)

        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        receipt = root / "SHA256SUMS"
        receipt.write_text(f"{digest}  archive/product\n", encoding="utf-8")
        found, found_digest = archive_receipt(original)
        assert found == receipt
        assert found_digest == hashlib.sha256(receipt.read_bytes()).hexdigest()

        expect_rejected(
            lambda: require_independent_inputs(original, original), "same file"
        )
        hardlink = live / "hardlink"
        os.link(original, hardlink)
        expect_rejected(
            lambda: require_independent_inputs(original, hardlink), "single-link"
        )
        symlink = live / "symlink"
        symlink.symlink_to(current)
        expect_rejected(
            lambda: require_independent_inputs(original, symlink), "symbolic links"
        )
        receipt.unlink()
        expect_rejected(lambda: archive_receipt(original), "pre-existing receipt")

    print("Operational diagnostic-patch provenance tests passed")


def test_provenance_guards() -> None:
    _run_provenance_tests()


def test_validate_hours_is_authoritative_and_fail_closed() -> None:
    assert validate_hours(AUTHORITATIVE_HOURS) == AUTHORITATIVE_HOURS
    assert validate_hours((12, 14), allow_partial=True) == (12, 14)

    expect_rejected(lambda: validate_hours((11, 12)), "unknown")
    expect_rejected(lambda: validate_hours((12, 12)), "duplicate")
    expect_rejected(lambda: validate_hours((13, 12)), "authoritative order")
    expect_rejected(
        lambda: validate_hours((12, 14)), "allow-partial-diagnostic"
    )
    expect_rejected(lambda: validate_hours(()), "at least one")
    expect_rejected(lambda: validate_hours((12, True)), "integers")


def test_plot_field_specs_are_single_fixed_level() -> None:
    specs = plot_field_specs()
    assert [item["plot_id"] for item in specs] == [
        "rain-550hpa", "snow-550hpa", "u-wind-550hpa",
    ]
    assert {item["level"] for item in specs} == {55000.0}
    assert [item["field"] for item in specs] == ["QR", "QS", "UU"]
    # Each call returns independent nested dictionaries suitable for sealing.
    specs[0]["scale"]["value_min"] = -1.0
    assert plot_field_specs()[0]["scale"]["value_min"] == 0.0
    expect_rejected(lambda: plot_field_specs(95000), "PLOT_LEVEL_PA")
    expect_rejected(lambda: plot_field_specs("55000"), "numeric")


def test_status_helpers_separate_execution_from_readiness() -> None:
    complete = status_values(AUTHORITATIVE_HOURS, True)
    assert complete["diagnostic_execution"] == "COMPLETE_DIAGNOSTIC"
    assert complete["authoritative_complete"] is True
    assert complete["diagnostic_exit"] == 0
    assert complete["comparison_readiness"] == "NOT_READY_MASS_BASIS_UNRESOLVED"
    assert complete["comparison_status"] == complete["comparison_readiness"]
    assert complete["available_artifact_validity"] == DIAGNOSTIC_PATCH_VALID
    assert complete["algorithm_comparison_ready"] is False
    assert complete["promotion_eligible"] is False
    text = render_status(complete)
    assert "diagnostic_execution=COMPLETE_DIAGNOSTIC\n" in text
    assert "diagnostic_exit=0\n" in text
    assert "comparison_readiness=NOT_READY_MASS_BASIS_UNRESOLVED\n" in text
    assert "comparison_status=NOT_READY_MASS_BASIS_UNRESOLVED\n" in text
    assert (
        "available_artifact_validity=DIAGNOSTIC_PATCH_VALID_NOT_COMPARABLE\n"
        in text
    )
    assert "algorithm_comparison_ready=false\n" in text
    assert "promotion_eligible=false\n" in text
    assert "comparison=" not in text

    partial = status_values((12, 14), True)
    assert partial["diagnostic_execution"] == "PARTIAL_DIAGNOSTIC"
    assert partial["diagnostic_exit"] == 3
    assert partial["authoritative_complete"] is False
    expect_rejected(
        lambda: render_status({**complete, "available_artifact_validity": "READY"}),
        "case inventory",
    )
    expect_rejected(
        lambda: render_status({**complete, "diagnostic_execution": "bad\nvalue"}),
        "single-line",
    )
    expect_rejected(
        lambda: render_status({**complete, "comparison_status": "READY",
                               "comparison_readiness": "READY"}),
        "case inventory",
    )
    expect_rejected(
        lambda: render_status({**complete, "diagnostic_execution": "bad\rvalue"}),
        "single-line",
    )
    expect_rejected(
        lambda: render_status({
            **complete,
            "comparison_readiness": "NOT_READY_\u2028INJECT=1",
            "comparison_status": "NOT_READY_\u2028INJECT=1",
        }),
        "single-line",
    )
    expect_rejected(
        lambda: render_status({**complete, "comparison_readiness": "NOT_READY_FAKE",
                               "comparison_status": "NOT_READY_FAKE"}),
        "case inventory",
    )
    impossible = status_values(AUTHORITATIVE_HOURS, True, available_pairs=False)
    assert impossible["diagnostic_execution"] == "INCOMPLETE_DIAGNOSTIC"
    assert impossible["diagnostic_exit"] == 3
    assert impossible["authoritative_complete"] is False


def test_invalid_hours_cli_returns_two_without_creating_output() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-invalid-hours-") as directory:
        root = Path(directory)
        output = root / "output"
        result = subprocess.run(
            [
                sys.executable, str(PROJECT / "tools/compare_operational_shadow.py"),
                "--original-root", str(root / "original"),
                "--live-root", str(root / "live"),
                "--shadow-root", str(root / "shadow"),
                "--output", str(output),
                "--source-commit", "0" * 40,
                "--hours", "12",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2
        assert "--allow-partial-diagnostic" in result.stderr
        assert not output.exists()


def test_compare_roots_reject_symlink_components_and_parent_traversal() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-root-path-") as directory:
        root = Path(directory)
        target = root / "target"
        target.mkdir()
        alias = root / "alias"
        alias.symlink_to(target, target_is_directory=True)

        expect_rejected(
            lambda: strict_root_path(alias, "original-root"), "symlink"
        )
        expect_rejected(
            lambda: strict_root_path(alias / ".." / "target", "original-root"),
            "parent traversal",
        )
        expect_rejected(
            lambda: strict_root_path(alias / "output", "output", must_exist=False),
            "symlink",
        )


def test_missing_partial_case_writes_non_ready_status_and_returns_three() -> None:
    from compare_operational_shadow import main as compare_main

    with tempfile.TemporaryDirectory(prefix="cloud-bal-empty-partial-") as directory:
        root = Path(directory)
        original = root / "original"
        live = root / "live"
        original.mkdir()
        live.mkdir()
        shadow_generation = root / "shadow-generation"
        shadow_generation.mkdir()
        shadow = root / "shadow"
        shadow.symlink_to(shadow_generation, target_is_directory=True)
        output = root / "output"
        argv = [
            "compare_operational_shadow.py",
            "--original-root", str(original),
            "--live-root", str(live),
            "--shadow-root", str(shadow),
            "--output", str(output),
            "--source-commit", "0" * 40,
            "--hours", "12",
            "--allow-partial-diagnostic",
        ]

        def git_output(command, **_kwargs):
            return "0" * 40 + "\n" if "rev-parse" in command else ""

        with mock.patch.object(sys, "argv", argv), \
                mock.patch("compare_operational_shadow.subprocess.check_output",
                           side_effect=git_output), \
                mock.patch("compare_operational_shadow.shadow_generation",
                           return_value=({}, "shadow-manifest-sha")):
            assert compare_main() == 3

        report = json.loads(
            (output / "comparison.json").read_text(encoding="utf-8")
        )
        assert report["diagnostic_exit"] == 3
        assert report["diagnostic_execution_status"] == "PARTIAL_DIAGNOSTIC"
        assert report["available_artifact_validity"] == "NO_DIAGNOSTIC_PATCH_AVAILABLE"
        assert report["algorithm_comparison_ready"] is False
        assert report["promotion_eligible"] is False
        status = (output / "STATUS.txt").read_text(encoding="utf-8")
        assert "diagnostic_exit=3\n" in status
        assert "comparison_status=NOT_READY_REQUESTED_CASES_INCOMPLETE\n" in status


def main() -> None:
    test_provenance_guards()
    test_validate_hours_is_authoritative_and_fail_closed()
    test_plot_field_specs_are_single_fixed_level()
    test_status_helpers_separate_execution_from_readiness()
    test_invalid_hours_cli_returns_two_without_creating_output()
    test_compare_roots_reject_symlink_components_and_parent_traversal()
    test_missing_partial_case_writes_non_ready_status_and_returns_three()


if __name__ == "__main__":
    main()
