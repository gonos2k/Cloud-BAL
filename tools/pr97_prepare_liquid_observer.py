#!/usr/bin/env python3
"""Attach a compact diagnostic to the frozen C1 liquid stores, without changing them."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

C1_PREPROCESSED_SHA256 = "7329d618f87a2924f167bd36fab43a9bd107e2697fbb6ac72ef3cee195953a67"


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"expected one source anchor: {before[:70]!r}")
    return source.replace(before, after, 1)


def prepare(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != C1_PREPROCESSED_SHA256:
        raise ValueError("diagnostic requires the frozen compiled C1 KDM6 source")
    text = source.decode()
    text = replace_once(text, "   use module_mp_radar\n", "   use module_mp_radar\n"
                        "   use pr97_liquid_observer, only: liquid_begin,liquid_record,liquid_end\n")
    text = replace_once(text, "   logical :: full_cloud_evap\n",
                        "   logical :: full_cloud_evap\n"
                        "   real :: pr97_q_before,pr97_c_before,pr97_extent\n")
    text = replace_once(text, "   kte_in = kte\n",
                        "   kte_in = kte\n   call liquid_begin(its,ite)\n")
    before = "            q(i,k) = max(q(i,k)-pcact(i,k)*dtcld,0.)\n"
    text = replace_once(text, before, "            pr97_q_before=q(i,k)\n"
                        "            pr97_c_before=qci(i,k,1)\n"
                        "            pr97_extent=pcact(i,k)*dtcld\n" + before)
    before = "            qci(i,k,1) = max(qci(i,k,1)+pcact(i,k)*dtcld,0.)\n"
    text = replace_once(text, before, before +
                        "            call liquid_record(i,1,pr97_q_before,pr97_c_before,pr97_extent, &\n"
                        "              q(i,k),qci(i,k,1),den(i,k),delz(i,k))\n")
    before = "          full_cloud_evap = .false.\n"
    text = replace_once(text, before, "          pr97_q_before=q(i,k)\n"
                        "          pr97_c_before=qci(i,k,1)\n"
                        "          pr97_extent=pcond(i,k)*dtcld\n" + before)
    before = "            t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld\n          endif\n"
    text = replace_once(text, before, before +
                        "          if(full_cloud_evap) pr97_extent=-cloud_evap_extent\n"
                        "          call liquid_record(i,merge(2,3,full_cloud_evap), &\n"
                        "            pr97_q_before,pr97_c_before,pr97_extent, &\n"
                        "            q(i,k),qci(i,k,1),den(i,k),delz(i,k))\n")
    text = replace_once(text, "   end subroutine kdm62d\n",
                        "   call liquid_end(lat,its,ite)\n   end subroutine kdm62d\n")
    return text.encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_bytes(prepare(args.source.read_bytes()))


if __name__ == "__main__":
    main()
