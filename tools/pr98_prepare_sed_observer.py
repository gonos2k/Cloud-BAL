#!/usr/bin/env python3
"""Add a read-only accepted-face capture to the frozen PR97 C1 diagnostic."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = "4872609b7a0b28f4214269dbf9298583a427ac19503c960412404959311b7a13"


def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"expected exactly one diagnostic source anchor: {before[:80]!r}")
    return text.replace(before, after, 1)


def prepare(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("face observer requires the frozen PR97 C1 diagnostic source")
    text = source.decode("ascii")
    start = text.index("SUBROUTINE pr85_kdm6_paired_sediment_column(")
    end_marker = "END SUBROUTINE pr85_kdm6_paired_sediment_column"
    end = text.index(end_marker, start) + len(end_marker)
    routine = text[start:end]
    routine = replace_once(routine,
        "USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64\n"
        "USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite\n",
        "USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64\n"
        "USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite\n"
        "USE pr98_budget_face_observer, ONLY: pr98_face_record,pr98_accumulate\n")
    routine = replace_once(routine,
        "LOGICAL :: candidate_valid,full_empty_unpaired\n",
        "LOGICAL :: candidate_valid,full_empty_unpaired\n"
        "INTEGER :: pr98_nonzero_packets\n"
        "REAL(real32) :: pr98_donor_before,pr98_receiver_before\n"
        "REAL(real32) :: pr98_receiver_density,pr98_receiver_dz\n"
        "REAL(real64) :: pr98_packet_sum,pr98_donor_error,pr98_receiver_error,pr98_packet\n"
        "REAL(real64) :: pr98_store_change_abs,pr98_donor_delta,pr98_receiver_delta\n"
        "REAL(real64) :: pr98_donor_comp,pr98_receiver_comp\n"
        "REAL(real64) :: pr98_donor_term,pr98_receiver_term,pr98_face_event_l1,pr98_max_face_error\n")
    routine = replace_once(routine,
        "approved_q_sum=0.0_real64\napproved_n_sum=0.0_real64\n",
        "approved_q_sum=0.0_real64\napproved_n_sum=0.0_real64\n"
        "pr98_packet_sum=0.0_real64; pr98_donor_error=0.0_real64\n"
        "pr98_receiver_error=0.0_real64; pr98_store_change_abs=0.0_real64\n"
        "pr98_face_event_l1=0.0_real64; pr98_max_face_error=0.0_real64\n")
    routine = replace_once(routine,
        "pr98_face_event_l1=0.0_real64; pr98_max_face_error=0.0_real64\n",
        "pr98_face_event_l1=0.0_real64; pr98_max_face_error=0.0_real64\n"
        "pr98_donor_comp=0.0_real64; pr98_receiver_comp=0.0_real64\n"
        "pr98_nonzero_packets=0\n")
    routine = replace_once(routine,
        "candidate_valid=accepted\nIF (.NOT.accepted) RETURN\nqwork(donor)=qd; nwork(donor)=nd\n",
        "candidate_valid=accepted\nIF (.NOT.accepted) RETURN\n"
        "IF(trace) THEN\n"
        "  pr98_donor_before=qwork(donor)\n"
        "  pr98_receiver_before=0.0_real32\n"
        "  pr98_receiver_density=0.0_real32; pr98_receiver_dz=0.0_real32\n"
        "  IF(has_receiver) THEN\n"
        "    pr98_receiver_before=qwork(receiver)\n"
        "    pr98_receiver_density=dry_density(receiver); pr98_receiver_dz=delz(receiver)\n"
        "  ENDIF\n"
        "  CALL pr98_face_record(cell_i,lat,substep,mode,donor,receiver,has_receiver, &\n"
        "       theta_local,pq,pr98_donor_before,qd,dry_density(donor),delz(donor), &\n"
        "       pr98_receiver_before,qr,pr98_receiver_density,pr98_receiver_dz)\n"
        "  pr98_packet=theta_local*pq\n"
        "  IF(pr98_packet/=0.0_real64) pr98_nonzero_packets=pr98_nonzero_packets+1\n"
        "  pr98_packet_sum=pr98_packet_sum+pr98_packet\n"
        "  pr98_donor_delta=(REAL(qd,real64)-REAL(qwork(donor),real64))* &\n"
        "       REAL(dry_density(donor),real64)*REAL(delz(donor),real64)\n"
        "  pr98_donor_term=pr98_donor_delta+pr98_packet\n"
        "  CALL pr98_accumulate(pr98_donor_error,pr98_donor_comp,pr98_donor_term)\n"
        "  pr98_store_change_abs=pr98_store_change_abs+ABS(pr98_donor_delta)\n"
        "  IF(has_receiver) THEN\n"
        "    pr98_receiver_delta=(REAL(qr,real64)-REAL(qwork(receiver),real64))* &\n"
        "         REAL(dry_density(receiver),real64)*REAL(delz(receiver),real64)\n"
        "    pr98_receiver_term=pr98_receiver_delta-pr98_packet\n"
        "    CALL pr98_accumulate(pr98_receiver_error,pr98_receiver_comp,pr98_receiver_term)\n"
        "    pr98_store_change_abs=pr98_store_change_abs+ABS(pr98_receiver_delta)\n"
        "  ELSE\n"
        "    pr98_receiver_term=0.0_real64\n"
        "  ENDIF\n"
        "  pr98_face_event_l1=pr98_face_event_l1+ABS(pr98_donor_term)+ABS(pr98_receiver_term)\n"
        "  pr98_max_face_error=MAX(pr98_max_face_error,ABS(pr98_donor_term),ABS(pr98_receiver_term))\n"
        "ENDIF\n"
        "qwork(donor)=qd; nwork(donor)=nd\n")
    routine = replace_once(routine,
        "IF (io_status/=0) ERROR STOP 'PR85 paired sedimentation ledger write failed'\nENDIF\nqstate=qwork\n",
        "IF (io_status/=0) ERROR STOP 'PR85 paired sedimentation ledger write failed'\nENDIF\n"
        "IF(trace .AND. (mode==PR85_SED_ICE .OR. mode==PR87_SED_RAIN)) THEN\n"
        "  WRITE(budget_unit,'(a,6i8,1p,10es26.17)',IOSTAT=io_status) &\n"
        "       'PR98_SED_FACE_SUM',cell_i,lat,substep,mode,nlevels,pr98_nonzero_packets,approved_q_sum, &\n"
        "       pr98_packet_sum,pr98_donor_error+pr98_donor_comp, &\n"
        "       pr98_receiver_error+pr98_receiver_comp,residual_q, &\n"
        "       stored_delta_q,ground_approved_q,pr98_store_change_abs, &\n"
        "       pr98_face_event_l1,pr98_max_face_error\n"
        "  IF(io_status/=0) ERROR STOP 'PR98 face summary write failed'\nENDIF\n"
        "qstate=qwork\n")
    return (text[:start] + routine + text[end:]).encode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_bytes(prepare(args.source.read_bytes()))


if __name__ == "__main__":
    main()
