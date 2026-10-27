#!/usr/bin/env python3
"""Score hourly precipitation contingency counts and plot them.

This offline utility consumes the retained hourly CSI CSV and, for two newly
requested cutoffs at lead 1, retained parsed/aligned NPZ fields. It does not
rerun a model or reingest raw RN1 bytes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any


CASES = ("OFF", "HYDRO", "LIQUID")
LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
ARCHIVED_THRESHOLDS = (0.1, 1.0, 5.0, 10.0)
COUNT_FIELDS = ("hit", "miss", "false_alarm", "correct_dry")
REQUIRED_FIELDS = (
    "case", "lead_hour", "valid_utc", "threshold_mm", "valid_cells",
    *COUNT_FIELDS, "CSI",
)
EXPECTED_ARCHIVED_ROWS = len(CASES) * len(LEADS) * len(ARCHIVED_THRESHOLDS)
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(value: str, field: str) -> datetime:
    try:
        return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"{field} must use {UTC_FORMAT}: {value!r}") from exc


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def longitude_aspect_ratio(latitude_deg: float) -> float:
    """Return y/x plot aspect that compensates for longitude's cos(latitude) scale."""
    if not math.isfinite(latitude_deg) or abs(latitude_deg) >= 90:
        raise ValueError("latitude must be finite and strictly between -90 and 90 degrees")
    return 1.0 / math.cos(math.radians(latitude_deg))


def threshold_contingency(forecast: Any, reference: Any, threshold: float) -> dict[str, int]:
    """Count events with inclusive ``amount >= threshold`` comparisons."""
    import numpy as np

    forecast_wet = forecast >= threshold
    reference_wet = reference >= threshold
    return {
        "hit": int(np.count_nonzero(forecast_wet & reference_wet)),
        "miss": int(np.count_nonzero(~forecast_wet & reference_wet)),
        "false_alarm": int(np.count_nonzero(forecast_wet & ~reference_wet)),
        "correct_dry": int(np.count_nonzero(~forecast_wet & ~reference_wet)),
    }


def load_and_score(
    input_csv: Path,
    start_time: str,
    expected_cells: int = 3688,
    thresholds: tuple[float, ...] = ARCHIVED_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Validate the requested hourly rows and derive CSI, POD, FAR and bias."""
    start = parse_utc(start_time, "start_time")
    expected_keys = {
        (case, lead, threshold)
        for case in CASES for lead in LEADS for threshold in thresholds
    }
    seen: set[tuple[str, int, float]] = set()
    scored: list[dict[str, Any]] = []

    with input_csv.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing_fields = set(REQUIRED_FIELDS) - set(reader.fieldnames or ())
        if missing_fields:
            raise ValueError(f"CSV missing columns: {', '.join(sorted(missing_fields))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                case = row["case"].strip()
                lead = int(row["lead_hour"])
                valid_time = parse_utc(row["valid_utc"].strip(), "valid_utc")
                threshold = float(row["threshold_mm"])
                valid_cells = int(row["valid_cells"])
                counts = {name: int(row[name]) for name in COUNT_FIELDS}
                raw_csi = row["CSI"].strip()
                recorded_csi = float(raw_csi) if raw_csi else None
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid value on CSV line {line_number}: {exc}") from exc

            key = (case, lead, threshold)
            if key not in expected_keys:
                raise ValueError(f"unexpected case/lead/threshold on CSV line {line_number}: {key}")
            if key in seen:
                raise ValueError(f"duplicate case/lead/threshold on CSV line {line_number}: {key}")
            seen.add(key)
            if valid_time != start + timedelta(hours=lead):
                raise ValueError(
                    f"valid_utc mismatch on CSV line {line_number}: lead {lead} from "
                    f"{start_time} requires {(start + timedelta(hours=lead)).strftime(UTC_FORMAT)}"
                )
            if valid_cells != expected_cells:
                raise ValueError(f"valid_cells must equal {expected_cells} on CSV line {line_number}")
            if any(value < 0 for value in counts.values()):
                raise ValueError(f"negative contingency count on CSV line {line_number}")
            if sum(counts.values()) != valid_cells:
                raise ValueError(f"contingency counts do not sum to valid_cells on CSV line {line_number}")
            if recorded_csi is not None and not math.isfinite(recorded_csi):
                raise ValueError(f"CSI must be finite on CSV line {line_number}")

            hit, miss, false_alarm, _ = (counts[name] for name in COUNT_FIELDS)
            csi = safe_ratio(hit, hit + miss + false_alarm)
            pod = safe_ratio(hit, hit + miss)
            far = safe_ratio(false_alarm, hit + false_alarm)
            frequency_bias = safe_ratio(hit + false_alarm, hit + miss)
            if csi is None:
                if recorded_csi is not None:
                    raise ValueError(f"CSI must be blank when its denominator is zero on CSV line {line_number}")
            elif recorded_csi is None or not math.isclose(recorded_csi, csi, rel_tol=1e-12, abs_tol=1e-15):
                raise ValueError(f"recorded CSI inconsistent with counts on CSV line {line_number}")

            window_end = valid_time
            window_start = window_end - timedelta(hours=1)
            scored.append({
                "status": "EVALUATED",
                "source_kind": ("archived_contingency_csv" if thresholds == ARCHIVED_THRESHOLDS
                                else "hourly_contingency_csv"),
                "case": case,
                "lead_hour": lead,
                "valid_utc": valid_time.strftime(UTC_FORMAT),
                "window_start_utc": window_start.strftime(UTC_FORMAT),
                "window_end_utc": window_end.strftime(UTC_FORMAT),
                "threshold_mm": threshold,
                "valid_cells": valid_cells,
                **counts,
                "CSI": csi,
                "POD": pod,
                "FAR": far,
                "frequency_bias": frequency_bias,
            })

    expected_rows = len(CASES) * len(LEADS) * len(thresholds)
    if len(seen) != expected_rows:
        missing = sorted(expected_keys - seen)
        label = "archived" if thresholds == ARCHIVED_THRESHOLDS else "complete hourly"
        raise ValueError(f"expected {expected_rows} {label} rows, found {len(seen)}; missing {missing[:5]}")
    return sorted(scored, key=lambda row: (row["threshold_mm"], row["lead_hour"], CASES.index(row["case"])))


def score_first_hour_pairs(pairs_npz: Path, archive_rows: list[dict[str, Any]], start_time: str) -> list[dict[str, Any]]:
    """Score first-hour arrays at new thresholds and verify existing lead-1 counts."""
    import numpy as np

    receipt_path = pairs_npz.with_name("first_hour_pairs_receipt.json")
    if not receipt_path.is_file():
        raise ValueError(f"missing first-hour pair receipt: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    declared_hash = receipt.get("derived_npz", {}).get("sha256")
    actual_hash = hashlib.sha256(pairs_npz.read_bytes()).hexdigest()
    if declared_hash != actual_hash:
        raise ValueError("first-hour NPZ hash does not match its receipt")
    if receipt.get("status") != "DERIVED_RETAINED_INTERMEDIATE" or receipt.get("raw_RN1_reingested") is not False:
        raise ValueError("first-hour receipt must identify a retained intermediate, not raw RN1 replay")
    if receipt.get("window_start_utc") != start_time:
        raise ValueError("first-hour NPZ window start does not match --start-time")
    expected_end = (parse_utc(start_time, "start_time") + timedelta(hours=1)).strftime(UTC_FORMAT)
    if receipt.get("window_end_utc") != expected_end or receipt.get("cells") != 3688:
        raise ValueError("first-hour receipt must declare the matching one-hour window and 3688 cells")

    with np.load(pairs_npz, allow_pickle=False) as archive:
        required = {*CASES, "reference", "latitude", "longitude", "flat_index_yx"}
        if set(archive.files) != required:
            raise ValueError(f"first-hour NPZ keys must be exactly {sorted(required)}")
        fields = {name: np.asarray(archive[name], dtype=np.float64) for name in (*CASES, "reference")}
        coordinates = {name: np.asarray(archive[name]) for name in ("latitude", "longitude")}
        flat_indices = np.asarray(archive["flat_index_yx"])
    if any(field.shape != (3688,) for field in (*fields.values(), *coordinates.values(), flat_indices)):
        raise ValueError("first-hour pair arrays must each contain 3688 selected cells")
    if any(not np.isfinite(field).all() for field in (*fields.values(), *coordinates.values())):
        raise ValueError("first-hour pair arrays must be finite")
    if not np.issubdtype(flat_indices.dtype, np.integer) or len(np.unique(flat_indices)) != 3688:
        raise ValueError("flat_index_yx must contain 3688 unique integer indexes")
    if (flat_indices < 0).any() or (flat_indices >= 253 * 149).any():
        raise ValueError("flat_index_yx indexes are outside the ODAM 253x149 crop")
    if any((fields[name] < 0).any() for name in fields):
        raise ValueError("first-hour precipitation amounts must be nonnegative")

    by_key = {(row["case"], row["lead_hour"], row["threshold_mm"]): row for row in archive_rows}
    additions = []
    for case in CASES:
        forecast = fields[case]
        observed = fields["reference"]
        for threshold in ARCHIVED_THRESHOLDS:
            counts = threshold_contingency(forecast, observed, threshold)
            archived = by_key[(case, 1, threshold)]
            if any(counts[name] != archived[name] for name in COUNT_FIELDS):
                raise ValueError(f"first-hour pairs do not reproduce archived lead-1 counts for {case} at {threshold:g} mm")

        for threshold in (0.5, 2.5):
            counts = threshold_contingency(forecast, observed, threshold)
            hit, miss, false_alarm, _ = (counts[name] for name in COUNT_FIELDS)
            additions.append({
                "status": "EVALUATED",
                "source_kind": "retained_first_hour_pairs_npz",
                "case": case,
                "lead_hour": 1,
                "valid_utc": expected_end,
                "window_start_utc": start_time,
                "window_end_utc": expected_end,
                "threshold_mm": threshold,
                "valid_cells": 3688,
                **counts,
                "CSI": safe_ratio(hit, hit + miss + false_alarm),
                "POD": safe_ratio(hit, hit + miss),
                "FAR": safe_ratio(false_alarm, hit + false_alarm),
                "frequency_bias": safe_ratio(hit + false_alarm, hit + miss),
            })
    return additions


def add_not_evaluated_rows(rows: list[dict[str, Any]], start_time: str, expected_cells: int = 3688) -> list[dict[str, Any]]:
    """Fill only unsupported new-threshold lead slots with explicit null status."""
    start = parse_utc(start_time, "start_time")
    by_key = {(row["case"], row["lead_hour"], row["threshold_mm"]): row for row in rows}
    for case in CASES:
        for lead in LEADS:
            end = start + timedelta(hours=lead)
            begin = end - timedelta(hours=1)
            for threshold in THRESHOLDS:
                key = (case, lead, threshold)
                if key in by_key:
                    continue
                row = {
                    "status": "NOT_EVALUATED",
                    "source_kind": "no_source_data",
                    "case": case,
                    "lead_hour": lead,
                    "valid_utc": end.strftime(UTC_FORMAT),
                    "window_start_utc": begin.strftime(UTC_FORMAT),
                    "window_end_utc": end.strftime(UTC_FORMAT),
                    "threshold_mm": threshold,
                    "valid_cells": None,
                    **{name: None for name in COUNT_FIELDS},
                    "CSI": None,
                    "POD": None,
                    "FAR": None,
                    "frequency_bias": None,
                }
                rows.append(row)
                by_key[key] = row
    return sorted(rows, key=lambda row: (row["threshold_mm"], row["lead_hour"], CASES.index(row["case"])))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = (
        "status", "source_kind", "case", "lead_hour", "valid_utc", "window_start_utc", "window_end_utc",
        "threshold_mm", "valid_cells", *COUNT_FIELDS, "CSI", "POD", "FAR", "frequency_bias",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def hourly_score_title(rows: list[dict[str, Any]]) -> str:
    """Describe the valid-time range represented by the hourly score rows."""
    by_key = {(row["case"], row["lead_hour"], row["threshold_mm"]): row for row in rows}
    first_valid = parse_utc(by_key[("OFF", LEADS[0], THRESHOLDS[0])]["valid_utc"], "valid_utc")
    last_valid = parse_utc(by_key[("OFF", LEADS[-1], THRESHOLDS[0])]["valid_utc"], "valid_utc")
    if first_valid.date() == last_valid.date():
        date_label = first_valid.strftime("%Y-%m-%d")
        hours_label = f"{first_valid:%H}–{last_valid:%H}"
    else:
        date_label = f"{first_valid:%Y-%m-%d %H}–{last_valid:%Y-%m-%d %H}"
        hours_label = ""
    period = f"{date_label} · 1-hour windows ending {hours_label} UTC" if hours_label else f"1-hour windows ending {date_label} UTC"
    return f"Hourly precipitation CSI · {period}"


def make_plots(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    import numpy as np

    by_key = {(row["case"], row["lead_hour"], row["threshold_mm"]): row for row in rows}
    threshold_labels = {threshold: f"{threshold:g}" for threshold in THRESHOLDS}
    colors = {"OFF": "#333333", "HYDRO": "#2878b5", "LIQUID": "#d95f02"}
    leads = list(LEADS)

    fig, axes = plt.subplots(3, 2, figsize=(10, 10), sharex=True, sharey=True, constrained_layout=True)
    for ax, threshold in zip(axes.flat, THRESHOLDS):
        for case in CASES:
            values = [by_key[(case, lead, threshold)]["CSI"] for lead in LEADS]
            ax.plot(leads, values, marker="o", linewidth=1.8, label=case, color=colors[case])
        ax.set_title(f"{threshold_labels[threshold]} mm")
        ax.set_xticks(leads)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        if threshold in (0.5, 2.5):
            unavailable = [lead for lead in LEADS if by_key[("OFF", lead, threshold)]["status"] != "EVALUATED"]
            if unavailable:
                note = ("All leads: NOT EVALUATED" if len(unavailable) == len(LEADS)
                        else "Leads " + ", ".join(map(str, unavailable)) + ": NOT EVALUATED")
                ax.text(0.98, 0.95, note, transform=ax.transAxes,
                        ha="right", va="top", fontsize=8, color="#555555")
    axes[2, 0].set_xlabel("Forecast lead (hour)")
    axes[2, 1].set_xlabel("Forecast lead (hour)")
    axes[0, 0].set_ylabel("CSI")
    axes[1, 0].set_ylabel("CSI")
    axes[2, 0].set_ylabel("CSI")
    axes[0, 0].legend(frameon=False)
    fig.suptitle(hourly_score_title(rows))
    evaluated_all = all(by_key[(case, lead, threshold)]["status"] == "EVALUATED"
                        for case in CASES for lead in LEADS for threshold in THRESHOLDS)
    caption = "Supplied hourly contingency counts on 3,688 fixed land points."
    if not evaluated_all:
        first_hour_only = any(
            by_key[(case, 1, threshold)]["status"] == "EVALUATED"
            for case in CASES for threshold in (0.5, 2.5)
        )
        caption += (" 0.5 and 2.5 mm use retained aligned fields at lead 1 only."
                    if first_hour_only else " 0.5 and 2.5 mm scores are NOT_EVALUATED.")
    fig.text(0.5, -0.015, caption,
             ha="center", fontsize=8)
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"hourly_csi.{suffix}", dpi=180 if suffix == "png" else None)
    plt.close(fig)

    deltas = np.full((2, len(THRESHOLDS), len(LEADS)), np.nan, dtype=float)
    for candidate_index, case in enumerate(("HYDRO", "LIQUID")):
        for threshold_index, threshold in enumerate(THRESHOLDS):
            for lead_index, lead in enumerate(LEADS):
                candidate = by_key[(case, lead, threshold)]["CSI"]
                off = by_key[("OFF", lead, threshold)]["CSI"]
                if candidate is not None and off is not None:
                    deltas[candidate_index, threshold_index, lead_index] = candidate - off
    finite_deltas = np.abs(deltas[np.isfinite(deltas)])
    maximum = float(finite_deltas.max()) if finite_deltas.size else 0.0
    limit = maximum if maximum > 0 else 0.01
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    cmap = plt.get_cmap("RdBu_r").copy()
    cmap.set_bad("#d9d9d9")
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), constrained_layout=True, sharey=True)
    image = None
    ylabels = [f"{threshold_labels[value]} mm" for value in THRESHOLDS]
    for row_index, case in enumerate(("HYDRO", "LIQUID")):
        ax = axes[row_index]
        values = np.ma.masked_invalid(deltas[row_index])
        image = ax.imshow(values, cmap=cmap, norm=norm, aspect="auto")
        ax.set_title(f"{case} − OFF")
        ax.set_xticks(range(len(leads)), labels=leads)
        ax.set_yticks(range(len(THRESHOLDS)), labels=ylabels)
        ax.set_xlabel("Forecast lead (hour)")
        for threshold_index in range(len(THRESHOLDS)):
            for lead_index in range(len(leads)):
                value = deltas[row_index, threshold_index, lead_index]
                if np.isfinite(value):
                    red, green, blue, _ = cmap(norm(value))
                    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                    label, color = f"{value:+.3f}", ("white" if luminance < 0.5 else "black")
                else:
                    label, color = "NA", "#555555"
                ax.text(lead_index, threshold_index, label, ha="center", va="center", fontsize=8, color=color)
        ax.set_xticks(np.arange(-0.5, len(leads), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(THRESHOLDS), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.2)
        ax.tick_params(which="minor", bottom=False, left=False)
    axes[0].set_ylabel("Rain threshold")
    fig.colorbar(image, ax=axes, label="ΔCSI", shrink=0.9)
    fig.suptitle(f"{hourly_score_title(rows)} · positive favors candidate")
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"hourly_csi_delta_vs_off.{suffix}", dpi=180 if suffix == "png" else None)
    plt.close(fig)


def make_first_hour_precipitation_plot(
    output_dir: Path,
    pairs_npz: Path,
    window_start_utc: str = "2026-08-16T12:00:00Z",
    window_end_utc: str = "2026-08-16T13:00:00Z",
    reference_label: str = "RN1 retained reference",
) -> None:
    """Plot aligned hourly amounts, with provenance supplied by the caller."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    import numpy as np

    with np.load(pairs_npz, allow_pickle=False) as archive:
        latitude = np.asarray(archive["latitude"], dtype=float)
        longitude = np.asarray(archive["longitude"], dtype=float)
        fields = [np.asarray(archive[name], dtype=float) for name in ("reference", *CASES)]
    boundaries = [0, 0.1, 0.5, 1, 2.5, 5, 10, 20, 50, 100]
    palette = ["#d9d9d9", "#d1e5f0", "#92c5de", "#4393c3", "#2166ac",
               "#fdae61", "#f46d43", "#d73027", "#a50026"]
    cmap = ListedColormap(palette)
    cmap.set_over("#67001f")
    norm = BoundaryNorm(boundaries, cmap.N, clip=False)
    labels = (reference_label, "OFF", "HYDRO", "LIQUID")
    mean_lat = float(np.mean(latitude))

    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True, sharex=True, sharey=True)
    for ax, values, label in zip(axes.flat, fields, labels):
        points = ax.scatter(longitude, latitude, c=values, s=5, marker="s", cmap=cmap, norm=norm, linewidths=0)
        ax.set_title(label)
        ax.set_aspect(longitude_aspect_ratio(mean_lat))
        ax.grid(True, linewidth=0.4, alpha=0.35)
    for ax in axes[-1, :]:
        ax.set_xlabel("Longitude (°E)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Latitude (°N)")
    centers = [(lower + upper) / 2 for lower, upper in zip(boundaries[:-1], boundaries[1:])]
    bin_labels = ["<0.1", "0.1–0.5", "0.5–1", "1–2.5", "2.5–5", "5–10", "10–20", "20–50", "50–100"]
    colorbar = fig.colorbar(points, ax=axes, boundaries=boundaries, ticks=centers,
                            extend="max", spacing="uniform", shrink=0.9)
    colorbar.ax.set_yticklabels(bin_labels)
    colorbar.set_label("Precipitation (mm per 1-hour window; nominal <0.1 mm gray; coverage unverified)")
    window_start = parse_utc(window_start_utc, "window_start_utc")
    window_end = parse_utc(window_end_utc, "window_end_utc")
    if window_end - window_start != timedelta(hours=1):
        raise ValueError("precipitation plot window must be exactly one hour")
    fig.suptitle(
        f"Hourly precipitation · {window_start:%Y-%m-%d %H}–{window_end:%H} UTC · {reference_label}"
    )
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"first_hour_precipitation.{suffix}", dpi=180 if suffix == "png" else None)
    plt.close(fig)


def build_summary(
    rows: list[dict[str, Any]], start_time: str, input_csv: Path,
    pairs_npz: Path | None = None, complete_hourly_csv: bool = False,
) -> dict[str, Any]:
    coverage = {
        str(threshold): {
            "evaluated_leads": [lead for lead in LEADS if any(
                row["threshold_mm"] == threshold and row["lead_hour"] == lead and row["status"] == "EVALUATED"
                for row in rows
            )],
            "not_evaluated_leads": [lead for lead in LEADS if not any(
                row["threshold_mm"] == threshold and row["lead_hour"] == lead and row["status"] == "EVALUATED"
                for row in rows
            )],
        } for threshold in THRESHOLDS
    }
    return {
        "status": "SCORED_HOURLY_COUNTS_WITH_EXPLICIT_COVERAGE",
        "scope": {
            "input": str(input_csv),
            "input_sha256": hashlib.sha256(input_csv.read_bytes()).hexdigest(),
            "first_hour_pairs_npz": str(pairs_npz) if pairs_npz else None,
            "first_hour_pairs_npz_sha256": hashlib.sha256(pairs_npz.read_bytes()).hexdigest() if pairs_npz else None,
            "initial_time_utc": start_time,
            "cases": list(CASES),
            "leads_hours": list(LEADS),
            "valid_times_utc": [(parse_utc(start_time, "start_time") + timedelta(hours=lead)).strftime(UTC_FORMAT) for lead in LEADS],
            "thresholds_mm": list(THRESHOLDS),
            "archived_thresholds_mm": list(ARCHIVED_THRESHOLDS),
            "evaluated_rows": sum(row["status"] == "EVALUATED" for row in rows),
            "not_evaluated_rows": sum(row["status"] != "EVALUATED" for row in rows),
            "threshold_coverage": coverage,
            "fixed_geographic_mask_cells": 3688,
            "score_population": "hourly events only; each score is based on one case, lead, threshold, and fixed point set",
            "observation_product": "ODAM RN1 analysis product under supplied one-hour/mm convention",
            "input_evidence": (
                "supplied complete six-threshold hourly contingency-count CSV; CSV counts are validated, "
                "but their provenance is not independently verified"
                if complete_hourly_csv else
                "supplied four-threshold hourly contingency-count CSV plus optional retained aligned first-hour NPZ; "
                "CSV provenance is not independently verified"
            ),
        },
        "definitions": {
            "wet_event": "amount >= threshold_mm",
            "CSI": "H / (H + M + F); null if denominator is zero or event is not evaluated",
            "POD": "H / (H + M); null if denominator is zero",
            "FAR": "F / (H + F); null if denominator is zero",
            "frequency_bias": "(H + F) / (H + M); null if denominator is zero",
        },
        "limitations": [
            "RN1 is a processed radar/AWS analysis; a separate radar-coverage validity mask is not archived.",
            "The result scores supplied contingency counts and is not a raw-observation reanalysis or new forecast validation.",
            "One case and one six-hour period do not establish statistical generality or an isolated physical mechanism.",
            *([] if complete_hourly_csv else [
                "Thresholds 0.5 and 2.5 mm are evaluated for lead 1 only from retained aligned intermediate arrays; later leads are NOT_EVALUATED."
            ]),
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path, help="hourly contingency CSV (four thresholds by default)")
    parser.add_argument("--start-time", required=True, help="initial UTC time, e.g. 2026-08-16T12:00:00Z")
    parser.add_argument("--first-hour-pairs", type=Path, help="optional retained NPZ for lead-1 thresholds 0.5 and 2.5 mm")
    parser.add_argument("--complete-hourly-csv", action="store_true",
                        help="require all six thresholds for every case and lead in the input CSV")
    parser.add_argument("--output-dir", required=True, type=Path, help="new empty output directory")
    return parser.parse_args()


def prepare_output_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"output directory must not exist or must be empty: {path}")
    else:
        path.mkdir(parents=True)


def main() -> None:
    args = parse_args()
    if args.complete_hourly_csv and args.first_hour_pairs:
        raise SystemExit("--first-hour-pairs cannot be combined with --complete-hourly-csv")
    thresholds = THRESHOLDS if args.complete_hourly_csv else ARCHIVED_THRESHOLDS
    rows = load_and_score(args.input_csv, args.start_time, thresholds=thresholds)
    if args.first_hour_pairs:
        rows.extend(score_first_hour_pairs(args.first_hour_pairs, rows, args.start_time))
    rows = add_not_evaluated_rows(rows, args.start_time)
    try:
        prepare_output_dir(args.output_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_csv(args.output_dir / "hourly_scores.csv", rows)
    summary = build_summary(rows, args.start_time, args.input_csv, args.first_hour_pairs,
                            complete_hourly_csv=args.complete_hourly_csv)
    (args.output_dir / "scores.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    try:
        make_plots(args.output_dir, rows)
        if args.first_hour_pairs:
            start = parse_utc(args.start_time, "start_time")
            end = start + timedelta(hours=1)
            make_first_hour_precipitation_plot(
                args.output_dir,
                args.first_hour_pairs,
                window_start_utc=start.strftime(UTC_FORMAT),
                window_end_utc=end.strftime(UTC_FORMAT),
            )
    except ImportError as exc:
        raise SystemExit(f"matplotlib and numpy are required for plots: {exc}") from exc
    print(json.dumps({"output_dir": str(args.output_dir), "evaluated_rows": summary["scope"]["evaluated_rows"], "not_evaluated_rows": summary["scope"]["not_evaluated_rows"], "status": summary["status"]}))


if __name__ == "__main__":
    main()
