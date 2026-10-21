#!/usr/bin/env python3
"""Prepare a bounded, read-only observer overlay from the frozen C1 sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
C1_RECEIPT = Path("/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json")
C1_RECEIPT_SHA256 = "ac7b1cbefc2cbbf128b7bbe08573d79b575b3b50d51db3a955f1bb0d6d02ae56"

OBSERVER = r'''SUBROUTINE pr98_dump3(tag,a,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
  REAL, INTENT(IN) :: a(ims:ime,kms:kme,jms:jme)
  CHARACTER(160), SAVE :: seen(512)
  INTEGER, SAVE :: nseen=0
  CHARACTER(160) :: key
  CHARACTER(32) :: tile
  INTEGER :: unit, q
  WRITE(tile,'(6(I0,"_"))') its,ite,jts,jte,kts,kte
  key=TRIM(tag)//'_'//TRIM(tile)
  DO q=1,nseen
    IF (TRIM(seen(q)) == TRIM(key)) RETURN
  END DO
  IF (nseen >= SIZE(seen)) RETURN
  nseen=nseen+1
  seen(nseen)=key
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(key)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump3

SUBROUTINE pr98_dump2(tag,a,ims,ime,jms,jme,its,ite,jts,jte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: ims,ime,jms,jme,its,ite,jts,jte
  REAL, INTENT(IN) :: a(ims:ime,jms:jme)
  CHARACTER(160), SAVE :: seen(512)
  INTEGER, SAVE :: nseen=0
  CHARACTER(160) :: key
  CHARACTER(32) :: tile
  INTEGER :: unit, q
  WRITE(tile,'(4(I0,"_"))') its,ite,jts,jte
  key=TRIM(tag)//'_'//TRIM(tile)
  DO q=1,nseen
    IF (TRIM(seen(q)) == TRIM(key)) RETURN
  END DO
  IF (nseen >= SIZE(seen)) RETURN
  nseen=nseen+1
  seen(nseen)=key
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(key)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) ims,ime,jms,jme,its,ite,jts,jte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump2

SUBROUTINE pr98_dump1(tag,a,kms,kme,kts,kte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: kms,kme,kts,kte
  REAL, INTENT(IN) :: a(kms:kme)
  INTEGER :: unit
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(tag)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) kms,kme,kts,kte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump1

SUBROUTINE pr98_dump0(tag,value)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  REAL, INTENT(IN) :: value
  LOGICAL, SAVE :: done=.FALSE.
  INTEGER :: unit
  IF (done) RETURN
  done=.TRUE.
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(tag)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) value
  CLOSE(unit)
END SUBROUTINE pr98_dump0
'''


def call_end(source: str, start: int) -> int:
    """Return the end of a possibly continued CALL statement."""
    opening = source.find("(", start)
    if opening < 0:
        raise ValueError("CALL without argument list")
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "(":
            depth += 1
        elif source[pos] == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
    raise ValueError("unclosed CALL argument list")


def source_calls(source: str, pattern: str, tag: str, vars_: tuple[str, ...], ndim: int) -> str:
    bounds = "ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte" if ndim == 3 else \
             "ims,ime,jms,jme,its,ite,jts,jte"
    updated = source
    matches = list(re.finditer(pattern, source, flags=re.IGNORECASE))
    for match in reversed(matches):
        begin = match.start()
        end = call_end(source, begin)
        before = ""
        if tag == "advu":
            metrics = ("msfuy", "msfvx_inv", "msfty", "msfux", "msfvx", "msfvy",
                       "msftx", "mut", "mu", "muu", "muv")
            before += "".join(
                f"\n      CALL pr98_dump2('geom_{name}',{name},ims,ime,jms,jme,its,ite,jts,jte)"
                for name in metrics)
            before += "\n      CALL pr98_dump1('geom_c1h',c1h,kms,kme,kts,kte)"
            before += "\n      CALL pr98_dump1('geom_c2h',c2h,kms,kme,kts,kte)"
        before += "".join(f"\n      CALL pr98_dump{ndim}('{tag}_{v}_in',{v},{bounds})" for v in vars_)
        after = "".join(f"\n      CALL pr98_dump{ndim}('{tag}_{v}_out',{v},{bounds})" for v in vars_)
        # Place the pre-capture before the CALL and post-capture after its closing parenthesis.
        updated = updated[:end] + after + updated[end:]
        updated = updated[:begin] + before + "\n      " + updated[begin:]
    return updated


def transform(module_source: str, solve_source: str) -> tuple[str, str]:
    original_calls = re.findall(r"(?im)^\s*CALL\s+(?:advect_[uvw]|advect_weno_[uv])\s*\(", module_source)
    if len(original_calls) < 5 or "SUBROUTINE rk_tendency" not in module_source:
        raise ValueError("receipt-bound module_em source does not match the expected C1 operator source")
    result = module_source
    specs = [
        (r"(?im)^\s*CALL\s+(?:advect_u|advect_weno_u)\s*\(", "advu", ("ru_tend",)),
        (r"(?im)^\s*CALL\s+(?:advect_v|advect_weno_v)\s*\(", "advv", ("rv_tend",)),
        (r"(?im)^\s*CALL\s+(?:advect_w|advect_weno_w)\s*\(", "advw", ("rw_tend",)),
        (r"(?im)^\s*CALL\s+horizontal_pressure_gradient\s*\(", "pgrad", ("ru_tend", "rv_tend")),
        (r"(?im)^\s*CALL\s+(?:perturbation_coriolis|coriolis)\s*\(", "coriolis", ("ru_tend", "rv_tend", "rw_tend")),
        (r"(?im)^\s*CALL\s+curvature\s*\(", "curvature", ("ru_tend", "rv_tend", "rw_tend")),
        (r"(?im)^\s*CALL\s+horizontal_diffusion\s*\(\s*'u'", "hdifu", ("ru_tendf",)),
        (r"(?im)^\s*CALL\s+horizontal_diffusion\s*\(\s*'v'", "hdifv", ("rv_tendf",)),
        (r"(?im)^\s*CALL\s+horizontal_diffusion\s*\(\s*'w'", "hdifw", ("rw_tendf",)),
        (r"(?im)^\s*CALL\s+vertical_diffusion_u\s*\(", "vdifu", ("ru_tendf",)),
        (r"(?im)^\s*CALL\s+vertical_diffusion_v\s*\(", "vdifv", ("rv_tendf",)),
    ]
    for pattern, tag, names in specs:
        result = source_calls(result, pattern, tag, names, 3)
    end_rk = re.search(r"(?im)^END\s+SUBROUTINE\s+rk_tendency", result)
    if not end_rk:
        raise ValueError("could not locate end of rk_tendency")
    bounds3 = "ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte"
    final = "".join(
        f"\n   CALL pr98_dump3('dyn_{name}_final',{name}_tend,{bounds3})"
        for name in ("ru", "rv", "rw"))
    result = result[:end_rk.start()] + final + "\n" + result[end_rk.start():]
    if result == module_source:
        raise ValueError("no momentum operator sites were instrumented")
    # `rk_addtend_dry` is instrumented immediately around the native call at solve_em.
    call_match = re.search(r"(?im)^\s*CALL\s+rk_addtend_dry\s*\(", solve_source)
    if not call_match:
        raise ValueError("could not locate native rk_addtend_dry call")
    end = call_end(solve_source, call_match.start())
    bounds3 = "ims,ime,kms,kme,jms,jme,grid%i_start(ij),grid%i_end(ij),k_start,k_end,grid%j_start(ij),grid%j_end(ij)"
    bounds2 = "ims,ime,jms,jme,grid%i_start(ij),grid%i_end(ij),grid%j_start(ij),grid%j_end(ij)"
    names = ("grid%ru_tend", "grid%rv_tend", "rw_tend")
    pre = "".join(f"\n       CALL pr98_dump3('assembled_{name.split('%')[-1]}_in',{name},{bounds3})" for name in names)
    post = "".join(f"\n       CALL pr98_dump3('assembled_{name.split('%')[-1]}_out',{name},{bounds3})" for name in names)
    pre += f"\n       CALL pr98_dump2('mu_large_in',mu_tend,{bounds2})"
    post += f"\n       CALL pr98_dump2('mu_large_out',mu_tend,{bounds2})"
    solve_updated = solve_source[:end] + post + solve_source[end:]
    solve_updated = solve_updated[:call_match.start()] + pre + "\n       " + solve_updated[call_match.start():]
    # Capture the actual small-step mass state around its real update call.
    advance = re.search(r"(?im)^\s*CALL\s+advance_mu_t\s*\(", solve_updated)
    if not advance:
        raise ValueError("could not locate native advance_mu_t call")
    end = call_end(solve_updated, advance.start())
    bounds = "ims,ime,jms,jme,grid%i_start(ij),grid%i_end(ij),grid%j_start(ij),grid%j_end(ij)"
    after = f"\n         CALL pr98_dump2('mu_small_out',grid%mu_2,{bounds})"
    after += f"\n         CALL pr98_dump2('mu_tend_small',mu_tend,{bounds})"
    before = f"\n         CALL pr98_dump2('mu_small_in',grid%mu_2,{bounds})"
    before += "\n         CALL pr98_dump0('dts_small',dts_rk)"
    after += f"\n         CALL pr98_dump2('mudf_small_out',grid%mudf,{bounds})"
    solve_updated = solve_updated[:end] + after + solve_updated[end:]
    solve_updated = solve_updated[:advance.start()] + before + "\n         " + solve_updated[advance.start():]
    return result, solve_updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(C1_RECEIPT.read_bytes()).hexdigest() != C1_RECEIPT_SHA256:
        raise ValueError("frozen C1 build receipt hash mismatch")
    receipt = json.loads(C1_RECEIPT.read_text())
    rows = {row["member"]: row for row in receipt["compiled_overrides"]}
    for member in ("module_em.o", "solve_em.o"):
        row = rows[member]
        source = Path(row["source_path"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["source_sha256"]:
            raise ValueError(f"frozen C1 source hash mismatch: {member}")
    module = Path(rows["module_em.o"]["source_path"]).read_text()
    solve = Path(rows["solve_em.o"]["source_path"]).read_text()
    module_out, solve_out = transform(module, solve)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "module_em.F").write_text(module_out)
    (args.out / "solve_em.F").write_text(solve_out)
    (args.out / "pr98_native_observer.f90").write_text(OBSERVER)
    print(json.dumps({"output": str(args.out), "module_em_bytes": len(module_out),
                      "solve_em_bytes": len(solve_out), "observer_bytes": len(OBSERVER)}, indent=2))


if __name__ == "__main__":
    main()
