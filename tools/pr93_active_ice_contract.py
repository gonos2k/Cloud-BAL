#!/usr/bin/env python3
"""Connect native ice PSD reconstruction to its freezing consumer predicate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4"
PAIR_NAME = "pr93_kdm6_pair_in_cone"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def consumer_predicate(helper: str) -> tuple[str, str]:
    """Use the consumer's exact mean, operation order and existing eight ULPs."""
    match = re.search(r"(?im)^PURE LOGICAL FUNCTION in_cone\(.*?^END FUNCTION in_cone\s*$",
                      helper, re.S)
    if match is None:
        raise ValueError("freezing consumer predicate is missing")
    original = match.group().rstrip()
    shared = re.sub(r"\bin_cone\b", PAIR_NAME, original)
    first, rest = shared.split("\n", 1)
    imports = ("USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64\n"
               "USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite\n")
    return original, first + "\n" + imports + rest + "\n"


def share_consumer(source: str, helper: str) -> str:
    original, shared = consumer_predicate(helper)
    start = source.index("SUBROUTINE pr85_kdm6_freezing_packet(")
    end = source.index("END SUBROUTINE pr85_kdm6_freezing_packet", start)
    end += len("END SUBROUTINE pr85_kdm6_freezing_packet")
    packet = source[start:end]
    if packet.strip() != helper.strip():
        raise ValueError("compiled freezing helper differs from reviewed source")
    packet = packet.replace(original, "")
    packet = re.sub(r"\bin_cone\b", PAIR_NAME, packet)
    packet = packet.replace("LOGICAL, INTENT(OUT) :: base_valid,accepted",
                            "LOGICAL, INTENT(OUT) :: base_valid,accepted\n" +
                            "LOGICAL, EXTERNAL :: " + PAIR_NAME, 1)
    return source[:start] + shared + "\n" + packet + source[end:]


def connect_ice_reconstruction(source: str) -> str:
    """Complete each active-ice PSD producer before its stored state is consumed."""
    # Match the existing declaration rather than changing the module interface.
    match = re.search(r"(?im)^.*\blogical\b.*::[^\n]*\bpr85_psd_valid\b[^\n]*$", source)
    if match is None:
        raise ValueError("PSD local declaration is missing")
    declaration = match.group()
    source = source.replace(declaration, declaration + "\n" +
                            "   logical :: pr93_ice_pair_valid,pr93_ice_direct_repair\n" +
                            "   logical, external :: " + PAIR_NAME + "\n" +
                            "   real(8) :: pr93_ice_mean,pr93_ice_min,pr93_ice_max", 1)
    pattern = re.compile(r"(?im)^          if\(qci\(i,k,2\)[^\n]*then\n"
                         r"            lamdi_tmp\(i,k\).*?^          endif", re.S)
    blocks = list(pattern.finditer(source))
    if len(blocks) != 3:
        raise ValueError(f"expected three ice reconstruction blocks, found {len(blocks)}")
    for match in reversed(blocks):
        block = match.group()
        slope = "            lamdi_tmp(i,k) = exp(log"
        preflight = """            if (.not.all(ieee_is_finite([qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k)])) .or. nci(i,k,2).le.0.0 .or. &
                 dry_carrier_density(i,k).le.0.0) &
              error stop 'PR93 invalid active ice PSD input'
"""
        if block.count(slope) != 1:
            raise ValueError("ice slope producer is not unique")
        block = block.replace(slope, preflight + slope, 1)
        boundary = "            if(lamdi_tmp(i,k) .le. lamdaimin) then"
        if block.count(boundary) != 1:
            raise ValueError("ice lower-bound branch is not unique")
        check = """            pr93_ice_min=DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi))
            pr93_ice_max=DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi))
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            pr93_ice_mean=0.0d0
            if (.not.pr93_ice_pair_valid) then
              pr93_ice_mean=DBLE(dry_carrier_density(i,k))* &
                   DBLE(qci(i,k,2))/DBLE(nci(i,k,2))
            endif
            pr93_ice_direct_repair=lamdi_tmp(i,k).gt.lamdaimin .and. &
                 lamdi_tmp(i,k).lt.lamdaimax .and. .not.pr93_ice_pair_valid
            if(lamdi_tmp(i,k) .le. lamdaimin .or. &
                 (.not.pr93_ice_pair_valid .and. pr93_ice_mean.gt.pr93_ice_max)) then"""
        block = block.replace(boundary, check)
        block = block.replace("elseif(lamdi_tmp(i,k) .ge. lamdaimax) then",
                              "elseif(lamdi_tmp(i,k) .ge. lamdaimax .or. &\n"
                              "                 (.not.pr93_ice_pair_valid .and. &\n"
                              "                  pr93_ice_mean.lt.pr93_ice_min)) then")
        # Existing per-event PSD ledger, only the newly caught interior-slope
        # cases additionally emit rows. Counts/changes remain reconstruction,
        # distinct from physical activation and the freezing packet ledger.
        if block.count("pr85_psd_native_available,pr67_trace_this_call,") != 2:
            raise ValueError("ice boundary ledger arguments changed")
        block = block.replace("pr85_psd_native_available,pr67_trace_this_call,",
                              "pr85_psd_native_available, &\n"
                              "                   (pr67_trace_this_call.or.pr93_ice_direct_repair),")
        closing = """            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            if (.not.pr93_ice_pair_valid) &
              error stop 'PR93 ice PSD output failed consumer contract'
"""
        last = block.rfind("          endif")
        if last < 0:
            raise ValueError("ice reconstruction endpoint is missing")
        block = block[:last] + closing + block[last:]
        source = source[:match.start()] + block + source[match.end():]
    return source


def capture_ice_column(source: str, cell_i: int, call_j: int, timestep: int) -> str:
    """Record one diagnostic column around the unchanged sedimentation call."""
    if min(cell_i, call_j, timestep) <= 0:
        raise ValueError("diagnostic column and timestep must be positive")
    declaration = "   logical :: pr93_ice_pair_valid,pr93_ice_direct_repair"
    source = source.replace(declaration, declaration +
                            "\n   integer :: pr93_ice_k,pr93_ice_ios", 1)
    row = f"""            if (pr87_model_timestep.eq.{timestep} .and. lat.eq.{call_j} .and. i.eq.{cell_i}) then
              do pr93_ice_k=kts,kte
                write(pr85_psd_unit,'(a,7i8,3(1x,z8.8),1p,4e25.16e3)',iostat=pr93_ice_ios) &
                     'PR93_ICE_SED_BEFORE',pr87_model_timestep,i,lat,loop,n,mstep_i(i),pr93_ice_k, &
                     transfer(qci(i,pr93_ice_k,2),0),transfer(nci(i,pr93_ice_k,2),0), &
                     transfer(dend(i,pr93_ice_k),0),DBLE(delz(i,pr93_ice_k)), &
                     mass_velocity_rate(i,pr93_ice_k,4),number_velocity_rate(i,pr93_ice_k,2),DBLE(dtcld)
                if (pr93_ice_ios.ne.0) error stop 'PR93 ice column capture failed'
              enddo
            endif
"""
    before = "            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i),"
    after = "            if (.not.pr85_ice_valid) error stop 'PR85 ice sedimentation packet rejected'"
    if source.count(before) != 1 or source.count(after) != 1:
        raise ValueError("ice sedimentation source boundary changed")
    source = source.replace(before, row + before, 1)
    return source.replace(after, after + "\n" + row.replace("_BEFORE", "_AFTER"), 1)


def generate(source: Path, output: Path, trace_column: tuple[int, int] | None = None,
             trace_step: int = 24) -> dict:
    if sha256(source) != SOURCE_SHA256:
        raise ValueError("selected C18 KDM6 source identity mismatch")
    helper = ROOT / "tools/pr85_kdm6_freezing_packet.F90"
    result = connect_ice_reconstruction(share_consumer(source.read_text(), helper.read_text()))
    if trace_column is not None:
        result = capture_ice_column(result, *trace_column, trace_step)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result)
    return {"schema": "pr93_active_ice_source_v1", "source": str(source),
            "source_sha256": sha256(source), "freezing_helper": str(helper),
            "freezing_helper_sha256": sha256(helper), "output": str(output),
            "output_sha256": sha256(output), "active_ice_producers": 3,
            "shared_predicate": PAIR_NAME, "existing_ulp_allowance": 8,
            "diagnostic_column": trace_column, "diagnostic_timestep": trace_step if trace_column else None,
            "scope": "PSD reconstruction and freezing share the original consumer predicate; no physical freezing rate or tolerance changes"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trace-column", type=int, nargs=2, metavar=("I", "CALL_J"))
    parser.add_argument("--trace-step", type=int, default=24)
    args = parser.parse_args()
    args.manifest.write_text(json.dumps(generate(args.source, args.output, args.trace_column,
                                                args.trace_step), indent=2) + "\n")


if __name__ == "__main__":
    main()
