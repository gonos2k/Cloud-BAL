#!/usr/bin/env python3
"""Generate a source-pinned fix for KDM6's per-column rain flux cache."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


V42_SOURCE_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"
V43_SMALL_POLICY_SOURCE_SHA256 = "ed1f1ee12beb4395e08e7df831bd86163080e7d93fa60d6ac427a04c0862a148"
SUPPORTED_SOURCE_SHA256 = {V42_SOURCE_SHA256, V43_SMALL_POLICY_SOURCE_SHA256}


class RainFluxCacheError(ValueError):
    """The source is not a supported frozen preimage or its caller drifted."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_exact(source: str, before: str, after: str, label: str, expected: int = 1) -> str:
    count = source.count(before)
    if count != expected:
        raise RainFluxCacheError(f"expected {expected} {label} source anchors, found {count}")
    return source.replace(before, after)


def _transform_pinned_source(source: str) -> str:
    """Store each returned pair in the existing per-column flux arrays."""
    source = _replace_exact(
        source,
        "        k = kte\n"
        "        do i = its, ite\n"
        "         if(n.le.mstep(i)) then\n"
        "           falk(i,k,1) = REAL(pr87_rain_qrate(k))\n"
        "           falkn(i,k,1) = REAL(pr87_rain_nrate(k))\n"
        "           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n",
        "        k = kte\n"
        "        do i = its, ite\n"
        "         if(n.le.mstep(i)) then\n"
        "           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n",
        "top-sweep deferred rain-rate assignment",
    )
    source = _replace_exact(
        source,
        "       do k = kte_in-1,kts,-1\n"
        "         do i = its,ite\n"
        "           if(n.le.mstep(i)) then\n"
        "             falk(i,k,1) = REAL(pr87_rain_qrate(k))\n"
        "             falkn(i,k,1) = REAL(pr87_rain_nrate(k))\n"
        "             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n",
        "       do k = kte_in-1,kts,-1\n"
        "         do i = its,ite\n"
        "           if(n.le.mstep(i)) then\n"
        "             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)\n",
        "lower-sweep deferred rain-rate assignment",
    )
    source = _replace_exact(
        source,
        "              error stop 'PR87 rain sedimentation packet rejected'\n"
        "            endif\n",
        "              error stop 'PR87 rain sedimentation packet rejected'\n"
        "            endif\n"
        "            do k = kts, kte\n"
        "              falk(i,k,1) = REAL(pr87_rain_qrate(k))\n"
        "              falkn(i,k,1) = REAL(pr87_rain_nrate(k))\n"
        "            enddo\n",
        "immediate per-column rain flux assignment",
    )
    sweep_start = source.index("        k = kte")
    if ("REAL(pr87_rain_qrate(k))" in source[sweep_start:] or
            "REAL(pr87_rain_nrate(k))" in source[sweep_start:]):
        raise RainFluxCacheError("a deferred one-dimensional rain-rate consumer remains")
    return source


def transform_source(source: str) -> tuple[str, dict]:
    """Verify a frozen V42 or composed V43 source, then return corrected source."""
    source_bytes = source.encode("utf-8")
    before_hash = sha256_bytes(source_bytes)
    if before_hash not in SUPPORTED_SOURCE_SHA256:
        raise RainFluxCacheError(f"unsupported source SHA-256: {before_hash}")
    generated = _transform_pinned_source(source)
    after_hash = sha256_bytes(generated.encode("utf-8"))
    return generated, {
        "schema": "pr87_rain_flux_cache_transform_v1",
        "input_sha256": before_hash,
        "output_sha256": after_hash,
        "accepted_preimage": "V42 frozen KDM6 or V43 diagnostic plus small-positive graupel policy composition",
        "changes": [
            "copy each helper result immediately into existing per-column falk/falkn slots",
            "remove later assignments that reused the final column's one-dimensional result",
            "retain existing top and lower fall/falln accumulation statements",
        ],
        "preserved": [
            "helper call order and substep gates",
            "rate and packet formulas, theta selection, state mutations, and vertical sweep order",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="frozen V42 or composed V43 KDM6 Fortran source")
    parser.add_argument("output", type=Path, help="write transformed candidate source here")
    parser.add_argument("--receipt", type=Path, help="optional JSON transform receipt")
    args = parser.parse_args()
    import json

    try:
        candidate, receipt = transform_source(args.source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, RainFluxCacheError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(candidate, encoding="utf-8")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
