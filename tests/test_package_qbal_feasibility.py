#!/usr/bin/env python3
"""Focused contract tests for the portable Q-BAL receiver bundle packager."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_qbal_feasibility import BundleError, package_bundle, sha256_file  # noqa: E402


REQUIRED = (
    "scripts/replay_receivers.sh",
    "candidates/bounded_candidate.npz",
    "hypothetical_faces/hypothetical.json",
    "receivers/receivers.json",
    "inputs/before.npz",
    "outputs/after.npz",
)


def write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def make_spec(root: Path) -> tuple[Path, dict[str, dict[str, str]]]:
    spec: dict[str, dict[str, str]] = {}
    for destination in REQUIRED:
        source = write(root / "history" / destination, destination.encode() + b"\n")
        spec[destination] = {"source": str(source), "sha256": sha256_file(source)}
    path = write(root / "spec.json", json.dumps(spec, indent=2).encode() + b"\n")
    return path, spec


def test_bundle_records_required_artifacts_and_hashes() -> None:
    with tempfile.TemporaryDirectory(prefix="qbal-packager-") as directory:
        root = Path(directory)
        specification, expected = make_spec(root)
        manifest = package_bundle(root / "bundle", specification)

        assert manifest["schema"] == "qbal-feasibility-reproduction-v1"
        assert manifest["candidate_regeneration_claim"] is False
        assert set(manifest["artifacts"]) == set(REQUIRED)
        for destination, details in expected.items():
            actual = manifest["artifacts"][destination]
            assert actual["source"] == str(Path(details["source"]).resolve())
            assert actual["sha256"] == details["sha256"]
            assert sha256_file(root / "bundle" / destination) == details["sha256"]
        assert json.loads((root / "bundle" / "manifest.json").read_text()) == manifest
        readme = (root / "bundle" / "README.md").read_text(encoding="utf-8")
        assert "hard-coded paths" in readme
        assert "./scripts/replay_receivers.sh" in readme
        assert "does not regenerate the" in readme


def test_hash_mismatch_fails_before_bundle_is_created() -> None:
    with tempfile.TemporaryDirectory(prefix="qbal-packager-mismatch-") as directory:
        root = Path(directory)
        specification, spec = make_spec(root)
        spec["candidates/bounded_candidate.npz"]["sha256"] = "0" * 64
        specification.write_text(json.dumps(spec) + "\n", encoding="utf-8")
        try:
            package_bundle(root / "bundle", specification)
        except BundleError as error:
            assert "SHA-256 mismatch" in str(error)
        else:
            raise AssertionError("hash mismatch unexpectedly packaged")
        assert not (root / "bundle").exists()


def test_malformed_spec_and_existing_destination_are_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="qbal-packager-invalid-") as directory:
        root = Path(directory)
        specification, spec = make_spec(root)
        malformed = dict(spec)
        malformed["../escape"] = malformed.pop(REQUIRED[0])
        bad_spec = write(root / "bad.json", json.dumps(malformed).encode())
        try:
            package_bundle(root / "bundle", bad_spec)
        except BundleError as error:
            assert "must stay relative" in str(error)
        else:
            raise AssertionError("path traversal was accepted")

        reserved = dict(spec)
        reserved["README.md"] = reserved.pop(REQUIRED[0])
        reserved_spec = write(root / "reserved.json", json.dumps(reserved).encode())
        try:
            package_bundle(root / "reserved-bundle", reserved_spec)
        except BundleError as error:
            assert "reserved" in str(error)
        else:
            raise AssertionError("reserved manifest path was accepted")

        destination = root / "existing"
        destination.mkdir()
        try:
            package_bundle(destination, specification)
        except BundleError as error:
            assert "already exists" in str(error)
        else:
            raise AssertionError("existing output was overwritten")


def test_missing_required_group_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="qbal-packager-required-") as directory:
        root = Path(directory)
        specification, spec = make_spec(root)
        del spec["receivers/receivers.json"]
        specification.write_text(json.dumps(spec) + "\n", encoding="utf-8")
        try:
            package_bundle(root / "bundle", specification)
        except BundleError as error:
            assert "receivers/" in str(error)
        else:
            raise AssertionError("specification without receiver list was accepted")


def main() -> None:
    test_bundle_records_required_artifacts_and_hashes()
    test_hash_mismatch_fails_before_bundle_is_created()
    test_malformed_spec_and_existing_destination_are_rejected()
    test_missing_required_group_is_rejected()
    print("Q-BAL feasibility bundle tests passed")


if __name__ == "__main__":
    main()
