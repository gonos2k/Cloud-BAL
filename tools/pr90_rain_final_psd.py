#!/usr/bin/env python3
"""Add an exact final-stage rain PSD bound check to the pinned C6 source."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

C6_KDM6_SOURCE_SHA256 = "732510e4b3e9aa83654452aafb10ef717037457c10cf40d328287f8a767868be"

PSD_OPEN = """   pr85_psd_unit=-1
   if (pr67_trace_this_call) then
     open(newunit=pr85_psd_unit,file='pr85_kdm6_psd_boundary.raw', &
          form='formatted',status='unknown',position='append',action='write', &
          iostat=pr85_psd_ios)
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger open failed'
     write(pr85_psd_unit,'(a)',iostat=pr85_psd_ios) &
          '# PR85_KDM6_PSD_BOUNDARY species,stage,i,lat,k,side,Q,rhoDry,lambdaMin,lambdaMax,Nbefore,Nnative,Ndirected; '// &
          'nativeDelta,storageCorrection,exactNmin,exactNmax,legacyAvailable; '// &
          'Q kg/kgdry, rho kg/m3, lambda m-1, N #/m3; unavailable native numeric fields are zero'
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger header failed'
   endif
"""

PSD_CLOSE = """   if (pr67_trace_this_call) then
     close(pr85_psd_unit,iostat=pr85_psd_ios)
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger close failed'
   endif
"""

def add_exact_final_rain_bound_check(source: str) -> str:
    """Reconstruct an R64-invalid final rain pair missed by R32 slope rounding."""
    if hashlib.sha256(source.encode()).hexdigest() != C6_KDM6_SOURCE_SHA256:
        raise ValueError("expected the hash-pinned C6 KDM6 source")
    if source.count(PSD_OPEN) != 1 or source.count(PSD_CLOSE) != 1:
        raise ValueError("expected one conditional PSD ledger lifecycle")
    open_block = PSD_OPEN.replace("   if (pr67_trace_this_call) then\n", "", 1)
    open_block = open_block.rsplit("   endif\n", 1)[0]
    open_block += """   write(pr85_psd_unit,'(a,2i10)',iostat=pr85_psd_ios) &
        '# PR90_KDM6_PSD_BOUNDARY_CONTEXT timestep,lat',pr87_model_timestep,lat
   if (pr85_psd_ios.ne.0) error stop 'PR90 PSD boundary context failed'
"""
    source = source.replace(PSD_OPEN, open_block, 1)
    close_block = PSD_CLOSE.replace("   if (pr67_trace_this_call) then\n", "", 1)
    close_block = close_block.rsplit("   endif\n", 1)[0]
    source = source.replace(PSD_CLOSE, close_block, 1)

    trigger = "          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then\n"
    if source.count(trigger) != 3:
        raise ValueError("expected rain PSD gates at three KDM stages")
    stage_marker = "'rain','stage3',i,lat,k,pr85_psd_before"
    stage_positions = [
        pos for pos in range(len(source)) if source.startswith(stage_marker, pos)
    ]
    if len(stage_positions) != 2:
        raise ValueError("expected the existing final rain stage3 boundary calls")
    stage_pos = stage_positions[0]
    stage_start = source.rfind(trigger, 0, stage_pos)
    if stage_start < 0:
        raise ValueError("could not locate the final active rain PSD gate")
    target_end = source.find("            if( nrs(i,k,1).gt.nrmax ) then", stage_pos)
    if target_end < 0:
        raise ValueError("could not locate the final rain number cap")
    target = source[stage_start:target_end]
    if "'rain','stage3'" not in target or "'rain','stage2'" in target:
        raise ValueError("final rain PSD anchor is ambiguous")
    cap = """            if( nrs(i,k,1).gt.nrmax ) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = dry_carrier_density(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            endif
"""
    if source.count(cap) != 1:
        raise ValueError("expected one final rain number cap")
    correction = """            if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin) then
            pr85_psd_exact_min=(DBLE(dry_carrier_density(i,k))*DBLE(lamdarmin)**3) &
                 /DBLE(pidnr)*DBLE(qrs(i,k,1))
            pr85_psd_exact_max=(DBLE(dry_carrier_density(i,k))*DBLE(lamdarmax)**3) &
                 /DBLE(pidnr)*DBLE(qrs(i,k,1))
            if (DBLE(nrs(i,k,1)).lt.pr85_psd_exact_min) then
              lamdr_tmp(i,k)=lamdarmin
              pr85_psd_before=nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdarmin, &
                   lamdarmin,lamdarmax,pidnr,dmr,1, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,.true., &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 exact PSD lower number invalid'
              nrs(i,k,1)=pr85_psd_directed
            elseif (DBLE(nrs(i,k,1)).gt.pr85_psd_exact_max) then
              lamdr_tmp(i,k)=lamdarmax
              pr85_psd_before=nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdarmax, &
                   lamdarmin,lamdarmax,pidnr,dmr,2, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,.true., &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 exact PSD upper number invalid'
              nrs(i,k,1)=pr85_psd_directed
            endif
            endif
"""
    source = source.replace(cap, cap + correction, 1)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = add_exact_final_rain_bound_check(args.source.read_text())
    args.output.write_text(result)
    print(hashlib.sha256(result.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
