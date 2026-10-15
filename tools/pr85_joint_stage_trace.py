#!/usr/bin/env python3
"""Read PR85 whole-tile Q/N/B snapshots and report completed-state failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np


STATE_MAGIC = b"PR85QND2"
LEGACY_STATE_MAGIC = b"PR85QNB1"
PBL_MAGIC = b"PR85PLB1"
HEADER_BYTES = 8 + 32 + 15 * 4
STATE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
PBL_FIELDS = ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
TENDENCY_SCOPES = {
    "POST_PBL_TEND": {
        "scope": "selected Shinhong common-mixing tendencies immediately after return and before FogDES",
        "unit_basis": "native PBL tendency-array units",
    },
    "PRE_GROUPED_PHYSICS_TEND": {
        "scope": "pending aggregate physical source used by grouped Q/N/B update; may include PBL, cumulus, and boundary terms",
        "unit_basis": "native mu-coordinate tendency per second",
    },
    "CUMULUS_PROCESS_TEND": {
        "scope": "selected KSAS QV/QC/QI/QNC/QNI process channels captured after calculate_phy_tend/update_phy_ten; QV/QC/QI mass channels have native mu coupling, while QNC/QNI remain raw process-channel inputs; source-specific attribution",
        "unit_basis": "mixed native process-channel basis: mu-coupled QV/QC/QI rates and raw QNC/QNI process rates; KSAS paired number-source ledger records its own dry rates",
    },
    "PRE_HORIZONTAL_DIFFUSION": {
        "scope": "aggregate QV/QC/QI/QNC/QNI tendencies immediately before horizontal diffusion",
        "unit_basis": "native mu-coordinate physical tendency per second",
    },
    "POST_HORIZONTAL_DIFFUSION": {
        "scope": "aggregate QV/QC/QI/QNC/QNI tendencies immediately after horizontal diffusion",
        "unit_basis": "native mu-coordinate physical tendency per second",
    },
}
RK1_TENDENCY_LABELS = {"CUMULUS_PROCESS_TEND", "PRE_HORIZONTAL_DIFFUSION",
                       "POST_HORIZONTAL_DIFFUSION"}
REQUIRED_PREUPDATE_TENDENCY_LABELS = {"POST_PBL_TEND", "PRE_GROUPED_PHYSICS_TEND"}
PAIRS = {"cloud": ("QC", "NC"), "ice": ("QI", "NI"),
         "rain": ("QR", "NR"), "graupel": ("QG", "BG")}
ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
POLICY_SHA256 = "7f0176742d736c9dbe2be127f43eb00ed35ebda89f0b792a51220efb7d4d7e92"
REQUIRED_STATES = ("PRE_RK", "RK_STAGE_END", "RK_STAGE_END", "RK_STAGE_END",
                   "PRE_KDM6", "POST_KDM6")


class TraceError(ValueError):
    """The trace is incomplete or internally inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_exact(view: memoryview, offset: int, count: int, label: str) -> tuple[memoryview, int]:
    end = offset + count
    if end > len(view):
        raise TraceError(f"truncated {label} at byte {offset}")
    return view[offset:end], end


def read_records(path: Path) -> dict:
    before = sha256(path)
    raw = path.read_bytes()
    view = memoryview(raw)
    offset = 0
    records = []
    state_geometry = None
    while offset < len(view):
        magic_view, offset = _read_exact(view, offset, 8, "record magic")
        magic = magic_view.tobytes()
        if magic not in (STATE_MAGIC, LEGACY_STATE_MAGIC, PBL_MAGIC):
            raise TraceError(f"wrong record magic at byte {offset - 8}: {magic!r}")
        label_view, offset = _read_exact(view, offset, 32, "stage label")
        try:
            label = label_view.tobytes().decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise TraceError("stage label is not ASCII") from exc
        header_view, offset = _read_exact(view, offset, 15 * 4, "record header")
        (kind, timestep, rkstep, ims, ime, jms, jme, kms, kme,
         its, ite, jts, jte, kts, kte) = struct.unpack(">15i", header_view)
        is_state = magic in (STATE_MAGIC, LEGACY_STATE_MAGIC)
        expected_kind = 1 if is_state else 2
        if kind != expected_kind or timestep <= 0 or rkstep < 0:
            raise TraceError(f"invalid record metadata for {label}: kind={kind}, timestep={timestep}, rk={rkstep}")
        bounds = dict(zip(("ims", "ime", "jms", "jme", "kms", "kme",
                           "its", "ite", "jts", "jte", "kts", "kte"),
                          (ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte), strict=True))
        for start, end, memory_start, memory_end, axis in (
                ("its", "ite", "ims", "ime", "i"), ("jts", "jte", "jms", "jme", "j"),
                ("kts", "kte", "kms", "kme", "k")):
            if bounds[memory_start] > bounds[memory_end] or bounds[start] > bounds[end]:
                raise TraceError(f"empty or inverted {axis} bounds in {label}")
            if bounds[start] < bounds[memory_start] or bounds[end] > bounds[memory_end]:
                raise TraceError(f"active {axis} bounds fall outside memory in {label}")
        this_geometry = tuple(bounds[key] for key in ("ims", "ime", "jms", "jme", "kms", "kme",
                                                       "its", "ite", "jts", "jte", "kts", "kte"))
        if expected_kind == 1:
            if state_geometry is not None and this_geometry != state_geometry:
                raise TraceError("completed state geometry changed within one trace")
            state_geometry = this_geometry
        if (expected_kind == 1 and label not in {"PRE_RK", "RK_STAGE_END", "PRE_KDM6", "POST_KDM6"}) or (
                expected_kind == 2 and label not in TENDENCY_SCOPES):
            raise TraceError(f"unexpected stage label or kind: {label}, kind={kind}")
        shape = (jte - jts + 1, kte - kts + 1, ite - its + 1)
        fields = {}
        names = STATE_FIELDS if expected_kind == 1 else PBL_FIELDS
        cells = int(np.prod(shape))
        for name in names:
            field_view, offset = _read_exact(view, offset, cells * 4, f"{label} {name}")
            fields[name] = np.frombuffer(field_view, dtype=np.dtype(">f4")).reshape(shape)
        density_contract_status = ("AUTHORITATIVE_DRY_FROM_AL_ALB" if magic == STATE_MAGIC else
                                   "UNVERIFIED_LEGACY_DECLARATION" if magic == LEGACY_STATE_MAGIC else None)
        records.append({"stage": label, "kind": kind, "timestep": timestep,
                        "rkstep": rkstep, "bounds": bounds, "shape_jki": list(shape),
                        "fields": fields, "density_contract_status": density_contract_status})
    if sha256(path) != before:
        raise TraceError("trace changed during offline read")
    return {"path": str(path), "sha256": before, "bytes": len(raw), "records": records}


def _stats(values: np.ndarray) -> dict:
    finite = np.isfinite(values)
    selected = values[finite]
    return {"size": int(values.size), "finite": int(finite.sum()),
            "nonfinite": int((~finite).sum()), "negative": int((values < 0).sum()),
            "zero": int((values == 0).sum()), "positive": int((values > 0).sum()),
            "min": float(selected.min()) if selected.size else None,
            "max": float(selected.max()) if selected.size else None}


def _policy_bounds(policy: dict, species: str) -> tuple[list[float], str]:
    if species == "graupel":
        declaration = policy["species"]["QGRAUP"]
        return ([declaration["bulk_density_min_kg_m-3"],
                 declaration["bulk_density_max_kg_m-3"]], "QGRAUP/QIB bulk density kg m-3")
    mass_name = {"cloud": "QCLOUD", "ice": "QICE", "rain": "QRAIN"}[species]
    declaration = policy["species"][mass_name]
    if (mass_name == "QICE" and policy.get("schema") == "pr84_same13_native_moment_policy_v2"):
        pidn = float(np.float32(declaration["source_pidni_binary32_value"]))
        exponent = float(declaration["shape_exponent_d"])
        bounds = [pidn / float(declaration["lambda_max_m-1"]) ** exponent,
                  pidn / float(declaration["lambda_min_m-1"]) ** exponent]
        return bounds, "source REAL32 PIDNI and lambda interval, QI/NI kg per particle"
    return declaration["particle_mean_mass_bounds_kg"], "source policy particle mean-mass bounds kg per particle"


def _eight_ulp(bound: float) -> float:
    return 8.0 * abs(float(np.spacing(np.float32(bound))))


def _pair_stats(fields: dict[str, np.ndarray], policy: dict) -> dict:
    result = {}
    for species, (mass_name, moment_name) in PAIRS.items():
        mass, moment = fields[mass_name], fields[moment_name]
        valid = np.isfinite(mass) & np.isfinite(moment) & (mass > 0) & (moment > 0)
        ratio = mass[valid].astype(np.float64) / moment[valid].astype(np.float64)
        bounds, basis = _policy_bounds(policy, species)
        lower_tolerance, upper_tolerance = _eight_ulp(bounds[0]), _eight_ulp(bounds[1])
        below = np.maximum(bounds[0] - ratio, 0.0)
        above = np.maximum(ratio - bounds[1], 0.0)
        outside = (below > 0.0) | (above > 0.0)
        beyond_tolerance = (below > lower_tolerance) | (above > upper_tolerance)
        result[species] = {
            "mass": mass_name, "moment": moment_name,
            "positive_mass_zero_moment": int(((mass > 0) & (moment == 0)).sum()),
            "positive_moment_zero_mass": int(((moment > 0) & (mass == 0)).sum()),
            "negative_mass": int((mass < 0).sum()),
            "negative_moment": int((moment < 0).sum()),
            "nonfinite_mass_or_moment": int((~np.isfinite(mass) | ~np.isfinite(moment)).sum()),
            "feasible_cone": {
                "parameter_basis": basis,
                "bounds": bounds,
                "ratio_name": "mass/moment",
                "valid_positive_pair_cells": int(valid.sum()),
                "exact_outside_bound_cells": int(outside.sum()),
                "outside_beyond_8_float32_ulp_cells": int(beyond_tolerance.sum()),
                "eight_ulp_tolerance_at_lower_bound": lower_tolerance,
                "eight_ulp_tolerance_at_upper_bound": upper_tolerance,
                "maximum_exact_lower_residual": float(below.max()) if below.size else 0.0,
                "maximum_exact_upper_residual": float(above.max()) if above.size else 0.0,
            },
        }
    return result


def _dry_density(fields: dict[str, np.ndarray], density_contract_status: str) -> np.ndarray:
    den = np.asarray(fields["DEN"], dtype=np.float32)
    if density_contract_status == "AUTHORITATIVE_DRY_FROM_AL_ALB":
        return den
    if density_contract_status != "UNVERIFIED_LEGACY_DECLARATION":
        raise TraceError(f"unknown density contract: {density_contract_status}")
    vapor = np.asarray(fields["Q"], dtype=np.float32)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
        return np.divide(den, np.add(np.float32(1), vapor, dtype=np.float32), dtype=np.float32)


def _conversion_stats(fields: dict[str, np.ndarray], density_contract_status: str) -> dict:
    dry_density = _dry_density(fields, density_contract_status)
    f32max = float(np.finfo(np.float32).max)
    smallest = np.nextafter(np.float32(0), np.float32(1), dtype=np.float32)
    report = {}
    for name in ("NN", "NC", "NI", "NR", "BG"):
        number = np.asarray(fields[name], dtype=np.float32)
        valid = np.isfinite(number) & np.isfinite(dry_density) & (number >= 0) & (dry_density > 0)
        exact = number.astype(np.float64) * dry_density.astype(np.float64)
        overflow = valid & (dry_density > 1) & (number.astype(np.float64) > f32max / dry_density.astype(np.float64))
        result = np.zeros(number.shape, dtype=np.float32)
        safe = valid & ~overflow
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            result[safe] = exact[safe].astype(np.float32)
        report[name] = {
            "quantity": "specific volume moment" if name == "BG" else "specific number moment",
            "nonfinite_input": int((~np.isfinite(number)).sum()),
            "negative_input": int((np.isfinite(number) & (number < 0)).sum()),
            "nonfinite_or_nonpositive_dry_density": int((~np.isfinite(dry_density) | (dry_density <= 0)).sum()),
            "overflow_guard": int(overflow.sum()),
            "nonfinite_result": int((safe & ~np.isfinite(result)).sum()),
            "positive_to_zero": int((safe & (number > 0) & (result == 0)).sum()),
            "product_at_or_below_half_minimum_subnormal": int((valid & (number > 0) &
                (exact <= float(smallest) / 2)).sum()),
        }
    return report


def _entry_caps(fields: dict[str, np.ndarray], policy: dict,
                density_contract_status: str) -> dict:
    density = _dry_density(fields, density_contract_status)
    result = {}
    for mass_name, moment_name in (("QCLOUD", "NC"), ("QRAIN", "NR")):
        mass_field = "QC" if mass_name == "QCLOUD" else "QR"
        declaration = policy["species"][mass_name]
        number = np.asarray(fields[moment_name], dtype=np.float32)
        with np.errstate(over="ignore", invalid="ignore", under="ignore"):
            internal = np.multiply(number, density, dtype=np.float32)
        finite_internal = internal[np.isfinite(internal)]
        cap = float(declaration["internal_number_cap_number_m-3"])
        result[moment_name] = {
            "source_cap_number_m-3": cap,
            "cells_above_source_cap": int((internal > cap).sum()),
            "max_finite_internal_number_m-3": float(finite_internal.max()) if finite_internal.size else None,
            "nonfinite_internal_number_cells": int((~np.isfinite(internal)).sum()),
            "role": "source entry-consumption diagnostic; not a persistent post-operator invariant",
            "paired_mass_positive_cells": int((fields[mass_field] > 0).sum()),
        }
    result["NI"] = {
        "role": "PR84 source entry guard is a PSD-compatible pre-consumption cap; not a persistent post-operator invariant",
        "persistent_fixed_cap_applied": False,
    }
    return result


def _tendency_consumer_overlap(tendency: dict, state: dict) -> dict:
    tb, sb = tendency["bounds"], state["bounds"]
    intersection = {}
    for axis in ("i", "j", "k"):
        low = max(tb[f"{axis}ts"], sb[f"{axis}ts"])
        high = min(tb[f"{axis}te"], sb[f"{axis}te"])
        if low > high:
            raise TraceError(f"tendency record does not overlap consumer state on {axis}")
        intersection[axis] = (low, high)
    tsl = tuple(slice(intersection[axis][0] - tb[f"{axis}ts"],
                      intersection[axis][1] - tb[f"{axis}ts"] + 1) for axis in ("j", "k", "i"))
    ssl = tuple(slice(intersection[axis][0] - sb[f"{axis}ts"],
                      intersection[axis][1] - sb[f"{axis}ts"] + 1) for axis in ("j", "k", "i"))
    covers_state = all(tb[f"{axis}ts"] <= sb[f"{axis}ts"] and tb[f"{axis}te"] >= sb[f"{axis}te"]
                       for axis in ("i", "j", "k"))
    return {"intersection_bounds": {axis: list(bounds) for axis, bounds in intersection.items()},
            "intersection_cell_count": int(np.prod([high - low + 1 for low, high in intersection.values()])),
            "consumer_cell_count": int(np.prod(state["fields"]["Q"].shape)),
            "tendency_covers_full_consumer_support": covers_state,
            "tendency_stats_on_intersection": {
                name: _stats(values[tsl]) for name, values in tendency["fields"].items()},
            "consumer_slices": [[item.start, item.stop] for item in ssl]}


def _load_policy() -> dict:
    if sha256(POLICY_PATH) != POLICY_SHA256:
        raise TraceError("pinned PR84 source-bound moment policy changed")
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def summarize(path: Path, *, build_receipt: Path | None = None,
              expected_executable: Path | None = None,
              expected_parent_executable_sha256: str | None = None) -> dict:
    source = read_records(path)
    records = source["records"]
    policy = _load_policy()
    states = [record for record in records if record["kind"] == 1]
    tendencies = [record for record in records if record["kind"] == 2]
    state_sequence = tuple(record["stage"] for record in states)
    completed_rk = [record["rkstep"] for record in states if record["stage"] == "RK_STAGE_END"]
    sequence_ok = state_sequence == REQUIRED_STATES
    rk_complete = completed_rk[:3] == [1, 2, 3]
    kdm_pre = any(record["stage"] == "PRE_KDM6" for record in states)
    kdm_post = any(record["stage"] == "POST_KDM6" for record in states)
    tendency_positions = [index for index, record in enumerate(records) if record["kind"] == 2]
    pre_rk_positions = [index for index, record in enumerate(records)
                        if record["kind"] == 1 and record["stage"] == "PRE_RK"]
    rk1_positions = [index for index, record in enumerate(records)
                     if record["kind"] == 1 and record["stage"] == "RK_STAGE_END" and record["rkstep"] == 1]
    tendency_overlaps = ([_tendency_consumer_overlap(record, states[0])
                          for record in tendencies] if states else [None] * len(tendencies))
    full_tendency_before_rk1 = (len(rk1_positions) == 1 and bool(tendencies) and
        any(record["stage"] in REQUIRED_PREUPDATE_TENDENCY_LABELS and
            overlap is not None and overlap["tendency_covers_full_consumer_support"] and
            tendency_positions[index] < rk1_positions[0]
            for index, (record, overlap) in enumerate(zip(tendencies, tendency_overlaps, strict=True))))
    state_before_rk1 = (len(pre_rk_positions) == 1 and len(rk1_positions) == 1 and
                        pre_rk_positions[0] < rk1_positions[0])
    timesteps = {record["timestep"] for record in records}
    timestep_consistent = len(timesteps) == 1
    metadata_ok = timestep_consistent and all(
        (record["stage"] != "PRE_RK" or record["rkstep"] == 0) and
        (record["stage"] != "RK_STAGE_END" or record["rkstep"] in (1, 2, 3)) and
        (record["stage"] not in ("PRE_KDM6", "POST_KDM6") or record["rkstep"] == 0)
        for record in states)
    metadata_ok = metadata_ok and all(
        record["rkstep"] == (1 if record["stage"] in RK1_TENDENCY_LABELS else 0)
        for record in tendencies)
    stage_reports = []
    first_failure = None
    for index, record in enumerate(states):
        fields = record["fields"]
        stats = {name: _stats(values) for name, values in fields.items()}
        pairs = _pair_stats(fields, policy)
        conversions = _conversion_stats(fields, record["density_contract_status"])
        caps = _entry_caps(fields, policy, record["density_contract_status"])
        negative_or_nonfinite = {
            name: {"negative": summary["negative"], "nonfinite": summary["nonfinite"]}
            for name, summary in stats.items()
            if summary["negative"] or summary["nonfinite"]
        }
        pair_violations = {
            species: values for species, values in pairs.items()
            if values["positive_mass_zero_moment"] or values["positive_moment_zero_mass"]
                or values["negative_mass"] or values["negative_moment"]
                or values["nonfinite_mass_or_moment"]
                or values["feasible_cone"]["outside_beyond_8_float32_ulp_cells"]
        }
        conversion_violations = {
            name: values for name, values in conversions.items()
            if any(value for key, value in values.items() if key != "quantity")
        }
        violates = bool(negative_or_nonfinite or pair_violations or conversion_violations)
        if violates and first_failure is None:
            first_failure = {"stage": record["stage"], "rkstep": record["rkstep"],
                             "state_index": index, "negative_or_nonfinite": negative_or_nonfinite,
                             "pair_violations": pair_violations,
                             "conversion_violations": conversion_violations}
        stage_reports.append({"stage": record["stage"], "rkstep": record["rkstep"],
                              "timestep": record["timestep"], "stats": stats,
                              "density_contract_status": record["density_contract_status"],
                              "pairs": pairs, "source_entry_cap_diagnostics": caps,
                              "number_conversion": conversions})
    density_contract_verified = bool(states) and all(
        record["density_contract_status"] == "AUTHORITATIVE_DRY_FROM_AL_ALB" for record in states)
    coverage_pass = (sequence_ok and rk_complete and state_before_rk1 and
                     full_tendency_before_rk1 and kdm_pre and kdm_post and
                     timestep_consistent and metadata_ok)
    admission_pass = coverage_pass and density_contract_verified and first_failure is None
    completed_state_admission = {
        "status": "PASS" if admission_pass else
                  "FAIL" if coverage_pass and density_contract_verified else "INCOMPLETE",
        "complete_required_state_sequence": sequence_ok,
        "full_consumer_support_checked_at_every_completed_state": sequence_ok,
        "density_contract_verified": density_contract_verified,
        "all_checked_states_pass_nonnegative_finite_pair_psd_and_conversion": first_failure is None,
        "earliest_observed_completed_state_violation": first_failure,
    }
    build_binding = {"status": "NOT_PROVIDED"}
    if build_receipt is not None:
        if expected_executable is None or not expected_parent_executable_sha256:
            raise TraceError("build receipt requires expected executable path and parent executable hash")
        from pr85_consumer_build_contract import validate_consumer_build
        try:
            build_binding = validate_consumer_build(
                build_receipt, expected_executable, expected_parent_executable_sha256)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise TraceError(f"consumer build receipt validation failed: {exc}") from exc
    elif expected_executable is not None or expected_parent_executable_sha256 is not None:
        raise TraceError("expected executable fields require a build receipt")
    return {
        "schema": "pr85_joint_moment_stage_summary_v3",
        "scope": "full active-tile completed state snapshots plus separately typed physical tendency snapshots",
        "input_path": source["path"], "input_sha256_before": source["sha256"],
        "input_sha256_after": sha256(path), "bytes": source["bytes"],
        "consumer_build_binding": build_binding,
        "state_stage_sequence": list(state_sequence),
        "all_record_sequence": [{"stage": record["stage"], "kind": record["kind"],
                                 "timestep": record["timestep"], "rkstep": record["rkstep"]}
                                for record in records],
        "kind2_tendency_records": [
            {"stage": record["stage"], "rkstep": record["rkstep"],
             **TENDENCY_SCOPES[record["stage"]],
             "stats": {name: _stats(values) for name, values in record["fields"].items()},
             "active_bounds": record["bounds"],
             "consumer_support_comparison": overlap}
            for record, overlap in zip(tendencies, tendency_overlaps, strict=True)],
        "completed_rk_sequence": completed_rk,
        "strict_stage_coverage": {
            "status": "PASS" if coverage_pass else "INCOMPLETE",
            "required_state_prefix": list(REQUIRED_STATES),
            "rk1_rk2_rk3_complete": rk_complete,
            "pre_kdm6_present": kdm_pre, "post_kdm6_present": kdm_post,
            "pre_rk_before_rk1": state_before_rk1,
            "full_kind2_tendency_before_rk1": full_tendency_before_rk1,
            "single_timestep": timestep_consistent,
            "stage_metadata_consistent": metadata_ok,
            "firstNC_skip_satisfies_gate": False,
        },
        "strict_density_contract": {
            "status": "PASS" if density_contract_verified else
                      "UNVERIFIED_LEGACY_DECLARATION" if states else "INCOMPLETE",
            "required_state_magic": STATE_MAGIC.decode("ascii"),
            "legacy_state_magic": LEGACY_STATE_MAGIC.decode("ascii"),
            "state_record_statuses": [record["density_contract_status"] for record in states],
            "formula_for_v2": "DEN is real32(1)/(AL+ALB), the authoritative dry-air density; use DEN directly.",
            "legacy_handling": "PR85QNB1 retains its historical DEN/(1+QV) arithmetic for reproduction only; the density contract remains unverified and cannot pass strict admission.",
        },
        "strict_completed_state_admission": completed_state_admission,
        "earliest_observed_completed_state_violation": first_failure,
        "completed_state_summaries": stage_reports,
        "field_semantics": {
            "mass_moment_pairs": {"QC": "NC", "QI": "NI", "QR": "NR", "QG": "BG"},
            "QS": "snow mass only; no number moment is inferred",
            "NN": "ambient CCN carrier; no condensate mass counterpart",
            "BG": "graupel specific-volume moment, not relabeled as particle number",
            "Q": "water vapor; runtime qmin is not applied as a positivity floor",
            "cone_policy_path": str(POLICY_PATH), "cone_policy_sha256": POLICY_SHA256,
            "cone_tolerance": "exact residual is reported; acceptance allows at most eight REAL32 ULP of each source bound",
        },
        "stage_semantics": {
            "PRE_RK": "Q/N/B state at the joint updater input boundary, after independent-channel tendencies are ready and before the grouped Q/N/B update",
            "POST_PBL_TEND": TENDENCY_SCOPES["POST_PBL_TEND"],
            "PRE_GROUPED_PHYSICS_TEND": TENDENCY_SCOPES["PRE_GROUPED_PHYSICS_TEND"],
            "CUMULUS_PROCESS_TEND": TENDENCY_SCOPES["CUMULUS_PROCESS_TEND"],
            "PRE_HORIZONTAL_DIFFUSION": TENDENCY_SCOPES["PRE_HORIZONTAL_DIFFUSION"],
            "POST_HORIZONTAL_DIFFUSION": TENDENCY_SCOPES["POST_HORIZONTAL_DIFFUSION"],
            "RK_STAGE_END": "state after the completed grouped update and remaining native RK-stage work",
            "PRE_KDM6": "state immediately before the native microphysics call containing KDM6",
            "POST_KDM6": "state snapshot only after that native microphysics call returns normally",
        },
    }


def write_new_json(path: Path, value: dict) -> None:
    output = Path(os.path.abspath(path))
    for component in reversed((output, *output.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if component.is_symlink():
            raise ValueError(f"output path contains a symlink: {component}")
        if component == output and not component.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
        if component != output and not component.is_dir():
            raise ValueError(f"output parent is not a directory: {component}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--expected-executable", type=Path)
    parser.add_argument("--expected-parent-executable-sha256")
    args = parser.parse_args()
    try:
        report = summarize(args.trace, build_receipt=args.build_receipt,
                           expected_executable=args.expected_executable,
                           expected_parent_executable_sha256=args.expected_parent_executable_sha256)
        write_new_json(args.output, report)
    except (OSError, TraceError, ValueError) as exc:
        parser.error(str(exc))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
