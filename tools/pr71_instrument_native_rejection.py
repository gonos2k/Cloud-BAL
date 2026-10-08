#!/usr/bin/env python3
"""Add a read-only first invalid ProgB status trace before slope consumption."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def instrument(source: str) -> str:
    declaration = (
        "   integer, dimension(its:ite,kts:kte)   , intent(out) :: progb_status\n"
    )
    if source.count(declaration) != 1:
        raise ValueError("expected one KDM62D status declaration")
    source = source.replace(
        declaration,
        declaration + "   integer :: pr71_trace_i, pr71_trace_k\n"
        "   logical :: pr71_reject_logged\n",
        1,
    )

    pattern = re.compile(
        r"(?ims)([ \t]*call\s+ProgB_param\b.*?progb_status\)\s*\n)"
        r"([ \t]*call\s+slope_kdm6\b)"
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 7:
        raise ValueError(f"expected seven ProgB-to-slope call pairs, found {len(matches)}")

    result = source
    for stage, match in reversed(list(enumerate(matches, start=1))):
        probe = (
            "      pr71_reject_logged=.false.\n"
            "      do pr71_trace_k=kts,kte\n"
            "        do pr71_trace_i=its,ite\n"
            "          if (.not.pr71_reject_logged .and. &\n"
            "              progb_status(pr71_trace_i,pr71_trace_k) /= PROGB_PSD_ACTIVE .and. &\n"
            "              progb_status(pr71_trace_i,pr71_trace_k) /= PROGB_ABSENT) then\n"
            "            write(*,'(A,1X,I0,1X,I0,1X,I0,1X,I0,1X,I0,1X,ES24.16,1X,ES24.16)') &\n"
            "                 'PR71_PROGB_REJECT',%d,lat,pr71_trace_i,pr71_trace_k, &\n"
            "                 progb_status(pr71_trace_i,pr71_trace_k), &\n"
            "                 qrs_tmp(pr71_trace_i,pr71_trace_k,3), &\n"
            "                 brs(pr71_trace_i,pr71_trace_k)\n"
            "            pr71_reject_logged=.true.\n"
            "          endif\n"
            "        enddo\n"
            "      enddo\n" % stage
        )
        insert_at = match.end(1)
        result = result[:insert_at] + probe + result[insert_at:]
    if result.count("'PR71_PROGB_REJECT'") != 7:
        raise ValueError("expected seven observer-only rejection probes")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    args = parser.parse_args()
    if not args.source.is_file() or args.source.is_symlink():
        raise SystemExit("source must be a regular file")
    if args.output.exists() or args.output.is_symlink() or args.patch.exists() or args.patch.is_symlink():
        raise SystemExit("refusing to overwrite instrumented source or patch")
    original = args.source.read_bytes()
    source_hash = sha256(original)
    if source_hash != args.expected_source_sha256:
        raise SystemExit(f"combined PR71 source SHA-256 mismatch: {source_hash}")
    text = original.decode("utf-8")
    updated = instrument(text)
    updated_bytes = updated.encode("utf-8")
    patch = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), updated.splitlines(keepends=True),
        fromfile=args.source.name, tofile=args.source.name,
    )).encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.patch.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(updated_bytes)
    with args.patch.open("xb") as stream:
        stream.write(patch)
    print(f"COMBINED_SOURCE_SHA256 {source_hash}")
    print(f"OBSERVER_SOURCE_SHA256 {sha256(updated_bytes)}")
    print(f"OBSERVER_PATCH_SHA256 {sha256(patch)}")
    print(f"OBSERVER_PATCH_BYTES {len(patch)}")


if __name__ == "__main__":
    main()
