#!/usr/bin/env python3
"""Audit the exact source produced by the frozen PR71 step-count transform."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


EXPECTED_BASE_SHA256 = "5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source = Path(sys.argv[1])
    original = Path(sys.argv[2])
    text = source.read_bytes().decode("latin-1")
    if sha256(original) != EXPECTED_BASE_SHA256:
        raise SystemExit("frozen base SHA mismatch")
    if text.count("call checked_substep_count(") != 2:
        raise SystemExit("expected exactly two checked substep count calls")
    if "PR71_STEP_COUNT_REJECT i,k,rate,dt=" not in text or \
            "PR71_STEP_COUNT_REJECT_ICE i,k,rate,dt=" not in text:
        raise SystemExit("both invalid-input diagnostics are required")
    if "error stop 'invalid PR71 KDM6 substep count'" not in text or \
            "error stop 'invalid PR71 KDM6 ice substep count'" not in text:
        raise SystemExit("both guarded consumers must fail before loop-count use")
    if "numdt(i)=max(nint(max(" in text or "numdt_i(i) = max(nint(max(" in text:
        raise SystemExit("unguarded original integer conversion remains")
    helper = text.split("PR71_STEP_COUNT_CONTRACT_BEGIN", 1)[1].split(
        "PR71_STEP_COUNT_CONTRACT_END", 1
    )[0]
    for required in ("count = 0", "valid = .false.", "abs(rate) > huge(rate) / dt64",
                     "real(huge(count), kind=kind(rate)) + 0.5d0",
                     "real(-huge(count) - 1, kind=kind(rate)) - 0.5d0",
                     "count = max(nint(rate * timestep + .5), 1)"):
        if required not in helper:
            raise SystemExit(f"missing helper contract: {required}")
    print(f"PR71_STEP_COUNT_SOURCE_AUDIT_PASS {sha256(source)}")


if __name__ == "__main__":
    main()
