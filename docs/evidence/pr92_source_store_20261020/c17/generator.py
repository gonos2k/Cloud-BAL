#!/usr/bin/env python3
"""Wire the reviewed bulk-volume representation opt-in into the C14 host."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pr91_host_store_trace import instrument_core, replace_once
from pr92_diffusion_producer_capture import TARGETS


D1_SHA256 = "1d6538e3e1aeb59a2f0f38b2ec8de8aef11c4991e2d6ae0c8d4641b065c821ef"
CORE_SHA256 = "aae36b8e259f7ef477429e8aa726c56668348ed2d3e8572b3eb71b3da723377e"


def digest(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def transform_module(source: str, core: str) -> str:
    if digest(source) != D1_SHA256 or digest(core) != CORE_SHA256:
        raise ValueError("unexpected diagnostic host or reviewed bulk-volume core")
    begin = source.index("module cloud_bal_joint_transport\n")
    marker = "end module cloud_bal_joint_transport"
    end = source.index(marker, begin) + len(marker)
    source = source[:begin] + instrument_core(core, CORE_SHA256).rstrip() + source[end:]

    def change(old: str, new: str, label: str) -> None:
        nonlocal source
        source = replace_once(source, old, new, label)

    change("  INTEGER :: inactive_q_quantum_adjustments(4)\n",
           "  INTEGER :: inactive_q_quantum_adjustments(4),bulk_volume_absences\n"
           "  REAL(real64) :: bulk_volume_delta(2)\n", "host bulk ledger locals")
    change("  WRITE(u,*) 'INACTIVE_Q_QUANTUM_ADJUSTMENTS',inactive_q_quantum_adjustments\n",
           "  WRITE(u,*) 'INACTIVE_Q_QUANTUM_ADJUSTMENTS',inactive_q_quantum_adjustments\n"
           "  WRITE(u,'(A,3(1X,I0),2(1X,ES26.17))') &\n"
           "    'BULK_VOLUME_ABSENCE',itimestep,rk,bulk_volume_absences,bulk_volume_delta\n",
           "committed bulk-volume event ledger")
    change("                         inactive_q_quantum_adjustments=inactive_q_quantum_adjustments, &\n",
           "                         inactive_q_quantum_adjustments=inactive_q_quantum_adjustments, &\n"
           "                         bulk_volume_quantum_absence=.TRUE., &\n"
           "                         bulk_volume_absences=bulk_volume_absences, &\n"
           "                         bulk_volume_delta=bulk_volume_delta, &\n",
           "grouped bulk-volume opt-in")
    change("    INTEGER :: trial_inactive_q_quantum_adjustments(4)\n",
           "    INTEGER :: trial_inactive_q_quantum_adjustments(4),trial_bulk_volume_absences\n"
           "    REAL(real64) :: trial_bulk_volume_delta(2)\n", "fallback trial bulk ledger")
    change("    trial_inactive_q_quantum_adjustments=0\n",
           "    trial_inactive_q_quantum_adjustments=0\n"
           "    trial_bulk_volume_absences=0; trial_bulk_volume_delta=0.0_real64\n",
           "fallback trial bulk reset")
    change("                                     trial_inactive_q_quantum_adjustments)\n",
           "                                     trial_inactive_q_quantum_adjustments, &\n"
           "                                 allow_bulk_absence=.TRUE., &\n"
           "                                 bulk_absences=trial_bulk_volume_absences, &\n"
           "                                 bulk_delta=trial_bulk_volume_delta)\n",
           "committed fallback bulk opt-in")
    change("    inactive_q_quantum_adjustments=trial_inactive_q_quantum_adjustments\n",
           "    inactive_q_quantum_adjustments=trial_inactive_q_quantum_adjustments\n"
           "    bulk_volume_absences=trial_bulk_volume_absences\n"
           "    bulk_volume_delta=trial_bulk_volume_delta\n", "fallback atomic bulk commit")
    change("      inactive_q_quantum_adjustments)\n",
           "      inactive_q_quantum_adjustments,allow_bulk_absence,bulk_absences,bulk_delta)\n",
           "certifier optional bulk outputs")
    change("    INTEGER,INTENT(OUT),OPTIONAL :: inactive_q_quantum_adjustments(4)\n",
           "    INTEGER,INTENT(OUT),OPTIONAL :: inactive_q_quantum_adjustments(4)\n"
           "    LOGICAL,INTENT(IN),OPTIONAL :: allow_bulk_absence\n"
           "    INTEGER,INTENT(OUT),OPTIONAL :: bulk_absences\n"
           "    REAL(real64),INTENT(OUT),OPTIONAL :: bulk_delta(2)\n"
           "    LOGICAL :: use_bulk_absence\n", "certifier bulk declarations")
    change("    IF (PRESENT(inactive_q_quantum_adjustments)) inactive_q_quantum_adjustments=0\n",
           "    IF (PRESENT(inactive_q_quantum_adjustments)) inactive_q_quantum_adjustments=0\n"
           "    IF (PRESENT(bulk_absences)) bulk_absences=0\n"
           "    IF (PRESENT(bulk_delta)) bulk_delta=0.0_real64\n"
           "    use_bulk_absence=.FALSE.\n"
           "    IF (PRESENT(allow_bulk_absence)) use_bulk_absence=allow_bulk_absence\n",
           "certifier bulk reset")
    change("    valid=.FALSE.\n    DO p=first_pair,last_pair\n",
           "    valid=.FALSE.\n"
           "    IF (use_bulk_absence.AND.(.NOT.PRESENT(bulk_absences).OR. &\n"
           "        .NOT.PRESENT(bulk_delta))) RETURN\n"
           "    DO p=first_pair,last_pair\n", "certifier bulk output requirement")
    change("                  strict_mass_ratio=.TRUE.,failure_stage=pr92_store_failure_stage)\n",
           "                  strict_mass_ratio=.TRUE.,failure_stage=pr92_store_failure_stage, &\n"
           "                  allow_bulk_volume_quantum_absence=use_bulk_absence)\n",
           "certifier bulk-volume store")
    change("            q_trial(c,p)=stored_q; n_trial(c,p)=stored_n\n",
           "            IF (use_bulk_absence.AND.p==4.AND.adjustment==5) THEN\n"
           "              bulk_absences=bulk_absences+1\n"
           "              bulk_delta=bulk_delta+[delta_q,delta_n]\n"
           "            END IF\n"
           "            q_trial(c,p)=stored_q; n_trial(c,p)=stored_n\n",
           "certifier code-five-only ledger")
    change("              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1\n",
           "              IF (itimestep==15) CALL write_pr92_valid_mixture(c,i,k,j,weights, &\n"
           "                  q_terms,n_terms,value_q,value_n,stored_q,stored_n,delta_q,delta_n)\n"
           "              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1\n",
           "T15 unchanged-mixture trial witness")
    change("    INTEGER :: probe_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count\n",
           "    INTEGER :: probe_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count\n"
           "    INTEGER :: probe_bulk_absences\n"
           "    REAL(real64) :: probe_bulk_delta(2)\n", "probe bulk policy outputs")
    change("        tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,.TRUE.)\n",
           "        tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,.TRUE., &\n"
           "        allow_bulk_absence=.TRUE.,bulk_absences=probe_bulk_absences, &\n"
           "        bulk_delta=probe_bulk_delta)\n", "same bulk policy for retry-selection probe")
    coordinates = ", &\n        ".join(",".join(map(str, point)) for point in TARGETS)
    helper = """  SUBROUTINE write_pr92_valid_mixture(c,i,k,j,weights,q_terms,b_terms, &
      candidate_q,candidate_b,stored_q,stored_b,delta_q,delta_b)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(IN) :: weights(7),candidate_q,candidate_b,delta_q,delta_b
    REAL(real32),INTENT(IN) :: q_terms(7),b_terms(7),stored_q,stored_b
    INTEGER :: u
    INTEGER,PARAMETER :: targets(3,12)=RESHAPE([ &
        COORDINATES], [3,12])
    ! Coordinate selection bounds diagnostic I/O only; it never changes a trial.
    IF (itimestep/=15.OR.rk/=1) RETURN
    IF (.NOT.ANY(targets(1,:)==i.AND.targets(2,:)==j.AND.targets(3,:)==k)) RETURN
    ! This witnesses a valid local trial, not its later transaction commit.
    OPEN(NEWUNIT=u,FILE='pr92_valid_mixture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,7(1X,I0))') 'PR92_MIXTURE_TRIAL',itimestep,rk,i,j,k,c, &
        MERGE(1,0,ANY(source_first_pair))
    WRITE(u,'(A,7(1X,Z16.16))') 'PR92_MIXTURE_WEIGHTS64',TRANSFER(weights,0_int64,7)
    WRITE(u,'(A,14(1X,Z8.8))') 'PR92_MIXTURE_TERMS32', &
        TRANSFER(q_terms,0_int32,7),TRANSFER(b_terms,0_int32,7)
    WRITE(u,'(A,11(1X,Z16.16))') 'PR92_MIXTURE_VALUES64', &
        TRANSFER(candidate_q,0_int64),TRANSFER(candidate_b,0_int64), &
        TRANSFER(delta_q,0_int64),TRANSFER(delta_b,0_int64), &
        TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
        TRANSFER(qa64(c,4),0_int64),TRANSFER(na64(c,4),0_int64), &
        TRANSFER(minmass(4),0_int64),TRANSFER(maxmass(4),0_int64), &
        TRANSFER(REAL(newcarrier(c),real64),0_int64)
    WRITE(u,'(A,8(1X,Z8.8))') 'PR92_MIXTURE_VALUES32', &
        TRANSFER(stored_q,0_int32),TRANSFER(stored_b,0_int32), &
        TRANSFER(dt,0_int32),TRANSFER(oldcarrier(c),0_int32),TRANSFER(newcarrier(c),0_int32), &
        TRANSFER(drydensity(c),0_int32),TRANSFER(qb(c,4),0_int32),TRANSFER(nb(c,4),0_int32)
    WRITE(u,'(A)') 'PR92_MIXTURE_END'
    CLOSE(u)
  END SUBROUTINE write_pr92_valid_mixture

"""
    helper = helper.replace("COORDINATES", coordinates)
    change("  SUBROUTINE write_pr92_store_failure_capture(context,stage,c,i,k,j,value_q,value_n,qs,nsource,qa,na, &\n",
           helper + "  SUBROUTINE write_pr92_store_failure_capture(context,stage,c,i,k,j,value_q,value_n,qs,nsource,qa,na, &\n",
           "valid-mixture witness helper")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("module", "core", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    result = transform_module(args.module.read_text(), args.core.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(result)
    print(f"generated_sha256={digest(result)}")


if __name__ == "__main__":
    main()
