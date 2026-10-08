#!/usr/bin/env python3
"""Add source-bound operands to the first transient-state rejection."""
from __future__ import annotations
import argparse, difflib, hashlib
from pathlib import Path

ANCHOR = """          if (progb_status(i,k) == PROGB_TRANSIENT) &
            error stop 'ProgB transient PSD state rejected'"""
TRACE = """          if (progb_status(i,k) == PROGB_TRANSIENT) then
            write(*,'(A,1X,3(I0,1X),10(ES24.16,1X))') 'PR72_TRANSIENT_STATE', &
              i,k,progb_status(i,k),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3), &
              qci(i,k),nrs(i,k),nci(i,k), &
              den(i,k),denfac(i,k),t(i,k)
            error stop 'ProgB transient PSD state rejected'
          endif"""

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('patch',type=Path);parser.add_argument('--expected-source-sha256',required=True)
    args=parser.parse_args()
    for path in (args.output,args.patch):
        if path.exists() or path.is_symlink(): raise SystemExit(f'refusing to overwrite {path}')
    if not args.source.is_file() or args.source.is_symlink(): raise SystemExit('source must be regular non-symlink')
    raw=args.source.read_bytes(); digest=sha(raw)
    if digest != args.expected_source_sha256: raise SystemExit(f'source hash mismatch: {digest}')
    source=raw.decode()
    if source.count(ANCHOR)!=1: raise SystemExit('transient guard anchor must occur exactly once')
    updated=source.replace(ANCHOR,TRACE,1)
    patch=''.join(difflib.unified_diff(source.splitlines(keepends=True),updated.splitlines(keepends=True),fromfile=args.source.name,tofile=args.source.name)).encode()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.patch.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(updated.encode());args.patch.write_bytes(patch)
    print(f'BASE_SOURCE_SHA256 {digest}')
    print(f'TRACED_SOURCE_SHA256 {sha(updated.encode())}')
    print(f'TRACE_PATCH_SHA256 {sha(patch)}')

if __name__=='__main__': main()
