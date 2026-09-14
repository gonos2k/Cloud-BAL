#!/usr/bin/env python3
"""Stage a source-bound CP02 metadata correction in a fresh directory.

The legacy writer creates NetCDF products from CDL files.  Its ``units``
arguments do not reach the C writer, so this tool changes only the CDL
metadata that the writer actually consumes.  It deliberately does not edit
the operational ``ANAL`` tree or product data.

The correction removes the stale ``valid_range`` declarations identified by
the CP02 source review.  No replacement range is inferred from observations:
the attribute is optional and there is no formal public range in the reviewed
contract.  PBL navigation is populated only when an exact, hash-bound static
grid is supplied.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping


class MetadataStageError(RuntimeError):
    """The requested metadata staging operation is unsafe or incomplete."""


PRODUCT_VARIABLES: dict[str, tuple[str, ...]] = {
    "lt1.cdl": ("t3",),
    "lh3.cdl": ("rh3", "rhl"),
    "lmr.cdl": ("r",),
    "lmt.cdl": ("lmt", "llr"),
    "pbl.cdl": ("ptp", "pdm"),
}

# These are the exact stale declarations covered by the source review.  A
# changed source must be reviewed again rather than silently transformed.
STALE_RANGE_TEXT: dict[tuple[str, str], str] = {
    ("lt1.cdl", "t3"): "0.f,100.f",
    ("lh3.cdl", "rh3"): "0.f,0.100f",
    ("lh3.cdl", "rhl"): "0.f,0.100f",
    ("lmr.cdl", "r"): "0.f,0.100f",
    ("lmt.cdl", "lmt"): "0.f,0.100f",
    ("lmt.cdl", "llr"): "0.f,0.100f",
    ("pbl.cdl", "ptp"): "0.f,10000.f",
    ("pbl.cdl", "pdm"): "0.f,6.0f",
}

RANGE_RATIONALE: dict[tuple[str, str], str] = {
    ("lt1.cdl", "t3"): (
        "Source writes Kelvin (K), while the 0..100 declaration masks the "
        "finite Kelvin field. No formal public interval was found; retain "
        "the source units and omit this optional declaration."
    ),
    ("lh3.cdl", "rh3"): (
        "Source labels the field percent and clamps it to 0..100, while the "
        "0..0.1 declaration masks percentage values. No fraction conversion "
        "or replacement public interval is inferred."
    ),
    ("lh3.cdl", "rhl"): (
        "Source labels the field percent and clamps it to 0..100, while the "
        "0..0.1 declaration masks percentage values. No fraction conversion "
        "or replacement public interval is inferred."
    ),
    ("lmr.cdl", "r"): (
        "Source writes dBZ, including negative values, while 0..0.1 is an "
        "incompatible declaration. Radar missing/base semantics and the "
        "formal dBZ domain remain separate contract questions."
    ),
    ("lmt.cdl", "lmt"): (
        "Source writes echo-top height in meters, while 0..0.1 is an "
        "incompatible declaration. No height interval is inferred from "
        "observed extrema."
    ),
    ("lmt.cdl", "llr"): (
        "Source writes low-level reflectivity in dBZ, while 0..0.1 is an "
        "incompatible declaration. Radar missing/base semantics and the "
        "formal dBZ domain remain separate contract questions."
    ),
    ("pbl.cdl", "ptp"): (
        "Source writes PBL-top pressure in pascals, while 0..10000 is not a "
        "formal public range in the reviewed contract. No pressure interval "
        "is inferred from observed extrema."
    ),
    ("pbl.cdl", "pdm"): (
        "Source writes PBL depth in meters, while 0..6 is not a formal public "
        "range in the reviewed contract. No depth interval is inferred from "
        "observed extrema."
    ),
}

PBL_NAV_NUMERIC = ("Nx", "Ny", "La1", "Lo1", "LoV", "Latin1", "Latin2", "Dx", "Dy")
PBL_NAV_TEXT = ("grid_type", "x_dim", "y_dim")
PBL_ORIGIN_TEXT = "origin_name"
PBL_REQUIRED_GRID_DIMENSIONS = ("x", "y", "nav", "namelen")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The CP02 replay manifest (tests/original_upstream_replay_20260816.json) and
# QBAL real-input contract (tools/check_qbal_real_inputs.py) pin this exact
# static grid. A caller-provided digest is checked against this authority; it
# is not allowed to authorize an arbitrary same-shape grid.
CANONICAL_STATIC_GRID_SHA256 = (
    "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b"
)
GRID_AUTHORITY = (
    "tests/original_upstream_replay_20260816.json + "
    "tools/check_qbal_real_inputs.py:STATIC_INPUTS"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_identity(status: os.stat_result) -> tuple[int, int, int, int]:
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)


def _identity_record(identity: tuple[int, int, int, int]) -> dict[str, int]:
    return {
        "device": identity[0],
        "inode": identity[1],
        "size": identity[2],
        "mtime_ns": identity[3],
    }


def _read_bound_file(path: Path, label: str) -> tuple[bytes, str, tuple[int, int, int, int]]:
    """Read and hash one stable regular-file descriptor exactly once."""

    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        )
    except OSError as exc:
        raise MetadataStageError(f"{label} cannot be opened safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MetadataStageError(f"{label} must be a regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            raise MetadataStageError(f"{label} changed while being read: {path}")
        payload = b"".join(chunks)
        if len(payload) != before.st_size:
            raise MetadataStageError(f"{label} size changed while being read: {path}")
        digest = hashlib.sha256(payload).hexdigest()
        return payload, digest, _file_identity(before)
    finally:
        os.close(descriptor)


def _source_root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise MetadataStageError(f"source directory must be a real directory: {path}")
    return path.resolve()


def _output_root(path: Path, source_root: Path) -> Path:
    resolved = path.resolve()
    if "ANAL" in resolved.parts:
        raise MetadataStageError("metadata output under operational ANAL is forbidden")
    try:
        resolved.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise MetadataStageError("metadata output must be outside the source directory")
    if path.is_symlink() or path.exists():
        raise MetadataStageError(f"metadata output must be a fresh path: {path}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MetadataStageError(
            f"metadata output parent must be a directory: {path.parent}"
        ) from exc
    if not path.parent.is_dir():
        raise MetadataStageError(
            f"metadata output parent must be a directory: {path.parent}"
        )
    return resolved


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing a racing target."""

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
        raise MetadataStageError("metadata publication parent is unsafe") from exc
    try:
        renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
        if renameat2 is None:
            raise MetadataStageError("atomic no-replace directory publication is unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(
            source_parent,
            os.fsencode(source.name),
            destination_parent,
            os.fsencode(destination.name),
            1,  # RENAME_NOREPLACE
        ) != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise MetadataStageError("metadata output appeared during publication")
            if error in {errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}:
                raise MetadataStageError("filesystem lacks atomic no-replace directory publication")
            if error == errno.EXDEV:
                raise MetadataStageError("metadata stage crosses a filesystem boundary")
            raise MetadataStageError(f"metadata publication failed: {os.strerror(error)}")
        os.fsync(source_parent)
        os.fsync(destination_parent)
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _validate_expected_hashes(
    expected: Mapping[str, str] | None,
) -> dict[str, str]:
    if expected is None:
        raise MetadataStageError(
            "expected source SHA256 values are required for hash-bound staging"
        )
    normalized = {str(name): str(value).lower() for name, value in expected.items()}
    if set(normalized) != set(PRODUCT_VARIABLES):
        missing = sorted(set(PRODUCT_VARIABLES) - set(normalized))
        extra = sorted(set(normalized) - set(PRODUCT_VARIABLES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise MetadataStageError("source hash map must cover exactly the five CDLs (" + "; ".join(details) + ")")
    for name, value in normalized.items():
        if not HEX64.fullmatch(value):
            raise MetadataStageError(f"invalid SHA256 for {name}: {value!r}")
    return normalized


def _normalize_range(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _remove_stale_ranges(name: str, payload: str) -> tuple[str, list[dict[str, str]]]:
    transformations: list[dict[str, str]] = []
    result = payload
    for variable in PRODUCT_VARIABLES[name]:
        pattern = re.compile(
            rf"(?m)^(?P<indent>[ \t]*){re.escape(variable)}:valid_range"
            rf"[ \t]*=[ \t]*(?P<value>[^;\n]+)[ \t]*;[^\n]*(?:\n|$)"
        )
        matches = list(pattern.finditer(result))
        if len(matches) != 1:
            raise MetadataStageError(
                f"{name}:{variable} must contain exactly one valid_range declaration"
            )
        match = matches[0]
        expected = STALE_RANGE_TEXT[(name, variable)]
        actual = _normalize_range(match.group("value"))
        if actual != expected:
            raise MetadataStageError(
                f"{name}:{variable} has reviewed-contract range {expected!r}, found {actual!r}"
            )
        result = result[: match.start()] + result[match.end() :]
        transformations.append(
            {
                "product": name.removesuffix(".cdl"),
                "variable": variable,
                "action": "remove_optional_attribute",
                "attribute": "valid_range",
                "source_declaration": actual,
                "rationale": RANGE_RATIONALE[(name, variable)],
            }
        )
    return result, transformations


def _dimension_length(dataset: Any, name: str) -> int:
    dimension = dataset.dimensions.get(name)
    if dimension is None or dimension.isunlimited():
        raise MetadataStageError(f"static grid has no fixed {name} dimension")
    return len(dimension)


def _scalar_grid_value(dataset: Any, name: str) -> Any:
    variable = dataset.variables.get(name)
    if variable is None:
        raise MetadataStageError(f"static grid is missing required navigation variable {name}")
    values = variable[:]
    if hasattr(values, "mask") and getattr(values, "mask").any():
        raise MetadataStageError(f"static grid navigation {name} contains fill values")
    if getattr(values, "size", 0) != 1:
        raise MetadataStageError(f"static grid navigation {name} must contain one value")
    return values.reshape(-1)[0]


def _grid_text_value(dataset: Any, name: str) -> str:
    variable = dataset.variables.get(name)
    if variable is None:
        raise MetadataStageError(f"static grid is missing required navigation variable {name}")
    values = variable[:]
    if getattr(values, "ndim", 0) == 2 and values.shape[0] == 1:
        values = values[0]
    elif getattr(values, "ndim", 0) != 1:
        raise MetadataStageError(f"static grid navigation {name} must be a one-row character array")
    if hasattr(values, "filled"):
        values = values.filled(b"\x00")
    return _decode_grid_text(values, name)


def _decode_grid_text(value: Any, name: str) -> str:
    raw = value.tobytes() if hasattr(value, "tobytes") else bytes(value)
    try:
        text = raw.decode("ascii").rstrip("\x00 ")
    except UnicodeDecodeError as exc:
        raise MetadataStageError(f"static grid {name} is not ASCII") from exc
    if not text or any(char in text for char in "\r\n\""):
        raise MetadataStageError(f"static grid {name} is empty or cannot be represented in CDL")
    return text


def _load_grid(path: Path, expected_sha256: str, pbl_payload: str) -> dict[str, Any]:
    grid = Path(path)
    grid_bytes, actual_hash, identity = _read_bound_file(grid, "static grid")
    expected = expected_sha256.lower()
    if not HEX64.fullmatch(expected) or expected != CANONICAL_STATIC_GRID_SHA256:
        raise MetadataStageError(
            "static grid SHA256 must equal the pinned CP02 contract identity "
            f"{CANONICAL_STATIC_GRID_SHA256}"
        )
    if actual_hash != expected:
        raise MetadataStageError(
            f"static grid SHA256 mismatch: expected {expected}, found {actual_hash}"
        )
    try:
        import netCDF4  # type: ignore
    except ImportError as exc:
        raise MetadataStageError("netCDF4 is required to validate PBL navigation") from exc

    # Derive the declared product domain from the staged PBL template itself.
    dimensions_match = re.search(r"(?ms)dimensions:\s*(.*?)\bvariables:", pbl_payload)
    if dimensions_match is None:
        raise MetadataStageError("PBL CDL has no parseable dimensions section")
    dimensions_text = dimensions_match.group(1)
    declared_dimensions: dict[str, int] = {}
    for dimension in ("x", "y", "namelen"):
        match = re.search(rf"(?m)^\s*{dimension}\s*=\s*(\d+)\s*[;,]", dimensions_text)
        if match is None:
            raise MetadataStageError(f"PBL CDL has no fixed {dimension} dimension")
        declared_dimensions[dimension] = int(match.group(1))

    # Open the exact bytes already hashed above. Re-opening ``grid`` by path
    # would allow a replacement between verification and consumption.
    with netCDF4.Dataset("cp02-static-grid", "r", memory=grid_bytes) as dataset:
        for name in PBL_REQUIRED_GRID_DIMENSIONS:
            if name not in dataset.dimensions:
                raise MetadataStageError(f"static grid is missing dimension {name}")
        if _dimension_length(dataset, "x") != declared_dimensions["x"]:
            raise MetadataStageError("static grid x dimension does not match staged PBL CDL")
        if _dimension_length(dataset, "y") != declared_dimensions["y"]:
            raise MetadataStageError("static grid y dimension does not match staged PBL CDL")
        if _dimension_length(dataset, "nav") != 1:
            raise MetadataStageError("static grid navigation dimension must be one")
        if _dimension_length(dataset, "namelen") != declared_dimensions["namelen"]:
            raise MetadataStageError("static grid namelen dimension does not match staged PBL CDL")

        values: dict[str, Any] = {}
        for name in PBL_NAV_NUMERIC:
            value = _scalar_grid_value(dataset, name)
            number = float(value)
            if not math.isfinite(number):
                raise MetadataStageError(f"static grid navigation {name} is non-finite")
            if name in ("Nx", "Ny"):
                integer = int(value)
                if number != integer or integer != declared_dimensions["x" if name == "Nx" else "y"]:
                    raise MetadataStageError(f"static grid {name} disagrees with staged PBL domain")
                values[name] = integer
            else:
                values[name] = number
        for name in (*PBL_NAV_TEXT, PBL_ORIGIN_TEXT):
            values[name] = _grid_text_value(dataset, name)
    values["source_path"] = str(grid.absolute())
    values["source_sha256"] = actual_hash
    values["source_identity"] = _identity_record(identity)
    values["authority"] = GRID_AUTHORITY
    return values


def _quote_cdl_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _data_string_assignment(payload: str, name: str) -> str | None:
    data_start = payload.find("data:")
    if data_start < 0:
        raise MetadataStageError("PBL CDL has no data section")
    data_end = payload.rfind("}")
    match = re.search(
        rf"(?m)^\s*{re.escape(name)}\s*=\s*\"([^\"]*)\"\s*;",
        payload[data_start:data_end],
    )
    return None if match is None else match.group(1)


def _populate_pbl_navigation(payload: str, values: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    for name in ("x_dim", "y_dim"):
        existing = _data_string_assignment(payload, name)
        if existing != values[name]:
            raise MetadataStageError(
                f"PBL CDL {name} assignment must match static-grid value {values[name]!r}"
            )
    for name in (*PBL_NAV_NUMERIC, "grid_type", PBL_ORIGIN_TEXT):
        if re.search(rf"(?m)^\s*{re.escape(name)}\s*=", payload):
            raise MetadataStageError(f"PBL CDL already contains navigation data for {name}")
    close = payload.rfind("}")
    if close < 0:
        raise MetadataStageError("PBL CDL has no closing brace")
    lines = ["", "        // CP02 staged navigation from the exact static grid:"]
    lines.extend(
        [
            f"        grid_type = {_quote_cdl_string(str(values['grid_type']))};",
            f"        origin_name = {_quote_cdl_string(str(values[PBL_ORIGIN_TEXT]))};",
            f"        Nx = {int(values['Nx'])};",
            f"        Ny = {int(values['Ny'])};",
        ]
    )
    for name in ("La1", "Lo1", "LoV", "Latin1", "Latin2", "Dx", "Dy"):
        lines.append(f"        {name} = {float(values[name]):.9g};")
    payload = payload[:close] + "\n".join(lines) + "\n" + payload[close:]
    return payload, {
        "status": "populated",
        "source_path": values["source_path"],
        "source_sha256": values["source_sha256"],
        "fields": list(PBL_NAV_NUMERIC + PBL_NAV_TEXT + (PBL_ORIGIN_TEXT,)),
        "preserved_fields": ["x_dim", "y_dim"],
        "contract": "fixed-domain-static-grid-exact-dimensions-v1",
    }


def stage_templates(
    source_dir: Path,
    output_dir: Path,
    *,
    expected_source_sha256: Mapping[str, str],
    grid_path: Path | None = None,
    expected_grid_sha256: str | None = None,
) -> dict[str, Any]:
    """Stage corrected CDLs and return the written receipt as a dictionary."""

    source_root = _source_root(Path(source_dir))
    output_root = _output_root(Path(output_dir), source_root)
    expected_hashes = _validate_expected_hashes(expected_source_sha256)
    if grid_path is None and expected_grid_sha256 is not None:
        raise MetadataStageError("expected grid SHA256 requires --grid")
    if grid_path is not None and expected_grid_sha256 is None:
        raise MetadataStageError("--grid requires an expected grid SHA256")

    source_files: dict[str, Path] = {}
    source_hashes: dict[str, str] = {}
    source_identities: dict[str, dict[str, int]] = {}
    source_payloads: dict[str, str] = {}
    for name in PRODUCT_VARIABLES:
        source = source_root / name
        source_bytes, actual_hash, identity = _read_bound_file(
            source, f"source CDL {name}"
        )
        if actual_hash != expected_hashes[name]:
            raise MetadataStageError(
                f"source CDL SHA256 mismatch for {name}: expected {expected_hashes[name]}, found {actual_hash}"
            )
        try:
            payload = source_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise MetadataStageError(f"source CDL is not ASCII: {source}") from exc
        source_files[name] = source
        source_hashes[name] = actual_hash
        source_identities[name] = _identity_record(identity)
        source_payloads[name] = payload

    grid_values: dict[str, Any] | None = None
    if grid_path is not None:
        grid_values = _load_grid(Path(grid_path), str(expected_grid_sha256), source_payloads["pbl.cdl"])

    transformations: list[dict[str, str]] = []
    outputs: dict[str, dict[str, Any]] = {}
    try:
        with tempfile.TemporaryDirectory(prefix=output_root.name + ".", dir=output_root.parent) as temporary:
            temporary_root = Path(temporary)
            for name, payload in source_payloads.items():
                transformed, changes = _remove_stale_ranges(name, payload)
                transformations.extend(changes)
                navigation: dict[str, Any]
                if name == "pbl.cdl" and grid_values is not None:
                    transformed, navigation = _populate_pbl_navigation(transformed, grid_values)
                elif name == "pbl.cdl":
                    navigation = {
                        "status": "not_requested",
                        "reason": "exact static-grid source was not supplied",
                    }
                else:
                    navigation = {"status": "not_applicable"}
                target = temporary_root / name
                target.write_text(transformed, encoding="ascii", newline="")
                outputs[name] = {
                    "source_path": str(source_files[name]),
                    "source_sha256": source_hashes[name],
                    "output_path": str((output_root / name).relative_to(output_root)),
                    "output_sha256": sha256_file(target),
                    "navigation": navigation,
                }
            receipt: dict[str, Any] = {
                "schema": 1,
                "contract": "cp02_metadata_staged_cdl_v1",
                "status": "STAGED",
                "source_root": str(source_root),
                "output_root": str(output_root),
                "source_sha256_verified": source_hashes,
                "source_identity": source_identities,
                "grid_sha256": None if grid_values is None else grid_values["source_sha256"],
                "grid_identity": None if grid_values is None else grid_values["source_identity"],
                "grid_authority": None if grid_values is None else grid_values["authority"],
                "transformations": transformations,
                "outputs": outputs,
            }
            (temporary_root / "metadata_stage_receipt.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="",
            )
            _rename_noreplace(temporary_root, output_root)
    except OSError as exc:
        raise MetadataStageError(f"could not publish isolated metadata stage: {exc}") from exc
    return receipt


def _parse_expected_hashes(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        name, separator, digest = item.partition("=")
        if not separator or not name or not digest:
            raise MetadataStageError("--expected-source-sha256 must use FILE=SHA256")
        if name in result:
            raise MetadataStageError(f"duplicate source hash for {name}")
        result[name] = digest
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--expected-source-sha256",
        action="append",
        default=[],
        metavar="FILE=SHA256",
        help="hash bind one source CDL; repeat for all five files",
    )
    parser.add_argument("--grid", type=Path, help="hash-bound static.nest7grid for PBL navigation")
    parser.add_argument("--expected-grid-sha256", help="SHA256 for --grid")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        receipt = stage_templates(
            args.source_dir,
            args.output_dir,
            expected_source_sha256=_parse_expected_hashes(args.expected_source_sha256),
            grid_path=args.grid,
            expected_grid_sha256=args.expected_grid_sha256,
        )
    except MetadataStageError as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
