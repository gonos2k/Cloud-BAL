#!/usr/bin/env python3
"""Apply the reviewed full-candidate bulk-absence certificate to pinned C1 sources."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pr91_host_store_trace import instrument_core, replace_once


HOST_SHA256 = "f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af"
BASE_CORE_SHA256 = "faa4ce0e31bf5b394c9a5ec2045a917464dca7cd4d902b6aa62be80a19aa5ac0"
EMBEDDED_CORE_SHA256 = "da7cc5729ae0299919e113484af3d788f97366dfbcf14f5d0e1a75d70c1af9b8"
CORE_SHA256 = "6c844fe8a68ded3c653d800065d428c390b08845a584dc65ab070995adc7dd53"


def digest(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def transform_module(host: str, core: str, baseline_core: str) -> str:
    if digest(host) != HOST_SHA256:
        raise ValueError("unexpected pinned C1 host")
    if digest(core) != CORE_SHA256:
        raise ValueError("unexpected reviewed grouped-transport core")
    if digest(baseline_core) != BASE_CORE_SHA256:
        raise ValueError("unexpected pre-certificate C1 core")
    start = host.index("module cloud_bal_joint_transport\n")
    end = host.index("end module cloud_bal_joint_transport", start) + len("end module cloud_bal_joint_transport")
    embedded_baseline = instrument_core(baseline_core, BASE_CORE_SHA256).rstrip()
    if digest(host[start:end]) != EMBEDDED_CORE_SHA256 or host[start:end] != embedded_baseline:
        raise ValueError("pinned host does not contain transformed pre-certificate core")
    host = host[:start] + instrument_core(core, CORE_SHA256).rstrip() + host[end:]

    host = replace_once(
        host,
        "  USE cloud_bal_joint_transport, ONLY: joint_moment_is_valid, joint_moment_is_valid64, &\n"
        "       joint_moment_store, joint_qnb_update\n",
        "  USE cloud_bal_joint_transport, ONLY: joint_moment_is_valid, joint_moment_is_valid64, &\n"
        "       joint_moment_store, joint_qnb_update, joint_bulk_candidate_absence_is_valid\n",
        "C1 shared certificate import",
    )
    host = replace_once(
        host,
        "                  allow_bulk_volume_quantum_storage=use_bulk_absence)\n"
        "              IF (store_valid.AND.value_n>0.0_real64) THEN\n",
        "                  allow_bulk_volume_quantum_storage=use_bulk_absence)\n"
        "              IF (.NOT.store_valid.AND.use_bulk_absence) THEN\n"
        "                IF (joint_bulk_candidate_absence_is_valid(qb(c,4),nb(c,4), &\n"
        "                    oldcarrier(c),newcarrier(c),dt,drydensity(c),qs64(c,4),ns64(c,4), &\n"
        "                    qa64(c,4),na64(c,4),1.0_real64,minmass(4),maxmass(4),value_q,value_n)) THEN\n"
        "                  stored_q=0.0_real32; stored_n=0.0_real32\n"
        "                  adjustment=5; store_valid=.TRUE.\n"
        "                END IF\n"
        "              END IF\n"
        "              IF (store_valid.AND.value_n>0.0_real64) THEN\n",
        "shared full-candidate certificate in host retry/commit certifier",
    )
    return host


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--baseline-core", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = transform_module(args.host.read_text(), args.core.read_text(), args.baseline_core.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(result)
    print(f"generated_sha256={digest(result)}")


if __name__ == "__main__":
    main()
