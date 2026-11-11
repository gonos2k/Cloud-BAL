#!/usr/bin/env python3
"""Run a pinned real producer in scratch and complete its native moments.

This is an input-generation boundary, not a forecast launcher. The producer and
policy identities are caller attestations; hashes alone do not prove a build.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib

import numpy as np
from netCDF4 import Dataset, default_fillvals

MASS = ("QCLOUD", "QICE", "QRAIN", "QGRAUP", "QSNOW")
MOMENT = ("QNCLOUD", "QNICE", "QNRAIN", "QNCCN", "QIB")
DIMS = ("Time", "bottom_top", "south_north", "west_east")
# Values from cloud_bal_state.f90, serialized by model_moment_driver.
STATUS_FAILED, STATUS_DEGRADED, STATUS_OK = -10, 10, 20
UNITS = {**dict.fromkeys(MASS, "kg kg-1"), **dict.fromkeys(MOMENT[:4], "kg-1"),
         "QIB": "m3 kg-1", "AL": "m3 kg-1", "ALB": "m3 kg-1",
         "P": "pa", "PB": "pa", "T": "k", "QVAPOR": "kg kg-1"}
UNIT_ALIASES = {"kg(-1)": "kg-1", "m(3) kg(-1)": "m3 kg-1"}
KDM6_REFERENCE = (Path(__file__).resolve().parents[1] /
                  "docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90")
KDM6_REFERENCE_SHA256 = "f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595"
# Mean mass = coefficient / lambda**3. Cloud uses muc=2 generalized gamma.
KDM6_LIMITS = ((math.pi * 1000.0 / 6.0, 12000.0, 500000.0),
               (500.0 * math.pi, 9080.0, 1820000.0),
               (4000.0 * math.pi, 961.0, 35000.0))
KDM6_CAPS = np.array([5e10, 1e6, 5e7, 2e10])



def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def checked_file(item):
    path = Path(item["path"]).resolve(strict=True)
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"input hash mismatch: {path}")
    return path


def validate_kdm6_policy(policy):
    """Require a caller policy to be contained within the pinned source profile."""
    if sha(KDM6_REFERENCE) != KDM6_REFERENCE_SHA256:
        raise ValueError("KDM6 reference source hash mismatch")
    if (not policy.get("source") or policy.get("declared_before_experiment") is not True
            or policy.get("mp_physics") != 37):
        raise ValueError("explicit source-bound prior policy required")
    arrays = {}
    for name, size in (("mass_threshold", 5), ("lower", 5),
                       ("upper", 5), ("number_cap", 4)):
        values = np.asarray(policy[name], dtype=np.float64)
        if values.shape != (size,) or not np.isfinite(values).all():
            raise ValueError(f"invalid policy: {name}")
        arrays[name] = values
    lower, upper, caps = arrays["lower"], arrays["upper"], arrays["number_cap"]
    if np.any(arrays["mass_threshold"] < 0) or np.any(caps <= 0) or np.any(caps > KDM6_CAPS):
        raise ValueError("policy exceeds KDM6 source thresholds or number caps")
    for slot, (coefficient, lambda_min, lambda_max) in enumerate(KDM6_LIMITS):
        source_min = coefficient / lambda_max**3
        source_max = coefficient / lambda_min**3
        if not (source_min <= lower[slot] <= upper[slot] <= source_max):
            raise ValueError(f"policy exceeds KDM6 source bounds: slot {slot + 1}")
    if not (0.0 <= lower[3] <= upper[3]):
        raise ValueError("invalid unused NN bounds")
    if not (100.0 <= lower[4] <= upper[4] <= 900.0):
        raise ValueError("policy exceeds KDM6 graupel density bounds")


def read_array(var, name):
    units = getattr(var, "units", None)
    if not isinstance(units, str):
        raise ValueError(f"missing units: {name}")
    units = " ".join(units.lower().split())
    if UNIT_ALIASES.get(units, units) != UNITS[name]:
        raise ValueError(f"unsupported units: {name}")
    if var.dimensions != DIMS or var.dtype != np.dtype("float32"):
        raise ValueError(f"expected native float32 mass-grid field: {name}")
    if any(attr in var.ncattrs() for attr in ("scale_factor", "add_offset")):
        raise ValueError(f"unsupported packed field: {name}")
    value = var[:]
    if np.any(value == np.float32(default_fillvals["f4"])):
        raise ValueError(f"missing field values: {name}")
    if any(np.isin(value, np.asarray(var.getncattr(attr))).any() for attr in ("_FillValue", "missing_value") if attr in var.ncattrs()):
        raise ValueError(f"missing field values: {name}")
    if np.ma.is_masked(value) or not np.isfinite(value).all():
        raise ValueError(f"masked or nonfinite field: {name}")
    return np.asarray(value)


def bundle(npz, prefix, shape):
    expected = (5, *shape)
    value = np.asarray(npz[prefix + "_value"], dtype=np.float64)
    valid = np.asarray(npz[prefix + "_valid"])
    source = np.asarray(npz[prefix + "_provenance"], dtype=np.int32)
    if value.shape != expected or valid.shape != expected or source.shape != expected:
        raise ValueError(f"invalid bundle shape: {prefix}")
    if not np.isin(valid, (0, 1)).all():
        raise ValueError(f"invalid bundle mask: {prefix}")
    return value, valid.astype(np.int32), source


def complete_file(source, target, driver, policy, candidates, work, use_theta_m):
    validate_kdm6_policy(policy)
    with Dataset(source) as ds:
        ds.set_auto_maskandscale(False)
        if getattr(ds, "MP_PHYSICS", None) != 37:
            raise ValueError("unsupported model MP_PHYSICS")
        if getattr(ds, "USE_THETA_M", None) != use_theta_m:
            raise ValueError("file USE_THETA_M differs from manifest")
        if "Times" not in ds.variables or ds["Times"].shape[0] != 1:
            raise ValueError("one native valid time is required")
        valid_time = b"".join(np.asarray(ds["Times"][:]).reshape(-1)).decode("ascii")
        fields = {name: read_array(ds[name], name) for name in (*MASS, *MOMENT, "AL", "ALB", "P", "PB", "T", "QVAPOR")}
        shape = fields[MASS[0]].shape
        if len(shape) != 4 or shape[0] != 1 or any(a.shape != shape for a in fields.values()):
            raise ValueError("one matching native initial time record is required")
        with np.load(candidates, allow_pickle=False) as npz:
            if str(npz["source_sha256"].item()) != sha(source):
                raise ValueError("candidate source hash mismatch")
            bg = bundle(npz, "background", shape[1:])
            prior = bundle(npz, "prior", shape[1:])
            obs = bundle(npz, "observed", shape[1:])
        # The initial inverse density is a same-time pre-advection proxy, not
        # an assertion about the later pre-microphysics value.
        alt = np.add(fields["AL"][0], fields["ALB"][0], dtype=np.float32)
        if np.any(alt <= 0) or not np.isfinite(alt).all():
            raise ValueError("invalid initial AL+ALB")
        den = np.divide(np.float32(1), alt, dtype=np.float32)
        if not np.isfinite(den).all() or np.any(den <= 0):
            raise ValueError("invalid initial dry density")
        # Background values are the exact model moments, with caller-supplied
        # validity and provenance. This prevents unrelated candidate state.
        if not np.array_equal(bg[0], np.stack([fields[n][0] for n in MOMENT]).astype(np.float64)):
            raise ValueError("background moments differ from native input")
        before = {name: hashlib.sha256(np.asarray(var[:]).tobytes()).digest()
                  for name, var in ds.variables.items()}
    inp, out = work / "driver.in", work / "driver.out"
    with inp.open("wb") as f:
        np.asarray(shape[:0:-1], dtype=np.int32).tofile(f)
        for name in MASS:
            fields[name][0].tofile(f)
        den.tofile(f)
        for name in ("P", "PB", "T", "QVAPOR"):
            fields[name][0].tofile(f)
        np.asarray([use_theta_m], dtype=np.int32).tofile(f)
        for b in (bg, prior, obs):
            for a in b:
                np.ascontiguousarray(a).tofile(f)
        for key, size in (("mass_threshold", 5), ("lower", 5), ("upper", 5), ("number_cap", 4)):
            a = np.asarray(policy[key], dtype=np.float64)
            if a.shape != (size,) or not np.isfinite(a).all():
                raise ValueError(f"invalid policy: {key}")
            a.tofile(f)
    subprocess.run([str(driver), str(inp), str(out)], cwd=work, check=True)
    count = 5 * int(np.prod(shape[1:]))
    with out.open("rb") as f:
        status = np.fromfile(f, dtype=np.int32, count=1)
        location = np.fromfile(f, dtype=np.int32, count=4)
        values = np.fromfile(f, dtype=np.float64, count=count)
        valid = np.fromfile(f, dtype=np.int32, count=count)
        provenance = np.fromfile(f, dtype=np.int32, count=count)
        temperature_range = np.fromfile(f, dtype=np.float32, count=2)
        failure_reason = np.fromfile(f, dtype=np.int32, count=1)
        interval = np.fromfile(f, dtype=np.float64, count=2)
        sizes = (status.size, location.size, values.size, valid.size, provenance.size,
                 temperature_range.size, failure_reason.size, interval.size)
        if (f.read(1) or sizes != (1, 4, count, count, count, 2, 1, 2)
                or not np.isfinite(temperature_range).all() or not np.isfinite(interval).all()):
            raise ValueError("invalid driver output")
    reasons = {1: "INVALID_OR_MISSING_INPUT", 2: "EMPTY_ANALYTICAL_INTERVAL", 3: "CANDIDATE_INADMISSIBLE"}
    reason = int(failure_reason[0])
    if not ((status[0] in (STATUS_OK, STATUS_DEGRADED) and reason == 0)
            or (status[0] == STATUS_FAILED and reason in reasons)):
        raise ValueError("inconsistent driver status and failure reason")
    if status[0] != STATUS_OK or not np.all(valid == 1) or not np.isfinite(values).all():
        raise ValueError(f"moment completion failed or incomplete: location={location.tolist()}, "
                         f"reason={reasons.get(reason, 'INCOMPLETE')} ({reason}), feasible_interval={interval.tolist()}")
    values = values.reshape((5, *shape[1:])).astype(np.float32)
    if not np.isfinite(values).all():
        raise ValueError("moment cannot be represented in native dtype")
    shutil.copy2(source, target)
    with Dataset(target, "r+") as ds:
        for name, value in zip(MOMENT, values):
            ds[name][0] = value
    with Dataset(target) as ds:
        ds.set_auto_maskandscale(False)
        for name, var in ds.variables.items():
            if name not in MOMENT and hashlib.sha256(np.asarray(var[:]).tobytes()).digest() != before[name]:
                raise ValueError(f"nonmoment changed: {name}")
        for name, value in zip(MOMENT, values):
            if not np.array_equal(read_array(ds[name], name)[0], value):
                raise ValueError(f"moment readback mismatch: {name}")
    return {"status": int(status[0]), "valid_time": valid_time, "input_thermodynamics": {"fields_sha256": {name: hashlib.sha256(fields[name].tobytes()).hexdigest() for name in ("P", "PB", "T", "QVAPOR", "AL", "ALB")}, "pressure": "P+PB", "exner": "(pressure/100000)**(287/1004.5)", "temperature": "(T+300)*exner", "driver_temperature_range_kelvin": temperature_range.tolist(), "scope": "file-state inputs and source formulas; not first-use capture"}, "provenance_encoding": "zlib-base64 little-endian int32, slot,z,y,x", "provenance_shape": [5, *shape[1:]], "provenance_data": base64.b64encode(zlib.compress(provenance.astype("<i4").tobytes())).decode("ascii"), "provenance_counts": {str(int(x)): int((provenance == x).sum()) for x in np.unique(provenance)}, "initial_dry_density": "float32 1/(float32(AL+ALB)); pre-advection proxy"}


def run_real_and_complete(manifest_path, output, receipt):
    manifest_hash = sha(manifest_path)
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("stage") != "fresh_real_before_model_launch" or (type(manifest.get("use_theta_m")) is not int or manifest["use_theta_m"] not in (0, 1)) or manifest.get("mp_physics") != 37:
        raise ValueError("explicit fresh-real stage and use_theta_m required")
    exe, driver, candidates, policy_path = (checked_file(manifest[k]) for k in ("producer", "driver", "candidates", "policy"))
    inputs = [(item["name"], checked_file(item)) for item in manifest["inputs"]]
    for key in ("source", "build"):
        checked_file(manifest[key])
    if not inputs or not any(name == "namelist.input" for name, _ in inputs):
        raise ValueError("pinned namelist.input required")
    if len({name for name, _ in inputs}) != len(inputs) or any(Path(name).name != name for name, _ in inputs):
        raise ValueError("input names must be unique basenames")
    if any(name.startswith(("wrfinput_", "wrfrst_", "wrfout_")) for name, _ in inputs):
        raise ValueError("producer inputs cannot include model output or restart files")
    namelist = next(path for name, path in inputs if name == "namelist.input")
    text = re.sub(r"!.*", "", namelist.read_text()).lower()
    restart = re.findall(r"\brestart\s*=\s*(\.[a-z]+\.)", text)
    if restart != [".false."]:
        raise ValueError("namelist must explicitly disable restart")
    mp = re.findall(r"\bmp_physics\s*=\s*(\d+)\b", text)
    if mp != ["37"]:
        raise ValueError("namelist MP_PHYSICS must be 37")
    theta = re.findall(r"\buse_theta_m\s*=\s*([01])\b", text)
    if theta != [str(manifest["use_theta_m"])]:
        raise ValueError("namelist use_theta_m must match manifest")
    policy = json.loads(policy_path.read_text())
    validate_kdm6_policy(policy)
    output, receipt = Path(output).absolute(), Path(receipt).absolute()
    if output == receipt or output.exists() or receipt.exists():
        raise ValueError("output and receipt must be distinct new paths")
    with tempfile.TemporaryDirectory(prefix="native-moments-") as tmp:
        work = Path(tmp)
        for name, path in inputs:
            shutil.copy2(path, work / name)
        subprocess.run([str(exe)], cwd=work, check=True)
        for name, path in inputs:
            if sha(work / name) != sha(path):
                raise ValueError(f"producer modified input: {name}")
        source = work / "wrfinput_d01"
        if not source.is_file():
            raise ValueError("producer did not create wrfinput_d01")
        source_hash = sha(source)
        candidate = work / "completed.nc"
        details = complete_file(source, candidate, driver, policy, candidates, work, manifest["use_theta_m"])
        if sha(source) != source_hash:
            raise ValueError("producer output changed during completion")
        for key in ("producer", "driver", "candidates", "policy", "source", "build"):
            checked_file(manifest[key])
        for item in manifest["inputs"]:
            checked_file(item)
        validate_kdm6_policy(policy)
        if sha(manifest_path) != manifest_hash:
            raise ValueError("manifest changed during completion")
        data = {"schema": "fresh_real_moment_handoff_v1", "stage": manifest["stage"], "use_theta_m": manifest["use_theta_m"], "producer_exit": 0, "producer_output_sha256": source_hash, "output_sha256": sha(candidate), "manifest_sha256": manifest_hash, "kdm6_reference_sha256": KDM6_REFERENCE_SHA256, "identities": manifest, "completion": details, "density_scope": "file_state_proxy", "native_first_use_verified": False, "provenance_limit": "Caller-attested producer and build; hashes do not prove source-to-binary identity or later first-call state."}
        output.parent.mkdir(parents=True, exist_ok=True)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive publication, with rollback if either link fails.
        candidate_tmp = receipt_tmp = None
        published = False
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as f:
                candidate_tmp = Path(f.name)
            with tempfile.NamedTemporaryFile(dir=receipt.parent, mode="w", delete=False) as f:
                receipt_tmp = Path(f.name)
                json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
                f.write("\n")
            shutil.copyfile(candidate, candidate_tmp)
            os.link(candidate_tmp, output)
            published = True
            os.link(receipt_tmp, receipt)
        except BaseException:
            if published:
                output.unlink(missing_ok=True)
            raise
        finally:
            if candidate_tmp is not None:
                candidate_tmp.unlink(missing_ok=True)
            if receipt_tmp is not None:
                receipt_tmp.unlink(missing_ok=True)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("output")
    parser.add_argument("receipt")
    args = parser.parse_args()
    run_real_and_complete(args.manifest, args.output, args.receipt)


if __name__ == "__main__":
    main()
