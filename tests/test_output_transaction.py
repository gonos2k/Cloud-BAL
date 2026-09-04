#!/usr/bin/env python3
"""Failure-injection tests for atomic Cloud-BAL generation publication."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from cloud_bal_transaction import OutputTransaction, TransactionError, _current  # noqa: E402

SOURCE_COMMIT = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
).strip()


def expect_rejected(action, message: str) -> None:
    try:
        action()
    except TransactionError:
        return
    raise AssertionError(message)


def expect_rejected_with_hook(
    action, hook, message: str
) -> None:
    """Run one failure-injection action and always restore the class hook."""
    original = OutputTransaction.__dict__["_inject"]
    OutputTransaction._inject = staticmethod(hook)
    try:
        expect_rejected(action, message)
    finally:
        OutputTransaction._inject = original


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
        assert old_manifest["schema"] == 2
        assert json.loads((old.generation / "TRANSACTION.json").read_text())["schema"] == 2
        assert json.loads(old.owner.read_text())["schema"] == 2

        legacy_root = Path(directory) / "legacy-publication"
        legacy_generation = legacy_root / "generations" / "legacy"
        legacy_generation.mkdir(parents=True)
        (legacy_root / ".staging").mkdir()
        (legacy_root / ".owners").mkdir()
        payload = b"legacy"
        (legacy_generation / "product").write_bytes(payload)
        legacy_context = {
            "schema": 1,
            "transaction_id": "legacy",
            "products": ["product"],
            "source_commit": SOURCE_COMMIT,
            "configuration": "shadow",
            "valid_time": 0,
            "expected_current": None,
        }
        (legacy_generation / "TRANSACTION.json").write_text(
            json.dumps(legacy_context), encoding="utf-8"
        )
        (legacy_generation / "MANIFEST.json").write_text(
            json.dumps(
                {
                    **legacy_context,
                    "committed_utc": "2026-01-01T00:00:00+00:00",
                    "products": [
                        {
                            "path": "product",
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (legacy_generation / "COMMITTED").write_text("legacy\n", encoding="ascii")
        (legacy_root / "current").symlink_to("generations/legacy")
        expect_rejected(
            lambda: _current(legacy_root),
            "ownerless schema-1 current generation was accepted",
        )

        adversary_outside = Path(directory) / "adversary-outside"
        adversary_outside.mkdir()

        # A caller that never ran begin() must not be able to forge a complete
        # looking staging tree by writing a plausible transaction context.
        forged = OutputTransaction(root, "forged")
        forged.staging.mkdir(parents=True)
        (forged.staging / "TRANSACTION.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "transaction_id": "forged",
                    "products": ["product"],
                    "source_commit": SOURCE_COMMIT,
                    "configuration": "shadow",
                    "valid_time": 1,
                    "expected_current": "old",
                }
            ),
            encoding="utf-8",
        )
        (forged.staging / "product").write_bytes(b"forged")
        expect_rejected(forged.commit, "forged staging without begin receipt was accepted")
        assert _current(root).name == "old"

        missing_owner = OutputTransaction(root, "missing_owner")
        missing_owner.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(missing_owner, {"product": b"candidate"})
        missing_owner.owner.unlink()
        expect_rejected(
            missing_owner.commit,
            "transaction without its begin receipt was accepted",
        )

        tampered_owner = OutputTransaction(root, "tampered_owner")
        tampered_owner.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(tampered_owner, {"product": b"candidate"})
        owner = json.loads(tampered_owner.owner.read_text())
        owner["context_sha256"] = "0" * 64
        tampered_owner.owner.write_text(json.dumps(owner), encoding="utf-8")
        expect_rejected(
            tampered_owner.commit,
            "transaction with a tampered begin receipt was accepted",
        )
        assert _current(root).name == "old"

        # Metadata targets are never allowed to be symlinks: replacing one
        # would hide an external write behind an apparently atomic rename.
        metadata_link = OutputTransaction(root, "metadata_link")
        metadata_link.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(metadata_link, {"product": b"candidate"})
        metadata_sentinel = adversary_outside / "manifest-sentinel"
        metadata_sentinel.write_bytes(b"untouched")
        (metadata_link.staging / "MANIFEST.json").symlink_to(metadata_sentinel)
        expect_rejected(
            metadata_link.commit,
            "metadata symlink external-write attempt was accepted",
        )
        assert metadata_sentinel.read_bytes() == b"untouched"
        assert _current(root).name == "old"

        # Swap the declared product itself after its initial hash/close pass.
        product_swap = OutputTransaction(root, "product_swap")
        product_swap.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(product_swap, {"product": b"candidate"})
        product_sentinel = adversary_outside / "product-sentinel"
        product_sentinel.write_bytes(b"untouched")

        def swap_product(point: str) -> None:
            if point == "after_manifest":
                candidate = product_swap.staging / "product"
                candidate.unlink()
                candidate.symlink_to(product_sentinel)

        expect_rejected_with_hook(
            product_swap.commit,
            swap_product,
            "product path swap around commit was accepted",
        )
        assert product_sentinel.read_bytes() == b"untouched"
        assert _current(root).name == "old"

        # Replace a product's directory parent at the same explicit commit
        # boundary.  The external directory contains a sentinel with the same
        # basename, so following the swapped parent would be observable.
        parent_swap = OutputTransaction(root, "parent_swap")
        parent_swap.begin(
            ["nested/product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(parent_swap, {"nested/product": b"candidate"})
        parent_target = adversary_outside / "parent-target"
        parent_target.mkdir()
        parent_sentinel = parent_target / "product"
        parent_sentinel.write_bytes(b"untouched")
        nested_parent = parent_swap.staging / "nested"
        nested_backup = parent_swap.staging / "nested-original"

        def swap_product_parent(point: str) -> None:
            if point == "after_manifest":
                nested_parent.rename(nested_backup)
                nested_parent.symlink_to(parent_target, target_is_directory=True)

        expect_rejected_with_hook(
            parent_swap.commit,
            swap_product_parent,
            "product directory-parent replacement was accepted",
        )
        assert parent_sentinel.read_bytes() == b"untouched"
        assert _current(root).name == "old"

        # A generation target can appear after begin().  It must not be
        # overwritten when the staged tree is renamed into generations/.
        collision = OutputTransaction(root, "generation_collision")
        collision.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(collision, {"product": b"candidate"})
        collision_sentinel = collision.generation / "existing-sentinel"

        def collide_generation(point: str) -> None:
            if point == "after_marker":
                collision.generation.mkdir()
                collision_sentinel.write_bytes(b"untouched")

        expect_rejected_with_hook(
            collision.commit,
            collide_generation,
            "generation target collision was accepted",
        )
        assert collision_sentinel.read_bytes() == b"untouched"
        assert _current(root).name == "old"

        replaced_generation = OutputTransaction(root, "replaced_generation")
        replaced_generation.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(replaced_generation, {"product": b"candidate"})

        def replace_generation(point: str) -> None:
            if point == "after_generation_rename":
                backup = replaced_generation.generation.with_name(
                    "replaced_generation-original"
                )
                replaced_generation.generation.rename(backup)
                shutil.copytree(backup, replaced_generation.generation)
                (replaced_generation.generation / "product").write_bytes(b"forged")

        expect_rejected_with_hook(
            replaced_generation.commit,
            replace_generation,
            "generation-directory replacement was accepted",
        )
        assert _current(root).name == "old"

        # Neither a symlinked publication lock nor a pre-existing current-temp
        # symlink may be followed or replaced, and both sentinels remain intact.
        lock_symlink = OutputTransaction(root, "lock_symlink")
        lock_symlink.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(lock_symlink, {"product": b"candidate"})
        lock_sentinel = adversary_outside / "lock-sentinel"
        lock_sentinel.write_bytes(b"untouched")
        lock_path = root / ".publish.lock"
        lock_path.unlink()
        lock_path.symlink_to(lock_sentinel)
        expect_rejected(
            lock_symlink.commit,
            "publication lock symlink was followed or replaced",
        )
        assert lock_sentinel.read_bytes() == b"untouched"
        assert lock_path.is_symlink()
        assert _current(root).name == "old"
        lock_path.unlink()

        temp_symlink = OutputTransaction(root, "temp_symlink")
        temp_symlink.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(temp_symlink, {"product": b"candidate"})
        temp_sentinel = adversary_outside / "current-temp-sentinel"
        temp_sentinel.write_bytes(b"untouched")
        temporary_pointer = root / f".current.{temp_symlink.transaction_id}.tmp"
        temporary_pointer.symlink_to(temp_sentinel)
        expect_rejected(
            temp_symlink.commit,
            "current temporary symlink was followed or replaced",
        )
        assert temp_sentinel.read_bytes() == b"untouched"
        assert temporary_pointer.is_symlink()
        assert _current(root).name == "old"
        temporary_pointer.unlink()

        swapped_temp = OutputTransaction(root, "swapped_temp")
        swapped_temp.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(swapped_temp, {"product": b"candidate"})

        def replace_current_temp(point: str) -> None:
            if point == "before_current_swap":
                temporary = root / ".current.swapped_temp.tmp"
                temporary.unlink()
                temporary.symlink_to("generations/old")

        expect_rejected_with_hook(
            swapped_temp.commit,
            replace_current_temp,
            "replacement current temporary pointer was published",
        )
        assert _current(root).name == "old"

        changed_after_verify = OutputTransaction(root, "changed_after_verify")
        changed_after_verify.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow"
        )
        write_products(changed_after_verify, {"product": b"candidate"})

        def mutate_verified_product(point: str) -> None:
            if point == "before_current_swap":
                (changed_after_verify.generation / "product").write_bytes(b"mutated")

        expect_rejected_with_hook(
            changed_after_verify.commit,
            mutate_verified_product,
            "product mutation after generation verification was published",
        )
        assert _current(root).name == "old"

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

        context_path = current / "TRANSACTION.json"
        original_context = context_path.read_text(encoding="utf-8")
        context_path.unlink()
        expect_rejected(lambda: _current(root), "generation without context was accepted")
        context_path.write_text(original_context, encoding="utf-8")

        rewritten_manifest = json.loads(original_manifest)
        rewritten_manifest["configuration"] = "rewritten"
        manifest_path.write_text(json.dumps(rewritten_manifest), encoding="utf-8")
        expect_rejected(lambda: _current(root), "rewritten manifest context was accepted")
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

        publication_target = Path(directory) / "publication-target"
        publication_target.mkdir()
        publication_alias = Path(directory) / "publication-alias"
        publication_alias.symlink_to(publication_target, target_is_directory=True)
        expect_rejected(
            lambda: OutputTransaction(publication_alias, "root_alias"),
            "symlinked publication root was accepted",
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
        assert protected.stat().st_nlink == 2
        (hardlink.staging / "product").unlink()
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
        assert protected.stat().st_nlink == 2
        (resolve_hardlink.staging / "product").unlink()
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
        assert protected.stat().st_nlink == 2
        (hidden_link.staging / "hidden" / "MANIFEST.json").unlink()
        assert protected.stat().st_nlink == 1
        assert hidden_link.staging.exists()
        assert not hidden_link.generation.exists()

        concurrent_a = OutputTransaction(root, "concurrent_a")
        concurrent_b = OutputTransaction(root, "concurrent_b")
        concurrent_a.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow", valid_time=2
        )
        concurrent_b.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow", valid_time=2
        )
        write_products(concurrent_a, {"product": b"a"})
        write_products(concurrent_b, {"product": b"b"})
        concurrent_a.commit()
        expect_rejected(
            concurrent_b.commit,
            "a transaction with a stale expected-current identity was committed",
        )
        assert _current(root).name == "concurrent_a"

        stale = OutputTransaction(root, "stale")
        stale.begin(
            ["product"], source_commit=SOURCE_COMMIT, configuration="shadow", valid_time=1
        )
        write_products(stale, {"product": b"stale"})
        expect_rejected(stale.commit, "an older analysis replaced current")
        assert _current(root).name == "concurrent_a"

    print("Cloud-BAL output transaction tests passed")


if __name__ == "__main__":
    main()
