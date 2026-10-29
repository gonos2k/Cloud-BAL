#!/usr/bin/env python3
"""Summarize same-density species comparisons for validated CP02 controls."""

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
ANALYZER_PATH = ROOT / "tools/cp02_control_capture_analysis.py"
CAPTURE_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/capture/hydro_capture.json.gz"
POINTS_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/capture/shadow_points.csv"
SELECTION_PATH = ROOT / "docs/evidence/cp02_density_controls_20261029/controls/capture_points.csv"
DEFAULT_OUTPUT = ROOT / "docs/evidence/cp02_control_reproducibility_20261029/science"
EXPECTED_CAPTURE_SHA256 = "b3686b7a7b3294c90504e71f75d17a8210f670df7608bef64714a27f777a6321"
EXPECTED_PROFILE_COUNT = 440
EXPECTED_OBSERVED_COUNT = 141
SPECIES = ("rain", "snow")
def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_analyzer():
    spec = importlib.util.spec_from_file_location("cp02_control_capture_analysis", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load CP02 control capture analyzer: {ANALYZER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finite_number(profile, field, *, minimum=None):
    value = profile.get(field)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field}: missing or invalid finite number")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field}: missing or invalid finite number") from exc
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError(f"{field}: missing or invalid finite number")
    return value


def sample_key(profile):
    fields = ("fortran_i", "fortran_j", "fortran_k")
    values = tuple(profile.get(field) for field in fields)
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError("invalid or missing 1-based Fortran sample key")
    return values


def build_sample(profile):
    """Bind raw mixing ratios and captured density to one validated sample."""
    key = sample_key(profile)
    require(profile.get("actual_observation.radar_reflectivity.valid") is True,
            f"{key}: reflectivity observation is not valid")
    require(profile.get("diagnose_radar_cells_post.radar_observed") is True,
            f"{key}: sample is not marked radar observed")
    for stage in ("density_entry", "density_return", "phase_allocation_return"):
        require(profile.get(f"{stage}.status") == "CAPTURED", f"{key}: {stage} was not captured")

    rho = finite_number(profile, "density_return.rho_d", minimum=0.0)
    allocation_rho = finite_number(profile, "phase_allocation_return.rho_d", minimum=0.0)
    require(rho > 0.0 and rho == allocation_rho,
            f"{key}: density return and phase allocation density must be equal and positive")
    phase_code = profile.get("diagnose_radar_cells_post.phase")
    require(type(phase_code) is int and phase_code in (1, 2), f"{key}: unsupported captured phase")
    quality = profile.get("actual_observation.radar_reflectivity.quality")
    require(type(quality) is int and quality >= 0, f"{key}: invalid reflectivity quality")

    sample = {
        "raw_sample_key": f"{key[0]},{key[1]},{key[2]}",
        "fortran_i": key[0], "fortran_j": key[1], "fortran_k": key[2],
        "point_id": profile.get("point_id"), "role": profile.get("role"),
        "phase_code": phase_code, "phase": "rain" if phase_code == 1 else "snow",
        "quality": quality,
        "dBZ": finite_number(profile, "actual_observation.radar_reflectivity.value"),
        "temperature_K": finite_number(profile, "density_entry.temperature", minimum=0.0),
        "pressure_Pa": finite_number(profile, "density_entry.pressure", minimum=0.0),
        "rho_d_kg_m3": rho,
    }
    require(isinstance(sample["point_id"], str) and isinstance(sample["role"], str),
            f"{key}: missing frozen point selection metadata")
    for species in SPECIES:
        qbg = finite_number(profile, f"background_{species}", minimum=0.0)
        qinput = finite_number(profile, f"actual_input.{species}", minimum=0.0)
        require(qbg == qinput, f"{key}: canonical background {species} differs from captured input")
        qdiag = finite_number(profile, f"publish_hydrometeor_candidate_post.{species}", minimum=0.0)
        qfinal = finite_number(profile, f"final.{species}", minimum=0.0)
        sample[f"qbg_{species}_kg_kg"] = qbg
        sample[f"qdiag_{species}_kg_kg"] = qdiag
        sample[f"qfinal_{species}_kg_kg"] = qfinal
        cbg, cdiag, cfinal = (rho * qbg, rho * qdiag, rho * qfinal)
        sample[f"Cbg_eq_{species}_kg_m3"] = cbg
        sample[f"Cdiag_{species}_kg_m3"] = cdiag
        sample[f"Cfinal_{species}_kg_m3"] = cfinal
        sample[f"Cdiag_minus_Cbg_eq_{species}_kg_m3"] = cdiag - cbg
        sample[f"Cfinal_minus_Cbg_eq_{species}_kg_m3"] = cfinal - cbg
        sample[f"ratio_Cdiag_over_Cbg_eq_{species}"] = cdiag / cbg if cbg > 0.0 else None
        sample[f"ratio_Cfinal_over_Cbg_eq_{species}"] = cfinal / cbg if cbg > 0.0 else None
    sample["qdiag_graupel_kg_kg"] = finite_number(
        profile, "publish_hydrometeor_candidate_post.graupel", minimum=0.0)
    sample["qfinal_graupel_kg_kg"] = finite_number(profile, "final.graupel", minimum=0.0)
    active = sample["phase"]
    inactive = "snow" if active == "rain" else "rain"
    allocation_total = finite_number(profile, "phase_allocation_return.total", minimum=0.0)
    require(allocation_total == sample[f"qdiag_{active}_kg_kg"],
            f"{key}: REAL64 allocation total differs from active diagnostic species")
    require(struct.pack("<f", allocation_total) == struct.pack("<f", sample[f"qfinal_{active}_kg_kg"]),
            f"{key}: allocation total does not round to active REAL32 final species")
    for precision in ("qdiag", "qfinal"):
        require(sample[f"{precision}_{inactive}_kg_kg"] == 0.0
                and sample[f"{precision}_graupel_kg_kg"] == 0.0,
                f"{key}: inactive species or graupel is nonzero in {precision} state")
    return sample


def summarize_group(rows, group, species, observed_control_count):
    qbg = sum(row[f"qbg_{species}_kg_kg"] for row in rows)
    qdiag = sum(row[f"qdiag_{species}_kg_kg"] for row in rows)
    qfinal = sum(row[f"qfinal_{species}_kg_kg"] for row in rows)
    cbg = sum(row[f"Cbg_eq_{species}_kg_m3"] for row in rows)
    cdiag = sum(row[f"Cdiag_{species}_kg_m3"] for row in rows)
    cfinal = sum(row[f"Cfinal_{species}_kg_m3"] for row in rows)
    background_positive = sum(row[f"qbg_{species}_kg_kg"] > 0.0 for row in rows)
    return {
        **group, "species": species, "phase": species,
        "sample_count": len(rows), "observed_control_count": observed_control_count,
        "positive_background_count": background_positive,
        "zero_background_count": len(rows) - background_positive,
        f"sum_qbg_{species}_kg_kg": qbg,
        f"sum_qdiag_{species}_kg_kg": qdiag,
        f"sum_qfinal_{species}_kg_kg": qfinal,
        f"sum_Cbg_eq_{species}_kg_m3": cbg,
        f"sum_Cdiag_{species}_kg_m3": cdiag,
        f"sum_Cfinal_{species}_kg_m3": cfinal,
        f"sum_Cdiag_minus_Cbg_eq_{species}_kg_m3": cdiag - cbg,
        f"sum_Cfinal_minus_Cbg_eq_{species}_kg_m3": cfinal - cbg,
        f"ratio_of_sums_Cdiag_over_Cbg_eq_{species}": cdiag / cbg if cbg > 0.0 else None,
        f"ratio_of_sums_Cfinal_over_Cbg_eq_{species}": cfinal / cbg if cbg > 0.0 else None,
        "dBZ_min": min(row["dBZ"] for row in rows), "dBZ_max": max(row["dBZ"] for row in rows),
        "temperature_K_min": min(row["temperature_K"] for row in rows),
        "temperature_K_max": max(row["temperature_K"] for row in rows),
        "pressure_Pa_min": min(row["pressure_Pa"] for row in rows),
        "pressure_Pa_max": max(row["pressure_Pa"] for row in rows),
        "rho_d_kg_m3_min": min(row["rho_d_kg_m3"] for row in rows),
        "rho_d_kg_m3_max": max(row["rho_d_kg_m3"] for row in rows),
    }


def grouped_stats(samples, dimensions):
    grouped = defaultdict(list)
    for sample in samples:
        key = tuple(sample[name] for name in dimensions)
        grouped[key].append(sample)
    rows = []
    for key, profiles in sorted(grouped.items()):
        group = dict(zip(dimensions, key))
        for species in SPECIES:
            active_profiles = [sample for sample in profiles if sample["phase"] == species]
            if active_profiles:
                rows.append(summarize_group(active_profiles, group, species, len(profiles)))
    return rows


def build_report(summary, profiles):
    require(summary.get("status") == "PASS_SCOPED_AVAILABLE_ENDPOINTS",
            "control capture analyzer did not return scoped pass")
    require(len(profiles) == EXPECTED_PROFILE_COUNT, f"expected {EXPECTED_PROFILE_COUNT} validated profiles")
    keys = [sample_key(profile) for profile in profiles]
    require(len(set(keys)) == EXPECTED_PROFILE_COUNT, "duplicate validated profile sample key")
    observed = [profile for profile in profiles
                if profile.get("actual_observation.radar_reflectivity.valid") is True]
    samples = [build_sample(profile) for profile in observed]
    require(len(samples) == EXPECTED_OBSERVED_COUNT,
            f"expected {EXPECTED_OBSERVED_COUNT} observed captured samples, found {len(samples)}")
    role_stats = grouped_stats(samples, ("role",))
    role_quality_stats = grouped_stats(samples, ("role", "quality"))
    return {
        "schema": "cp02_control_density_comparison_v1",
        "status": "PASS_SCOPED_VALIDATED_CONTROL_SAMPLES",
        "sample_count": len(samples),
        "formula": {
            "Cbg_eq": "captured density_return.rho_d × canonical background species mixing ratio",
            "Cdiag": "the same captured density_return.rho_d × REAL64 diagnostic candidate mixing ratio",
            "Cfinal": "the same captured density_return.rho_d × final REAL32 mixing ratio",
            "group_ratio": "ratio of concentration sums; density weighted and undefined when summed background concentration is zero",
            "difference": "concentration sum minus same-density background-equivalent concentration sum",
        },
        "grouped_role_species_stats": role_stats,
        "grouped_role_species_quality_stats": role_quality_stats,
        "provenance": {
            "capture_analysis_summary": summary,
            "limitations": [
                "Only the frozen selected 20-column set is represented; observed rows are the valid reflectivity samples within those columns.",
                "This is an equal-density comparison of archived captured operands, not historical density reconstruction, causal attribution, forecast skill, or a mass-conservation result.",
                "Zero-background ratios are null; zero-background samples remain included in counts and concentration sums.",
            ],
        },
        "samples": samples,
    }


def plot_comparison(role_rows, output_path):
    role_labels = {
        "lost_hit": "Lost hit",
        "retained_hit": "Retained hit",
        "removed_false_alarm": "Removed FA",
        "RN1_positive_reference_all_forecasts_below5mm": "Weak positive",
    }
    role_order = {role: index for index, role in enumerate(role_labels)}
    groups = sorted({(row["role"], row["species"]) for row in role_rows},
                    key=lambda item: (role_order.get(item[0], len(role_order)), item[1]))
    labels = [f"{role_labels.get(role, role)}\n{species}" for role, species in groups]
    ratios = [next((row[f"ratio_of_sums_Cdiag_over_Cbg_eq_{species}"]
                    for row in role_rows if row["role"] == role and row["species"] == species), None)
              for role, species in groups]
    colors = ["#1769aa" if species == "rain" else "#d35400" for _, species in groups]
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    positions = list(range(len(groups)))
    ax.bar(positions, [value if value is not None else 0.0 for value in ratios], color=colors)
    ax.set_xticks(positions, labels, fontsize=9)
    ax.set_ylabel("Ratio of summed same-density concentrations")
    ax.set_title("Archived observed control samples by role and species")
    ax.axhline(1.0, color="#555", linewidth=1, linestyle="--")
    ax.grid(True, axis="y", alpha=0.25)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def run(output_dir=DEFAULT_OUTPUT):
    for path in (CAPTURE_PATH, POINTS_PATH, SELECTION_PATH):
        require(path.is_file(), f"missing frozen input: {path}")
    capture_hash = hashlib.sha256(CAPTURE_PATH.read_bytes()).hexdigest()
    require(capture_hash == EXPECTED_CAPTURE_SHA256, "capture SHA-256 differs from frozen archived capture")
    analyzer = load_analyzer()
    summary, profiles = analyzer.analyze_paths(CAPTURE_PATH, POINTS_PATH, SELECTION_PATH)
    report = build_report(summary, profiles)
    report["provenance"]["input_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CAPTURE_PATH, POINTS_PATH, SELECTION_PATH, ANALYZER_PATH,
                     Path(__file__), ROOT / "tests/test_cp02_control_density_comparison.py")
    }
    write_outputs(report, output_dir)
    return report


def write_outputs(report, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = (output_dir / "control_density_comparison.json",
             output_dir / "control_density_samples.csv",
             output_dir / "control_density_groups.csv",
             output_dir / "control_density_comparison.png")
    require(not any(path.exists() or path.is_symlink() for path in paths),
            "refusing to overwrite existing control density evidence")
    saved_report = {key: value for key, value in report.items() if key != "samples"}
    paths[0].write_text(json.dumps(saved_report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with paths[1].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report["samples"][0]))
        writer.writeheader()
        writer.writerows(report["samples"])
    groups = report["grouped_role_species_stats"] + report["grouped_role_species_quality_stats"]
    with paths[2].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in groups for key in row)))
        writer.writeheader()
        writer.writerows(groups)
    plot_comparison(report["grouped_role_species_stats"], paths[3])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.output_dir)
    print(f"{report['status']}: {report['sample_count']} observed samples -> {args.output_dir}")


if __name__ == "__main__":
    main()
