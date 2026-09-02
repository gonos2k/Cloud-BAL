#!/usr/bin/env python3
"""Contract tests for operational-original/SHADOW comparison preparation."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path

import netCDF4
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from prepare_operational_comparison import (  # noqa: E402
    SHADOW_CONFIGURATION,
    prepare,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(payload: bytes) -> bytes:
    marker = struct.pack("<i", len(payload))
    return marker + payload + marker


def wps_field(
    field: str,
    units: str,
    level: float,
    values: list[float],
    *,
    valid_time: str = "2026-08-16_13:00:00",
    projection: bytes = b"projection-v1",
    wind: int = 1,
    source: str = "KLAPS",
) -> bytes:
    metadata = bytearray(156)
    metadata[0:24] = valid_time.encode("ascii").ljust(24)
    metadata[24:28] = struct.pack("<f", 0.0)
    metadata[28:60] = source.encode("ascii").ljust(32)
    metadata[60:69] = field.encode("ascii").ljust(9)
    metadata[69:94] = units.encode("ascii").ljust(25)
    metadata[140:144] = struct.pack("<f", level)
    metadata[144:156] = struct.pack("<iii", 2, 2, 1)
    slab = np.asarray(values, dtype="<f4").tobytes()
    return b"".join(
        (
            record(struct.pack("<i", 5)),
            record(bytes(metadata)),
            record(projection),
            record(struct.pack("<i", wind)),
            record(slab),
        )
    )


def write_wps(
    path: Path,
    *,
    candidate: bool = False,
    omit_rh: bool = False,
    source: str = "KLAPS",
) -> None:
    tt = [281.0, 282.0, 283.0, 284.0]
    if candidate:
        tt = [282.0, 283.0, 284.0, 285.0]
    fields = {
        "HGT": ("m", [5000.0] * 4),
        "PMSL": ("Pa", [101000.0] * 4),
        "PSFC": ("Pa", [100000.0] * 4),
        "QC": ("kg kg-1", [0.0] * 4),
        "QG": ("kg kg-1", [0.0] * 4),
        "QI": ("kg kg-1", [0.0] * 4),
        "QR": ("kg kg-1", [0.0] * 4),
        "QS": ("kg kg-1", [0.0] * 4),
        "RH": ("%", [50.0, 60.0, 70.0, 80.0]),
        "SKINTEMP": ("K", [290.0] * 4),
        "TT": ("K", tt),
        "UU": ("m s-1", [5.0] * 4),
        "VV": ("m s-1", [2.0] * 4),
    }
    if omit_rh:
        fields.pop("RH")
    payload = b"".join(
        wps_field(field, units, 50000.0, values, source=source)
        for field, (units, values) in sorted(fields.items())
    )
    path.write_bytes(payload)


def met_em(path: Path, *, candidate: bool = False, diagnostic: bool = False) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("Time", None)
        dataset.createDimension("DateStrLen", 19)
        dataset.createDimension("num_metgrid_levels", 2)
        dataset.createDimension("south_north", 2)
        dataset.createDimension("west_east", 3)
        for key, value in {
            "GRIDTYPE": "C",
            "MAP_PROJ": 1,
            "DX": 5000.0,
            "DY": 5000.0,
            "CEN_LAT": 38.0,
            "CEN_LON": 126.0,
            "TRUELAT1": 30.0,
            "TRUELAT2": 60.0,
            "STAND_LON": 126.0,
            "POLE_LAT": 90.0,
            "POLE_LON": 0.0,
        }.items():
            setattr(dataset, key, value)
        if diagnostic:
            dataset.result_authority = "DIAGNOSTIC_PROPOSAL_ONLY"
        times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[0, :] = np.asarray(list("2026-08-16_13:00:00"), dtype="S1")
        three_dimensional = {
            "PRES": "Pa",
            "GHT": "m",
            "QC": "kg kg-1",
            "QG": "kg kg-1",
            "QI": "kg kg-1",
            "QR": "kg kg-1",
            "QS": "kg kg-1",
            "RH": "%",
            "TT": "K",
            "UU": "m s-1",
            "VV": "m s-1",
        }
        base = np.arange(12, dtype=np.float32).reshape(1, 2, 2, 3)
        for name, units in three_dimensional.items():
            field = dataset.createVariable(
                name,
                "f4",
                ("Time", "num_metgrid_levels", "south_north", "west_east"),
            )
            field.units = units
            field.stagger = "U" if name == "UU" else "V" if name == "VV" else "M"
            values = base + (270.0 if name == "TT" else 1.0)
            if candidate and name == "TT":
                values = values + 0.5
            field[:] = values
        for name, units, value in (
            ("PMSL", "Pa", 101000.0),
            ("PSFC", "Pa", 100000.0),
            ("SKINTEMP", "K", 290.0),
        ):
            field = dataset.createVariable(
                name, "f4", ("Time", "south_north", "west_east")
            )
            field.units = units
            field.stagger = "M"
            field[:] = value


def seal_original(path: Path) -> None:
    (path.parent / "SHA256SUMS").write_text(
        f"{sha256(path)}  {path.name}\n", encoding="utf-8"
    )


def seal_candidate(path: Path) -> None:
    transaction_id = "fixture-shadow-generation"
    manifest = {
        "schema": 1,
        "transaction_id": transaction_id,
        "source_commit": "1" * 40,
        "configuration": SHADOW_CONFIGURATION,
        "products": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        ],
    }
    (path.parent / "MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    (path.parent / "COMMITTED").write_text(transaction_id + "\n", encoding="ascii")


def make_wps_triad(
    root: Path,
    name: str,
    *,
    omit_rh: bool = False,
    candidate_source: str = "KLAPS",
) -> tuple[Path, Path, Path]:
    scenario = root / name
    original = scenario / "archive" / "LAPS:2026-08-16_13:00"
    candidate = scenario / "shadow" / "LAPS:2026-08-16_13:00"
    operational = scenario / "live" / "LAPS:2026-08-16_13:00"
    for path in (original, candidate, operational):
        path.parent.mkdir(parents=True, exist_ok=True)
    write_wps(original)
    write_wps(
        candidate, candidate=True, omit_rh=omit_rh, source=candidate_source
    )
    write_wps(operational)
    seal_original(original)
    seal_candidate(candidate)
    return original, candidate, operational


def make_netcdf_triad(
    root: Path, name: str, *, diagnostic: bool = False
) -> tuple[Path, Path, Path]:
    scenario = root / name
    filename = "met_em.d01.2026-08-16_13:00:00.nc"
    original = scenario / "archive" / filename
    candidate = scenario / "shadow" / filename
    operational = scenario / "live" / filename
    for path in (original, candidate, operational):
        path.parent.mkdir(parents=True, exist_ok=True)
    met_em(original)
    met_em(candidate, candidate=True, diagnostic=diagnostic)
    met_em(operational)
    seal_original(original)
    seal_candidate(candidate)
    return original, candidate, operational


def artifact(role: str, origin: str, path: Path, root: Path) -> dict[str, object]:
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
            "format": "CLOUD_BAL_GENERATION",
            "path": attestation.relative_to(root).as_posix(),
            "sha256": sha256(attestation),
        }
    return result


def pair(root: Path, paths: tuple[Path, Path, Path], *, product: str = "LAPS") -> dict:
    original, candidate, operational = paths
    result = {
        "pair_id": f"{product.lower()}-20260816T130000Z",
        "product_kind": product,
        "format": "WPS_INTERMEDIATE" if product != "MET_EM" else "MET_EM_NETCDF",
        "valid_time": "2026-08-16T13:00:00Z",
        "original": artifact(
            "REAL_OPERATIONAL_ORIGINAL", "ARCHIVED_OPERATIONAL_KLAPS", original, root
        ),
        "candidate": artifact(
            "SHADOW_CANDIDATE", "FULL_SHADOW_KLAPS_PRODUCT", candidate, root
        ),
        "operational_unchanged": artifact(
            "OPERATIONAL_UNCHANGED",
            "LIVE_OPERATIONAL_KLAPS_UNCHANGED",
            operational,
            root,
        ),
    }
    if product == "MET_EM":
        result["plot_fields"] = [
            {
                "plot_id": "temperature-level0",
                "field": "TT",
                "indices": {"Time": 0, "num_metgrid_levels": 0},
                "scale": {"value_min": 260.0, "value_max": 310.0, "delta_abs_max": 5.0},
            }
        ]
    else:
        result["plot_fields"] = [
            {
                "plot_id": "temperature-500hpa",
                "field": "TT",
                "level": 50000.0,
                "scale": {"value_min": 260.0, "value_max": 310.0, "delta_abs_max": 5.0},
            }
        ]
    return result


def write_manifest(path: Path, pairs: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {"schema_version": 1, "comparison_id": "fixture", "pairs": pairs},
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def expect_not_ready(
    root: Path, name: str, pairs: list[dict], expected_message: str
) -> dict:
    manifest = root / f"{name}.json"
    write_manifest(manifest, pairs)
    report = prepare(manifest, root, root / f"{name}-report")
    assert report["status"] == "NOT_READY"
    assert report["algorithm_comparison_status"] == "NOT_RUN"
    assert expected_message in report["failures"][0]
    assert not (root / f"{name}-report" / "comparison_data").exists()
    return report


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-operational-compare-") as directory:
        root = Path(directory)

        original, candidate, operational = make_wps_triad(root, "ready-wps")
        manifest = root / "wps-manifest.json"
        write_manifest(manifest, [pair(root, (original, candidate, operational))])

        ready_a = prepare(manifest, root, root / "ready-a")
        ready_b = prepare(manifest, root, root / "ready-b")
        assert ready_a == ready_b
        assert ready_a["status"] == "READY"
        assert ready_a["algorithm_comparison_status"] == (
            "READY_FOR_NUMERICAL_AND_PLOT_COMPARISON"
        )
        assert ready_a["bigfile_used"] is False
        assert ready_a["promotion_eligible"] is False
        assert ready_a["certified_operational_provenance"] is False
        assert ready_a["scientific_conclusion"] == "NOT_ASSESSED"
        assert ready_a["evidence_time_scope"] == (
            "CHECKSUM_BOUND_INPUT_SNAPSHOTS_NOT_LIVE_STATE"
        )
        evidence = ready_a["pairs"][0]["evidence"]
        assert evidence["original"]["evidence_role"] == "REAL_OPERATIONAL_ORIGINAL"
        assert evidence["candidate"]["evidence_role"] == "SHADOW_CANDIDATE"
        assert evidence["operational_unchanged"]["evidence_role"] == (
            "OPERATIONAL_UNCHANGED"
        )
        bundle = root / "ready-a" / "comparison_data" / ready_a["pairs"][0]["pair_id"]
        bundle = bundle / "temperature-500hpa"
        delta = np.load(bundle / "delta.npy", allow_pickle=False)
        assert np.all(delta == 1.0)
        metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["fixed_scale"] == {
            "value_min": 260.0,
            "value_max": 310.0,
            "delta_abs_max": 5.0,
        }
        assert metadata["scale_source"] == "MANIFEST_FIXED"
        assert (root / "ready-a" / "READINESS.json").read_bytes() == (
            root / "ready-b" / "READINESS.json"
        ).read_bytes()

        incomplete_paths = make_wps_triad(root, "incomplete-wps", omit_rh=True)
        expect_not_ready(
            root, "incomplete", [pair(root, incomplete_paths)], "field inventory"
        )

        metadata_paths = make_wps_triad(
            root, "metadata-mismatch", candidate_source="NOT_SHADOW_SOURCE"
        )
        expect_not_ready(
            root,
            "metadata-mismatch",
            [pair(root, metadata_paths)],
            "field metadata",
        )

        canonical_source_paths = make_wps_triad(
            root, "canonical-source", candidate_source="CANONICAL_BACKGROUND"
        )
        expect_not_ready(
            root,
            "canonical-source",
            [pair(root, canonical_source_paths)],
            "forbidden diagnostic WPS source label",
        )

        empty_source_paths = make_wps_triad(
            root, "empty-source", candidate_source=""
        )
        expect_not_ready(
            root,
            "empty-source",
            [pair(root, empty_source_paths)],
            "empty WPS source label",
        )

        duplicate_paths = make_wps_triad(root, "duplicate-pair-a")
        duplicate_paths_b = make_wps_triad(root, "duplicate-pair-b")
        first_duplicate = pair(root, duplicate_paths)
        second_duplicate = pair(root, duplicate_paths_b)
        second_duplicate["pair_id"] = "laps-duplicate-20260816T130000Z"
        expect_not_ready(
            root,
            "duplicate-pair-time",
            [first_duplicate, second_duplicate],
            "duplicate product_kind/valid_time",
        )

        reused_paths = make_wps_triad(root, "reused-artifact")
        first_reuse = pair(root, reused_paths)
        second_reuse = pair(root, reused_paths)
        second_reuse["pair_id"] = "laps-reuse-20260816T130000Z"
        expect_not_ready(
            root,
            "reused-artifact",
            [first_reuse, second_reuse],
            "artifact path is reused",
        )

        missing_pair = pair(root, (original, candidate, operational))
        missing_pair["valid_time"] = "2026-08-16T12:00:00Z"
        missing_pair["original"]["path"] = "missing/LAPS:2026-08-16_12:00"
        expect_not_ready(root, "missing-original", [missing_pair], "original")

        bad_checksum_pair = pair(root, (original, candidate, operational))
        bad_checksum_pair["candidate"]["sha256"] = "0" * 64
        expect_not_ready(root, "checksum", [bad_checksum_pair], "checksum")

        bad_attestation_paths = make_wps_triad(root, "bad-attestation")
        generation_path = bad_attestation_paths[1].parent / "MANIFEST.json"
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        generation["products"][0]["sha256"] = "0" * 64
        generation_path.write_text(json.dumps(generation, sort_keys=True), encoding="utf-8")
        expect_not_ready(
            root,
            "bad-attestation",
            [pair(root, bad_attestation_paths)],
            "generation manifest",
        )

        wrong_profile_paths = make_wps_triad(root, "wrong-shadow-profile")
        generation_path = wrong_profile_paths[1].parent / "MANIFEST.json"
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        generation["configuration"] = "shadow-typo"
        generation_path.write_text(json.dumps(generation, sort_keys=True), encoding="utf-8")
        expect_not_ready(
            root,
            "wrong-shadow-profile",
            [pair(root, wrong_profile_paths)],
            "approved SHADOW profile",
        )

        fractional_pair = pair(root, (original, candidate, operational))
        fractional_pair["valid_time"] = "2026-08-16T13:00:00.1Z"
        expect_not_ready(
            root, "fractional-time", [fractional_pair], "filename valid time"
        )

        background_pair = pair(root, (original, candidate, operational))
        background_pair["candidate"]["origin"] = "CANONICAL_BACKGROUND"
        expect_not_ready(
            root,
            "background",
            [background_pair],
            "FULL_SHADOW_KLAPS_PRODUCT",
        )

        malformed_id_pair = pair(root, (original, candidate, operational))
        malformed_id_pair["pair_id"] = []
        expect_not_ready(root, "malformed-id", [malformed_id_pair], "invalid pair_id")

        malformed_plot_pair = pair(root, (original, candidate, operational))
        malformed_plot_pair["plot_fields"][0]["plot_id"] = []
        expect_not_ready(
            root, "malformed-plot", [malformed_plot_pair], "invalid plot_id"
        )

        normalized_path_pair = pair(root, (original, candidate, operational))
        normalized_path_pair["candidate"]["path"] = "./candidate.wps"
        expect_not_ready(
            root,
            "normalized-path",
            [normalized_path_pair],
            "normalized relative path",
        )

        bigfile_paths = make_wps_triad(root, "bigfile-final")
        big_candidate = bigfile_paths[1]
        big_pair = pair(root, (original, candidate, operational))
        big_pair["candidate"] = artifact(
            "SHADOW_CANDIDATE", "FULL_SHADOW_KLAPS_PRODUCT", big_candidate, root
        )
        expect_not_ready(root, "forbidden-path", [big_pair], "bigfile")

        bigfile_target = root / "bigfile-store" / "artifacts"
        bigfile_target.mkdir(parents=True)
        safe_alias = root / "safe-alias"
        safe_alias.symlink_to(bigfile_target.parent, target_is_directory=True)
        symlink_root = prepare(
            manifest,
            safe_alias / "artifacts",
            root / "symlink-root-report",
        )
        assert symlink_root["status"] == "NOT_READY"
        assert "symbolic link" in symlink_root["failures"][0]

        original_nc, candidate_nc, operational_nc = make_netcdf_triad(
            root, "ready-netcdf"
        )
        nc_manifest = root / "nc-manifest.json"
        write_manifest(
            nc_manifest,
            [pair(root, (original_nc, candidate_nc, operational_nc), product="MET_EM")],
        )
        netcdf_ready = prepare(nc_manifest, root, root / "netcdf-ready")
        assert netcdf_ready["status"] == "READY"
        nc_bundle = root / "netcdf-ready" / "comparison_data"
        nc_bundle /= netcdf_ready["pairs"][0]["pair_id"]
        nc_bundle /= "temperature-level0"
        assert np.allclose(np.load(nc_bundle / "delta.npy", allow_pickle=False), 0.5)

        repeated_time_paths = make_netcdf_triad(root, "repeated-time-netcdf")
        with netCDF4.Dataset(repeated_time_paths[1], "r+") as dataset:
            dataset.variables["Times"][1, :] = np.asarray(
                list("2026-08-16_13:00:00"), dtype="S1"
            )
        seal_candidate(repeated_time_paths[1])
        expect_not_ready(
            root,
            "repeated-time",
            [pair(root, repeated_time_paths, product="MET_EM")],
            "exactly one Times record",
        )

        diagnostic_paths = make_netcdf_triad(root, "diagnostic-netcdf", diagnostic=True)
        expect_not_ready(
            root,
            "diagnostic",
            [pair(root, diagnostic_paths, product="MET_EM")],
            "diagnostic/background",
        )

        background_nc_paths = make_netcdf_triad(root, "background-netcdf")
        with netCDF4.Dataset(background_nc_paths[1], "r+") as dataset:
            dataset.result_authority = "CANONICAL_BACKGROUND"
        seal_candidate(background_nc_paths[1])
        expect_not_ready(
            root,
            "background-netcdf",
            [pair(root, background_nc_paths, product="MET_EM")],
            "diagnostic/background",
        )

    print("Operational comparison preparation tests passed")


def test_operational_comparison_preparation() -> None:
    """Allow normal pytest discovery in addition to direct execution."""
    main()


if __name__ == "__main__":
    main()
