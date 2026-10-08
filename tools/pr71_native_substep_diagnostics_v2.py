#!/usr/bin/env python3
"""Add print-only substep diagnostics to the frozen PR71 native observer."""

from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path


EXPECTED_SOURCE_SHA256 = "b3d4dbdb36b7485b87a4d3cd1dc83ac005e55bcc7bab8254cc7483a5b46c5846"

LIQUID_DIAGNOSTIC = """      if (lat == jts) then
        write(*,*) 'PR71_SUBSTEP_V2_LIQ', lat, its, ite, kts, kte, dtcld, &
                   mstepmax, count(mstep(its:ite) > 1), &
                   maxval(mstep(its:ite)), its+maxloc(mstep(its:ite))-1
        write(*,*) 'PR71_SUBSTEP_V2_LIQ_RATE_QR', &
                   maxval(mass_velocity_rate(its:ite,kts:kte,1)), &
                   maxloc(mass_velocity_rate(its:ite,kts:kte,1)) + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_LIQ_RATE_QS', &
                   maxval(mass_velocity_rate(its:ite,kts:kte,2)), &
                   maxloc(mass_velocity_rate(its:ite,kts:kte,2)) + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_LIQ_RATE_QG', &
                   maxval(mass_velocity_rate(its:ite,kts:kte,3)), &
                   maxloc(mass_velocity_rate(its:ite,kts:kte,3)) + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_LIQ_RATE_NR', &
                   maxval(number_velocity_rate(its:ite,kts:kte,1)), &
                   maxloc(number_velocity_rate(its:ite,kts:kte,1)) + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_LIQ_DELZ', &
                   minval(delz(its:ite,kts:kte)), maxval(delz(its:ite,kts:kte)), &
                   maxloc(delz(its:ite,kts:kte)) + [its-1,kts-1]
      endif
"""

ICE_DIAGNOSTIC = """      if (lat == jts) then
        write(*,*) 'PR71_SUBSTEP_V2_ICE', lat, its, ite, kts, kte, dtcld, &
                   mstepmax_i, count(mstep_i(its:ite) > 1), &
                   maxval(mstep_i(its:ite)), its+maxloc(mstep_i(its:ite))-1
        pr71_substep_loc = maxloc(mass_velocity_rate(its:ite,kts:kte,4))
        pr71_substep_loc = pr71_substep_loc + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_ICE_RATE_QI', &
                   maxval(mass_velocity_rate(its:ite,kts:kte,4)), &
                   pr71_substep_loc, &
                   delz(pr71_substep_loc(1),pr71_substep_loc(2)), &
                   terminal_velocity_mass(pr71_substep_loc(1),pr71_substep_loc(2),4)
        pr71_substep_loc = maxloc(number_velocity_rate(its:ite,kts:kte,2))
        pr71_substep_loc = pr71_substep_loc + [its-1,kts-1]
        write(*,*) 'PR71_SUBSTEP_V2_ICE_RATE_NI', &
                   maxval(number_velocity_rate(its:ite,kts:kte,2)), &
                   pr71_substep_loc, &
                   delz(pr71_substep_loc(1),pr71_substep_loc(2)), &
                   terminal_velocity_number(pr71_substep_loc(1),pr71_substep_loc(2),2)
        write(*,*) 'PR71_SUBSTEP_V2_ICE_DELZ', &
                   minval(delz(its:ite,kts:kte)), maxval(delz(its:ite,kts:kte)), &
                   maxloc(delz(its:ite,kts:kte)) + [its-1,kts-1]
      endif
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(source: str) -> str:
    if "write(pr67_unit) work1(its:ite,kts:kte,4)" in source:
        raise ValueError("base observer still reads the unassigned legacy work1 field")
    if source.count("write(pr67_unit) mass_velocity_rate(its:ite,kts:kte,4)") != 1:
        raise ValueError("expected the fixed stage-0 named ice-rate field from the base patch")
    declaration = "   integer :: pr67_unit\n"
    if source.count(declaration) != 1:
        raise ValueError("expected one KDM62D trace-unit declaration")
    source = source.replace(
        declaration,
        declaration + "   integer :: pr71_substep_loc(2)\n",
        1,
    )
    anchors = (
        ("      do n = 1, mstepmax\n", LIQUID_DIAGNOSTIC),
        ("      do n = 1, mstepmax_i\n", ICE_DIAGNOSTIC),
    )
    for anchor, diagnostic in anchors:
        if source.count(anchor) != 1:
            raise ValueError(f"expected one loop anchor {anchor.strip()!r}")
        source = source.replace(anchor, diagnostic + anchor, 1)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("patch", type=Path)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    source_hash = digest(raw)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"base-fixed observer source SHA mismatch: {source_hash}")
    updated = transform(raw.decode("utf-8")).encode("utf-8")
    patch = "".join(difflib.unified_diff(
        raw.decode("utf-8").splitlines(keepends=True),
        updated.decode("utf-8").splitlines(keepends=True),
        fromfile=args.source.name,
        tofile=args.output.name,
    )).encode("utf-8")
    for path, payload in ((args.output, updated), (args.patch, patch)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise SystemExit(f"refusing to overwrite different diagnostic artifact: {path}")
        else:
            with path.open("xb") as stream:
                stream.write(payload)
    print(f"SOURCE_SHA256 {source_hash}")
    print(f"DIAGNOSTIC_SOURCE_SHA256 {digest(updated)}")
    print(f"DIAGNOSTIC_PATCH_SHA256 {digest(patch)}")
    print("DIAGNOSTIC_ANCHORS 2")


if __name__ == "__main__":
    main()
