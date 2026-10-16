#!/usr/bin/env python3
"""Compile and exercise the exact PR87 native source-first procedure on ifx."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import struct
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
KERNEL = ROOT / "src/common/cloud_bal_joint_transport.f90"
DENSITY_HELPER = ROOT / "tools/pr85_joint_stage_observer.f90"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_subroutine(source: str, name: str) -> str:
    start = re.search(rf"^\s*SUBROUTINE\s+{re.escape(name)}\s*\(", source,
                      re.IGNORECASE | re.MULTILINE)
    if not start:
        raise ValueError(f"missing procedure {name}")
    tail = source[start.start():]
    end = re.search(rf"^\s*END\s+SUBROUTINE\s+{re.escape(name)}\b", tail,
                    re.IGNORECASE | re.MULTILINE)
    if not end:
        raise ValueError(f"missing terminator for {name}")
    return tail[:end.end()].strip()


def profile_flags(name: str) -> tuple[str, list[str]]:
    if name not in ("CLOUD_BAL_FREE_FLAGS", "CLOUD_BAL_REPRO_FLAGS"):
        raise ValueError(f"unsupported compiler flags: {name}")
    command = (
        f"source {shlex.quote(str(PROFILE))}; "
        f"printf '%s\\n' \"${{{name}[@]}}\""
    )
    output = subprocess.check_output(["bash", "-lc", command], text=True)
    compiler = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""],
        text=True,
    ).strip()
    return compiler, output.splitlines()


def source_text(procedure: str, density_helper: str) -> str:
    return f"""MODULE module_state_description
  INTEGER, PARAMETER :: P_QV=1
END MODULE module_state_description

MODULE source_first_test_support
  REAL, SAVE :: q2_state(1:5,1:2,1:4,6),n2_state(1:5,1:2,1:4,5)
CONTAINS
  SUBROUTINE wrf_error_fatal(message)
    CHARACTER(*),INTENT(IN) :: message
    WRITE(*,'(a,1x,a)') 'PR87_EXPECTED_FATAL',TRIM(message)
    WRITE(*,'(a,4(1x,es24.16))') 'PR87_FATAL_ATOMIC_STATE', &
         q2_state(2,1,2,2),q2_state(3,1,2,2),n2_state(2,1,2,1),n2_state(3,1,2,1)
    WRITE(*,'(a,4(1x,es24.16))') 'PR87_FATAL_ATOMIC_RAIN_STATE', &
         q2_state(2,1,2,4),q2_state(3,1,2,4),n2_state(2,1,2,3),n2_state(3,1,2,3)
    ERROR STOP 87
  END SUBROUTINE wrf_error_fatal
END MODULE source_first_test_support

MODULE source_first_procedure
  USE module_state_description, ONLY: P_QV
  USE source_first_test_support, ONLY: wrf_error_fatal
CONTAINS
{procedure}
END MODULE source_first_procedure

{density_helper}

SUBROUTINE pr85_pbl_tendency_dump(stage,itimestep,rkstep, &
     ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
     qv_tend,qc_tend,qi_tend,qnc_tend,qni_tend)
  IMPLICIT NONE
  CHARACTER(*),INTENT(IN) :: stage
  INTEGER,INTENT(IN) :: itimestep,rkstep,ims,ime,jms,jme,kms,kme
  INTEGER,INTENT(IN) :: its,ite,jts,jte,kts,kte
  REAL,INTENT(IN) :: qv_tend(*),qc_tend(*),qi_tend(*),qnc_tend(*),qni_tend(*)
END SUBROUTINE pr85_pbl_tendency_dump

PROGRAM pr87_source_first_fallback_regression
  USE iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_joint_transport, ONLY: joint_moment_store
  USE source_first_procedure, ONLY: rk_update_joint_moments
  USE source_first_test_support, ONLY: q2_state,n2_state
  IMPLICIT NONE
  INTEGER,PARAMETER :: ims=1,ime=5,jms=1,jme=4,kms=1,kme=2
  INTEGER,PARAMETER :: ids=1,ide=5,jds=1,jde=4,kds=1,kde=2
  INTEGER,PARAMETER :: its=1,ite=4,jts=2,jte=2,kts=1,kte=1
  INTEGER,PARAMETER :: nmoist=6,nscalar=5
  INTEGER :: qindex(4),nindex(4),i,j,k,mode
  REAL(real32) :: q1(ims:ime,kms:kme,jms:jme,nmoist)
  REAL(real32) :: qt(ims:ime,kms:kme,jms:jme,nmoist),n1(ims:ime,kms:kme,jms:jme,nscalar)
  REAL(real32) :: nt(ims:ime,kms:kme,jms:jme,nscalar)
  REAL(real32) :: raw_qsrc(ims:ime,kms:kme,jms:jme,2),raw_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL(real32) :: coupled_qsrc(ims:ime,kms:kme,jms:jme,2),coupled_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL(real64) :: later_qsrc(ims:ime,kms:kme,jms:jme,2),later_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL(real64) :: rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)
  REAL(real32) :: source_carrier(ims:ime,kms:kme,jms:jme),dt
  REAL(real32) :: ru(ims:ime,kms:kme,jms:jme),rv(ims:ime,kms:kme,jms:jme)
  REAL(real32) :: ww(ims:ime,kms:kme,jms:jme),muold(ims:ime,jms:jme)
  REAL(real32) :: munew(ims:ime,jms:jme),mub(ims:ime,jms:jme),c1(kms:kme),c2(kms:kme)
  REAL(real32) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme),rdnw(kms:kme)
  REAL(real32) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  REAL(real64),PARAMETER :: min_cloud=4.188790204786391e-15_real64
  REAL(real64),PARAMETER :: min_rain_mass=12566.37109375_real64/35000.0_real64**3
  REAL(real32) :: expected_q,expected_n,carrier,old_q,old_n
  REAL(real64) :: expected_q64,expected_n64
  REAL(real64) :: rain_minmass,rain_maxmass,rain_bounds(2),rain_delta_q,rain_delta_n
  REAL(real64) :: rain_qcontinuous,rain_ncontinuous
  REAL(real32) :: rain_source_q,rain_source_n,rain_old_carrier,rain_new_carrier
  REAL(real32) :: rain_expected_q,rain_expected_n
  CHARACTER(32) :: mode_text

  CALL get_command_argument(1,mode_text)
  SELECT CASE(TRIM(mode_text))
  CASE('baseline'); mode=1
  CASE('source_first'); mode=2
  CASE('virtual_donor'); mode=3
  CASE('negative_donor'); mode=4
  CASE('invalid_endpoint'); mode=5
  CASE('no_air'); mode=6
  CASE('stale_step'); mode=7
  CASE('stale_carrier'); mode=8
  CASE('stale_source_ref'); mode=9
  CASE('later_no_air'); mode=10
  CASE('nonfinite_later'); mode=11
  CASE('later_cadence'); mode=12
  CASE('rain_air_precision'); mode=13
  CASE('rain_diffusion_precision'); mode=14
  CASE('stale_diffusion_step'); mode=15
  CASE('partial_diffusion_delta'); mode=16
  CASE('partial_diffusion_step'); mode=17
  CASE('nonfinite_diffusion_delta'); mode=18
  CASE('zero_diffusion_delta'); mode=19
  CASE DEFAULT; ERROR STOP 'pass baseline, source_first, virtual_donor, negative_donor, invalid_endpoint, no_air, stale_step, stale_carrier, stale_source_ref, later_no_air, nonfinite_later, later_cadence, rain_air_precision, rain_diffusion_precision, stale_diffusion_step, partial_diffusion_delta, partial_diffusion_step, nonfinite_diffusion_delta, or zero_diffusion_delta'
  END SELECT

  qindex=[2,3,4,5]; nindex=[1,2,3,4]
  q1=0.0_real32; q2_state=0.0_real32; qt=0.0_real32
  n1=0.0_real32; n2_state=0.0_real32; nt=0.0_real32
  raw_qsrc=0.0_real32; raw_nsrc=0.0_real32
  coupled_qsrc=0.0_real32; coupled_nsrc=0.0_real32
  later_qsrc=0.0_real64; later_nsrc=0.0_real64
  rain_diffusion_delta=0.0_real64
  source_carrier=1.0_real32; dt=1.0_real32
  ru=0.25_real32; rv=0.0_real32; ww=0.0_real32
  muold=0.0_real32; munew=0.0_real32; mub=1.0_real32
  c1=1.0_real32; c2=0.0_real32; rdnw=-1.0_real32
  msftx=1.0_real32; msfty=1.0_real32; al=1.0_real32; alb=0.0_real32
  DO j=jms,jme
    DO k=kms,kme
      DO i=ims,ime
        IF (mode==1.OR.mode==2.OR.(mode>=7.AND.mode<=12)) THEN
          q1(i,k,j,qindex(1))=REAL(min_cloud*1.0e8_real64,real32)
        ELSE
          q1(i,k,j,qindex(1))=REAL(1.5_real64*min_cloud*1.0e8_real64,real32)
        END IF
        n1(i,k,j,nindex(1))=1.0e8_real32
        IF ((mode==1.OR.mode==2.OR.(mode>=7.AND.mode<=12)).AND.i==3) &
          q1(i,k,j,qindex(1))=REAL(1.5_real64*min_cloud*1.0e8_real64,real32)
      END DO
    END DO
  END DO
  IF (mode==13) THEN
    q1(1:4,1,2,qindex(3))=[0.0002928402682300657_real32, &
                            0.002892484422773123_real32, &
                            0.00017703388584777713_real32, &
                            0.01728409342467785_real32]
    n1(1:4,1,2,nindex(3))=[999136.9375_real32,9868821.0_real32, &
                            604019.0625_real32,58971320.0_real32]
  END IF
  q2_state=q1; n2_state=n1
  IF (mode==2.OR.(mode>=7.AND.mode/=10.AND.mode/=12)) THEN
    qt(2,1,2,qindex(1))=REAL(0.125_real64*min_cloud*1.0e8_real64,real32)
    qt(3,1,2,qindex(1))=REAL(-0.5_real64*min_cloud*1.0e8_real64,real32)
  ELSE IF (mode==3) THEN
    qt(2,1,2,qindex(1))=REAL(-0.625_real64*min_cloud*1.0e8_real64,real32)
  ELSE IF (mode==4) THEN
    qt(2,1,2,qindex(1))=REAL(-1.625_real64*min_cloud*1.0e8_real64,real32)
  ELSE IF (mode==5) THEN
    qt(2,1,2,qindex(1))=REAL(-1.0_real64*min_cloud*1.0e8_real64,real32)
  ELSE IF (mode==6.OR.mode==10.OR.mode==12) THEN
    carrier=REAL(92363.85_real64,real32)
    expected_q=REAL(3.7537916e-8_real64,real32)
    expected_n=8961516.0_real32
    q1(:,:,:,qindex(1))=expected_q; n1(:,:,:,nindex(1))=expected_n
    muold=0.0_real32; munew=0.0_real32; mub=1.0_real32
    c1=carrier; c2=0.0_real32
    ru=0.0_real32; rv=0.0_real32; ww=0.0_real32
    dt=20.0_real32
    source_carrier=carrier
    raw_qsrc(:,:,:,1)=REAL(-3.059018638396083e-7_real64,real32)/carrier
    raw_nsrc(:,:,:,1)=REAL(-72988600.0_real64,real32)/carrier
    coupled_qsrc(:,:,:,1)=carrier*raw_qsrc(:,:,:,1)
    coupled_nsrc(:,:,:,1)=carrier*raw_nsrc(:,:,:,1)
    qt(:,:,:,qindex(1))=coupled_qsrc(:,:,:,1)
    nt(:,:,:,nindex(1))=coupled_nsrc(:,:,:,1)
  END IF
  IF (mode/=6.AND.mode/=10.AND.mode/=12) THEN
    coupled_qsrc(:,:,:,1)=qt(:,:,:,qindex(1))
    coupled_nsrc(:,:,:,1)=nt(:,:,:,nindex(1))
    raw_qsrc(:,:,:,1)=coupled_qsrc(:,:,:,1)
    raw_nsrc(:,:,:,1)=coupled_nsrc(:,:,:,1)
  END IF
  IF (mode==8) source_carrier(2,1,2)=2.0_real32
  IF (mode==9) coupled_qsrc(2,1,2,1)=coupled_qsrc(2,1,2,1)+1.0_real32
  IF (mode==10.OR.mode==12) THEN
    later_qsrc(:,:,:,1)=0.000009236385_real64
    later_nsrc(:,:,:,1)=9236.385_real64
  END IF
  IF (mode==11) later_qsrc(2,1,2,1)=ieee_value(0.0_real64,ieee_quiet_nan)
  IF (mode>=14) THEN
    rain_source_q=REAL(5.799455138344456e-8_real64,real32)
    rain_source_n=REAL(197.8706817626953_real64,real32)
    rain_delta_q=5.799454978655696e-8_real64-REAL(rain_source_q,real64)
    rain_delta_n=197.87067140247404_real64-REAL(rain_source_n,real64)
    rain_diffusion_delta(:,:,:,1)=rain_delta_q
    rain_diffusion_delta(:,:,:,2)=rain_delta_n
    q1(:,:,:,qindex(3))=0.0_real32; n1(:,:,:,nindex(3))=0.0_real32
    qt(:,:,:,qindex(3))=rain_source_q; nt(:,:,:,nindex(3))=rain_source_n
    muold=0.0_real32; mub=REAL(94642.36_real64,real32)
    munew=REAL(94640.8_real64,real32)-mub
    c1=1.0_real32; c2=0.0_real32
    al=1.0_real32; alb=0.0_real32
    ru=0.0_real32; rv=0.0_real32; ww=0.0_real32
    IF (mode==18) rain_diffusion_delta(2,1,2,1)=ieee_value(0.0_real64,ieee_quiet_nan)
    IF (mode==19) rain_diffusion_delta=0.0_real64
  END IF
  q2_state=q1; n2_state=n1
  IF (mode==14) THEN
    dt=20.0_real32/3.0_real32
    CALL invoke_rain_diffusion_update(dt,1,.TRUE.,.TRUE.)
    CALL assert_rain_diffusion_stage(dt,'RK1')
    dt=10.0_real32
    CALL invoke_rain_diffusion_update(dt,2,.TRUE.,.TRUE.)
    CALL assert_rain_diffusion_stage(dt,'RK2')
    dt=20.0_real32
    CALL invoke_rain_diffusion_update(dt,3,.TRUE.,.TRUE.)
    CALL assert_rain_diffusion_stage(dt,'RK3')
    WRITE(*,'(a,6(1x,es24.16))') 'PR87_RAIN_DIFFUSION_RESULT', &
      q2_state(2,1,2,qindex(3)),n2_state(2,1,2,nindex(3)), &
      q2_state(3,1,2,qindex(3)),n2_state(3,1,2,nindex(3)),rain_delta_q,rain_delta_n
    WRITE(*,'(a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS rain_diffusion_precision'
    STOP
  ELSE IF (mode==15) THEN
    CALL invoke_rain_diffusion_update(20.0_real32,3,.TRUE.,.TRUE.,step_override=2)
  ELSE IF (mode==16) THEN
    CALL invoke_rain_diffusion_update(20.0_real32,3,.TRUE.,.FALSE.)
  ELSE IF (mode==17) THEN
    CALL invoke_rain_diffusion_update(20.0_real32,3,.FALSE.,.TRUE.)
  ELSE IF (mode==18) THEN
    CALL invoke_rain_diffusion_update(20.0_real32,3,.TRUE.,.TRUE.)
  ELSE IF (mode==19) THEN
    CALL invoke_rain_diffusion_update(20.0_real32,3,.TRUE.,.TRUE.)
  ELSE IF (mode==12) THEN
    old_q=expected_q; old_n=expected_n
    dt=20.0_real32/3.0_real32
    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
         al,alb,dt,1,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
         later_qsrc,later_nsrc)
    CALL assert_interior_qn(q1,n1,old_q,old_n,'after RK1')
    dt=10.0_real32
    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
         al,alb,dt,2,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
         later_qsrc,later_nsrc)
    CALL assert_interior_qn(q1,n1,old_q,old_n,'after RK2')
    dt=20.0_real32
    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
         al,alb,dt,3,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
         later_qsrc,later_nsrc)
    CALL assert_interior_qn(q1,n1,old_q,old_n,'after RK3')
  ELSE IF (mode==7) THEN
    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
         al,alb,dt,3,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,2, &
         later_qsrc,later_nsrc)
  ELSE
    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
         al,alb,dt,3,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
         later_qsrc,later_nsrc)
  END IF

  IF (mode==1) THEN
    expected_q=REAL(1.375_real64*min_cloud*1.0e8_real64,real32)
    CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'baseline flux result')
    CALL assert_near(n2_state(3,1,2,nindex(1)),1.0e8_real32,'baseline number result')
  ELSE
    IF (mode==4.OR.mode==5.OR.mode==7.OR.mode==8.OR.mode==9.OR.mode==11) &
      ERROR STOP 'rejected source-first candidate unexpectedly completed'
    IF (mode==6) THEN
      expected_q=expected_q+dt*raw_qsrc(2,1,2,1)
      expected_n=expected_n+dt*raw_nsrc(2,1,2,1)
      IF (q2_state(2,1,2,qindex(1))/=expected_q.OR.q2_state(3,1,2,qindex(1))/=expected_q .OR. &
          n2_state(2,1,2,nindex(1))/=expected_n.OR.n2_state(3,1,2,nindex(1))/=expected_n) &
        ERROR STOP 'no-air source-first endpoint was not the R32 intensive stage'
      IF (REAL(expected_q,real64)/REAL(expected_n,real64) < &
          min_cloud-8.0_real64*ABS(REAL(SPACING(REAL(min_cloud,real32)),real64))) &
        ERROR STOP 'no-air R32 staged endpoint fell outside the existing tolerance'
      WRITE(*,'(a,1x,a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS','no_air'
      STOP
    END IF
    IF (mode==13) THEN
      expected_q64=0.75_real64*REAL(q1(2,1,2,qindex(3)),real64) + &
                   0.25_real64*REAL(q1(1,1,2,qindex(3)),real64)
      expected_n64=0.75_real64*REAL(n1(2,1,2,nindex(3)),real64) + &
                   0.25_real64*REAL(n1(1,1,2,nindex(3)),real64)
      expected_q=nearest(REAL(expected_q64,real32),1.0_real32)
      expected_n=REAL(expected_n64,real32)
      IF (q2_state(2,1,2,qindex(3))/=expected_q.OR. &
          n2_state(2,1,2,nindex(3))/=expected_n) &
        ERROR STOP 'R64 air-rate endpoint mismatch at first rain cell'
      expected_q64=0.75_real64*REAL(q1(3,1,2,qindex(3)),real64) + &
                   0.25_real64*REAL(q1(2,1,2,qindex(3)),real64)
      expected_n64=0.75_real64*REAL(n1(3,1,2,nindex(3)),real64) + &
                   0.25_real64*REAL(n1(2,1,2,nindex(3)),real64)
      expected_q=REAL(expected_q64,real32)
      expected_n=REAL(expected_n64,real32)
      IF (q2_state(3,1,2,qindex(3))/=expected_q.OR. &
          n2_state(3,1,2,nindex(3))/=expected_n) &
        ERROR STOP 'R64 air-rate endpoint mismatch at second rain cell'
      IF (REAL(q2_state(2,1,2,qindex(3)),real64)/REAL(n2_state(2,1,2,nindex(3)),real64)<min_rain_mass .OR. &
          REAL(q2_state(3,1,2,qindex(3)),real64)/REAL(n2_state(3,1,2,nindex(3)),real64)<min_rain_mass) &
        ERROR STOP 'committed R64 air-rate rain endpoint violates strict lower mass bound'
      WRITE(*,'(a,4(1x,es24.16))') 'PR87_RAIN_AIR_RESULT', &
          q2_state(2,1,2,qindex(3)),n2_state(2,1,2,nindex(3)), &
          q2_state(3,1,2,qindex(3)),n2_state(3,1,2,nindex(3))
      WRITE(*,'(a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS rain_air_precision'
      STOP
    END IF
    IF (mode==10.OR.mode==12) THEN
      expected_q=expected_q+dt*raw_qsrc(2,1,2,1)
      expected_n=expected_n+dt*raw_nsrc(2,1,2,1)
      expected_q=REAL((REAL(carrier,real64)*REAL(expected_q,real64)+ &
                       REAL(dt,real64)*later_qsrc(2,1,2,1))/REAL(carrier,real64),real32)
      expected_n=REAL((REAL(carrier,real64)*REAL(expected_n,real64)+ &
                       REAL(dt,real64)*later_nsrc(2,1,2,1))/REAL(carrier,real64),real32)
      IF (q2_state(2,1,2,qindex(1))/=expected_q.OR.q2_state(3,1,2,qindex(1))/=expected_q .OR. &
          n2_state(2,1,2,nindex(1))/=expected_n.OR.n2_state(3,1,2,nindex(1))/=expected_n) THEN
        WRITE(*,*) 'later actual/expected',q2_state(2,1,2,qindex(1)),expected_q, &
                   n2_state(2,1,2,nindex(1)),expected_n
        ERROR STOP 'later non-air source was not applied once after the R32 stage'
      END IF
      IF (mode==10) THEN
        WRITE(*,'(a,1x,a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS','later_no_air'
      ELSE
        WRITE(*,'(a,1x,a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS','later_cadence'
      END IF
      STOP
    END IF
    IF (mode==3) THEN
      expected_q=REAL(1.03125_real64*min_cloud*1.0e8_real64,real32)
      CALL assert_near(q2_state(2,1,2,qindex(1)),expected_q,'virtual-donor left endpoint')
      expected_q=REAL(1.34375_real64*min_cloud*1.0e8_real64,real32)
      CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'virtual-donor right endpoint')
      CALL assert_near(n2_state(2,1,2,nindex(1)),1.0e8_real32,'virtual-donor left number')
      CALL assert_near(n2_state(3,1,2,nindex(1)),1.0e8_real32,'virtual-donor right number')
      expected_q=REAL(2.375_real64*min_cloud*1.0e8_real64,real32)
      CALL assert_near(q2_state(2,1,2,qindex(1))+q2_state(3,1,2,qindex(1)),expected_q, &
                       'out-of-cone virtual donor endpoint conservation')
      WRITE(*,'(a,1x,a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS','virtual_donor'
      STOP
    END IF
    expected_q=REAL(1.09375_real64*min_cloud*1.0e8_real64,real32)
    CALL assert_near(q2_state(2,1,2,qindex(1)),expected_q,'source-first left cloud result')
    expected_q=REAL(1.03125_real64*min_cloud*1.0e8_real64,real32)
    CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'source-first right cloud result')
    CALL assert_near(n2_state(2,1,2,nindex(1)),1.0e8_real32,'source-first left number result')
    CALL assert_near(n2_state(3,1,2,nindex(1)),1.0e8_real32,'source-first right number result')
    expected_q=REAL(2.125_real64*min_cloud*1.0e8_real64,real32)
    CALL assert_near(q2_state(2,1,2,qindex(1))+q2_state(3,1,2,qindex(1)),expected_q, &
                     'two-cell source-plus-transport conservation')
  END IF
  WRITE(*,'(a,1x,a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS',TRIM(mode_text)
CONTAINS
  SUBROUTINE invoke_rain_diffusion_update(stage_dt,stage_rk,include_delta,include_step,step_override)
    REAL(real32),INTENT(IN) :: stage_dt
    INTEGER,INTENT(IN) :: stage_rk
    LOGICAL,INTENT(IN) :: include_delta,include_step
    INTEGER,INTENT(IN),OPTIONAL :: step_override
    INTEGER :: payload_step
    payload_step=1
    IF (PRESENT(step_override)) payload_step=step_override
    IF (include_delta.AND.include_step) THEN
      CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
           ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
           al,alb,stage_dt,stage_rk,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
           its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
           later_qsrc,later_nsrc,pr87_rain_diffusion_delta=rain_diffusion_delta, &
           pr87_rain_diffusion_step=payload_step)
    ELSE IF (include_delta) THEN
      CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
           ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
           al,alb,stage_dt,stage_rk,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
           its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
           later_qsrc,later_nsrc,pr87_rain_diffusion_delta=rain_diffusion_delta)
    ELSE IF (include_step) THEN
      CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
           ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
           al,alb,stage_dt,stage_rk,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
           its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
           later_qsrc,later_nsrc,pr87_rain_diffusion_step=payload_step)
    ELSE
      CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &
           ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &
           al,alb,stage_dt,stage_rk,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
           its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &
           later_qsrc,later_nsrc)
    END IF
  END SUBROUTINE invoke_rain_diffusion_update

  SUBROUTINE assert_rain_diffusion_stage(stage_dt,stage_name)
    REAL(real32),INTENT(IN) :: stage_dt
    CHARACTER(*),INTENT(IN) :: stage_name
    REAL(real64) :: old_carrier64,new_carrier64,q64,n64
    REAL(real64) :: minmass,maxmass,bounds(2)
    REAL(real32) :: stored_q,stored_n
    INTEGER :: adjustment
    LOGICAL :: valid
    old_carrier64=REAL(c1(1)*(muold(2,2)+mub(2,2))+c2(1),real64)
    new_carrier64=REAL(c1(1)*(munew(2,2)+mub(2,2))+c2(1),real64)
    minmass=REAL(12566.37109375_real32,real64)/REAL(35000.0_real32,real64)**3
    maxmass=REAL(12566.37109375_real32,real64)/REAL(961.0_real32,real64)**3
    bounds=[REAL(961.0_real32,real64)**3/REAL(12566.37109375_real32,real64), &
            REAL(35000.0_real32,real64)**3/REAL(12566.37109375_real32,real64)]
    q64=(old_carrier64*REAL(q1(2,1,2,qindex(3)),real64)+REAL(stage_dt,real64)* &
         (REAL(rain_source_q,real64)+rain_delta_q))/new_carrier64
    n64=(old_carrier64*REAL(n1(2,1,2,nindex(3)),real64)+REAL(stage_dt,real64)* &
         (REAL(rain_source_n,real64)+rain_delta_n))/new_carrier64
    IF (q64/n64<minmass.OR.n64>bounds(2)*q64) ERROR STOP 'corrected strict rain candidate is invalid'
    CALL joint_moment_store(q64,n64,1.0_real32,minmass,maxmass,.TRUE., &
         stored_q,stored_n,adjustment,valid,allow_normal_q_adjustment=.TRUE., &
         allow_joint_quantum_absence=.TRUE.,volume_number_bounds=bounds)
    IF (.NOT.valid) ERROR STOP 'corrected strict rain candidate could not be stored'
    IF (q2_state(2,1,2,qindex(3))/=stored_q.OR.n2_state(2,1,2,nindex(3))/=stored_n .OR. &
        q2_state(3,1,2,qindex(3))/=stored_q.OR.n2_state(3,1,2,nindex(3))/=stored_n) THEN
      WRITE(*,*) 'rain correction actual/expected ',TRIM(stage_name), &
        q2_state(2,1,2,qindex(3)),stored_q,n2_state(2,1,2,nindex(3)),stored_n
      ERROR STOP 'rain correction was missing, repeated, or applied to the wrong RK stage'
    END IF
    IF (q1(2,1,2,qindex(3))/=0.0_real32.OR.n1(2,1,2,nindex(3))/=0.0_real32) &
      ERROR STOP 'rain correction changed old stage state'
  END SUBROUTINE assert_rain_diffusion_stage

  SUBROUTINE assert_interior_qn(mass,number,expected_mass,expected_number,stage)
    REAL(real32),INTENT(IN) :: mass(ims:ime,kms:kme,jms:jme,nmoist)
    REAL(real32),INTENT(IN) :: number(ims:ime,kms:kme,jms:jme,nscalar)
    REAL(real32),INTENT(IN) :: expected_mass,expected_number
    CHARACTER(*),INTENT(IN) :: stage
    IF (mass(2,1,2,qindex(1))/=expected_mass.OR.mass(3,1,2,qindex(1))/=expected_mass .OR. &
        number(2,1,2,nindex(1))/=expected_number.OR.number(3,1,2,nindex(1))/=expected_number) THEN
      WRITE(*,*) 'RK cadence changed q1/n1 interior ',TRIM(stage)
      ERROR STOP 'RK cadence q1/n1 invariant failed'
    END IF
  END SUBROUTINE assert_interior_qn
  SUBROUTINE assert_near(actual,expected,label)
    REAL(real32),INTENT(IN) :: actual,expected
    CHARACTER(*),INTENT(IN) :: label
    IF (ABS(actual-expected)>8.0_real32*SPACING(expected)) THEN
      WRITE(*,*) 'assertion failed: ',label,actual,expected,SPACING(expected)
      ERROR STOP 'source-first fixture value mismatch'
    END IF
  END SUBROUTINE assert_near
END PROGRAM pr87_source_first_fallback_regression
"""


def run(command: list[str], cwd: Path, log_path: Path) -> subprocess.CompletedProcess[str]:
    shell_command = " ".join(shlex.quote(part) for part in command)
    result = subprocess.run(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {shell_command}"],
        cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(result.stdout, encoding="utf-8")
    return result


def fallback_flags(path: Path) -> list[bool]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if "SOURCE_FIRST_PAIR_FALLBACK" in line]
    if len(lines) != 1:
        raise RuntimeError(f"expected one fallback ledger row in {path}, got {len(lines)}")
    values = re.findall(r"(?<![\w.])(?:\.TRUE\.|\.FALSE\.|T|F)(?![\w.])",
                        lines[0], re.IGNORECASE)
    if len(values) != 4:
        raise RuntimeError(f"could not parse four fallback flags from: {lines[0]}")
    return [value.lower() in ("t", ".true.") for value in values]


def assert_baseline_ledger(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"BASELINE_JOINT_FEASIBLE\s+1\s+3\s+(?:\.TRUE\.|T)(?![A-Z])", text, re.IGNORECASE):
        raise RuntimeError("baseline control did not accept theta=1")
    if fallback_flags(path) != [False, False, False, False]:
        raise RuntimeError("baseline control unexpectedly selected source-first fallback")


def assert_fallback_ledger(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"BASELINE_JOINT_FEASIBLE\s+1\s+3\s+(?:\.FALSE\.|F)(?![A-Z])", text, re.IGNORECASE):
        raise RuntimeError("dyadic control did not reject the original theta=1 candidate")
    if fallback_flags(path) != [True, False, False, False]:
        raise RuntimeError("fallback was not limited to the cloud pair")


def assert_rain_air_baseline_ledger(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"BASELINE_JOINT_FEASIBLE\s+1\s+3\s+(?:\.TRUE\.|T)(?![A-Z])", text, re.IGNORECASE):
        raise RuntimeError("R64 rain-air control did not accept the original theta=1 candidate")
    if fallback_flags(path) != [False, False, False, False]:
        raise RuntimeError("R64 rain-air control unexpectedly selected source-first fallback")


def assert_rain_storage_ledger(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()

    def values(tag: str, count: int, cast):
        starts = [index for index, line in enumerate(lines) if line.strip().startswith(tag)]
        if len(starts) != 1:
            raise RuntimeError(f"expected one {tag} row, got {starts}")
        result = lines[starts[0]].split()[1:]
        for continuation in lines[starts[0] + 1:]:
            if len(result) >= count or continuation.strip().startswith(("JOINT_STORAGE", "STORAGE_DELTA_", "STORED_PAIR")):
                break
            result.extend(continuation.split())
        if len(result) != count:
            raise RuntimeError(f"malformed {tag} row: {result}")
        return [cast(value) for value in result]

    header = values("JOINT_STORAGE", 7, int)
    if header[:3] != [1, 3, 2] or header[5] != 1:
        raise RuntimeError(f"expected exactly one directed rain Q adjustment: {header}")
    delta_q = values("STORAGE_DELTA_PRESSURE_Q", 4, float)
    delta_n = values("STORAGE_DELTA_PRESSURE_MOMENT", 4, float)
    if not (delta_q[2] > 0.0 and delta_n[2] > 0.0):
        raise RuntimeError(f"rain storage ledger did not retain both signed nearest-storage deltas: {delta_q}, {delta_n}")
    return {"joint_storage_header": header, "signed_delta_q": delta_q,
            "signed_delta_n": delta_n}


def assert_rain_cast_mutant_rejected(result: subprocess.CompletedProcess[str], cwd: Path) -> dict:
    expected = [real32(0.002892484422773123), real32(0.00017703388584777713),
                real32(9868821.0), real32(604019.0625)]
    if result.returncode == 0 or "PR87 full joint moment candidate infeasible" not in result.stdout:
        raise RuntimeError(f"independent R32 air-rate cast mutant was not rejected:\n{result.stdout}")
    matches = [line for line in result.stdout.splitlines()
               if "PR87_FATAL_ATOMIC_RAIN_STATE" in line]
    if len(matches) != 1:
        raise RuntimeError("rain-cast mutant fatal stub did not report atomic rain state")
    actual = [float(value) for value in matches[0].split()[1:]]
    if len(actual) != 4 or any(a != b for a, b in zip(actual, expected, strict=True)):
        raise RuntimeError(f"rain-cast mutant changed rain state before commit: {actual}")
    if (cwd / "pr87_joint_storage.raw").exists():
        raise RuntimeError("rejected rain-cast mutant wrote a committed-storage ledger")
    budget = cwd / "pr85_joint_transport_budget.raw"
    if not budget.is_file() or fallback_flags(budget) != [False, False, False, False]:
        raise RuntimeError("rain-cast mutant rejection did not preserve baseline/no-fallback scope")
    return {"status": "PASS_R32_CAST_MUTANT_REJECTED_ATOMICALLY",
            "rain_qn_at_fatal": actual, "run_log_sha256": sha256(cwd / "run.log"),
            "storage_ledger_absent": True, "budget_sha256": sha256(budget)}


def assert_rain_diffusion_ledger(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headers = [line.split()[1:] for line in lines
               if line.strip().startswith("RAIN_DIFFUSION_RK_CORRECTION")]
    sums = [line.split()[1:] for line in lines
            if line.strip().startswith("DT_SUM_PRESSURE_Q_N")]
    l1s = [line.split()[1:] for line in lines
           if line.strip().startswith("DT_L1_PRESSURE_Q_N")]
    maxima = [line.split()[1:] for line in lines
              if line.strip().startswith("DT_MAXABS_PRESSURE_Q_N")]
    if len(headers) != 3 or len(sums) != 3 or len(l1s) != 3 or len(maxima) != 3:
        raise RuntimeError("expected one signed rain diffusion ledger block per RK stage")
    expected_rks = [1, 2, 3]
    dts = [real32(20.0 / 3.0), real32(10.0), real32(20.0)]
    delta_q = 5.799454978655696e-8 - real32(5.799455138344456e-8)
    delta_n = 197.87067140247404 - real32(197.8706817626953)
    for index, (header, sum_row, l1_row, max_row, dt) in enumerate(
            zip(headers, sums, l1s, maxima, dts, strict=True)):
        if [int(header[0]), int(header[1]), int(header[2])] != [1, expected_rks[index], 2]:
            raise RuntimeError(f"wrong diffusion correction stage/cell count: {header}")
        expected_sum = [2.0 * dt * delta_q, 2.0 * dt * delta_n]
        expected_l1 = [2.0 * dt * abs(delta_q), 2.0 * dt * abs(delta_n)]
        expected_max = [dt * abs(delta_q), dt * abs(delta_n)]
        for recorded, expected, label in ((sum_row, expected_sum, "signed sum"),
                                          (l1_row, expected_l1, "L1"),
                                          (max_row, expected_max, "max")):
            if len(recorded) != 2 or any(
                    not math.isclose(float(actual), target, rel_tol=1.0e-12, abs_tol=1.0e-27)
                    for actual, target in zip(recorded, expected, strict=True)):
                raise RuntimeError(f"rain diffusion {label} ledger mismatch at RK{index+1}: {recorded}")
    return {"status": "PASS_SIGNED_PER_RK_PRESSURE_VECTOR",
            "headers": headers, "signed_sum_rows": sums, "l1_rows": l1s,
            "max_abs_rows": maxima, "delta_q_per_second": delta_q,
            "delta_n_per_second": delta_n}


def assert_rain_diffusion_transport(path: Path) -> list[list[bool]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    baseline = [line for line in lines if "BASELINE_JOINT_FEASIBLE" in line]
    fallback = [line for line in lines if "SOURCE_FIRST_PAIR_FALLBACK" in line]
    joint = [line for line in lines if "JOINT_RK" in line]
    if len(baseline) != 3 or len(fallback) != 3 or len(joint) != 3:
        raise RuntimeError("rain correction cadence did not emit exactly three candidate records")
    parsed_fallback: list[list[bool]] = []
    for rk, (base_line, fallback_line, joint_line) in enumerate(
            zip(baseline, fallback, joint, strict=True), start=1):
        if not re.search(rf"BASELINE_JOINT_FEASIBLE\s+1\s+{rk}\s+(?:\.TRUE\.|T)(?![A-Z])",
                         base_line, re.IGNORECASE):
            raise RuntimeError(f"R{rk} corrected candidate was not baseline-feasible: {base_line}")
        flags = re.findall(r"(?<![\w.])(?:\.TRUE\.|\.FALSE\.|T|F)(?![A-Z])",
                           fallback_line, re.IGNORECASE)
        if len(flags) != 4 or any(value.lower() in ("t", ".true.") for value in flags):
            raise RuntimeError(f"R{rk} unexpectedly selected another fallback: {fallback_line}")
        fields = joint_line.split()
        if len(fields) < 6:
            row_index = lines.index(joint_line)
            fields.extend(lines[row_index + 1].split())
        if len(fields) < 6 or int(fields[1]) != rk or int(fields[2]) != 2 or \
                fields[5].lower() not in ("t", ".true."):
            raise RuntimeError(f"R{rk} corrected candidate did not pass its common endpoint gate: {joint_line}")
        parsed_fallback.append([False] * 4)
    return parsed_fallback


def assert_rain_diffusion_rejected(result: subprocess.CompletedProcess[str], cwd: Path,
                                   mode: str, reason: str) -> dict[str, object]:
    if result.returncode == 0 or reason not in result.stdout:
        raise RuntimeError(f"{mode} did not reject with {reason}:\n{result.stdout}")
    matches = [line for line in result.stdout.splitlines()
               if "PR87_FATAL_ATOMIC_RAIN_STATE" in line]
    if len(matches) != 1:
        raise RuntimeError(f"{mode} did not report one fatal rain state")
    actual = [float(value) for value in matches[0].split()[1:]]
    if actual != [0.0, 0.0, 0.0, 0.0]:
        raise RuntimeError(f"{mode} changed a rain Q/N cell before rejection: {actual}")
    if (cwd / "pr87_joint_storage.raw").exists():
        raise RuntimeError(f"{mode} wrote committed storage before rejection")
    if mode == "zero_diffusion_delta":
        failure = cwd / "pr85_joint_source_failure.raw"
        budget = cwd / "pr85_joint_transport_budget.raw"
        precision = cwd / "pr87_rain_diffusion_precision.raw"
        if not failure.is_file() or "FULL_FAILURE_COUNT" not in failure.read_text(encoding="utf-8"):
            raise RuntimeError("zero-delta mutant did not fail the strict full candidate gate")
        if not budget.is_file() or not precision.is_file():
            raise RuntimeError("zero-delta mutant omitted attempted-candidate diagnostics")
        return {"status": "PASS_ZERO_DELTA_STRICT_ENDPOINT_REJECTED_ATOMICALLY",
                "rain_qn_at_fatal": actual, "source_failure_sha256": sha256(failure),
                "budget_sha256": sha256(budget), "precision_ledger_sha256": sha256(precision),
                "storage_ledger_absent": True, "run_log_sha256": sha256(cwd / "run.log")}
    if any((cwd / name).exists() for name in ("pr85_joint_transport_budget.raw",
                                               "pr87_joint_storage.raw",
                                               "pr87_rain_diffusion_precision.raw")):
        raise RuntimeError(f"{mode} wrote diagnostics after an entry guard rejected the payload")
    return {"status": "PASS_INVALID_DIFFUSION_PAYLOAD_REJECTED_ATOMICALLY",
            "reason": reason, "rain_qn_at_fatal": actual,
            "storage_ledger_absent": True, "run_log_sha256": sha256(cwd / "run.log")}


def assert_cadence_ledger(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if "SOURCE_FIRST_PAIR_FALLBACK" in line]
    if len(rows) != 3:
        raise RuntimeError(f"expected three fallback rows for RK cadence, got {len(rows)}")
    parsed = []
    for line in rows:
        values = re.findall(r"(?<![\w.])(?:\.TRUE\.|\.FALSE\.|T|F)(?![A-Z])", line, re.IGNORECASE)
        if len(values) != 4:
            raise RuntimeError(f"could not parse RK cadence fallback row: {line}")
        parsed.append([value.lower() in ("t", ".true.") for value in values])
    if parsed != [[False] * 4, [False] * 4, [True, False, False, False]]:
        raise RuntimeError(f"unexpected RK cadence fallback sequence: {parsed}")


def real32(value: float) -> float:
    return struct.unpack("=f", struct.pack("=f", value))[0]


def assert_no_air_source_ledger(path: Path, later_source: bool = False) -> dict[str, list[float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip().startswith("SOURCE_TOTAL")]
    if len(starts) != 1:
        raise RuntimeError(f"expected one source total row, got {starts}")
    row = lines[starts[0]].split()
    values = row[6:]
    for continuation in lines[starts[0] + 1:]:
        if len(values) >= 10 or continuation.strip().startswith("SOURCE_"):
            break
        values.extend(continuation.split())
    if len(row) < 6 or len(values) != 10:
        raise RuntimeError(f"expected one complete source total row, got {row + values}")
    if [int(value) for value in row[1:6]] != [1, 3, 1, 2, 2]:
        raise RuntimeError(f"unexpected no-air source ledger scope: {row[:6]}")
    values = [float(value) for value in values]
    proposal_q, proposal_n, represented_q, represented_n, delta_q, delta_n, \
        l1_q, l1_n, max_q, max_n = values

    carrier = real32(92363.85)
    q0 = real32(3.7537916e-8)
    n0 = real32(8961516.0)
    dt = real32(20.0)
    raw_q = real32(real32(-3.059018638396083e-7) / carrier)
    raw_n = real32(real32(-72988600.0) / carrier)
    coupled_q = real32(carrier * raw_q)
    coupled_n = real32(carrier * raw_n)
    staged_q = real32(q0 + real32(dt * raw_q))
    staged_n = real32(n0 + real32(dt * raw_n))
    expected = {
        "proposal": [2.0 * dt * coupled_q, 2.0 * dt * coupled_n],
        "represented": [2.0 * carrier * (staged_q - q0),
                        2.0 * carrier * (staged_n - n0)],
    }
    if later_source:
        expected["represented"][0] += 2.0 * dt * 0.000009236385
        expected["represented"][1] += 2.0 * dt * 9236.385
    expected["delta"] = [b - a for a, b in zip(expected["proposal"], expected["represented"], strict=True)]
    expected["l1"] = [abs(value) for value in expected["delta"]]
    expected["max_abs"] = [abs(value) / 2.0 for value in expected["delta"]]
    observed = {
        "proposal": [proposal_q, proposal_n],
        "represented": [represented_q, represented_n],
        "delta": [delta_q, delta_n],
        "l1": [l1_q, l1_n],
        "max_abs": [max_q, max_n],
    }
    for key, expected_values in expected.items():
        for observed_value, expected_value in zip(observed[key], expected_values, strict=True):
            if not math.isclose(observed_value, expected_value, rel_tol=2.0e-8, abs_tol=1.0e-12):
                raise RuntimeError(f"no-air {key} mismatch: {observed[key]} != {expected_values}")
    if later_source:
        later_starts = [index for index, line in enumerate(lines)
                        if line.strip().startswith("SOURCE_LATER_TOTAL")]
        if len(later_starts) != 1:
            raise RuntimeError(f"expected one later-source row, got {later_starts}")
        later_fields = lines[later_starts[0]].split()[1:]
        for continuation in lines[later_starts[0] + 1:]:
            if len(later_fields) >= 7 or continuation.strip().startswith("SOURCE_"):
                break
            later_fields.extend(continuation.split())
        if len(later_fields) != 7:
            raise RuntimeError(f"expected one complete later-source row, got {later_fields}")
        later = [float(value) for value in later_fields]
        expected_later = [1.0, 3.0, 1.0, 2.0 * dt * 0.000009236385,
                          2.0 * dt * 9236.385]
        for actual, goal in zip(later[:5], expected_later, strict=True):
            if not math.isclose(actual, goal, rel_tol=2.0e-8, abs_tol=1.0e-12):
                raise RuntimeError(f"later-source total mismatch: {later} != {expected_later}")
        if any(not math.isfinite(value) or value < 0.0 for value in later[5:]):
            raise RuntimeError(f"later-source identity residual is invalid: {later}")
        observed["later_source_amount"] = later[3:5]
        observed["later_source_identity_residual_max"] = later[5:7]
    return observed


def assert_rejected_without_commit(result: subprocess.CompletedProcess[str], cwd: Path,
                                   expected_message: str, cloud_mass: float | tuple[float, float],
                                   allow_attempt_budget: bool = False) -> dict:
    if result.returncode == 0 or expected_message not in result.stdout:
        raise RuntimeError(f"expected candidate rejection did not occur:\n{result.stdout}")
    matches = [line for line in result.stdout.splitlines()
               if "PR87_FATAL_ATOMIC_STATE" in line]
    if len(matches) != 1:
        raise RuntimeError("fatal stub did not report the pre-commit cloud state")
    values = [float(value) for value in matches[0].split()[1:]]
    cloud_masses = cloud_mass if isinstance(cloud_mass, tuple) else (cloud_mass, cloud_mass)
    expected = [cloud_masses[0], cloud_masses[1], 1.0e8, 1.0e8]
    if len(values) != 4 or any(abs(actual - goal) > 8.0 * abs(goal) * 1.2e-7
                               for actual, goal in zip(values, expected, strict=True)):
        raise RuntimeError(f"fatal path changed q2/n2 before commit: {values}")
    storage = cwd / "pr87_joint_storage.raw"
    transport = cwd / "pr85_joint_transport_budget.raw"
    if storage.exists():
        raise RuntimeError("rejected candidate wrote a committed-storage ledger")
    if transport.exists() and not allow_attempt_budget:
        raise RuntimeError("rejected donor wrote an unexpected transport budget")
    if transport.exists():
        if fallback_flags(transport) != [True, False, False, False]:
            raise RuntimeError("invalid endpoint did not use only the cloud fallback pair")
        budget_text = transport.read_text(encoding="utf-8")
        if not re.search(r"JOINT_RK\s+3\s+2\s+[\d.Ee+-]+\s+[\d.Ee+-]+\s+F(?:\s|$)",
                         budget_text, re.IGNORECASE):
            raise RuntimeError("invalid endpoint was not rejected after the retry")
    return {"status": "PASS_REJECTED_BEFORE_COMMIT", "q2_n2_at_fatal": values,
            "run_log": str(cwd / "run.log"), "run_log_sha256": sha256(cwd / "run.log"),
            "storage_ledger_absent": True,
            "transport_budget_present_for_failed_retry": transport.exists(),
            "transport_budget_sha256": sha256(transport) if transport.exists() else None}


def execute(proposal: Path, receipt_path: Path) -> dict:
    if not proposal.is_file():
        raise ValueError(f"native proposal does not exist: {proposal}")
    proposal_text = proposal.read_text(encoding="utf-8")
    procedure = extract_subroutine(proposal_text, "rk_update_joint_moments")
    rate_assignment = re.compile(
        r"qa64\(cell,p\)=rate\(1\);\s*na64\(cell,p\)=rate\(2\)", re.IGNORECASE)
    cast_mutant_procedure, mutant_replacements = rate_assignment.subn(
        "qa64(cell,p)=REAL(qa(cell,p),real64); na64(cell,p)=REAL(na(cell,p),real64)",
        procedure, count=1)
    if mutant_replacements != 1:
        raise ValueError("proposal must retain R64 air tendencies directly in qa64/na64")
    observer = DENSITY_HELPER.read_text(encoding="utf-8")
    density_helper = extract_subroutine(observer, "pr85_dry_density_from_al_alb")
    generated_source = source_text(procedure, density_helper)
    scratch = Path(tempfile.mkdtemp(prefix="pr87_source_first_fixture_", dir="/var/tmp"))
    source = scratch / "source_first_fixture.F90"
    source.write_text(generated_source, encoding="utf-8")
    results: dict[str, object] = {}
    for level, profile_flag in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                                ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        compiler, flags = profile_flags(profile_flag)
        build = scratch / level
        build.mkdir()
        exe = build / "source_first_fixture.exe"
        compile_result = run([compiler, *flags, str(KERNEL), str(source), "-o", str(exe)],
                             build, build / "compile.log")
        if compile_result.returncode:
            raise RuntimeError(f"{level} compile failed:\n{compile_result.stdout}")
        modes: dict[str, object] = {}
        mode_names = ["baseline", "source_first", "virtual_donor", "no_air", "later_no_air", "later_cadence",
                      "negative_donor", "invalid_endpoint", "stale_step",
                      "stale_carrier", "stale_source_ref", "nonfinite_later", "rain_air_precision"]
        has_diffusion_payload = "pr87_rain_diffusion_delta" in procedure
        if has_diffusion_payload:
            mode_names.extend(["rain_diffusion_precision", "stale_diffusion_step",
                               "partial_diffusion_delta", "partial_diffusion_step",
                               "nonfinite_diffusion_delta", "zero_diffusion_delta"])
        for mode in mode_names:
            cwd = build / mode
            cwd.mkdir()
            result = run([str(exe), mode], cwd, cwd / "run.log")
            rejected_modes = ("negative_donor", "invalid_endpoint", "stale_step",
                              "stale_carrier", "stale_source_ref", "nonfinite_later")
            diffusion_rejections = {
                "stale_diffusion_step": "PR87 rain diffusion timestep mismatch",
                "partial_diffusion_delta": "PR87 rain diffusion delta/step must be supplied together",
                "partial_diffusion_step": "PR87 rain diffusion delta/step must be supplied together",
                "nonfinite_diffusion_delta": "PR87 nonfinite rain diffusion correction",
                "zero_diffusion_delta": "PR87 full joint moment candidate infeasible",
            }
            if mode in diffusion_rejections:
                modes[mode] = assert_rain_diffusion_rejected(
                    result, cwd, mode, diffusion_rejections[mode])
                continue
            if mode in rejected_modes:
                reasons = {
                    "negative_donor": "PR87 unsafe continuous intensive source donor",
                    "invalid_endpoint": "PR87 full joint moment candidate infeasible",
                    "stale_step": "PR87 intensive source payload is not current or changed after capture",
                    "stale_carrier": "PR87 physical source and old state use different dry carriers",
                    "stale_source_ref": "PR87 coupled source changed since its intensive capture",
                    "nonfinite_later": "PR87 nonfinite later non-air source payload",
                }
                expected_cloud = (1.0 * 4.188790204786391e-15 * 1.0e8,
                                  1.5 * 4.188790204786391e-15 * 1.0e8)
                state = assert_rejected_without_commit(
                    result, cwd, reasons[mode],
                    1.5 * 4.188790204786391e-15 * 1.0e8 if mode in ("negative_donor", "invalid_endpoint")
                    else expected_cloud,
                    allow_attempt_budget=(mode == "invalid_endpoint"))
                modes[mode] = state
                continue
            if mode == "rain_air_precision":
                if result.returncode or "PR87_SOURCE_FIRST_FIXTURE_PASS rain_air_precision" not in result.stdout:
                    raise RuntimeError(f"{level} R64 rain-air control failed:\n{result.stdout}")
                ledger = cwd / "pr85_joint_transport_budget.raw"
                assert_rain_air_baseline_ledger(ledger)
                storage_ledger = assert_rain_storage_ledger(cwd / "pr87_joint_storage.raw")
                result_line = next((line for line in result.stdout.splitlines()
                                    if "PR87_RAIN_AIR_RESULT" in line), None)
                if result_line is None:
                    raise RuntimeError("R64 rain-air control did not report its committed Q/N endpoints")
                endpoints = [float(value) for value in result_line.split()[1:]]
                if len(endpoints) != 4:
                    raise RuntimeError(f"malformed R64 rain-air endpoint row: {result_line}")
                modes[mode] = {
                    "status": "PASS_R64_AIR_RATES_STRICT_RAIN_ENDPOINT",
                    "run_log_sha256": sha256(cwd / "run.log"),
                    "budget_path": str(ledger), "budget_sha256": sha256(ledger),
                    "fallback_flags": fallback_flags(ledger),
                    "committed_endpoints_q2_n2_q3_n3": endpoints,
                    "signed_storage_evidence": storage_ledger,
                    "run_log": str(cwd / "run.log"),
                }
                continue
            if mode == "rain_diffusion_precision":
                if result.returncode or "PR87_SOURCE_FIRST_FIXTURE_PASS rain_diffusion_precision" not in result.stdout:
                    raise RuntimeError(f"{level} corrected rain diffusion fixture failed:\n{result.stdout}")
                budget = cwd / "pr85_joint_transport_budget.raw"
                diffusion = cwd / "pr87_rain_diffusion_precision.raw"
                parsed_fallback = assert_rain_diffusion_transport(budget)
                diffusion_ledger = assert_rain_diffusion_ledger(diffusion)
                result_line = next((line for line in result.stdout.splitlines()
                                    if "PR87_RAIN_DIFFUSION_RESULT" in line), None)
                if result_line is None or len(result_line.split()) != 7:
                    raise RuntimeError("corrected rain fixture did not report endpoint/delta evidence")
                endpoint = [float(value) for value in result_line.split()[1:]]
                modes[mode] = {
                    "status": "PASS_CORRECTED_STRICT_RAIN_ENDPOINT_AT_RK1_RK2_RK3",
                    "run_log_sha256": sha256(cwd / "run.log"),
                    "budget_sha256": sha256(budget),
                    "diffusion_ledger_sha256": sha256(diffusion),
                    "fallback_flags_by_rk": parsed_fallback,
                    "committed_q2_n2_q3_n3_delta_q_delta_n": endpoint,
                    "signed_diffusion_evidence": diffusion_ledger,
                    "run_log": str(cwd / "run.log"),
                }
                continue
            if result.returncode or f"PR87_SOURCE_FIRST_FIXTURE_PASS {mode}" not in result.stdout:
                raise RuntimeError(f"{level} {mode} run failed:\n{result.stdout}")
            ledger = cwd / "pr85_joint_transport_budget.raw"
            if mode == "baseline":
                assert_baseline_ledger(ledger)
            elif mode == "later_cadence":
                assert_cadence_ledger(ledger)
            else:
                assert_fallback_ledger(ledger)
            source_representation = None
            if mode in ("no_air", "later_no_air", "later_cadence"):
                source_representation = assert_no_air_source_ledger(
                    cwd / "pr87_source_representation.raw",
                    later_source=(mode in ("later_no_air", "later_cadence")))
            if mode == "later_cadence":
                transport_rows = [line for line in ledger.read_text(encoding="utf-8").splitlines()
                                  if "SOURCE_FIRST_PAIR_FALLBACK" in line]
                recorded_fallback = [
                    [value.lower() in ("t", ".true.") for value in re.findall(
                        r"(?<![\w.])(?:\.TRUE\.|\.FALSE\.|T|F)(?![A-Z])", line, re.IGNORECASE)]
                    for line in transport_rows
                ]
            else:
                recorded_fallback = fallback_flags(ledger)
            modes[mode] = {
                "status": "PASS",
                "run_log_sha256": sha256(cwd / "run.log"),
                "budget_path": str(ledger),
                "budget_sha256": sha256(ledger),
                "fallback_flags": recorded_fallback,
                "source_representation_pressure_amounts": source_representation,
                "run_log": str(cwd / "run.log"),
            }

        mutant_source = scratch / f"source_first_fixture_r32_cast_mutant_{level}.F90"
        mutant_source.write_text(source_text(cast_mutant_procedure, density_helper), encoding="utf-8")
        mutant_build = scratch / f"R32_CAST_MUTANT_{level}"
        mutant_build.mkdir()
        mutant_exe = mutant_build / "source_first_fixture.exe"
        mutant_compile = run([compiler, *flags, str(KERNEL), str(mutant_source), "-o", str(mutant_exe)],
                             mutant_build, mutant_build / "compile.log")
        if mutant_compile.returncode:
            raise RuntimeError(f"{level} independent R32-cast mutant compile failed:\n{mutant_compile.stdout}")
        mutant_cwd = mutant_build / "rain_air_precision"
        mutant_cwd.mkdir()
        mutant_result = run([str(mutant_exe), "rain_air_precision"], mutant_cwd, mutant_cwd / "run.log")
        mutant_evidence = assert_rain_cast_mutant_rejected(mutant_result, mutant_cwd)
        mutant_evidence.update({
            "compile_log": str(mutant_build / "compile.log"),
            "compile_log_sha256": sha256(mutant_build / "compile.log"),
            "executable": str(mutant_exe), "executable_sha256": sha256(mutant_exe),
            "procedure_mutation": "qa64/na64 use the independent REAL32 qa/na casts instead of the R64 air_tendency result",
        })
        modes["rain_air_precision"]["r32_cast_mutant"] = mutant_evidence
        results[level] = {
            "compiler": compiler,
            "flags": flags,
            "compiler_sha256": sha256(Path(compiler)),
            "compile_log": str(build / "compile.log"),
            "compile_log_sha256": sha256(build / "compile.log"),
            "executable": str(exe),
            "executable_sha256": sha256(exe),
            "modes": modes,
        }
    evidence = {
        "schema": "pr87_r64_air_transport_precision_ifx_v1",
        "status": "PASS_O0_O2",
        "proposal_path": str(proposal),
        "proposal_sha256": sha256(proposal),
        "runner_path": str(Path(__file__).resolve()),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "extracted_procedure": "rk_update_joint_moments",
        "extracted_procedure_sha256": hashlib.sha256(procedure.encode()).hexdigest(),
        "generated_fixture_sha256": sha256(source),
        "kernel_path": str(KERNEL),
        "kernel_sha256": sha256(KERNEL),
        "density_helper_source": str(DENSITY_HELPER),
        "density_helper_source_sha256": sha256(DENSITY_HELPER),
        "density_helper_procedure_sha256": hashlib.sha256(density_helper.encode()).hexdigest(),
        "pinned_profile": str(PROFILE),
        "pinned_profile_sha256": sha256(PROFILE),
        "scratch": str(scratch),
        "fixture_contract": {
            "dimensions": {"i": [1,5], "j": [1,4], "k": [1,2], "active_i": [2,3], "active_j": [2,2], "active_k": [1,1]},
            "registry": {"nmoist": 6, "nscalar": 5, "qindex": [2,3,4,5], "nindex": [1,2,3,4], "qsindex": 6, "nnindex": 5},
            "dry_carrier": "old/new=1 via c1=1,c2=0,muold=munew=0,mub=1",
            "density": "DEN=1 from AL=1, ALB=0 using source-matched helper",
            "horizontal_flux": "ru=+0.25 on all x faces; rv=ww=0; dt=1",
            "explicit_source_payload": {
                "raw_source_arrays": "raw intensive Q/N source rates, REAL32, 4-D pair dimension 2",
                "coupled_source_arrays": "captured extensive Q/N tendencies, REAL32, 4-D pair dimension 2; compared to qt/nt",
                "carrier_and_step": "captured carrier equals old carrier at each active cell; source step must match itimestep",
                "later_source_arrays": "weighted REAL64 Q/N non-air source rates captured after RK1; current RK call applies them once",
            },
            "cadence_fixture": {
                "dt_by_rk": [20.0 / 3.0, 10.0, 20.0],
                "later_source_payload": "same captured REAL64 D passed to all calls; source-first retry occurs at RK3",
                "q1_n1_interior": "bit-equal to initial state after RK1, RK2, and RK3",
                "final_state": "bit-equal to one full 20-second source application, not cumulative 110/3-second application",
            },
            "rain_air_precision": {
                "kind": "manufactured two-cell R64 shared-face transport; not a native-cell replay",
                "strict_rain_mean_mass_lower_bound": 12566.37109375 / 35000.0**3,
                "old_rain_q": [0.0002928402682300657, 0.002892484422773123,
                               0.00017703388584777713, 0.01728409342467785],
                "old_rain_n": [999136.9375, 9868821.0, 604019.0625, 58971320.0],
                "transport": "R64 air_tendency from one old-time upwind donor map; ru=0.25; dt=1; equal old/new carrier",
                "expected": "R64 proposal passes strict continuous/stored rain contract and commits; independent R32 rate-cast mutant rejects before commit",
                "storage_evidence": "positive directed Q and nearest-storage N deltas for rain; rejected mutant leaves both rain cells unchanged and emits no committed-storage ledger",
            },
            "cloud_bounds": {"minimum_particle_mass": 4.188790204786391e-15, "maximum_particle_mass": 3.0300855069345996e-10},
            "dyadic_cases_in_units_of_minimum_mass_times_1e8": {
                "baseline": {
                    "old_cloud_mass": [1.0, 1.5],
                    "old_cloud_number": [1.0, 1.0],
                    "source_cloud_mass": [0.0, 0.0],
                    "theta1_result_cloud_mass": [1.0, 1.375],
                    "source_first_fallback_selected": False,
                },
                "source_first": {
                    "old_cloud_mass": [1.0, 1.5],
                    "old_cloud_number": [1.0, 1.0],
                    "source_cloud_mass": [0.125, -0.5],
                    "source_prepared_mass": [1.125, 1.0],
                    "original_theta1_cloud_mass": [1.125, 0.875],
                    "completed_fallback_cloud_mass": [1.09375, 1.03125],
                    "completed_cloud_number": [1.0, 1.0],
                    "completed_mass_sum": 2.125,
                    "source_first_fallback_selected": True,
                    "selected_pair": "cloud (Q index 2, N index 1)",
                },
                "virtual_donor": {
                    "old_cloud_mass": [1.5, 1.5],
                    "old_cloud_number": [1.0, 1.0],
                    "source_cloud_mass": [-0.625, 0.0],
                    "source_prepared_mass": [0.875, 1.5],
                    "original_theta1_cloud_mass": [0.875, 1.5],
                    "completed_fallback_cloud_mass": [1.03125, 1.34375],
                    "completed_cloud_number": [1.0, 1.0],
                    "completed_mass_sum": 2.375,
                    "source_first_fallback_selected": True,
                    "intermediate_outside_psd_cone": True,
                    "final_endpoint_passes_psd_cone": True,
                },
                "negative_donor": {
                    "old_cloud_mass": [1.5, 1.5],
                    "source_cloud_mass": [-1.625, 0.0],
                    "source_prepared_mass": [-0.125, 1.5],
                    "expected_result": "reject before commit and preserve q2/n2",
                },
                "invalid_endpoint": {
                    "old_cloud_mass": [1.5, 1.5],
                    "source_cloud_mass": [-1.0, 0.0],
                    "source_prepared_mass": [0.5, 1.5],
                    "expected_final_cloud_mass": [0.75, 1.25],
                    "final_endpoint_passes_psd_cone": False,
                    "expected_result": "reject before commit and preserve q2/n2",
                },
                "no_air": {
                    "kind": "manufactured no-air regression using supplied numeric fixture; not a native-cell replay",
                    "carrier": 92363.85,
                    "old_q": 3.7537916e-8,
                    "old_n": 8961516.0,
                    "dt": 20.0,
                    "raw_q_source": "REAL32(REAL32(-3.059018638396083e-7)/W)",
                    "raw_n_source": "REAL32(REAL32(-72988600)/W)",
                    "baseline_weighted_q_over_n_gap_r32_ulp": 8.160412680357695,
                    "intensive_r32_stored_q_over_n_gap_r32_ulp": 7.263443915173411,
                    "expected": "baseline theta=1 rejects; source-first stage is accepted within existing 8-ULP bound and bit-equal to the no-air final state",
                    "ledger_units": "pressure-carrier amounts; original dt*coupled source versus W*(staged-old), signed delta, L1, and max absolute delta; no kg or energy interpretation",
                },
                "stale_payload_rejections": {
                    "stale_step": "reject before commit",
                    "stale_carrier": "reject before commit",
                    "stale_source_ref": "reject before commit",
                },
            },
        },
        "results": results,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True,
                        help="exact generated native_update.f90 from the candidate source manifest")
    parser.add_argument("--receipt", type=Path, required=True,
                        help="new receipt path; existing files are never overwritten")
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error(f"receipt already exists; choose a new path: {args.receipt}")
    evidence = execute(args.proposal, args.receipt)
    print(f"{evidence['status']}: {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
