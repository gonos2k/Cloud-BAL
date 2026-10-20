#!/usr/bin/env python3
"""Add failed virtual-donor operand capture to the pinned C10 host overlay."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

C10_MODULE_SHA256 = "af54a8bd951e47407f6900dbfd4b16396cd6fc30753bb32437fd46c45b86be4c"
C10_SOLVE_SHA256 = "dd3d8436ec6e7712ea8b62a33502acf89832f2d8a9f45969f84968f06ff78ca6"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def transform_c10_module(source: str) -> str:
    c10 = source
    if sha256(c10) != C10_MODULE_SHA256:
        raise ValueError("input is not the pinned C10 module")
    anchor = "  INTEGER :: source_diff_cells,source_diff_u\n"
    if c10.count(anchor) != 1:
        raise ValueError("C10 diagnostic declaration anchor changed")
    c10 = c10.replace(anchor, anchor +
        "  INTEGER :: stage_diag_u,stage_diag_dx,stage_diag_dy\n"
        "  REAL(real64) :: stage_diag_qdiff,stage_diag_ndiff\n", 1)

    guard = """        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) &
          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')
"""
    capture = """        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) THEN
          ! Failed-call-only C11 capture. Recompute Dprepared for this exact pair/cell;
          ! the full-field workspace may currently belong to the other selected pair.
          CALL horizontal_diffusion64(prepared_q(:,:,:,p),mut_diff,c1,c2, &
               msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
               rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_diffusion)
          CALL horizontal_diffusion64(prepared_n(:,:,:,p),mut_diff,c1,c2, &
               msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
               rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_n_diffusion)
          stage_diag_qdiff=prepared_diffusion(i,k,j)
          stage_diag_ndiff=prepared_n_diffusion(i,k,j)
          OPEN(NEWUNIT=stage_diag_u,FILE='pr85_joint_source_failure.raw', &
               STATUS='UNKNOWN',POSITION='APPEND')
          WRITE(stage_diag_u,'(a,1x,6(i10,1x),2(z16.16,1x))') 'VIRTUAL_DONOR_STAGE',itimestep,rk,p,i,j,k, &
               TRANSFER(source_sum64(1),0_int64),TRANSFER(source_sum64(2),0_int64)
          WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_OPERANDS_R32', &
               TRANSFER(qb(cell,p),0_int32),TRANSFER(nb(cell,p),0_int32), &
               TRANSFER(oldcarrier(cell),0_int32),TRANSFER(newcarrier(cell),0_int32), &
               TRANSFER(drydensity(cell),0_int32),TRANSFER(dt,0_int32)
          WRITE(stage_diag_u,'(a,1x,2(z16.16,1x))') 'VDS_OPERANDS_R64', &
               TRANSFER(qs64(cell,p),0_int64),TRANSFER(ns64(cell,p),0_int64)
          WRITE(stage_diag_u,'(a,1x,12(z16.16,1x))') 'VDS_SOURCE_DIFFUSION', &
               TRANSFER(pr87_later_qsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_later_nsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p),0_int64), &
               TRANSFER(stage_diag_qdiff,0_int64),TRANSFER(stage_diag_ndiff,0_int64), &
               TRANSFER(minmass(p),0_int64),TRANSFER(maxmass(p),0_int64), &
               TRANSFER(number_bounds(cell,1,p),0_int64),TRANSFER(number_bounds(cell,2,p),0_int64)
          ! 3x3 prepared REAL32 stencil, same k; each row is dx=-1,0,+1 and dy.
          DO stage_diag_dy=-1,1
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_Q_STENCIL',itimestep,p,stage_diag_dy, &
              (TRANSFER(prepared_q(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
               stage_diag_dx=-1,1)
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_N_STENCIL',itimestep,p,stage_diag_dy, &
              (TRANSFER(prepared_n(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
               stage_diag_dx=-1,1)
          END DO
          WRITE(stage_diag_u,'(a,1x,3(z8.8,1x))') 'VDS_DIFFUSIVITY', &
               TRANSFER(mut_diff(i,j),0_int32),TRANSFER(c1(k),0_int32),TRANSFER(c2(k),0_int32)
          DO stage_diag_dy=-1,1
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),6(z8.8,1x))') 'VDS_GEOMETRY_X',itimestep,p,stage_diag_dy, &
              (TRANSFER(xkmhd_diff(i+stage_diag_dx,k,j+stage_diag_dy),0_int32), &
               stage_diag_dx=-1,1), &
              (TRANSFER(mut_diff(i+stage_diag_dx,j+stage_diag_dy),0_int32),stage_diag_dx=-1,1)
          END DO
          WRITE(stage_diag_u,'(a,1x,10(z8.8,1x))') 'VDS_GEOMETRY_FACE', &
               TRANSFER(msfux_diff(i,j),0_int32),TRANSFER(msfux_diff(i+1,j),0_int32), &
               TRANSFER(msfuy_diff(i,j),0_int32),TRANSFER(msfuy_diff(i+1,j),0_int32), &
               TRANSFER(msfvx_inv_diff(i,j-1),0_int32),TRANSFER(msfvx_inv_diff(i,j),0_int32), &
               TRANSFER(msfvx_inv_diff(i,j+1),0_int32), &
               TRANSFER(msfvy_diff(i,j),0_int32),TRANSFER(msfvy_diff(i,j+1),0_int32)
          WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_GEOMETRY_Y', &
               TRANSFER(msfvy_diff(i,j-1),0_int32),TRANSFER(msfvy_diff(i,j),0_int32), &
               TRANSFER(msfvy_diff(i,j+1),0_int32),TRANSFER(msftx(i,j),0_int32), &
               TRANSFER(msfty(i,j),0_int32),TRANSFER(rdx,0_int32)
          WRITE(stage_diag_u,'(a,1x,z8.8,1x)') 'VDS_RDY',TRANSFER(rdy,0_int32)
          CLOSE(stage_diag_u)
          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')
        END IF
"""
    if c10.count(guard) != 1:
        raise ValueError("C10 virtual-donor failure guard changed")
    return c10.replace(guard, capture, 1)


def transform_files(module_path: Path, solve_path: Path,
                    module_output: Path, solve_output: Path) -> dict[str, str]:
    source = module_path.read_text()
    module = transform_c10_module(source)
    solve = solve_path.read_text()
    if sha256(solve) != C10_SOLVE_SHA256:
        raise ValueError("input is not the pinned C10 solve source")
    if module_output.exists() or solve_output.exists():
        raise FileExistsError("C11 outputs exist; refusing to overwrite")
    module_output.parent.mkdir(parents=True, exist_ok=True)
    solve_output.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for path, content in ((module_output, module), (solve_output, solve)):
            with path.open("x") as stream:
                created.append(path)
                stream.write(content)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {"module_sha256": sha256(module), "solve_sha256": sha256(solve),
            "module_output": str(module_output), "solve_output": str(solve_output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--solve", required=True, type=Path)
    parser.add_argument("--module-output", required=True, type=Path)
    parser.add_argument("--solve-output", required=True, type=Path)
    args = parser.parse_args()
    for key, value in transform_files(args.module, args.solve, args.module_output, args.solve_output).items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
