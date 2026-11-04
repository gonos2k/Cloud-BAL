#!/usr/bin/env python3
"""Create a B1-only QNRAIN PSD-prior input after first-call cap validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import numpy as np
from netCDF4 import Dataset


INPUT_SHA256 = "9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5"
POLICY_PATH = Path(__file__).resolve().parents[1] / "docs/evidence/cp02_state_path_20261104/lineage/B1_RAIN_PSD_PRIOR_POLICY_20261104.json"
POLICY_SHA256 = "25387970de9685e3024af7983d47650ab6b6068188f765df58243d6ebefa7601"
ENTRY_FIELDS = ("DEN_ENTRY", "CALLED")
EXPECTED_SHAPE = (1, 39, 282, 234)
LAMBDA_MIN = 961.0
LAMBDA_MAX = 35000.0
LAMBDA_CENTER = float(np.sqrt(LAMBDA_MIN * LAMBDA_MAX))
RHO_WATER = 1000.0
MU = 1.0
D = 3
PIDNR = float(math.pi * RHO_WATER / 6.0 * math.gamma(D + MU + 1.0) / math.gamma(MU + 1.0))
QCRMIN = 1.0e-9
NRMIN = 1.0e-2
NRMAX = 5.0e7
NR_PER_QRAIN = LAMBDA_CENTER**D / PIDNR
_SHA = set("0123456789abcdef")


class PriorError(ValueError):
    """The B1 input or first-call evidence cannot support this prior."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def initialize_qnrain(
    qrain: np.ndarray,
    qnrain: np.ndarray,
    baseline_entry_den: np.ndarray,
    called: np.ndarray,
    *,
    lambda_center: float = LAMBDA_CENTER,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fill input-state zeros where baseline first-call geometry is active."""
    if not math.isfinite(lambda_center) or not LAMBDA_MIN <= lambda_center <= LAMBDA_MAX:
        raise PriorError("LAMBDA_OUTSIDE_SOURCE_RANGE")
    arrays = (qrain, qnrain, baseline_entry_den, called)
    if any(np.shape(array) != EXPECTED_SHAPE for array in arrays):
        raise PriorError("ENTRY_OR_INPUT_SHAPE_MISMATCH")
    called = np.asarray(called)
    if called.dtype != np.bool_:
        raise PriorError("CALLED_MASK_MUST_BE_BOOLEAN")
    if not np.any(called):
        raise PriorError("EMPTY_CALLED_DOMAIN")
    for name, values in (
        ("QRAIN", qrain), ("QNRAIN", qnrain), ("DEN_ENTRY", baseline_entry_den),
    ):
        if not np.all(np.isfinite(np.asarray(values)[called])):
            raise PriorError(f"NONFINITE_CALLED_FIELD:{name}")
    if np.any(np.asarray(baseline_entry_den)[called] <= 0.0):
        raise PriorError("NONPOSITIVE_CALLED_DENSITY")
    if np.any(np.asarray(qrain) < 0.0) or np.any(np.asarray(qnrain) < 0.0):
        raise PriorError("NEGATIVE_INPUT_HYDROMETEOR")
    if not np.all(np.isfinite(qrain)) or not np.all(np.isfinite(qnrain)):
        raise PriorError("NONFINITE_INPUT_HYDROMETEOR")

    active_missing = called[0] & (qrain[0] > QCRMIN) & (qnrain[0] == 0.0)
    candidate = np.array(qnrain, copy=True)
    proposed = (qrain.astype(np.float64) * (lambda_center**D / PIDNR)).astype(qnrain.dtype)
    candidate[0][active_missing] = proposed[0][active_missing]
    # Baseline ENTRY density is only a planning proxy. Candidate first-ENTRY
    # QRAIN/QNRAIN/DEN must be captured separately after the forecast starts.
    internal_number = np.multiply(candidate, baseline_entry_den, dtype=np.float32)
    if np.any(internal_number[0][called[0]] > np.float32(NRMAX)):
        maximum = float(np.max(internal_number[0][called[0]]))
        raise PriorError(f"SOURCE_NUMBER_CAP_EXCEEDED:{maximum:.9g}")
    below_nrmin = active_missing & (internal_number[0] < np.float32(NRMIN))
    diagnostics = {
        "candidate_cells": int(np.count_nonzero(active_missing)),
        "below_nrmin_cells": int(np.count_nonzero(below_nrmin)),
        "max_internal_number_candidate_f32_product": (
            float(np.max(internal_number[0][active_missing])) if np.any(active_missing) else 0.0
        ),
        "candidate_qnrain_sha256": _array_sha256(candidate),
        "input_qrain_sha256": _array_sha256(qrain),
        "input_qnrain_sha256": _array_sha256(qnrain),
        "baseline_entry_den_sha256": _array_sha256(baseline_entry_den),
        "lambda_center_m-1": lambda_center,
        "mean_particle_mass_kg": PIDNR / lambda_center**D,
    }
    return candidate, diagnostics


def validate_candidate_entry(
    initial_qrain: np.ndarray,
    candidate_entry_qrain: np.ndarray,
    candidate_entry_qnrain: np.ndarray,
    candidate_entry_den: np.ndarray,
    called: np.ndarray,
) -> dict[str, Any]:
    """Report the actual first-call candidate state after startup transformations."""
    arrays = (initial_qrain, candidate_entry_qrain, candidate_entry_qnrain, candidate_entry_den, called)
    if any(np.shape(array) != EXPECTED_SHAPE for array in arrays):
        raise PriorError("CANDIDATE_ENTRY_SHAPE_MISMATCH")
    called = np.asarray(called)
    if called.dtype != np.bool_:
        raise PriorError("CALLED_MASK_MUST_BE_BOOLEAN")
    if not np.any(called):
        raise PriorError("EMPTY_CALLED_DOMAIN")
    for name, values in (
        ("INITIAL_QRAIN", initial_qrain), ("ENTRY_QRAIN", candidate_entry_qrain),
        ("ENTRY_QNRAIN", candidate_entry_qnrain), ("ENTRY_DEN", candidate_entry_den),
    ):
        if not np.all(np.isfinite(np.asarray(values)[called])):
            raise PriorError(f"NONFINITE_CANDIDATE_ENTRY:{name}")
    q = np.asarray(candidate_entry_qrain, dtype=np.float32)
    nr = np.asarray(candidate_entry_qnrain, dtype=np.float32)
    den = np.asarray(candidate_entry_den, dtype=np.float32)
    if np.any(den[called] <= 0.0):
        raise PriorError("NONPOSITIVE_CANDIDATE_ENTRY_DENSITY")
    internal_nr = np.multiply(nr, den, dtype=np.float32)
    if np.any(internal_nr[called] > np.float32(NRMAX)):
        raise PriorError("CANDIDATE_ENTRY_SOURCE_NUMBER_CAP_EXCEEDED")
    # KDM6's PSD path uses inclusive lower bounds for both fields.
    source_active = called & (q >= np.float32(QCRMIN)) & (internal_nr >= np.float32(NRMIN))
    raw_lambda = np.full(EXPECTED_SHAPE, np.nan, dtype=np.float64)
    pidnr_f32 = np.float32(PIDNR)
    numerator = np.multiply(pidnr_f32, internal_nr, dtype=np.float32)
    denominator = np.multiply(q, den, dtype=np.float32)
    ratio = np.full(EXPECTED_SHAPE, np.nan, dtype=np.float32)
    np.divide(numerator, denominator, out=ratio, where=source_active)
    raw_lambda[source_active] = np.exp(
        np.multiply(np.log(ratio[source_active], dtype=np.float32), np.float32(1.0 / D), dtype=np.float32),
        dtype=np.float32,
    ).astype(np.float64)
    if not np.all(np.isfinite(raw_lambda[source_active])):
        raise PriorError("NONFINITE_CANDIDATE_ENTRY_PSD")
    if not np.any(source_active):
        raise PriorError("NO_SOURCE_ACTIVE_CANDIDATE_ENTRY_CELLS")
    prior_nr = np.asarray(initial_qrain, dtype=np.float64) * NR_PER_QRAIN
    ratios = np.full(EXPECTED_SHAPE, np.nan, dtype=np.float64)
    valid_prior = called & (initial_qrain > QCRMIN) & (prior_nr > 0.0)
    ratios[valid_prior] = nr[valid_prior] / prior_nr[valid_prior]
    active_lambda = raw_lambda[source_active]
    return {
        "schema": "b1_rain_psd_candidate_entry_preflight_v2",
        "status": "PASS",
        "called_cells": int(np.count_nonzero(called)),
        "source_active_candidate_entry_cells": int(np.count_nonzero(source_active)),
        "entry_source_guard_inactive_cells": int(np.count_nonzero(called & ~source_active)),
        "entry_below_source_nrmin_cells": int(np.count_nonzero(called & (q >= np.float32(QCRMIN)) & (internal_nr < np.float32(NRMIN)))),
        "entry_below_source_qcrmin_cells": int(np.count_nonzero(called & (q < np.float32(QCRMIN)))),
        "entry_negative_qrain_cells_source_guard_inactive": int(np.count_nonzero(called & (q < 0.0))),
        "entry_negative_qnrain_cells_source_guard_inactive": int(np.count_nonzero(called & (nr < 0.0))),
        "candidate_entry_cells_exceeding_nrmax": 0,
        "entry_lambda_float32_formula_reconstruction_m-1": {
            "min": float(np.min(active_lambda)) if active_lambda.size else None,
            "median": float(np.median(active_lambda)) if active_lambda.size else None,
            "max": float(np.max(active_lambda)) if active_lambda.size else None,
            "within_1pct_center_cells": int(np.count_nonzero(np.abs(active_lambda / LAMBDA_CENTER - 1.0) <= 0.01)),
            "source_slope_floor_m-1": LAMBDA_MIN,
            "lambda_reconstruction_dtype": "float32",
            "below_source_slope_floor_cells": int(np.count_nonzero(active_lambda < LAMBDA_MIN)),
            "above_source_fallback_lambda_35000_cells": int(np.count_nonzero(active_lambda > LAMBDA_MAX)),
        },
        "entry_number_over_initial_prior_number_ratio": {
            "median": float(np.nanmedian(ratios[valid_prior])) if np.any(valid_prior) else None,
            "min": float(np.nanmin(ratios[valid_prior])) if np.any(valid_prior) else None,
            "max": float(np.nanmax(ratios[valid_prior])) if np.any(valid_prior) else None,
        },
        "startup_fields_are_distinct_stage": True,
        "initial_qrain_sha256": _array_sha256(initial_qrain),
        "candidate_entry_qrain_sha256": _array_sha256(candidate_entry_qrain),
        "candidate_entry_qnrain_sha256": _array_sha256(candidate_entry_qnrain),
        "candidate_entry_den_sha256": _array_sha256(candidate_entry_den),
    }


def _read_entry_npz(path: Path, expected_sha256: str) -> dict[str, np.ndarray]:
    if not _SHA.issuperset(expected_sha256) or len(expected_sha256) != 64:
        raise PriorError("ENTRY_CAPTURE_HASH_MISSING_OR_INVALID")
    if file_sha256(path) != expected_sha256:
        raise PriorError("ENTRY_CAPTURE_HASH_MISMATCH")
    with np.load(path, allow_pickle=False) as capture:
        if set(capture.files) != set(ENTRY_FIELDS):
            raise PriorError("ENTRY_CAPTURE_FIELD_INVENTORY_MISMATCH")
        return {name: np.asarray(capture[name]) for name in ENTRY_FIELDS}


def _read_input(path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if file_sha256(path) != INPUT_SHA256:
        raise PriorError("B1_INPUT_HASH_MISMATCH")
    with Dataset(path, "r") as dataset:
        if "QRAIN" not in dataset.variables or "QNRAIN" not in dataset.variables:
            raise PriorError("RAIN_FIELDS_MISSING")
        variables = {name: dataset.variables[name] for name in ("QRAIN", "QNRAIN")}
        for name, variable in variables.items():
            if variable.dimensions != ("Time", "bottom_top", "south_north", "west_east"):
                raise PriorError(f"MALFORMED_DIMENSIONS:{name}")
            if np.shape(variable[:]) != EXPECTED_SHAPE:
                raise PriorError(f"MALFORMED_SHAPE:{name}")
            variable.set_auto_maskandscale(False)
        if variables["QRAIN"].getncattr("units").strip() != "kg kg-1":
            raise PriorError("QRAIN_UNITS_MISMATCH")
        if variables["QNRAIN"].getncattr("units").strip() != "kg(-1)":
            raise PriorError("QNRAIN_UNITS_MISMATCH")
        times = dataset.variables.get("Times")
        if times is None or bytes(times[0].tobytes()).decode("ascii").rstrip("\x00") != "2026-08-16_12:00:00":
            raise PriorError("VALID_TIME_MISMATCH")
        qrain = np.asarray(variables["QRAIN"][:])
        qnrain = np.asarray(variables["QNRAIN"][:])
        attrs = {
            "global": {name: dataset.getncattr(name) for name in dataset.ncattrs()},
            "qrain": {name: variables["QRAIN"].getncattr(name) for name in variables["QRAIN"].ncattrs()},
            "qnrain": {name: variables["QNRAIN"].getncattr(name) for name in variables["QNRAIN"].ncattrs()},
        }
    return {"QRAIN": qrain, "QNRAIN": qnrain}, attrs


def _verify_copy(source: Path, candidate: Path, expected_qnrain: np.ndarray) -> None:
    def same_attribute(left: Any, right: Any) -> bool:
        return np.array_equal(np.asarray(left), np.asarray(right))

    with Dataset(source, "r") as left, Dataset(candidate, "r") as right:
        if left.ncattrs() != right.ncattrs():
            raise PriorError("GLOBAL_METADATA_CHANGED")
        for name in left.ncattrs():
            if not same_attribute(left.getncattr(name), right.getncattr(name)):
                raise PriorError(f"GLOBAL_ATTRIBUTE_CHANGED:{name}")
        if set(left.variables) != set(right.variables):
            raise PriorError("VARIABLE_INVENTORY_CHANGED")
        for name in left.variables:
            a, b = left.variables[name], right.variables[name]
            if a.dimensions != b.dimensions or a.ncattrs() != b.ncattrs():
                raise PriorError(f"VARIABLE_METADATA_CHANGED:{name}")
            for attr in a.ncattrs():
                if not same_attribute(a.getncattr(attr), b.getncattr(attr)):
                    raise PriorError(f"VARIABLE_ATTRIBUTE_CHANGED:{name}.{attr}")
            a.set_auto_maskandscale(False)
            b.set_auto_maskandscale(False)
            values_a, values_b = np.asarray(a[:]), np.asarray(b[:])
            if values_a.dtype != values_b.dtype:
                raise PriorError(f"VARIABLE_DTYPE_CHANGED:{name}")
            if name == "QNRAIN":
                if values_b.dtype != expected_qnrain.dtype or values_b.tobytes() != expected_qnrain.tobytes():
                    raise PriorError("CANDIDATE_QNRAIN_READBACK_MISMATCH")
            elif values_a.tobytes() != values_b.tobytes():
                raise PriorError(f"NON_TARGET_VARIABLE_CHANGED:{name}")


def prepare_candidate(input_path: Path, entry_path: Path, entry_sha256: str, output_path: Path) -> dict[str, Any]:
    if file_sha256(POLICY_PATH) != POLICY_SHA256:
        raise PriorError("FROZEN_POLICY_HASH_MISMATCH")
    if os.path.lexists(output_path):
        raise PriorError("OUTPUT_ALREADY_EXISTS")
    fields, attrs = _read_input(input_path)
    entry = _read_entry_npz(entry_path, entry_sha256)
    candidate, diagnostics = initialize_qnrain(
        fields["QRAIN"], fields["QNRAIN"], entry["DEN_ENTRY"], entry["CALLED"],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        shutil.copy2(input_path, temporary_path)
        with Dataset(temporary_path, "r+") as dataset:
            variable = dataset.variables["QNRAIN"]
            variable.set_auto_maskandscale(False)
            variable[:] = candidate
        _verify_copy(input_path, temporary_path, candidate)
        os.link(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    temporary_path.unlink(missing_ok=True)
    diagnostics.update({
        "schema": "b1_rain_psd_prior_candidate_v1",
        "status": "PREPARED_CANDIDATE_NOT_RUN",
        "policy_path": str(POLICY_PATH.resolve()),
        "policy_sha256": POLICY_SHA256,
        "initializer_sha256": file_sha256(Path(__file__).resolve()),
        "input_path": str(input_path.resolve()),
        "input_sha256": file_sha256(input_path),
        "baseline_density_capture_path": str(entry_path.resolve()),
        "entry_capture_sha256": file_sha256(entry_path),
        "output_path": str(output_path.resolve()),
        "output_sha256": file_sha256(output_path),
        "target_field": "QNRAIN",
        "unchanged_fields_verified": "all variables except QNRAIN, including QRAIN/QVAPOR/T, all metadata and all global attributes",
        "prior_status": "DECLARED_RESEARCH_PSD_PRIOR_NOT_OBSERVED_CALIBRATION",
        "units": attrs["qnrain"].get("units", ""),
    })
    return diagnostics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--baseline-density-capture", required=True, type=Path, help="Hash-bound NPZ with baseline first-KDM6 DEN and call mask")
    parser.add_argument("--baseline-density-capture-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.receipt):
            raise PriorError("RECEIPT_ALREADY_EXISTS")
        receipt = prepare_candidate(args.input, args.baseline_density_capture, args.baseline_density_capture_sha256, args.output)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"B1_RAIN_PRIOR_REJECTED:{error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
