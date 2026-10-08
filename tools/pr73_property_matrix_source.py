#!/usr/bin/env python3
"""Expose only private PR72 KDM6 state needed by the PR73 routine test."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819"
HOOK_ANCHOR = "      mstepmax = 1\n      mstepmax_i = 1"
HOOK = """#ifdef TEST_PR73_PROPERTY_MATRIX
          open(unit=97,file='pr73_property_capture.dat',status='replace',action='write')
          do k=kts,kte
            do i=its,ite
              write(97,*) i,k,rslopec(i,k),rslopec2(i,k),rslopec3(i,k), &
                   rslopecmu(i,k),rslopecd(i,k),rslope(i,k,:),rslopeb(i,k,:), &
                   rslope2(i,k,:),rslope3(i,k,:),rsloped(i,k,:),rslopemu(i,k,:), &
                   terminal_velocity_mass(i,k,:),terminal_velocity_number(i,k,:), &
                   rhox(i,k),pidn0g(i,k),pvtg(i,k),bvtg(i,k),rslopegbmax(i,k), &
                   progb_status(i,k),qrs(i,k,:),nrs(i,k,1),qci(i,k,:),nci(i,k,1:2),brs(i,k)
            enddo
          enddo
          close(97)
          return
#endif
"""
TEST_POISON = """#ifdef TEST_PR73_PROPERTY_MATRIX
          rslopec=-777.0; rslopec2=-777.0; rslopec3=-777.0
          rslopecmu=-777.0; rslopecd=-777.0
#endif
"""
PROGB_POISON = """#ifdef TEST_PR73_PROPERTY_MATRIX
   rhox=-777.0; cmg=-777.0; pidn0g=-777.0; avtg=-777.0; pvtg=-777.0; precg2=-777.0
   bvtg=-777.0; bvtg1=-777.0; bvtg2=-777.0; bvtg3=-777.0; bvtg4=-777.0
   rslopegbmax=-777.0; g1pbg=-777.0; g3pbg=-777.0; g4pbg=-777.0; g5pbgo2=-777.0
   g1pdgbgmg=-777.0; dgbgmug1=-777.0; progb_status=-777
#endif
"""
SLOPE_POISON = """#ifdef TEST_PR73_PROPERTY_MATRIX
   rslope=-777.0; rslopeb=-777.0; rslope2=-777.0; rslope3=-777.0; rsloped=-777.0
   rslopemu=-777.0; terminal_velocity_mass=-777.0; terminal_velocity_number=-777.0
#endif
"""
RATE_POISON = """#ifdef TEST_PR73_PROPERTY_MATRIX
   mass_velocity_rate=-777.0; number_velocity_rate=-777.0
#endif
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(source: str) -> str:
    if source.count(HOOK_ANCHOR) != 1:
        raise ValueError("expected exactly one post-property/pre-process insertion point")
    cloud_anchor = "      do k = kts, kte\n        do i = its, ite\n          if(qci(i,k,1).le.qmin"
    progb_anchor = "   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin"
    slope_anchor = "   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp"
    rate_anchor = "   call kdm6_velocity_rates(terminal_velocity_mass"
    for anchor, name in ((cloud_anchor, "cloud slope"), (progb_anchor, "ProgB"),
                         (slope_anchor, "slope"), (rate_anchor, "velocity rates")):
        if anchor not in source:
            raise ValueError(f"missing source-backed {name} insertion point")
    transformed = source.replace(cloud_anchor, TEST_POISON + cloud_anchor, 1)
    transformed = transformed.replace(progb_anchor, PROGB_POISON + progb_anchor, 1)
    transformed = transformed.replace(slope_anchor, SLOPE_POISON + slope_anchor, 1)
    transformed = transformed.replace(rate_anchor, RATE_POISON + rate_anchor, 1)
    return transformed.replace(HOOK_ANCHOR, HOOK + HOOK_ANCHOR, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()

    source_hash = sha256(args.source)
    if source_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"unexpected frozen source SHA-256: {source_hash}")
    original = args.source.read_text()
    transformed = compose(original)
    args.output.write_text(transformed)
    args.patch.write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), transformed.splitlines(keepends=True),
        fromfile="frozen_combined_source.F", tofile="property_matrix_source.F")))
    result = {
        "schema": "pr73_property_matrix_source_v1",
        "source": str(args.source),
        "source_sha256": source_hash,
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "patch": str(args.patch),
        "patch_sha256": sha256(args.patch),
        "change": "test-only poison of actual cloud/ProgB/slope/velocity-rate outputs, then capture and early return before substep/rate application",
        "exposed_names": [],
        "production_source_modified": False,
    }
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
