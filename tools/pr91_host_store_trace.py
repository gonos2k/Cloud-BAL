#!/usr/bin/env python3
"""Add failure-only trace outputs to the pinned PR90 C7 host/core sources."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


CORE_SHA256 = "c8ecedde5cc8f9adedf6cf082054596ca1c0d6a3565d152c73d730c00cd678f3"
HOST_SHA256 = "090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b"


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def replace_once(source: str, before: str, after: str, label: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"expected one {label} anchor")
    return source.replace(before, after, 1)


def instrument_core(source: str, expected_sha256: str = CORE_SHA256) -> str:
    if sha256(source) != expected_sha256:
        raise ValueError("shared core source hash mismatch")
    has_bulk_volume_policy = "bulk_volume_absences, bulk_volume_delta)" in source
    bulk_option = ("bulk_volume_quantum_storage" if "bulk_volume_quantum_storage" in source
                   else "bulk_volume_quantum_absence")
    if has_bulk_volume_policy:
        source = replace_once(
            source,
            f"                              {bulk_option}, bulk_volume_absences, bulk_volume_delta)\n",
            f"                              {bulk_option}, bulk_volume_absences, bulk_volume_delta, &\n"
            "                              diagnostic_stage, diagnostic_candidate, diagnostic_stored, &\n"
            "                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells)\n",
            "bulk-volume joint update optional outputs",
        )
    elif "inactive_q_quantum_adjustment_pairs, inactive_q_quantum_adjustments)" in source:
        source = replace_once(
            source,
            "                              inactive_q_quantum_adjustment_pairs, inactive_q_quantum_adjustments)\n",
            "                              inactive_q_quantum_adjustment_pairs, inactive_q_quantum_adjustments, &\n"
            "                              diagnostic_stage, diagnostic_candidate, diagnostic_stored, &\n"
            "                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells)\n",
            "joint update optional outputs",
        )
    else:
        source = replace_once(
            source,
            "                              strict_mass_pairs, inactive_mass_limits)\n",
            "                              strict_mass_pairs, inactive_mass_limits, &\n"
            "                              diagnostic_stage, diagnostic_candidate, diagnostic_stored, &\n"
            "                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells)\n",
            "joint update optional outputs",
        )
    old_declaration = "    real(real64), intent(in), optional :: inactive_mass_limits(:)\n"
    new_declaration = (
        "    real(real64), intent(in), optional :: inactive_mass_limits(:)\n"
        "    integer, intent(out), optional :: diagnostic_stage(:,:)\n"
        "    real(real64), intent(out), optional :: diagnostic_candidate(:,:,:)\n"
        "    real(real32), intent(out), optional :: diagnostic_stored(:,:,:)\n"
        "    integer, intent(out), optional :: diagnostic_adjustment(:,:)\n"
        "    real(real64), intent(out), optional :: diagnostic_scale(:,:)\n"
        "    integer, intent(in), optional :: diagnostic_cells(:)\n\n"
    )
    if has_bulk_volume_policy:
        old_declaration = "    real(real64), intent(out), optional :: bulk_volume_delta(2)\n\n"
        new_declaration = (
            "    real(real64), intent(out), optional :: bulk_volume_delta(2)\n"
            "    integer, intent(out), optional :: diagnostic_stage(:,:)\n"
            "    real(real64), intent(out), optional :: diagnostic_candidate(:,:,:)\n"
            "    real(real32), intent(out), optional :: diagnostic_stored(:,:,:)\n"
            "    integer, intent(out), optional :: diagnostic_adjustment(:,:)\n"
            "    real(real64), intent(out), optional :: diagnostic_scale(:,:)\n"
            "    integer, intent(in), optional :: diagnostic_cells(:)\n\n"
        )
    elif expected_sha256 == CORE_SHA256:
        old_declaration += "\n"
    else:
        old_declaration = (
            "    integer, intent(out), optional :: inactive_q_quantum_adjustments(:)\n\n"
        )
        new_declaration = (
            "    integer, intent(out), optional :: inactive_q_quantum_adjustments(:)\n"
            "    integer, intent(out), optional :: diagnostic_stage(:,:)\n"
            "    real(real64), intent(out), optional :: diagnostic_candidate(:,:,:)\n"
            "    real(real32), intent(out), optional :: diagnostic_stored(:,:,:)\n"
            "    integer, intent(out), optional :: diagnostic_adjustment(:,:)\n"
            "    real(real64), intent(out), optional :: diagnostic_scale(:,:)\n"
            "    integer, intent(in), optional :: diagnostic_cells(:)\n\n"
        )
    source = replace_once(
        source,
        old_declaration,
        new_declaration,
        "joint update diagnostic declarations",
    )
    local_anchor = ("    logical :: use_bulk_volume_absence\n" if has_bulk_volume_policy else
                    "    logical :: use_joint_storage, use_constrained_storage, use_quantum_absence, storage_valid\n")
    source = replace_once(source, local_anchor + "\n",
                          local_anchor + "    integer :: local_store_stage\n\n",
                          "joint update diagnostic local")
    source = replace_once(source,
        "      real(real64) :: cell_volume_bounds(2)\n      integer :: i, p\n",
        "      real(real64) :: cell_volume_bounds(2)\n      integer :: i, p, trace_cell\n",
        "form-candidate diagnostic index")
    source = replace_once(
        source,
        "    feasible = .false.\n    theta = 0.0_real64\n",
        "    feasible = .false.\n"
        "    if (present(diagnostic_stage)) diagnostic_stage = 0\n"
        "    if (present(diagnostic_candidate)) diagnostic_candidate = 0.0_real64\n"
        "    if (present(diagnostic_stored)) diagnostic_stored = 0.0_real32\n"
        "    if (present(diagnostic_adjustment)) diagnostic_adjustment = 0\n"
        "    if (present(diagnostic_scale)) diagnostic_scale = 0.0_real64\n"
        "    theta = 0.0_real64\n",
        "joint update diagnostic initialization",
    )
    source = replace_once(
        source,
        "      if (use_joint_storage) then\n        local_delta_q = 0.0_real64\n",
        "      if (present(diagnostic_stage)) diagnostic_stage = 0\n"
        "      if (present(diagnostic_candidate)) diagnostic_candidate = 0.0_real64\n"
        "      if (present(diagnostic_stored)) diagnostic_stored = 0.0_real32\n"
        "      if (present(diagnostic_adjustment)) diagnostic_adjustment = 0\n"
        "      if (present(diagnostic_scale)) diagnostic_scale = 0.0_real64\n"
        "      if (use_joint_storage) then\n        local_delta_q = 0.0_real64\n",
        "final-pass diagnostic reset",
    )
    source = replace_once(
        source,
        "volume_number_bounds=cell_volume_bounds, &\n                                      strict_mass_ratio=pair_has_strict_mass(p))",
        "volume_number_bounds=cell_volume_bounds, &\n"
        "                                      strict_mass_ratio=pair_has_strict_mass(p), &\n"
        "                                      failure_stage=local_store_stage)",
        "volume-bounds store call",
    )
    if "allow_inactive_q_quantum_adjustment= &" in source:
        source = replace_once(
            source,
            "allow_inactive_q_quantum_adjustment= &\n"
            "                                          pair_allows_inactive_q_quantum(p))",
            "allow_inactive_q_quantum_adjustment= &\n"
            "                                          pair_allows_inactive_q_quantum(p), &\n"
            "                                      failure_stage=local_store_stage)",
            "inactive-limit store call",
        )
    else:
        source = replace_once(
            source,
            "inactive_mass_limit=inactive_mass_limit_by_pair(p))",
            "inactive_mass_limit=inactive_mass_limit_by_pair(p), &\n"
            "                                      failure_stage=local_store_stage)",
            "inactive-limit store call",
        )
    source = replace_once(source,
        "    if (npairs == 0 .or. ncells == 0) return\n",
        """    if (npairs == 0 .or. ncells == 0) return
    if (present(diagnostic_cells)) then
      if (.not.present(diagnostic_stage) .or. .not.present(diagnostic_candidate) .or. &
          .not.present(diagnostic_stored) .or. .not.present(diagnostic_adjustment) .or. &
          .not.present(diagnostic_scale)) return
      if (size(diagnostic_stage,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_candidate,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_candidate,2)/=2 .or. size(diagnostic_candidate,3)/=npairs .or. &
          size(diagnostic_stored,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_stored,2)/=2 .or. size(diagnostic_stored,3)/=npairs .or. &
          size(diagnostic_adjustment,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_scale,1)/=size(diagnostic_cells)) return
    end if
""",
        "sparse trace array validation")
    if has_bulk_volume_policy:
        source = replace_once(
            source,
            f"allow_{bulk_option}= &\n"
            "                                          use_bulk_volume_absence .and. p==4)",
            f"allow_{bulk_option}= &\n"
            "                                          use_bulk_volume_absence .and. p==4, &\n"
            "                                      failure_stage=local_store_stage)",
            "bulk-volume strict-mass store call",
        )
    else:
        source = replace_once(
            source,
            "strict_mass_ratio=pair_has_strict_mass(p))",
            "strict_mass_ratio=pair_has_strict_mass(p), &\n"
            "                                      failure_stage=local_store_stage)",
            "strict-mass store call",
        )
    anchor = """            if (.not. storage_valid) then
              q_candidate(i,p) = -1.0_real32
              n_candidate(i,p) = -1.0_real32
"""
    source = replace_once(
        source,
        anchor,
        """            if (.not. storage_valid) then
              if (present(diagnostic_cells)) then
                do trace_cell = 1, size(diagnostic_cells)
                  if (diagnostic_cells(trace_cell) /= i) cycle
                  if (present(diagnostic_stage)) diagnostic_stage(trace_cell,p) = local_store_stage
                  if (present(diagnostic_candidate)) then
                    diagnostic_candidate(trace_cell,1,p) = q_value
                    diagnostic_candidate(trace_cell,2,p) = n_value
                  end if
                  if (present(diagnostic_stored)) then
                    diagnostic_stored(trace_cell,1,p) = q_candidate(i,p)
                    diagnostic_stored(trace_cell,2,p) = n_candidate(i,p)
                  end if
                  if (present(diagnostic_adjustment)) diagnostic_adjustment(trace_cell,p) = adjustment
                  if (present(diagnostic_scale)) diagnostic_scale(trace_cell,p) = scale
                end do
              end if
              q_candidate(i,p) = -1.0_real32
              n_candidate(i,p) = -1.0_real32
""",
        "failed storage capture",
    )
    return source


def instrument_host(source: str, core: str, original_core: str) -> str:
    if sha256(source) != HOST_SHA256:
        raise ValueError("C7 module_em source hash mismatch")
    if not source.startswith(original_core) or not original_core.endswith("end module cloud_bal_joint_transport\n"):
        raise ValueError("C7 host does not begin with the supplied shared-core source")
    source = core + source[len(original_core):]
    call = """                         inactive_mass_limits=[0.0_real64,REAL(NEAREST(1.e-14,-1.0),real64), &
                         0.0_real64,0.0_real64])
    IF (.NOT.feasible) CALL try_graupel_mixture_trial()"""
    replacement = """                         inactive_mass_limits=[0.0_real64,REAL(NEAREST(1.e-14,-1.0),real64), &
                         0.0_real64,0.0_real64], &
                         diagnostic_stage=pr91_stage, diagnostic_candidate=pr91_candidate, &
                         diagnostic_stored=pr91_stored, diagnostic_adjustment=pr91_adjustment, &
                         diagnostic_scale=pr91_scale, diagnostic_cells=pr91_cells)
    IF (.NOT.feasible) CALL write_pr91_actual_store_failures( &
      pr91_stage,pr91_candidate,pr91_stored,pr91_adjustment,pr91_scale, &
      pr91_cells,pr91_target_i,pr91_target_j,pr91_target_k)
    IF (.NOT.feasible) CALL try_graupel_mixture_trial()"""
    source = replace_once(source, call, replacement, "actual solver call")
    decl = """  SUBROUTINE evaluate_joint_candidate()
    CALL joint_qnb_update"""
    source = replace_once(
        source,
        decl,
        """  SUBROUTINE evaluate_joint_candidate()
    INTEGER :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    INTEGER :: pr91_target_i(6),pr91_target_j(6),pr91_target_k(6),c,i,j,k,t
    REAL(real64) :: pr91_scale(6,4)
    REAL(real64) :: pr91_candidate(6,2,4)
    REAL(real32) :: pr91_stored(6,2,4)
    pr91_target_i=[130,194,132,196,168,231]
    pr91_target_j=[182,80,201,211,225,240]
    pr91_target_k=[2,22,19,16,20,20]
    pr91_cells=0; c=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      c=c+1
      DO t=1,6
        IF (i==pr91_target_i(t).AND.j==pr91_target_j(t).AND.k==pr91_target_k(t)) &
          pr91_cells(t)=c
      END DO
    END DO
    END DO
    END DO
    CALL joint_qnb_update""",
        "host solver trace arrays",
    )
    tail = """  END SUBROUTINE evaluate_joint_candidate

  SUBROUTINE try_graupel_mixture_trial()"""
    writer = """  END SUBROUTINE evaluate_joint_candidate

  SUBROUTINE write_pr91_actual_store_failures(pr91_stage,pr91_candidate,pr91_stored, &
      pr91_adjustment,pr91_scale,pr91_cells,pr91_target_i,pr91_target_j,pr91_target_k)
    INTEGER,INTENT(IN) :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    INTEGER,INTENT(IN) :: pr91_target_i(6),pr91_target_j(6),pr91_target_k(6)
    REAL(real64),INTENT(IN) :: pr91_candidate(6,2,4),pr91_scale(6,4)
    REAL(real32),INTENT(IN) :: pr91_stored(6,2,4)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: u,ios,c,i,k,j,p,t
    OPEN(NEWUNIT=u,FILE='pr91_actual_store_failures.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) CALL wrf_error_fatal('PR91 trace open failed')
    CALL get_environment_variable('PR91_RUN_ID',run_id,STATUS=ios)
    IF (ios/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR91_RUN_ID is required')
    WRITE(u,*) 'PR91_HOST_STORE_TRACE_V1',TRIM(run_id)
    WRITE(u,*) 'META: attempt_id,timestep,rk,pair,i,j,k,attempted_scale,dt'
    WRITE(u,*) 'R64: carriers,base,source,transport,candidate,density,mass_bounds,number_bounds,stored'
    WRITE(u,*) 'HEX64: candidate,source,transport,mass_bounds,number_bounds'
    WRITE(u,*) 'HEX32: stored,density,carriers,base,dt; tail:failure_stage,adjustment'
    WRITE(u,*) 'OPTIONS: run_id,attempt,timestep,rk,pair,i,j,k,subnormal,normal_adjust'
    WRITE(u,*) 'OPTIONS2: quantum_absence,strict_mass,inactive_limit,volume_bounds'
    WRITE(u,*) 'OPTIONS3: number_pair_bounds,strict_number_pair,inactive_value'
    DO t=1,6
      c=pr91_cells(t)
      IF (c<=0) CYCLE
      i=pr91_target_i(t); j=pr91_target_j(t); k=pr91_target_k(t)
      DO p=1,4
        IF (pr91_stage(t,p)<=0) CYCLE
        WRITE(u,'(a,1x,a,7i10,1p,19es26.17,10(1x,z16.16),8(1x,z8.8),2i6)') &
          'ACTUAL_STORE_FAILURE',TRIM(run_id),MERGE(1,0,ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,pr91_scale(t,p),dt,oldcarrier(c),newcarrier(c), &
          qb(c,p),nb(c,p),qs64(c,p),ns64(c,p),qa64(c,p),na64(c,p), &
          pr91_candidate(t,1,p),pr91_candidate(t,2,p),drydensity(c),minmass(p),maxmass(p), &
          number_bounds(c,1,p),number_bounds(c,2,p),pr91_stored(t,1,p),pr91_stored(t,2,p), &
          TRANSFER(pr91_candidate(t,1,p),0_8),TRANSFER(pr91_candidate(t,2,p),0_8), &
          TRANSFER(qs64(c,p),0_8),TRANSFER(ns64(c,p),0_8), &
          TRANSFER(qa64(c,p),0_8),TRANSFER(na64(c,p),0_8), &
          TRANSFER(minmass(p),0_8),TRANSFER(maxmass(p),0_8), &
          TRANSFER(number_bounds(c,1,p),0_8),TRANSFER(number_bounds(c,2,p),0_8), &
          TRANSFER(pr91_stored(t,1,p),0_4),TRANSFER(pr91_stored(t,2,p),0_4), &
          TRANSFER(drydensity(c),0_4),TRANSFER(oldcarrier(c),0_4),TRANSFER(newcarrier(c),0_4), &
          TRANSFER(qb(c,p),0_4),TRANSFER(nb(c,p),0_4),TRANSFER(dt,0_4), &
          pr91_stage(t,p),pr91_adjustment(t,p)
        WRITE(u,'(A,1X,A,1X,A,6(1X,I0),8(1X,L1),1X,ES26.17)') &
          'ACTUAL_STORE_OPTIONS',TRIM(run_id), &
          MERGE('SOURCE_FIRST_FALLBACK','BASELINE             ',ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,.TRUE.,.TRUE.,.TRUE.,p==4,p==2, &
          (p==1.OR.p==3).AND.ANY(number_bounds(c,:,p)/=0.0_real64),.TRUE.,.FALSE., &
          MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2)
      END DO
    END DO
    CLOSE(u)
  END SUBROUTINE write_pr91_actual_store_failures

  SUBROUTINE try_graupel_mixture_trial()"""
    source = replace_once(source, tail, writer, "failure-only host writer")
    probe_decl = """    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    IF (.NOT.failed_pairs(4)) RETURN"""
    source = replace_once(source, probe_decl,
        """    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    CHARACTER(LEN=64) :: pr91_run_id
    INTEGER :: pr91_env_status
    IF (.NOT.failed_pairs(4)) RETURN""", "probe trace declarations")
    probe_result = """    IF (valid) failed_pairs(4)=.FALSE.
    DEALLOCATE(q_probe,n_probe)"""
    probe_record = """    IF (.NOT.valid.AND.reject_reason>0) THEN
      CALL get_environment_variable('PR91_RUN_ID',pr91_run_id,STATUS=pr91_env_status)
      IF (pr91_env_status/=0.OR.LEN_TRIM(pr91_run_id)==0) &
        CALL wrf_error_fatal('PR91_RUN_ID is required for probe trace')
      WRITE(*,'(A,1X,A,7(1X,I0),6(1X,Z16.16))') 'PROBE_GRAUPEL_REJECT', &
        TRIM(pr91_run_id),itimestep,rk,reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits
    END IF
    IF (valid) failed_pairs(4)=.FALSE.
    DEALLOCATE(q_probe,n_probe)"""
    source = replace_once(source, probe_result, probe_record, "probe rejection event")
    trial_anchor = """      IF (reject_reason>0) WRITE(*,'(A,5(1X,I0),6(1X,Z16.16))') &
        'PR87_GRAUPEL_TRIAL_REJECT',reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits"""
    trial_replacement = """      IF (reject_reason>0) WRITE(*,'(A,7(1X,I0))') &
        'PR91_GRAUPEL_TRIAL_REJECT_CONTEXT',itimestep,rk,reject_reason,reject_pair, &
        reject_i,reject_j,reject_k
      IF (reject_reason>0) WRITE(*,'(A,5(1X,I0),6(1X,Z16.16))') &
        'PR87_GRAUPEL_TRIAL_REJECT',reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits"""
    source = replace_once(source, trial_anchor, trial_replacement, "graupel trial rejection context")
    mixture_anchor = """                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1"""
    mixture_replacement = """                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                CALL write_pr91_mixture_store_reject(itimestep,rk,p,i,k,j,c,dt,newcarrier(c), &
                    weights,q_terms,n_terms)
                RETURN
              END IF
              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1"""
    source = replace_once(source, mixture_anchor, mixture_replacement, "mixture store rejection")
    mixture_proc = """  SUBROUTINE write_pr91_mixture_store_reject(timestep,rk,pair,i,k,j,cell,dt,denominator, &
      weights,q_terms,n_terms)
    INTEGER,INTENT(IN) :: timestep,rk,pair,i,k,j,cell
    REAL(real32),INTENT(IN) :: dt,denominator,q_terms(7),n_terms(7)
    REAL(real64),INTENT(IN) :: weights(7)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: env_status
    CALL get_environment_variable('PR91_RUN_ID',run_id,STATUS=env_status)
    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) &
      CALL wrf_error_fatal('PR91_RUN_ID is required for mixture trace')
    WRITE(*,'(A,1X,A,8(1X,I0),1X,A,1X,Z8.8)') 'PR91_MIXTURE_STORE_REJECT',TRIM(run_id), &
      timestep,rk,4,pair,i,j,k,cell,'PR87_GRAUPEL_DONOR_ORDER_V1',TRANSFER(denominator,0_int32)
    WRITE(*,'(A,1X,A,7(1X,Z16.16))') 'PR91_MIXTURE_WEIGHTS64',TRIM(run_id), &
      TRANSFER(weights,0_int64,7)
    WRITE(*,'(A,1X,A,14(1X,Z8.8))') 'PR91_MIXTURE_TERMS32',TRIM(run_id), &
      TRANSFER(q_terms,0_int32,7),TRANSFER(n_terms,0_int32,7)
    WRITE(*,'(A,1X,A,1X,Z8.8)') 'PR91_MIXTURE_DT32',TRIM(run_id),TRANSFER(dt,0_int32)
  END SUBROUTINE write_pr91_mixture_store_reject

  SUBROUTINE graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,valid)"""
    source = replace_once(source,
        "  SUBROUTINE graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,valid)",
        mixture_proc, "mixture failure evidence procedure")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    original_core = args.core.read_text()
    core = instrument_core(original_core)
    host = instrument_host(args.host.read_text(), core, original_core)
    (args.out / args.core.name).write_text(core)
    (args.out / args.host.name).write_text(host)
    print(f"wrote failure-only trace sources to {args.out}")


if __name__ == "__main__":
    main()
