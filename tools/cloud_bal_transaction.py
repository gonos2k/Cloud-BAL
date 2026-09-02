#!/usr/bin/env python3
"""Atomic generation publisher for Cloud-BAL products.

Writers receive paths only inside ``ROOT/.staging/TRANSACTION``.  A complete
set is hashed, marked, renamed as one generation, and only then made current.
An exception never changes the current-generation pointer.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterable


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONTEXT = "TRANSACTION.json"
_MANIFEST = "MANIFEST.json"
_COMMITTED = "COMMITTED"
_LOCK = ".publish.lock"


class TransactionError(RuntimeError):
    """The candidate generation is incomplete or violates its path contract."""


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock(root: Path):
    """Serialize the compare-and-swap of the current-generation pointer."""
    lock_path = root / _LOCK
    try:
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise TransactionError("publication lock is unsafe") from exc
    try:
        if os.fstat(descriptor).st_nlink != 1:
            raise TransactionError("publication lock is unsafe")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise TransactionError(f"unsafe metadata temporary: {temporary.name}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise


def _write_marker(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise TransactionError(f"unsafe metadata temporary: {temporary.name}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(value)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value) or value in {".", ".."}:
        raise TransactionError(f"invalid transaction identifier: {value!r}")
    return value


def _product(value: str) -> str:
    product = PurePosixPath(value)
    if (
        not value
        or product.is_absolute()
        or any(part in {"", ".", ".."} for part in product.parts)
    ):
        raise TransactionError(f"unsafe product path: {value!r}")
    return product.as_posix()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _product_inventory(root: Path) -> set[str]:
    """Return safe non-metadata files and remove unsafe external links."""
    metadata = {_CONTEXT, _MANIFEST, _COMMITTED}
    actual: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative in metadata:
            continue
        if path.is_symlink():
            path.unlink()
            raise TransactionError(f"generation contains unsafe entry: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise TransactionError(f"generation contains unsafe entry: {relative}")
        if path.stat(follow_symlinks=False).st_nlink != 1:
            path.unlink()
            raise TransactionError(f"generation contains unsafe entry: {relative}")
        actual.add(relative)
    return actual


def _validate_context(context: object, transaction_id: str) -> dict:
    expected_keys = {
        "schema", "transaction_id", "products", "source_commit",
        "configuration", "valid_time", "expected_current",
    }
    if not isinstance(context, dict) or context.get("schema") != 1 or \
            context.get("transaction_id") != transaction_id or \
            set(context) != expected_keys:
        raise TransactionError("transaction context identity is invalid")
    products = context.get("products")
    if not isinstance(products, list) or not products or \
            not all(isinstance(item, str) for item in products):
        raise TransactionError("transaction product declaration is invalid")
    normalized = [_product(item) for item in products]
    if normalized != sorted(set(normalized)):
        raise TransactionError("transaction products must be sorted and unique")
    source_commit = context.get("source_commit")
    configuration = context.get("configuration")
    valid_time = context.get("valid_time")
    expected_current = context.get("expected_current")
    if not isinstance(source_commit, str) or not _GIT_COMMIT.fullmatch(source_commit):
        raise TransactionError("a lowercase 40-hex Git commit identity is required")
    if not isinstance(configuration, str) or not configuration.strip() or \
            configuration.strip().lower() == "unknown":
        raise TransactionError("an exact configuration identity is required")
    if not isinstance(valid_time, int) or valid_time < 0:
        raise TransactionError("a nonnegative analysis valid time is required")
    if expected_current is not None and (
        not isinstance(expected_current, str)
        or _identifier(expected_current) != expected_current
    ):
        raise TransactionError("expected current generation is invalid")
    return context


class OutputTransaction:
    """One immutable set of declared output products."""

    def __init__(self, root: Path | str, transaction_id: str):
        self.root = Path(root).resolve()
        self.transaction_id = _identifier(transaction_id)
        self.staging_parent = self.root / ".staging"
        self.generations = self.root / "generations"
        self.staging = self.staging_parent / self.transaction_id
        self.generation = self.generations / self.transaction_id

    def _validate_layout(self, *, require_staging: bool) -> None:
        root = self.root.resolve(strict=True)
        for directory in (self.staging_parent, self.generations):
            if directory.is_symlink() or not directory.is_dir() or \
                    directory.resolve(strict=True).parent != root:
                raise TransactionError("publication directories escaped their root")
        if self.staging_parent.stat().st_dev != self.generations.stat().st_dev:
            raise TransactionError("staging and generations must share a filesystem")
        if require_staging and (self.staging.is_symlink() or not self.staging.is_dir() or \
                self.staging.resolve(strict=True).parent != self.staging_parent.resolve(strict=True)):
            raise TransactionError("transaction staging directory is unsafe")

    def begin(
        self,
        products: Iterable[str],
        *,
        source_commit: str,
        configuration: str,
        valid_time: int = 0,
    ) -> None:
        normalized = [_product(item) for item in products]
        if len(normalized) != len(set(normalized)):
            raise TransactionError("output products must have unique identities")
        declared = sorted(normalized)
        if not declared:
            raise TransactionError("at least one output product is required")
        self.root.mkdir(parents=True, exist_ok=True)
        if self.staging_parent.is_symlink() or self.generations.is_symlink():
            raise TransactionError("publication directories must not be symlinks")
        self.staging_parent.mkdir(exist_ok=True)
        self.generations.mkdir(exist_ok=True)
        self._validate_layout(require_staging=False)
        if self.staging.exists() or self.generation.exists():
            raise TransactionError("transaction identifier already exists")

        with _publication_lock(self.root):
            expected_current = _current_id(self.root)
        context = {
            "schema": 1,
            "transaction_id": self.transaction_id,
            "products": declared,
            "source_commit": source_commit,
            "configuration": configuration,
            "valid_time": valid_time,
            "expected_current": expected_current,
        }
        _validate_context(context, self.transaction_id)

        self.staging.mkdir(mode=0o750)
        _write_json_atomic(
            self.staging / _CONTEXT,
            context,
        )
        _fsync_directory(self.staging)
        _fsync_directory(self.staging_parent)

    def _context(self) -> dict:
        context_path = self.staging / _CONTEXT
        try:
            unsafe = context_path.is_symlink() or \
                context_path.stat(follow_symlinks=False).st_nlink != 1
        except OSError as exc:
            raise TransactionError("transaction context is missing or invalid") from exc
        if unsafe:
            raise TransactionError("transaction context is unsafe")
        try:
            with context_path.open(encoding="utf-8") as stream:
                context = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise TransactionError("transaction context is missing or invalid") from exc
        return _validate_context(context, self.transaction_id)

    def resolve_output(self, product: str) -> Path:
        normalized = _product(product)
        context = self._context()
        if normalized not in context.get("products", []):
            raise TransactionError(f"undeclared output product: {normalized}")

        staging_real = self.staging.resolve(strict=True)
        parent = self.staging
        parts = PurePosixPath(normalized).parts
        for component in parts[:-1]:
            child = parent / component
            if child.is_symlink() or (child.exists() and not child.is_dir()):
                raise TransactionError(f"unsafe output parent: {normalized}")
            if not child.exists():
                child.mkdir(mode=0o750)
            if not _inside(child.resolve(strict=True), staging_real):
                raise TransactionError(f"output path escapes staging root: {normalized}")
            parent = child
        candidate = parent / parts[-1]
        if candidate.is_symlink():
            raise TransactionError(f"unsafe output product: {normalized}")
        if candidate.exists() and (not candidate.is_file() or \
                candidate.stat(follow_symlinks=False).st_nlink != 1):
            if candidate.is_file():
                candidate.unlink()
            raise TransactionError(f"unsafe output product: {normalized}")
        return candidate

    def commit(self) -> dict:
        self._validate_layout(require_staging=True)
        context = self._context()
        if _product_inventory(self.staging) != set(context["products"]):
            raise TransactionError("staging contains undeclared or missing products")
        records = []
        staging_real = self.staging.resolve(strict=True)
        for product in context["products"]:
            path = self.staging.joinpath(*PurePosixPath(product).parts)
            if path.is_symlink() or not path.is_file() or \
                    path.stat(follow_symlinks=False).st_nlink != 1:
                raise TransactionError(f"missing or unsafe output product: {product}")
            if not _inside(path.resolve(strict=True), staging_real):
                raise TransactionError(f"output product escapes staging root: {product}")
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            records.append(
                {"path": product, "bytes": path.stat().st_size, "sha256": _sha256(path)}
            )

        manifest = {
            **context,
            "committed_utc": datetime.now(timezone.utc).isoformat(),
            "products": records,
        }
        self._validate_layout(require_staging=True)
        _write_json_atomic(self.staging / _MANIFEST, manifest)
        self._inject("after_manifest")
        self._validate_layout(require_staging=True)
        _write_marker(self.staging / _COMMITTED, self.transaction_id)
        _fsync_directory(self.staging)
        self._inject("after_marker")

        self._validate_layout(require_staging=True)
        if _product_inventory(self.staging) != set(context["products"]):
            raise TransactionError("staging contains undeclared or missing products")
        os.replace(self.staging, self.generation)
        _fsync_directory(self.generations)
        self._inject("after_generation_rename")
        _verify_generation(self.generation, self.transaction_id)

        with _publication_lock(self.root):
            current_id = _current_id(self.root)
            if current_id != context["expected_current"]:
                raise TransactionError("current generation changed during the transaction")
            if current_id is not None:
                current_manifest = json.loads(
                    (self.generations / current_id / _MANIFEST).read_text(encoding="utf-8")
                )
                if context["valid_time"] < current_manifest["valid_time"]:
                    raise TransactionError("an older analysis cannot replace current")
            pointer = self.root / "current"
            temporary_pointer = self.root / f".current.{self.transaction_id}.tmp"
            if temporary_pointer.exists() or temporary_pointer.is_symlink():
                raise TransactionError("temporary current pointer already exists")
            os.symlink(f"generations/{self.transaction_id}", temporary_pointer)
            try:
                self._inject("before_current_swap")
                os.replace(temporary_pointer, pointer)
            finally:
                if temporary_pointer.is_symlink() or temporary_pointer.exists():
                    temporary_pointer.unlink()
            _fsync_directory(self.root)
        return manifest

    @staticmethod
    def _inject(point: str) -> None:
        if os.environ.get("CLOUD_BAL_FAIL_AT") == point:
            raise TransactionError(f"injected publication failure at {point}")


def _verify_generation(generation: Path, expected_id: str) -> Path:
    generation = generation.resolve(strict=True)
    if generation.name != expected_id or not _IDENTIFIER.fullmatch(generation.name):
        raise TransactionError("generation identity is invalid")
    marker_path = generation / _COMMITTED
    manifest_path = generation / _MANIFEST
    context_path = generation / _CONTEXT
    if marker_path.is_symlink() or manifest_path.is_symlink() or \
            context_path.is_symlink() or not marker_path.is_file() or \
            not manifest_path.is_file() or not context_path.is_file() or \
            marker_path.stat(follow_symlinks=False).st_nlink != 1 or \
            manifest_path.stat(follow_symlinks=False).st_nlink != 1 or \
            context_path.stat(follow_symlinks=False).st_nlink != 1:
        raise TransactionError("generation is not complete")
    try:
        marker = marker_path.read_text(encoding="ascii").strip()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransactionError("generation metadata is invalid") from exc
    if marker != generation.name or manifest.get("schema") != 1 or \
       manifest.get("transaction_id") != generation.name:
        raise TransactionError("generation identity mismatch")
    context = _validate_context(context, generation.name)
    records = manifest.get("products")
    if not isinstance(records, list) or not records:
        raise TransactionError("generation product manifest is empty")
    declared: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise TransactionError("generation product record is invalid")
        product = _product(str(record.get("path", "")))
        if product in declared:
            raise TransactionError("generation has duplicate products")
        declared.add(product)
        path = generation.joinpath(*PurePosixPath(product).parts)
        digest = str(record.get("sha256", ""))
        size = record.get("bytes")
        if path.is_symlink() or not path.is_file() or \
           path.stat(follow_symlinks=False).st_nlink != 1 or \
           not _inside(path.resolve(strict=True), generation) or \
           not isinstance(size, int) or size < 0 or path.stat().st_size != size or \
           not re.fullmatch(r"[0-9a-f]{64}", digest) or _sha256(path) != digest:
            raise TransactionError(f"generation product failed verification: {product}")
    manifest_context = {
        name: manifest.get(name) for name in context if name != "products"
    }
    manifest_context["products"] = sorted(declared)
    if manifest_context != context or set(manifest) != set(context) | {"committed_utc"}:
        raise TransactionError("generation manifest differs from transaction context")
    actual = _product_inventory(generation)
    if actual != declared:
        raise TransactionError("generation contains undeclared or missing products")
    return generation


def _current(root: Path) -> Path:
    pointer = root.resolve() / "current"
    if not pointer.is_symlink():
        raise TransactionError("no committed current generation")
    generation = pointer.resolve(strict=True)
    generations = root.resolve() / "generations"
    if generation.parent != generations:
        raise TransactionError("current pointer is not one direct generation")
    return _verify_generation(generation, generation.name)


def _current_id(root: Path) -> str | None:
    pointer = root / "current"
    if not pointer.exists() and not pointer.is_symlink():
        return None
    return _current(root).name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    begin = subparsers.add_parser("begin")
    begin.add_argument("root", type=Path)
    begin.add_argument("transaction_id")
    begin.add_argument("products", nargs="+")
    begin.add_argument("--source-commit", required=True)
    begin.add_argument("--configuration", required=True)
    begin.add_argument("--valid-time", required=True, type=int)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("root", type=Path)
    resolve.add_argument("transaction_id")
    resolve.add_argument("product")

    commit = subparsers.add_parser("commit")
    commit.add_argument("root", type=Path)
    commit.add_argument("transaction_id")

    current = subparsers.add_parser("current")
    current.add_argument("root", type=Path)

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "begin":
            transaction = OutputTransaction(arguments.root, arguments.transaction_id)
            transaction.begin(
                arguments.products,
                source_commit=arguments.source_commit,
                configuration=arguments.configuration,
                valid_time=arguments.valid_time,
            )
            print(transaction.staging)
        elif arguments.command == "resolve":
            print(OutputTransaction(arguments.root, arguments.transaction_id).resolve_output(arguments.product))
        elif arguments.command == "commit":
            manifest = OutputTransaction(arguments.root, arguments.transaction_id).commit()
            print(json.dumps(manifest, sort_keys=True))
        else:
            print(_current(arguments.root))
    except TransactionError as exc:
        print(f"cloud-bal transaction rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
