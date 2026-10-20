#!/usr/bin/env python3
"""Add the existing strict cloud volume contract to source-first store calls."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PINNED_HOST_SHA256 = "dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d"

INITIAL_CLOUD_CALL = """          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)"""

INITIAL_CLOUD_CALL_WITH_VOLUME = """          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE., &
               volume_number_bounds=number_bounds(cell,:,p))"""

FALLBACK_CALL = """          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2),adjustment,full_valid, &
               allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                 inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2))"""

FALLBACK_WITH_VOLUME = """          IF (p==1) THEN
            CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
                 minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
                 adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
                 allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE., &
                 volume_number_bounds=number_bounds(cell,:,p))
          ELSE
            CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
                 minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2),adjustment,full_valid, &
                 allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                   inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2))
          END IF"""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"expected exactly one {label} anchor, found {count}")
    return source.replace(before, after, 1)


def transform_source(source: str) -> str:
    if INITIAL_CLOUD_CALL_WITH_VOLUME in source:
        raise ValueError("source-first volume contract is already applied")
    source = replace_once(source, INITIAL_CLOUD_CALL, INITIAL_CLOUD_CALL_WITH_VOLUME,
                          "initial strict source-first cloud store")
    return replace_once(source, FALLBACK_CALL, FALLBACK_WITH_VOLUME,
                        "source-first cloud fallback store")


def transform_file(source_path: Path, output_path: Path) -> dict[str, str]:
    source = source_path.read_text()
    source_hash = sha256(source)
    if source_hash != PINNED_HOST_SHA256:
        raise ValueError(f"unexpected generated host SHA-256: {source_hash}")
    output = transform_source(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as destination:
        destination.write(output)
    return {"source_sha256": source_hash, "output_sha256": sha256(output),
            "output_path": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="pinned generated `_i` module_em.F source")
    parser.add_argument("--output", required=True, type=Path,
                        help="write the C8 candidate host source here")
    args = parser.parse_args()
    result = transform_file(args.source, args.output)
    print(f"source_sha256={result['source_sha256']}")
    print(f"output_sha256={result['output_sha256']}")
    print(f"output={result['output_path']}")


if __name__ == "__main__":
    main()
