#!/usr/bin/env python3
"""Atomic generation publisher for Cloud-BAL products.

Writers receive paths only inside ``ROOT/.staging/TRANSACTION``.  A complete
set is hashed, marked, renamed as one generation, and only then made current.
An exception never changes the current-generation pointer.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
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
_OWNERS = ".owners"
_RENAME_NOREPLACE = 1


class TransactionError(RuntimeError):
    """The candidate generation is incomplete or violates its path contract."""


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock(root: Path):
    """Serialize the compare-and-swap of the current-generation pointer."""
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError("publication root is unsafe") from exc
    try:
        opened = os.fstat(descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        named = os.stat(root, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise TransactionError("publication root changed while acquiring its lock")
        try:
            marker = os.open(
                _LOCK,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
        except OSError as exc:
            raise TransactionError("publication lock marker is unsafe") from exc
        try:
            marker_status = os.fstat(marker)
            if not stat.S_ISREG(marker_status.st_mode) or marker_status.st_nlink != 1:
                raise TransactionError("publication lock marker is unsafe")
        finally:
            os.close(marker)
        yield descriptor
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _stable_regular_bytes(path: Path, *, sync: bool = False) -> tuple[bytes, os.stat_result]:
    """Read one regular, single-link file through one stable descriptor."""

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError(f"unsafe file: {path.name}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise TransactionError(f"unsafe file: {path.name}")
        if sync:
            os.fsync(descriptor)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink,
        )
        if identity(before) != identity(after) or after.st_nlink != 1:
            raise TransactionError(f"file changed while reading: {path.name}")
        payload = b"".join(chunks)
        if len(payload) != after.st_size:
            raise TransactionError(f"file size changed while reading: {path.name}")
        return payload, after
    finally:
        os.close(descriptor)


def _regular_bytes_at(
    root: int, product: str, *, sync: bool = False
) -> tuple[bytes, os.stat_result]:
    """Read a relative regular file without following any path component."""

    parts = PurePosixPath(_product(product)).parts
    parent = os.dup(root)
    try:
        for component in parts[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            os.close(parent)
            parent = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise TransactionError(f"unsafe file: {product}")
            if sync:
                os.fsync(descriptor)
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            identity = lambda value: (
                value.st_dev, value.st_ino, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns, value.st_nlink,
            )
            if identity(before) != identity(after) or \
                    (named.st_dev, named.st_ino) != (after.st_dev, after.st_ino) or \
                    after.st_nlink != 1:
                raise TransactionError(f"file changed while reading: {product}")
            payload = b"".join(chunks)
            if len(payload) != after.st_size:
                raise TransactionError(f"file size changed while reading: {product}")
            return payload, after
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise TransactionError(f"unsafe file: {product}") from exc
    finally:
        os.close(parent)


def _parse_json(payload: bytes, name: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TransactionError(f"invalid JSON metadata: {name}") from exc
    if not isinstance(value, dict):
        raise TransactionError(f"invalid JSON metadata: {name}")
    return value


def _read_json(path: Path) -> dict:
    payload, _ = _stable_regular_bytes(path)
    return _parse_json(payload, path.name)


def _write_atomic(path: Path, payload: bytes, mode: int = 0o600) -> None:
    """Create new metadata below a pinned, non-symlink parent directory."""

    try:
        parent = os.open(
            path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise TransactionError(f"unsafe metadata parent: {path.parent.name}") from exc
    temporary = f".{path.name}.tmp"
    descriptor = None
    created = False
    try:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise TransactionError(f"metadata already exists: {path.name}")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
            dir_fd=parent,
        )
        created = True
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise TransactionError(f"failed to write metadata: {path.name}")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(
            temporary,
            path.name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
            follow_symlinks=False,
        )
        os.unlink(temporary, dir_fd=parent)
        created = False
        os.fsync(parent)
    except OSError as exc:
        raise TransactionError(f"unsafe metadata write: {path.name}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _write_json_atomic(path: Path, payload: dict) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_atomic(path, data)


def _write_marker(path: Path, value: str) -> None:
    _write_atomic(path, f"{value}\n".encode("ascii"))


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
    payload, _ = _stable_regular_bytes(path)
    return hashlib.sha256(payload).hexdigest()


def _product_record(path: Path, product: str) -> dict:
    payload, status = _stable_regular_bytes(path, sync=True)
    return {
        "path": product,
        "bytes": status.st_size,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _directory_identity(path: Path) -> list[int]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError(f"unsafe publication directory: {path.name}") from exc
    try:
        status = os.fstat(descriptor)
        return [status.st_dev, status.st_ino]
    finally:
        os.close(descriptor)


def _fd_identity(descriptor: int) -> list[int]:
    status = os.fstat(descriptor)
    return [status.st_dev, status.st_ino]


def _open_directory_at(parent: int, name: str) -> int:
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise TransactionError(f"unsafe publication directory: {name}") from exc
    if _fd_identity(descriptor) != [named.st_dev, named.st_ino]:
        os.close(descriptor)
        raise TransactionError(f"publication directory changed: {name}")
    return descriptor


def _valid_directory_identity(value: object) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(
        isinstance(item, int) and item >= 0 for item in value
    )


def _symlink_identity(parent: int, name: str, expected_target: str) -> tuple[int, int]:
    try:
        status = os.stat(name, dir_fd=parent, follow_symlinks=False)
        target = os.readlink(name, dir_fd=parent)
    except OSError as exc:
        raise TransactionError(f"publication pointer is unsafe: {name}") from exc
    if not stat.S_ISLNK(status.st_mode) or target != expected_target:
        raise TransactionError(f"publication pointer is unsafe: {name}")
    return status.st_dev, status.st_ino


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically move one directory without replacing an existing target."""

    try:
        source_parent = os.open(
            source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        destination_parent = os.open(
            destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        if "source_parent" in locals():
            os.close(source_parent)
        raise TransactionError("generation rename parent is unsafe") from exc
    try:
        renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
        if renameat2 is None:
            raise TransactionError("atomic no-replace rename is unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            source_parent,
            os.fsencode(source.name),
            destination_parent,
            os.fsencode(destination.name),
            _RENAME_NOREPLACE,
        )
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise TransactionError("generation target already exists")
            raise TransactionError(
                f"atomic no-replace generation rename failed: {os.strerror(error)}"
            )
        os.fsync(source_parent)
        os.fsync(destination_parent)
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _product_inventory(root: Path) -> set[str]:
    """Return safe non-metadata files without following directory links."""
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError("generation root is unsafe") from exc
    try:
        return _product_inventory_at(descriptor)
    finally:
        os.close(descriptor)


def _product_inventory_at(root: int) -> set[str]:
    metadata = {_CONTEXT, _MANIFEST, _COMMITTED}
    actual: set[str] = set()

    def walk(directory: int, prefix: tuple[str, ...]) -> None:
        for name in sorted(os.listdir(directory)):
            relative = PurePosixPath(*prefix, name).as_posix()
            if not prefix and relative in metadata:
                continue
            status = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISDIR(status.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (status.st_dev, status.st_ino):
                        raise TransactionError(
                            f"generation entry changed: {relative}"
                        )
                    walk(child, (*prefix, name))
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise TransactionError(f"generation contains unsafe entry: {relative}")
            actual.add(relative)

    try:
        walk(root, ())
    except OSError as exc:
        raise TransactionError("generation inventory changed while reading") from exc
    return actual


def _validate_context(context: object, transaction_id: str) -> dict:
    expected_keys = {
        "schema", "transaction_id", "products", "source_commit",
        "configuration", "valid_time", "expected_current", "owner_nonce",
        "publication_identity",
    }
    if not isinstance(context, dict) or context.get("schema") != 2 or \
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
    nonce = context.get("owner_nonce")
    identities = context.get("publication_identity")
    required_identities = {
        "root", "staging_parent", "generations", "owners", "staging"
    }
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise TransactionError("transaction owner nonce is invalid")
    if not isinstance(identities, dict) or set(identities) != required_identities or \
            not all(_valid_directory_identity(value) for value in identities.values()):
        raise TransactionError("transaction publication identity is invalid")
    return context


class OutputTransaction:
    """One immutable set of declared output products."""

    def __init__(self, root: Path | str, transaction_id: str):
        self.root = Path(os.path.abspath(root))
        component_path = Path(self.root.anchor)
        for component in self.root.parts[1:]:
            component_path /= component
            if component_path.is_symlink():
                raise TransactionError("publication root cannot contain a symlink")
        self.transaction_id = _identifier(transaction_id)
        self.staging_parent = self.root / ".staging"
        self.generations = self.root / "generations"
        self.owner_parent = self.root / _OWNERS
        self.staging = self.staging_parent / self.transaction_id
        self.generation = self.generations / self.transaction_id
        self.owner = self.owner_parent / f"{self.transaction_id}.json"

    def _validate_layout(self, *, require_staging: bool) -> None:
        root = self.root.resolve(strict=True)
        for directory in (self.staging_parent, self.generations, self.owner_parent):
            if directory.is_symlink() or not directory.is_dir() or \
                    directory.resolve(strict=True).parent != root:
                raise TransactionError("publication directories escaped their root")
        devices = {
            directory.stat(follow_symlinks=False).st_dev
            for directory in (self.staging_parent, self.generations, self.owner_parent)
        }
        if len(devices) != 1:
            raise TransactionError("publication directories must share a filesystem")
        if require_staging and (self.staging.is_symlink() or not self.staging.is_dir() or \
                self.staging.resolve(strict=True).parent != self.staging_parent.resolve(strict=True)):
            raise TransactionError("transaction staging directory is unsafe")

    def _publication_identity(self, transaction_path: Path | None = None) -> dict:
        return {
            "root": _directory_identity(self.root),
            "staging_parent": _directory_identity(self.staging_parent),
            "generations": _directory_identity(self.generations),
            "owners": _directory_identity(self.owner_parent),
            "staging": _directory_identity(transaction_path or self.staging),
        }

    def _assert_publication_identity(
        self, context: dict, transaction_path: Path | None = None
    ) -> None:
        if "publication_identity" not in context:
            raise TransactionError("transaction lacks schema-2 begin binding")
        if self._publication_identity(transaction_path) != context["publication_identity"]:
            raise TransactionError("publication directories changed during transaction")

    def _context_record(self) -> tuple[dict, str]:
        try:
            payload, _ = _stable_regular_bytes(self.staging / _CONTEXT)
        except TransactionError as exc:
            raise TransactionError("transaction context is missing or invalid") from exc
        context = _validate_context(
            _parse_json(payload, _CONTEXT), self.transaction_id
        )
        return context, hashlib.sha256(payload).hexdigest()

    def _require_owner(self, context: dict, context_sha256: str) -> None:
        if "owner_nonce" not in context:
            raise TransactionError("transaction lacks schema-2 begin binding")
        owner = _read_json(self.owner)
        expected = {
            "schema": 2,
            "transaction_id": self.transaction_id,
            "owner_nonce": context["owner_nonce"],
            "context_sha256": context_sha256,
            "publication_identity": context["publication_identity"],
        }
        if owner != expected:
            raise TransactionError("transaction begin receipt is invalid")

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
        if self.staging_parent.is_symlink() or self.generations.is_symlink() or \
                self.owner_parent.is_symlink():
            raise TransactionError("publication directories must not be symlinks")
        self.staging_parent.mkdir(exist_ok=True)
        self.generations.mkdir(exist_ok=True)
        self.owner_parent.mkdir(exist_ok=True)
        self._validate_layout(require_staging=False)
        if self.staging.exists() or self.generation.exists() or self.owner.exists() or \
                self.staging.is_symlink() or self.generation.is_symlink() or \
                self.owner.is_symlink():
            raise TransactionError("transaction identifier already exists")

        with _publication_lock(self.root):
            expected_current = _current_id(self.root)
        self.staging.mkdir(mode=0o750)
        context = {
            "schema": 2,
            "transaction_id": self.transaction_id,
            "products": declared,
            "source_commit": source_commit,
            "configuration": configuration,
            "valid_time": valid_time,
            "expected_current": expected_current,
            "owner_nonce": secrets.token_hex(32),
            "publication_identity": self._publication_identity(),
        }
        _validate_context(context, self.transaction_id)

        _write_json_atomic(self.staging / _CONTEXT, context)
        context_payload, _ = _stable_regular_bytes(self.staging / _CONTEXT)
        _write_json_atomic(
            self.owner,
            {
                "schema": 2,
                "transaction_id": self.transaction_id,
                "owner_nonce": context["owner_nonce"],
                "context_sha256": hashlib.sha256(context_payload).hexdigest(),
                "publication_identity": context["publication_identity"],
            },
        )
        self._assert_publication_identity(context)
        _fsync_directory(self.staging)
        _fsync_directory(self.staging_parent)
        _fsync_directory(self.owner_parent)

    def _context(self) -> dict:
        context, _ = self._context_record()
        return context

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
            raise TransactionError(f"unsafe output product: {normalized}")
        return candidate

    def commit(self) -> dict:
        self._validate_layout(require_staging=True)
        context, context_sha256 = self._context_record()
        self._require_owner(context, context_sha256)
        self._assert_publication_identity(context)
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
            records.append(_product_record(path, product))

        manifest = {
            **context,
            "committed_utc": datetime.now(timezone.utc).isoformat(),
            "products": records,
        }
        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        _write_json_atomic(self.staging / _MANIFEST, manifest)
        self._inject("after_manifest")
        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        _write_marker(self.staging / _COMMITTED, self.transaction_id)
        _fsync_directory(self.staging)
        self._inject("after_marker")

        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        if _product_inventory(self.staging) != set(context["products"]):
            raise TransactionError("staging contains undeclared or missing products")
        _rename_noreplace(self.staging, self.generation)
        self._assert_publication_identity(context, self.generation)
        self._inject("after_generation_rename")
        _verify_generation(self.generation, self.transaction_id)

        with _publication_lock(self.root) as root_descriptor:
            current_id = _current_id(self.root)
            if current_id != context["expected_current"]:
                raise TransactionError("current generation changed during the transaction")
            if current_id is not None:
                current_manifest = _read_json(
                    self.generations / current_id / _MANIFEST
                )
                if context["valid_time"] < current_manifest["valid_time"]:
                    raise TransactionError("an older analysis cannot replace current")
            temporary_name = f".current.{self.transaction_id}.tmp"
            try:
                os.stat(temporary_name, dir_fd=root_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise TransactionError("temporary current pointer already exists")
            os.symlink(
                f"generations/{self.transaction_id}",
                temporary_name,
                dir_fd=root_descriptor,
            )
            target = f"generations/{self.transaction_id}"
            temporary_identity = _symlink_identity(
                root_descriptor, temporary_name, target
            )
            try:
                self._inject("before_current_swap")
                _verify_generation(self.generation, self.transaction_id)
                if _symlink_identity(root_descriptor, temporary_name, target) != \
                        temporary_identity:
                    raise TransactionError("temporary current pointer changed")
                if _directory_identity(self.generation) != \
                        context["publication_identity"]["staging"]:
                    raise TransactionError("verified generation changed before publication")
                os.replace(
                    temporary_name,
                    "current",
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                )
                if _symlink_identity(root_descriptor, "current", target) != \
                        temporary_identity:
                    raise TransactionError("published current pointer changed")
            finally:
                try:
                    os.unlink(temporary_name, dir_fd=root_descriptor)
                except FileNotFoundError:
                    pass
            os.fsync(root_descriptor)
        return manifest

    @staticmethod
    def _inject(point: str) -> None:
        if os.environ.get("CLOUD_BAL_FAIL_AT") == point:
            raise TransactionError(f"injected publication failure at {point}")


def _verify_generation(generation: Path, expected_id: str) -> Path:
    generation = generation.absolute()
    if generation.name != expected_id or not _IDENTIFIER.fullmatch(generation.name):
        raise TransactionError("generation identity is invalid")
    root = generation.parent.parent
    if generation.parent.name != "generations":
        raise TransactionError("generation is outside a publication root")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError("publication root is unsafe") from exc
    try:
        opened: list[int] = []
        try:
            staging_fd = _open_directory_at(root_fd, ".staging")
            opened.append(staging_fd)
            generations_fd = _open_directory_at(root_fd, "generations")
            opened.append(generations_fd)
            owners_fd = _open_directory_at(root_fd, _OWNERS)
            opened.append(owners_fd)
            generation_fd = _open_directory_at(generations_fd, generation.name)
            opened.append(generation_fd)
        except Exception:
            for descriptor in reversed(opened):
                os.close(descriptor)
            raise
        try:
            marker_bytes, _ = _regular_bytes_at(generation_fd, _COMMITTED)
            marker = marker_bytes.decode("ascii").strip()
            manifest_bytes, _ = _regular_bytes_at(generation_fd, _MANIFEST)
            manifest = _parse_json(manifest_bytes, _MANIFEST)
            context_bytes, _ = _regular_bytes_at(generation_fd, _CONTEXT)
            context = _validate_context(
                _parse_json(context_bytes, _CONTEXT), generation.name
            )
            if marker != generation.name or manifest.get("schema") != 2 or \
                    manifest.get("transaction_id") != generation.name:
                raise TransactionError("generation identity mismatch")

            owner_bytes, _ = _regular_bytes_at(
                owners_fd, f"{generation.name}.json"
            )
            owner = _parse_json(owner_bytes, f"{generation.name}.json")
            expected_owner = {
                "schema": 2,
                "transaction_id": generation.name,
                "owner_nonce": context["owner_nonce"],
                "context_sha256": hashlib.sha256(context_bytes).hexdigest(),
                "publication_identity": context["publication_identity"],
            }
            if owner != expected_owner:
                raise TransactionError("generation begin receipt is invalid")

            expected_identity = context["publication_identity"]
            actual_identity = {
                "root": _fd_identity(root_fd),
                "staging_parent": _fd_identity(staging_fd),
                "generations": _fd_identity(generations_fd),
                "owners": _fd_identity(owners_fd),
                "staging": _fd_identity(generation_fd),
            }
            if actual_identity != expected_identity:
                raise TransactionError("generation publication identity is invalid")

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
                payload, status = _regular_bytes_at(generation_fd, product)
                digest = str(record.get("sha256", ""))
                size = record.get("bytes")
                if not isinstance(size, int) or size < 0 or \
                        status.st_size != size or \
                        not re.fullmatch(r"[0-9a-f]{64}", digest) or \
                        hashlib.sha256(payload).hexdigest() != digest:
                    raise TransactionError(
                        f"generation product failed verification: {product}"
                    )
            manifest_context = {
                name: manifest.get(name) for name in context if name != "products"
            }
            manifest_context["products"] = sorted(declared)
            if manifest_context != context or \
                    set(manifest) != set(context) | {"committed_utc"}:
                raise TransactionError(
                    "generation manifest differs from transaction context"
                )
            if _product_inventory_at(generation_fd) != declared:
                raise TransactionError(
                    "generation contains undeclared or missing products"
                )
            named = os.stat(
                generation.name,
                dir_fd=generations_fd,
                follow_symlinks=False,
            )
            if _fd_identity(generation_fd) != [named.st_dev, named.st_ino]:
                raise TransactionError("generation changed while verifying")
        finally:
            for descriptor in reversed(opened):
                os.close(descriptor)
    except UnicodeError as exc:
        raise TransactionError("generation metadata is invalid") from exc
    finally:
        os.close(root_fd)
    return generation


def _current(root: Path) -> Path:
    root = Path(root).absolute()
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError("publication root is unsafe") from exc
    try:
        try:
            pointer_status = os.stat(
                "current", dir_fd=root_fd, follow_symlinks=False
            )
            target = os.readlink("current", dir_fd=root_fd)
        except OSError as exc:
            raise TransactionError("no committed current generation") from exc
        target_parts = PurePosixPath(target).parts
        if not stat.S_ISLNK(pointer_status.st_mode) or len(target_parts) != 2 or \
                target_parts[0] != "generations" or \
                _identifier(target_parts[1]) != target_parts[1]:
            raise TransactionError("current pointer is not one direct generation")
        pointer_identity = (pointer_status.st_dev, pointer_status.st_ino)
        generation = root / "generations" / target_parts[1]
        _verify_generation(generation, target_parts[1])
        if _symlink_identity(root_fd, "current", target) != pointer_identity:
            raise TransactionError("current pointer changed while verifying")
        current_fd = os.open("current", os.O_RDONLY | os.O_DIRECTORY, dir_fd=root_fd)
        try:
            if _fd_identity(current_fd) != _directory_identity(generation):
                raise TransactionError("current target changed while verifying")
        finally:
            os.close(current_fd)
        return generation
    except OSError as exc:
        raise TransactionError("current generation is unsafe") from exc
    finally:
        os.close(root_fd)


def verify_current_generation(root: Path) -> Path:
    """Return the fully verified current generation for a publication root."""
    return _current(root)


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
