#!/usr/bin/env python3
"""Failure-injection tests for atomic Cloud-BAL generation publication."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from cloud_bal_transaction import OutputTransaction, TransactionError, _current  # noqa: E402

SOURCE_COMMIT = "cb0a5713f1acd737fa9a058f9d32adedf71bd9d1"


def expect_rejected(action, message: str) -> None:
    try:
        action()
    except TransactionError:
        return
    raise AssertionError(message)


def write_products(transaction: OutputTransaction, values: dict[str, bytes]) -> None:
    for product, payload in values.items():
        path = transaction.resolve_output(product)
        path.write_bytes(payload)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-transaction-") as directory:
        root = Path(directory) / "publication"

        old = OutputTransaction(root, "old")
        old.begin(
            ["wps/LAPS:old", "balance/lw3/old"],
            source_commit=SOURCE_COMMIT,
            configuration="shadow-v1",
        )
        write_products(old, {"wps/LAPS:old": b"old-wps", "balance/lw3/old": b"old-lw3"})
        old_manifest = old.commit()
        assert _current(root).name == "old"
        assert len(old_manifest["products"]) == 2

        incomplete = OutputTransaction(root, "incomplete")
        incomplete.begin(
            ["wps/LAPS:new", "balance/lw3/new"],
            source_commit=SOURCE_COMMIT,
            configuration="shadow-v1",
        )
        incomplete.resolve_output("wps/LAPS:new").write_bytes(b"partial")
        expect_rejected(incomplete.commit, "incomplete generation was committed")
        assert _current(root).name == "old"

        after_manifest = OutputTransaction(root, "after_manifest")
        after_manifest.begin(
            ["wps/LAPS:new"], source_commit=SOURCE_COMMIT, configuration="shadow-v1"
        )
        write_products(after_manifest, {"wps/LAPS:new": b"new-manifest"})
        os.environ["CLOUD_BAL_FAIL_AT"] = "after_manifest"
        expect_rejected(after_manifest.commit, "manifest failure was accepted")
        os.environ.pop("CLOUD_BAL_FAIL_AT")
        assert _current(root).name == "old"
        assert (after_manifest.staging / "MANIFEST.json").is_file()
        assert not (after_manifest.staging / "COMMITTED").exists()

        after_marker = OutputTransaction(root, "after_marker")
        after_marker.begin(
            ["wps/LAPS:new"], source_commit=SOURCE_COMMIT, configuration="shadow-v1"
        )
        write_products(after_marker, {"wps/LAPS:new": b"new-marked"})
        os.environ["CLOUD_BAL_FAIL_AT"] = "after_marker"
        expect_rejected(after_marker.commit, "marker failure was accepted")
        os.environ.pop("CLOUD_BAL_FAIL_AT")
        assert _current(root).name == "old"
        assert (after_marker.staging / "COMMITTED").is_file()

        after_rename = OutputTransaction(root, "after_rename")
        after_rename.begin(
            ["wps/LAPS:new"], source_commit=SOURCE_COMMIT, configuration="shadow-v1"
        )
        write_products(after_rename, {"wps/LAPS:new": b"new-renamed"})
        os.environ["CLOUD_BAL_FAIL_AT"] = "after_generation_rename"
        expect_rejected(after_rename.commit, "generation-rename failure was accepted")
        os.environ.pop("CLOUD_BAL_FAIL_AT")
        assert _current(root).name == "old"
        assert (after_rename.generation / "COMMITTED").is_file()

        before_swap = OutputTransaction(root, "before_swap")
        before_swap.begin(
            ["wps/LAPS:new"], source_commit=SOURCE_COMMIT, configuration="shadow-v1"
        )
        write_products(before_swap, {"wps/LAPS:new": b"new-before-swap"})
        os.environ["CLOUD_BAL_FAIL_AT"] = "before_current_swap"
        expect_rejected(before_swap.commit, "current-swap failure was accepted")
        os.environ.pop("CLOUD_BAL_FAIL_AT")
        assert _current(root).name == "old"
        assert (before_swap.generation / "COMMITTED").is_file()
        assert not (root / ".current.before_swap.tmp").exists()

        successful = OutputTransaction(root, "new")
        successful.begin(
            ["wps/LAPS:new", "balance/lw3/new"],
            source_commit=SOURCE_COMMIT,
            configuration="shadow",
        )
        write_products(successful, {"wps/LAPS:new": b"new-wps", "balance/lw3/new": b"new-lw3"})
        successful.commit()
        current = _current(root)
        assert current.name == "new"
        assert (current / "wps/LAPS:new").read_bytes() == b"new-wps"
        manifest = json.loads((current / "MANIFEST.json").read_text(encoding="utf-8"))
        assert {item["path"] for item in manifest["products"]} == {
            "wps/LAPS:new",
            "balance/lw3/new",
        }

        product = current / "wps/LAPS:new"
        product.write_bytes(b"tampered")
        expect_rejected(lambda: _current(root), "tampered product was accepted")
        product.write_bytes(b"new-wps")
        assert _current(root).name == "new"

        manifest_path = current / "MANIFEST.json"
        original_manifest = manifest_path.read_text(encoding="utf-8")
        corrupted_manifest = json.loads(original_manifest)
        corrupted_manifest["products"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(corrupted_manifest), encoding="utf-8")
        expect_rejected(lambda: _current(root), "tampered manifest was accepted")
        manifest_path.write_text(original_manifest, encoding="utf-8")

        marker_path = current / "COMMITTED"
        marker_path.write_text("wrong\n", encoding="ascii")
        expect_rejected(lambda: _current(root), "tampered marker was accepted")
        marker_path.write_text("new\n", encoding="ascii")
        assert _current(root).name == "new"

        context_tampered = OutputTransaction(root, "context_tampered")
        context_tampered.begin(
            ["wps/LAPS:bad"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(context_tampered, {"wps/LAPS:bad": b"bad"})
        context_path = context_tampered.staging / "TRANSACTION.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["source_commit"] = "unknown"
        context_path.write_text(json.dumps(context), encoding="utf-8")
        expect_rejected(context_tampered.commit, "tampered context was committed")
        assert _current(root).name == "new"

        unsafe = OutputTransaction(root, "unsafe")
        expect_rejected(
            lambda: unsafe.begin(
                ["../ANAL/reference"], source_commit=SOURCE_COMMIT, configuration="shadow"
            ),
            "parent traversal was accepted",
        )
        expect_rejected(
            lambda: OutputTransaction(root, "duplicate").begin(
                ["a", "a"], source_commit=SOURCE_COMMIT, configuration="shadow"
            ),
            "duplicate product identity was accepted",
        )
        expect_rejected(
            lambda: OutputTransaction(root, "unknown").begin(
                ["a"], source_commit="unknown", configuration="shadow"
            ),
            "unknown source commit was accepted",
        )
        expect_rejected(
            lambda: OutputTransaction(root, "short_sha").begin(
                ["a"], source_commit="abc", configuration="shadow"
            ),
            "short source commit was accepted",
        )

        outside = Path(directory) / "outside"
        outside.mkdir()
        symlinked = OutputTransaction(root, "symlinked")
        symlinked.begin(
            ["escape/product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        (symlinked.staging / "escape").symlink_to(outside, target_is_directory=True)
        expect_rejected(
            lambda: symlinked.resolve_output("escape/product"),
            "symlink path escape was accepted",
        )

        nested_escape = OutputTransaction(root, "nested_escape")
        nested_escape.begin(
            ["alias/created/product"],
            source_commit=SOURCE_COMMIT,
            configuration="shadow",
        )
        (nested_escape.staging / "alias").symlink_to(outside, target_is_directory=True)
        expect_rejected(
            lambda: nested_escape.resolve_output("alias/created/product"),
            "nested symlink path escape was accepted",
        )
        assert not (outside / "created").exists()

        generation_escape = OutputTransaction(root, "generation_escape")
        generation_escape.begin(
            ["alias/created/product"],
            source_commit=SOURCE_COMMIT,
            configuration="shadow",
        )
        (generation_escape.staging / "alias").symlink_to(current, target_is_directory=True)
        expect_rejected(
            lambda: generation_escape.resolve_output("alias/created/product"),
            "generation symlink path escape was accepted",
        )
        assert not (current / "created").exists()

        symlink_root = Path(directory) / "symlink-publication"
        symlink_root.mkdir()
        (symlink_root / "generations").symlink_to(outside, target_is_directory=True)
        expect_rejected(
            lambda: OutputTransaction(symlink_root, "parent_escape").begin(
                ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
            ),
            "symlinked publication parent was accepted",
        )

        staging_symlink_root = Path(directory) / "staging-symlink-publication"
        staging_symlink_root.mkdir()
        (staging_symlink_root / ".staging").symlink_to(outside, target_is_directory=True)
        expect_rejected(
            lambda: OutputTransaction(staging_symlink_root, "parent_escape").begin(
                ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
            ),
            "symlinked staging parent was accepted",
        )

        swapped_root = Path(directory) / "swapped-publication"
        swapped = OutputTransaction(swapped_root, "swapped")
        swapped.begin(["product"], source_commit=SOURCE_COMMIT, configuration="shadow")
        write_products(swapped, {"product": b"candidate"})
        swapped.generations.rmdir()
        swapped.generations.symlink_to(outside, target_is_directory=True)
        expect_rejected(swapped.commit, "replaced generation parent was accepted")
        assert not (outside / "swapped").exists()

        hardlink = OutputTransaction(root, "hardlink")
        hardlink.begin(["product"], source_commit=SOURCE_COMMIT, configuration="shadow")
        protected = outside / "protected-analysis"
        protected.write_bytes(b"protected")
        os.link(protected, hardlink.resolve_output("product"))
        expect_rejected(hardlink.commit, "hardlinked output product was accepted")
        assert protected.read_bytes() == b"protected"
        assert protected.stat().st_nlink == 1

        resolve_hardlink = OutputTransaction(root, "resolve_hardlink")
        resolve_hardlink.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        os.link(protected, resolve_hardlink.staging / "product")
        expect_rejected(
            lambda: resolve_hardlink.resolve_output("product"),
            "pre-existing output hardlink was returned to a writer",
        )
        assert protected.read_bytes() == b"protected"
        assert protected.stat().st_nlink == 1

        manifest_temp = OutputTransaction(root, "manifest_temp")
        manifest_temp.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(manifest_temp, {"product": b"candidate"})
        sentinel = outside / "metadata-sentinel"
        sentinel.write_bytes(b"untouched")
        (manifest_temp.staging / ".MANIFEST.json.tmp").symlink_to(sentinel)
        expect_rejected(manifest_temp.commit, "manifest temporary symlink was accepted")
        assert sentinel.read_bytes() == b"untouched"

        marker_temp = OutputTransaction(root, "marker_temp")
        marker_temp.begin(["product"], source_commit=SOURCE_COMMIT, configuration="shadow")
        write_products(marker_temp, {"product": b"candidate"})
        (marker_temp.staging / ".COMMITTED.tmp").symlink_to(sentinel)
        expect_rejected(marker_temp.commit, "marker temporary symlink was accepted")
        assert sentinel.read_bytes() == b"untouched"

        hidden_plain = OutputTransaction(root, "hidden_plain")
        hidden_plain.begin(["product"], source_commit=SOURCE_COMMIT, configuration="shadow")
        write_products(hidden_plain, {"product": b"candidate"})
        hidden_plain.resolve_output("product").parent.joinpath("hidden").mkdir()
        (hidden_plain.staging / "hidden" / "MANIFEST.json").write_bytes(b"undeclared")
        expect_rejected(hidden_plain.commit, "nested metadata-named file was hidden")

        hidden_link = OutputTransaction(root, "hidden_link")
        hidden_link.begin(["product"], source_commit=SOURCE_COMMIT, configuration="shadow")
        write_products(hidden_link, {"product": b"candidate"})
        (hidden_link.staging / "hidden").mkdir()
        os.link(protected, hidden_link.staging / "hidden" / "MANIFEST.json")
        expect_rejected(hidden_link.commit, "nested metadata-named hardlink was hidden")
        assert protected.read_bytes() == b"protected"
        assert protected.stat().st_nlink == 1
        assert hidden_link.staging.exists()
        assert not hidden_link.generation.exists()

    print("Cloud-BAL output transaction tests passed")


if __name__ == "__main__":
    main()
