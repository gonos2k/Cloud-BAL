#!/usr/bin/env python3
"""Transform pinned C8 sources to use source-prepared paired diffusion once."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

MODULE_SHA256 = "de21c8b0aad8c99ae1ed7de4e0e4fc77ebfc6050f998754c7ee6c3d27bfc90a2"
SOLVE_SHA256 = "412183300ea8dd6af028ac1a5254f937477b054630db4eb1f5910a6bf974c3c5"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return text.replace(old, new, 1)


def transform_module(source: str) -> str:
    if "PR91_SOURCE_DIFFUSION_C9" in source:
        raise ValueError("C9 transform already applied")
    source = replace_once(
        source,
        "its, ite, jts, jte, kts, kte, all_pair_diffusion_delta )",
        "its, ite, jts, jte, kts, kte, all_pair_diffusion_delta, &\n"
        "                            all_pair_diffusion_old, all_pair_diffusion_identity, &\n"
        "                            all_pair_diffusion_valid )",
        "diffusion producer interface",
    )
    source = replace_once(
        source,
        "   REAL(real64), OPTIONAL, INTENT(INOUT) :: &\n"
        "      all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)\n",
        "   REAL(real64), OPTIONAL, INTENT(INOUT) :: &\n"
        "      all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8), &\n"
        "      all_pair_diffusion_old(ims:ime,kms:kme,jms:jme,4)\n"
        "   INTEGER, OPTIONAL, INTENT(INOUT) :: all_pair_diffusion_identity(8), &\n"
        "      all_pair_diffusion_valid(8)\n",
        "diffusion producer cache declarations",
    )
    source = replace_once(
        source,
        "           pr87_diff_k_end = MIN(kte,kde-1)\n",
        "           pr87_diff_k_end = MIN(kte,kde-1)\n"
        "           IF ((PRESENT(all_pair_diffusion_old) .NEQV. &\n"
        "                PRESENT(all_pair_diffusion_identity)).OR. &\n"
        "               (PRESENT(all_pair_diffusion_old) .NEQV. &\n"
        "                PRESENT(all_pair_diffusion_valid))) &\n"
        "             CALL wrf_error_fatal('PR91 incomplete source diffusion cache')\n"
        "           IF (PRESENT(all_pair_diffusion_old)) THEN\n"
        "             IF (ANY(all_pair_diffusion_valid/=0).AND. &\n"
        "                 ANY(all_pair_diffusion_identity(2:8)/=[rk_step,pr87_diff_i_start, &\n"
        "                     pr87_diff_i_end,pr87_diff_j_start,pr87_diff_j_end,kts,pr87_diff_k_end])) &\n"
        "               CALL wrf_error_fatal('PR91 producer diffusion bounds changed within RK1')\n"
        "             all_pair_diffusion_identity(2:8) = [rk_step,pr87_diff_i_start, &\n"
        "                 pr87_diff_i_end,pr87_diff_j_start,pr87_diff_j_end,kts,pr87_diff_k_end]\n"
        "           END IF\n",
        "diffusion producer identity",
    )
    source = replace_once(
        source,
        "                 all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &\n"
        "                                      pr87_diff_channel) = &\n"
        "                      REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &\n"
        "                      pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j) - &\n"
        "                      REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)\n",
        "                 all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &\n"
        "                                      pr87_diff_channel) = &\n"
        "                      REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &\n"
        "                      pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j) - &\n"
        "                      REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)\n"
        "                 IF (PRESENT(all_pair_diffusion_old).AND.pr87_diff_channel<=4) &\n"
        "                   all_pair_diffusion_old(pr87_diff_i,pr87_diff_k,pr87_diff_j, &\n"
        "                                          pr87_diff_channel) = &\n"
        "                        pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j)\n"
        "                 IF (PRESENT(all_pair_diffusion_valid).AND.pr87_diff_channel<=4) &\n"
        "                   all_pair_diffusion_valid(pr87_diff_channel)=1\n",
        "old REAL64 diffusion cache capture",
    )
    source = replace_once(
        source,
        "     mut_diff,xkmhd_diff,msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff)\n",
        "     mut_diff,xkmhd_diff,msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff, &\n"
        "     pr87_all_pair_diffusion_old,pr87_all_pair_diffusion_identity, &\n"
        "     pr87_all_pair_diffusion_valid) ! PR91_SOURCE_DIFFUSION_C9\n",
        "joint updater signature",
    )
    source = replace_once(
        source,
        "  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite\n  IMPLICIT NONE\n",
        "  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite\n"
        "  USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64\n  IMPLICIT NONE\n",
        "joint updater diffusion helper import",
    )
    source = replace_once(
        source,
        "  REAL(real64),INTENT(IN),OPTIONAL :: &\n"
        "       pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)\n",
        "  REAL(real64),INTENT(IN),OPTIONAL :: &\n"
        "       pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)\n"
        "  REAL(real64),INTENT(IN),OPTIONAL :: &\n"
        "       pr87_all_pair_diffusion_old(ims:ime,kms:kme,jms:jme,4)\n"
        "  INTEGER,INTENT(IN),OPTIONAL :: pr87_all_pair_diffusion_identity(8), &\n"
        "       pr87_all_pair_diffusion_valid(8)\n",
        "joint updater cache declarations",
    )
    source = replace_once(
        source,
        "  REAL(real64),ALLOCATABLE :: donor_q(:,:,:,:),donor_n(:,:,:,:)\n",
        "  REAL(real64),ALLOCATABLE :: donor_q(:,:,:,:),donor_n(:,:,:,:)\n"
        "  REAL,ALLOCATABLE :: prepared_q(:,:,:,:),prepared_n(:,:,:,:)\n"
        "  REAL(real64),ALLOCATABLE :: prepared_diffusion(:,:,:),prepared_n_diffusion(:,:,:)\n"
        "  REAL(real64) :: source_diff_delta(2),source_diff_sum(2),source_diff_l1(2),source_diff_max(2)\n"
        "  INTEGER :: source_diff_cells,source_diff_u\n",
        "prepared-field work arrays",
    )
    source = replace_once(
        source,
        "  IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "    IF (pr87_all_pair_diffusion_step /= itimestep) &\n"
        "      CALL wrf_error_fatal('PR87 rain diffusion timestep mismatch')\n"
        "  END IF\n",
        "  IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "    IF (pr87_all_pair_diffusion_step /= itimestep) &\n"
        "      CALL wrf_error_fatal('PR87 rain diffusion timestep mismatch')\n"
        "  END IF\n"
        "  IF ((PRESENT(pr87_all_pair_diffusion_old) .NEQV. &\n"
        "       PRESENT(pr87_all_pair_diffusion_identity)).OR. &\n"
        "      (PRESENT(pr87_all_pair_diffusion_old) .NEQV. &\n"
        "       PRESENT(pr87_all_pair_diffusion_valid))) &\n"
        "    CALL wrf_error_fatal('PR91 incomplete source diffusion cache')\n"
        "  IF (PRESENT(pr87_all_pair_diffusion_old)) THEN\n"
        "    IF (pr87_all_pair_diffusion_identity(1)/=itimestep.OR. &\n"
        "        pr87_all_pair_diffusion_identity(2)/=1.OR. &\n"
        "        pr87_all_pair_diffusion_identity(3)<ims+1.OR. &\n"
        "        pr87_all_pair_diffusion_identity(4)>ime-1.OR. &\n"
        "        pr87_all_pair_diffusion_identity(5)<jms+1.OR. &\n"
        "        pr87_all_pair_diffusion_identity(6)>jme-1.OR. &\n"
        "        pr87_all_pair_diffusion_identity(7)<kms.OR. &\n"
        "        pr87_all_pair_diffusion_identity(8)>kme) &\n"
        "      CALL wrf_error_fatal('PR91 source diffusion cache identity mismatch')\n"
        "  END IF\n",
        "source diffusion identity validation",
    )
    source = replace_once(
        source,
        "  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &\n"
        "    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')\n",
        "  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &\n"
        "    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')\n"
        "  IF (PRESENT(pr87_all_pair_diffusion_identity)) THEN\n"
        "    IF (pr87_all_pair_diffusion_identity(3)<il.OR.pr87_all_pair_diffusion_identity(4)>ih.OR. &\n"
        "        pr87_all_pair_diffusion_identity(5)<jl.OR.pr87_all_pair_diffusion_identity(6)>jh.OR. &\n"
        "        pr87_all_pair_diffusion_identity(7)<kl.OR.pr87_all_pair_diffusion_identity(8)>kh) &\n"
        "      CALL wrf_error_fatal('PR91 diffusion bounds differ from prepared source footprint')\n"
        "  END IF\n",
        "source diffusion/update active-bounds agreement",
    )
    source = replace_once(
        source,
        "    DO p=1,2\n"
        "      IF (.NOT.source_first_pair(p)) CYCLE\n"
        "      donor_q(:,:,:,p)=REAL(q1(:,:,:,qindex(p)),real64)\n"
        "      donor_n(:,:,:,p)=REAL(n1(:,:,:,nindex(p)),real64)\n"
        "    END DO\n",
        "    ALLOCATE(prepared_q(ims:ime,kms:kme,jms:jme,2), &\n"
        "             prepared_n(ims:ime,kms:kme,jms:jme,2), &\n"
        "             prepared_diffusion(ims:ime,kms:kme,jms:jme), &\n"
        "             prepared_n_diffusion(ims:ime,kms:kme,jms:jme))\n"
        "    DO p=1,2\n"
        "      prepared_q(:,:,:,p)=q1(:,:,:,qindex(p))\n"
        "      prepared_n(:,:,:,p)=n1(:,:,:,nindex(p))\n"
        "      IF (.NOT.source_first_pair(p)) CYCLE\n"
        "      donor_q(:,:,:,p)=REAL(q1(:,:,:,qindex(p)),real64)\n"
        "      donor_n(:,:,:,p)=REAL(n1(:,:,:,nindex(p)),real64)\n"
        "    END DO\n",
        "prepared full-field initialization",
    )
    source = replace_once(
        source,
        "        ! RK1 adds weighted diffusion/diabatic/boundary tendencies after physics coupling.\n",
        "        prepared_q(i,k,j,p)=source_endpoint32(1)\n"
        "        prepared_n(i,k,j,p)=source_endpoint32(2)\n"
        "        ! RK1 adds weighted diffusion/diabatic/boundary tendencies after physics coupling.\n",
        "stored physical source endpoint copy",
    )
    source = replace_once(
        source,
        "        ! Match the canonical no-air consumer arithmetic before using this virtual donor.\n"
        "        source_sum64=(REAL(oldcarrier(cell),real64)*REAL(source_endpoint32,real64)+ &\n"
        "                      REAL(dt,real64)*[qs64(cell,p),ns64(cell,p)])/REAL(oldcarrier(cell),real64)\n"
        "        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) &\n"
        "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n"
        "        donor_q(i,k,j,p)=source_sum64(1)\n"
        "        donor_n(i,k,j,p)=source_sum64(2)\n",
        "        ! Virtual donors are formed after the prepared-field diffusion pass.\n",
        "defer virtual donor construction",
    )
    source = replace_once(
        source,
        "    cell=0\n"
        "    DO j=jl,jh\n"
        "    DO k=kl,kh\n"
        "    DO i=il,ih\n"
        "      cell=cell+1\n"
        "      DO p=1,2\n"
        "        IF (.NOT.source_first_pair(p)) CYCLE\n"
        "        rate=air_tendency(q1(:,:,:,qindex(p)),n1(:,:,:,nindex(p)),i,k,j,p)\n",
        _DIFFUSION_AND_DONOR_PASS,
        "prepared-field diffusion consumer pass",
    )
    source = replace_once(
        source,
        "  END SUBROUTINE prepare_source_first_rates\n",
        "    DEALLOCATE(prepared_q,prepared_n,prepared_diffusion,prepared_n_diffusion)\n"
        "  END SUBROUTINE prepare_source_first_rates\n",
        "prepared-field workspace cleanup",
    )
    return source


_DIFFUSION_AND_DONOR_PASS = """    source_diff_sum=0.0_real64; source_diff_l1=0.0_real64; source_diff_max=0.0_real64
    source_diff_cells=0
    DO p=1,2
      IF (.NOT.source_first_pair(p)) CYCLE
      source_diff_sum=0.0_real64; source_diff_l1=0.0_real64; source_diff_max=0.0_real64
      source_diff_cells=0
      IF (.NOT.PRESENT(pr87_all_pair_diffusion_old)) &
        CALL wrf_error_fatal('PR91 source-first diffusion requires producer cache')
      IF (ANY(pr87_all_pair_diffusion_valid(2*p-1:2*p)==0)) &
        CALL wrf_error_fatal('PR91 missing paired old diffusion cache channel')
      CALL horizontal_diffusion64(prepared_q(:,:,:,p),mut_diff,c1,c2, &
           msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
           rdx,rdy,ims,ime,kms,kme,jms,jme, &
           pr87_all_pair_diffusion_identity(3),pr87_all_pair_diffusion_identity(4), &
           pr87_all_pair_diffusion_identity(5),pr87_all_pair_diffusion_identity(6), &
           pr87_all_pair_diffusion_identity(7),pr87_all_pair_diffusion_identity(8),prepared_diffusion)
      CALL horizontal_diffusion64(prepared_n(:,:,:,p),mut_diff,c1,c2, &
           msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
           rdx,rdy,ims,ime,kms,kme,jms,jme, &
           pr87_all_pair_diffusion_identity(3),pr87_all_pair_diffusion_identity(4), &
           pr87_all_pair_diffusion_identity(5),pr87_all_pair_diffusion_identity(6), &
           pr87_all_pair_diffusion_identity(7),pr87_all_pair_diffusion_identity(8),prepared_n_diffusion)
      cell=0
      DO j=jl,jh
      DO k=kl,kh
      DO i=il,ih
        cell=cell+1
        IF (i<pr87_all_pair_diffusion_identity(3).OR.i>pr87_all_pair_diffusion_identity(4).OR. &
            j<pr87_all_pair_diffusion_identity(5).OR.j>pr87_all_pair_diffusion_identity(6).OR. &
            k<pr87_all_pair_diffusion_identity(7).OR.k>pr87_all_pair_diffusion_identity(8)) CYCLE
        source_diff_delta=[prepared_diffusion(i,k,j)-pr87_all_pair_diffusion_old(i,k,j,2*p-1), &
                           prepared_n_diffusion(i,k,j)-pr87_all_pair_diffusion_old(i,k,j,2*p)]
        IF (.NOT.ALL(ieee_is_finite(source_diff_delta))) &
          CALL wrf_error_fatal('PR91 nonfinite source-prepared diffusion delta')
        qs64(cell,p)=qs64(cell,p)+source_diff_delta(1)
        ns64(cell,p)=ns64(cell,p)+source_diff_delta(2)
        source_diff_sum=source_diff_sum+REAL(dt,real64)*source_diff_delta
        source_diff_l1=source_diff_l1+REAL(dt,real64)*ABS(source_diff_delta)
        source_diff_max=MAX(source_diff_max,REAL(dt,real64)*ABS(source_diff_delta))
        source_diff_cells=source_diff_cells+1
      END DO
      END DO
      END DO
      OPEN(NEWUNIT=source_diff_u,FILE='pr85_joint_source_diffusion.raw',STATUS='UNKNOWN',POSITION='APPEND')
      WRITE(source_diff_u,'(a,9i10,1p,6es26.17,i12)') 'SOURCE_DIFFUSION_DELTA_DT_PRESSURE', &
           itimestep,rk,p,pr87_all_pair_diffusion_identity(3:8), &
           source_diff_sum,source_diff_l1,source_diff_max,source_diff_cells
      CLOSE(source_diff_u)
    END DO
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        source_sum64=(REAL(oldcarrier(cell),real64)*REAL([qb(cell,p),nb(cell,p)],real64)+ &
                      REAL(dt,real64)*[qs64(cell,p),ns64(cell,p)])/REAL(oldcarrier(cell),real64)
        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) &
          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')
        donor_q(i,k,j,p)=source_sum64(1); donor_n(i,k,j,p)=source_sum64(2)
      END DO
    END DO
    END DO
    END DO
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        rate=air_tendency(q1(:,:,:,qindex(p)),n1(:,:,:,nindex(p)),i,k,j,p)
"""


def transform_solve(source: str) -> str:
    if "PR91_SOURCE_DIFFUSION_C9" in source:
        raise ValueError("C9 transform already applied")
    source = replace_once(
        source,
        "   REAL(real64), ALLOCATABLE :: pr87_all_pair_diffusion_delta(:,:,:,:)\n",
        "   REAL(real64), ALLOCATABLE :: pr87_all_pair_diffusion_delta(:,:,:,:)\n"
        "   REAL(real64), ALLOCATABLE :: pr87_all_pair_diffusion_old(:,:,:,:)\n"
        "   INTEGER :: pr87_all_pair_diffusion_identity(8),pr87_all_pair_diffusion_valid(8)\n",
        "solve diffusion cache declarations",
    )
    source = replace_once(
        source,
        "                  pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8))\n",
        "                  pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8), &\n"
        "                  pr87_all_pair_diffusion_old(ims:ime,kms:kme,jms:jme,4))\n"
        "         pr87_all_pair_diffusion_identity=0\n"
        "         pr87_all_pair_diffusion_valid=0\n",
        "solve diffusion cache allocation",
    )
    source = replace_once(
        source,
        "         pr87_all_pair_diffusion_delta = 0.0_real64\n",
        "         pr87_all_pair_diffusion_delta = 0.0_real64\n"
        "         pr87_all_pair_diffusion_old = 0.0_real64\n"
        "         pr87_all_pair_diffusion_identity=[grid%itimestep,rk_step,0,0,0,0,0,0]\n"
        "         pr87_all_pair_diffusion_valid=0\n",
        "solve diffusion cache reset",
    )
    source = source.replace(
        "all_pair_diffusion_delta=pr87_all_pair_diffusion_delta)",
        "all_pair_diffusion_delta=pr87_all_pair_diffusion_delta, &\n"
        "                 all_pair_diffusion_old=pr87_all_pair_diffusion_old, &\n"
        "                 all_pair_diffusion_identity=pr87_all_pair_diffusion_identity, &\n"
        "                 all_pair_diffusion_valid=pr87_all_pair_diffusion_valid)",
    )
    if source.count("all_pair_diffusion_old=pr87_all_pair_diffusion_old") != 2:
        raise ValueError("expected exactly two diffusion producer calls")
    source = replace_once(
        source,
        "              pr87_rk1_muts,grid%xkhh,grid%msfux,grid%msfuy,grid%msfvx_inv,grid%msfvy)\n",
        "              pr87_rk1_muts,grid%xkhh,grid%msfux,grid%msfuy,grid%msfvx_inv,grid%msfvy, &\n"
        "              pr87_all_pair_diffusion_old,pr87_all_pair_diffusion_identity, &\n"
        "              pr87_all_pair_diffusion_valid) ! PR91_SOURCE_DIFFUSION_C9\n",
        "joint update cache handoff",
    )
    return source


def transform_files(module_path: Path, solve_path: Path,
                    module_output: Path, solve_output: Path) -> dict[str, str]:
    module, solve = module_path.read_text(), solve_path.read_text()
    module_hash, solve_hash = sha256(module), sha256(solve)
    if module_hash != MODULE_SHA256:
        raise ValueError(f"unexpected C8 module SHA-256: {module_hash}")
    if solve_hash != SOLVE_SHA256:
        raise ValueError(f"unexpected C7 solve SHA-256: {solve_hash}")
    module_new, solve_new = transform_module(module), transform_solve(solve)
    module_output.parent.mkdir(parents=True, exist_ok=True)
    solve_output.parent.mkdir(parents=True, exist_ok=True)
    if module_output.exists() or solve_output.exists():
        raise FileExistsError("C9 output already exists; refusing to overwrite")
    module_created = False
    try:
        with module_output.open("x") as stream:
            module_created = True
            stream.write(module_new)
        with solve_output.open("x") as stream:
            stream.write(solve_new)
    except Exception:
        if module_created:
            module_output.unlink(missing_ok=True)
        raise
    return {"module_sha256": sha256(module_new), "solve_sha256": sha256(solve_new),
            "module_output": str(module_output), "solve_output": str(solve_output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--solve", required=True, type=Path)
    parser.add_argument("--module-output", required=True, type=Path)
    parser.add_argument("--solve-output", required=True, type=Path)
    args = parser.parse_args()
    result = transform_files(args.module, args.solve, args.module_output, args.solve_output)
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
