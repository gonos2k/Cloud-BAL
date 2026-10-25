#!/usr/bin/env python3
"""Generate a standalone driver around the hash-pinned native diffusion routine."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import struct
from pathlib import Path

from pr101_upper_wind_replay import Record, read_records


DIFFUSION_SOURCE = Path(
    "/var/tmp/pr61_ccn_origin_20261006/hostcopy/"
    "dyn_em/module_big_step_utilities_em.F"
)
DIFFUSION_SOURCE_SHA256 = "27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c"


def f90(value: float) -> str:
    return f"{float(value):.17E}"


def real32_bits(value: float) -> str:
    bits = struct.unpack(">I", struct.pack(">f", float(value)))[0]
    return f"INT(Z'{bits:08X}',int32)"


def extract_routine(source: str) -> str:
    starts = list(re.finditer(r"(?m)^SUBROUTINE horizontal_diffusion \(", source))
    ends = list(re.finditer(r"(?m)^END SUBROUTINE horizontal_diffusion$", source))
    if len(starts) != 1 or len(ends) != 1 or ends[0].start() < starts[0].start():
        raise ValueError("expected one complete horizontal_diffusion routine")
    return source[starts[0].start():ends[0].end()]


def _paired_records(capture: Path) -> list[tuple[Record, Record]]:
    grouped: dict[tuple[str, int, int, int, int], dict[int, Record]] = {}
    for rec in read_records(capture):
        key = rec.component, rec.face_i, rec.face_j, rec.time_step, rec.rk_step
        phases = grouped.setdefault(key, {})
        if rec.phase in phases:
            raise ValueError(f"duplicate capture phase for {key}")
        phases[rec.phase] = rec
    pairs = []
    for key, phases in sorted(grouped.items()):
        if set(phases) != {1, 2}:
            raise ValueError(f"incomplete PRE/POST records for {key}")
        before, after = phases[1], phases[2]
        if (before.bounds, before.flags, before.rk_step, before.time_step) != \
           (after.bounds, after.flags, after.rk_step, after.time_step):
            raise ValueError("event metadata changed between PRE and POST")
        if (before.diff_opt, before.km_opt, before.diff_6th_opt) != \
           (after.diff_opt, after.km_opt, after.diff_6th_opt):
            raise ValueError("diffusion options changed between PRE and POST")
        for rec in (before, after):
            floats = [rec.khdif, rec.rdx, rec.rdy, *rec.c1.values(), *rec.c2.values(),
                      *rec.values.values(), *rec.xkmhd.values(), *rec.tendency.values()]
            floats.extend(value for row in rec.metrics.values() for value in row.values())
            if any(not math.isfinite(float(value)) for value in floats):
                raise ValueError(f"non-finite operand in capture event {key}")
        if (before.c1, before.c2, before.values, before.xkmhd, before.metrics,
            before.khdif, before.rdx, before.rdy) != \
           (after.c1, after.c2, after.values, after.xkmhd, after.metrics,
            after.khdif, after.rdx, after.rdy):
            raise ValueError("diffusion input operands changed between PRE and POST")
        if before.diff_opt != 1:
            raise ValueError("capture event was not in the native diff_opt=1 branch")
        pairs.append((before, after))
    if not pairs:
        raise ValueError("capture file has no paired call records")
    reference = pairs[0][0]
    if any((before.bounds, before.flags) != (reference.bounds, reference.flags)
           for before, _ in pairs[1:]):
        raise ValueError("capture events have different domain or tile bounds")
    return pairs


def _block(before: Record, after: Record, number: int) -> str:
    b, f, i, j = before.bounds, before.flags, before.face_i, before.face_j
    lines = [f"  ! Capture pair {number}: {before.component.upper()} face ({i},{j}), "
             f"time_step={before.time_step}, rk_step={before.rk_step}",
             "  field=0.0; tendency=0.0; xkmhd=0.0; mut=0.0",
             "  c1=0.0; c2=1.0",
             "  msfux=1.0; msfuy=1.0; msfvx=1.0; msfvx_inv=1.0",
             "  msfvy=1.0; msftx=1.0; msfty=1.0",
             f"  config_flags%open_xs={'.TRUE.' if f['open_xs'] else '.FALSE.'}",
             f"  config_flags%open_xe={'.TRUE.' if f['open_xe'] else '.FALSE.'}",
             f"  config_flags%open_ys={'.TRUE.' if f['open_ys'] else '.FALSE.'}",
             f"  config_flags%open_ye={'.TRUE.' if f['open_ye'] else '.FALSE.'}",
             f"  config_flags%specified={'.TRUE.' if f['specified'] else '.FALSE.'}",
             f"  config_flags%nested={'.TRUE.' if f['nested'] else '.FALSE.'}",
             f"  config_flags%periodic_x={'.TRUE.' if f['periodic_x'] else '.FALSE.'}",
             f"  config_flags%polar={'.TRUE.' if f['polar'] else '.FALSE.'}"]
    for k in (37, 38, 39):
        lines.extend((f"  c1({k})={f90(before.c1[k])}; c2({k})={f90(before.c2[k])}",
                      f"  tendency({i},{k},{j})={f90(before.tendency[k])}"))
        for jj in range(j-1, j+2):
            for ii in range(i-1, i+2):
                lines.append(f"  field({ii},{k},{jj})={f90(before.values[ii,k,jj])}; "
                             f"xkmhd({ii},{k},{jj})={f90(before.xkmhd[ii,k,jj])}")
    for (ii, jj), values in before.metrics.items():
        lines.append(f"  mut({ii},{jj})={f90(values['mut'])}")
        for name in ("msfux", "msfuy", "msfvx", "msfvx_inv", "msfvy", "msftx", "msfty"):
            lines.append(f"  {name}({ii},{jj})={f90(values[name])}")
    lines.extend((f"  khdif={f90(before.khdif)}; rdx={f90(before.rdx)}; rdy={f90(before.rdy)}",
                  f"  CALL horizontal_diffusion('{before.component}', field, tendency, mut, c1, c2, &",
                  "       config_flags, msfux, msfuy, msfvx, msfvx_inv, msfvy, msftx, msfty, &",
                  "       khdif, xkmhd, rdx, rdy, &",
                  "       ids, ide, jds, jde, kds, kde, ims, ime, jms, jme, kms, kme, &",
                  "       its, ite, jts, jte, kts, kte)") )
    for k in (37, 38, 39):
        lines.extend((f"  expected_bits={real32_bits(after.tendency[k])}",
                      f"  IF (TRANSFER(tendency({i},{k},{j}),0_int32) /= expected_bits) THEN",
                      f"    WRITE(error_unit,'(A,1X,A,1X,3(I0,1X))') 'PR101_REPLAY_MISMATCH', &",
                      f"      '{before.component.upper()}', {i}, {k}, {j}",
                      "    ERROR STOP 1",
                      "  END IF",
                      f"  WRITE(result_unit,'(A,1X,5(I0,1X),Z8.8)') &",
                      f"    '{before.component.upper()}', {i}, {k}, {j}, {before.time_step}, {before.rk_step}, &",
                      f"    TRANSFER(tendency({i},{k},{j}),0_int32)"))
    return "\n".join(lines)


def generate(capture: Path, source_path: Path = DIFFUSION_SOURCE) -> str:
    source_bytes = source_path.read_bytes()
    actual_sha = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha != DIFFUSION_SOURCE_SHA256:
        raise ValueError(f"diffusion source hash mismatch: {actual_sha}")
    routine = extract_routine(source_bytes.decode("utf-8"))
    pairs = _paired_records(capture)
    first = pairs[0][0]
    b = first.bounds
    declarations = f"""PROGRAM pr101_source_replay
  USE pr101_standalone_hdiff, ONLY: horizontal_diffusion, grid_config_rec_type
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32, error_unit
  IMPLICIT NONE
  TYPE(grid_config_rec_type) :: config_flags
  INTEGER :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte,k
  INTEGER :: expected_bits, result_unit
  REAL, ALLOCATABLE :: field(:,:,:), tendency(:,:,:), xkmhd(:,:,:)
  REAL, ALLOCATABLE :: mut(:,:), msfux(:,:), msfuy(:,:), msfvx(:,:), msfvx_inv(:,:)
  REAL, ALLOCATABLE :: msfvy(:,:), msftx(:,:), msfty(:,:), c1(:), c2(:)
  REAL :: khdif, rdx, rdy
  CHARACTER(LEN=*), PARAMETER :: result_file='pr101_upper_wind_fortran_replay.txt'
"""
    for name in ("ids","ide","jds","jde","kds","kde","ims","ime","jms","jme",
                 "kms","kme","its","ite","jts","jte","kts","kte"):
        declarations += f"  {name}={b[name]}\n"
    declarations += f"""  OPEN(NEWUNIT=result_unit,FILE=result_file,STATUS='REPLACE',ACTION='WRITE')
  WRITE(result_unit,'(A)') 'PR101_UPPER_WIND_FORTRAN_REPLAY_RESULT v1 time_step_seconds'
  ALLOCATE(field(ims:ime,kms:kme,jms:jme), tendency(ims:ime,kms:kme,jms:jme), &
    xkmhd(ims:ime,kms:kme,jms:jme), mut(ims:ime,jms:jme), msfux(ims:ime,jms:jme), &
    msfuy(ims:ime,jms:jme), msfvx(ims:ime,jms:jme), msfvx_inv(ims:ime,jms:jme), &
    msfvy(ims:ime,jms:jme), msftx(ims:ime,jms:jme), msfty(ims:ime,jms:jme), c1(kms:kme), c2(kms:kme))
"""
    blocks = "\n".join(_block(before, after, n+1) for n, (before, after) in enumerate(pairs))
    type_module = """MODULE pr101_standalone_hdiff
  IMPLICIT NONE
  TYPE :: grid_config_rec_type
    LOGICAL :: specified, nested, open_xs, open_xe, open_ys, open_ye, periodic_x, polar
  END TYPE grid_config_rec_type
CONTAINS
""" + routine + "\nEND MODULE pr101_standalone_hdiff\n"
    return (f"! Diffusion source SHA256: {actual_sha}\n"
            f"! Capture SHA256: {hashlib.sha256(capture.read_bytes()).hexdigest()}\n" +
            type_module + "\n" + declarations + blocks +
            "\n  WRITE(result_unit,'(A)') 'PR101_UPPER_WIND_FORTRAN_REPLAY_PASS v1'\n"
            "  CLOSE(result_unit)\n"
            "  WRITE(*,'(A)') 'PR101_UPPER_WIND_FORTRAN_REPLAY_PASS v1'\n"
            "END PROGRAM pr101_source_replay\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--source", type=Path, default=DIFFUSION_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = generate(args.capture, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"wrote {args.output} ({hashlib.sha256(output.encode()).hexdigest()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
