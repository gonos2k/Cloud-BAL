#!/usr/bin/env python3
"""Classify retained PR87 source-only and full-candidate REAL32 failures."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "c84cbd3a0bc366112afe9ebad1087a220eb23b46"
RUN_ROOTS = {
    "OFF": Path("/var/tmp/pr87_joint_OFF_40s_20261016"),
    "COUPLED": Path("/var/tmp/pr87_joint_COUPLED_40s_20261016"),
}
BUILD_RECEIPT = Path("/var/tmp/pr87_joint_cycle_build_20261016_v2/pr87_native_overlay_build.json")
BUILD_RECEIPT_SHA256 = "95a82d7089657e85b96aeafafe8476de6b67339772017d39048e713dac3cca63"
LEDGER_SHA256 = "f7ce6365240a93339dcf61003b61103feeab521a09efb978e621026d6732bd88"
RUN_RECEIPT_SHA256 = {
    "OFF": "525812ebf6e0e9a82accc7ddd97ff673f98397b9ea53e91d6f889006c8142503",
    "COUPLED": "b8dea1ca3f8848289b9987ce586e7dcffc15e710b58b56869b54b437b099dfc2",
}
PREFLIGHT_SHA256 = {
    "OFF": "ceea8d8c78503a3e0dfebe01eadc304a93ab426a79553cf114da4c260826dd4e",
    "COUPLED": "8116a1e73e85774c8c1086521ee1a0c2fb5cbd8d16a94621bd7f7c9a400d0969",
}
SOURCE_RECEIPT_SHA256 = {
    "OFF": "65fe21132d20292d9a6e20209e42fa63d96e7680b9ed1e29d0b1b6ee1a187a3e",
    "COUPLED": "8dc7aa4c8b1cdffc72ab29da5a8db255ee96a271bb452fb5bd73a1e62f32d675",
}
V3_RUN_ROOTS = {
    "OFF": Path("/var/tmp/pr87_joint_OFF_40s_v3_20261016"),
    "COUPLED": Path("/var/tmp/pr87_joint_COUPLED_40s_v3_20261016"),
}
V3_BUILD_RECEIPT = Path("/var/tmp/pr87_joint_cycle_build_20261016_v3/pr87_native_overlay_build.json")
V3_BUILD_RECEIPT_SHA256 = "0745161bc235fe3fbc16f7c33105f7f6316388dc6f348600c31975f85d4e6cf9"
V3_OVERLAY_EXE_SHA256 = "0a53474445b5a1a021572ae05d99fc677993bd4355d7dac97383589bbdf72ea5"
V3_LEDGER_SHA256 = "00688a8c1623135d5eeb777c08092ac982ac744afa475024cfe10e9f5e966bad"
V3_STORAGE_SHA256 = "d32e8863b14140a36813373c0ac0f89a990b64fcc60d7577c4a91a1e1d42c9aa"
V3_RUN_RECEIPT_SHA256 = {
    "OFF": "66c77a62607d5b86cd9ae6d4481e6a76cf4a45fdf139c6ab3a80ba47425cb3f4",
    "COUPLED": "f5e23ec8742265cdb7941140bfb79ce465519fabafe99b55791bfe1653e190d4",
}
V3_SOURCE_RECEIPT_SHA256 = {
    "OFF": "65fe21132d20292d9a6e20209e42fa63d96e7680b9ed1e29d0b1b6ee1a187a3e",
    "COUPLED": "8dc7aa4c8b1cdffc72ab29da5a8db255ee96a271bb452fb5bd73a1e62f32d675",
}
PARENT_EXE_SHA256 = "9642a471acd39320efca247a55104da9369ef93d8735e60a0d266bf20332b943"
OVERLAY_EXE_SHA256 = "0ee83b88eb94112ad152b8f780e81e3c996cc86f2d70cba4095a89e6839fc8da"
NATIVE_FRAGMENT_SHA256 = "e2186892418889a3a943181d827b83e2af3aac12eac3a770fca33e2314dea5eb"
BASE_KERNEL_SHA256 = "0291a36603b585b310eefc7fe2b6de5635bd769855c72ddf728d0c031862418b"
PARENT_KERNEL_MODULE_SHA256 = "005ce953c3dc014934b747769daa75a1d2bfbff5e486511d7a0ce0daa01a2950"
PAIR_BOUNDS = (
    (4.188790204786391e-15, 3.0300855069345996e-10),
    (1570.79638671875 / 1820000.0**3, 1570.79638671875 / 9080.0**3),
    (2.930931921716425e-10, 1.4159232106169906e-5),
    (100.0, 900.0),
)
PAIR_NAMES = ("QC/QNC", "QI/QNI", "QR/QNR", "QG/QIB")
SOURCE_MARKERS = {"SOURCE", "SOURCE_FAILURE_COUNT", "SOURCE_INVALID_OPERAND", "SOURCE_NOT_STORABLE_R32"}
ALL_LEDGER_MARKERS = SOURCE_MARKERS | {"FULL", "FULL_FAILURE_COUNT"}
FLOAT32_MAX = 3.4028234663852886e38
FLOAT32_MIN_SUBNORMAL = 2.0**-149


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_sha(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"{label} hash mismatch: {path}")


def as_float32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


def float32_spacing(value: float) -> float:
    """Return Fortran SPACING(REAL(value,REAL32)) for positive normal bounds."""
    rounded = as_float32(value)
    bits = struct.unpack("!I", struct.pack("!f", rounded))[0]
    next_value = struct.unpack("!f", struct.pack("!I", bits + 1))[0]
    return abs(next_value - rounded)


def read_source_rows(path: Path) -> tuple[list[list[float]], int, dict[str, int]]:
    """Read wrapped list-directed SOURCE rows without changing the gzip ledger."""
    rows: list[list[float]] = []
    declared_count = None
    other_markers: dict[str, int] = {}
    lines = gzip.open(path, "rt", errors="strict").read().splitlines()
    index = 0
    while index < len(lines):
        tokens = lines[index].split()
        if not tokens:
            index += 1
            continue
        marker = tokens[0]
        if marker == "SOURCE_FAILURE_COUNT":
            if len(tokens) != 2:
                raise ValueError(f"malformed failure count in {path}:{index + 1}")
            declared_count = int(tokens[1])
            index += 1
            continue
        if marker in {"SOURCE_INVALID_OPERAND", "SOURCE_NOT_STORABLE_R32"}:
            other_markers[marker] = other_markers.get(marker, 0) + 1
            index += 1
            continue
        if marker != "SOURCE":
            index += 1
            continue
        values = tokens[1:]
        index += 1
        while index < len(lines):
            continuation = lines[index].split()
            if continuation and continuation[0] in ALL_LEDGER_MARKERS:
                break
            values.extend(continuation)
            index += 1
        if len(values) != 16:
            raise ValueError(f"SOURCE row at {path}:{index + 1} has {len(values)} values, expected 16")
        try:
            rows.append([float(value.replace("D", "E").replace("d", "e")) for value in values])
        except ValueError as exc:
            raise ValueError(f"nonnumeric SOURCE row in {path}") from exc
    if declared_count is None:
        raise ValueError(f"missing SOURCE_FAILURE_COUNT in {path}")
    if declared_count != len(rows):
        raise ValueError(f"declared/parsed SOURCE counts differ in {path}: {declared_count}/{len(rows)}")
    return rows, declared_count, other_markers


def read_full_rows(path: Path) -> tuple[list[list[float]], int]:
    """Read wrapped list-directed FULL rows, preserving the raw ledger."""
    rows: list[list[float]] = []
    declared_count = None
    lines = gzip.open(path, "rt", errors="strict").read().splitlines()
    index = 0
    while index < len(lines):
        tokens = lines[index].split()
        if not tokens:
            index += 1
            continue
        if tokens[0] == "FULL_FAILURE_COUNT":
            if len(tokens) != 2:
                raise ValueError(f"malformed FULL failure count in {path}:{index + 1}")
            declared_count = int(tokens[1])
            index += 1
            continue
        if tokens[0] != "FULL":
            index += 1
            continue
        values = tokens[1:]
        index += 1
        while index < len(lines):
            continuation = lines[index].split()
            if continuation and continuation[0] in ALL_LEDGER_MARKERS:
                break
            values.extend(continuation)
            index += 1
        if len(values) != 20:
            raise ValueError(f"FULL row at {path}:{index + 1} has {len(values)} values, expected 20")
        try:
            rows.append([float(value.replace("D", "E").replace("d", "e")) for value in values])
        except ValueError as exc:
            raise ValueError(f"nonnumeric FULL row in {path}") from exc
    if declared_count is None or declared_count != len(rows):
        raise ValueError(f"declared/parsed FULL counts differ in {path}: {declared_count}/{len(rows)}")
    return rows, declared_count


def classify_full_row(values: list[float]) -> dict:
    """Classify the full continuous candidate and its independent REAL32 rounding."""
    timestep, rk, pair_value, i, j, k = values[:6]
    q_continuous, n_continuous = values[14:16]
    q_logged, n_logged, density = values[16:19]
    pair = int(pair_value) - 1
    if pair not in range(4):
        raise ValueError(f"invalid pair index: {pair_value}")
    continuous_valid, continuous_reason, continuous_ratio, _ = validate_pair(
        q_continuous, n_continuous, density, pair)
    q_rounded, n_rounded = as_float32(q_continuous), as_float32(n_continuous)
    rounded_valid, rounded_reason, rounded_ratio, _ = validate_pair(q_rounded, n_rounded, density, pair)
    if not continuous_valid:
        classification = "continuous_candidate_outside_coded_8ulp_gate"
    elif not rounded_valid:
        classification = "continuous_valid_real32_rounding_crosses_gate"
    else:
        classification = "continuous_and_rounded_pair_pass"
    minimum, _ = PAIR_BOUNDS[pair]
    spacing = float32_spacing(minimum)
    return {
        "timestep": int(timestep), "rk": int(rk), "pair_index": pair + 1,
        "pair": PAIR_NAMES[pair], "i": int(i), "j": int(j), "k": int(k),
        "continuous_q": q_continuous, "continuous_n": n_continuous,
        "continuous_q_over_n": continuous_ratio,
        "continuous_ratio_margin_ulps_from_minimum": (
            (continuous_ratio - minimum) / spacing if continuous_ratio is not None else None),
        "continuous_valid_with_coded_8ulp_tolerance": continuous_valid,
        "continuous_validity_reason": continuous_reason,
        "independently_rounded_q": q_rounded, "independently_rounded_n": n_rounded,
        "independently_rounded_q_over_n": rounded_ratio,
        "independently_rounded_valid_with_coded_8ulp_tolerance": rounded_valid,
        "independently_rounded_validity_reason": rounded_reason,
        "logged_full_stored_q": q_logged, "logged_full_stored_n": n_logged,
        "classification": classification,
    }


def validate_pair(q: float, n: float, density: float, pair: int) -> tuple[bool, str, float | None, float | None]:
    if not all(math.isfinite(value) for value in (q, n, density)):
        return False, "nonfinite", None, None
    if abs(q) > FLOAT32_MAX or abs(n) > FLOAT32_MAX:
        return False, "outside_real32_range", None, None
    if density <= 0.0:
        return False, "nonpositive_dry_density", None, None
    if q < 0.0 or n < 0.0:
        return False, "negative_moment", None, None
    number_density = n * density
    if n > 0.0 and (not math.isfinite(number_density) or
                    number_density <= 0.5 * FLOAT32_MIN_SUBNORMAL or number_density > FLOAT32_MAX):
        return False, "number_density_unstorable", None, number_density
    if q == 0.0:
        return (n == 0.0), ("valid" if n == 0.0 else "zero_q_positive_n"), None, number_density
    if n == 0.0:
        return False, "positive_q_zero_n", None, number_density
    ratio = q / n
    minimum, maximum = PAIR_BOUNDS[pair]
    lower_tolerance = 8.0 * float32_spacing(minimum)
    upper_tolerance = 8.0 * float32_spacing(maximum)
    if ratio < minimum - lower_tolerance:
        return False, "below_min_ratio", ratio, number_density
    if ratio > maximum + upper_tolerance:
        return False, "above_max_ratio", ratio, number_density
    return True, "valid", ratio, number_density


def classify_row(values: list[float]) -> dict:
    rk, pair_value, i, j, k, old_carrier, new_carrier, q_base, n_base, q_source, n_source, \
        q_continuous, n_continuous, q_logged, n_logged, density = values
    pair = int(pair_value) - 1
    if pair not in range(4):
        raise ValueError(f"invalid pair index: {pair_value}")
    q_rounded = as_float32(q_continuous)
    # Fortran list-directed output prints too few decimal digits to recover
    # every positive REAL32 bit pattern. Use the logged stored values for ratio
    # checks; the listed cases sit well beyond the 8-ULP tolerance boundary.
    continuous_valid, continuous_reason, continuous_ratio, number_density = validate_pair(
        q_continuous, n_continuous, density, pair)
    stored_valid, stored_reason, stored_ratio, stored_number_density = validate_pair(
        q_logged, n_logged, density, pair)
    minimum, maximum = PAIR_BOUNDS[pair]
    if q_continuous > 0.0:
        if continuous_ratio is None:
            raise ValueError("positive continuous Q must have a pair ratio")
        if continuous_ratio < minimum or continuous_ratio > maximum:
            continuous_exact_psd = False
        else:
            continuous_exact_psd = True
    else:
        continuous_exact_psd = q_continuous == 0.0 and n_continuous == 0.0
    if stored_ratio is not None and stored_ratio < minimum:
        stored_ratio_boundary = "minimum"
        stored_ratio_endpoint = minimum
    elif stored_ratio is not None and stored_ratio > maximum:
        stored_ratio_boundary = "maximum"
        stored_ratio_endpoint = maximum
    else:
        stored_ratio_boundary = None
        stored_ratio_endpoint = None
    if not continuous_valid:
        classification = "continuous_source_infeasible"
    elif q_rounded == 0.0 and q_logged == 0.0 and q_continuous > 0.0 and n_logged > 0.0:
        classification = "q_underflow_pair_loss"
    elif not stored_valid:
        classification = f"stored_{stored_reason}"
    else:
        classification = "stored_valid"
    return {
        "rk": int(rk), "pair_index": pair + 1, "pair": PAIR_NAMES[pair],
        "i": int(i), "j": int(j), "k": int(k),
        "old_dry_carrier": old_carrier, "new_dry_carrier": new_carrier,
        "base_q": q_base, "base_n": n_base, "q_source": q_source, "n_source": n_source,
        "continuous_q": q_continuous, "continuous_n": n_continuous,
        "continuous_q_over_n": continuous_ratio, "dry_density": density,
        "continuous_number_density": number_density,
        "continuous_valid_with_coded_8ulp_tolerance": continuous_valid,
        "continuous_validity_reason": continuous_reason,
        "continuous_exact_pair_bounds": continuous_exact_psd,
        "real32_q_logged": q_logged, "real32_n_logged": n_logged,
        "real32_q_over_n": stored_ratio,
        "real32_number_density": stored_number_density,
        "real32_valid_with_coded_8ulp_tolerance": stored_valid,
        "real32_validity_reason": stored_reason,
        "real32_ratio_boundary": stored_ratio_boundary,
        "real32_ratio_endpoint": stored_ratio_endpoint,
        "real32_endpoint_8ulp_tolerance": (
            8.0 * float32_spacing(stored_ratio_endpoint) if stored_ratio_endpoint is not None else None),
        "real32_ratio_margin_ulps": (
            (stored_ratio - stored_ratio_endpoint) / float32_spacing(stored_ratio_endpoint)
            if stored_ratio_endpoint is not None and stored_ratio is not None else None),
        "classification": classification,
    }


def summarize_rows(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    by_pair: dict[str, dict[str, int]] = {}
    for row in rows:
        label, pair = row["classification"], row["pair"]
        counts[label] = counts.get(label, 0) + 1
        by_pair.setdefault(pair, {})[label] = by_pair.setdefault(pair, {}).get(label, 0) + 1
    underflow = [row for row in rows if row["classification"] == "q_underflow_pair_loss"]
    ratio_failures = [row for row in rows if row["classification"].startswith("stored_below_min") or
                      row["classification"].startswith("stored_above_max")]
    def ranges(items: list[dict], key: str) -> dict | None:
        if not items:
            return None
        values = [item[key] for item in items]
        return {"min": min(values), "max": max(values)}
    first = underflow[0] if underflow else None
    return {
        "row_count": len(rows), "classification_counts": counts, "counts_by_pair": by_pair,
        "continuous_valid_count": sum(row["continuous_valid_with_coded_8ulp_tolerance"] for row in rows),
        "continuous_exact_pair_bounds_count": sum(row["continuous_exact_pair_bounds"] for row in rows),
        "continuous_negative_count": sum(row["continuous_q"] < 0.0 or row["continuous_n"] < 0.0 for row in rows),
        "continuous_nonfinite_count": sum(not math.isfinite(row["continuous_q"]) or
                                           not math.isfinite(row["continuous_n"]) for row in rows),
        "continuous_outside_real32_range_count": sum(abs(row["continuous_q"]) > FLOAT32_MAX or
                                                       abs(row["continuous_n"]) > FLOAT32_MAX for row in rows),
        "continuous_number_density_unstorable_count": sum(
            row["continuous_validity_reason"] == "number_density_unstorable" for row in rows),
        "continuous_exact_pair_bounds_violation_count": sum(not row["continuous_exact_pair_bounds"] for row in rows),
        "q_underflow_pair_loss_ranges": {
            "continuous_q": ranges(underflow, "continuous_q"),
            "continuous_n": ranges(underflow, "continuous_n"),
            "continuous_q_over_n": ranges(underflow, "continuous_q_over_n"),
            "dry_density": ranges(underflow, "dry_density"),
        },
        "first_q_underflow_pair_loss": first,
        "positive_real32_ratio_exceptions": ratio_failures,
    }


def bind_build() -> dict:
    require_sha(BUILD_RECEIPT, BUILD_RECEIPT_SHA256, "v2 overlay build receipt")
    build = json.loads(BUILD_RECEIPT.read_text())
    if build.get("schema") != "pr87_native_overlay_build_v1" or build.get("status") != "PASS_OVERLAY_BUILD":
        raise ValueError("v2 build receipt schema/status mismatch")
    if build.get("full_clean_build") is not False or build.get("model_run") is not False:
        raise ValueError("v2 build receipt must remain a partial overlay without a model run")
    if build.get("executable_sha256") != OVERLAY_EXE_SHA256:
        raise ValueError("v2 overlay executable identity mismatch")
    if build.get("parent_candidate_executable_sha256") != PARENT_EXE_SHA256:
        raise ValueError("pinned PR85 parent executable identity mismatch")
    if build.get("parent_candidate_archive_sha256") != "102faf532e0d0cb361e8cf0ce2098224c0b7ef09aaa008cf4a421e1584059911":
        raise ValueError("pinned PR85 parent archive identity mismatch")
    compiled = {row["member"]: row for row in build["compiled_overrides"]}
    solve = compiled["solve_em.o"]
    if solve["source_sha256"] != "c48becd786634a589cb5f2ef71b83f43d158637fed1d38f839fe7fc9963f540b":
        raise ValueError("v2 native wrapper source identity mismatch")
    if solve["object_sha256"] != "3f75869813e7ab43fa2dc99104a4e8303f98e0fc3d85e31447933fe9c4569574":
        raise ValueError("v2 native wrapper object identity mismatch")
    module = next((item for item in build["modules"]
                   if item["path"].endswith("/cloud_bal_joint_transport.mod")), None)
    if module is None or module["sha256"] != PARENT_KERNEL_MODULE_SHA256:
        raise ValueError("v2 parent kernel module identity mismatch")
    for rel, expected in (("tools/pr85_native_joint_update.f90", NATIVE_FRAGMENT_SHA256),
                          ("src/common/cloud_bal_joint_transport.f90", BASE_KERNEL_SHA256)):
        base_bytes = subprocess.check_output(["git", "show", f"{BASE_COMMIT}:{rel}"], cwd=ROOT)
        if hashlib.sha256(base_bytes).hexdigest() != expected:
            raise ValueError(f"base commit source identity mismatch: {rel}")
    return {
        "path": str(BUILD_RECEIPT), "sha256": BUILD_RECEIPT_SHA256,
        "identity": build["identity"], "status": build["status"],
        "executable_path": build["executable_path"], "executable_sha256": build["executable_sha256"],
        "parent_executable_sha256": build["parent_candidate_executable_sha256"],
        "parent_archive_sha256": build["parent_candidate_archive_sha256"],
        "source_mapped_native_wrapper": {
            "source_sha256": solve["source_sha256"], "generated_source_sha256": solve["generated_source_sha256"],
            "object_sha256": solve["object_sha256"],
        },
        "base_native_fragment": {"path": "tools/pr85_native_joint_update.f90", "sha256": NATIVE_FRAGMENT_SHA256},
        "base_transport_kernel": {"path": "src/common/cloud_bal_joint_transport.f90", "sha256": BASE_KERNEL_SHA256,
                                  "parent_module_sha256": module["sha256"]},
    }


def bind_run(arm: str, build: dict) -> dict:
    root = RUN_ROOTS[arm]
    ledger = root / "run/pr85_joint_source_failure.raw.gz"
    receipt_path = root / "receipt.json"
    preflight_path = root / "preflight.json"
    require_sha(ledger, LEDGER_SHA256, f"{arm} source-only failure ledger")
    require_sha(receipt_path, RUN_RECEIPT_SHA256[arm], f"{arm} run receipt")
    require_sha(preflight_path, PREFLIGHT_SHA256[arm], f"{arm} preflight receipt")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("arm") != arm or receipt.get("status") != "INCOMPLETE" or receipt.get("returncode") == 0:
        raise ValueError(f"{arm} native run receipt does not bind the recorded incomplete attempt")
    if receipt.get("candidate_build", {}).get("executable_sha256") != build["executable_sha256"]:
        raise ValueError(f"{arm} run does not bind the expected v2 executable")
    if receipt.get("executed_executable_sha256") != OVERLAY_EXE_SHA256:
        raise ValueError(f"{arm} actual executed executable identity mismatch")
    if receipt.get("baseline_frozen_executable_sha256") != PARENT_EXE_SHA256:
        raise ValueError(f"{arm} frozen baseline executable identity mismatch")
    rows, declared, other_markers = read_source_rows(ledger)
    if other_markers:
        raise ValueError(f"{arm} ledger contains non-SOURCE source-failure categories: {other_markers}")
    classified = [classify_row(row) for row in rows]
    return {
        "arm": arm, "run_identity": receipt["run_identity"], "status": receipt["status"],
        "returncode": receipt["returncode"], "final_completed_step": receipt["final_completed_step"],
        "receipt_path": str(receipt_path), "receipt_sha256": RUN_RECEIPT_SHA256[arm],
        "preflight_path": str(preflight_path), "preflight_sha256": PREFLIGHT_SHA256[arm],
        "source_receipt_sha256": receipt["source_receipt_sha256"],
        "candidate_build_executable_sha256": receipt["candidate_build"]["executable_sha256"],
        "executed_executable_sha256": receipt["executed_executable_sha256"],
        "ledger_path": str(ledger), "ledger_sha256": LEDGER_SHA256,
        "declared_source_failure_count": declared, "other_source_failure_markers": other_markers,
        "summary": summarize_rows(classified),
    }


def bind_v3_build() -> dict:
    require_sha(V3_BUILD_RECEIPT, V3_BUILD_RECEIPT_SHA256, "v3 overlay build receipt")
    build = json.loads(V3_BUILD_RECEIPT.read_text())
    if build.get("schema") != "pr87_native_overlay_build_v1" or build.get("status") != "PASS_OVERLAY_BUILD":
        raise ValueError("v3 build receipt schema/status mismatch")
    if build.get("full_clean_build") is not False or build.get("model_run") is not False:
        raise ValueError("v3 build receipt must remain a partial overlay")
    if build.get("executable_sha256") != V3_OVERLAY_EXE_SHA256:
        raise ValueError("v3 overlay executable identity mismatch")
    if build.get("parent_receipt_sha256") != "a2c09db99d3b934a6de677c30901434ce75012fb2fd9020f19c800ee19954353":
        raise ValueError("v3 pinned PR85 parent receipt identity mismatch")
    if build.get("compiler_profile_sha256") != "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4":
        raise ValueError("v3 pinned Intel profile identity mismatch")
    compiled = {row["member"]: row for row in build["compiled_overrides"]}
    expected = {
        "module_microphysics_zero_out.o": ("b70e521c589f8858e4551d10619b3282a4fb3261732b3b8770f369b62792a1a0",
                                           "2e337a7c5c7e4371da9b043d234b46361e92c4f2d12a06b083ad606441d716c3"),
        "module_em.o": ("357521fc1a8f41e6f76e6868d1e88121afea21ac0dd1d66122724408660944df",
                         "1027e6cd1a8a681d31b9f1b106d3314a9b8ffee10c9979e214fcb49a7cc3106d"),
        "solve_em.o": ("c48becd786634a589cb5f2ef71b83f43d158637fed1d38f839fe7fc9963f540b",
                       "11b52427c6a6758dbae4f26783e940f7ec6b737f991c24b5d4bdbad3c42503ed"),
    }
    for member, (source_sha, object_sha) in expected.items():
        row = compiled.get(member)
        if row is None or row.get("source_sha256") != source_sha or row.get("object_sha256") != object_sha:
            raise ValueError(f"v3 compiled override identity mismatch: {member}")
    return {
        "path": str(V3_BUILD_RECEIPT), "sha256": V3_BUILD_RECEIPT_SHA256,
        "identity": build["identity"], "status": build["status"],
        "executable_path": build["executable_path"], "executable_sha256": build["executable_sha256"],
        "parent_receipt_sha256": build["parent_receipt_sha256"],
        "parent_executable_sha256": build["parent_candidate_executable_sha256"],
        "parent_archive_sha256": build["parent_candidate_archive_sha256"],
        "compiler_profile_sha256": build["compiler_profile_sha256"],
        "compiler_sha256": build["compiler_sha256"],
        "compiled_overrides": {
            member: {"source_sha256": compiled[member]["source_sha256"],
                     "generated_source_sha256": compiled[member]["generated_source_sha256"],
                     "object_sha256": compiled[member]["object_sha256"]}
            for member in expected
        },
    }


def bind_v3_run(arm: str, build: dict) -> dict:
    root = V3_RUN_ROOTS[arm]
    receipt_path = root / "receipt.json"
    ledger_path = root / "run/pr85_joint_source_failure.raw.gz"
    storage_path = root / "run/pr87_joint_storage.raw.gz"
    require_sha(receipt_path, V3_RUN_RECEIPT_SHA256[arm], f"v3 {arm} run receipt")
    require_sha(ledger_path, V3_LEDGER_SHA256, f"v3 {arm} source/full ledger")
    require_sha(storage_path, V3_STORAGE_SHA256, f"v3 {arm} joint storage ledger")
    receipt = json.loads(receipt_path.read_text())
    candidate = receipt.get("candidate_build", {})
    if (receipt.get("arm") != arm or receipt.get("status") != "INCOMPLETE" or
            receipt.get("returncode") != 1 or receipt.get("final_completed_step") != 1 or
            receipt.get("maximum_seen_timestep") != 2):
        raise ValueError(f"v3 {arm} receipt does not bind the observed incomplete two-step attempt")
    if (candidate.get("receipt_sha256") != build["sha256"] or
            candidate.get("executable_sha256") != build["executable_sha256"] or
            receipt.get("executed_executable_sha256") != build["executable_sha256"]):
        raise ValueError(f"v3 {arm} receipt does not bind the expected executed candidate")
    if receipt.get("baseline_frozen_executable_sha256") != PARENT_EXE_SHA256:
        raise ValueError(f"v3 {arm} frozen baseline executable identity mismatch")
    if receipt.get("source_receipt_sha256") != V3_SOURCE_RECEIPT_SHA256[arm]:
        raise ValueError(f"v3 {arm} source receipt identity mismatch")
    source_rows, source_count, other_markers = read_source_rows(ledger_path)
    full_rows, full_count = read_full_rows(ledger_path)
    if other_markers:
        raise ValueError(f"v3 {arm} ledger contains unexpected source failure categories: {other_markers}")
    classified = [classify_full_row(row) for row in full_rows]
    counts: dict[str, int] = {}
    for row in classified:
        label = row["classification"]
        counts[label] = counts.get(label, 0) + 1
    if source_count != 445 or full_count != 17:
        raise ValueError(f"v3 {arm} source/full counts changed: {source_count}/{full_count}")
    return {
        "arm": arm, "run_identity": receipt["run_identity"], "status": receipt["status"],
        "returncode": receipt["returncode"], "final_completed_step": receipt["final_completed_step"],
        "maximum_seen_timestep": receipt["maximum_seen_timestep"],
        "completed_post_kdm6_timesteps": receipt["snapshots"]["completed_post_kdm6_timesteps"],
        "fatal_text": "PR87 full joint moment candidate infeasible; see source/full diagnostics",
        "receipt_path": str(receipt_path), "receipt_sha256": V3_RUN_RECEIPT_SHA256[arm],
        "source_receipt_sha256": receipt["source_receipt_sha256"],
        "candidate_build_executable_sha256": candidate["executable_sha256"],
        "executed_executable_sha256": receipt["executed_executable_sha256"],
        "baseline_frozen_executable_sha256": receipt["baseline_frozen_executable_sha256"],
        "probe": receipt.get("pr87_probe"),
        "source_full_ledger_path": str(ledger_path), "source_full_ledger_sha256": V3_LEDGER_SHA256,
        "source_failure_count": source_count, "full_failure_count": full_count,
        "source_failure_rows_are_historical_diagnostic_only": True,
        "full_failure_classification_counts": counts,
        "full_failure_rows": classified,
        "storage_ledger_path": str(storage_path), "storage_ledger_sha256": V3_STORAGE_SHA256,
    }


def create_evidence() -> dict:
    build = bind_build()
    runs = {arm: bind_run(arm, build) for arm in ("OFF", "COUPLED")}
    off, coupled = runs["OFF"]["summary"], runs["COUPLED"]["summary"]
    if off != coupled:
        raise ValueError("OFF and COUPLED source-only classifications differ")
    expected = {"q_underflow_pair_loss": 577, "stored_below_min_ratio": 4, "stored_above_max_ratio": 1}
    if off["classification_counts"] != expected:
        raise ValueError(f"source failure classification counts changed: {off['classification_counts']}")
    if off["continuous_valid_count"] != 582 or off["continuous_exact_pair_bounds_count"] != 582:
        raise ValueError("some recorded continuous candidate fails its nonnegative pair checks")
    v3_build = bind_v3_build()
    v3_runs = {arm: bind_v3_run(arm, v3_build) for arm in ("OFF", "COUPLED")}
    v3_off, v3_coupled = v3_runs["OFF"], v3_runs["COUPLED"]
    for key in ("source_failure_count", "full_failure_count", "full_failure_classification_counts",
                "full_failure_rows", "storage_ledger_sha256", "executed_executable_sha256"):
        if v3_off[key] != v3_coupled[key]:
            raise ValueError(f"v3 OFF and COUPLED {key} differ")
    # These categories use the unrounded REAL64 candidate and a separate RNE
    # binary32 conversion. They must never be merged into the historical v2 rows.
    expected_v3 = {
        "continuous_candidate_outside_coded_8ulp_gate": 14,
        "continuous_valid_real32_rounding_crosses_gate": 3,
    }
    if v3_off["full_failure_classification_counts"] != expected_v3:
        raise ValueError(f"v3 full-candidate classification changed: {v3_off['full_failure_classification_counts']}")
    if any(row["pair"] != "QC/QNC" or row["timestep"] != 2 or row["rk"] != 3 for row in v3_off["full_failure_rows"]):
        raise ValueError("v3 FULL failures no longer isolate step-2 RK3 cloud pairs")
    return {
        "schema": "pr87_source_storage_failure_classification_v2",
        "base_commit": BASE_COMMIT,
        "analysis_tool": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
        "scope": "Read-only classification of source-only diagnostics in the corrected PR87 v2 40-second OFF and COUPLED attempts.",
        "classification_basis": {
            "source_only_formula": "(old_dry_carrier * [Qbase,Nbase] + dt * [Qsource,Nsource]) / new_dry_carrier; values are the recorded REAL64 source_candidate fields, without transport.",
            "coded_pair_bounds": [
                {"pair": PAIR_NAMES[index], "minimum": low, "maximum": high,
                 "minimum_8ulp_tolerance": 8.0 * float32_spacing(low),
                 "maximum_8ulp_tolerance": 8.0 * float32_spacing(high)}
                for index, (low, high) in enumerate(PAIR_BOUNDS)
            ],
            "endpoint_tolerance": "8 * abs(real(spacing(real(endpoint,real32)),real64)) at both bounds, matching joint_moment_is_valid.",
            "number_density_check": "N * dry_density must exceed half the REAL32 minimum subnormal and not exceed REAL32 max, matching joint_moment_is_valid.",
            "real32_conversion": "Continuous Q is round-to-nearest-even binary32 converted with Python struct to identify Q underflow. Positive stored values are parsed from Fortran list-directed output; its decimal precision does not preserve every REAL32 bit pattern, but listed ratio exceptions are far beyond the coded 8-ULP tolerance.",
        },
        "classification_counts_identical_both_arms": off["classification_counts"],
        "counts_by_pair_identical_both_arms": off["counts_by_pair"],
        "continuous_candidate_checks": {
            "rows": off["row_count"], "valid_with_coded_tolerance": off["continuous_valid_count"],
            "inside_exact_pair_bounds_without_tolerance": off["continuous_exact_pair_bounds_count"],
            "negative_count": off["continuous_negative_count"], "nonfinite_count": off["continuous_nonfinite_count"],
            "outside_real32_range_count": off["continuous_outside_real32_range_count"],
            "number_density_unstorable_count": off["continuous_number_density_unstorable_count"],
            "exact_pair_bounds_violation_count": off["continuous_exact_pair_bounds_violation_count"],
            "half_real32_min_subnormal": 0.5 * FLOAT32_MIN_SUBNORMAL,
        },
        "runs": runs,
        "v2_build_identity": build,
        "historical_v2_source_only_attempts": {
            "status": "source-only diagnostic rows; full-candidate offending operands were not recorded",
            "source_failure_count_per_arm": 582,
            "counts_identical_both_arms": off["classification_counts"],
            "build_executable_sha256": OVERLAY_EXE_SHA256,
            "arms": {arm: {"receipt_sha256": runs[arm]["receipt_sha256"],
                            "ledger_sha256": runs[arm]["ledger_sha256"]} for arm in runs},
        },
        "latest_v3_full_candidate_attempts": {
            "status": "incomplete; step 1 completed, step 2 reached RK3 and failed full-candidate feasibility",
            "build": v3_build,
            "source_failure_count_per_arm": v3_off["source_failure_count"],
            "full_failure_count_per_arm": v3_off["full_failure_count"],
            "full_failure_classification_counts": v3_off["full_failure_classification_counts"],
            "runs": v3_runs,
            "classification_basis": (
                "Each FULL record's REAL64 source_candidate Q/N is checked against joint_moment_is_valid64's "
                "existing 8*SPACING(REAL32 endpoint) tolerance; Q and N are also independently rounded to "
                "binary32 and checked. A FULL failure means joint_moment_store returned invalid. The 14/3 "
                "classification is 14 continuous-candidate gate failures and 3 continuous-valid pairs whose "
                "independent binary32 rounding crosses the gate. The two continuous-invalid records whose "
                "rounded pair passes still fail the earlier continuous gate."
            ),
        },
        "interpretation_limits": [
            "This ledger records the source-only candidate diagnostic. It does not identify which operands make the full source-plus-transport candidate infeasible.",
            "The full grouped candidate was rejected by the kernel, but its offending full-candidate operands are not logged by these rows.",
            "Values are local mixing ratios and number moments; no physical-kg or domain-integrated amount is inferred without the required timestep geometry.",
            "The 577 Q-underflow rows support evaluating a common absent-pair representation only with explicit rejected continuous Q and N accounting; this evidence alone does not authorize that policy.",
            "The five positive REAL32 ratio exceptions remain distinct and are not classified as Q-underflow pair loss.",
            "The v3 FULL records are a later, distinct full-candidate failure stage; their 17 cloud rows are not the historical v2 source-only rows.",
            "The coded 8-ULP endpoint tolerance is unchanged. This diagnostic does not relax the separate strict QV predictor gate; that gate remains an independent open validation condition.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/pr87_source_storage_failures_20261016.json")
    args = parser.parse_args()
    evidence = create_evidence()
    output = args.output.resolve()
    if not output.parent.is_dir():
        raise ValueError(f"evidence output parent does not exist: {output.parent}")
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(output), "sha256": sha256(output),
                      "counts": evidence["classification_counts_identical_both_arms"]}, indent=2))


if __name__ == "__main__":
    main()
