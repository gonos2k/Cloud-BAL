#!/usr/bin/env python3
"""Inject and summarize bounded PR92 graupel source identity captures."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

C14_MODULE_SHA256 = "6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1"
PRODUCER_KEYS = ("step", "rk", "channel", "im", "i", "j", "k")
IDENTITY_GUARD = """    IF (TRANSFER(qs64(c,4),0_int64)/=TRANSFER(qdiff,0_int64).OR. &
        TRANSFER(ns64(c,4),0_int64)/=TRANSFER(ndiff,0_int64)) THEN
      WRITE(*,'(A,5(1X,I0),4(1X,Z16.16))') 'PR87_GRAUPEL_SOURCE_IDENTITY_FAIL', &
        itimestep,rk,i,j,k,TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
        TRANSFER(qdiff,0_int64),TRANSFER(ndiff,0_int64)
      valid=.FALSE.; RETURN
    END IF"""

CAPTURE = """    IF (TRANSFER(qs64(c,4),0_int64)/=TRANSFER(qdiff,0_int64).OR. &
        TRANSFER(ns64(c,4),0_int64)/=TRANSFER(ndiff,0_int64)) THEN
      CALL write_pr92_graupel_source_capture(c,i,k,j,weights,q_terms,n_terms, &
          qdiff,ndiff,qface,nface)
      valid=.FALSE.; RETURN
    END IF"""

WRITER = """
  SUBROUTINE write_pr92_graupel_source_capture(c,i,k,j,weights,q_terms,n_terms, &
                                               qdiff,ndiff,qface,nface)
    USE iso_fortran_env, ONLY: int32,int64,real32,real64
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(IN) :: weights(7),qdiff,ndiff
    REAL(real32),INTENT(IN) :: q_terms(7),n_terms(7)
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128),INTENT(IN) :: qface(4),nface(4)
    INTEGER :: u,dx,dy
    OPEN(NEWUNIT=u,FILE='pr92_graupel_source_capture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,5(1X,I0),1X,I0)') 'PR92_FAIL',itimestep,rk,i,j,k,c
    IF (PRESENT(pr87_all_pair_diffusion_identity)) THEN
      WRITE(u,'(A,1X,8(I0,1X))') 'PR92_PRODUCER_IDENTITY', &
        pr87_all_pair_diffusion_identity
    ELSE
      WRITE(u,'(A)') 'PR92_PRODUCER_IDENTITY UNAVAILABLE'
    END IF
    WRITE(u,'(A,8(1X,Z8.8))') 'PR92_R32',TRANSFER(dt,0_int32), &
      TRANSFER(oldcarrier(c),0_int32),TRANSFER(newcarrier(c),0_int32), &
      TRANSFER(drydensity(c),0_int32),TRANSFER(qt(i,k,j,qindex(4)),0_int32), &
      TRANSFER(nt(i,k,j,nindex(4)),0_int32),TRANSFER(q1(i,k,j,qindex(4)),0_int32), &
      TRANSFER(n1(i,k,j,nindex(4)),0_int32)
    WRITE(u,'(A,12(1X,Z16.16))') 'PR92_R64', &
      TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
      TRANSFER(qdiff,0_int64),TRANSFER(ndiff,0_int64), &
      TRANSFER(REAL(qt(i,k,j,qindex(4)),real64),0_int64), &
      TRANSFER(REAL(nt(i,k,j,nindex(4)),real64),0_int64), &
      TRANSFER(REAL(mut_diff(i,j),real64),0_int64), &
      TRANSFER(REAL(c1(k),real64),0_int64),TRANSFER(REAL(c2(k),real64),0_int64), &
      TRANSFER(REAL(rdx,real64),0_int64),TRANSFER(REAL(rdy,real64),0_int64), &
      TRANSFER(REAL(xkmhd_diff(i,k,j),real64),0_int64)
    DO dy=-1,1
      WRITE(u,'(A,1X,I0,12(1X,Z8.8))') 'PR92_STENCIL',dy, &
        TRANSFER(q1(i-1,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(q1(i,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(q1(i+1,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(n1(i-1,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(n1(i,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(n1(i+1,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(xkmhd_diff(i-1,k,j+dy),0_int32), &
        TRANSFER(xkmhd_diff(i,k,j+dy),0_int32), &
        TRANSFER(xkmhd_diff(i+1,k,j+dy),0_int32), &
        TRANSFER(mut_diff(i-1,j+dy),0_int32),TRANSFER(mut_diff(i,j+dy),0_int32), &
        TRANSFER(mut_diff(i+1,j+dy),0_int32)
    END DO
    WRITE(u,'(A,10(1X,Z8.8))') 'PR92_METRICS', &
      TRANSFER(msfux_diff(i,j),0_int32),TRANSFER(msfux_diff(i+1,j),0_int32), &
      TRANSFER(msfuy_diff(i,j),0_int32),TRANSFER(msfuy_diff(i+1,j),0_int32), &
      TRANSFER(msfvx_inv_diff(i,j),0_int32),TRANSFER(msfvx_inv_diff(i,j+1),0_int32), &
      TRANSFER(msfvy_diff(i,j),0_int32),TRANSFER(msfvy_diff(i,j+1),0_int32), &
      TRANSFER(msftx(i,j),0_int32),TRANSFER(msfty(i,j),0_int32)
    WRITE(u,'(A,7(1X,Z16.16))') 'PR92_WEIGHTS',TRANSFER(weights,0_int64,7)
    WRITE(u,'(A,14(1X,Z8.8))') 'PR92_DONOR_TERMS', &
      TRANSFER(q_terms,0_int32,7),TRANSFER(n_terms,0_int32,7)
    WRITE(u,'(A,16(1X,Z16.16))') 'PR92_FACE_COEFFICIENTS', &
      TRANSFER(qface,0_int64,8),TRANSFER(nface,0_int64,8)
    IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN
      WRITE(u,'(A,2(1X,Z16.16))') 'PR92_CACHE_DELTA', &
        TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,7),0_int64), &
        TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,8),0_int64)
    ELSE
      WRITE(u,'(A)') 'PR92_CACHE_DELTA UNAVAILABLE'
    END IF
    CLOSE(u)
  END SUBROUTINE write_pr92_graupel_source_capture
"""

STORE_CALL = """                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                  strict_mass_ratio=.TRUE.)"""
STORE_CALL_CAPTURE = """                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                  strict_mass_ratio=.TRUE.,failure_stage=pr92_store_failure_stage)"""
STORE_REJECT = """            IF (.NOT.store_valid) THEN
              IF (p/=4) THEN"""
STORE_REJECT_CAPTURE = """            IF (.NOT.store_valid) THEN
              IF (p==4) THEN
                CALL write_pr92_store_failure_capture('CERTIFIER',pr92_store_failure_stage,c,i,k,j, &
                    value_q,value_n,qs64(c,4),ns64(c,4),qa64(c,4),na64(c,4), &
                    drydensity(c),minmass(4),maxmass(4),oldcarrier(c),newcarrier(c), &
                    qb(c,4),nb(c,4))
              END IF
              IF (p/=4) THEN"""
STORE_WRITER = """
  SUBROUTINE write_pr92_store_failure_capture(context,stage,c,i,k,j,value_q,value_n,qs,nsource,qa,na, &
                                               rho,minmass_value,maxmass_value,oldmass,newmass,qbase,nbase)
    USE iso_fortran_env, ONLY: int64,real64
    CHARACTER(LEN=*),INTENT(IN) :: context
    INTEGER,INTENT(IN) :: stage,c,i,k,j
    REAL(real64),INTENT(IN) :: value_q,value_n,qs,nsource,qa,na
    REAL(real32),INTENT(IN) :: rho,oldmass,newmass,qbase,nbase
    REAL(real64),INTENT(IN) :: minmass_value,maxmass_value
    INTEGER :: u
    OPEN(NEWUNIT=u,FILE='pr92_graupel_source_capture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,7(1X,I0),13(1X,Z16.16))') 'PR92_STORE_FAIL_'//TRIM(context), &
      itimestep,rk,i,j,k,c,stage, &
      TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
      TRANSFER(qs,0_int64),TRANSFER(nsource,0_int64),TRANSFER(qa,0_int64),TRANSFER(na,0_int64), &
      TRANSFER(REAL(rho,real64),0_int64),TRANSFER(minmass_value,0_int64), &
      TRANSFER(maxmass_value,0_int64),TRANSFER(REAL(oldmass,real64),0_int64), &
      TRANSFER(REAL(newmass,real64),0_int64),TRANSFER(REAL(qbase,real64),0_int64), &
      TRANSFER(REAL(nbase,real64),0_int64)
    WRITE(u,'(A,6(1X,Z8.8))') 'PR92_STORE_R32',TRANSFER(dt,0_int32), &
      TRANSFER(oldmass,0_int32),TRANSFER(newmass,0_int32),TRANSFER(rho,0_int32), &
      TRANSFER(qbase,0_int32),TRANSFER(nbase,0_int32)
    CLOSE(u)
  END SUBROUTINE write_pr92_store_failure_capture
"""
FULL_CALL = """             strict_mass_ratio=(p==4), &
             inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2), &
                 allow_inactive_q_quantum_adjustment=(p==2))"""
FULL_CALL_CAPTURE = """             strict_mass_ratio=(p==4), &
             inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2), &
                 allow_inactive_q_quantum_adjustment=(p==2),failure_stage=pr92_full_store_stage)"""
FULL_FAILURE = """        IF (.NOT.full_valid) THEN
          full_failures=full_failures+1"""
FULL_FAILURE_CAPTURE = """        IF (.NOT.full_valid) THEN
          IF (p==4) CALL write_pr92_store_failure_capture('FULL',pr92_full_store_stage, &
              cell,i,k,j,source_candidate(1),source_candidate(2),qs64(cell,4),ns64(cell,4), &
              qa64(cell,4),na64(cell,4),drydensity(cell),minmass(4),maxmass(4), &
              oldcarrier(cell),newcarrier(cell),qb(cell,4),nb(cell,4))
          full_failures=full_failures+1"""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _float32(bits: str) -> float:
    return struct.unpack(">f", int(bits, 16).to_bytes(4, "big"))[0]


def _float64(bits: str) -> float:
    return struct.unpack(">d", int(bits, 16).to_bytes(8, "big"))[0]


def parse_producer_capture(path: Path) -> dict[tuple[int, ...], dict[str, object]]:
    """Parse complete producer blocks; reject partial target records."""
    records: dict[tuple[int, ...], dict[str, object]] = {}
    current: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        tag = fields[0]
        if tag == "PR92_PRODUCER":
            if current is not None or len(fields) != 8:
                raise ValueError("nested or malformed PR92_PRODUCER block")
            current = dict(zip(PRODUCER_KEYS, map(int, fields[1:])))
            current.update({"stencil": {}, "ended": False})
        elif current is None:
            raise ValueError(f"producer row outside block: {tag}")
        elif tag == "PR92_PRODUCER_BOUNDS" and len(fields) == 9:
            current["identity"] = list(map(int, fields[1:]))
        elif tag == "PR92_TENDENCY" and len(fields) == 4:
            current["before32_bits"], current["after32_bits"] = fields[1:3]
            current["diffusion64_bits"] = fields[3]
        elif tag == "PR92_PRODUCER_SCALE" and len(fields) == 5:
            current["scale32_bits"] = fields[1:]
        elif tag == "PR92_PRODUCER_STENCIL" and len(fields) == 11:
            dy = int(fields[1])
            if dy not in (-1, 0, 1) or dy in current["stencil"]:
                raise ValueError("duplicate or invalid producer stencil row")
            current["stencil"][dy] = fields[2:]
        elif tag == "PR92_PRODUCER_METRICS" and len(fields) == 11:
            current["metrics32_bits"] = fields[1:]
        elif tag == "PR92_PRODUCER_END" and len(fields) == 1:
            required = {"identity", "before32_bits", "after32_bits", "diffusion64_bits",
                        "scale32_bits", "metrics32_bits"}
            if not required.issubset(current) or set(current["stencil"]) != {-1, 0, 1}:
                raise ValueError("incomplete producer capture block")
            key = tuple(int(current[name]) for name in PRODUCER_KEYS)
            if key in records:
                raise ValueError(f"duplicate producer capture key: {key}")
            current["ended"] = True
            records[key] = current
            current = None
        else:
            raise ValueError(f"malformed or unknown producer row: {tag}")
    if current is not None:
        raise ValueError("truncated producer capture block")
    if not records:
        raise ValueError("producer capture has no complete records")
    return records


def parse_consumer_capture(path: Path) -> dict[str, object]:
    """Return complete identity blocks and FULL/CERTIFIER store failures."""
    identity: list[dict[str, object]] = []
    store_failures: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    pending_store: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        tag = fields[0]
        if tag == "PR92_FAIL":
            if pending_store is not None or len(fields) != 7:
                raise ValueError("malformed or out-of-order PR92_FAIL")
            if current is not None:
                _finish_identity(current)
                identity.append(current)
            current = {"step": int(fields[1]), "rk": int(fields[2]), "i": int(fields[3]),
                       "j": int(fields[4]), "k": int(fields[5]), "cell": int(fields[6]),
                       "stencil": {}}
        elif tag.startswith("PR92_STORE_FAIL_"):
            if current is not None:
                _finish_identity(current)
                identity.append(current)
                current = None
            if pending_store is not None or tag not in {"PR92_STORE_FAIL_FULL", "PR92_STORE_FAIL_CERTIFIER"} \
                    or len(fields) != 21:
                raise ValueError("malformed PR92 store failure row")
            pending_store = {"context": tag.removeprefix("PR92_STORE_FAIL_"),
                             "step": int(fields[1]), "rk": int(fields[2]), "i": int(fields[3]),
                             "j": int(fields[4]), "k": int(fields[5]), "cell": int(fields[6]),
                             "failure_stage": int(fields[7]),
                             "candidate_bits64": fields[8:]}
        elif tag == "PR92_STORE_R32":
            if pending_store is None or len(fields) != 7:
                raise ValueError("orphan or malformed PR92_STORE_R32")
            pending_store["r32_bits"] = fields[1:]
            store_failures.append(pending_store)
            pending_store = None
        elif current is not None:
            if tag == "PR92_PRODUCER_IDENTITY" and fields[1:] == ["UNAVAILABLE"]:
                current["producer_identity"] = None
            elif tag == "PR92_PRODUCER_IDENTITY" and len(fields) == 9:
                current["producer_identity"] = list(map(int, fields[1:]))
            elif tag == "PR92_R32" and len(fields) == 9:
                current["r32_bits"] = fields[1:]
            elif tag == "PR92_R64" and len(fields) == 13:
                current["r64_bits"] = fields[1:]
                current["r64"] = [_float64(value) for value in fields[1:]]
            elif tag == "PR92_STENCIL" and len(fields) == 14:
                dy = int(fields[1])
                if dy not in (-1, 0, 1) or dy in current["stencil"]:
                    raise ValueError("duplicate or invalid consumer stencil row")
                current["stencil"][dy] = fields[2:]
            elif tag == "PR92_METRICS" and len(fields) == 11:
                current["metrics32_bits"] = fields[1:]
            elif tag == "PR92_WEIGHTS" and len(fields) == 8:
                current["weights64_bits"] = fields[1:]
            elif tag == "PR92_DONOR_TERMS" and len(fields) == 15:
                current["donor32_bits"] = fields[1:]
            elif tag == "PR92_FACE_COEFFICIENTS" and len(fields) == 17:
                current["face_coeff64_bits"] = fields[1:]
            elif tag == "PR92_CACHE_DELTA" and len(fields) in (2, 3):
                current["cache_delta64_bits"] = None if len(fields) == 2 else fields[1:]
            else:
                raise ValueError(f"malformed or unknown consumer row: {tag}")
        else:
            raise ValueError(f"consumer row outside capture block: {tag}")
    if current is not None:
        _finish_identity(current)
        identity.append(current)
    if pending_store is not None:
        raise ValueError("truncated consumer store failure block")
    if not identity and not store_failures:
        raise ValueError("consumer capture has no recognized failure records")
    return {"identity_failures": identity, "store_failures": store_failures}


def _finish_identity(record: dict[str, object]) -> None:
    required = {"producer_identity", "r32_bits", "r64_bits", "metrics32_bits", "weights64_bits",
                "donor32_bits", "face_coeff64_bits"}
    if not required.issubset(record) or set(record["stencil"]) != {-1, 0, 1}:
        raise ValueError("incomplete consumer identity capture block")


def transform_c14_module(source: str) -> str:
    if sha256(source) != C14_MODULE_SHA256:
        raise ValueError("input is not the pinned PR91 C14 module")
    if source.count(IDENTITY_GUARD) != 1:
        raise ValueError("pinned C14 source identity guard is missing or ambiguous")
    transformed = source.replace(IDENTITY_GUARD, CAPTURE)
    end = "  END SUBROUTINE add_graupel_diffusion_mixture\n"
    if transformed.count(end) != 1:
        raise ValueError("pinned C14 graupel mixture routine is missing or ambiguous")
    transformed = transformed.replace(end, end + WRITER)
    declaration = "    INTEGER :: c,i,k,j,p,adjustment,first_pair,last_pair\n"
    declaration_capture = "    INTEGER :: c,i,k,j,p,adjustment,first_pair,last_pair\n" \
        "    INTEGER :: pr92_store_failure_stage\n"
    if transformed.count(declaration) != 1:
        raise ValueError("pinned C14 certification declarations are missing or ambiguous")
    transformed = transformed.replace(declaration, declaration_capture)
    if transformed.count(STORE_CALL) != 1 or transformed.count(STORE_REJECT) != 1:
        raise ValueError("pinned C14 initial graupel store branch is missing or ambiguous")
    transformed = transformed.replace(STORE_CALL, STORE_CALL_CAPTURE)
    transformed = transformed.replace(STORE_REJECT, STORE_REJECT_CAPTURE)
    cert_end = "  END SUBROUTINE certify_graupel_storage\n"
    if transformed.count(cert_end) != 1:
        raise ValueError("pinned C14 certification routine end is missing or ambiguous")
    transformed = transformed.replace(cert_end, cert_end + STORE_WRITER)
    full_call = "  INTEGER :: stage_diag_u,stage_diag_dx,stage_diag_dy\n"
    if transformed.count(full_call) != 1 or transformed.count(FULL_CALL) != 1 \
            or transformed.count(FULL_FAILURE) != 1:
        raise ValueError("pinned C14 full-candidate audit is missing or ambiguous")
    transformed = transformed.replace(full_call, full_call +
        "  INTEGER :: pr92_full_store_stage\n")
    transformed = transformed.replace(FULL_CALL, FULL_CALL_CAPTURE)
    transformed = transformed.replace(FULL_FAILURE, FULL_FAILURE_CAPTURE)
    return transformed


def summarize_capture(path: Path) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    store_failures: list[dict[str, object]] = []
    maximum_absolute_difference = [0.0, 0.0]
    blocks: list[dict[str, int]] = []
    current: dict[str, int] | None = None
    pending_store_failure: dict[str, object] | None = None
    for line in path.read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields and fields[0] == "PR92_FAIL":
            if pending_store_failure is not None:
                raise ValueError("truncated PR92 store failure block")
            if len(fields) != 7:
                raise ValueError("malformed PR92_FAIL capture row")
            if current is not None:
                blocks.append(current)
            current = {}
            step, rk, i, j, k, cell = map(int, fields[1:])
            failures.append({"step": step, "rk": rk, "i": i, "j": j, "k": k, "cell": cell})
        elif fields[0].startswith("PR92_STORE_FAIL_"):
            if current is not None:
                blocks.append(current)
                current = None
            if pending_store_failure is not None or fields[0] not in {
                    "PR92_STORE_FAIL_FULL", "PR92_STORE_FAIL_CERTIFIER"} or len(fields) != 21:
                raise ValueError("malformed or out of order PR92 store failure row")
            step, rk, i, j, k, cell, stage = map(int, fields[1:8])
            pending_store_failure = {"step": step, "rk": rk, "i": i, "j": j, "k": k,
                                     "cell": cell, "failure_stage": stage,
                                     "context": fields[0].removeprefix("PR92_STORE_FAIL_")}
        elif fields[0] == "PR92_STORE_R32":
            if pending_store_failure is None or len(fields) != 7:
                raise ValueError("orphan or malformed PR92_STORE_R32 row")
            store_failures.append(pending_store_failure)
            pending_store_failure = None
        elif current is not None:
            expected_fields = {"PR92_PRODUCER_IDENTITY": (2, 9), "PR92_R32": (9,),
                               "PR92_R64": (13,), "PR92_STENCIL": (14,),
                               "PR92_METRICS": (11,), "PR92_WEIGHTS": (8,),
                               "PR92_DONOR_TERMS": (15,), "PR92_FACE_COEFFICIENTS": (17,),
                               "PR92_CACHE_DELTA": (2, 3)}
            if fields[0] not in expected_fields:
                raise ValueError(f"unknown PR92 identity capture record: {fields[0]}")
            if len(fields) not in expected_fields[fields[0]]:
                raise ValueError(f"malformed {fields[0]} capture row")
            current[fields[0]] = current.get(fields[0], 0) + 1
            if fields[0] == "PR92_R64":
                bits = [int(value, 16) for value in fields[1:]]
                for channel, (source_index, diffusion_index) in enumerate(((0, 2), (1, 3))):
                    source = struct.unpack(">d", bits[source_index].to_bytes(8, "big"))[0]
                    diffusion = struct.unpack(">d", bits[diffusion_index].to_bytes(8, "big"))[0]
                    maximum_absolute_difference[channel] = max(
                        maximum_absolute_difference[channel], abs(source - diffusion))
        else:
            raise ValueError(f"unexpected capture row: {fields[0]}")
    if current is not None:
        blocks.append(current)
    if pending_store_failure is not None:
        raise ValueError("truncated PR92 store failure block")
    required = {"PR92_PRODUCER_IDENTITY", "PR92_R32", "PR92_R64", "PR92_STENCIL",
                "PR92_METRICS", "PR92_WEIGHTS", "PR92_DONOR_TERMS", "PR92_FACE_COEFFICIENTS"}
    if any(not required.issubset(block) or block["PR92_STENCIL"] != 3 for block in blocks):
        raise ValueError("incomplete PR92 identity capture block")
    if not failures and not store_failures:
        raise ValueError("capture has no recognized PR92 failure records")
    first_failure = failures[0] if failures else store_failures[0]
    return {"identity_failure_count": len(failures), "store_failure_count": len(store_failures),
            "first_failure": first_failure,
            "max_abs_source_minus_recomputed_diffusion": maximum_absolute_difference}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    transform = sub.add_parser("transform")
    transform.add_argument("--module", required=True, type=Path)
    transform.add_argument("--output", required=True, type=Path)
    summary = sub.add_parser("summary")
    summary.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "transform":
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(transform_c14_module(args.module.read_text()))
    else:
        print(summarize_capture(args.capture))


if __name__ == "__main__":
    main()
