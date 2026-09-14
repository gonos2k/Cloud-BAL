#!/usr/bin/env python3
"""Atomic generation publisher for Cloud-BAL products.

Writers receive paths only inside ``ROOT/.staging/TRANSACTION``.  A complete
set is copied to detached regular-file inodes, hashed, marked, renamed as one
generation, and only then made current.  A retained writer descriptor remains
attached to the old staging inode and cannot alter the published bytes.
Failures before the current swap preserve the pointer. A post-swap failure
raises PublicationUncertainError: visibility has changed and durability must be
reconciled with recover(), without claiming rollback or crash certification.
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
import tempfile
import types
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
_VALIDATION = "validation"
_TRUSTED_VALIDATOR_FILES = {
    "verify_stage_off_generation": "verify_stage_off_generation.py",
    "validate_shadow_diagnostics": "validate_shadow_diagnostics.py",
    "verify_real_manufactured_balance_generation":
        "verify_real_manufactured_balance_generation.py",
}
_RENAME_NOREPLACE = 1


class TransactionError(RuntimeError):
    """The candidate generation is incomplete or violates its path contract."""


class PublicationUncertainError(TransactionError):
    """Current may already expose this generation; recover before retrying work."""


def _sync_tree(path: Path) -> None:
    """Sync regular files and directories bottom-up without following links."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        def sync(directory: int) -> None:
            for name in sorted(os.listdir(directory)):
                status = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(status.st_mode):
                    child = _open_directory_at(directory, name)
                    try:
                        sync(child)
                    finally:
                        os.close(child)
                else:
                    _regular_bytes_at(directory, name, sync=True)
            os.fsync(directory)
        sync(descriptor)
    finally:
        os.close(descriptor)


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
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _stable_regular_bytes(path: Path, *, sync: bool = False) -> tuple[bytes, os.stat_result]:
    """Read one regular, single-link file through one stable descriptor."""

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
        if _regular_status_identity(before) != _regular_status_identity(after) or \
                after.st_nlink != 1:
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
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
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
            if _regular_status_identity(before) != _regular_status_identity(after) or \
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


def _regular_status_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    """Return the identity fields used to detect a changing regular file."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def _open_or_create_directory_at(parent: int, name: str) -> int:
    """Open a child directory, creating it only when it is absent."""
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o750, dir_fd=parent)
        except FileExistsError:
            pass
    except OSError as exc:
        raise TransactionError(f"unsafe publication directory: {name}") from exc
    return _open_directory_at(parent, name)


def _snapshot_product_at(source_root: int, destination_root: int, product: str) -> None:
    """Copy one writer file into a fresh coordinator-owned regular inode.

    The destination is never the producer's namespace.  O_EXCL creation means
    a foreign path can only make this transaction fail; it is never replaced or
    removed.  A producer may retain a descriptor to the source inode, so source
    identity is checked around the copy and the generation uses only the
    detached destination inode.  No permission-bit change is treated as an
    immutability mechanism.
    """
    parts = PurePosixPath(_product(product)).parts
    source_parent = os.dup(source_root)
    destination_parent = os.dup(destination_root)
    source = None
    destination = None
    try:
        for component in parts[:-1]:
            child = _open_directory_at(source_parent, component)
            os.close(source_parent)
            source_parent = child
            child = _open_or_create_directory_at(destination_parent, component)
            os.close(destination_parent)
            destination_parent = child

        source = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=source_parent,
        )
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise TransactionError(f"unsafe file: {product}")

        chunks = []
        while True:
            chunk = os.read(source, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks)
        after_read = os.fstat(source)
        named = os.stat(parts[-1], dir_fd=source_parent, follow_symlinks=False)
        if (
            _regular_status_identity(before)
            != _regular_status_identity(after_read)
            or (named.st_dev, named.st_ino) != (after_read.st_dev, after_read.st_ino)
            or len(payload) != after_read.st_size
        ):
            raise TransactionError(f"file changed while snapshotting: {product}")

        try:
            destination = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                stat.S_IMODE(before.st_mode),
                dir_fd=destination_parent,
            )
        except OSError as exc:
            raise TransactionError(f"output snapshot destination is unsafe: {product}") from exc
        view = memoryview(payload)
        while view:
            written = os.write(destination, view)
            if written <= 0:
                raise TransactionError(f"failed to snapshot output: {product}")
            view = view[written:]
        os.fsync(destination)

        after_copy = os.fstat(source)
        named = os.stat(parts[-1], dir_fd=source_parent, follow_symlinks=False)
        if (
            _regular_status_identity(before)
            != _regular_status_identity(after_copy)
            or (named.st_dev, named.st_ino) != (after_copy.st_dev, after_copy.st_ino)
        ):
            raise TransactionError(f"file changed while snapshotting: {product}")

        destination_status = os.fstat(destination)
        destination_named = os.stat(
            parts[-1], dir_fd=destination_parent, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(destination_status.st_mode)
            or destination_status.st_nlink != 1
            or (destination_status.st_dev, destination_status.st_ino)
            != (destination_named.st_dev, destination_named.st_ino)
            or destination_status.st_size != len(payload)
        ):
            raise TransactionError(f"snapshot destination changed: {product}")
        os.fsync(destination_parent)
    except OSError as exc:
        raise TransactionError(f"output snapshot failed: {product}") from exc
    finally:
        if source is not None:
            os.close(source)
        if destination is not None:
            os.close(destination)
        os.close(source_parent)
        os.close(destination_parent)


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
    """Create metadata below a pinned parent; failed temps remain for review."""

    try:
        parent = os.open(
            path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as exc:
        raise TransactionError(f"unsafe metadata parent: {path.parent.name}") from exc
    temporary = f".{path.name}.tmp"
    descriptor = None
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
        os.fsync(parent)
    except OSError as exc:
        raise TransactionError(f"unsafe metadata write: {path.name}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
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


def _trusted_validator_source_sha256(name: str) -> str:
    """Hash one allowlisted validator from this trusted tools directory."""
    filename = _TRUSTED_VALIDATOR_FILES.get(name)
    if filename is None:
        raise TransactionError("snapshot validation receipt validator is not trusted")
    source = Path(__file__).resolve().with_name(filename)
    try:
        payload, _ = _stable_regular_bytes(source)
    except TransactionError as exc:
        raise TransactionError("trusted snapshot validator source is unavailable") from exc
    return hashlib.sha256(payload).hexdigest()


def _validate_validation_receipt(
    receipt: object,
    context: dict,
    snapshot: Path,
    records: list[dict],
) -> dict:
    """Bind a semantic PASS receipt to one snapshot and its exact product hashes."""
    required = {
        "schema", "status", "transaction_id", "snapshot_identity",
        "validator", "products",
    }
    if not isinstance(receipt, dict) or set(receipt) != required or \
            receipt.get("schema") != 1 or receipt.get("status") != "PASS" or \
            receipt.get("transaction_id") != context["transaction_id"]:
        raise TransactionError("snapshot validation receipt is invalid")
    if receipt.get("snapshot_identity") != _directory_identity(snapshot):
        raise TransactionError("snapshot validation receipt identity is invalid")
    validator = receipt.get("validator")
    if not isinstance(validator, dict) or set(validator) != {"name", "source_sha256"} or \
            not isinstance(validator.get("name"), str) or not validator["name"].strip() or \
            not isinstance(validator.get("source_sha256"), str) or \
            not re.fullmatch(r"[0-9a-f]{64}", validator["source_sha256"]):
        raise TransactionError("snapshot validation receipt validator is invalid")
    if context["require_validation"] and (
        validator["name"] not in _TRUSTED_VALIDATOR_FILES
        or validator["source_sha256"] != _trusted_validator_source_sha256(validator["name"])
    ):
        raise TransactionError("snapshot validation receipt validator is not trusted")
    if receipt.get("products") != records:
        raise TransactionError("snapshot validation receipt products differ")
    return receipt


def _execute_trusted_validator(name: str, snapshot: Path) -> dict:
    """Execute the allowlisted source itself; a public PASS dictionary is no proof."""
    filename = _TRUSTED_VALIDATOR_FILES.get(name)
    if filename is None:
        raise TransactionError("snapshot validator is not trusted")
    source = Path(__file__).resolve().with_name(filename)
    payload, _ = _stable_regular_bytes(source)
    module = types.ModuleType("_cloud_bal_publication_validator")
    module.__file__ = str(source)
    try:
        exec(compile(payload, str(source), "exec"), module.__dict__)
        if name == "validate_shadow_diagnostics":
            return module.validate_snapshot(snapshot)
        if name == "verify_real_manufactured_balance_generation":
            repo = source.parent.parent
            return module.verify_snapshot(
                snapshot, repo / "tests/qbal_real_manufactured_cases_20260816.tsv", repo
            )
        return module.verify_snapshot(snapshot)
    except Exception as exc:
        raise TransactionError(f"trusted semantic validation failed: {exc}") from exc


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
            if error in {
                errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP
            }:
                raise TransactionError(
                    "publication filesystem does not support atomic "
                    "no-replace generation rename"
                )
            if error == errno.EXDEV:
                raise TransactionError(
                    "cannot atomically move generation across a filesystem or "
                    "mount boundary"
                )
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


def _validate_staging_namespace(root: Path) -> None:
    """Reject non-regular producer entries without opening their contents."""
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise TransactionError("transaction staging directory is unsafe") from exc

    def walk(directory: int) -> None:
        try:
            names = sorted(os.listdir(directory))
            for name in names:
                status = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(status.st_mode):
                    child = _open_directory_at(directory, name)
                    try:
                        walk(child)
                    finally:
                        os.close(child)
                elif not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                    raise TransactionError(f"transaction staging contains unsafe entry: {name}")
        except OSError as exc:
            raise TransactionError("transaction staging changed while checking safety") from exc

    try:
        walk(descriptor)
    finally:
        os.close(descriptor)


def _validate_context(context: object, transaction_id: str) -> dict:
    expected_keys = {
        "schema", "transaction_id", "products", "source_commit",
        "configuration", "valid_time", "expected_current", "owner_nonce",
        "publication_identity", "require_validation",
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
    if not isinstance(context.get("require_validation"), bool):
        raise TransactionError("validation requirement is invalid")
    nonce = context.get("owner_nonce")
    identities = context.get("publication_identity")
    required_identities = {
        "root", "staging_parent", "generations", "owners", "staging",
        "snapshot",
    }
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise TransactionError("transaction owner nonce is invalid")
    if not isinstance(identities, dict) or set(identities) != required_identities or \
            not all(_valid_directory_identity(value) for value in identities.values()):
        raise TransactionError("transaction publication identity is invalid")
    return context


class OutputTransaction:
    """One detached set of declared output products."""

    def __init__(self, root: Path | str, transaction_id: str):
        self.root = Path(os.path.abspath(root))
        component_path = Path(self.root.anchor)
        for component in self.root.parts[1:]:
            component_path /= component
            if component_path.is_symlink():
                raise TransactionError("publication root cannot contain a symlink")
        self.transaction_id = _identifier(transaction_id)
        self.staging_parent = self.root / ".staging"
        self.snapshot_parent = self.root / ".snapshots"
        self.generations = self.root / "generations"
        self.owner_parent = self.root / _OWNERS
        self.staging = self.staging_parent / self.transaction_id
        self.snapshot = self.snapshot_parent / self.transaction_id
        self.generation = self.generations / self.transaction_id
        self.owner = self.owner_parent / f"{self.transaction_id}.json"

    def _validate_layout(self, *, require_staging: bool) -> None:
        root = self.root.resolve(strict=True)
        for directory in (
            self.staging_parent,
            self.snapshot_parent,
            self.generations,
            self.owner_parent,
        ):
            if directory.is_symlink() or not directory.is_dir() or \
                directory.resolve(strict=True).parent != root:
                raise TransactionError("publication directories escaped their root")
        devices = {
            directory.stat(follow_symlinks=False).st_dev
            for directory in (
                self.staging_parent,
                self.snapshot_parent,
                self.generations,
                self.owner_parent,
            )
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
            "staging": _directory_identity(self.staging),
            "snapshot": _directory_identity(transaction_path or self.snapshot),
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
        require_validation: bool = False,
    ) -> None:
        if not isinstance(require_validation, bool):
            raise TransactionError("validation requirement must be a boolean")
        normalized = [_product(item) for item in products]
        if len(normalized) != len(set(normalized)):
            raise TransactionError("output products must have unique identities")
        declared = sorted(normalized)
        if not declared:
            raise TransactionError("at least one output product is required")
        self.root.mkdir(parents=True, exist_ok=True)
        if self.staging_parent.is_symlink() or self.snapshot_parent.is_symlink() or \
                self.generations.is_symlink() or self.owner_parent.is_symlink():
            raise TransactionError("publication directories must not be symlinks")
        self.staging_parent.mkdir(exist_ok=True)
        self.snapshot_parent.mkdir(exist_ok=True)
        self.generations.mkdir(exist_ok=True)
        self.owner_parent.mkdir(exist_ok=True)
        self._validate_layout(require_staging=False)
        if self.staging.exists() or self.snapshot.exists() or self.generation.exists() or \
                self.owner.exists() or self.staging.is_symlink() or \
                self.snapshot.is_symlink() or self.generation.is_symlink() or \
                self.owner.is_symlink():
            raise TransactionError("transaction identifier already exists")

        with _publication_lock(self.root):
            expected_current = _current_id(self.root)
        self.staging.mkdir(mode=0o750)
        self.snapshot.mkdir(mode=0o750)
        context = {
            "schema": 2,
            "transaction_id": self.transaction_id,
            "products": declared,
            "source_commit": source_commit,
            "configuration": configuration,
            "valid_time": valid_time,
            "require_validation": require_validation,
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
        _fsync_directory(self.snapshot)
        _fsync_directory(self.snapshot_parent)
        _fsync_directory(self.owner_parent)
        _fsync_directory(self.root)

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

    def _snapshot_outputs(self, context: dict, context_sha256: str) -> None:
        """Copy declared writer outputs into the fresh coordinator snapshot."""
        staging = None
        snapshot = None
        try:
            staging = os.open(
                self.staging,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            snapshot = os.open(
                self.snapshot,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as exc:
            if staging is not None:
                os.close(staging)
            raise TransactionError("transaction staging directory is unsafe") from exc
        try:
            if _fd_identity(staging) != context["publication_identity"]["staging"]:
                raise TransactionError("transaction staging directory changed")
            if _fd_identity(snapshot) != context["publication_identity"]["snapshot"]:
                raise TransactionError("transaction snapshot directory changed")
            if _product_inventory_at(snapshot):
                raise TransactionError("transaction snapshot is not empty")
            for name in (_CONTEXT, _MANIFEST, _COMMITTED):
                try:
                    os.stat(name, dir_fd=snapshot, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise TransactionError("transaction snapshot already contains metadata")
            for product in context["products"]:
                _snapshot_product_at(staging, snapshot, product)
            context_payload, _ = _stable_regular_bytes(self.staging / _CONTEXT)
            if hashlib.sha256(context_payload).hexdigest() != context_sha256:
                raise TransactionError("transaction context changed while snapshotting")
            _write_atomic(self.snapshot / _CONTEXT, context_payload)
        finally:
            os.close(staging)
            os.close(snapshot)

    def prepare(self) -> Path:
        """Copy producer outputs into a sealed coordinator snapshot for validation."""
        self._validate_layout(require_staging=True)
        if self.generation.exists() or self.generation.is_symlink():
            raise TransactionError("transaction generation already exists")
        if self.snapshot.is_symlink() or not self.snapshot.is_dir():
            raise TransactionError("transaction snapshot directory is unsafe")
        context, context_sha256 = self._context_record()
        self._require_owner(context, context_sha256)
        self._assert_publication_identity(context)
        _validate_staging_namespace(self.staging)
        if _product_inventory(self.staging) != set(context["products"]):
            raise TransactionError("staging contains undeclared or missing products")
        self._snapshot_outputs(context, context_sha256)
        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        return self.snapshot

    def _snapshot_records(self, context: dict) -> list[dict]:
        snapshot_real = self.snapshot.resolve(strict=True)
        records = []
        for product in context["products"]:
            path = self.snapshot.joinpath(*PurePosixPath(product).parts)
            if path.is_symlink() or not path.is_file() or \
                    path.stat(follow_symlinks=False).st_nlink != 1:
                raise TransactionError(f"missing or unsafe snapshot product: {product}")
            if not _inside(path.resolve(strict=True), snapshot_real):
                raise TransactionError(f"output product escapes snapshot root: {product}")
            records.append(_product_record(path, product))
        return records

    def _assert_snapshot_context(self, context: dict, context_sha256: str) -> None:
        try:
            payload, _ = _stable_regular_bytes(self.snapshot / _CONTEXT)
        except TransactionError as exc:
            raise TransactionError("prepared snapshot context is missing or invalid") from exc
        if hashlib.sha256(payload).hexdigest() != context_sha256 or \
                _validate_context(_parse_json(payload, _CONTEXT), self.transaction_id) != context:
            raise TransactionError("prepared snapshot context differs from staging")

    def commit(self, *, validation_receipt: dict | None = None) -> dict:
        """Snapshot writer outputs, then publish the verified generation.

        Generic callers may commit directly, which prepares a detached snapshot
        internally.  Science callers must call prepare(), run their semantic
        validator on the returned snapshot, and pass its explicit validation
        receipt here before publication.
        """
        self._validate_layout(require_staging=True)
        if self.generation.exists() or self.generation.is_symlink():
            raise TransactionError("transaction generation already exists")
        if self.snapshot.is_symlink() or not self.snapshot.is_dir():
            raise TransactionError("transaction snapshot directory is unsafe")
        context, context_sha256 = self._context_record()
        self._require_owner(context, context_sha256)
        self._assert_publication_identity(context)
        snapshot_has_entries = any(self.snapshot.iterdir())
        if snapshot_has_entries:
            if validation_receipt is None:
                raise TransactionError("prepared snapshot requires validation receipt")
            self._assert_snapshot_context(context, context_sha256)
            if _product_inventory(self.snapshot) != set(context["products"]):
                raise TransactionError("prepared snapshot contains undeclared or missing products")
        elif context["require_validation"]:
            raise TransactionError(
                "required validation transaction must prepare a snapshot before commit"
            )
        else:
            self.prepare()
            context, context_sha256 = self._context_record()
            self._require_owner(context, context_sha256)
            self._assert_publication_identity(context)
        self._inject("after_snapshot")
        records = self._snapshot_records(context)
        if validation_receipt is not None:
            validation_receipt = _validate_validation_receipt(
                validation_receipt, context, self.snapshot, records
            )
            if context["require_validation"]:
                executed = _execute_trusted_validator(
                    validation_receipt["validator"]["name"], self.snapshot
                )
                fresh_records = self._snapshot_records(context)
                executed = _validate_validation_receipt(
                    executed, context, self.snapshot, fresh_records
                )
                if executed != validation_receipt or fresh_records != records:
                    raise TransactionError("executed validation differs from supplied receipt")
                validation_receipt = executed

        manifest = {
            **context,
            "committed_utc": datetime.now(timezone.utc).isoformat(),
            "products": records,
        }
        if validation_receipt is not None:
            manifest[_VALIDATION] = validation_receipt
        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        _write_json_atomic(self.snapshot / _MANIFEST, manifest)
        self._inject("after_manifest")
        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        _write_marker(self.snapshot / _COMMITTED, self.transaction_id)
        _fsync_directory(self.snapshot)
        self._inject("after_marker")

        self._validate_layout(require_staging=True)
        self._assert_publication_identity(context)
        if validation_receipt is None:
            _validate_staging_namespace(self.staging)
            if _product_inventory(self.staging) != set(context["products"]):
                raise TransactionError("staging contains undeclared or missing products")
        # The producer namespace is deliberately not consulted after the
        # detached snapshot has been validated.  A retained writer may close,
        # replace, or mutate staging paths; none of those operations can alter
        # the bytes accepted by the semantic validator.
        _sync_tree(self.snapshot)
        _rename_noreplace(self.snapshot, self.generation)
        self._assert_publication_identity(context, self.generation)
        self._inject("after_generation_rename")
        _verify_generation(self.generation, self.transaction_id)

        return self._publish(context, manifest)

    def recover(self) -> dict:
        """Reconcile a complete renamed generation; never rebuild staged metadata.

        A changed current or any failed integrity check requires intervention.
        Successful resynchronization is a local syscall result, not evidence of
        power-loss durability on a particular filesystem.
        """
        self._validate_layout(require_staging=False)
        if self.snapshot.exists() or self.snapshot.is_symlink():
            raise TransactionError("unrenamed transaction snapshot requires intervention")
        _verify_generation(self.generation, self.transaction_id)
        context = _read_json(self.generation / _CONTEXT)
        manifest = _read_json(self.generation / _MANIFEST)
        return self._publish(context, manifest, recovery=True)

    def _publish(self, context: dict, manifest: dict, *, recovery: bool = False) -> dict:
        swapped = False
        try:
            with _publication_lock(self.root) as root_descriptor:
                current_id = _current_id(self.root)
                if recovery and current_id == self.transaction_id:
                    swapped = True
                    self._sync_recovery(context)
                    os.fsync(root_descriptor)
                    return manifest
                if current_id != context["expected_current"]:
                    raise TransactionError("current generation changed during the transaction")
                if current_id is not None:
                    current_manifest = _read_json(
                        self.generations / current_id / _MANIFEST
                    )
                    if context["valid_time"] < current_manifest["valid_time"]:
                        raise TransactionError("an older analysis cannot replace current")
                if recovery:
                    self._sync_recovery(context)
                temporary_name = f".current.{self.transaction_id}.tmp"
                target = f"generations/{self.transaction_id}"
                try:
                    os.stat(temporary_name, dir_fd=root_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    os.symlink(target, temporary_name, dir_fd=root_descriptor)
                else:
                    if not recovery:
                        raise TransactionError("temporary current pointer already exists")
                    # Explicit recovery may reuse a matching orphan left by process exit.
                    # No foreign target is overwritten or unlinked on rejection.
                    _symlink_identity(root_descriptor, temporary_name, target)
                temporary_identity = _symlink_identity(
                    root_descriptor, temporary_name, target
                )
                # Keep the temporary pointer after a pre-swap failure. A
                # check-then-unlink cleanup could delete a replacement at this
                # pathname; recover() validates and handles matching orphans.
                self._inject("before_current_swap")
                _verify_generation(self.generation, self.transaction_id)
                if _symlink_identity(root_descriptor, temporary_name, target) != \
                        temporary_identity:
                    raise TransactionError("temporary current pointer changed")
                if _directory_identity(self.generation) != \
                        context["publication_identity"]["snapshot"]:
                    raise TransactionError("verified generation changed before publication")
                os.replace(
                    temporary_name,
                    "current",
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                )
                swapped = True
                if _symlink_identity(root_descriptor, "current", target) != \
                        temporary_identity:
                    raise TransactionError("published current pointer changed")
                os.fsync(root_descriptor)
        except Exception as exc:
            if swapped:
                raise PublicationUncertainError(
                    "current exposes this generation; publication completion is uncertain; run recover"
                ) from exc
            raise
        return manifest

    def _sync_recovery(self, context: dict) -> None:
        self._assert_publication_identity(context, self.generation)
        _verify_generation(self.generation, self.transaction_id)
        _sync_tree(self.generation)
        _fsync_directory(self.staging_parent)
        _fsync_directory(self.generations)
        _fsync_directory(self.owner_parent)
        _verify_generation(self.generation, self.transaction_id)

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
            staging_parent_fd = _open_directory_at(root_fd, ".staging")
            opened.append(staging_parent_fd)
            snapshot_parent_fd = _open_directory_at(root_fd, ".snapshots")
            opened.append(snapshot_parent_fd)
            generations_fd = _open_directory_at(root_fd, "generations")
            opened.append(generations_fd)
            owners_fd = _open_directory_at(root_fd, _OWNERS)
            opened.append(owners_fd)
            staging_fd = _open_directory_at(staging_parent_fd, generation.name)
            opened.append(staging_fd)
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
                "staging_parent": _fd_identity(staging_parent_fd),
                "generations": _fd_identity(generations_fd),
                "owners": _fd_identity(owners_fd),
                "staging": _fd_identity(staging_fd),
                "snapshot": _fd_identity(generation_fd),
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
            validation_receipt = manifest.get(_VALIDATION)
            if context["require_validation"] and validation_receipt is None:
                raise TransactionError(
                    "generation lacks required semantic validation receipt"
                )
            if validation_receipt is not None:
                _validate_validation_receipt(
                    validation_receipt,
                    context,
                    generation,
                    records,
                )
            manifest_context = {
                name: manifest.get(name) for name in context if name != "products"
            }
            manifest_context["products"] = sorted(declared)
            expected_manifest_keys = set(context) | {"committed_utc"}
            if validation_receipt is not None:
                expected_manifest_keys.add(_VALIDATION)
            if manifest_context != context or set(manifest) != expected_manifest_keys:
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


def preflight_publication_filesystem(root: Path | str) -> dict:
    """Exercise publication primitives in a disposable child of an existing root.

    This is a local capability check, not a crash-durability or multi-host lock
    certification. Existing publication directories and current are never used.
    """

    root = OutputTransaction(root, "preflight").root
    try:
        identity = _directory_identity(root)
        for name in (".staging", ".snapshots", "generations", _OWNERS):
            directory = root / name
            if directory.exists() or directory.is_symlink():
                if _directory_identity(directory)[0] != identity[0]:
                    raise TransactionError("publication layout is on another filesystem")
        with tempfile.TemporaryDirectory(prefix=".cloud-bal-preflight-", dir=root) as temporary:
            probe = Path(temporary)
            if probe.stat().st_dev != identity[0]:
                raise TransactionError("preflight scratch is on another filesystem")

            # Separate open descriptions must contend on the actual directory lock.
            with _publication_lock(probe):
                descriptor = os.open(probe, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        raise TransactionError("publication directory lock does not exclude contenders")
                finally:
                    os.close(descriptor)

            source = probe / "collision-source"
            destination = probe / "collision-target"
            source.mkdir()
            destination.mkdir()
            before = (_directory_identity(source), _directory_identity(destination))
            try:
                _rename_noreplace(source, destination)
            except TransactionError as exc:
                if str(exc) != "generation target already exists":
                    raise
            else:
                raise TransactionError("no-replace rename overwrote an existing target")
            if before != (_directory_identity(source), _directory_identity(destination)):
                raise TransactionError("no-replace collision changed a directory")

            publication = probe / "publication"
            transactions = [OutputTransaction(publication, name) for name in ("first", "stale")]
            for transaction in transactions:
                transaction.begin(
                    ["product"], source_commit="0" * 40,
                    configuration="filesystem-preflight-only",
                )
                transaction.resolve_output("product").write_bytes(b"filesystem preflight\n")
            transactions[0].commit()
            first = _current(publication)
            try:
                transactions[1].commit()
            except TransactionError as exc:
                if str(exc) != "current generation changed during the transaction":
                    raise
            else:
                raise TransactionError("stale publication compare-and-swap was accepted")
            if _current(publication) != first:
                raise TransactionError("stale publication changed current")

            replacement = OutputTransaction(publication, "replacement")
            replacement.begin(
                ["product"], source_commit="0" * 40,
                configuration="filesystem-preflight-only",
            )
            replacement.resolve_output("product").write_bytes(b"replacement\n")
            replacement.commit()
            if _current(publication) != replacement.generation:
                raise TransactionError("publication current replacement failed")
        if _directory_identity(root) != identity:
            raise TransactionError("publication root changed during preflight")
        _fsync_directory(root)
    except OSError as exc:
        raise TransactionError(f"publication filesystem preflight failed: {exc}") from exc
    return {
        "schema": 1,
        "status": "PASS",
        "root": str(root),
        "root_identity": identity,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "checks": ["directory_lock_exclusion", "rename_noreplace_collision",
                   "generation_rename", "file_and_directory_fsync",
                   "stale_current_rejection", "current_replacement"],
        "scope": "private child on root filesystem; local syscall capability only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="probe an existing root using disposable files")
    preflight.add_argument("root", type=Path)

    begin = subparsers.add_parser("begin")
    begin.add_argument("root", type=Path)
    begin.add_argument("transaction_id")
    begin.add_argument("products", nargs="+")
    begin.add_argument("--source-commit", required=True)
    begin.add_argument("--configuration", required=True)
    begin.add_argument("--valid-time", required=True, type=int)
    begin.add_argument(
        "--require-validation",
        action="store_true",
        help="require prepare plus an exact semantic validation receipt before commit",
    )

    prepare = subparsers.add_parser(
        "prepare", help="detach outputs into a snapshot for semantic validation"
    )
    prepare.add_argument("root", type=Path)
    prepare.add_argument("transaction_id")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("root", type=Path)
    resolve.add_argument("transaction_id")
    resolve.add_argument("product")

    commit = subparsers.add_parser("commit")
    commit.add_argument("root", type=Path)
    commit.add_argument("transaction_id")
    commit.add_argument(
        "--validation-receipt", type=Path,
        help="JSON receipt returned by a semantic snapshot validator",
    )

    recover = subparsers.add_parser("recover", help="reconcile a complete renamed generation")
    recover.add_argument("root", type=Path)
    recover.add_argument("transaction_id")

    current = subparsers.add_parser("current")
    current.add_argument("root", type=Path)

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "preflight":
            print(json.dumps(preflight_publication_filesystem(arguments.root), sort_keys=True))
        elif arguments.command == "begin":
            transaction = OutputTransaction(arguments.root, arguments.transaction_id)
            transaction.begin(
                arguments.products,
                source_commit=arguments.source_commit,
                configuration=arguments.configuration,
                valid_time=arguments.valid_time,
                require_validation=arguments.require_validation,
            )
            print(transaction.staging)
        elif arguments.command == "prepare":
            transaction = OutputTransaction(arguments.root, arguments.transaction_id)
            print(transaction.prepare())
        elif arguments.command == "resolve":
            print(OutputTransaction(arguments.root, arguments.transaction_id).resolve_output(arguments.product))
        elif arguments.command in {"commit", "recover"}:
            transaction = OutputTransaction(arguments.root, arguments.transaction_id)
            if arguments.command == "commit":
                receipt = (
                    None if arguments.validation_receipt is None
                    else _read_json(arguments.validation_receipt)
                )
                manifest = transaction.commit(validation_receipt=receipt)
            else:
                manifest = transaction.recover()
            print(json.dumps(manifest, sort_keys=True))
        else:
            print(_current(arguments.root))
    except PublicationUncertainError as exc:
        print(f"cloud-bal publication uncertain: {exc}", file=sys.stderr)
        return 3
    except (TransactionError, OSError) as exc:
        print(f"cloud-bal transaction rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
