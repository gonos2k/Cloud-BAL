#!/usr/bin/env python3
"""Package a hash-checked Q-BAL receiver diagnostic reproduction bundle.

The input is deliberately explicit: a JSON object maps each destination path
inside the bundle to its source file and expected SHA-256.  This keeps the
portable replay auditable and avoids guessing historical paths or silently
including unrelated files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA = "qbal-feasibility-reproduction-v1"
REQUIRED_PATHS = (
    "scripts/replay_receivers.sh",
    "candidates/",
    "hypothetical_faces/",
    "receivers/",
    "inputs/",
    "outputs/",
)
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


class BundleError(ValueError):
    """Raised when the bundle specification cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_spec(path: Path) -> dict[str, dict[str, str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read bundle specification {path}: {error}") from error
    if not isinstance(document, dict) or not document:
        raise BundleError("bundle specification must be a non-empty JSON object")
    result: dict[str, dict[str, str]] = {}
    for destination, details in document.items():
        if not isinstance(destination, str) or not destination:
            raise BundleError("bundle destination paths must be non-empty strings")
        destination_path = Path(destination)
        if destination_path.is_absolute() or ".." in destination_path.parts:
            raise BundleError(f"bundle destination must stay relative: {destination!r}")
        if destination in {"manifest.json", "README.md"}:
            raise BundleError(f"bundle destination is reserved: {destination!r}")
        if destination_path.as_posix() != destination or destination.endswith("/"):
            raise BundleError(f"bundle destination must use normalized file paths: {destination!r}")
        if not isinstance(details, dict) or set(details) != {"source", "sha256"}:
            raise BundleError(
                f"bundle entry {destination!r} must contain exactly source and sha256"
            )
        source = details["source"]
        expected = details["sha256"]
        if not isinstance(source, str) or not source:
            raise BundleError(f"source for {destination!r} must be a non-empty string")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise BundleError(f"invalid SHA-256 for {destination!r}")
        result[destination] = {"source": source, "sha256": expected.lower()}
    missing = [
        required
        for required in REQUIRED_PATHS
        if not (
            required in result
            if required.endswith(".sh")
            else any(name.startswith(required) for name in result)
        )
    ]
    if missing:
        raise BundleError("bundle specification is missing required artifact groups: " + ", ".join(missing))
    return result


def _validated_sources(spec: Mapping[str, Mapping[str, str]]) -> dict[str, tuple[Path, str]]:
    """Resolve and hash every selected source before creating a destination."""

    validated: dict[str, tuple[Path, str]] = {}
    for destination, details in spec.items():
        source = Path(details["source"]).expanduser()
        try:
            source = source.resolve(strict=True)
        except OSError as error:
            raise BundleError(f"source does not exist for {destination}: {source}") from error
        if not source.is_file():
            raise BundleError(f"source is not a regular file for {destination}: {source}")
        actual = sha256_file(source)
        expected = details["sha256"]
        if actual != expected:
            raise BundleError(
                f"SHA-256 mismatch for {destination}: expected {expected}, got {actual}"
            )
        validated[destination] = (source, actual)
    return validated


def _write_readme(path: Path, spec: Mapping[str, Mapping[str, str]]) -> None:
    historical = sorted(
        details["source"]
        for destination, details in spec.items()
        if destination.startswith("scripts/")
    )
    lines = [
        "# Q-BAL receiver diagnostic reproduction bundle",
        "",
        "This bundle contains only the explicitly listed scripts, candidates,",
        "hypothetical face set, receiver list, inputs, and outputs. Every file is",
        "recorded with its SHA-256 in `manifest.json`.",
        "",
        "## Exact historical replay",
        "",
        "The copied execution scripts retain their historical contents and any",
        "hard-coded paths. Run them from the exact source layout recorded in",
        "`manifest.json`; copying them here does not make those paths portable.",
        "The original Fortran replay requires the pinned Intel profile and a",
        "fresh scratch build.",
    ]
    if historical:
        lines.extend(["", "Historical script sources:", *[f"- `{source}`" for source in historical]])
    lines.extend(
        [
            "",
            "## Portable receiver replay",
            "",
            "Run `./scripts/replay_receivers.sh` from this bundle root. The",
            "script invokes the receiver diagnostic and re-reads the supplied candidate, masks,",
            "receiver list, and before/after fields; it does not regenerate the",
            "historical candidate.",
            "",
            "The bundle therefore makes no independent-candidate claim and does",
            "not establish production BALCON approval.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def package_bundle(bundle: Path, specification: Path) -> dict[str, object]:
    """Validate *specification*, copy its files, and write the bundle manifest."""

    bundle = bundle.expanduser()
    if bundle.exists():
        raise BundleError(f"bundle destination already exists: {bundle}")
    spec = _load_spec(specification.expanduser())
    validated = _validated_sources(spec)
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "bundle_kind": "diagnostic_receiver_reproduction",
        "candidate_regeneration_claim": False,
        "production_approval_claim": False,
        "specification": str(specification.expanduser().resolve()),
        "artifacts": {
            destination: {
                "source": str(source),
                "sha256": actual,
            }
            for destination, (source, actual) in validated.items()
        },
    }

    bundle_parent = bundle.parent.resolve()
    bundle_parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=f".{bundle.name}.", dir=bundle_parent) as temporary:
            staging = Path(temporary)
            for destination, (source, _) in validated.items():
                target = staging / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                target.chmod(stat.S_IMODE(source.stat().st_mode))
                if sha256_file(target) != spec[destination]["sha256"]:
                    raise BundleError(f"copied bytes changed while packaging {destination}")
            (staging / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            _write_readme(staging / "README.md", spec)
            os.replace(staging, bundle)
    except OSError as error:
        raise BundleError(f"unable to create bundle {bundle}: {error}") from error
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="JSON destination -> source/SHA-256 map")
    parser.add_argument("--bundle", required=True, type=Path, help="new output directory")
    args = parser.parse_args(argv)
    try:
        manifest = package_bundle(args.bundle, args.spec)
    except BundleError as error:
        print(f"package_qbal_feasibility: error: {error}", file=sys.stderr)
        return 2
    print(f"created {args.bundle} with {len(manifest['artifacts'])} hash-checked artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
