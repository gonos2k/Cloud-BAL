#!/usr/bin/env python3
"""Gate only PR85 observer writes after the frozen 600-second prefix."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


FULL_PREFIX_STEPS = 30
DETAILED_STEPS = (60, 90, 180)
SOURCE_SHA256 = "ea50fe2b380d2d5572da42f97261afe19eabdfef194edbfa5e4abc6360ee33bb"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def compact_observer(source: str, duration_seconds: int) -> str:
    """Return observer source with post-prefix write gates around existing IO only."""
    if duration_seconds not in (1800, 3600):
        raise ValueError("duration must be 1800 or 3600 seconds")
    gates = " .OR. ".join(
        f"itimestep.EQ.{step}" for step in DETAILED_STEPS
        if FULL_PREFIX_STEPS < step and step * 20 <= duration_seconds
    )
    state_gate = (
        f"  IF (itimestep.LE.{FULL_PREFIX_STEPS} .OR. ({gates}) .OR. &\n"
        "      TRIM(label).EQ.'POST_KDM6') THEN\n"
    )
    tendency_gate = (
        f"  IF (itimestep.LE.{FULL_PREFIX_STEPS} .OR. ({gates})) THEN\n"
    )
    def gate_routine(text: str, name: str, gate: str, suffix: str) -> str:
        start_marker = f"SUBROUTINE {name}"
        end_marker = f"END SUBROUTINE {name}"
        start = text.index(start_marker)
        end = text.index(end_marker, start) + len(end_marker)
        routine = text[start:end]
        open_marker = "  OPEN(NEWUNIT=u,FILE='pr85_joint_moment_stages.raw',ACCESS='STREAM', &\n"
        if routine.count(open_marker) != 1 or routine.count(suffix) != 1:
            raise ValueError(f"unexpected {name} IO anchors")
        routine = routine.replace(open_marker, gate + open_marker, 1)
        routine = routine.replace(suffix, suffix.replace("  CLOSE(u)\n", "  CLOSE(u)\n  ENDIF\n", 1), 1)
        return text[:start] + routine + text[end:]

    transformed = gate_routine(
        source, "pr85_joint_stage_dump", state_gate,
        "  CLOSE(u)\n  DEALLOCATE(dry_density)\nEND SUBROUTINE pr85_joint_stage_dump")
    transformed = gate_routine(
        transformed, "pr85_pbl_tendency_dump", tendency_gate,
        "  CLOSE(u)\nEND SUBROUTINE pr85_pbl_tendency_dump")
    return transformed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration-seconds", type=int, choices=(1800, 3600), required=True)
    args = parser.parse_args()
    payload = args.source.read_bytes()
    if sha256_bytes(payload) != SOURCE_SHA256:
        parser.error("observer source does not match the frozen PR93-C4 input")
    transformed = compact_observer(payload.decode("utf-8"), args.duration_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(transformed)
    print(f"input_sha256 {sha256_bytes(payload)}")
    print(f"output_sha256 {sha256_bytes(transformed.encode('utf-8'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
