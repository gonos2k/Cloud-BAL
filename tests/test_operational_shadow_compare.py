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
    FULL_SCOPE,
    P1_EXCLUDED_UTC_HOURS,
    P1_EXCLUSION_STATUS,
    P1_EXCLUSION_PROVENANCE,
    P1_EXCLUSION_REASON,
    P1_OPERATIONAL_HOURS,
    P1_OPERATIONAL_SCOPE,
    archive_receipt,
    paths_overlap,
    plot_field_specs,
    require_independent_inputs,
    render_status,
    scope_exclusions,
    status_values,
    strict_root_path,
    validate_scope_inventory,
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


def test_p1_operational_scope_excludes_12_and_has_its_own_authority() -> None:
    assert P1_OPERATIONAL_HOURS == (13, 14, 15)
    assert validate_hours(
        P1_OPERATIONAL_HOURS, scope=P1_OPERATIONAL_SCOPE
    ) == P1_OPERATIONAL_HOURS
    expect_rejected(
        lambda: validate_hours(
            (12, 13, 14, 15), allow_partial=True, scope=P1_OPERATIONAL_SCOPE
        ),
        "12 UTC",
    )
    expect_rejected(
        lambda: validate_hours((13, 13), scope=P1_OPERATIONAL_SCOPE),
        "duplicate",
    )
    expect_rejected(
        lambda: validate_hours((14, 13), scope=P1_OPERATIONAL_SCOPE),
        "authoritative order",
    )
    expect_rejected(
        lambda: validate_hours((16,), scope=P1_OPERATIONAL_SCOPE),
        "unknown",
    )
    expect_rejected(
        lambda: validate_hours((13, 14), scope=P1_OPERATIONAL_SCOPE),
        "allow-partial-diagnostic",
    )

    complete = status_values(
        P1_OPERATIONAL_HOURS, True, scope=P1_OPERATIONAL_SCOPE
    )
    assert complete["comparison_scope"] == P1_OPERATIONAL_SCOPE
    assert complete["authoritative_hours"] == list(P1_OPERATIONAL_HOURS)
    assert complete["excluded_utc_hours"] == list(P1_EXCLUDED_UTC_HOURS)
    assert complete["excluded_utc_status"] == P1_EXCLUSION_STATUS
    assert complete["excluded_utc_reason"] == P1_EXCLUSION_REASON
    assert complete["excluded_utc_provenance"] == P1_EXCLUSION_PROVENANCE
    assert scope_exclusions(P1_OPERATIONAL_SCOPE) == [{
        "case_id": "20260816T120000Z",
        "valid_time": "2026-08-16T12:00:00Z",
        "status": P1_EXCLUSION_STATUS,
        "reason": P1_EXCLUSION_REASON,
        "provenance": P1_EXCLUSION_PROVENANCE,
    }]
    assert complete["diagnostic_execution"] == "COMPLETE_DIAGNOSTIC"
    assert complete["diagnostic_exit"] == 0
    assert complete["authoritative_complete"] is True
    assert complete["comparison_status"] == "NOT_READY_MASS_BASIS_UNRESOLVED"
    assert complete["algorithm_comparison_ready"] is False
    assert complete["promotion_eligible"] is False
    status = render_status(complete)
    assert "comparison_scope=p1-operational\n" in status
    assert "scope_hours=13,14,15\n" in status
    assert "excluded_utc_hours=12\n" in status
    assert f"excluded_utc_reason={P1_EXCLUSION_REASON}\n" in status
    assert f"excluded_utc_status={P1_EXCLUSION_STATUS}\n" in status
    assert f"excluded_utc_provenance={P1_EXCLUSION_PROVENANCE}\n" in status

    partial = status_values((13, 14), True, scope=P1_OPERATIONAL_SCOPE)
    assert partial["diagnostic_execution"] == "PARTIAL_DIAGNOSTIC"
    assert partial["diagnostic_exit"] == 3
    assert partial["comparison_status"] == (
        "NOT_READY_REQUESTED_CASES_INCOMPLETE"
    )

    # The original full replay remains unchanged and includes 12 UTC.
    full = status_values(AUTHORITATIVE_HOURS, True, scope=FULL_SCOPE)
    assert full["authoritative_hours"] == list(AUTHORITATIVE_HOURS)
    assert full["excluded_utc_hours"] == []


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
    assert partial["comparison_status"] == (
        "NOT_READY_REQUESTED_CASES_INCOMPLETE"
    )
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


def test_p1_scope_rejects_12_cli_without_creating_output() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-invalid-p1-hours-") as directory:
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
                "--scope", P1_OPERATIONAL_SCOPE,
                "--hours", "12", "13", "14", "15",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2
        assert "12 UTC" in result.stderr
        assert not output.exists()


def test_p1_scope_rejects_stale_missing_inventory_claim() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-p1-inventory-") as directory:
        root = Path(directory)
        original = root / "original"
        live = root / "live"
        original.mkdir()
        live.mkdir()
        validate_scope_inventory(original, live, P1_OPERATIONAL_SCOPE)

        excluded = (
            original / "2026081612" / "LAPS:2026-08-16_12:00"
        )
        excluded.parent.mkdir()
        excluded.write_bytes(b"newly available")
        expect_rejected(
            lambda: validate_scope_inventory(
                original, live, P1_OPERATIONAL_SCOPE
            ),
            "cannot remain excluded",
        )


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


def test_p1_report_and_status_seal_12_utc_exclusion_provenance() -> None:
    from compare_operational_shadow import main as compare_main

    with tempfile.TemporaryDirectory(prefix="cloud-bal-p1-provenance-") as directory:
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
            "--scope", P1_OPERATIONAL_SCOPE,
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
        manifest = json.loads(
            (output / "comparison-manifest.json").read_text(encoding="utf-8")
        )
        scope_manifest = json.loads(
            (output / "scope-manifest.json").read_text(encoding="utf-8")
        )
        assert report["comparison_scope"] == P1_OPERATIONAL_SCOPE
        assert report["scope_hours"] == list(P1_OPERATIONAL_HOURS)
        assert report["excluded_utc_hours"] == [12]
        assert report["excluded_utc_status"] == P1_EXCLUSION_STATUS
        assert report["excluded_utc_reason"] == P1_EXCLUSION_REASON
        assert report["excluded_utc_provenance"] == P1_EXCLUSION_PROVENANCE
        assert report["scope_exclusions"] == scope_exclusions(
            P1_OPERATIONAL_SCOPE
        )
        assert set(manifest) == {"schema_version", "comparison_id", "pairs"}
        assert manifest["comparison_id"].startswith(
            "operational-shadow-p1-operational-"
        )
        assert scope_manifest["comparison_id"] == manifest["comparison_id"]
        assert scope_manifest["comparison_scope"] == P1_OPERATIONAL_SCOPE
        assert scope_manifest["scope_hours"] == list(P1_OPERATIONAL_HOURS)
        assert scope_manifest["source_commit"] == "0" * 40
        assert scope_manifest["comparison_tool_sha256"] == report[
            "comparison_tool_sha256"
        ]
        assert scope_manifest["shadow_generation_manifest_sha256"] == (
            "shadow-manifest-sha"
        )
        assert scope_manifest["comparison_manifest_sha256"] == hashlib.sha256(
            (output / "comparison-manifest.json").read_bytes()
        ).hexdigest()
        assert scope_manifest["scope_exclusions"] == scope_exclusions(
            P1_OPERATIONAL_SCOPE
        )
        status = (output / "STATUS.txt").read_text(encoding="utf-8")
        assert "comparison_scope=p1-operational\n" in status
        assert "excluded_utc_hours=12\n" in status
        assert f"excluded_utc_status={P1_EXCLUSION_STATUS}\n" in status
        assert f"excluded_utc_reason={P1_EXCLUSION_REASON}\n" in status
        assert f"excluded_utc_provenance={P1_EXCLUSION_PROVENANCE}\n" in status
        assert "algorithm_comparison_ready=false\n" in status
        assert "promotion_eligible=false\n" in status
        assert "mass_basis_gate=BLOCKED_UNRESOLVED\n" in status


def main() -> None:
    test_provenance_guards()
    test_validate_hours_is_authoritative_and_fail_closed()
    test_p1_operational_scope_excludes_12_and_has_its_own_authority()
    test_plot_field_specs_are_single_fixed_level()
    test_status_helpers_separate_execution_from_readiness()
    test_invalid_hours_cli_returns_two_without_creating_output()
    test_p1_scope_rejects_12_cli_without_creating_output()
    test_p1_scope_rejects_stale_missing_inventory_claim()
    test_compare_roots_reject_symlink_components_and_parent_traversal()
    test_missing_partial_case_writes_non_ready_status_and_returns_three()
    test_p1_report_and_status_seal_12_utc_exclusion_provenance()


if __name__ == "__main__":
    main()
