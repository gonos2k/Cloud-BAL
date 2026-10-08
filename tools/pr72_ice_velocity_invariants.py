#!/usr/bin/env python3
"""Restore ice slope and velocity invariants when graupel PSD is absent."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path


ICE_SLOPE_ANCHOR = """          endif
          if(qci(i,k) .le. qmin) then  
            rslope(i,k,4) = rslopeimax
            rslopeb(i,k,4) = rslopeibmax
            rslopemu(i,k,4) = rslopeimmax
            rsloped(i,k,4) = rslopeidmax
            rslope2(i,k,4) = rslopei2max
            rslope3(i,k,4) = rslopei3max
          else
           rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &
                          1./lamdaimax)
            rslopeb(i,k,4) = (rslope(i,k,4))**bvti
            rslopemu(i,k,4) = DBLE(rslope(i,k,4))**mui
            rsloped(i,k,4) = (rslope(i,k,4))**dmi
            rslope2(i,k,4) = (rslope(i,k,4))*rslope(i,k,4)
            rslope3(i,k,4) = (rslope2(i,k,4))*rslope(i,k,4)
            endif
          endif
          vt(i,k,1) = DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
"""
ICE_SLOPE_REPLACEMENT = """          endif
          endif
          if(qci(i,k) .le. qmin) then  
            rslope(i,k,4) = rslopeimax
            rslopeb(i,k,4) = rslopeibmax
            rslopemu(i,k,4) = rslopeimmax
            rsloped(i,k,4) = rslopeidmax
            rslope2(i,k,4) = rslopei2max
            rslope3(i,k,4) = rslopei3max
          else
           rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &
                          1./lamdaimax)
            rslopeb(i,k,4) = (rslope(i,k,4))**bvti
            rslopemu(i,k,4) = DBLE(rslope(i,k,4))**mui
            rsloped(i,k,4) = (rslope(i,k,4))**dmi
            rslope2(i,k,4) = (rslope(i,k,4))*rslope(i,k,4)
            rslope3(i,k,4) = (rslope2(i,k,4))*rslope(i,k,4)
            endif
          vt(i,k,1) = DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
"""
VELOCITY_ANCHOR = """          vt(i,k,4) = DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          if(qrs(i,k,1).le.0.0) vt(i,k,1) = 0.0 
          if(qrs(i,k,2).le.0.0) vt(i,k,2) = 0.0
          if(qrs(i,k,3).le.0.0) vt(i,k,3) = 0.0
          if(qci(i,k).le.0.0) vt(i,k,4) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k,1) = 0.0 
          if(nci(i,k).le.0.0) vtn(i,k,2) = 0.0 
          vtn(i,k,1) = DBLE(pvtrn)*rslopeb(i,k,1)*denfac(i,k)
          vtn(i,k,2) = DBLE(pvtin)*rslopeb(i,k,4)*denfac(i,k) 
"""
VELOCITY_REPLACEMENT = """          vt(i,k,4) = DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          vtn(i,k,1) = DBLE(pvtrn)*rslopeb(i,k,1)*denfac(i,k)
          vtn(i,k,2) = DBLE(pvtin)*rslopeb(i,k,4)*denfac(i,k) 
          if(qrs(i,k,1).le.0.0) vt(i,k,1) = 0.0 
          if(qrs(i,k,2).le.0.0) vt(i,k,2) = 0.0
          if(qrs(i,k,3).le.0.0) vt(i,k,3) = 0.0
          if(qci(i,k).le.0.0) vt(i,k,4) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k,1) = 0.0 
          if(nci(i,k).le.0.0) vtn(i,k,2) = 0.0 
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(source: str) -> str:
    if source.count(ICE_SLOPE_ANCHOR) != 1:
        raise ValueError("expected one nested ice slope block under graupel presence branch")
    if source.count(VELOCITY_ANCHOR) != 1:
        raise ValueError("expected one ice number velocity overwrite sequence")
    source = source.replace(ICE_SLOPE_ANCHOR, ICE_SLOPE_REPLACEMENT, 1)
    source = source.replace(VELOCITY_ANCHOR, VELOCITY_REPLACEMENT, 1)
    if source.count("rslopeb(i,k,4) = rslopeibmax") != 1:
        raise ValueError("inactive ice slope initialization is not unique")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    args = parser.parse_args()
    for path in (args.output, args.patch, args.receipt):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite output: {path}")
    if not args.source.is_file() or args.source.is_symlink():
        raise SystemExit("source must be a regular non-symlink file")
    original = args.source.read_bytes()
    before = sha256(original)
    if before != args.expected_source_sha256:
        raise SystemExit(f"source SHA-256 mismatch: {before}")
    text = original.decode("utf-8")
    updated = transform(text)
    updated_bytes = updated.encode("utf-8")
    patch = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile=args.source.name, tofile=args.source.name,
    )).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.patch.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(updated_bytes)
    with args.patch.open("xb") as stream:
        stream.write(patch)
    receipt = {
        "schema": "pr72_ice_velocity_invariants_v1",
        "input_source": str(args.source), "input_source_sha256": before,
        "output_source": str(args.output), "output_source_sha256": sha256(updated_bytes),
        "patch": str(args.patch), "patch_sha256": sha256(patch),
        "changes": [
            "close the graupel-absent slope branch before initializing ice slope moments",
            "compute ice number velocity before applying the zero-number gate",
        ],
    }
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"INPUT_SOURCE_SHA256 {before}")
    print(f"OUTPUT_SOURCE_SHA256 {receipt['output_source_sha256']}")
    print(f"PATCH_SHA256 {receipt['patch_sha256']}")
    print(f"COMPOSITION_RECEIPT {args.receipt}")


if __name__ == "__main__":
    main()
