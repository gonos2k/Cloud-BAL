#!/usr/bin/env python3
"""Weight PR85 v17 first-call process requests by same-cell call geometry.

The mass/count values are vector-activity proxies built from the source-logged
process vectors. They describe proposal suppression, not independent primitive
process gross rates or a closed global budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from pr86_water_budget import cell_slot, load_call_measure

GROUPS = ("NG", "AUT", "G", "WARM")
STAGES = ("proposed", "applied", "deferred")
METRICS = ("mass_kg", "count_number", "heat_abs", "heat_signed")
COLD_SLICES = {"NG": slice(94, 127), "AUT": slice(127, 160), "G": slice(162, 195)}
SEDIMENTATION_FILES = {
    "ICE": "pr85_ice_sedimentation_budget.raw",
    "GRAUPEL": "pr85_graupel_sedimentation_budget.raw",
}


class LedgerError(ValueError):
    """Raised for malformed or geometry-inconsistent first-call ledgers."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _bound_ledger(path: Path, call: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LedgerError(f"ledger is not a regular file: {path}")
    expected = call["receipt"].get("native_trace_outputs", {}).get(path.name, {}).get("sha256")
    if not expected:
        raise LedgerError(f"run receipt does not bind {path.name}")
    return {"path": str(path), "expected_sha256": expected, "bytes": path.stat().st_size}


def _finish_ledger(path: Path, binding: dict[str, Any], digest: Any) -> dict[str, Any]:
    actual = digest.hexdigest()
    if actual != binding["expected_sha256"]:
        raise LedgerError(f"run receipt hash mismatch for {path.name}")
    return {"path": str(path), "sha256": actual, "bytes": binding["bytes"]}


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0.0 else None


def _record_values(line: str, expected_tag: str, count: int,
                   line_number: int) -> tuple[list[int], list[float]]:
    fields = line.split()
    if not fields or fields[0] != expected_tag:
        raise LedgerError(f"line {line_number}: expected {expected_tag}")
    if len(fields) != count:
        raise LedgerError(f"line {line_number}: expected {count} tokens, got {len(fields)}")
    try:
        if expected_tag == "PR85_KDM6_COLD":
            integer_count = 8
            if fields[9] not in ("T", "F"):
                raise ValueError("bad cold stored-noop flag")
            raw_values = fields[10:]
        else:
            integer_count = 7
            if len(fields[8]) != 2 or any(flag not in "TF" for flag in fields[8]):
                raise ValueError("bad warm no-op flags")
            raw_values = fields[9:]
        ids = [int(value) for value in fields[1:1 + integer_count]]
        values = [float(value.replace("D", "E").replace("d", "e"))
                  for value in raw_values]
    except ValueError as exc:
        raise LedgerError(f"line {line_number}: invalid numeric field") from exc
    if not all(math.isfinite(value) for value in values):
        raise LedgerError(f"line {line_number}: nonfinite ledger value")
    return ids, values


def _cold_stage(group: str, data: list[float], stage: int, dry_mass: float,
                cell_volume: float) -> dict[str, float]:
    # Each group serializes three consecutive Q(5), N(3), B, T, QV packets.
    q = data[stage * 5:(stage + 1) * 5]
    n0 = 15 + stage * 3
    number = data[n0:n0 + 3]
    temperature = data[27 + stage]
    qv = data[30 + stage]
    return {
        "mass_kg": 0.5 * (sum(abs(x) for x in (*q, qv))) * dry_mass,
        "count_number": sum(abs(x) for x in number) * cell_volume,
        "heat_abs": abs(temperature) * dry_mass,
        "heat_signed": temperature * dry_mass,
    }


def _warm_stage(data: list[float], stage: int, dry_mass: float,
                cell_volume: float, cpm: float) -> dict[str, float]:
    # Postcap request, admitted request, and stored delta vectors are serialized
    # separately. The deferred vector is request minus admitted, preserving the
    # source's accepted alpha and any native REAL32 rounding.
    requested_q = data[63:68]
    requested_n = data[68:71]
    requested_qv = data[73]
    admitted_q = data[74:79]
    admitted_n = data[79:82]
    admitted_qv = data[84]
    temperature = data[72]
    admitted_temperature = data[83]
    vectors = {
        "proposed": (requested_q, requested_n, requested_qv, temperature),
        "applied": (admitted_q, admitted_n, admitted_qv, admitted_temperature),
        "deferred": ([a - b for a, b in zip(requested_q, admitted_q)],
                     [a - b for a, b in zip(requested_n, admitted_n)],
                     requested_qv - admitted_qv, temperature - admitted_temperature),
    }
    q, number, qv, delta_t = vectors[STAGES[stage]]
    return {
        "mass_kg": 0.5 * sum(abs(x) for x in (*q, qv)) * dry_mass,
        "count_number": sum(abs(x) for x in number) * cell_volume,
        "heat_abs": abs(cpm * delta_t) * dry_mass,
        "heat_signed": cpm * delta_t * dry_mass,
    }


def _new_totals() -> dict[str, dict[str, dict[str, float]]]:
    return {group: {stage: {metric: 0.0 for metric in METRICS} for stage in STAGES}
            for group in GROUPS}


def _new_maps(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    maps = {f"{group}_{stage}_{metric}": np.zeros(shape, dtype=np.float64)
            for group in GROUPS for stage in STAGES for metric in METRICS}
    maps.update({f"cold_residual_{kind}_water_kg": np.zeros(shape, dtype=np.float64)
                 for kind in ("signed", "absolute")})
    maps.update({f"rain_freeze_{stage}_{metric}": np.zeros(shape, dtype=np.float64)
                 for stage in STAGES for metric in ("mass_kg", "count_number")})
    maps.update({f"{kind.lower()}_sedimentation_{stage}_{metric}": np.zeros(shape, dtype=np.float64)
                 for kind in SEDIMENTATION_FILES for stage in STAGES
                 for metric in ("mass_kg", "count_number", "second_inventory")})
    maps.update({f"{kind.lower()}_residual_{side}_water_kg": np.zeros(shape, dtype=np.float64)
                 for kind in ("cold", "warm") for side in ("signed", "absolute")})
    maps["rain_freeze_observed_heat_signed_Kkg"] = np.zeros(shape, dtype=np.float64)
    maps["rain_freeze_observed_heat_abs_Kkg"] = np.zeros(shape, dtype=np.float64)
    return maps


def _add_stage(total: dict[str, float], values: dict[str, float], target: np.ndarray,
               j: int, i: int) -> None:
    for metric in METRICS:
        total[metric] += values[metric]
    target[j, i] += values["mass_kg"]


def _stage_result(values: dict[str, float]) -> dict[str, float]:
    return {key: float(value) for key, value in values.items()}


def _finish_metrics(totals: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group, stages in totals.items():
        metrics: dict[str, Any] = {}
        for metric in METRICS:
            proposed = stages["proposed"][metric]
            applied = stages["applied"][metric]
            deferred = stages["deferred"][metric]
            metrics[metric] = {"proposed": proposed, "applied": applied,
                               "deferred": deferred,
                               "applied_over_proposed": _ratio(applied, proposed),
                               "deferred_over_proposed": _ratio(deferred, proposed)}
        result[group] = metrics
    return result


def analyze_arm(run_root: Path, map_path: Path) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Decode a hash-bound arm ledger and accumulate same-cell weighted activity."""
    call = load_call_measure(run_root)
    bounds = call["bounds"]
    dry_mass = call["dry_mass_jki"]
    volume = call["volume_jki"]
    nj, _, ni = dry_mass.shape
    totals = _new_totals()
    maps = _new_maps((nj, ni))
    identities = {"first_call_receipt_sha256": call["identities"]["receipt"]["sha256"],
                  "ledger_files": {}}
    row_counts = {"cold": 0, "warm": 0}
    residuals = {kind: {side: 0.0 for side in ("signed_water_kg", "absolute_water_kg")}
                 for kind in ("cold", "warm")}
    rain_freeze = {
        stage: {metric: 0.0 for metric in ("mass_kg", "count_number")}
        for stage in STAGES
    }
    rain_freeze_heat = {"signed_Kkg": 0.0, "absolute_Kkg": 0.0}
    absent_receiver = {"records": 0, "proposed_mass_kg": 0.0,
                       "withheld_mass_kg": 0.0, "applied_mass_kg": 0.0}
    sedimentation: dict[str, Any] = {}

    cold_path = run_root / "pr85_kdm6_cold_budget.raw"
    cold_binding = _bound_ledger(cold_path, call)
    cold_digest = hashlib.sha256()
    with cold_path.open("rb") as stream:
        header = None
        for line_number, raw_line in enumerate(stream, 1):
            cold_digest.update(raw_line)
            line = raw_line.decode("ascii").rstrip("\n")
            if line.startswith("# PR85_KDM6_COLD"):
                header = line.rstrip("\n")
                continue
            if not line.startswith("PR85_KDM6_COLD"):
                continue
            ids, data = _record_values(line, "PR85_KDM6_COLD", 217, line_number)
            i, j, k, loop = ids[:4]
            slot = cell_slot(bounds, i, j, k)
            jy, ky, ix = slot
            if data[1] != float(call["rho_dry_jki"][slot]):
                raise LedgerError(f"cold rhoDry differs from same-cell call at {(i,j,k)}")
            for group, span in COLD_SLICES.items():
                packet = data[span]
                if len(packet) != 33:
                    raise LedgerError("cold process packet layout changed")
                for stage_index, stage in enumerate(STAGES):
                    values = _cold_stage(group, packet, stage_index,
                                         float(dry_mass[slot]), float(volume[slot]))
                    _add_stage(totals[group][stage], values,
                               maps[f"{group}_{stage}_mass_kg"], jy, ix)
                    for metric in ("count_number", "heat_abs", "heat_signed"):
                        maps[f"{group}_{stage}_{metric}"][jy, ix] += values[metric]
            # Stored-minus-approved REAL32 residuals are one combined cold-row
            # endpoint check, kept separate from process proposal vectors.
            cold_q = data[195:200]
            cold_qv = data[206]
            cold_signed = (sum(cold_q) + cold_qv) * float(dry_mass[slot])
            cold_absolute = sum(abs(value) for value in (*cold_q, cold_qv)) * float(dry_mass[slot])
            residuals["cold"]["signed_water_kg"] += cold_signed
            residuals["cold"]["absolute_water_kg"] += cold_absolute
            maps["cold_residual_signed_water_kg"][jy, ix] += cold_signed
            maps["cold_residual_absolute_water_kg"][jy, ix] += cold_absolute
            row_counts["cold"] += 1
        if header is None or not header.startswith("# PR85_KDM6_COLD fields:"):
            raise LedgerError("cold ledger header is missing or changed")
    identities["ledger_files"][cold_path.name] = _finish_ledger(cold_path, cold_binding, cold_digest)

    warm_path = run_root / "pr85_kdm6_warm_budget.raw"
    warm_binding = _bound_ledger(warm_path, call)
    warm_digest = hashlib.sha256()
    with warm_path.open("rb") as stream:
        header = None
        for line_number, raw_line in enumerate(stream, 1):
            warm_digest.update(raw_line)
            line = raw_line.decode("ascii").rstrip("\n")
            if line.startswith("# PR85_KDM6_WARM"):
                header = line.rstrip("\n")
                continue
            if not line.startswith("WARM"):
                continue
            ids, data = _record_values(line, "WARM", 116, line_number)
            i, j, k, loop = ids[:4]
            slot = cell_slot(bounds, i, j, k)
            jy, ky, ix = slot
            if data[1] != float(call["rho_dry_jki"][slot]):
                raise LedgerError(f"warm rhoDry differs from same-cell call at {(i,j,k)}")
            for stage_index, stage in enumerate(STAGES):
                values = _warm_stage(data, stage_index, float(dry_mass[slot]),
                                     float(volume[slot]), float(data[2]))
                _add_stage(totals["WARM"][stage], values,
                           maps[f"WARM_{stage}_mass_kg"], jy, ix)
                for metric in ("count_number", "heat_abs", "heat_signed"):
                    maps[f"WARM_{stage}_{metric}"][jy, ix] += values[metric]
            warm_q = data[96:101]
            warm_qv = data[106]
            warm_signed = (sum(warm_q) + warm_qv) * float(dry_mass[slot])
            warm_absolute = sum(abs(value) for value in (*warm_q, warm_qv)) * float(dry_mass[slot])
            residuals["warm"]["signed_water_kg"] += warm_signed
            residuals["warm"]["absolute_water_kg"] += warm_absolute
            maps["warm_residual_signed_water_kg"][jy, ix] += warm_signed
            maps["warm_residual_absolute_water_kg"][jy, ix] += warm_absolute
            row_counts["warm"] += 1
        if header is None or not header.startswith("# PR85_KDM6_WARM"):
            raise LedgerError("warm ledger header is missing or changed")
    identities["ledger_files"][warm_path.name] = _finish_ledger(warm_path, warm_binding, warm_digest)

    if not row_counts["cold"] or not row_counts["warm"]:
        raise LedgerError("cold and warm ledgers must both contain records")
    rain_path = run_root / "pr85_rain_freezing_budget.raw"
    rain_binding = _bound_ledger(rain_path, call)
    rain_digest = hashlib.sha256()
    rain_records = 0
    with rain_path.open("rb") as stream:
        header = None
        for line_number, raw_line in enumerate(stream, 1):
            rain_digest.update(raw_line)
            line = raw_line.decode("ascii").rstrip("\n")
            if line.startswith("# PR85_RAIN_FREEZE:"):
                header = line.rstrip("\n")
                continue
            if not line.startswith("PR85_RAIN_FREEZE"):
                continue
            fields = line.split()
            if len(fields) != 34:
                raise LedgerError(f"rain-freezing line {line_number}: expected 34 tokens")
            i, j, k, _loop = map(int, fields[1:5])
            if len(fields[5]) != 2 or any(value not in "TF" for value in fields[5]):
                raise LedgerError(f"rain-freezing line {line_number}: invalid logical flags")
            try:
                data = [float(value.replace("D", "E").replace("d", "e"))
                        for value in fields[6:]]
            except ValueError as exc:
                raise LedgerError(f"rain-freezing line {line_number}: invalid real") from exc
            if len(data) != 28 or not all(math.isfinite(value) for value in data):
                raise LedgerError(f"rain-freezing line {line_number}: invalid real vector")
            slot = cell_slot(bounds, i, j, k)
            jy, _ky, ix = slot
            cell_mass = float(dry_mass[slot])
            cell_volume = float(volume[slot])
            stage_values = {
                "proposed": (data[1], data[2]),
                "applied": (data[4], data[5]),
                "deferred": (data[7], data[8]),
            }
            for stage, (mass_delta, number_delta) in stage_values.items():
                mass_activity = abs(mass_delta) * cell_mass
                number_activity = abs(number_delta) * cell_volume
                rain_freeze[stage]["mass_kg"] += mass_activity
                rain_freeze[stage]["count_number"] += number_activity
                maps[f"rain_freeze_{stage}_mass_kg"][jy, ix] += mass_activity
                maps[f"rain_freeze_{stage}_count_number"][jy, ix] += number_activity
            observed_heat = (data[19] - data[18]) * cell_mass
            rain_freeze_heat["signed_Kkg"] += observed_heat
            rain_freeze_heat["absolute_Kkg"] += abs(observed_heat)
            maps["rain_freeze_observed_heat_signed_Kkg"][jy, ix] += observed_heat
            maps["rain_freeze_observed_heat_abs_Kkg"][jy, ix] += abs(observed_heat)
            if data[1] != 0.0 and data[12] == 0.0 and data[13] == 0.0:
                absent_receiver["records"] += 1
                absent_receiver["proposed_mass_kg"] += abs(data[1]) * cell_mass
                absent_receiver["applied_mass_kg"] += abs(data[4]) * cell_mass
                absent_receiver["withheld_mass_kg"] += abs(data[7]) * cell_mass
            rain_records += 1
        if header is None or not header.startswith("# PR85_RAIN_FREEZE:"):
            raise LedgerError("rain-freezing ledger header is missing or changed")
    identities["ledger_files"][rain_path.name] = _finish_ledger(rain_path, rain_binding, rain_digest)
    row_counts["rain_freeze"] = rain_records

    for kind, basename in SEDIMENTATION_FILES.items():
        path = run_root / basename
        binding = _bound_ledger(path, call)
        digest = hashlib.sha256()
        tag = "PR85_ICE_SED" if kind == "ICE" else "PR85_G_SED"
        stage_values = {stage: {"mass_kg": 0.0, "count_number": 0.0,
                                "second_inventory": 0.0} for stage in STAGES}
        record_count = 0
        with path.open("rb") as stream:
            header = None
            for line_number, raw_line in enumerate(stream, 1):
                digest.update(raw_line)
                line = raw_line.decode("ascii").rstrip("\n")
                if line.startswith(f"# {tag}:"):
                    header = line.rstrip("\n")
                    continue
                if not line.startswith(tag):
                    continue
                fields = line.split()
                if len(fields) != 17:
                    raise LedgerError(f"{tag} line {line_number}: expected 17 tokens")
                i, j, _substep, _nlevels = map(int, fields[1:5])
                try:
                    values = [float(value.replace("D", "E").replace("d", "e"))
                              for value in fields[5:]]
                except ValueError as exc:
                    raise LedgerError(f"{tag} line {line_number}: invalid real") from exc
                if not all(math.isfinite(value) for value in values):
                    raise LedgerError(f"{tag} line {line_number}: nonfinite real")
                slot = cell_slot(bounds, i, j, bounds["kts"])
                jy, _ky, ix = slot
                area = float(call["area_ji"][jy, ix])
                for stage_index, stage in enumerate(STAGES):
                    mass_activity = values[stage_index] * area
                    second_activity = values[3 + stage_index] * area
                    stage_values[stage]["mass_kg"] += mass_activity
                    maps[f"{kind.lower()}_sedimentation_{stage}_mass_kg"][jy, ix] += mass_activity
                    if kind == "ICE":
                        stage_values[stage]["count_number"] += second_activity
                        maps[f"{kind.lower()}_sedimentation_{stage}_count_number"][jy, ix] += second_activity
                    else:
                        stage_values[stage]["second_inventory"] += second_activity
                        maps[f"{kind.lower()}_sedimentation_{stage}_second_inventory"][jy, ix] += second_activity
                record_count += 1
            if header is None:
                raise LedgerError(f"{tag} ledger header is missing or changed")
        identities["ledger_files"][basename] = _finish_ledger(path, binding, digest)
        sedimentation[kind] = {
            "records": record_count,
            "values": stage_values,
            "secondary_inventory": "count_number" if kind == "ICE" else "volume_m3",
            "applied_mass_over_proposed": _ratio(stage_values["applied"]["mass_kg"],
                                                   stage_values["proposed"]["mass_kg"]),
            "deferred_mass_over_proposed": _ratio(stage_values["deferred"]["mass_kg"],
                                                    stage_values["proposed"]["mass_kg"]),
        }
        if kind == "ICE":
            sedimentation[kind]["applied_count_over_proposed"] = _ratio(
                stage_values["applied"]["count_number"], stage_values["proposed"]["count_number"])
            sedimentation[kind]["deferred_count_over_proposed"] = _ratio(
                stage_values["deferred"]["count_number"], stage_values["proposed"]["count_number"])

    np.savez_compressed(map_path, i=np.arange(bounds["its"], bounds["ite"] + 1),
                        j=np.arange(bounds["jts"], bounds["jte"] + 1), **maps)
    report = {
        "arm": call["arm"],
        "run_root": str(run_root),
        "identity": identities,
        "active_bounds": {key: bounds[key] for key in ("its", "ite", "jts", "jte", "kts", "kte")},
        "same_cell_weighting": {
            "coordinate_mapping": "ledger (i,j,k) maps directly to active call array slot (j-jts,k-kts,i-its)",
            "mass": "rhoDry * DELZ * MAPFAC_M-area; ledger Q and QV kg/kgdry are dry-mass weighted",
            "count": "MAPFAC_M-area * DELZ; ledger N #/m3 is volume weighted",
            "rhoDry_crosscheck": "exact REAL32 ledger value equals the same-cell first-call DEN readback",
            "native_hybrid_mass_same_call_capture": False,
        },
        "source_vector_activity_definition": {
            "mass": "half L1 of the process Q(5) and QV component vector, weighted by same-cell dry-air mass; this is a vector-activity proxy, not independent primitive-process gross mass",
            "count": "L1 of process N(3), weighted by same-cell geometric volume; this is a count-vector activity proxy",
            "cold_heat": "absolute or signed source-logged temperature increment times dry-air mass (K kg); no energy conversion claimed",
            "warm_heat": "cpm * source-logged temperature increment times dry-air mass (J proxy); not a total-enthalpy or closure claim",
            "deferred": "cold source-withheld vector; warm request minus admitted vector",
            "ratios": "applied/proposed and deferred/proposed for the matching process and metric; null when proposal activity is zero",
        },
        "record_counts": row_counts,
        "process_activity": _finish_metrics(totals),
        "rain_freezing": {
            "activity": rain_freeze,
            "proposed_mass_applied_ratio": _ratio(rain_freeze["applied"]["mass_kg"], rain_freeze["proposed"]["mass_kg"]),
            "deferred_mass_proposed_ratio": _ratio(rain_freeze["deferred"]["mass_kg"], rain_freeze["proposed"]["mass_kg"]),
            "proposed_count_applied_ratio": _ratio(rain_freeze["applied"]["count_number"], rain_freeze["proposed"]["count_number"]),
            "deferred_count_proposed_ratio": _ratio(rain_freeze["deferred"]["count_number"], rain_freeze["proposed"]["count_number"]),
            "observed_temperature_increment": rain_freeze_heat,
            "absent_graupel_receiver": absent_receiver,
            "temperature_limit": "Only observed approved ΔT is logged; proposed heat cannot be reconstructed because source-matched xlf/cpm are absent from this ledger.",
        },
        "sedimentation": sedimentation,
        "stored_minus_approved_water_residuals": residuals,
        "spatial_map": {"path": str(map_path), "sha256": _sha256(map_path),
                        "fields": sorted(maps), "axes": "(j,i); one-based i and j arrays included"},
        "limitations": [
            "Frozen PR85 v17 first-call records only; no model reruns or physics changes.",
            "Weighted process vectors measure source-logged candidate activity and suppression, not a complete physical water, number, carrier, or energy closure.",
            "The cold temperature ledger has no source-matched heat capacity term; its heat quantities remain K kg diagnostics.",
            "The warm cpm-weighted temperature diagnostic omits full total-enthalpy terms and is not an energy closure.",
            "The geometry uses captured first-call DEN and DELZ with initial-wrfout MAPFAC_M area; same-call hybrid MU geometry was not captured.",
        ],
    }
    return report, maps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, required=True)
    parser.add_argument("--coupled-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map-dir", type=Path, required=True)
    args = parser.parse_args()
    args.map_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for arm, run_root in (("OFF", args.off_root), ("COUPLED", args.coupled_root)):
        map_path = args.map_dir / f"pr86_process_budget_{arm.lower()}_map.npz"
        report, _ = analyze_arm(run_root.resolve(), map_path)
        if report["arm"] != arm:
            raise LedgerError(f"expected {arm} run but receipt identified {report['arm']}")
        reports[arm] = report
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"schema": "pr86_v17_first_call_process_budget_v1",
                                    "arms": reports}, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"report": str(args.out), "sha256": _sha256(args.out),
                      "arms": {arm: row["record_counts"] for arm, row in reports.items()}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
