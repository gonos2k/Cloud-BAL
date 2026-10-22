#!/usr/bin/env python3
"""Add a failure-only record at the first grouped candidate predicate."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


SOURCE_SHA256 = "f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def replace_once(source: str, before: str, after: str, label: str) -> str:
    if source.count(before) != 1:
        raise ValueError(f"expected one {label} anchor")
    return source.replace(before, after, 1)


def transform(source: str, expected_sha256: str = SOURCE_SHA256) -> str:
    if sha256(source) != expected_sha256:
        raise ValueError("C1 staged module_em source hash mismatch")
    # The core returns the first failing cell/pair and the exact predicate.  The
    # optional arrays are allocated only by the one timestep-gated host call.
    source = replace_once(
        source,
        "                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells)\n",
        "                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells, &\n"
        "                              group_failure_cell, group_failure_pair, group_failure_predicate, &\n"
        "                              group_failure_store_stage, group_failure_candidate64, &\n"
        "                              group_failure_stored32, group_failure_enabled)\n",
        "group failure outputs",
    )
    source = replace_once(
        source,
        "    integer, intent(in), optional :: diagnostic_cells(:)\n",
        "    integer, intent(in), optional :: diagnostic_cells(:)\n"
        "    integer, intent(out), optional :: group_failure_cell, group_failure_pair\n"
        "    integer, intent(out), optional :: group_failure_predicate, group_failure_store_stage\n"
        "    real(real64), intent(out), optional :: group_failure_candidate64(2)\n"
        "    real(real32), intent(out), optional :: group_failure_stored32(2)\n",
        "group failure declarations",
    )
    source = replace_once(
        source,
        "    real(real32), intent(out), optional :: group_failure_stored32(2)\n",
        "    real(real32), intent(out), optional :: group_failure_stored32(2)\n"
        "    logical, intent(in), optional :: group_failure_enabled\n",
        "group failure enable declaration",
    )
    source = replace_once(
        source,
        "    integer, allocatable :: local_inactive_q_quantum_adjustments(:)\n",
        "    integer, allocatable :: local_inactive_q_quantum_adjustments(:)\n"
        "    integer, allocatable :: local_failure_stage(:,:)\n"
        "    real(real64) :: failure_q64, failure_n64\n",
        "group failure locals",
    )
    source = replace_once(
        source,
        "    logical :: use_bulk_volume_absence\n",
        "    logical :: use_bulk_volume_absence, capture_group_failure\n",
        "group failure enable local",
    )
    source = replace_once(
        source,
        "    feasible = .false.\n    if (present(diagnostic_stage)) diagnostic_stage = 0\n",
        "    feasible = .false.\n"
        "    if (present(group_failure_cell)) group_failure_cell=0\n"
        "    if (present(group_failure_pair)) group_failure_pair=0\n"
        "    if (present(group_failure_predicate)) group_failure_predicate=0\n"
        "    if (present(group_failure_store_stage)) group_failure_store_stage=0\n"
        "    if (present(group_failure_candidate64)) group_failure_candidate64=0.0_real64\n"
        "    if (present(group_failure_stored32)) group_failure_stored32=0.0_real32\n"
        "    capture_group_failure=.false.\n"
        "    if (present(group_failure_enabled)) capture_group_failure=group_failure_enabled\n"
        "    if (present(diagnostic_stage)) diagnostic_stage = 0\n",
        "group failure initialization",
    )
    source = replace_once(
        source,
        "    allocate(q_candidate(ncells,npairs), n_candidate(ncells,npairs))\n",
        "    allocate(q_candidate(ncells,npairs), n_candidate(ncells,npairs))\n"
        "    if (present(group_failure_cell) .and. capture_group_failure) then\n"
        "      if (.not.present(group_failure_pair) .or. .not.present(group_failure_predicate) .or. &\n"
        "          .not.present(group_failure_store_stage) .or. .not.present(group_failure_candidate64) .or. &\n"
        "          .not.present(group_failure_stored32)) return\n"
        "      allocate(local_failure_stage(ncells,npairs)); local_failure_stage=0\n"
        "    end if\n",
        "group failure storage allocation",
    )
    source = replace_once(
        source,
        "            if (.not. storage_valid) then\n",
        "            if (.not. storage_valid) then\n"
        "              if (allocated(local_failure_stage)) local_failure_stage(i,p)=local_store_stage\n",
        "store stage capture",
    )
    source = replace_once(
        source,
        "          if (.not.pair_valid) return\n",
        "          if (.not.pair_valid) then\n"
        "            call record_group_failure(i,p,1)\n"
        "            return\n"
        "          end if\n",
        "joint predicate capture",
    )
    source = replace_once(
        source,
        "            if (.not. volume_number_stored_contract_valid(q_candidate(i,p),n_candidate(i,p), &\n"
        "                    dry_density(i),cell_volume_bounds)) return\n",
        "            if (.not. volume_number_stored_contract_valid(q_candidate(i,p),n_candidate(i,p), &\n"
        "                    dry_density(i),cell_volume_bounds)) then\n"
        "              call record_group_failure(i,p,2)\n"
        "              return\n"
        "            end if\n",
        "volume predicate capture",
    )
    source = replace_once(
        source,
        "    logical function candidate_is_feasible()\n",
        "    subroutine record_group_failure(i,p,predicate)\n"
        "      integer, intent(in) :: i,p,predicate\n"
        "      if (.not.present(group_failure_cell) .or. .not.capture_group_failure) return\n"
        "      if (group_failure_cell/=0) return\n"
        "      group_failure_cell=i; group_failure_pair=p; group_failure_predicate=predicate\n"
        "      if (allocated(local_failure_stage)) group_failure_store_stage=local_failure_stage(i,p)\n"
        "      group_failure_stored32=[q_candidate(i,p),n_candidate(i,p)]\n"
        "      if (use_constrained_storage) then\n"
        "        failure_q64=(real(carrier_old(i),real64)*real(q_base(i,p),real64)+ &\n"
        "          real(dt,real64)*(q_source_rate64(i,p)+q_transport_rate64(i,p)))/real(carrier_new(i),real64)\n"
        "        failure_n64=(real(carrier_old(i),real64)*real(n_base(i,p),real64)+ &\n"
        "          real(dt,real64)*(n_source_rate64(i,p)+n_transport_rate64(i,p)))/real(carrier_new(i),real64)\n"
        "      else\n"
        "        failure_q64=real(q_candidate(i,p),real64); failure_n64=real(n_candidate(i,p),real64)\n"
        "      end if\n"
        "      group_failure_candidate64=[failure_q64,failure_n64]\n"
        "    end subroutine record_group_failure\n\n"
        "    logical function candidate_is_feasible()\n",
        "group failure helper",
    )
    # Host hook is enabled only for the failing C1 forecast step, and writes
    # before any existing retry/fallback callback can run.
    source = replace_once(
        source,
        "                         diagnostic_scale=pr91_scale, diagnostic_cells=pr91_cells)\n"
        "    IF (.NOT.feasible) CALL write_pr91_actual_store_failures( &\n",
        "                         diagnostic_scale=pr91_scale, diagnostic_cells=pr91_cells, &\n"
        "                         group_failure_cell=pr99_cell, group_failure_pair=pr99_pair, &\n"
        "                         group_failure_predicate=pr99_predicate, &\n"
        "                         group_failure_store_stage=pr99_stage, &\n"
        "                         group_failure_candidate64=pr99_candidate64, &\n"
        "                         group_failure_stored32=pr99_stored32, &\n"
        "                         group_failure_enabled=itimestep==32)\n"
        "    IF (.NOT.feasible .AND. itimestep==32 .AND. pr99_cell>0) &\n"
        "      CALL write_pr99_group_failure(pr99_cell,pr99_pair,pr99_predicate,pr99_stage, &\n"
        "        pr99_candidate64,pr99_stored32,ANY(source_first_pair))\n"
        "    IF (.NOT.feasible) CALL write_pr91_actual_store_failures( &\n",
        "host initial-group capture hook",
    )
    source = replace_once(
        source,
        "    INTEGER :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)\n",
        "    INTEGER :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)\n"
        "    INTEGER :: pr99_cell,pr99_pair,pr99_predicate,pr99_stage\n"
        "    REAL(real64) :: pr99_candidate64(2)\n"
        "    REAL(real32) :: pr99_stored32(2)\n",
        "host group capture locals",
    )
    source = replace_once(
        source,
        "    IF (.NOT.feasible) CALL try_graupel_mixture_trial()\n"
        "  END SUBROUTINE evaluate_joint_candidate\n",
        "    IF (.NOT.feasible) CALL try_graupel_mixture_trial()\n"
        "    IF (itimestep==32 .AND. pr99_cell>0) &\n"
        "      CALL write_pr99_group_retry_result(pr99_cell,pr99_pair,pr99_predicate,feasible)\n"
        "  END SUBROUTINE evaluate_joint_candidate\n",
        "post-retry grouped status",
    )
    source = replace_once(
        source,
        "  SUBROUTINE try_graupel_mixture_trial()\n",
        "  SUBROUTINE write_pr99_group_failure(cell,pair,predicate,store_stage,candidate64,stored32,source_first)\n"
        "    INTEGER,INTENT(IN) :: cell,pair,predicate,store_stage\n"
        "    LOGICAL,INTENT(IN) :: source_first\n"
        "    REAL(real64),INTENT(IN) :: candidate64(2)\n"
        "    REAL(real32),INTENT(IN) :: stored32(2)\n"
        "    CHARACTER(LEN=64) :: run_id\n"
        "    INTEGER :: u,c,i,j,k,env_status\n"
        "    c=0; i=0; j=0; k=0\n"
        "    DO j=jl,jh; DO k=kl,kh; DO i=il,ih\n"
        "      c=c+1; IF (c==cell) EXIT\n"
        "    END DO; IF (c==cell) EXIT; END DO; IF (c==cell) EXIT; END DO\n"
        "    CALL GET_ENVIRONMENT_VARIABLE('PR91_RUN_ID',run_id,STATUS=env_status)\n"
        "    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR99 run id missing')\n"
        "    OPEN(NEWUNIT=u,FILE='pr99_group_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')\n"
        "    WRITE(u,*) 'PR99_GROUP_FAILURE_V1',TRIM(run_id),MERGE('SOURCE_FIRST','BASELINE    ',source_first), &\n"
        "      itimestep,rk,cell,pair,i,j,k,predicate,store_stage,store_stage==0\n"
        "    WRITE(u,*) 'R64_CANDIDATE',candidate64\n"
        "    WRITE(u,*) 'R32_STORED',stored32\n"
        "    WRITE(u,*) 'R32_CARRIERS',oldcarrier(cell),newcarrier(cell),drydensity(cell),dt\n"
        "    WRITE(u,*) 'R32_BASE',qb(cell,pair),nb(cell,pair)\n"
        "    WRITE(u,*) 'R64_SOURCE_RATE',qs64(cell,pair),ns64(cell,pair)\n"
        "    WRITE(u,*) 'R64_TRANSPORT_RATE',qa64(cell,pair),na64(cell,pair)\n"
        "    WRITE(u,*) 'R64_MASS_BOUNDS',minmass(pair),maxmass(pair)\n"
        "    WRITE(u,*) 'R64_NUMBER_BOUNDS',number_bounds(cell,:,pair)\n"
        "    WRITE(u,*) 'CELLS_AND_PAIRS',SIZE(qb,1),SIZE(qb,2)\n"
        "    WRITE(u,*) 'OPT_joint_constrained_storage',.TRUE.\n"
        "    WRITE(u,*) 'OPT_joint_quantum_absence',.TRUE.\n"
        "    WRITE(u,*) 'OPT_normal_q_adjustment',.TRUE.\n"
        "    WRITE(u,*) 'OPT_strict_mass_pair',pair==4\n"
        "    WRITE(u,*) 'OPT_inactive_mass_pair',pair==2\n"
        "    WRITE(u,*) 'OPT_inactive_q_quantum_pair',pair==2\n"
        "    WRITE(u,*) 'OPT_bulk_volume_quantum_storage',.TRUE.\n"
        "    WRITE(u,*) 'OPT_number_pair_bounds',.TRUE.\n"
        "    WRITE(u,*) 'OPT_source_first_fallback',source_first\n"
        "    WRITE(u,*) 'R64_INACTIVE_MASS_LIMIT', &\n"
        "      MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,pair==2)\n"
        "    WRITE(u,'(A,Z16.16)') 'HEX64_INACTIVE_MASS_LIMIT ', &\n"
        "      TRANSFER(MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,pair==2),0_int64)\n"
        "    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_CANDIDATE',TRANSFER(candidate64,0_int64,2)\n"
        "    WRITE(u,'(A,2(1X,Z8.8))') 'HEX32_STORED',TRANSFER(stored32,0_int32,2)\n"
        "    WRITE(u,'(A,4(1X,Z8.8))') 'HEX32_CARRIERS_DT', &\n"
        "      TRANSFER(oldcarrier(cell),0_int32),TRANSFER(newcarrier(cell),0_int32), &\n"
        "      TRANSFER(drydensity(cell),0_int32),TRANSFER(dt,0_int32)\n"
        "    WRITE(u,'(A,2(1X,Z8.8))') 'HEX32_BASE',TRANSFER(qb(cell,pair),0_int32), &\n"
        "      TRANSFER(nb(cell,pair),0_int32)\n"
        "    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_SOURCE_RATE',TRANSFER(qs64(cell,pair),0_int64), &\n"
        "      TRANSFER(ns64(cell,pair),0_int64)\n"
        "    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_TRANSPORT_RATE',TRANSFER(qa64(cell,pair),0_int64), &\n"
        "      TRANSFER(na64(cell,pair),0_int64)\n"
        "    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_MASS_BOUNDS',TRANSFER(minmass(pair),0_int64), &\n"
        "      TRANSFER(maxmass(pair),0_int64)\n"
        "    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_NUMBER_BOUNDS', &\n"
        "      TRANSFER(number_bounds(cell,1,pair),0_int64), &\n"
        "      TRANSFER(number_bounds(cell,2,pair),0_int64)\n"
        "    CLOSE(u)\n"
        "  END SUBROUTINE write_pr99_group_failure\n\n"
        "  SUBROUTINE write_pr99_group_retry_result(cell,pair,predicate,retry_feasible)\n"
        "    INTEGER,INTENT(IN) :: cell,pair,predicate\n"
        "    LOGICAL,INTENT(IN) :: retry_feasible\n"
        "    CHARACTER(LEN=64) :: run_id\n"
        "    INTEGER :: u,env_status\n"
        "    CALL GET_ENVIRONMENT_VARIABLE('PR91_RUN_ID',run_id,STATUS=env_status)\n"
        "    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR99 run id missing')\n"
        "    OPEN(NEWUNIT=u,FILE='pr99_group_failure.raw',STATUS='OLD',POSITION='APPEND')\n"
        "    WRITE(u,*) 'PR99_GROUP_POST_RETRY_V1',TRIM(run_id),itimestep,rk,cell,pair,predicate,retry_feasible\n"
        "    CLOSE(u)\n"
        "  END SUBROUTINE write_pr99_group_retry_result\n\n"
        "  SUBROUTINE try_graupel_mixture_trial()\n",
        "group failure writer",
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = transform(args.source.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(result)
    print(f"generated_sha256={sha256(result)}")


if __name__ == "__main__":
    main()
