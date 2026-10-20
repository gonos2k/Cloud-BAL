#!/usr/bin/env python3
"""Hash C18 joint-stage traces and retain only one cell's T23/T24 QI/NI/DEN."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F")
SOURCE_SHA256 = "983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4"
STATE_MAGIC = b"PR85QND2"
TENDENCY_MAGIC = b"PR85PLB1"
STATE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
TENDENCY_FIELDS = ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
TARGET = (230, 247, 20)  # i, j, k
STAGES = {"POST_KDM6", "PRE_RK", "RK_STAGE_END", "PRE_KDM6"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def scan_trace(path: Path) -> tuple[str, dict]:
    """Hash the decompressed stream while extracting only the requested stages."""
    digest = hashlib.sha256()
    selected: dict[str, dict] = {}
    with gzip.open(path, "rb") as stream:
        record_index = 0
        while True:
            magic = stream.read(8)
            if not magic:
                break
            digest.update(magic)
            if magic not in (STATE_MAGIC, TENDENCY_MAGIC):
                raise ValueError(f"unexpected stage-trace magic at record {record_index}")
            label_raw = stream.read(32)
            header_raw = stream.read(60)
            if len(label_raw) != 32 or len(header_raw) != 60:
                raise ValueError(f"truncated stage-trace header at record {record_index}")
            digest.update(label_raw)
            digest.update(header_raw)
            label = label_raw.decode("ascii").strip()
            values = struct.unpack(">15i", header_raw)
            (kind, timestep, rkstep, ims, ime, jms, jme, kms, kme,
             its, ite, jts, jte, kts, kte) = values
            expected_kind = 1 if magic == STATE_MAGIC else 2
            if kind != expected_kind or timestep < 1:
                raise ValueError(f"invalid trace metadata at record {record_index}")
            nx, nk, nj = ite - its + 1, kte - kts + 1, jte - jts + 1
            cells = nx * nk * nj
            if min(nx, nk, nj) <= 0:
                raise ValueError(f"invalid active bounds at record {record_index}")
            target_in_bounds = (its <= TARGET[0] <= ite and jts <= TARGET[1] <= jte and
                                kts <= TARGET[2] <= kte)
            requested_stage = ((timestep == 23 and label == "POST_KDM6") or
                               (timestep == 24 and label in {"PRE_RK", "RK_STAGE_END", "PRE_KDM6"}))
            is_target = magic == STATE_MAGIC and requested_stage and target_in_bounds
            target_offset = (((TARGET[1] - jts) * nk + TARGET[2] - kts) * nx +
                             TARGET[0] - its) * 4 if is_target else -1
            fields = {}
            names = STATE_FIELDS if expected_kind == 1 else TENDENCY_FIELDS
            field_bytes = cells * 4
            for name in names:
                field_digest_start = 0
                bytes_left = field_bytes
                captured = None
                while bytes_left:
                    chunk = stream.read(min(bytes_left, 4 * 1024 * 1024))
                    if not chunk:
                        raise ValueError(f"truncated {label} {name} in record {record_index}")
                    digest.update(chunk)
                    if target_offset >= field_digest_start and target_offset + 4 <= field_digest_start + len(chunk):
                        captured = struct.unpack_from(">f", chunk, target_offset - field_digest_start)[0]
                    field_digest_start += len(chunk)
                    bytes_left -= len(chunk)
                if is_target and name in ("DEN", "QI", "NI"):
                    if captured is None:
                        raise ValueError(f"target value missing for {label} {name}")
                    fields[name] = {"value": captured,
                                    "bits": struct.pack(">f", captured).hex().upper()}
            if is_target:
                density = fields["DEN"]["value"]
                qi = fields["QI"]["value"]
                number_public = fields["NI"]["value"]
                number_volume = f32(number_public * density)
                mean = float(density) * float(qi) / float(number_volume)
                fields["NI_volume"] = {
                    "value": number_volume,
                    "bits": struct.pack(">f", number_volume).hex().upper(),
                    "conversion": "REAL32(public_NI * REAL32(DEN))",
                }
                fields["ice_mean_mass_kg"] = mean
                selected[f"T{timestep}_{label}_RK{rkstep}"] = {
                    "timestep": timestep, "stage": label, "rkstep": rkstep,
                    "point_ijk": list(TARGET), "fields": fields,
                }
            record_index += 1
    expected = {"T23_POST_KDM6_RK0", "T24_PRE_RK_RK0", "T24_RK_STAGE_END_RK1",
                "T24_RK_STAGE_END_RK2", "T24_RK_STAGE_END_RK3", "T24_PRE_KDM6_RK0"}
    if set(selected) != expected:
        raise ValueError(f"selected target stage set differs: {sorted(selected)}")
    return digest.hexdigest(), selected


def inspect_arm(arm: str, trace_root: Path, source_hash: str) -> dict:
    run = trace_root / f"pr92_{arm}_600s_c18_20261020"
    receipt_path = run / "receipt.json"
    trace_path = run / "run/pr85_joint_moment_stages.raw.gz"
    receipt_sha = sha256(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    trace_row = next((row for row in receipt.get("compressed_outputs", [])
                      if row.get("compressed_path") == trace_path.name), None)
    if trace_row is None:
        raise ValueError(f"trace is not bound by receipt: {receipt_path}")
    compressed_sha = sha256(trace_path)
    if compressed_sha != trace_row.get("compressed_sha256"):
        raise ValueError(f"compressed trace hash differs from C18 receipt: {trace_path}")
    payload_sha, selected = scan_trace(trace_path)
    if payload_sha != trace_row.get("sha256"):
        raise ValueError(f"decompressed trace hash differs from C18 receipt: {trace_path}")
    return {
        "receipt_path": str(receipt_path), "receipt_sha256": receipt_sha,
        "receipt_status": receipt.get("status"),
        "trace_path": str(trace_path), "trace_compressed_sha256": compressed_sha,
        "trace_compressed_bytes": trace_path.stat().st_size,
        "receipt_bound_compressed_sha256": trace_row.get("compressed_sha256"),
        "receipt_bound_compressed_bytes": trace_row.get("compressed_bytes"),
        "trace_payload_sha256": payload_sha,
        "receipt_bound_payload_sha256": trace_row.get("sha256"),
        "receipt_bound_payload_bytes": trace_row.get("bytes"),
        "selected_target_states": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", type=Path, default=Path("/var/tmp"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    source_hash = sha256(args.source)
    if source_hash != SOURCE_SHA256:
        raise ValueError("selected source identity differs from preserved C18 source")
    result = {
        "schema": "pr93_c18_target_trace_provenance_v1",
        "source_path": str(args.source), "source_sha256": source_hash,
        "coordinate_convention": "i,j,k; public NI is # kg-1 dry air; KDM6 internal NI is # m-3",
        "number_conversion_source": "specific_number_to_volume(public_NI,DEN,number_value) in selected module_mp_kdm6.F",
        "conversion_precision": "REAL32 product, then exact REAL64 helper mean DEN*QI/NI_volume",
        "arms": {arm: inspect_arm(arm, args.trace_root, source_hash)
                 for arm in ("OFF", "COUPLED")},
        "retained_scope": "only T23 POST_KDM6 and T24 PRE_RK, RK1, RK2, RK3, PRE_KDM6 at (230,247,20)",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "PASS_TRACE_PROVENANCE", "output": str(args.output),
                      "arms": {arm: {"receipt_sha256": row["receipt_sha256"],
                                     "compressed_sha256": row["trace_compressed_sha256"],
                                     "payload_sha256": row["trace_payload_sha256"],
                                     "selected_states": len(row["selected_target_states"])}
                                for arm, row in result["arms"].items()}}, indent=2))


if __name__ == "__main__":
    main()
