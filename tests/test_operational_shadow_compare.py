#!/usr/bin/env python3
"""Adversarial tests for diagnostic-patch input provenance."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from compare_operational_shadow import (  # noqa: E402
    archive_receipt,
    paths_overlap,
    require_independent_inputs,
)


def expect_rejected(action, text: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert text in str(exc)
    else:
        raise AssertionError(f"expected rejection containing {text!r}")


def main() -> None:
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


if __name__ == "__main__":
    main()
