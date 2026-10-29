#!/usr/bin/env python3
"""Extract selected initial thermodynamic fields from historical CP02 inputs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from netCDF4 import Dataset


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/inputs"
MANIFEST_PATH = EVIDENCE / "copy_manifest.json"
SELECTED_PATH = EVIDENCE / "selected_initial_fields.csv"
OUTPUT = Path(__file__).with_name("initial_thermo.csv")
RECEIPT = Path(__file__).with_name("initial_thermo_receipt.json")
FIELD_NAMES = ("QVAPOR", "QCLOUD", "QRAIN", "T", "THM", "P", "PB")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_entry(manifest: dict[str, Any], arm: str, filename: str) -> dict[str, Any]:
    matches = [
        item
        for item in manifest["arms"][arm]["copy_files"]
        if item["destination_name"] == filename
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {filename} entry for {arm}, got {len(matches)}")
    return matches[0]


def read_field(dataset: Dataset, name: str, k0: int, j0: int, i0: int) -> float:
    variable = dataset[name]
    if len(variable.shape) != 4 or variable.shape[0] != 1:
        raise ValueError(f"unexpected {name} shape: {variable.shape}")
    return float(variable[0, k0, j0, i0])


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    selected = list(csv.DictReader(SELECTED_PATH.open(encoding="utf-8", newline="")))
    source_rows: dict[str, dict[str, Path]] = {}
    hashes_before: dict[str, dict[str, str]] = {}
    rows: list[dict[str, str | float | int]] = []
    t00_values: dict[str, float] = {}

    for arm in ("OFF", "HYDRO", "LIQUID"):
        input_entry = copy_entry(manifest, arm, "wrfinput_d01")
        source = Path(input_entry["source_path"])
        observed_hash = sha256(source)
        if observed_hash != input_entry["sha256"]:
            raise ValueError(f"{arm} wrfinput hash differs from PR126 copy manifest")
        source_rows[arm] = {"wrfinput_d01": source}
        hashes_before[arm] = {"wrfinput_d01": observed_hash}

        arm_rows = [row for row in selected if row["arm"] == arm]
        if len(arm_rows) != 624:
            raise ValueError(f"expected 624 selected rows for {arm}, got {len(arm_rows)}")

        with Dataset(source) as dataset:
            if tuple(dataset.variables[name].shape for name in FIELD_NAMES) != ((1, 39, 282, 234),) * len(FIELD_NAMES):
                raise ValueError(f"unexpected selected-field dimensions for {arm}")
            t00_values[arm] = float(dataset["T00"][0])
            for selected_row in arm_rows:
                i0 = int(selected_row["native_i0"])
                j0 = int(selected_row["native_j0"])
                k0 = int(selected_row["level_k0"])
                field_values = {
                    name: read_field(dataset, name, k0, j0, i0)
                    for name in FIELD_NAMES
                }
                for field in ("QVAPOR", "QCLOUD", "QRAIN"):
                    expected = float(selected_row[field])
                    if field_values[field] != expected:
                        raise ValueError(f"{arm} {selected_row['point_id']} {field} source mismatch")
                rows.append(
                    {
                        "arm": arm,
                        "point_id": selected_row["point_id"],
                        "role": selected_row["role"],
                        "corner": selected_row["corner"],
                        "weight": float(selected_row["weight"]),
                        "i_wrf_1based": i0 + 1,
                        "j_wrf_1based": j0 + 1,
                        "k_wrf_1based": k0 + 1,
                        **field_values,
                        "T00_K_metadata_only": t00_values[arm],
                    }
                )

    fieldnames = [
        "arm",
        "point_id",
        "role",
        "corner",
        "weight",
        "i_wrf_1based",
        "j_wrf_1based",
        "k_wrf_1based",
        *FIELD_NAMES,
        "T00_K_metadata_only",
    ]
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    hashes_after = {
        arm: {name: sha256(path) for name, path in files.items()}
        for arm, files in source_rows.items()
    }
    if hashes_after != hashes_before:
        raise ValueError("a bound source file changed during extraction")

    source_hashes = {
        str(path): {"sha256": hashes_before[arm][name], "size_bytes": path.stat().st_size}
        for arm, files in source_rows.items()
        for name, path in files.items()
    }
    receipt = {
        "purpose": "Read-only selected initial fields for historical CP02 thermodynamic trace",
        "extractor": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "source_evidence": {
            "copy_manifest": {"path": str(MANIFEST_PATH), "sha256": sha256(MANIFEST_PATH)},
            "selected_initial_fields": {"path": str(SELECTED_PATH), "sha256": sha256(SELECTED_PATH)},
            "wrfinput_files_before_after": source_hashes,
        },
        "extraction": {
            "output": str(OUTPUT),
            "output_sha256": sha256(OUTPUT),
            "row_count": len(rows),
            "rows_per_arm": {arm: sum(row["arm"] == arm for row in rows) for arm in ("OFF", "HYDRO", "LIQUID")},
            "fields": list(FIELD_NAMES),
            "T00_K": t00_values,
            "T00_use": "Recorded metadata/context only; not added to T or THM.",
        },
        "method": {
            "netCDF4": __import__("netCDF4").__version__,
            "coordinate_basis": "selected_initial_fields.csv zero-based native indices converted to 1-based WRF coordinates",
            "meaning_limit": "Initial input arrays only; does not prove driver/KDM6 consumed them unchanged.",
        },
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
