#!/usr/bin/env python3
"""Build and compare an isolated Cloud-BAL SHADOW WPS candidate.

The operational LAPS file is copied byte-for-byte.  Only hydrometeor cells
changed by the real-data Cloud-BAL column stage are replaced in the candidate.
All other fields, including wind, remain the operational values.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from compare_baseline import _records, read_wps
from prepare_operational_comparison import prepare


HYDROMETEORS = {
    "QC": ("background_cloud_water", "candidate_cloud_water"),
    "QI": ("background_cloud_ice", "candidate_cloud_ice"),
    "QR": ("background_rain", "candidate_rain"),
    "QS": ("background_snow", "candidate_snow"),
    "QG": ("background_graupel", "candidate_graupel"),
}
SHADOW_CONFIGURATION = "radar-only-shadow-ifx-2026-v3"


@dataclass(frozen=True)
class CasePaths:
    case_id: str
    original: Path
    live_original: Path
    shadow: Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shadow_generation(root: Path, source_commit: str) -> tuple[dict[str, dict], str]:
    manifest_path = root.resolve(strict=True) / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValueError("unsupported SHADOW generation manifest")
    if manifest.get("source_commit") != source_commit:
        raise ValueError("SHADOW generation source commit differs from --source-commit")
    if manifest.get("configuration") != SHADOW_CONFIGURATION:
        raise ValueError("SHADOW generation configuration is not the approved profile")
    products = manifest.get("products")
    if not isinstance(products, list):
        raise ValueError("SHADOW generation product inventory is invalid")
    by_path = {item.get("path"): item for item in products if isinstance(item, dict)}
    if len(by_path) != len(products):
        raise ValueError("SHADOW generation product inventory has duplicate paths")
    return by_path, sha256(manifest_path)


def write_record(stream, endian: str, payload: bytes) -> None:
    marker = struct.pack(endian + "i", len(payload))
    stream.write(marker)
    stream.write(payload)
    stream.write(marker)


def wps_records(path: Path) -> list[tuple[str, bytes]]:
    return list(_records(path))


def build_candidate(original: Path, shadow: Path, output: Path) -> dict:
    records = wps_records(original)
    if len(records) % 5:
        raise ValueError(f"incomplete WPS record group: {original}")

    modified_by_field: dict[str, int] = {field: 0 for field in HYDROMETEORS}
    modified_by_level: dict[str, int] = {}
    with Dataset(shadow) as dataset:
        if getattr(dataset, "result_authority", "") != "DIAGNOSTIC_PROPOSAL_ONLY":
            raise ValueError(f"unexpected SHADOW authority: {shadow}")
        if int(getattr(dataset, "operational_state_changed", 1)) != 0:
            raise ValueError(f"SHADOW diagnostic claims an operational change: {shadow}")

        pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
        pressure_index = {int(round(value)): index for index, value in enumerate(pressure)}
        above_ground = np.asarray(dataset.variables["above_ground"][:], dtype=bool)
        column_changed = np.asarray(dataset.variables["column_changed"][:], dtype=bool)
        radar_valid = np.asarray(dataset.variables["radar_valid"][:], dtype=bool)
        hydro_support = np.asarray(dataset.variables["hydro_support"][:], dtype=bool)
        replacement_union = np.zeros_like(column_changed)
        field_values = {
            field: (
                np.asarray(dataset.variables[background][:], dtype=np.float64),
                np.asarray(dataset.variables[candidate][:], dtype=np.float64),
            )
            for field, (background, candidate) in HYDROMETEORS.items()
        }

        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("wb") as stream:
            for offset in range(0, len(records), 5):
                group = records[offset : offset + 5]
                endian = group[0][0]
                if any(item[0] != endian for item in group):
                    raise ValueError("mixed-endian WPS record group")
                metadata = group[1][1]
                field = metadata[60:69].decode("ascii", "replace").strip()
                level = int(round(struct.unpack(endian + "f", metadata[140:144])[0]))
                nx, ny = struct.unpack(endian + "ii", metadata[144:152])
                slab = group[4][1]

                if field in HYDROMETEORS and level in pressure_index:
                    k = pressure_index[level]
                    background, candidate = field_values[field]
                    replacement = (
                        above_ground[k]
                        & column_changed[k]
                        & np.isfinite(background[k])
                        & np.isfinite(candidate[k])
                        & (candidate[k] != background[k])
                    )
                    if replacement.shape != (ny, nx):
                        raise ValueError(
                            f"grid mismatch for {field} at {level} Pa: "
                            f"{replacement.shape} != {(ny, nx)}"
                        )
                    values = np.frombuffer(slab, dtype=endian + "f4").copy().reshape(ny, nx)
                    if np.any(candidate[k][replacement] < 0.0):
                        raise ValueError(f"negative candidate {field} at {level} Pa")
                    values[replacement] = candidate[k][replacement].astype(np.float32)
                    slab = values.astype(endian + "f4", copy=False).tobytes(order="C")
                    count = int(np.count_nonzero(replacement))
                    replacement_union[k] |= replacement
                    modified_by_field[field] += count
                    modified_by_level[str(level)] = modified_by_level.get(str(level), 0) + count

                for record_index, (_, payload) in enumerate(group):
                    write_record(stream, endian, slab if record_index == 4 else payload)
        temporary.replace(output)

        outside_support = replacement_union & ~hydro_support
        if np.any(outside_support):
            raise ValueError("hydrometeor replacement escaped Cloud-BAL support")
        flux_names = (
            "flux_input", "flux_deposited", "flux_suspended", "flux_boundary_exit",
            "flux_terrain_intercept", "flux_observation_blocked",
            "flux_no_echo_blocked",
            "flux_microphysical_loss", "flux_ledger_error",
        )
        flux = {name: float(getattr(dataset, name)) for name in flux_names}

    unique_modified = int(np.count_nonzero(replacement_union))
    direct_radar = int(np.count_nonzero(replacement_union & radar_valid))
    return {
        "modified_by_field": modified_by_field,
        "modified_by_level": modified_by_level,
        "modified_cells": sum(modified_by_field.values()),
        "unique_modified_cells": unique_modified,
        "direct_radar_modified_cells": direct_radar,
        "transported_modified_cells": unique_modified - direct_radar,
        "outside_hydrometeor_support_cells": 0,
        "flux_ledger": flux,
        "flux_relative_closure_error": abs(flux["flux_ledger_error"]) / max(
            abs(flux["flux_input"]), 1.0
        ),
    }


def valid(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (np.abs(values) < 1.0e20)


def compare_products(original: Path, candidate: Path) -> tuple[list[dict], dict]:
    old = read_wps(original)
    new = read_wps(candidate)
    if set(old) != set(new):
        raise ValueError("candidate WPS field inventory differs from the operational original")

    rows: list[dict] = []
    changed_fields: set[str] = set()
    for key in sorted(old, key=lambda item: (item[0], item[1], item[2])):
        field, level, hdate = key
        old_units, old_shape, old_values, old_metadata = old[key]
        new_units, new_shape, new_values, new_metadata = new[key]
        if (old_units, old_shape, old_metadata) != (new_units, new_shape, new_metadata):
            raise ValueError(f"metadata changed for {key}")
        common = valid(old_values) & valid(new_values)
        delta = new_values[common] - old_values[common]
        changed = int(np.count_nonzero(delta))
        if changed:
            changed_fields.add(field)
        if field in HYDROMETEORS:
            rows.append(
                {
                    "field": field,
                    "level_pa": int(round(level)),
                    "valid_time": hdate,
                    "valid_cells": int(np.count_nonzero(common)),
                    "changed_cells": changed,
                    "bias": float(np.mean(delta)) if delta.size else None,
                    "rms_delta": float(np.sqrt(np.mean(delta * delta))) if delta.size else None,
                    "max_abs_delta": float(np.max(np.abs(delta))) if delta.size else None,
                }
            )

    unauthorized = changed_fields - set(HYDROMETEORS)
    if unauthorized:
        raise ValueError(f"unauthorized WPS fields changed: {sorted(unauthorized)}")
    return rows, {"changed_fields": sorted(changed_fields)}


def arrays_at_level(path: Path, level: int) -> dict[str, np.ndarray]:
    fields = read_wps(path)
    arrays = {}
    for (field, record_level, _), (_, (nx, ny), slab, _) in fields.items():
        if int(round(record_level)) == level:
            arrays[field] = slab.reshape(ny, nx)
    return arrays


def finite_image(values: np.ndarray) -> np.ndarray:
    return np.where(valid(values), values, np.nan)


def plot_case(
    case_id: str,
    original: Path,
    candidate: Path,
    shadow: Path,
    level: int,
    output: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    old = arrays_at_level(original, level)
    new = arrays_at_level(candidate, level)
    old_hydro = sum(finite_image(old[field]) for field in HYDROMETEORS) * 1000.0
    new_hydro = sum(finite_image(new[field]) for field in HYDROMETEORS) * 1000.0
    old_speed = np.hypot(finite_image(old["UU"]), finite_image(old["VV"]))
    new_speed = np.hypot(finite_image(new["UU"]), finite_image(new["VV"]))

    with Dataset(shadow) as dataset:
        pressure = np.asarray(dataset.variables["pressure"][:], dtype=np.float64)
        k = int(np.argmin(np.abs(pressure - level)))
        lon = np.asarray(dataset.variables["longitude"][:], dtype=np.float64)
        lat = np.asarray(dataset.variables["latitude"][:], dtype=np.float64)
        radar = np.asarray(dataset.variables["radar_dbz"][k], dtype=np.float64)
        radar_valid = np.asarray(dataset.variables["radar_valid"][k], dtype=bool)
        changed = np.asarray(dataset.variables["column_changed"][k], dtype=bool)

    hydro_limit = float(np.nanpercentile(np.concatenate([old_hydro.ravel(), new_hydro.ravel()]), 99.5))
    hydro_limit = max(hydro_limit, 0.01)
    speed_limit = max(float(np.nanpercentile(old_speed, 99.5)), 1.0)
    hydro_delta = new_hydro - old_hydro
    delta_limit = max(float(np.nanpercentile(np.abs(hydro_delta), 99.5)), 0.001)

    fig, axes = plt.subplots(2, 4, figsize=(19, 9), constrained_layout=True)
    common = {"shading": "auto", "rasterized": True}
    panels = [
        (old_hydro, "Operational total hydrometeor", "viridis", 0.0, hydro_limit, None),
        (new_hydro, "SHADOW candidate total hydrometeor", "viridis", 0.0, hydro_limit, None),
        (hydro_delta, "Candidate - operational", "RdBu_r", None, None,
         TwoSlopeNorm(vmin=-delta_limit, vcenter=0.0, vmax=delta_limit)),
        (np.where(radar_valid, radar, np.nan), "S-band radar reflectivity", "turbo", 5.0, 65.0, None),
        (old_speed, "Operational wind speed", "magma", 0.0, speed_limit, None),
        (new_speed, "Candidate wind speed (copied)", "magma", 0.0, speed_limit, None),
        (new_speed - old_speed, "Candidate - operational wind", "RdBu_r", -0.01, 0.01, None),
        (changed.astype(float), "Cloud-BAL column-change mask", "Greys", 0.0, 1.0, None),
    ]
    units = ["g kg$^{-1}$", "g kg$^{-1}$", "g kg$^{-1}$", "dBZ",
             "m s$^{-1}$", "m s$^{-1}$", "m s$^{-1}$", "0/1"]
    for axis, panel, unit in zip(axes.ravel(), panels, units):
        values, title, cmap, vmin, vmax, norm = panel
        kwargs = {"cmap": cmap, **common}
        if norm is None:
            kwargs.update(vmin=vmin, vmax=vmax)
        else:
            kwargs["norm"] = norm
        image = axis.pcolormesh(lon, lat, values, **kwargs)
        axis.set_title(title)
        axis.set_xlabel("longitude")
        axis.set_ylabel("latitude")
        fig.colorbar(image, ax=axis, shrink=0.82, label=unit)
    fig.suptitle(
        f"{case_id} at {level / 100:.0f} hPa — isolated operational/SHADOW comparison\n"
        "Wind is unchanged: dynamic balance is not authorized",
        fontsize=14,
    )
    fig.savefig(output, dpi=150)
    plt.close(fig)


def case_paths(args, hour: int) -> CasePaths:
    case_id = f"20260816T{hour:02d}0000Z"
    filename = f"LAPS:2026-08-16_{hour:02d}:00"
    return CasePaths(
        case_id=case_id,
        original=args.original_root / f"20260816{hour:02d}" / filename,
        live_original=args.live_root / f"20260816{hour:02d}" / filename,
        shadow=args.shadow_root / f"{case_id}.nc",
    )


def artifact(root: Path, role: str, origin: str, path: Path) -> dict:
    result = {
        "evidence_role": role,
        "origin": origin,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "wind_coordinate": "GRID_RELATIVE",
    }
    if role == "REAL_OPERATIONAL_ORIGINAL":
        attestation = path.parent / "SHA256SUMS"
        result["attestation"] = {
            "format": "SHA256SUMS",
            "path": attestation.relative_to(root).as_posix(),
            "sha256": sha256(attestation),
        }
    elif role == "SHADOW_CANDIDATE":
        attestation = path.parent / "MANIFEST.json"
        result["attestation"] = {
            "format": "LOCAL_DIAGNOSTIC_MANIFEST",
            "path": attestation.relative_to(root).as_posix(),
            "sha256": sha256(attestation),
        }
    return result


def seal_case(root: Path, case_id: str, source_commit: str, original: Path,
              candidate: Path, operational: Path, hour: int) -> dict:
    (original.parent / "SHA256SUMS").write_text(
        f"{sha256(original)}  {original.name}\n", encoding="utf-8"
    )
    transaction_id = f"cloud-bal-{case_id.lower()}-{source_commit[:12]}"
    generation = {
        "schema": 1,
        "transaction_id": transaction_id,
        "source_commit": source_commit,
        "configuration": SHADOW_CONFIGURATION,
        "products": [{
            "path": candidate.name,
            "bytes": candidate.stat().st_size,
            "sha256": sha256(candidate),
        }],
    }
    (candidate.parent / "MANIFEST.json").write_text(
        json.dumps(generation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (candidate.parent / "COMMITTED").write_text(transaction_id + "\n", encoding="ascii")
    valid_time = f"2026-08-16T{hour:02d}:00:00Z"
    return {
        "pair_id": f"laps-{case_id}",
        "product_kind": "LAPS",
        "format": "WPS_INTERMEDIATE",
        "valid_time": valid_time,
        "original": artifact(
            root, "REAL_OPERATIONAL_ORIGINAL", "ARCHIVED_OPERATIONAL_KLAPS", original
        ),
        "candidate": artifact(
            root, "SHADOW_CANDIDATE", "HYBRID_DIAGNOSTIC_HYDROMETEOR_REPLACEMENT", candidate
        ),
        "operational_unchanged": artifact(
            root, "OPERATIONAL_UNCHANGED", "LIVE_OPERATIONAL_KLAPS_UNCHANGED",
            operational,
        ),
        "plot_fields": [
            {
                "plot_id": "rain-950hpa", "field": "QR", "level": 95000.0,
                "scale": {"value_min": 0.0, "value_max": 0.02,
                          "delta_abs_max": 0.02},
            },
            {
                "plot_id": "snow-950hpa", "field": "QS", "level": 95000.0,
                "scale": {"value_min": 0.0, "value_max": 0.02,
                          "delta_abs_max": 0.02},
            },
            {
                "plot_id": "u-wind-950hpa", "field": "UU", "level": 95000.0,
                "scale": {"value_min": -60.0, "value_max": 60.0,
                          "delta_abs_max": 1.0},
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--live-root", required=True, type=Path)
    parser.add_argument("--shadow-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--hours", nargs="+", type=int, default=[12, 13, 14, 15])
    args = parser.parse_args()

    if args.output.exists():
        print(f"output already exists: {args.output}", file=sys.stderr)
        return 2
    if len(args.source_commit) != 40 or any(
        character not in "0123456789abcdef" for character in args.source_commit
    ):
        print("--source-commit must be a 40-character lowercase SHA", file=sys.stderr)
        return 2
    shadow_products, shadow_manifest_sha = shadow_generation(
        args.shadow_root, args.source_commit
    )
    args.output.mkdir(parents=True)

    report = {
        "schema_version": 1,
        "comparison_authority": "DIAGNOSTIC_FIELD_LEVEL_ONLY",
        "algorithm_comparison_status": "NOT_RUN_FULL_END_TO_END",
        "dynamic_balance_authorized": False,
        "operational_original_modified": False,
        "candidate_construction": (
            "operational WPS copy with QC/QI/QR/QS/QG replaced only where the "
            "real-data Cloud-BAL column stage changed that hydrometeor"
        ),
        "mass_basis_caveat": (
            "operational WPS declares kg kg-1; Cloud-BAL declares kg kg-1 dryair; "
            "the legacy producer does not fully prove an identical denominator"
        ),
        "source_commit": args.source_commit,
        "shadow_generation_manifest_sha256": shadow_manifest_sha,
        "cases": [],
    }
    all_rows: list[dict] = []
    contract_pairs: list[dict] = []

    for hour in args.hours:
        paths = case_paths(args, hour)
        case_report = {"case_id": paths.case_id}
        missing = [
            label
            for label, path in (
                ("operational_original", paths.original),
                ("live_operational_original", paths.live_original),
                ("shadow_diagnostic", paths.shadow),
            )
            if not path.is_file()
        ]
        if missing:
            case_report.update(status="NOT_AVAILABLE", missing=missing)
            report["cases"].append(case_report)
            continue

        shadow_entry = shadow_products.get(paths.shadow.name)
        shadow_sha = sha256(paths.shadow)
        if (not isinstance(shadow_entry, dict)
                or shadow_entry.get("sha256") != shadow_sha
                or shadow_entry.get("bytes") != paths.shadow.stat().st_size):
            raise ValueError(f"SHADOW diagnostic is not generation-bound: {paths.case_id}")
        expected_epoch = calendar.timegm((2026, 8, 16, hour, 0, 0))
        with Dataset(paths.shadow) as shadow_dataset:
            if int(getattr(shadow_dataset, "valid_time_epoch", -1)) != expected_epoch:
                raise ValueError(f"SHADOW valid time differs from case: {paths.case_id}")

        original_sha = sha256(paths.original)
        live_sha = sha256(paths.live_original)
        if original_sha != live_sha:
            raise ValueError(f"archived/live operational mismatch for {paths.case_id}")

        case_root = args.output / paths.case_id
        original_dir = case_root / "original"
        candidate_dir = case_root / "candidate"
        operational_dir = case_root / "operational_unchanged"
        figures_dir = case_root / "figures"
        original_dir.mkdir(parents=True)
        candidate_dir.mkdir()
        operational_dir.mkdir()
        figures_dir.mkdir()
        isolated_original = original_dir / paths.original.name
        candidate = candidate_dir / paths.original.name
        operational = operational_dir / paths.original.name
        shutil.copy2(paths.original, isolated_original)
        shutil.copy2(paths.original, candidate)
        shutil.copy2(paths.live_original, operational)
        if isolated_original.stat().st_ino == paths.original.stat().st_ino:
            raise ValueError("operational original was not independently copied")
        if (sha256(isolated_original) != original_sha
                or sha256(candidate) != original_sha
                or sha256(operational) != original_sha):
            raise ValueError("isolated operational copy failed checksum validation")

        build = build_candidate(isolated_original, paths.shadow, candidate)
        rows, comparison = compare_products(isolated_original, candidate)
        level = max(
            (int(item) for item in build["modified_by_level"]),
            key=lambda item: build["modified_by_level"][str(item)],
        )
        figure = figures_dir / f"{paths.case_id}_{level // 100}hPa.png"
        plot_case(paths.case_id, isolated_original, candidate, paths.shadow, level, figure)
        contract_pairs.append(seal_case(
            args.output, paths.case_id, args.source_commit, isolated_original,
            candidate, operational, hour,
        ))

        for row in rows:
            row["case_id"] = paths.case_id
            all_rows.append(row)
        case_report.update(
            status="COMPLETED_DIAGNOSTIC",
            operational_original=str(paths.original.resolve()),
            isolated_original=str(isolated_original.resolve()),
            shadow_diagnostic=str(paths.shadow.resolve()),
            shadow_diagnostic_sha256=shadow_sha,
            candidate=str(candidate.resolve()),
            operational_unchanged=str(operational.resolve()),
            figure=str(figure.resolve()),
            operational_sha256=original_sha,
            isolated_original_sha256=sha256(isolated_original),
            candidate_sha256=sha256(candidate),
            selected_level_pa=level,
            **build,
            **comparison,
        )
        report["cases"].append(case_report)

    if not any(case["status"] == "COMPLETED_DIAGNOSTIC" for case in report["cases"]):
        raise ValueError("no comparison case was available")
    requested_cases_complete = all(
        case["status"] == "COMPLETED_DIAGNOSTIC" for case in report["cases"]
    )

    with (args.output / "field_statistics.tsv").open("w", newline="") as stream:
        columns = [
            "case_id", "field", "level_pa", "valid_time", "valid_cells",
            "changed_cells", "bias", "rms_delta", "max_abs_delta",
        ]
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(all_rows)
    contract_manifest = args.output / "comparison-manifest.json"
    contract_manifest.write_text(json.dumps({
        "schema_version": 1,
        "comparison_id": f"operational-shadow-{args.source_commit[:12]}",
        "pairs": contract_pairs,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readiness = prepare(
        contract_manifest, args.output, args.output / "contract_evidence"
    )
    if readiness["status"] != "READY":
        raise ValueError(
            "operational comparison contract failed: "
            + "; ".join(readiness["failures"])
        )
    report["requested_case_set_complete"] = requested_cases_complete
    report["structural_comparison_readiness"] = {
        "status": (
            readiness["status"] if requested_cases_complete
            else "NOT_READY_REQUESTED_CASES_INCOMPLETE"
        ),
        "available_pairs_status": readiness["status"],
        "algorithm_comparison_status": readiness["algorithm_comparison_status"],
        "readiness_path": str(
            (args.output / "contract_evidence" / "READINESS.json").resolve()
        ),
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    comparison_status = (
        "COMPLETED_DIAGNOSTIC" if requested_cases_complete
        else "INCOMPLETE_DIAGNOSTIC"
    )
    (args.output / "STATUS.txt").write_text(
        f"comparison={comparison_status}\n"
        "full_end_to_end=NO\n"
        "dynamic_balance_authorized=NO\n"
        "operational_original_modified=NO\n"
        "science_promotion=NO\n"
    )
    print(args.output.resolve())
    return 0 if requested_cases_complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
