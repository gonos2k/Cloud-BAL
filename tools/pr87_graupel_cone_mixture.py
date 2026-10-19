"""Pin the selective REAL64 boundary repair to the frozen PR85 advection source."""

from __future__ import annotations

import hashlib


V42_MODULE_EM_SHA256 = "5eb415ca23119460ae3dd766d9acea0f4c99b96ad576100efb95c3bb4d402a6c"
V42_SOLVE_EM_SHA256 = "e78f0a3981c399e5c4326bd550d55a6ca5522d297f8c44c0d60a18ac3768b2b3"


def extend_graupel_cone_mixture(source: str) -> str:
    """Add a strict, source-certified mixture fallback for stored graupel pairs."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != V42_MODULE_EM_SHA256:
        raise ValueError(f"unexpected pinned module_em source hash: {actual_hash}")

    import_anchor = "SUBROUTINE rk_update_joint_moments("
    import_end = "USE iso_fortran_env, ONLY: real32,real64"
    import_start = source.find(import_anchor)
    import_line = source.find(import_end, import_start)
    if import_start < 0 or import_line < 0:
        raise ValueError("missing pinned RK routine kind import")
    source = source[:import_line] + "USE iso_fortran_env, ONLY: int32,int64,real32,real64" + source[import_line + len(import_end):]

    signature = "pr87_all_pair_diffusion_delta,pr87_all_pair_diffusion_step,pr87_pbl_tendency_delta64,pr87_pbl_tendency_step,pr87_pbl_tendency_phase)"
    extended_signature = signature[:-1] + ", &\n     mut_diff,xkmhd_diff,msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff)"
    if source.count(signature) != 1:
        raise ValueError("expected one pinned joint RK signature")
    source = source.replace(signature, extended_signature, 1)

    declaration_anchor = "  REAL,INTENT(IN) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)\n"
    geometry_declarations = """  REAL,INTENT(IN) :: mut_diff(ims:ime,jms:jme)
  REAL,INTENT(IN) :: xkmhd_diff(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: msfux_diff(ims:ime,jms:jme),msfuy_diff(ims:ime,jms:jme)
  REAL,INTENT(IN) :: msfvx_inv_diff(ims:ime,jms:jme),msfvy_diff(ims:ime,jms:jme)
"""
    if source.count(declaration_anchor) != 1:
        raise ValueError("expected pinned joint RK geometry declarations")
    source = source.replace(declaration_anchor, declaration_anchor + geometry_declarations, 1)

    call_anchor = """                         number_pair_bounds=number_bounds, &
                         strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.])
  END SUBROUTINE evaluate_joint_candidate"""
    call_replacement = """                         number_pair_bounds=number_bounds, &
                         strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.])
    IF (.NOT.feasible) CALL try_graupel_mixture_trial()
  END SUBROUTINE evaluate_joint_candidate

  SUBROUTINE try_graupel_mixture_trial()
    REAL(real32),ALLOCATABLE :: q_trial(:,:),n_trial(:,:)
    REAL(real64) :: trial_delta_q(4),trial_delta_n(4)
    INTEGER :: trial_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count
    INTEGER :: tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER(int32) :: witness_q32,witness_n32
    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    ALLOCATE(q_trial(cells,4),n_trial(cells,4))
    q_trial=qc; n_trial=nc
    trial_delta_q=0.0_real64; trial_delta_n=0.0_real64; trial_adjustments=0
    CALL certify_graupel_storage(q_trial,n_trial,trial_delta_q,trial_delta_n, &
                                 trial_adjustments,valid,fallback_count,witness_i,witness_j,witness_k, &
                                 witness_q64,witness_n64,witness_q32,witness_n32, &
                                 witness_canonical_valid,witness_stored_valid, &
                                 reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
                                 tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits)
    IF (.NOT.valid) THEN
      feasible=.FALSE.; theta=0.0_real64; rejected_q=0.0_real64; rejected_n=0.0_real64
      IF (reject_reason>0) WRITE(*,'(A,5(1X,I0),6(1X,Z16.16))') &
        'PR87_GRAUPEL_TRIAL_REJECT',reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits
      DEALLOCATE(q_trial,n_trial); RETURN
    END IF
    qc=q_trial; nc=n_trial
    storage_delta_q=trial_delta_q; storage_delta_n=trial_delta_n
    storage_adjustments=trial_adjustments
    theta=1.0_real64; rejected_q=0.0_real64; rejected_n=0.0_real64
    feasible=.TRUE.
    IF (fallback_count>0) WRITE(*,'(A,6(1X,I0),2(1X,Z16.16),2(1X,Z8.8),2(1X,L1))') &
      'PR87_GRAUPEL_MIXTURE',itimestep,rk,fallback_count,witness_i,witness_j,witness_k, &
      witness_q64,witness_n64,witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid
    IF (tiny_bg_count>0) WRITE(*,'(A,6(1X,I0),2(1X,Z16.16))') &
      'PR87_GRAUPEL_TINY_BG_ROLE',itimestep,rk,tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k, &
      tiny_bg_bits,tiny_bg_rho_bits
    DEALLOCATE(q_trial,n_trial)
  END SUBROUTINE try_graupel_mixture_trial

  SUBROUTINE probe_failed_graupel_pair()
    REAL(real32),ALLOCATABLE :: q_probe(:,:),n_probe(:,:)
    REAL(real64) :: probe_delta_q(4),probe_delta_n(4)
    INTEGER :: probe_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count
    INTEGER :: tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER(int32) :: witness_q32,witness_n32
    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    IF (.NOT.failed_pairs(4)) RETURN
    ALLOCATE(q_probe(cells,4),n_probe(cells,4))
    q_probe=qc; n_probe=nc
    probe_delta_q=0.0_real64; probe_delta_n=0.0_real64; probe_adjustments=0
    CALL certify_graupel_storage(q_probe,n_probe,probe_delta_q,probe_delta_n,probe_adjustments, &
        valid,fallback_count,witness_i,witness_j,witness_k,witness_q64,witness_n64, &
        witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid, &
        reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
        tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,.TRUE.)
    IF (valid) failed_pairs(4)=.FALSE.
    DEALLOCATE(q_probe,n_probe)
  END SUBROUTINE probe_failed_graupel_pair

  SUBROUTINE certify_graupel_storage(q_trial,n_trial,delta_q_by_pair,delta_n_by_pair, &
      adjustments_by_pair,valid,fallback_count,witness_i,witness_j,witness_k, &
      witness_q64,witness_n64,witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid, &
      reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
      tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,graupel_only)
    REAL(real32),INTENT(INOUT) :: q_trial(cells,4),n_trial(cells,4)
    REAL(real64),INTENT(INOUT) :: delta_q_by_pair(4),delta_n_by_pair(4)
    INTEGER,INTENT(INOUT) :: adjustments_by_pair(4)
    INTEGER,INTENT(OUT) :: fallback_count,witness_i,witness_j,witness_k
    INTEGER,INTENT(OUT) :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER,INTENT(OUT) :: tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER(int32),INTENT(OUT) :: witness_q32,witness_n32
    INTEGER(int64),INTENT(OUT) :: witness_q64,witness_n64,reject_bits(6)
    INTEGER(int64),INTENT(OUT) :: tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL,INTENT(OUT) :: witness_canonical_valid,witness_stored_valid,valid
    LOGICAL,INTENT(IN),OPTIONAL :: graupel_only
    INTEGER :: c,i,k,j,p,adjustment,first_pair,last_pair
    REAL(real64) :: value_q,value_n,weights(7),delta_q,delta_n,replay_rates(2)
    REAL(real32) :: q_terms(7),n_terms(7),stored_q,stored_n
    REAL(real64) :: minimum_positive32
    LOGICAL :: store_valid,mixture_valid,fallback_used
    delta_q_by_pair=0.0_real64; delta_n_by_pair=0.0_real64
    adjustments_by_pair=0
    fallback_count=0; witness_i=0; witness_j=0; witness_k=0
    witness_q64=0_int64; witness_n64=0_int64; witness_q32=0_int32; witness_n32=0_int32
    witness_canonical_valid=.FALSE.; witness_stored_valid=.FALSE.
    reject_reason=0; reject_pair=0; reject_i=0; reject_j=0; reject_k=0; reject_bits=0_int64
    tiny_bg_count=0; tiny_bg_i=0; tiny_bg_j=0; tiny_bg_k=0
    tiny_bg_bits=0_int64; tiny_bg_rho_bits=0_int64
    first_pair=1; last_pair=4
    IF (PRESENT(graupel_only)) THEN
      IF (graupel_only) first_pair=4
    END IF
    minimum_positive32=REAL(NEAREST(0.0_real32,1.0_real32),real64)
    valid=.FALSE.
    DO p=first_pair,last_pair
      c=0
      DO j=jl,jh
        DO k=kl,kh
          DO i=il,ih
            c=c+1
            value_q=(REAL(oldcarrier(c),real64)*REAL(qb(c,p),real64)+ &
                REAL(dt,real64)*(qs64(c,p)+qa64(c,p)))/REAL(newcarrier(c),real64)
            value_n=(REAL(oldcarrier(c),real64)*REAL(nb(c,p),real64)+ &
                REAL(dt,real64)*(ns64(c,p)+na64(c,p)))/REAL(newcarrier(c),real64)
            delta_q=0.0_real64; delta_n=0.0_real64; adjustment=0; fallback_used=.FALSE.
            IF (p==1.OR.p==3) THEN
              IF (ANY(number_bounds(c,:,p)/=0.0_real64)) THEN
                CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                    .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                    allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                    volume_number_bounds=number_bounds(c,:,p))
              ELSE
                CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                    .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                    allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)
              END IF
            ELSE IF (p==4) THEN
              CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                  strict_mass_ratio=.TRUE.)
              IF (store_valid.AND.value_n>0.0_real64) THEN
                IF (REAL(drydensity(c),real64)*value_n<=0.5_real64*minimum_positive32) THEN
                  tiny_bg_count=tiny_bg_count+1
                  IF (tiny_bg_count==1) THEN
                    tiny_bg_i=i; tiny_bg_j=j; tiny_bg_k=k
                    tiny_bg_bits=TRANSFER(value_n,tiny_bg_bits)
                    tiny_bg_rho_bits=TRANSFER(drydensity(c),tiny_bg_rho_bits)
                  END IF
                END IF
              END IF
            ELSE
              CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)
            END IF
            IF (.NOT.store_valid) THEN
              IF (p/=4) THEN
                reject_reason=1
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              replay_rates=air_tendency(q1(:,:,:,qindex(4)),n1(:,:,:,nindex(4)),i,k,j,4)
              IF (TRANSFER(qb(c,4),0_int32)/=TRANSFER(q1(i,k,j,qindex(4)),0_int32).OR. &
                  TRANSFER(nb(c,4),0_int32)/=TRANSFER(n1(i,k,j,nindex(4)),0_int32).OR. &
                  TRANSFER(qa64(c,4),0_int64)/=TRANSFER(replay_rates(1),0_int64).OR. &
                  TRANSFER(na64(c,4),0_int64)/=TRANSFER(replay_rates(2),0_int64)) THEN
                reject_reason=5
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qa64(c,4),0_int64),TRANSFER(na64(c,4),0_int64), &
                    TRANSFER(replay_rates(1),0_int64),TRANSFER(replay_rates(2),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=3
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL add_graupel_diffusion_mixture(c,i,k,j,weights,q_terms,n_terms,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=6
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL store_graupel_mixture(weights,q_terms,n_terms,newcarrier(c),minmass(4), &
                  maxmass(4),value_q,value_n,stored_q,stored_n,delta_q,delta_n,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=4
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1
              IF (fallback_count==1) THEN
                witness_i=i; witness_j=j; witness_k=k
                witness_q64=TRANSFER(value_q,witness_q64)
                witness_n64=TRANSFER(value_n,witness_n64)
                witness_q32=TRANSFER(stored_q,witness_q32)
                witness_n32=TRANSFER(stored_n,witness_n32)
                witness_canonical_valid=strict_graupel_pair(value_q,value_n,minmass(4),maxmass(4))
                witness_stored_valid=strict_graupel_pair(REAL(stored_q,real64), &
                    REAL(stored_n,real64),minmass(4),maxmass(4))
              END IF
            ELSE IF (adjustment/=0) THEN
              delta_q=REAL(newcarrier(c),real64)*(REAL(stored_q,real64)-value_q)
              delta_n=REAL(newcarrier(c),real64)*(REAL(stored_n,real64)-value_n)
            END IF
            q_trial(c,p)=stored_q; n_trial(c,p)=stored_n
            delta_q_by_pair(p)=delta_q_by_pair(p)+delta_q
            delta_n_by_pair(p)=delta_n_by_pair(p)+delta_n
            IF (fallback_used.OR.adjustment/=0) adjustments_by_pair(p)=adjustments_by_pair(p)+1
          END DO
        END DO
      END DO
    END DO
    valid=.TRUE.
  END SUBROUTINE certify_graupel_storage

  SUBROUTINE graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,valid)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(OUT) :: weights(7)
    REAL(real32),INTENT(OUT) :: q_terms(7),n_terms(7)
    LOGICAL,INTENT(OUT) :: valid
    REAL(real64) :: xscale,yscale,zscale,outflow,edge,base_weight
    weights=0.0_real64; q_terms=0.0_real32; n_terms=0.0_real32; valid=.FALSE.
    xscale=REAL(msfty(i,j),real64)*REAL(msftx(i,j)*rdx,real64)
    yscale=REAL(msfty(i,j),real64)*REAL(msftx(i,j)*rdy,real64)
    zscale=REAL(msfty(i,j),real64)*REAL(-rdnw(k),real64)
    IF (.NOT.ALL(ieee_is_finite([xscale,yscale,zscale]))) RETURN
    IF (MIN(xscale,yscale,zscale)<0.0_real64) RETURN
    outflow=xscale*(MAX(REAL(ru(i+1,k,j),real64),0.0_real64)+ &
                    MAX(-REAL(ru(i,k,j),real64),0.0_real64))+ &
            yscale*(MAX(REAL(rv(i,k,j+1),real64),0.0_real64)+ &
                    MAX(-REAL(rv(i,k,j),real64),0.0_real64))
    IF (k>kl) outflow=outflow+zscale*MAX(REAL(ww(i,k,j),real64),0.0_real64)
    IF (k<kh) outflow=outflow+zscale*MAX(-REAL(ww(i,k+1,j),real64),0.0_real64)
    base_weight=REAL(oldcarrier(c),real64)-REAL(dt,real64)*outflow
    IF (.NOT.ieee_is_finite(base_weight)) RETURN
    IF (base_weight<0.0_real64) RETURN
    weights(1)=base_weight
    q_terms(1)=q1(i,k,j,qindex(4)); n_terms(1)=n1(i,k,j,nindex(4))

    edge=REAL(ru(i+1,k,j),real64)
    IF (edge<0.0_real64) THEN
      weights(2)=REAL(dt,real64)*xscale*(-edge)
      q_terms(2)=q1(i+1,k,j,qindex(4)); n_terms(2)=n1(i+1,k,j,nindex(4))
    END IF
    edge=REAL(ru(i,k,j),real64)
    IF (edge>0.0_real64) THEN
      weights(3)=REAL(dt,real64)*xscale*edge
      q_terms(3)=q1(i-1,k,j,qindex(4)); n_terms(3)=n1(i-1,k,j,nindex(4))
    END IF
    edge=REAL(rv(i,k,j+1),real64)
    IF (edge<0.0_real64) THEN
      weights(4)=REAL(dt,real64)*yscale*(-edge)
      q_terms(4)=q1(i,k,j+1,qindex(4)); n_terms(4)=n1(i,k,j+1,nindex(4))
    END IF
    edge=REAL(rv(i,k,j),real64)
    IF (edge>0.0_real64) THEN
      weights(5)=REAL(dt,real64)*yscale*edge
      q_terms(5)=q1(i,k,j-1,qindex(4)); n_terms(5)=n1(i,k,j-1,nindex(4))
    END IF
    IF (k<kh) THEN
      edge=REAL(ww(i,k+1,j),real64)
      IF (edge>0.0_real64) THEN
        weights(6)=REAL(dt,real64)*zscale*edge
        q_terms(6)=q1(i,k+1,j,qindex(4)); n_terms(6)=n1(i,k+1,j,nindex(4))
      END IF
    END IF
    IF (k>kl) THEN
      edge=REAL(ww(i,k,j),real64)
      IF (edge<0.0_real64) THEN
        weights(7)=REAL(dt,real64)*zscale*(-edge)
        q_terms(7)=q1(i,k-1,j,qindex(4)); n_terms(7)=n1(i,k-1,j,nindex(4))
      END IF
    END IF
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    valid=.TRUE.
  END SUBROUTINE graupel_transport_mixture

  SUBROUTINE add_graupel_diffusion_mixture(c,i,k,j,weights,q_terms,n_terms,valid)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(INOUT) :: weights(7)
    REAL(real32),INTENT(INOUT) :: q_terms(7),n_terms(7)
    LOGICAL,INTENT(OUT) :: valid
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real64) :: qdiff,ndiff
    REAL(real128) :: qface(4),nface(4),amount(4),base_weight,face_weight
    INTEGER :: face,slot
    valid=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([qs64(c,4),ns64(c,4)]))) RETURN
    IF (qs64(c,4)==0.0_real64.AND.ns64(c,4)==0.0_real64) THEN
      valid=.TRUE.; RETURN
    END IF
    CALL graupel_diffusion_point(q1(:,:,:,qindex(4)),i,k,j,qdiff,qface,valid)
    IF (.NOT.valid) RETURN
    CALL graupel_diffusion_point(n1(:,:,:,nindex(4)),i,k,j,ndiff,nface,valid)
    IF (.NOT.valid) RETURN
    valid=.FALSE.
    IF (TRANSFER(qs64(c,4),0_int64)/=TRANSFER(qdiff,0_int64).OR. &
        TRANSFER(ns64(c,4),0_int64)/=TRANSFER(ndiff,0_int64)) THEN
      WRITE(*,'(A,5(1X,I0),4(1X,Z16.16))') 'PR87_GRAUPEL_SOURCE_IDENTITY_FAIL', &
        itimestep,rk,i,j,k,TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
        TRANSFER(qdiff,0_int64),TRANSFER(ndiff,0_int64)
      valid=.FALSE.; RETURN
    END IF
    IF (ANY(qface/=nface).OR.ANY(qface<0.0_real128)) THEN
      valid=.FALSE.; RETURN
    END IF
    amount=REAL(dt,real128)*qface
    IF (.NOT.ALL(ieee_is_finite(amount))) THEN
      valid=.FALSE.; RETURN
    END IF
    base_weight=REAL(weights(1),real128)-SUM(amount)
    IF (.NOT.ieee_is_finite(base_weight)) THEN
      valid=.FALSE.; RETURN
    END IF
    IF (base_weight<0.0_real128.OR.base_weight>REAL(HUGE(0.0_real64),real128)) THEN
      valid=.FALSE.; RETURN
    END IF
    weights(1)=REAL(base_weight,real64)
    IF (base_weight>0.0_real128.AND.weights(1)==0.0_real64) THEN
      valid=.FALSE.; RETURN
    END IF
    q_terms(2)=q1(i+1,k,j,qindex(4)); n_terms(2)=n1(i+1,k,j,nindex(4))
    q_terms(3)=q1(i-1,k,j,qindex(4)); n_terms(3)=n1(i-1,k,j,nindex(4))
    q_terms(4)=q1(i,k,j+1,qindex(4)); n_terms(4)=n1(i,k,j+1,nindex(4))
    q_terms(5)=q1(i,k,j-1,qindex(4)); n_terms(5)=n1(i,k,j-1,nindex(4))
    DO face=1,4
      slot=face+1
      face_weight=REAL(weights(slot),real128)+amount(face)
      IF (.NOT.ieee_is_finite(face_weight)) THEN
        valid=.FALSE.; RETURN
      END IF
      IF (face_weight<0.0_real128.OR.face_weight>REAL(HUGE(0.0_real64),real128)) THEN
        valid=.FALSE.; RETURN
      END IF
      weights(slot)=REAL(face_weight,real64)
      IF (face_weight>0.0_real128.AND.weights(slot)==0.0_real64) THEN
        valid=.FALSE.; RETURN
      END IF
    END DO
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    valid=.TRUE.
  END SUBROUTINE add_graupel_diffusion_mixture

  SUBROUTINE graupel_diffusion_point(field,i,k,j,increment,face_coefficients,valid)
    INTEGER,INTENT(IN) :: i,k,j
    REAL(real32),INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL(real64),INTENT(OUT) :: increment
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128),INTENT(OUT) :: face_coefficients(4)
    LOGICAL,INTENT(OUT) :: valid
    REAL(real128) :: increment128,mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real128) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real128) :: x_i,x_im,x_ip,x_jm,x_jp
    increment=0.0_real64; face_coefficients=0.0_real128; valid=.FALSE.
    IF (i<ims+1.OR.i>ime-1.OR.j<jms+1.OR.j>jme-1.OR.k<kms.OR.k>kme) RETURN
    IF (.NOT.ALL(ieee_is_finite([field(i,k,j),field(i-1,k,j),field(i+1,k,j), &
        field(i,k,j-1),field(i,k,j+1),mut_diff(i,j),mut_diff(i-1,j),mut_diff(i+1,j), &
        mut_diff(i,j-1),mut_diff(i,j+1),xkmhd_diff(i,k,j),xkmhd_diff(i-1,k,j), &
        xkmhd_diff(i+1,k,j),xkmhd_diff(i,k,j-1),xkmhd_diff(i,k,j+1), &
        msfux_diff(i,j),msfuy_diff(i,j),msfux_diff(i+1,j),msfuy_diff(i+1,j), &
        msfvx_inv_diff(i,j),msfvy_diff(i,j),msfvx_inv_diff(i,j+1),msfvy_diff(i,j+1), &
        msftx(i,j),msfty(i,j),c1(k),c2(k),rdx,rdy]))) RETURN
    IF (msfuy_diff(i,j)==0.0.OR.msfuy_diff(i+1,j)==0.0) RETURN
    mut_i=REAL(c1(k),real128)*REAL(mut_diff(i,j),real128)+REAL(c2(k),real128)
    mut_im=REAL(c1(k),real128)*REAL(mut_diff(i-1,j),real128)+REAL(c2(k),real128)
    mut_ip=REAL(c1(k),real128)*REAL(mut_diff(i+1,j),real128)+REAL(c2(k),real128)
    mut_jm=REAL(c1(k),real128)*REAL(mut_diff(i,j-1),real128)+REAL(c2(k),real128)
    mut_jp=REAL(c1(k),real128)*REAL(mut_diff(i,j+1),real128)+REAL(c2(k),real128)
    x_i=REAL(xkmhd_diff(i,k,j),real128); x_im=REAL(xkmhd_diff(i-1,k,j),real128)
    x_ip=REAL(xkmhd_diff(i+1,k,j),real128); x_jm=REAL(xkmhd_diff(i,k,j-1),real128)
    x_jp=REAL(xkmhd_diff(i,k,j+1),real128)
    mkrdxm=(REAL(msfux_diff(i,j),real128)/REAL(msfuy_diff(i,j),real128))* &
      0.5_real128*(x_i+x_im)*0.5_real128*(mut_i+mut_im)*REAL(rdx,real128)
    mkrdxp=(REAL(msfux_diff(i+1,j),real128)/REAL(msfuy_diff(i+1,j),real128))* &
      0.5_real128*(x_ip+x_i)*0.5_real128*(mut_ip+mut_i)*REAL(rdx,real128)
    mrdx=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdx,real128)
    mkrdym=(REAL(msfvy_diff(i,j),real128)*REAL(msfvx_inv_diff(i,j),real128))* &
      0.5_real128*(x_i+x_jm)*0.5_real128*(mut_i+mut_jm)*REAL(rdy,real128)
    mkrdyp=(REAL(msfvy_diff(i,j+1),real128)*REAL(msfvx_inv_diff(i,j+1),real128))* &
      0.5_real128*(x_jp+x_i)*0.5_real128*(mut_jp+mut_i)*REAL(rdy,real128)
    mrdy=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdy,real128)
    face_coefficients=[mrdx*mkrdxp,mrdx*mkrdxm,mrdy*mkrdyp,mrdy*mkrdym]
    IF (.NOT.ALL(ieee_is_finite(face_coefficients))) RETURN
    IF (ANY(face_coefficients<0.0_real128)) RETURN
    increment128= &
      mrdx*(mkrdxp*(REAL(field(i+1,k,j),real128)-REAL(field(i,k,j),real128))- &
            mkrdxm*(REAL(field(i,k,j),real128)-REAL(field(i-1,k,j),real128)))+ &
      mrdy*(mkrdyp*(REAL(field(i,k,j+1),real128)-REAL(field(i,k,j),real128))- &
            mkrdym*(REAL(field(i,k,j),real128)-REAL(field(i,k,j-1),real128)))
    increment=REAL(increment128,real64)
    IF (.NOT.ieee_is_finite(increment)) RETURN
    valid=.TRUE.
  END SUBROUTINE graupel_diffusion_point

  PURE LOGICAL FUNCTION strict_graupel_pair(q,n,minimum_ratio,maximum_ratio)
    REAL(real64),INTENT(IN) :: q,n,minimum_ratio,maximum_ratio
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: q128,n128
    strict_graupel_pair=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([q,n,minimum_ratio,maximum_ratio]))) RETURN
    IF (q<0.0_real64.OR.n<0.0_real64.OR.minimum_ratio<=0.0_real64.OR. &
        maximum_ratio<minimum_ratio) RETURN
    IF (q==0.0_real64.AND.n==0.0_real64) THEN
      strict_graupel_pair=.TRUE.; RETURN
    END IF
    IF (q<=0.0_real64.OR.n<=0.0_real64) RETURN
    q128=REAL(q,real128); n128=REAL(n,real128)
    strict_graupel_pair=q128>=REAL(minimum_ratio,real128)*n128.AND. &
                        q128<=REAL(maximum_ratio,real128)*n128
  END FUNCTION strict_graupel_pair

  SUBROUTINE store_graupel_mixture(weights,q_terms,n_terms,denominator,minimum_ratio, &
      maximum_ratio,reference_q,reference_n,stored_q,stored_n,delta_q,delta_n,valid)
    REAL(real64),INTENT(IN) :: weights(7),minimum_ratio,maximum_ratio,reference_q,reference_n
    REAL(real32),INTENT(IN) :: q_terms(7),n_terms(7),denominator
    REAL(real32),INTENT(OUT) :: stored_q,stored_n
    REAL(real64),INTENT(OUT) :: delta_q,delta_n
    LOGICAL,INTENT(OUT) :: valid
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: qsum,nsum,qvalue,nvalue,qcheck,ncheck
    INTEGER :: term,attempt
    stored_q=-1.0_real32; stored_n=-1.0_real32
    delta_q=0.0_real64; delta_n=0.0_real64; valid=.FALSE.
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    IF (.NOT.ALL(ieee_is_finite(q_terms))) RETURN
    IF (.NOT.ALL(ieee_is_finite(n_terms))) RETURN
    IF (.NOT.ieee_is_finite(denominator)) RETURN
    IF (denominator<=0.0_real32) RETURN
    IF (.NOT.ieee_is_finite(reference_q).OR..NOT.ieee_is_finite(reference_n)) RETURN
    qsum=0.0_real128; nsum=0.0_real128
    DO term=1,7
      IF (weights(term)==0.0_real64) CYCLE
      IF (.NOT.strict_graupel_pair(REAL(q_terms(term),real64),REAL(n_terms(term),real64), &
                                   minimum_ratio,maximum_ratio)) RETURN
      qsum=qsum+REAL(weights(term),real128)*REAL(q_terms(term),real128)
      nsum=nsum+REAL(weights(term),real128)*REAL(n_terms(term),real128)
    END DO
    qvalue=qsum/REAL(denominator,real128); nvalue=nsum/REAL(denominator,real128)
    IF (.NOT.ieee_is_finite(qvalue).OR..NOT.ieee_is_finite(nvalue)) RETURN
    IF (qvalue>REAL(HUGE(0.0_real32),real128).OR.nvalue>REAL(HUGE(0.0_real32),real128)) RETURN
    stored_q=REAL(qvalue,real32); stored_n=REAL(nvalue,real32)
    IF (.NOT.ieee_is_finite(stored_q).OR..NOT.ieee_is_finite(stored_n)) RETURN
    DO attempt=1,4
      IF (strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                              minimum_ratio,maximum_ratio)) EXIT
      qcheck=REAL(stored_q,real128); ncheck=REAL(stored_n,real128)
      IF (stored_q<=0.0_real32.OR.stored_n<=0.0_real32) RETURN
      IF (qcheck<REAL(minimum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,1.0_real32)
      ELSE IF (qcheck>REAL(maximum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,-1.0_real32)
      ELSE
        RETURN
      END IF
    END DO
    IF (.NOT.strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                                 minimum_ratio,maximum_ratio)) RETURN
    delta_q=REAL(denominator,real64)*(REAL(stored_q,real64)-reference_q)
    delta_n=REAL(denominator,real64)*(REAL(stored_n,real64)-reference_n)
    IF (.NOT.ALL(ieee_is_finite([delta_q,delta_n]))) RETURN
    valid=.TRUE.
  END SUBROUTINE store_graupel_mixture"""

    if source.count(call_anchor) != 1:
        raise ValueError("expected one joint candidate call anchor")
    source = source.replace(call_anchor, call_replacement, 1)
    failure_scan = "    CALL find_failed_baseline_pairs()\n"
    if source.count(failure_scan) != 1:
        raise ValueError("expected one pinned baseline-pair failure scan")
    source = source.replace(failure_scan, failure_scan + "    CALL probe_failed_graupel_pair()\n", 1)
    return source


def extend_graupel_cone_solve_em(source: str) -> str:
    """Pass RK1 diffusion geometry to later joint RK updates in the same step."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != V42_SOLVE_EM_SHA256:
        raise ValueError(f"unexpected pinned solve_em source hash: {actual_hash}")
    declaration_anchor = "   INTEGER :: number_of_small_timesteps, rk_step\n"
    declaration_replacement = declaration_anchor + "   INTEGER :: pr87_diffusion_capture_step, pr87_diffusion_capture_rk\n" \
        + "   LOGICAL :: pr87_diffusion_geometry_captured\n" \
        + "   REAL, ALLOCATABLE :: pr87_rk1_muts(:,:)\n"
    if source.count(declaration_anchor) != 1:
        raise ValueError("expected one pinned RK local declaration anchor")
    source = source.replace(declaration_anchor, declaration_replacement, 1)

    loop_anchor = "   Runge_Kutta_loop:  DO rk_step = 1, rk_order\n"
    loop_replacement = "   pr87_diffusion_geometry_captured = .FALSE.\n" \
        + "   pr87_diffusion_capture_step = -1\n" \
        + "   pr87_diffusion_capture_rk = 0\n" + loop_anchor
    if source.count(loop_anchor) != 1:
        raise ValueError("expected one pinned RK loop anchor")
    source = source.replace(loop_anchor, loop_replacement, 1)

    scalar_anchor = "       moist_scalar_advance: IF (num_3d_m >= PARAM_FIRST_SCALAR )  THEN\n"
    scalar_replacement = """       IF (config_flags%mp_physics == 37 .AND. rk_step == 1) THEN
         IF (ALLOCATED(pr87_rk1_muts)) DEALLOCATE(pr87_rk1_muts)
         ALLOCATE(pr87_rk1_muts(ims:ime,jms:jme))
         pr87_rk1_muts = grid%muts(ims:ime,jms:jme)
         pr87_diffusion_capture_step = grid%itimestep
         pr87_diffusion_capture_rk = rk_step
         pr87_diffusion_geometry_captured = .TRUE.
       END IF

""" + scalar_anchor
    if source.count(scalar_anchor) != 1:
        raise ValueError("expected one pinned moist scalar producer-stage anchor")
    source = source.replace(scalar_anchor, scalar_replacement, 1)

    call_start = source.index("CALL rk_update_joint_moments(")
    call_end_anchor = "              pr87_all_pair_diffusion_delta, pr87_all_pair_diffusion_step, pr87_pbl_tendency_delta64, pr87_pbl_tendency_step, pr87_pbl_tendency_phase)"
    if source.count(call_end_anchor) != 1:
        raise ValueError("expected one pinned joint RK call")
    call_end = source.index(call_end_anchor, call_start) + len(call_end_anchor)
    call = source[call_start:call_end]
    call = call.replace(call_end_anchor, """              pr87_all_pair_diffusion_delta, pr87_all_pair_diffusion_step, pr87_pbl_tendency_delta64, pr87_pbl_tendency_step, pr87_pbl_tendency_phase, &
              pr87_rk1_muts,grid%xkhh,grid%msfux,grid%msfuy,grid%msfvx_inv,grid%msfvy)""", 1)
    guard = """IF (.NOT.pr87_diffusion_geometry_captured .OR. &
             pr87_diffusion_capture_step /= grid%itimestep .OR. &
             pr87_diffusion_capture_rk /= 1) THEN
           CALL wrf_error_fatal('PR87 missing RK1 diffusion geometry for joint update')
         END IF
         """
    if source.count("     IF ( config_flags%mp_physics == 37 ) THEN\n       IF ( rk_order /= 3 ) THEN") != 1:
        raise ValueError("expected joint RK call inside pinned mp_physics 37 guard")
    guarded_call = guard + call
    return source[:call_start] + guarded_call + source[call_end:]
