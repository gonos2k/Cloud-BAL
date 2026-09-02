#!/usr/bin/env python3
"""Prepare a fail-closed operational-original/SHADOW comparison bundle.

This tool never treats a Cloud-BAL canonical ``background`` field as an
operational original.  A comparison is ready only when an independently
archived operational product, a hybrid diagnostic candidate, and a separately
snapshotted operational product satisfy the same explicit contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import netCDF4
import numpy as np

from compare_baseline import _records, read_wps

__all__ = ("prepare",)


SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
SHADOW_CONFIGURATION = "radar-only-shadow-ifx-2026-v3"
ROLES = {
    "original": ("REAL_OPERATIONAL_ORIGINAL", "ARCHIVED_OPERATIONAL_KLAPS"),
    "candidate": (
        "SHADOW_CANDIDATE",
        "HYBRID_DIAGNOSTIC_HYDROMETEOR_REPLACEMENT",
    ),
    "operational_unchanged": (
        "OPERATIONAL_UNCHANGED",
        "LIVE_OPERATIONAL_KLAPS_UNCHANGED",
    ),
}
FORMATS = {"WPS_INTERMEDIATE", "MET_EM_NETCDF"}
WIND_COORDINATES = {"GRID_RELATIVE", "EARTH_RELATIVE"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
TRANSACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_DIAGNOSTIC_TOKENS = (
    "CANONICAL", "BACKGROUND", "DIAGNOSTIC", "PROPOSAL", "SYNTHETIC",
)
MET_EM_PROJECTION_ATTRIBUTES = (
    "GRIDTYPE",
    "MAP_PROJ",
    "DX",
    "DY",
    "CEN_LAT",
    "CEN_LON",
    "TRUELAT1",
    "TRUELAT2",
    "STAND_LON",
    "POLE_LAT",
    "POLE_LON",
)
REQUIRED_PRODUCT_FIELDS = {
    "LAPS": {
        "HGT", "PMSL", "PSFC", "QC", "QG", "QI", "QR", "QS", "RH",
        "SKINTEMP", "TT", "UU", "VV",
    },
    "KLBG": {
        "HGT", "PMSL", "PSFC", "QC", "QG", "QI", "QR", "QS", "RH",
        "SNOWH", "T", "U", "V",
    },
    "MET_EM": {
        "Times", "PRES", "GHT", "PMSL", "PSFC", "QC", "QG", "QI", "QR",
        "QS", "RH", "SKINTEMP", "TT", "UU", "VV",
    },
}


class ContractError(ValueError):
    """An input failed the comparison evidence contract."""


@dataclass(frozen=True)
class Artifact:
    relative_path: str
    source_path: Path
    path: Path
    sha256: str
    wind_coordinate: str
    attestation_path: str | None
    attestation_sha256: str | None


@dataclass
class Product:
    format: str
    valid_time: str
    field_metadata: dict[str, dict[str, Any]]
    grid_projection: dict[str, Any]
    levels: dict[str, Any]
    units: dict[str, str]
    stagger: dict[str, str]
    validity: dict[str, dict[str, Any]]
    embedded_wind_coordinate: str | None
    payload: Any


@dataclass
class PlotBundle:
    pair_id: str
    plot_id: str
    field: str
    selector: dict[str, Any]
    units: str
    scale: dict[str, float]
    original: np.ndarray
    candidate: np.ndarray
    common_valid: np.ndarray
    metrics: dict[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    """Convert NetCDF/numpy metadata to deterministic JSON values."""
    if isinstance(value, np.ndarray):
        return [json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise ContractError("metadata bytes are not valid UTF-8") from exc
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non-finite metadata is forbidden")
        return value
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    raise ContractError(f"unsupported metadata type: {type(value).__name__}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ContractError(f"{context} keys differ: missing={missing}, extra={extra}")


def canonical_time(value: str, context: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{context} must be a string")
    text = value.strip().replace("_", "T")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text):
        text += ":00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"invalid {context}: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(f"{context} must be UTC: {value!r}")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond:
        fraction = f"{parsed.microsecond:06d}".rstrip("0")
        return parsed.strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction}Z"
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def contains_bigfile(path: PurePosixPath | Path) -> bool:
    return any("bigfile" in part.lower() for part in path.parts)


def contains_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def validate_root(root: Path) -> Path:
    if contains_bigfile(root):
        raise ContractError("bigfile paths are forbidden")
    if contains_symlink_component(root):
        raise ContractError("artifact root path must not contain a symbolic link")
    resolved = root.resolve(strict=True)
    if contains_bigfile(resolved):
        raise ContractError("resolved bigfile paths are forbidden")
    if not resolved.is_dir():
        raise ContractError("artifact root must be a directory")
    return resolved


def resolve_artifact(root: Path, raw: str, context: str) -> tuple[str, Path]:
    if not isinstance(raw, str) or not raw:
        raise ContractError(f"{context} path must be a nonempty string")
    relative = PurePosixPath(raw)
    if (
        raw != relative.as_posix()
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ContractError(f"{context} path must be a normalized relative path")
    if contains_bigfile(relative):
        raise ContractError(f"{context} uses forbidden bigfile path")
    unresolved = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ContractError(f"{context} path contains a symbolic link")
    try:
        resolved = unresolved.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ContractError(f"{context} file is missing or escapes artifact root") from exc
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ContractError(f"{context} must be a regular file")
    if resolved.stat().st_nlink != 1:
        raise ContractError(f"{context} must be an independent single-link file")
    if contains_bigfile(resolved):
        raise ContractError(f"{context} resolves through a forbidden bigfile path")
    return relative.as_posix(), resolved


def read_attestation(
    root: Path,
    value: Any,
    key: str,
    artifact_path: Path,
    artifact_sha: str,
    context: str,
) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ContractError(f"{context} attestation must be an object")
    require_exact_keys(value, {"format", "path", "sha256"}, f"{context} attestation")
    expected_format = (
        "SHA256SUMS" if key == "original" else "LOCAL_DIAGNOSTIC_MANIFEST"
    )
    if value["format"] != expected_format:
        raise ContractError(f"{context} attestation format must be {expected_format}")
    expected_sha = value["sha256"]
    if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
        raise ContractError(f"{context} attestation sha256 is invalid")
    relative, path = resolve_artifact(root, value["path"], f"{context} attestation")
    expected_name = "SHA256SUMS" if key == "original" else "MANIFEST.json"
    if path.name != expected_name:
        raise ContractError(f"{context} attestation filename must be {expected_name}")
    content = path.read_bytes()
    actual_sha = hashlib.sha256(content).hexdigest()
    if actual_sha != expected_sha:
        raise ContractError(f"{context} attestation checksum does not match")
    try:
        product_from_attestation = artifact_path.relative_to(path.parent).as_posix()
    except ValueError as exc:
        raise ContractError(f"{context} product is outside its attested generation") from exc

    if key == "original":
        records: dict[str, str] = {}
        try:
            lines = content.decode("utf-8", "strict").splitlines()
        except UnicodeError as exc:
            raise ContractError(f"{context} SHA256SUMS is not UTF-8") from exc
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or not SHA256.fullmatch(parts[0]):
                raise ContractError(f"{context} SHA256SUMS contains an invalid record")
            recorded_path = parts[1].lstrip("*")
            if recorded_path in records:
                raise ContractError(f"{context} SHA256SUMS contains a duplicate path")
            records[recorded_path] = parts[0]
        if records.get(product_from_attestation) != artifact_sha:
            raise ContractError(f"{context} product is not bound by SHA256SUMS")
    else:
        try:
            generation = json.loads(content.decode("utf-8", "strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"{context} generation manifest is invalid") from exc
        if not isinstance(generation, dict) or generation.get("schema") != 1:
            raise ContractError(f"{context} generation manifest schema is invalid")
        transaction_id = generation.get("transaction_id")
        source_commit = generation.get("source_commit")
        configuration = generation.get("configuration")
        products = generation.get("products")
        if not isinstance(transaction_id, str) or not TRANSACTION_ID.fullmatch(transaction_id):
            raise ContractError(f"{context} generation transaction_id is invalid")
        if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise ContractError(f"{context} generation source_commit is invalid")
        if configuration != SHADOW_CONFIGURATION:
            raise ContractError(
                f"{context} generation configuration is not the approved SHADOW profile"
            )
        if not isinstance(products, list):
            raise ContractError(f"{context} generation products are invalid")
        matches = [
            item
            for item in products
            if isinstance(item, dict) and item.get("path") == product_from_attestation
        ]
        if len(matches) != 1 or matches[0].get("sha256") != artifact_sha:
            raise ContractError(f"{context} product is not bound by generation manifest")
        if matches[0].get("bytes") != artifact_path.stat().st_size:
            raise ContractError(f"{context} generation product size differs")
        marker = path.parent / "COMMITTED"
        if contains_symlink_component(marker) or not marker.is_file() or marker.stat().st_nlink != 1:
            raise ContractError(f"{context} generation lacks an independent COMMITTED marker")
        if marker.read_text(encoding="ascii").strip() != transaction_id:
            raise ContractError(f"{context} COMMITTED marker differs from transaction_id")
    return relative, actual_sha


def snapshot_file(source: Path, destination: Path, expected_sha: str, context: str) -> Path:
    destination.parent.mkdir(parents=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        opened = os.fstat(reader.fileno())
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
        closed = os.fstat(reader.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if identity(opened) != identity(closed):
        raise ContractError(f"{context} changed while it was snapshotted")
    if sha256_file(destination) != expected_sha:
        raise ContractError(f"{context} snapshot checksum does not match manifest")
    destination.chmod(0o400)
    return destination


def parse_artifact(
    root: Path,
    value: Any,
    key: str,
    context: str,
    snapshot_directory: Path,
) -> Artifact:
    if not isinstance(value, dict):
        raise ContractError(f"{context} must be an object")
    expected_keys = {"evidence_role", "origin", "path", "sha256", "wind_coordinate"}
    if key in {"original", "candidate"}:
        expected_keys.add("attestation")
    require_exact_keys(value, expected_keys, context)
    expected_role, expected_origin = ROLES[key]
    if value["evidence_role"] != expected_role:
        raise ContractError(f"{context} evidence_role must be {expected_role}")
    if value["origin"] != expected_origin:
        raise ContractError(f"{context} origin must be {expected_origin}")
    expected_sha = value["sha256"]
    if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
        raise ContractError(f"{context} sha256 must be 64 lowercase hexadecimal digits")
    wind = value["wind_coordinate"]
    if wind not in WIND_COORDINATES:
        raise ContractError(f"{context} has invalid wind_coordinate")
    relative, path = resolve_artifact(root, value["path"], context)
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise ContractError(f"{context} checksum does not match manifest")
    attestation_path = None
    attestation_sha = None
    if key in {"original", "candidate"}:
        attestation_path, attestation_sha = read_attestation(
            root,
            value["attestation"],
            key,
            path,
            actual_sha,
            context,
        )
    snapshot = snapshot_file(
        path, snapshot_directory / key / path.name, actual_sha, context
    )
    return Artifact(
        relative,
        path,
        snapshot,
        actual_sha,
        wind,
        attestation_path,
        attestation_sha,
    )


def wps_key(field: str, level: float) -> str:
    return f"{field}|{float(level).hex()}"


def validity_record(data: Any) -> dict[str, Any]:
    values, valid = finite_array(data)
    packed = np.packbits(valid.ravel(order="C"), bitorder="little")
    return {
        "shape": list(values.shape),
        "valid_count": int(np.count_nonzero(valid)),
        "mask_sha256": hashlib.sha256(packed.tobytes()).hexdigest(),
    }


def read_wps_product(path: Path) -> Product:
    try:
        raw_fields = read_wps(path)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        raise ContractError(f"invalid WPS intermediate product: {path.name}") from exc
    if not raw_fields:
        raise ContractError("WPS intermediate product contains no fields")
    fields: dict[str, dict[str, Any]] = {}
    payload: dict[str, np.ndarray] = {}
    validity: dict[str, dict[str, Any]] = {}
    record_contracts: dict[str, str] = {}
    record_sources: dict[str, str] = {}
    records = iter(_records(path))
    while True:
        try:
            endian, version_record = next(records)
        except StopIteration:
            break
        try:
            _, metadata_record = next(records)
            _, projection_record = next(records)
            _, wind_record = next(records)
            next(records)  # slab; values are compared separately
        except StopIteration as exc:
            raise ContractError("truncated WPS record group") from exc
        try:
            source = metadata_record[28:60].decode("ascii", "strict").strip()
            field = metadata_record[60:69].decode("ascii", "strict").strip()
        except UnicodeError as exc:
            raise ContractError("WPS metadata contains non-ASCII bytes") from exc
        level = np.frombuffer(metadata_record[140:144], dtype=endian + "f4")[0]
        if not source:
            raise ContractError("empty WPS source label")
        if any(token in source.upper() for token in FORBIDDEN_DIAGNOSTIC_TOKENS):
            raise ContractError(f"forbidden diagnostic WPS source label: {source!r}")
        # read_wps already validates endianness and record structure.  Bind all
        # non-data bytes so XFCST, source, description, projection and wind
        # metadata cannot change unnoticed.
        digest = hashlib.sha256()
        for item in (version_record, metadata_record, projection_record, wind_record):
            digest.update(len(item).to_bytes(8, "big"))
            digest.update(item)
        key = wps_key(field, float(level))
        if key in record_contracts:
            raise ContractError(f"duplicate WPS metadata identity: {field} {level}")
        record_contracts[key] = digest.hexdigest()
        record_sources[key] = source
    times: set[str] = set()
    wind_values: set[bool] = set()
    for (field, level, raw_time), (units, shape, values, metadata) in raw_fields.items():
        key = wps_key(field, level)
        if key in fields:
            raise ContractError(f"duplicate WPS field/level identity: {field} {level}")
        if key not in record_contracts:
            raise ContractError(f"WPS metadata identity is inconsistent: {field} {level}")
        times.add(canonical_time(raw_time, "WPS valid time"))
        wind_values.add(bool(metadata["wind_grid_relative"]))
        fields[key] = {
            "field": field,
            "level": float(level),
            "shape": list(shape),
            "projection": int(metadata["projection"]),
            "projection_record_sha256": metadata["projection_record_sha256"],
            "record_contract_sha256": record_contracts[key],
            "source": record_sources[key],
        }
        payload[key] = np.asarray(values, dtype=np.float64).reshape(shape[1], shape[0])
        validity[key] = validity_record(payload[key])
    if len(times) != 1:
        raise ContractError("WPS product contains multiple valid times")
    if len(wind_values) != 1:
        raise ContractError("WPS product contains inconsistent wind coordinates")
    units_map = {
        wps_key(field, level): units
        for (field, level, _), (units, _, _, _) in raw_fields.items()
    }
    stagger = {key: "WPS_INTERMEDIATE_UNSTAGGERED" for key in fields}
    grid_projection = {
        key: {
            "shape": metadata["shape"],
            "projection": metadata["projection"],
            "projection_record_sha256": metadata["projection_record_sha256"],
        }
        for key, metadata in fields.items()
    }
    levels: dict[str, list[float]] = {}
    for metadata in fields.values():
        levels.setdefault(metadata["field"], []).append(metadata["level"])
    levels = {key: sorted(value) for key, value in sorted(levels.items())}
    embedded = "GRID_RELATIVE" if next(iter(wind_values)) else "EARTH_RELATIVE"
    return Product(
        "WPS_INTERMEDIATE",
        next(iter(times)),
        fields,
        grid_projection,
        levels,
        units_map,
        stagger,
        validity,
        embedded,
        payload,
    )


def decode_times(variable: netCDF4.Variable) -> list[str]:
    raw = np.ma.asarray(variable[:])
    if np.any(np.ma.getmaskarray(raw)):
        raise ContractError("masked Times values are forbidden")
    data = np.ma.getdata(raw)
    if data.ndim != 2 or data.dtype.kind not in {"S", "U"}:
        raise ContractError("Times must be a two-dimensional character array")
    result = []
    for row in data:
        if data.dtype.kind == "S":
            try:
                text = b"".join(row.tolist()).decode("ascii", "strict")
            except UnicodeError as exc:
                raise ContractError("Times contains non-ASCII bytes") from exc
        else:
            text = "".join(row.tolist())
        result.append(canonical_time(text.rstrip("\x00 "), "NetCDF valid time"))
    return result


def inferred_stagger(variable: netCDF4.Variable) -> str:
    if "stagger" in variable.ncattrs():
        value = str(getattr(variable, "stagger")).strip()
        if not value:
            raise ContractError(f"empty stagger attribute: {variable.name}")
        return value
    staggered = tuple(name for name in variable.dimensions if name.endswith("_stag"))
    return ",".join(staggered) if staggered else "UNSTAGGERED"


def read_netcdf_product(path: Path) -> Product:
    try:
        dataset = netCDF4.Dataset(path, "r")
    except OSError as exc:
        raise ContractError(f"invalid met_em NetCDF product: {path.name}") from exc
    try:
        if "Times" not in dataset.variables:
            raise ContractError("met_em product lacks Times")
        decoded_times = decode_times(dataset.variables["Times"])
        if len(decoded_times) != 1:
            raise ContractError("met_em product must contain exactly one Times record")
        times = set(decoded_times)
        for attribute in MET_EM_PROJECTION_ATTRIBUTES:
            if attribute not in dataset.ncattrs():
                raise ContractError(f"met_em product lacks projection attribute {attribute}")
        authority = str(getattr(dataset, "result_authority", ""))
        if any(token in authority.upper() for token in FORBIDDEN_DIAGNOSTIC_TOKENS):
            raise ContractError("diagnostic/background NetCDF is not a full met_em candidate")
        fields: dict[str, dict[str, Any]] = {}
        units: dict[str, str] = {}
        stagger: dict[str, str] = {}
        for name, variable in dataset.variables.items():
            metadata = {
                "dtype": str(variable.dtype),
                "dimensions": list(variable.dimensions),
                "shape": list(variable.shape),
                "attributes": {
                    attribute: json_value(getattr(variable, attribute))
                    for attribute in sorted(variable.ncattrs())
                },
            }
            fields[name] = metadata
            units[name] = str(getattr(variable, "units", ""))
            stagger[name] = inferred_stagger(variable)
        dimensions = {
            name: {"size": len(dimension), "unlimited": bool(dimension.isunlimited())}
            for name, dimension in sorted(dataset.dimensions.items())
        }
        projection = {
            attribute: json_value(getattr(dataset, attribute))
            for attribute in MET_EM_PROJECTION_ATTRIBUTES
        }
        for optional in ("corner_lats", "corner_lons"):
            if optional in dataset.ncattrs():
                projection[optional] = json_value(getattr(dataset, optional))
        grid_projection = {"dimensions": dimensions, "projection": projection}
        levels = {
            name: len(dimension)
            for name, dimension in sorted(dataset.dimensions.items())
            if "level" in name.lower() or "layer" in name.lower()
        }
        validity = {
            name: validity_record(variable[:])
            for name, variable in dataset.variables.items()
            if np.issubdtype(variable.dtype, np.number)
        }
        # Keep only a path in the payload.  Plot fields are read lazily after
        # every metadata gate has succeeded.
        return Product(
            "MET_EM_NETCDF",
            next(iter(times)),
            fields,
            grid_projection,
            levels,
            units,
            stagger,
            validity,
            "GRID_RELATIVE",
            path,
        )
    finally:
        dataset.close()


def ensure_same(label: str, products: dict[str, Product], attribute: str) -> None:
    reference = getattr(products["original"], attribute)
    for key in ("candidate", "operational_unchanged"):
        if getattr(products[key], attribute) != reference:
            raise ContractError(f"{label} differs between original and {key}")


def validate_product_identity(
    product_kind: str, artifacts: dict[str, Artifact], expected_time: str
) -> None:
    names = {artifact.source_path.name for artifact in artifacts.values()}
    if len(names) != 1:
        raise ContractError("product filenames differ across evidence roles")
    name = next(iter(names))
    if product_kind in {"LAPS", "KLBG"}:
        prefix = product_kind + ":"
        if not name.startswith(prefix):
            raise ContractError(f"{product_kind} product filename has the wrong prefix")
        filename_time = canonical_time(name[len(prefix):], f"{product_kind} filename time")
    else:
        match = re.fullmatch(r"met_em\.d\d\d\.(.+)\.nc", name)
        if match is None:
            raise ContractError("MET_EM product filename is not a met_em domain product")
        filename_time = canonical_time(match.group(1), "MET_EM filename time")
    if filename_time != expected_time:
        raise ContractError("product filename valid time differs from manifest")


def validate_required_fields(product_kind: str, product: Product) -> None:
    present = (
        set(product.levels)
        if product.format == "WPS_INTERMEDIATE"
        else set(product.field_metadata)
    )
    missing = sorted(REQUIRED_PRODUCT_FIELDS[product_kind] - present)
    if missing:
        raise ContractError(f"{product_kind} lacks required full-product fields: {missing}")
    for field in REQUIRED_PRODUCT_FIELDS[product_kind]:
        if product.format == "WPS_INTERMEDIATE":
            counts = [
                product.validity[wps_key(field, level)]["valid_count"]
                for level in product.levels[field]
            ]
        elif field in product.validity:
            counts = [product.validity[field]["valid_count"]]
        else:
            continue
        if not counts or max(counts) == 0:
            raise ContractError(f"{product_kind} required field has no valid data: {field}")


def parse_scale(value: Any, context: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ContractError(f"{context} scale must be an object")
    require_exact_keys(value, {"value_min", "value_max", "delta_abs_max"}, context)
    result: dict[str, float] = {}
    for key in ("value_min", "value_max", "delta_abs_max"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ContractError(f"{context} {key} must be numeric")
        result[key] = float(number)
        if not math.isfinite(result[key]):
            raise ContractError(f"{context} {key} must be finite")
    if result["value_min"] >= result["value_max"]:
        raise ContractError(f"{context} value_min must be less than value_max")
    if result["delta_abs_max"] <= 0.0:
        raise ContractError(f"{context} delta_abs_max must be positive")
    return result


def finite_array(data: Any) -> tuple[np.ndarray, np.ndarray]:
    masked = np.ma.asarray(data)
    values = np.asarray(np.ma.getdata(masked), dtype=np.float64)
    valid = ~np.ma.getmaskarray(masked) & np.isfinite(values) & (np.abs(values) < 1.0e20)
    return values, valid


def numeric_metrics(
    original: np.ndarray,
    candidate: np.ndarray,
    original_valid: np.ndarray,
    candidate_valid: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    if original.shape != candidate.shape:
        raise ContractError("plot field shape differs")
    common = original_valid & candidate_valid
    if not np.any(common):
        raise ContractError("plot field has no common valid cells")
    delta = candidate[common] - original[common]

    def clean(value: float) -> float:
        return 0.0 if value == 0.0 else float(value)

    metrics = {
        "shape": list(original.shape),
        "original_valid_count": int(np.count_nonzero(original_valid)),
        "candidate_valid_count": int(np.count_nonzero(candidate_valid)),
        "common_valid_count": int(np.count_nonzero(common)),
        "valid_mask_changed_count": int(np.count_nonzero(original_valid != candidate_valid)),
        "original_min": clean(np.min(original[original_valid])),
        "original_max": clean(np.max(original[original_valid])),
        "candidate_min": clean(np.min(candidate[candidate_valid])),
        "candidate_max": clean(np.max(candidate[candidate_valid])),
        "mean_delta": clean(np.mean(delta)),
        "rms_delta": clean(np.sqrt(np.mean(delta * delta))),
        "max_abs_delta": clean(np.max(np.abs(delta))),
    }
    return common, metrics


def make_plot_bundle(
    pair_id: str,
    plot_id: str,
    field: str,
    selector: dict[str, Any],
    units: str,
    scale: Any,
    original_data: Any,
    candidate_data: Any,
) -> PlotBundle:
    original, original_valid = finite_array(original_data)
    candidate, candidate_valid = finite_array(candidate_data)
    common, metrics = numeric_metrics(
        original, candidate, original_valid, candidate_valid
    )
    return PlotBundle(
        pair_id,
        plot_id,
        field,
        selector,
        units,
        parse_scale(scale, f"plot field {plot_id}"),
        original,
        candidate,
        common,
        metrics,
    )


def wps_plot_bundle(
    pair_id: str,
    spec: dict[str, Any],
    original: Product,
    candidate: Product,
) -> PlotBundle:
    require_exact_keys(spec, {"plot_id", "field", "level", "scale"}, "WPS plot field")
    plot_id = spec["plot_id"]
    if not isinstance(plot_id, str) or not SAFE_ID.fullmatch(plot_id):
        raise ContractError("invalid WPS plot_id")
    if not isinstance(spec["field"], str) or not spec["field"]:
        raise ContractError("invalid WPS plot field name")
    if isinstance(spec["level"], bool) or not isinstance(spec["level"], (int, float)):
        raise ContractError("WPS plot level must be numeric")
    key = wps_key(spec["field"], float(spec["level"]))
    if key not in original.payload or key not in candidate.payload:
        raise ContractError(f"WPS plot field/level is absent: {spec['field']} {spec['level']}")
    return make_plot_bundle(
        pair_id,
        plot_id,
        spec["field"],
        {"level": float(spec["level"])},
        original.units[key],
        spec["scale"],
        original.payload[key],
        candidate.payload[key],
    )


def netcdf_slice(path: Path, field: str, indices: dict[str, int]) -> tuple[np.ndarray, str]:
    with netCDF4.Dataset(path, "r") as dataset:
        if field not in dataset.variables:
            raise ContractError(f"NetCDF plot field is absent: {field}")
        variable = dataset.variables[field]
        if not np.issubdtype(variable.dtype, np.number):
            raise ContractError(f"NetCDF plot field is not numeric: {field}")
        unknown = set(indices) - set(variable.dimensions)
        if unknown:
            raise ContractError(f"indices name dimensions not used by {field}: {sorted(unknown)}")
        selection: list[int | slice] = []
        remaining = 0
        for dimension, size in zip(variable.dimensions, variable.shape):
            if dimension in indices:
                index = indices[dimension]
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < size:
                    raise ContractError(f"invalid {field} index for {dimension}")
                selection.append(index)
            else:
                selection.append(slice(None))
                remaining += 1
        if remaining != 2:
            raise ContractError(f"NetCDF plot selection for {field} must leave exactly 2 dimensions")
        return np.ma.asarray(variable[tuple(selection)]), str(getattr(variable, "units", ""))


def netcdf_plot_bundle(
    pair_id: str,
    spec: dict[str, Any],
    original: Product,
    candidate: Product,
) -> PlotBundle:
    require_exact_keys(
        spec, {"plot_id", "field", "indices", "scale"}, "NetCDF plot field"
    )
    plot_id = spec["plot_id"]
    if not isinstance(plot_id, str) or not SAFE_ID.fullmatch(plot_id):
        raise ContractError("invalid NetCDF plot_id")
    field = spec["field"]
    if not isinstance(field, str) or not field:
        raise ContractError("invalid NetCDF plot field name")
    if not isinstance(spec["indices"], dict) or not all(
        isinstance(key, str) for key in spec["indices"]
    ):
        raise ContractError("NetCDF plot indices must be an object")
    left_raw, left_units = netcdf_slice(original.payload, field, spec["indices"])
    right_raw, right_units = netcdf_slice(candidate.payload, field, spec["indices"])
    if left_units != right_units:
        raise ContractError(f"plot field units differ: {field}")
    return make_plot_bundle(
        pair_id,
        plot_id,
        field,
        {"indices": dict(sorted(spec["indices"].items()))},
        left_units,
        spec["scale"],
        left_raw,
        right_raw,
    )


def validate_pair(
    root: Path, value: Any, snapshot_directory: Path
) -> tuple[dict[str, Any], list[PlotBundle]]:
    if not isinstance(value, dict):
        raise ContractError("pair must be an object")
    require_exact_keys(
        value,
        {
            "pair_id",
            "product_kind",
            "format",
            "valid_time",
            "plot_fields",
            "original",
            "candidate",
            "operational_unchanged",
        },
        "pair",
    )
    pair_id = value["pair_id"]
    if not isinstance(pair_id, str) or not SAFE_ID.fullmatch(pair_id):
        raise ContractError("invalid pair_id")
    product_kind = value["product_kind"]
    product_format = value["format"]
    if product_kind not in {"LAPS", "KLBG", "MET_EM"}:
        raise ContractError(f"invalid product_kind for {pair_id}")
    if product_format not in FORMATS:
        raise ContractError(f"invalid format for {pair_id}")
    if product_kind in {"LAPS", "KLBG"} and product_format != "WPS_INTERMEDIATE":
        raise ContractError(f"{product_kind} must use WPS_INTERMEDIATE")
    if product_kind == "MET_EM" and product_format != "MET_EM_NETCDF":
        raise ContractError("MET_EM must use MET_EM_NETCDF")
    expected_time = canonical_time(value["valid_time"], f"{pair_id} valid_time")
    if not isinstance(value["plot_fields"], list) or not value["plot_fields"]:
        raise ContractError(f"{pair_id} must declare at least one fixed-scale plot field")

    artifacts = {
        key: parse_artifact(
            root, value[key], key, f"{pair_id}.{key}", snapshot_directory
        )
        for key in ROLES
    }
    paths = [artifact.source_path for artifact in artifacts.values()]
    if len(set(paths)) != 3:
        raise ContractError(f"{pair_id} roles must reference three distinct files")
    inodes = {(path.stat().st_dev, path.stat().st_ino) for path in paths}
    if len(inodes) != 3:
        raise ContractError(f"{pair_id} roles must be independent files")
    if artifacts["original"].sha256 != artifacts["operational_unchanged"].sha256:
        raise ContractError(f"{pair_id} operational product is not byte-identical to original")
    wind_coordinates = {artifact.wind_coordinate for artifact in artifacts.values()}
    if len(wind_coordinates) != 1:
        raise ContractError(f"{pair_id} manifest wind coordinates differ")
    validate_product_identity(product_kind, artifacts, expected_time)

    reader = (
        read_wps_product
        if product_format == "WPS_INTERMEDIATE"
        else read_netcdf_product
    )
    try:
        products = {
            key: reader(artifact.path)
            for key, artifact in artifacts.items()
        }
    except ContractError:
        raise
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        raise ContractError(f"{pair_id} product parsing failed: {exc}") from exc
    if any(product.valid_time != expected_time for product in products.values()):
        raise ContractError(f"{pair_id} product valid time differs from manifest")
    inventory = set(products["original"].field_metadata)
    if any(set(products[key].field_metadata) != inventory for key in products if key != "original"):
        raise ContractError("field inventory differs between evidence roles")
    ensure_same("field metadata", products, "field_metadata")
    ensure_same("grid/projection", products, "grid_projection")
    ensure_same("levels", products, "levels")
    ensure_same("units", products, "units")
    ensure_same("stagger", products, "stagger")
    ensure_same("valid masks", products, "validity")
    for product in products.values():
        validate_required_fields(product_kind, product)
    embedded = {product.embedded_wind_coordinate for product in products.values()}
    embedded.discard(None)
    if embedded and embedded != wind_coordinates:
        raise ContractError(f"{pair_id} embedded and manifest wind coordinates differ")

    bundles: list[PlotBundle] = []
    seen_plot_ids: set[str] = set()
    for spec in value["plot_fields"]:
        if not isinstance(spec, dict):
            raise ContractError(f"{pair_id} plot field must be an object")
        plot_id = spec.get("plot_id")
        if not isinstance(plot_id, str) or not SAFE_ID.fullmatch(plot_id):
            raise ContractError(f"{pair_id} has invalid plot_id")
        if plot_id in seen_plot_ids:
            raise ContractError(f"{pair_id} contains duplicate plot_id {plot_id!r}")
        seen_plot_ids.add(plot_id)
        if product_format == "WPS_INTERMEDIATE":
            bundle = wps_plot_bundle(pair_id, spec, products["original"], products["candidate"])
        else:
            bundle = netcdf_plot_bundle(
                pair_id, spec, products["original"], products["candidate"]
            )
        bundles.append(bundle)

    report = {
        "pair_id": pair_id,
        "product_kind": product_kind,
        "format": product_format,
        "valid_time": expected_time,
        "status": "READY",
        "evidence": {
            key: {
                "evidence_role": ROLES[key][0],
                "origin": ROLES[key][1],
                "path": artifact.relative_path,
                "sha256": artifact.sha256,
                "wind_coordinate": artifact.wind_coordinate,
                "attestation_path": artifact.attestation_path,
                "attestation_sha256": artifact.attestation_sha256,
            }
            for key, artifact in artifacts.items()
        },
        "contract_checks": {
            "candidate_full_field_inventory": "PASS",
            "candidate_full_valid_masks": "PASS",
            "local_product_attestations": "PASS",
            "checksums": "PASS",
            "grid_projection": "PASS",
            "independent_files": "PASS",
            "levels": "PASS",
            "operational_unchanged": "PASS",
            "stagger": "PASS",
            "units": "PASS",
            "valid_time": "PASS",
            "wind_coordinate": "PASS",
        },
    }
    return report, bundles


def bundle_metadata(bundle: PlotBundle, directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True)
    original = np.where(bundle.common_valid, bundle.original, np.nan).astype("<f8")
    candidate = np.where(bundle.common_valid, bundle.candidate, np.nan).astype("<f8")
    delta = np.where(bundle.common_valid, candidate - original, np.nan).astype("<f8")
    common = bundle.common_valid.astype("u1")
    arrays = {
        "original.npy": original,
        "candidate.npy": candidate,
        "delta.npy": delta,
        "common_valid.npy": common,
    }
    products = []
    for name, array in arrays.items():
        path = directory / name
        with path.open("wb") as stream:
            np.lib.format.write_array(stream, array, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        products.append({"path": name, "sha256": sha256_file(path)})
    metadata = {
        "pair_id": bundle.pair_id,
        "plot_id": bundle.plot_id,
        "field": bundle.field,
        "selector": bundle.selector,
        "units": bundle.units,
        "fixed_scale": bundle.scale,
        "scale_source": "MANIFEST_FIXED",
        "evidence_roles": {
            "original": "REAL_OPERATIONAL_ORIGINAL",
            "candidate": "SHADOW_CANDIDATE",
            "operational": "OPERATIONAL_UNCHANGED",
        },
        "metrics": bundle.metrics,
        "arrays": sorted(products, key=lambda item: item["path"]),
    }
    write_json(directory / "metadata.json", metadata)
    metadata["metadata_sha256"] = sha256_file(directory / "metadata.json")
    return metadata


def base_report(manifest_sha: str | None, comparison_id: str | None) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "manifest_sha256": manifest_sha,
        "status": "NOT_READY",
        "status_scope": "STRUCTURAL_NUMERICAL_READINESS_UNDER_LOCAL_MANIFEST",
        "algorithm_comparison_status": "NOT_RUN",
        "operational_authority": "NOT_MODIFIED_BY_COMPARISON_TOOL",
        "evidence_time_scope": "CHECKSUM_BOUND_INPUT_SNAPSHOTS_NOT_LIVE_STATE",
        "provenance_authority": "LOCAL_ATTESTATION_BOUND_NOT_SIGNED",
        "certified_operational_provenance": False,
        "scientific_conclusion": "NOT_ASSESSED",
        "promotion_eligible": False,
        "bigfile_used": False,
        "evidence_roles": {
            "original": "REAL_OPERATIONAL_ORIGINAL",
            "candidate": "SHADOW_CANDIDATE",
            "operational": "OPERATIONAL_UNCHANGED",
        },
        "pairs": [],
        "failures": [],
        "comparison_data": [],
    }


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if contains_bigfile(path):
        raise ContractError("bigfile paths are forbidden")
    if contains_symlink_component(path):
        raise ContractError("manifest path must not contain a symbolic link")
    if contains_bigfile(path.resolve(strict=False)):
        raise ContractError("resolved bigfile manifest paths are forbidden")
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ContractError("manifest must be an independent regular file")
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    try:
        manifest = json.loads(content.decode("utf-8", "strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ContractError("manifest must be an object")
    require_exact_keys(manifest, {"schema_version", "comparison_id", "pairs"}, "manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ContractError("unsupported manifest schema_version")
    comparison_id = manifest["comparison_id"]
    if not isinstance(comparison_id, str) or not SAFE_ID.fullmatch(comparison_id):
        raise ContractError("invalid comparison_id")
    if not isinstance(manifest["pairs"], list) or not manifest["pairs"]:
        raise ContractError("manifest pairs must be a nonempty array")
    return manifest, digest


def validate_output_path(path: Path) -> Path:
    if contains_bigfile(path):
        raise ContractError("bigfile output paths are forbidden")
    if path.exists() or path.is_symlink():
        raise ContractError("output directory must not already exist")
    if contains_symlink_component(path.parent):
        raise ContractError("output parent path must not contain a symbolic link")
    parent = path.parent.resolve(strict=True)
    if contains_bigfile(parent):
        raise ContractError("resolved bigfile output paths are forbidden")
    return parent / path.name


def prepare(manifest_path: Path, artifact_root: Path, output_path: Path) -> dict[str, Any]:
    output = validate_output_path(output_path)
    parent = output.parent
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    manifest_sha: str | None = None
    comparison_id: str | None = None
    report = base_report(None, None)
    bundles: list[PlotBundle] = []
    try:
        try:
            root = validate_root(artifact_root)
            manifest, manifest_sha = load_manifest(manifest_path)
            comparison_id = manifest["comparison_id"]
            report = base_report(manifest_sha, comparison_id)
            pair_ids: set[str] = set()
            pair_identities: set[tuple[str, str]] = set()
            artifact_paths: set[str] = set()
            artifact_inodes: set[tuple[int, int]] = set()
            for index, pair in enumerate(manifest["pairs"]):
                pair_id = pair.get("pair_id") if isinstance(pair, dict) else None
                if isinstance(pair_id, str) and pair_id in pair_ids:
                    raise ContractError(f"duplicate pair_id: {pair_id!r}")
                if isinstance(pair_id, str):
                    pair_ids.add(pair_id)
                try:
                    pair_report, pair_bundles = validate_pair(
                        root, pair, staging / ".input_snapshots" / f"pair-{index:04d}"
                    )
                except ContractError as exc:
                    report["pairs"].append(
                        {
                            "pair_id": pair_id,
                            "status": "NOT_READY",
                            "failure": str(exc),
                        }
                    )
                    report["failures"].append(f"pair[{index}]: {exc}")
                else:
                    pair_paths = {
                        item["path"] for item in pair_report["evidence"].values()
                    }
                    if artifact_paths & pair_paths:
                        raise ContractError("one artifact path is reused across pairs")
                    pair_inodes = {
                        ((root / relative).stat().st_dev, (root / relative).stat().st_ino)
                        for relative in pair_paths
                    }
                    if artifact_inodes & pair_inodes:
                        raise ContractError("one artifact inode is reused across pairs")
                    identity = (
                        pair_report["product_kind"], pair_report["valid_time"]
                    )
                    if identity in pair_identities:
                        raise ContractError(
                            "duplicate product_kind/valid_time comparison pair: "
                            f"{identity[0]} {identity[1]}"
                        )
                    pair_identities.add(identity)
                    artifact_paths.update(pair_paths)
                    artifact_inodes.update(pair_inodes)
                    report["pairs"].append(pair_report)
                    bundles.extend(pair_bundles)
            if not report["failures"] and len(report["pairs"]) == len(manifest["pairs"]):
                comparison_data = []
                for bundle in sorted(bundles, key=lambda item: (item.pair_id, item.plot_id)):
                    relative = Path("comparison_data") / bundle.pair_id / bundle.plot_id
                    metadata = bundle_metadata(bundle, staging / relative)
                    comparison_data.append(
                        {
                            "pair_id": bundle.pair_id,
                            "plot_id": bundle.plot_id,
                            "path": relative.as_posix(),
                            "metadata_sha256": metadata["metadata_sha256"],
                        }
                    )
                report["comparison_data"] = comparison_data
                report["status"] = "READY"
                report["algorithm_comparison_status"] = (
                    "READY_FOR_NUMERICAL_AND_PLOT_COMPARISON"
                )
        except ContractError as exc:
            comparison_data = staging / "comparison_data"
            if comparison_data.exists() and not comparison_data.is_symlink():
                shutil.rmtree(comparison_data)
            report = base_report(manifest_sha, comparison_id)
            report["failures"].append(str(exc))
        report["failures"] = sorted(report["failures"])
        report["pairs"] = sorted(
            report["pairs"], key=lambda item: str(item.get("pair_id", ""))
        )
        snapshots = staging / ".input_snapshots"
        if snapshots.exists() and not snapshots.is_symlink():
            shutil.rmtree(snapshots)
        write_json(staging / "READINESS.json", report)
        os.replace(staging, output)
        return report
    except Exception:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.manifest, args.artifact_root, args.output_directory)
    except (OSError, ContractError) as exc:
        print(f"OPERATIONAL COMPARISON ERROR: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
