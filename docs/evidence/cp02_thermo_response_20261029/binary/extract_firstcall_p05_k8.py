#!/usr/bin/env python3
"""Select the archived PR126 public KDM6 call endpoints for P05 corner 11 k8."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PR126 = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
PROFILES = PR126 / "analysis/selected_profiles.csv"
CALLS = PR126 / "analysis/per_arm_call.csv"
OUTPUT = Path(__file__).with_name("p05_k8_public_kdm6.csv")
RECEIPT = Path(__file__).with_name("p05_k8_public_kdm6_receipt.json")
FIELDS = (
    "arm", "rank", "call_ordinal", "endpoint", "label", "i", "j", "k",
    "q", "qc", "qr", "qi", "qs", "qg", "th", "den", "p", "pii",
    "delz", "nn", "nc", "ni", "nr", "bg", "rain", "rainncv", "snow",
    "snowncv", "graupel", "graupelncv",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    profile_rows = list(csv.DictReader(PROFILES.open(encoding="utf-8", newline="")))
    call_rows = list(csv.DictReader(CALLS.open(encoding="utf-8", newline="")))
    selected = [
        row
        for row in profile_rows
        if row["label"] == "P05_11"
        and row["k"] == "8"
        and row["endpoint"] in {"entry", "return"}
    ]
    selected.sort(key=lambda row: (row["arm"], int(row["call_ordinal"]), row["endpoint"]))
    expected_keys = {
        (arm, ordinal, endpoint)
        for arm in ("OFF", "HYDRO", "LIQUID")
        for ordinal in ("1", "2")
        for endpoint in ("entry", "return")
    }
    found_keys = {(row["arm"], row["call_ordinal"], row["endpoint"]) for row in selected}
    if found_keys != expected_keys or len(selected) != 12:
        raise ValueError("expected one P05_11 k8 row for each arm/call/endpoint")

    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({name: row[name] for name in FIELDS} for row in selected)

    call_metadata = [
        {name: row[name] for name in (
            "arm", "call_ordinal", "observed_itimestep", "observed_dt",
            "diagflag", "do_radar_ref", "has_reqc", "has_reqi", "has_reqs",
        )}
        for row in call_rows
    ]
    receipt = {
        "purpose": "Hash-bound subset of the PR126 selected public KDM6 endpoint values",
        "extractor": {"path": str(Path(__file__)), "sha256": sha256(Path(__file__))},
        "source_files": {
            str(path): {"sha256": sha256(path), "size_bytes": path.stat().st_size}
            for path in (PROFILES, CALLS)
        },
        "output": {"path": str(OUTPUT), "sha256": sha256(OUTPUT), "row_count": len(selected)},
        "selection": {
            "point": "P05_11",
            "coordinates_wrf_1based": {"i": 164, "j": 71, "k": 8},
            "arms": ["OFF", "HYDRO", "LIQUID"],
            "call_ordinals": [1, 2],
            "endpoints": ["entry", "return"],
            "public_call_metadata": call_metadata,
        },
        "meaning_limit": "Whole public KDM6 call PRE/POST values; not inner KDM62D state or process rates.",
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
