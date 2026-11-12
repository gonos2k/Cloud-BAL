#!/usr/bin/env python3
"""Generate a QI/QS/NI proposal using an explicitly attested prior-cycle background.

The common Fortran producer owns the equations and strict NI acceptance. This
boundary verifies native file identity, time, grid and declared dry-air basis.
It publishes a proposal, not a completed model input or a forecast approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from netCDF4 import Dataset, default_fillvals

from initialize_model_moments import (
    KDM6_REFERENCE_SHA256, STATUS_OK, checked_file, read_array, sha,
    validate_kdm6_policy,
)

GRID_ATTRIBUTES = ("MAP_PROJ", "DX", "DY", "CEN_LAT", "CEN_LON", "TRUELAT1", "TRUELAT2", "STAND_LON")
GRID_VARIABLES = {
    "XLAT": ("Time", "south_north", "west_east"),
    "XLONG": ("Time", "south_north", "west_east"),
    "HGT": ("Time", "south_north", "west_east"),
    "ZNU": ("Time", "bottom_top"), "ZNW": ("Time", "bottom_top_stag"),
}
HYBRID_VARIABLES = ("C1H", "C2H", "C3H", "C4H", "C1F", "C2F", "C3F", "C4F", "P_TOP")
RULE = "Retain background ice fraction and mean ice mass; no cap-driven repartition."


def timestamp(text):
    return datetime.strptime(text, "%Y-%m-%d_%H:%M:%S").replace(tzinfo=timezone.utc)


def source_label(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("explicit background source required")
    encoded = value.encode("utf-8")
    if len(encoded) > 256 or b"\0" in encoded:
        raise ValueError("background source exceeds native label contract")
    return encoded


def native_time(ds):
    if getattr(ds, "MP_PHYSICS", None) != 37:
        raise ValueError("background proposal requires KDM6 MP_PHYSICS=37")
    if "Times" not in ds.variables or ds["Times"].dimensions != ("Time", "DateStrLen"):
        raise ValueError("native Times required")
    if ds["Times"].shape != (1, 19):
        raise ValueError("one native valid time required")
    text = b"".join(np.asarray(ds["Times"][:]).reshape(-1)).decode("ascii")
    timestamp(text)
    return text


def grid_fingerprint(ds):
    """Hash exact native coordinates, projection and available hybrid coefficients."""
    digest = hashlib.sha256()
    for name in GRID_ATTRIBUTES:
        if name not in ds.ncattrs():
            raise ValueError(f"missing grid attribute: {name}")
        value = np.asarray(ds.getncattr(name))
        if value.ndim or value.dtype.kind not in "iuf" or not np.isfinite(value):
            raise ValueError(f"invalid grid attribute: {name}")
        digest.update(name.encode() + str(value.dtype).encode() + value.tobytes())
    digest.update(repr(getattr(ds, "HYBRID_OPT", None)).encode())
    for name in (*GRID_VARIABLES, *HYBRID_VARIABLES):
        if name not in ds.variables:
            if name in GRID_VARIABLES:
                raise ValueError(f"missing grid coordinate: {name}")
            digest.update((name + ":absent").encode())
            continue
        var = ds[name]
        if name in GRID_VARIABLES and var.dimensions != GRID_VARIABLES[name]:
            raise ValueError(f"invalid coordinate dimensions: {name}")
        if var.dtype != np.dtype("float32") or any(a in var.ncattrs() for a in ("scale_factor", "add_offset")):
            raise ValueError(f"unsupported grid encoding: {name}")
        value = var[:]
        if (np.ma.is_masked(value) or not np.isfinite(value).all()
                or np.any(value == np.float32(default_fillvals["f4"]))):
            raise ValueError(f"invalid coordinate: {name}")
        if any(np.isin(value, np.asarray(var.getncattr(a))).any()
               for a in ("_FillValue", "missing_value") if a in var.ncattrs()):
            raise ValueError(f"missing coordinate: {name}")
        digest.update(name.encode() + repr(var.dimensions).encode())
        digest.update(str(getattr(var, "units", "")).encode())
        digest.update(repr(value.shape).encode() + np.asarray(value).tobytes())
    return digest.hexdigest()


def publish(output, receipt, arrays, details):
    """Publish a synced receipt first and an atomic proposal commit marker last.

    Receipt existence alone is not success. Consumers require both files and
    verify the proposal SHA. A crash before the marker can leave an orphan
    receipt; no partially written proposal is ever visible at the final path.
    """
    temporary, created = [], []
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            proposed = Path(stream.name)
            temporary.append(proposed)
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        with np.load(proposed, allow_pickle=False) as stored:
            if set(stored.files) != set(arrays) or any(
                    not np.array_equal(stored[key], value) for key, value in arrays.items()):
                raise ValueError("stored proposal readback mismatch")
        details["proposal_sha256"] = sha(proposed)
        details["proposal_file"] = output.name
        with tempfile.NamedTemporaryFile(mode="w", dir=receipt.parent, delete=False) as stream:
            prepared = Path(stream.name)
            temporary.append(prepared)
            json.dump(details, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if json.loads(prepared.read_text()) != details:
            raise ValueError("staged receipt readback mismatch")
        for source, target in ((prepared, receipt), (proposed, output)):
            os.link(source, target)
            created.append((target, source.stat()))
            descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        for path, owned in reversed(created):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                    path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def generate(manifest_path, output, receipt, work_root=None):
    manifest_path, output, receipt = map(Path, (manifest_path, output, receipt))
    manifest_hash = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "background_ice_prior_v1" or manifest.get("mass_basis") != "dry_air":
        raise ValueError("explicit background-ice schema and dry-air basis required")
    if (output.parent.resolve() != receipt.parent.resolve() or output.resolve() == receipt.resolve()
            or output.exists() or receipt.exists()):
        raise ValueError("new distinct proposal and receipt paths required")
    identities = {key: checked_file(manifest[key])
                  for key in ("analysis", "background", "authority", "mask", "driver", "policy")}
    if manifest["analysis"]["sha256"] == manifest["background"]["sha256"]:
        raise ValueError("analysis cannot be its own independent background")
    authority = json.loads(identities["authority"].read_text())
    if (authority.get("kind") != "prior_cycle_forecast"
            or authority.get("mass_basis") != "dry_air"
            or authority.get("microphysics_source_sha256") != KDM6_REFERENCE_SHA256
            or authority.get("analysis_sha256") != manifest["analysis"]["sha256"]
            or authority.get("background_sha256") != manifest["background"]["sha256"]
            or not isinstance(authority.get("independence_attestation"), str)
            or not authority["independence_attestation"].strip()):
        raise ValueError("background lineage/independence attestation required")
    label = source_label(authority.get("source"))
    policy = json.loads(identities["policy"].read_text())
    validate_kdm6_policy(policy)
    with Dataset(identities["analysis"]) as analysis, Dataset(identities["background"]) as background:
        analysis.set_auto_maskandscale(False)
        background.set_auto_maskandscale(False)
        valid_time = native_time(analysis)
        if native_time(background) != valid_time:
            raise ValueError("background valid time differs from analysis")
        cycle = authority.get("cycle_start")
        if not isinstance(cycle, str) or timestamp(cycle) >= timestamp(valid_time):
            raise ValueError("background must originate in an earlier forecast cycle")
        if (getattr(background, "SIMULATION_START_DATE", None) != cycle
                or ("START_DATE" in background.ncattrs() and background.START_DATE != cycle)):
            raise ValueError("background cycle differs from native metadata")
        grid = grid_fingerprint(analysis)
        if grid_fingerprint(background) != grid:
            raise ValueError("background native grid differs; no implicit regridding")
        target = [read_array(analysis[n], n) for n in ("QICE", "QSNOW")]
        prior = [read_array(background[n], n) for n in ("QICE", "QSNOW", "QNICE")]
        inverse = [read_array(analysis[n], n) for n in ("AL", "ALB")]
    shape = target[0].shape
    if len(shape) != 4 or shape[0] != 1 or shape[1] < 2 or any(a.shape != shape for a in (*target, *prior, *inverse)):
        raise ValueError("matching native mass-grid fields required")
    with np.load(identities["mask"], allow_pickle=False) as data:
        mask = np.asarray(data["valid"])
        if str(data["source_sha256"].item()) != manifest["analysis"]["sha256"]:
            raise ValueError("selection mask is not bound to analysis")
        if mask.shape != shape[1:] or mask.dtype.kind not in "biu" or not np.isin(mask, (0, 1)).all() or not mask.any():
            raise ValueError("nonempty explicit selection mask required")
    alt = np.add(*inverse, dtype=np.float32)
    if np.any(alt <= 0) or not np.isfinite(alt).all():
        raise ValueError("invalid analysis dry-air inverse density")
    with np.errstate(over="raise", divide="raise", invalid="raise"):
        density = np.divide(np.float32(1), alt, dtype=np.float32)
    if np.any(density <= 0) or not np.isfinite(density).all():
        raise ValueError("invalid analysis dry-air density")
    with tempfile.TemporaryDirectory(prefix="ice-background-prior.", dir=work_root) as temporary:
        work = Path(temporary)
        inp, out = work / "input.bin", work / "output.bin"
        with inp.open("xb") as stream:
            np.asarray(shape[:0:-1], dtype=np.int32).tofile(stream)
            np.asarray(int(timestamp(valid_time).timestamp()), dtype=np.int64).tofile(stream)
            stream.write(grid.encode("ascii"))
            stream.write(label.ljust(256, b" "))
            for value in (*target, *prior, density):
                np.ascontiguousarray(value[0]).tofile(stream)
            np.ascontiguousarray(mask, dtype=np.int32).tofile(stream)
            for key in ("mass_threshold", "lower", "upper", "number_cap"):
                np.asarray(policy[key], dtype=np.float64).tofile(stream)
        subprocess.run([str(identities["driver"]), str(inp), str(out)], cwd=work, check=True)
        with out.open("rb") as stream:
            header = np.fromfile(stream, dtype=np.int32, count=5)
            if header.size != 5:
                raise ValueError("truncated background producer output")
            if header[0] != STATUS_OK:
                raise ValueError(f"background proposal rejected: location={header[1:].tolist()}; no fallback")
            if np.any(header[1:] != 0):
                raise ValueError("successful producer retained a failure location")
            values = np.fromfile(stream, dtype=np.float32, count=3 * int(np.prod(shape[1:])))
            if stream.read(1) or values.size != 3 * int(np.prod(shape[1:])):
                raise ValueError("invalid background producer output size")
        values = values.reshape((3, *shape[1:]))
        active = mask.astype(bool)
        if not np.isfinite(values[:, active]).all() or np.any(values[:, active] < 0):
            raise ValueError("invalid proposed stored moments")
        before = target[0][0].astype(np.float64) + target[1][0].astype(np.float64)
        after = values[:2].astype(np.float64).sum(axis=0)
        residual = after - before
        if np.any(np.abs(residual[active]) > np.finfo(np.float32).eps * np.maximum(before[active], after[active])):
            raise ValueError("stored proposal does not conserve frozen water")
        for key, path in identities.items():
            checked_file(manifest[key])
        if sha(manifest_path) != manifest_hash:
            raise ValueError("manifest changed during proposal generation")
        arrays = dict(zip(("qi", "qs", "ni"), values))
        arrays.update(valid=mask.astype(np.uint8), source_sha256=manifest["analysis"]["sha256"],
                      source=authority["source"], provenance=np.int32(2),
                      producer="background_ice_prior_v1", producer_receipt=receipt.name,
                      producer_manifest_sha256=manifest_hash)
        details = {"schema": "background_ice_proposal_receipt_v1", "status": "PASS",
                   "manifest_sha256": manifest_hash, "identities": manifest, "authority": authority,
                   "valid_time": valid_time, "grid_sha256": grid, "selected_cells": int(active.sum()),
                   "maximum_frozen_water_residual_kg_kg": float(np.max(np.abs(residual[active]))),
                   "rule": RULE, "native_first_use_verified": False,
                   "density_scope": "file-state float32 1/(AL+ALB); not first-use density",
                   "authority_scope": "Caller-attested independence and dry-air basis; hashes and dates do not prove scientific authority.",
                   "handoff": "Proposal only; complete_ice_snow_initialization must still complete all other moments."}
        publish(output, receipt, arrays, details)
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args()
    generate(args.manifest, args.output, args.receipt, args.work_root)


if __name__ == "__main__":
    main()
