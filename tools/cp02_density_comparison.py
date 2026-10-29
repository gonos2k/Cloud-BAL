#!/usr/bin/env python3
"""Compare archived CP02 candidate and background species at captured density."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "docs/evidence/cp02_radar_inputs_20261028/analyze_radar_inputs.py"
CAPTURE_PATH = ROOT / "docs/evidence/cp02_radar_inputs_20261028/hydro_capture.json.gz"
BACKGROUND_PATH = ROOT / "docs/evidence/cp02_initial_species_20261027/final/shadow/shadow_species_profiles.csv"
DEFAULT_OUTPUT = ROOT / "docs/evidence/cp02_density_controls_20261029/density"
EXPECTED_PROFILE_COUNT = 440
EXPECTED_OBSERVED_COUNT = 190


def load_analyzer():
    spec = importlib.util.spec_from_file_location("cp02_radar_inputs_analyzer", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load validated CP02 analyzer: {ANALYZER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finite_number(profile, name, *, minimum=None):
    value = profile.get(name)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name}: missing or invalid finite number")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: missing or invalid finite number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name}: missing or invalid finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name}: value must be >= {minimum}")
    return value


def sample_key(profile):
    names = ("fortran_i", "fortran_j", "fortran_k")
    values = tuple(profile.get(name) for name in names)
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError("invalid or missing 1-based Fortran sample key")
    return values


def build_sample(profile):
    """Make one same-density sample; all inputs remain bound to one raw key."""
    key = sample_key(profile)
    prefix = "density_entry."
    pressure = finite_number(profile, prefix + "pressure", minimum=0.0)
    temperature = finite_number(profile, prefix + "temperature", minimum=0.0)
    rho = finite_number(profile, "density_return.rho_d", minimum=0.0)
    allocation_rho = finite_number(profile, "phase_allocation_return.rho_d", minimum=0.0)
    if pressure <= 0.0 or temperature <= 0.0 or rho <= 0.0 or allocation_rho <= 0.0:
        raise ValueError(f"{key}: pressure, temperature, and dry-air density must be positive")
    if rho != allocation_rho:
        raise ValueError(f"{key}: density return and allocation density differ")
    if profile.get("density_entry.status") != "CAPTURED" or profile.get("density_return.status") != "CAPTURED":
        raise ValueError(f"{key}: density call was not captured")
    if profile.get("phase_allocation_return.status") != "CAPTURED":
        raise ValueError(f"{key}: phase allocation was not captured")
    phase = profile.get("diagnose_radar_cells_post.phase")
    if type(phase) is not int or phase not in (1, 2):
        raise ValueError(f"{key}: unsupported observed phase")
    if profile.get("actual_observation.radar_reflectivity.valid") is not True:
        raise ValueError(f"{key}: observed sample lacks valid reflectivity")
    if profile.get("diagnose_radar_cells_post.radar_observed") is not True:
        raise ValueError(f"{key}: sample is not marked radar observed")
    quality = profile.get("actual_observation.radar_reflectivity.quality")
    if type(quality) is not int or quality < 0:
        raise ValueError(f"{key}: invalid reflectivity quality")
    dbz = finite_number(profile, "actual_observation.radar_reflectivity.value")
    total = finite_number(profile, "phase_allocation_return.total", minimum=0.0)

    qbg = {
        species: finite_number(profile, f"background_{species}", minimum=0.0)
        for species in ("rain", "snow")
    }
    for species in ("rain", "snow"):
        actual_input = finite_number(profile, f"actual_input.{species}", minimum=0.0)
        if actual_input != qbg[species]:
            raise ValueError(f"{key}: canonical background {species} differs from captured actual input")
    sample = {
        "raw_sample_key": f"{key[0]},{key[1]},{key[2]}",
        "fortran_i": key[0], "fortran_j": key[1], "fortran_k": key[2],
        "dBZ": dbz, "temperature_K": temperature, "pressure_Pa": pressure,
        "rho_d_kg_m3": rho, "phase_code": phase,
        "phase": "rain" if phase == 1 else "snow", "quality": quality,
        "qbg_rain_kg_kg": qbg["rain"],
        "qbg_snow_kg_kg": qbg["snow"],
        "total_kg_kg": total,
        "qdiag_rain_kg_kg": finite_number(profile, "publish_hydrometeor_candidate_post.rain", minimum=0.0),
        "qdiag_snow_kg_kg": finite_number(profile, "publish_hydrometeor_candidate_post.snow", minimum=0.0),
        "qdiag_graupel_kg_kg": finite_number(profile, "publish_hydrometeor_candidate_post.graupel", minimum=0.0),
        "qfinal_rain_kg_kg": finite_number(profile, "final.rain", minimum=0.0),
        "qfinal_snow_kg_kg": finite_number(profile, "final.snow", minimum=0.0),
        "qfinal_graupel_kg_kg": finite_number(profile, "final.graupel", minimum=0.0),
    }
    for species in ("rain", "snow"):
        qbg = sample[f"qbg_{species}_kg_kg"]
        qdiag = sample[f"qdiag_{species}_kg_kg"]
        qfinal = sample[f"qfinal_{species}_kg_kg"]
        cdiag = rho * qdiag
        cfinal = rho * qfinal
        cbg = rho * qbg
        sample[f"Cdiag_{species}_kg_m3"] = cdiag
        sample[f"Cfinal_{species}_kg_m3"] = cfinal
        sample[f"Cbg_eq_{species}_kg_m3"] = cbg
        sample[f"ratio_{species}_Cdiag_over_Cbg_eq"] = cdiag / cbg if cbg > 0.0 else None
        sample[f"ratio_{species}_Cfinal_over_Cbg_eq"] = cfinal / cbg if cbg > 0.0 else None
    active = "rain" if phase == 1 else "snow"
    other = "snow" if phase == 1 else "rain"
    active_diag = sample[f"qdiag_{active}_kg_kg"]
    active_final = sample[f"qfinal_{active}_kg_kg"]
    active_total = sample["total_kg_kg"]
    if active_total != active_diag:
        raise ValueError(f"{key}: captured total differs from active REAL64 diagnostic species")
    rounds_to_final = struct.pack("<f", active_total) == struct.pack("<f", active_final)
    if not rounds_to_final:
        raise ValueError(f"{key}: captured total does not round to final active REAL32 species")
    for prefix in ("qdiag", "qfinal"):
        if sample[f"{prefix}_{other}_kg_kg"] != 0.0 or sample[f"{prefix}_graupel_kg_kg"] != 0.0:
            raise ValueError(f"{key}: inactive phase or graupel is nonzero in {prefix} species")
    sample["active_species"] = active
    sample["active_Cdiag_kg_m3"] = sample[f"Cdiag_{active}_kg_m3"]
    sample["active_Cfinal_kg_m3"] = sample[f"Cfinal_{active}_kg_m3"]
    sample["active_Cbg_eq_kg_m3"] = sample[f"Cbg_eq_{active}_kg_m3"]
    sample["active_diag_concentration_ratio"] = sample[f"ratio_{active}_Cdiag_over_Cbg_eq"]
    sample["active_final_concentration_ratio"] = sample[f"ratio_{active}_Cfinal_over_Cbg_eq"]
    sample["total_minus_active_diag_kg_kg"] = active_total - active_diag
    sample["total_minus_active_final_kg_kg"] = active_total - active_final
    sample["total_rounds_to_active_final_real32"] = rounds_to_final
    return sample


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = fraction * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def grouped_stats(samples):
    groups = defaultdict(list)
    for row in samples:
        groups[(row["phase_code"], row["quality"])].append(row)
    output = []
    for (phase_code, quality), rows in sorted(groups.items()):
        species = "rain" if phase_code == 1 else "snow"
        diag_ratios = [row["active_diag_concentration_ratio"] for row in rows
                       if row["active_diag_concentration_ratio"] is not None]
        final_ratios = [row["active_final_concentration_ratio"] for row in rows
                        if row["active_final_concentration_ratio"] is not None]
        sum_cdiag = sum(row["active_Cdiag_kg_m3"] for row in rows)
        sum_cfinal = sum(row["active_Cfinal_kg_m3"] for row in rows)
        sum_cbg = sum(row["active_Cbg_eq_kg_m3"] for row in rows)
        output.append({
            "phase_code": phase_code, "phase": species, "quality": quality,
            "count": len(rows), "positive_background_count": len(diag_ratios),
            "zero_background_count": len(rows) - len(diag_ratios),
            "sum_Cdiag_kg_m3": sum_cdiag, "sum_Cbg_eq_kg_m3": sum_cbg,
            "ratio_of_sums_Cdiag_over_Cbg_eq": sum_cdiag / sum_cbg if sum_cbg > 0.0 else None,
            "cell_Cdiag_ratio_median": percentile(diag_ratios, 0.5),
            "cell_Cdiag_ratio_p10": percentile(diag_ratios, 0.1),
            "cell_Cdiag_ratio_p90": percentile(diag_ratios, 0.9),
            "cell_Cdiag_ratio_min": min(diag_ratios) if diag_ratios else None,
            "cell_Cdiag_ratio_max": max(diag_ratios) if diag_ratios else None,
            "sum_Cfinal_kg_m3": sum_cfinal,
            "ratio_of_sums_Cfinal_over_Cbg_eq": sum_cfinal / sum_cbg if sum_cbg > 0.0 else None,
            "cell_Cfinal_ratio_median": percentile(final_ratios, 0.5),
            "cell_Cfinal_ratio_p10": percentile(final_ratios, 0.1),
            "cell_Cfinal_ratio_p90": percentile(final_ratios, 0.9),
        })
    return output


def build_comparison(profiles):
    if len(profiles) != EXPECTED_PROFILE_COUNT:
        raise ValueError(f"expected {EXPECTED_PROFILE_COUNT} validated canonical profiles")
    all_keys = [sample_key(profile) for profile in profiles]
    if len(set(all_keys)) != EXPECTED_PROFILE_COUNT:
        raise ValueError("duplicate canonical profile sample key")
    observed_profiles = [profile for profile in profiles
                         if profile.get("actual_observation.radar_reflectivity.valid") is True]
    samples = [build_sample(profile) for profile in observed_profiles]
    if len(samples) != EXPECTED_OBSERVED_COUNT:
        raise ValueError(f"expected {EXPECTED_OBSERVED_COUNT} observed samples, found {len(samples)}")
    return {
        "schema": "cp02_same_captured_density_comparison_v1",
        "status": "PASS_SCOPED_ARCHIVED_SAMPLES",
        "sample_count": len(samples),
        "formula": {
            "Cdiag": "captured density_return.rho_d * REAL64 publish_hydrometeor_candidate_post diagnostic species mixing ratio",
            "Cfinal": "the same captured density_return.rho_d * final REAL32 species mixing ratio, shown separately to expose output rounding",
            "Cbg_eq": "the same captured density_return.rho_d * canonical background species mixing ratio",
            "ratio": "Cdiag / Cbg_eq; per-cell this equals qdiag / qbg because both use identical rho_d; undefined when Cbg_eq is zero",
            "grouped_ratio": "ratio of concentration sums is dry-density weighted and can differ from an unweighted mean of per-cell ratios",
            "scope_note": "This equal-density counterfactual is not a reconstruction of historical original concentration.",
        },
        "grouped_phase_quality_stats": grouped_stats(samples),
        "captured_final_state_contract": {
            "diagnostic_species_precision": "REAL64 captured publish_hydrometeor_candidate_post work arrays",
            "final_species_precision": "REAL32 decoded by the existing CP02 analyzer",
            "total_active_diagnostic_identity": "each REAL64 phase allocation total exactly equals active REAL64 diagnostic species",
            "diagnostic_inactive_species_identity": "the other rain/snow phase and graupel are zero in diagnostic work arrays",
            "final_inactive_species_identity": "the other rain/snow phase and graupel are zero in final REAL32 state",
            "total_rounds_to_active_final_real32_all": all(row["total_rounds_to_active_final_real32"] for row in samples),
            "total_minus_active_final_abs_max_kg_kg": max(abs(row["total_minus_active_final_kg_kg"]) for row in samples),
            "total_minus_active_diagnostic_abs_max_kg_kg": max(abs(row["total_minus_active_diag_kg_kg"]) for row in samples),
        },
        "samples": samples,
    }


def plot_comparison(samples, path):
    """Plot equal-density concentration pairs and phase/QC ratio distributions."""
    groups = sorted({(row["phase_code"], row["quality"]) for row in samples})
    palette = ("#1769aa", "#d35400", "#2e8b57", "#8e44ad")
    colors = {group: palette[index % len(palette)] for index, group in enumerate(groups)}
    figure, (scatter, ratios) = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    positive = [row for row in samples if row["active_Cbg_eq_kg_m3"] > 0 and row["active_Cdiag_kg_m3"] > 0]
    for group in groups:
        phase, quality = group
        rows = [row for row in positive if (row["phase_code"], row["quality"]) == group]
        scatter.scatter([row["active_Cbg_eq_kg_m3"] for row in rows],
                        [row["active_Cdiag_kg_m3"] for row in rows],
                        s=24, alpha=0.75, color=colors[group],
                        label=f"{'rain' if phase == 1 else 'snow'}, QC={quality}")
    if positive:
        bound = max(max(row["active_Cbg_eq_kg_m3"], row["active_Cdiag_kg_m3"]) for row in positive)
        scatter.plot([bound * 1e-5, bound], [bound * 1e-5, bound], color="#555", linewidth=1, linestyle="--")
        scatter.set_xscale("log")
        scatter.set_yscale("log")
    scatter.set_xlabel("Cbg_eq = captured rho_d × qbg (kg m⁻³)")
    scatter.set_ylabel("Cdiag = captured rho_d × REAL64 diagnostic qdiag (kg m⁻³)")
    scatter.set_title("Same captured density")
    scatter.grid(True, which="both", alpha=0.2)
    scatter.legend(fontsize=8)
    box_values, box_labels, box_colors = [], [], []
    for group in groups:
        phase, quality = group
        values = [row["active_diag_concentration_ratio"] for row in samples
                  if (row["phase_code"], row["quality"]) == group and row["active_diag_concentration_ratio"] is not None]
        if values:
            box_values.append(values)
            box_labels.append(f"{'rain' if phase == 1 else 'snow'}\nQC={quality}\nn={len(values)}")
            box_colors.append(colors[group])
    if box_values:
        artists = ratios.boxplot(box_values, tick_labels=box_labels, patch_artist=True)
        for box, color in zip(artists["boxes"], box_colors):
            box.set_facecolor(color)
            box.set_alpha(0.55)
    ratios.axhline(1.0, color="#555", linewidth=1, linestyle="--")
    ratios.set_ylabel("Per-cell Cdiag / Cbg_eq")
    ratios.set_title("Only cells with positive background")
    ratios.grid(True, axis="y", alpha=0.2)
    figure.suptitle("Archived CP02 observed samples (n=190)")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def write_outputs(report, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "density_comparison.json"
    csv_path = output_dir / "density_comparison.csv"
    plot_path = output_dir / "density_comparison.png"
    existing = [path.name for path in (json_path, csv_path, plot_path) if path.exists() or path.is_symlink()]
    if existing:
        raise ValueError("refusing to overwrite existing density evidence: " + ", ".join(existing))
    json_path.write_text(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2, allow_nan=False)
                         + "\n", encoding="utf-8")
    columns = list(report["samples"][0])
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(report["samples"])
    plot_comparison(report["samples"], plot_path)


def run(output_dir=DEFAULT_OUTPUT):
    analyzer = load_analyzer()
    report = analyzer.analyze(CAPTURE_PATH, BACKGROUND_PATH)
    if report.get("schema") != "cp02-radar-input-analysis-v1" or report.get("status") != "SCOPED_PASS":
        raise ValueError("validated CP02 radar analyzer did not return scoped pass")
    comparison = build_comparison(report["profiles"])
    comparison["provenance"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), ANALYZER_PATH, CAPTURE_PATH, BACKGROUND_PATH)
    }
    comparison["validated_capture_sha256"] = report["capture_sha256"]
    comparison["validated_background_sha256"] = report["background_csv_sha256"]
    write_outputs(comparison, output_dir)
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.output_dir)
    print(f"{report['status']}: {report['sample_count']} archived observed samples -> {args.output_dir}")


if __name__ == "__main__":
    main()
