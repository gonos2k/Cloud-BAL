#!/usr/bin/env python3
"""Audit Q/N/B invariants independently at each completed native stage."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pr85_joint_stage_trace as pr85


STATE_SEQUENCE = ("PRE_RK", "RK_STAGE_END", "RK_STAGE_END", "RK_STAGE_END",
                  "PRE_KDM6", "POST_KDM6")
STRICT_SOURCE_COEFFICIENTS = {
    "cloud": {"mass": "QC", "number": "NC", "pidn_r32": 523.59881591796875,
              "power_r32": 3.0, "lambda_min_r32": 12000.0, "lambda_max_r32": 500000.0},
    "rain": {"mass": "QR", "number": "NR", "pidn_r32": 12566.37109375,
             "power_r32": 3.0, "lambda_min_r32": 961.0, "lambda_max_r32": 35000.0},
    "ice_diagnostic": {"mass": "QI", "number": "NI", "pidn_r32": 1570.79638671875,
                       "power_r32": 3.0, "lambda_min_r32": 9080.0, "lambda_max_r32": 1820000.0},
}
STRICT_ENDPOINT_STAGES = {("RK_STAGE_END", 3), ("PRE_KDM6", 0), ("POST_KDM6", 0)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_records(path: Path) -> tuple[dict, dict]:
    source_sha = sha256(path)
    if path.suffix == ".gz":
        with tempfile.TemporaryDirectory(prefix="pr87_stage_audit_") as temp:
            expanded = Path(temp) / path.stem
            with gzip.open(path, "rb") as compressed, expanded.open("wb") as raw:
                while block := compressed.read(8 * 1024 * 1024):
                    raw.write(block)
            decoded = pr85.read_records(expanded)
    else:
        decoded = pr85.read_records(path)
    if sha256(path) != source_sha:
        raise pr85.TraceError("trace changed during offline read")
    return decoded, {"path": str(path), "sha256": source_sha,
                     "bytes": path.stat().st_size,
                     "decoded_sha256": decoded["sha256"]}


def _stage_violations(record: dict, policy: dict) -> dict:
    fields = record["fields"]
    stats = {name: pr85._stats(values) for name, values in fields.items()}
    pairs = pr85._pair_stats(fields, policy)
    conversions = pr85._conversion_stats(fields, record["density_contract_status"])
    bad_fields = {name: {"negative": summary["negative"],
                         "nonfinite": summary["nonfinite"]}
                  for name, summary in stats.items()
                  if summary["negative"] or summary["nonfinite"]}
    bad_pairs = {
        species: value for species, value in pairs.items()
        if value["positive_mass_zero_moment"] or value["positive_moment_zero_mass"]
        or value["negative_mass"] or value["negative_moment"]
        or value["nonfinite_mass_or_moment"]
        or value["feasible_cone"]["outside_beyond_8_float32_ulp_cells"]
    }
    bad_conversions = {
        name: value for name, value in conversions.items()
        if any(amount for key, amount in value.items() if key != "quantity")
    }
    return {"stats": stats, "pairs": pairs,
            "source_entry_cap_diagnostics": pr85._entry_caps(
                fields, policy, record["density_contract_status"]),
            "number_conversion": conversions,
            "violations": {"fields": bad_fields, "pairs": bad_pairs,
                           "number_conversion": bad_conversions}}


def _strict_source_checks(fields: dict[str, object]) -> dict:
    """Check source-defined cloud/rain and diagnostic ice bounds without ULP slack."""
    import numpy as np

    result = {}
    for species, source in STRICT_SOURCE_COEFFICIENTS.items():
        mass = np.asarray(fields[source["mass"]], dtype=np.float32)
        number = np.asarray(fields[source["number"]], dtype=np.float32)
        rho = np.asarray(fields["DEN"], dtype=np.float32)
        pidn = np.float64(np.float32(source["pidn_r32"]))
        power = np.float64(np.float32(source["power_r32"]))
        lambda_min = np.float64(np.float32(source["lambda_min_r32"]))
        lambda_max = np.float64(np.float32(source["lambda_max_r32"]))
        lower_mass = pidn / lambda_max ** power
        upper_mass = pidn / lambda_min ** power

        finite = np.isfinite(mass) & np.isfinite(number) & np.isfinite(rho)
        negative = finite & ((mass < 0) | (number < 0))
        absent = finite & (mass == 0) & (number == 0)
        positive_mass_zero_number = finite & (mass > 0) & (number == 0)
        positive_number_zero_mass = finite & (number > 0) & (mass == 0)
        positive_pair = finite & (mass > 0) & (number > 0) & (rho > 0)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
            specific_ratio = mass.astype(np.float64) / number.astype(np.float64)
            volume64 = rho.astype(np.float64) * number.astype(np.float64)
            volume32 = np.multiply(rho, number, dtype=np.float32).astype(np.float64)
            volume_lower_ratio = rho.astype(np.float64) / upper_mass
            volume_upper_ratio = rho.astype(np.float64) / lower_mass
            volume64_ratio = volume64 / mass.astype(np.float64)
            volume32_ratio = volume32 / mass.astype(np.float64)
        specific_outside = positive_pair & ((specific_ratio < lower_mass) |
                                             (specific_ratio > upper_mass))
        volume64_outside = positive_pair & ((volume64_ratio < volume_lower_ratio) |
                                              (volume64_ratio > volume_upper_ratio))
        volume32_outside = positive_pair & ((volume32_ratio < volume_lower_ratio) |
                                              (volume32_ratio > volume_upper_ratio))
        bad_rho = finite & (rho <= 0) & ((mass != 0) | (number != 0))
        result[species] = {
            "mass_field": source["mass"], "number_field": source["number"],
            "coefficient_basis": "REAL32 source coefficients promoted to REAL64; exact bounds, no ULP allowance",
            "source_coefficients_real32": {key: source[key] for key in
                ("pidn_r32", "power_r32", "lambda_min_r32", "lambda_max_r32")},
            "specific_mass_per_number_bounds": [float(lower_mass), float(upper_mass)],
            "counts": {
                "absent_pair": int(absent.sum()),
                "positive_mass_zero_number_orphan": int(positive_mass_zero_number.sum()),
                "positive_number_zero_mass_orphan": int(positive_number_zero_mass.sum()),
                "negative_pair": int(negative.sum()),
                "nonfinite_pair_or_density": int((~finite).sum()),
                "nonpositive_density_with_present_pair": int(bad_rho.sum()),
                "positive_pair_cells": int(positive_pair.sum()),
                "specific_ratio_outside_exact_bounds": int(specific_outside.sum()),
                "real64_volume_ratio_outside_exact_bounds": int(volume64_outside.sum()),
                "real32_density_times_number_volume_ratio_outside_exact_bounds": int(volume32_outside.sum()),
            },
        }

    qg = np.asarray(fields["QG"], dtype=np.float32)
    bg = np.asarray(fields["BG"], dtype=np.float32)
    finite = np.isfinite(qg) & np.isfinite(bg)
    absent = finite & (qg == 0) & (bg == 0)
    positive_pair = finite & (qg > 0) & (bg > 0)
    orphan = finite & (((qg > 0) & (bg == 0)) | ((bg > 0) & (qg == 0)))
    negative = finite & ((qg < 0) | (bg < 0))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        ratio = qg.astype(np.float64) / bg.astype(np.float64)
    outside = positive_pair & ((ratio < 100.0) | (ratio > 900.0))
    result["graupel_exact_stored"] = {
        "mass_field": "QG", "moment_field": "BG",
        "ratio": "QG/BG, exact selected bounds [100,900], no ULP allowance",
        "counts": {
            "absent_pair": int(absent.sum()),
            "positive_mass_zero_moment_orphan": int((finite & (qg > 0) & (bg == 0)).sum()),
            "positive_moment_zero_mass_orphan": int((finite & (bg > 0) & (qg == 0)).sum()),
            "negative_pair": int(negative.sum()),
            "nonfinite_pair": int((~finite).sum()),
            "positive_pair_cells": int(positive_pair.sum()),
            "ratio_outside_exact_bounds": int(outside.sum()),
        },
    }
    return result


def _strict_source_violations(checks: dict) -> dict:
    violations = {}
    for species in ("cloud", "rain"):
        counts = checks[species]["counts"]
        bad = {key: counts[key] for key in (
            "positive_mass_zero_number_orphan", "positive_number_zero_mass_orphan",
            "negative_pair", "nonfinite_pair_or_density", "nonpositive_density_with_present_pair",
            "specific_ratio_outside_exact_bounds", "real64_volume_ratio_outside_exact_bounds",
            "real32_density_times_number_volume_ratio_outside_exact_bounds") if counts[key]}
        if bad:
            violations[species] = bad
    counts = checks["graupel_exact_stored"]["counts"]
    bad = {key: counts[key] for key in (
        "positive_mass_zero_moment_orphan", "positive_moment_zero_mass_orphan",
        "negative_pair", "nonfinite_pair", "ratio_outside_exact_bounds") if counts[key]}
    if bad:
        violations["graupel_exact_stored"] = bad
    return violations


def _bind_overlay_build(receipt_path: Path, executable: Path,
                        expected_parent_executable_sha256: str) -> dict:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "pr87_native_overlay_build_v1" or \
            receipt.get("status") != "PASS_OVERLAY_BUILD" or \
            receipt.get("full_clean_build") is not False:
        raise pr85.TraceError("unsupported or incomplete PR87 overlay build receipt")
    candidate = Path(receipt["executable_path"])
    if candidate.resolve() != executable.resolve() or \
            sha256(candidate) != receipt.get("executable_sha256"):
        raise pr85.TraceError("candidate executable does not match build receipt")
    parent = Path(receipt["parent_candidate_executable_path"])
    if sha256(parent) != receipt.get("parent_candidate_executable_sha256") or \
            receipt.get("parent_candidate_executable_sha256") != expected_parent_executable_sha256:
        raise pr85.TraceError("parent executable identity does not match expected hash")
    parent_receipt = Path(receipt["parent_receipt_path"])
    if sha256(parent_receipt) != receipt.get("parent_receipt_sha256"):
        raise pr85.TraceError("parent native build receipt hash mismatch")
    parent_build = json.loads(parent_receipt.read_text(encoding="utf-8"))
    if (parent_build.get("candidate_executable_path") != str(parent) or
            parent_build.get("candidate_executable_sha256") != receipt.get("parent_candidate_executable_sha256")):
        raise pr85.TraceError("parent executable does not match the bound parent build receipt")
    parent_archive = Path(receipt["parent_candidate_archive_path"])
    if sha256(parent_archive) != receipt.get("parent_candidate_archive_sha256") or \
            parent_build.get("candidate_archive_path") != str(parent_archive) or \
            parent_build.get("candidate_archive_sha256") != receipt.get("parent_candidate_archive_sha256"):
        raise pr85.TraceError("parent archive does not match the bound parent build receipt")
    archive = Path(receipt["parent_archive_copy"])
    if sha256(archive) != receipt.get("archive_sha256"):
        raise pr85.TraceError("candidate archive does not match build receipt")
    return {
        "status": "PASS_BOUND_PARTIAL_OVERLAY",
        "identity": receipt.get("identity"),
        "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
        "schema": receipt["schema"], "full_clean_build": False,
        "candidate_executable_path": str(candidate),
        "candidate_executable_sha256": receipt["executable_sha256"],
        "parent_executable_path": str(parent),
        "parent_executable_sha256": receipt["parent_candidate_executable_sha256"],
        "parent_receipt_path": str(parent_receipt),
        "parent_receipt_sha256": receipt["parent_receipt_sha256"],
        "candidate_archive_path": str(archive),
        "candidate_archive_sha256": receipt["archive_sha256"],
        "compiler_path": receipt.get("compiler_path"),
        "compiler_sha256": receipt.get("compiler_sha256"),
        "compiler_version": receipt.get("compiler_version"),
        "compiler_profile_path": receipt.get("compiler_profile_path"),
        "compiler_profile_sha256": receipt.get("compiler_profile_sha256"),
    }


def audit(path: Path, *, build_receipt: Path | None = None,
          expected_executable: Path | None = None,
          expected_parent_executable_sha256: str | None = None,
          strict_source_coefficients: bool = False) -> dict:
    source, input_identity = _read_records(path)
    states = [record for record in source["records"] if record["kind"] == 1]
    by_timestep: dict[int, list[dict]] = defaultdict(list)
    for record in states:
        by_timestep[record["timestep"]].append(record)
    policy = pr85._load_policy()
    timestep_reports = []
    for timestep, records in sorted(by_timestep.items()):
        sequence = [record["stage"] for record in records]
        sequence_ok = tuple(sequence) == STATE_SEQUENCE
        expected_rksteps = (0, 1, 2, 3, 0, 0)
        rkstep_sequence_ok = (len(records) == len(expected_rksteps) and
                              tuple(record["rkstep"] for record in records) == expected_rksteps)
        stage_reports = []
        first_failure = None
        predictor_qv_negative = []
        for index, record in enumerate(records):
            result = _stage_violations(record, policy)
            violations = result["violations"]
            strict_checks = _strict_source_checks(record["fields"]) if strict_source_coefficients else None
            strict_violations = _strict_source_violations(strict_checks) if strict_checks else {}
            gate_stage = (record["stage"], record["rkstep"]) in STRICT_ENDPOINT_STAGES
            if strict_source_coefficients and (
                    (record["stage"] == "PRE_RK" and record["rkstep"] == 0) or
                    (record["stage"] == "RK_STAGE_END" and record["rkstep"] in (1, 2))):
                q_stats = result["stats"].get("Q", {})
                if q_stats.get("negative", 0):
                    predictor_qv_negative.append({"stage": record["stage"], "rkstep": record["rkstep"],
                                                  "negative_cells": q_stats["negative"]})
            should_gate = (gate_stage if strict_source_coefficients else True)
            has_failure = (any(violations.values()) or bool(strict_violations)) if should_gate else False
            if first_failure is None and has_failure:
                first_failure = {"stage": record["stage"], "rkstep": record["rkstep"],
                                 "state_index": index, **violations}
                if strict_violations:
                    first_failure["strict_source_coefficients"] = strict_violations
            stage_reports.append({"stage": record["stage"], "rkstep": record["rkstep"],
                                  "density_contract_status": record["density_contract_status"],
                                  **result,
                                  **({"strict_source_coefficients": strict_checks,
                                     "strict_source_coefficient_violations": strict_violations,
                                     "strict_endpoint_gate_applies": gate_stage}
                                    if strict_source_coefficients else {})})
        density_verified = all(
            record["density_contract_status"] == "AUTHORITATIVE_DRY_FROM_AL_ALB"
            for record in records)
        complete = (sequence_ok and rkstep_sequence_ok and density_verified and
                    "POST_KDM6" in sequence)
        passed = complete and first_failure is None
        timestep_reports.append({
            "timestep": timestep,
            "observed_post_kdm6": "POST_KDM6" in sequence,
            "completed_post_kdm6": complete,
            "state_record_count": len(records),
            "state_stage_sequence": sequence,
            "required_state_sequence_complete": sequence_ok,
            "required_rkstep_sequence_complete": rkstep_sequence_ok,
            "density_contract_verified": density_verified,
            "first_recorded_state_violation": first_failure,
            **({"intermediate_predictor_qv_negative_records": predictor_qv_negative}
               if strict_source_coefficients else {}),
            "status": "PASS" if passed else "FAIL" if complete else "INCOMPLETE",
            "completed_state_summaries": stage_reports,
        })
    build_binding = {"status": "NOT_PROVIDED"}
    if build_receipt is not None:
        if expected_executable is None or not expected_parent_executable_sha256:
            raise pr85.TraceError("build receipt requires expected executable and parent hash")
        build_binding = _bind_overlay_build(
            build_receipt, expected_executable, expected_parent_executable_sha256)
    elif expected_executable is not None or expected_parent_executable_sha256 is not None:
        raise pr85.TraceError("executable binding requires a build receipt")
    timestep_ids = sorted(by_timestep)
    timestep_ids_contiguous = timestep_ids == list(range(1, max(timestep_ids, default=0) + 1))
    status = ("FAIL" if any(report["status"] == "FAIL" for report in timestep_reports) else
              "INCOMPLETE" if not timestep_reports or
              not timestep_ids_contiguous or
              any(report["status"] == "INCOMPLETE" for report in timestep_reports) else "PASS")
    stage_counts = Counter(record["stage"] for record in states)
    return {
        "schema": "pr87_completed_state_audit_v1",
        "status": status,
        "scope": "Independent completed-state Q/N/B, PSD-cone, dry-density conversion, and entry-cap checks per timestep; rules are delegated to PR85 helpers.",
        "strict_source_coefficient_mode": strict_source_coefficients,
        **({"strict_source_coefficient_contract": {
                "cloud_rain_bounds": "source REAL32 coefficients, exact Q/N bounds and both REAL64 and REAL32 rho*N volume checks; no ULP tolerance",
                "graupel_bounds": "exact QG/BG in [100,900]; no ULP tolerance",
                "ice": "additional exact source-coefficient diagnostic only; existing native ice acceptance remains separately declared",
                "gate_stages": [list(stage) for stage in sorted(STRICT_ENDPOINT_STAGES)],
                "coefficients": STRICT_SOURCE_COEFFICIENTS,
            }} if strict_source_coefficients else {}),
        "input": input_identity,
        "consumer_build_binding": build_binding,
        "trace_timestep_count": len(by_timestep),
        "trace_timesteps": timestep_ids,
        "timestep_ids_contiguous_from_one": timestep_ids_contiguous,
        "completed_post_kdm6_timestep_count": sum(
            report["completed_post_kdm6"] for report in timestep_reports),
        "state_record_count": len(states),
        "state_stage_counts": dict(sorted(stage_counts.items())),
        "density_contract": {
            "formula_for_v2": "DEN is real32(1)/(AL+ALB), authoritative dry-air density; use DEN directly.",
            "source_helper": "pr85_joint_stage_trace._dry_density",
            "policy_sha256": pr85.POLICY_SHA256,
        },
        "timestep_audits": timestep_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--expected-executable", type=Path, required=True)
    parser.add_argument("--expected-parent-executable-sha256", required=True)
    parser.add_argument("--strict-source-coefficients", action="store_true",
                        help="add exact source-coefficient checks; gate completed endpoint states")
    args = parser.parse_args()
    try:
        report = audit(args.trace, build_receipt=args.build_receipt,
                       expected_executable=args.expected_executable,
                       expected_parent_executable_sha256=args.expected_parent_executable_sha256,
                       strict_source_coefficients=args.strict_source_coefficients)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    except (OSError, pr85.TraceError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
