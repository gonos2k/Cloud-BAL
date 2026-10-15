PROGRAM pr85_kdm6_ice_sedimentation_source
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_is_finite
  IMPLICIT NONE
  INTERFACE
    SUBROUTINE pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
        dry_density,delz,mass_rate,second_rate,qice,nice,mode,q_active_min,second_active_min, &
        density_min,density_max,approved_q_rate,approved_second_rate, &
        budget_unit,trace,valid)
      USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
      INTEGER, INTENT(IN) :: kts,kte,cell_i,lat,substep,mstep,mode,budget_unit
      REAL(real32), INTENT(IN) :: dt
      REAL(real32), INTENT(IN) :: dry_density(kts:kte),delz(kts:kte)
      REAL(real64), INTENT(IN) :: mass_rate(kts:kte),second_rate(kts:kte)
      REAL(real32), INTENT(IN) :: q_active_min,second_active_min,density_min,density_max
      REAL(real32), INTENT(INOUT) :: qice(kts:kte),nice(kts:kte)
      REAL(real64), INTENT(OUT) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
      LOGICAL, INTENT(IN) :: trace
      LOGICAL, INTENT(OUT) :: valid
    END SUBROUTINE pr85_kdm6_paired_sediment_column
  END INTERFACE
  INTEGER :: failures
  failures=0
  CALL recorded_underflow_case(failures)
  CALL mirrored_underflow_case(failures)
  CALL distinct_velocity_column_case(failures)
  CALL outgoing_limited_case(failures)
  CALL finite_r64_unrepresentable_endpoint_case(failures)
  CALL donor_invisible_receiver_subnormal_case(failures)
  CALL negative_huge_endpoint_backtrack_case(failures)
  CALL invalid_input_is_atomic_case(failures)
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)','PR85 KDM6 ice sedimentation cases PASS'
CONTAINS
  SUBROUTINE recorded_underflow_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    REAL(real32) :: qbefore(1:2),nbefore(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    ! PR67 recorded donor QI and mass velocity rate, but not number rate or
    ! mstep_i. Public PRE_KDM captured NI=1.0169752641940557e-33 #/kgdry at
    ! this cell; convert it with the recorded DEND. The fixture chooses a
    ! distinct number rate only to exercise atomic paired admission. Use
    ! mstep=1 as the largest possible packet; actual mstep_i is unknown.
    q=[0.0_real32,5.605193857299268e-44_real32]
    n=0.0_real32
    rho=[0.99_real32,0.9921161532402039_real32]
    n(2)=REAL(1.0169752641940557e-33_real64*REAL(rho(2),real64),real32)
    dz=[304.0_real32,303.97412109375_real32]
    vrq=[0.0_real64,2.208469404135152d-5]
    vrn=[0.0_real64,2.0d-5]
    qbefore=q; nbefore=n
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,120,2,1,20.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.TRUE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. ANY(q/=qbefore) .OR. ANY(n/=nbefore)) THEN
      PRINT '(a)','FAIL recorded underflow: unrepresentable Q plus positive N was not withheld atomically'
      failures=failures+1
    ENDIF
    PRINT '(a,2(es15.7,1x))','CASE recorded underflow unchanged QI/NI receiver=',q(1),n(1)
  END SUBROUTINE recorded_underflow_case

  SUBROUTINE mirrored_underflow_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2),qbefore(1:2),nbefore(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    q=[0.0_real32,1.0e-4_real32]
    n=[0.0_real32,NEAREST(0.0_real32,1.0_real32)]
    rho=1.0_real32; dz=1.0_real32
    vrq=[0.0_real64,1.0e-3_real64]
    vrn=[0.0_real64,1.0e-5_real64]
    qbefore=q; nbefore=n
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,121,2,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. ANY(q/=qbefore) .OR. ANY(n/=nbefore)) THEN
      PRINT '(a)','FAIL mirrored empty-receiver N underflow was not withheld atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE empty receiver Q representable / N underflow withheld'
  END SUBROUTINE mirrored_underflow_case

  SUBROUTINE distinct_velocity_column_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:3),n(1:3),rho(1:3),dz(1:3),qold(1:3),nold(1:3)
    REAL(real64) :: vrq(1:3),vrn(1:3),fq(1:3),fn(1:3)
    REAL(real64) :: q0,n0,q1,n1,groundq,groundn,expected_q_rate,expected_n_rate
    REAL(real64) :: expected_delta_q,expected_delta_n,expected_residual_q,expected_residual_n
    INTEGER :: unit
    CHARACTER(len=512) :: line
    CHARACTER(len=16) :: tag
    INTEGER :: ci,lat,substep,nlevels
    REAL(real64) :: ledger_values(12)
    LOGICAL :: valid
    q=[2.0e-4_real32,5.0e-5_real32,1.0e-4_real32]
    n=[1.0e5_real32,3.0e4_real32,8.0e4_real32]
    rho=[0.8_real32,0.9_real32,1.0_real32]
    dz=[120.0_real32,180.0_real32,240.0_real32]
    ! Native rates are V/DELZ. Different mass and number rates exercise the
    ! source's distinct VQ and VN sedimentation paths.
    vrq=[2.0e-3_real64,1.5e-3_real64,1.0e-3_real64]
    vrn=[1.0e-3_real64,2.0e-3_real64,4.0e-3_real64]
    qold=q; nold=n
    expected_q_rate=REAL(rho(2),real64)*REAL(q(2),real64)*vrq(2)
    expected_n_rate=REAL(n(2),real64)*vrn(2)
    q0=SUM(REAL(rho,real64)*REAL(q,real64)*REAL(dz,real64))
    n0=SUM(REAL(n,real64)*REAL(dz,real64))
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,3,17,4,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.TRUE.,valid)
    REWIND(unit)
    READ(unit,'(a)') line
    READ(line,*) tag,ci,lat,substep,nlevels,ledger_values
    groundq=ledger_values(7); groundn=ledger_values(8)
    CLOSE(unit)
    q1=SUM(REAL(rho,real64)*REAL(q,real64)*REAL(dz,real64))
    n1=SUM(REAL(n,real64)*REAL(dz,real64))
    expected_delta_q=0.0_real64; expected_delta_n=0.0_real64
    BLOCK
      INTEGER :: k
      DO k=1,3
        expected_delta_q=expected_delta_q+(REAL(q(k),real64)-REAL(qold(k),real64))* &
                          REAL(rho(k),real64)*REAL(dz(k),real64)
        expected_delta_n=expected_delta_n+(REAL(n(k),real64)-REAL(nold(k),real64))* &
                          REAL(dz(k),real64)
      ENDDO
    END BLOCK
    expected_residual_q=expected_delta_q+groundq
    expected_residual_n=expected_delta_n+groundn
    IF (.NOT.valid .OR. q(1)<=0.0_real32 .OR. n(1)<=0.0_real32 .OR. &
        q(3)>=1.0e-4_real32 .OR. n(3)>=8.0e4_real32 .OR. &
        ABS(q1+groundq-q0)>5.0e-7_real64*MAX(q0,1.0e-20_real64) .OR. &
        ABS(n1+groundn-n0)>5.0e-7_real64*MAX(n0,1.0_real64) .OR. &
        ABS(fq(2)-expected_q_rate)>1.0e-13_real64*expected_q_rate .OR. &
        ABS(fn(2)-expected_n_rate)>1.0e-13_real64*expected_n_rate .OR. &
        ABS(ledger_values(9)-expected_delta_q)>1.0e-13_real64*MAX(ABS(expected_delta_q),1.0e-30_real64) .OR. &
        ABS(ledger_values(10)-expected_delta_n)>1.0e-13_real64*MAX(ABS(expected_delta_n),1.0e-30_real64) .OR. &
        ABS(ledger_values(11)-expected_residual_q)>1.0e-13_real64*MAX(ABS(expected_residual_q),1.0e-30_real64) .OR. &
        ABS(ledger_values(12)-expected_residual_n)>1.0e-13_real64*MAX(ABS(expected_residual_n),1.0e-30_real64)) THEN
      PRINT '(a)','FAIL distinct-velocity rate, ledger, or column closure'
      failures=failures+1
    ENDIF
    PRINT '(a,4(es15.7,1x))','CASE distinct velocities ground(Q,N), residual(Q,N)=', &
      groundq,groundn,q1+groundq-q0,n1+groundn-n0
  END SUBROUTINE distinct_velocity_column_case

  SUBROUTINE outgoing_limited_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    q=[1.0e-5_real32,2.0e-5_real32]
    n=[4.0e2_real32,8.0e2_real32]
    rho=1.0_real32; dz=10.0_real32
    vrq=2.0_real64; vrn=1.0_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,18,4,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. ANY(q<0.0_real32) .OR. ANY(n<0.0_real32) .OR. &
        ANY((q==0.0_real32).NEQV.(n==0.0_real32)) .OR. fq(2)>=2.0e-5_real64) THEN
      PRINT '(a)','FAIL outgoing-limited paired approval'
      failures=failures+1
    ENDIF
    PRINT '(a,4(es15.7,1x))','CASE outgoing limited QI/NI donor rate=',q(2),n(2),fq(2),fn(2)
  END SUBROUTINE outgoing_limited_case

  SUBROUTINE finite_r64_unrepresentable_endpoint_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2),qbefore(1:2),nbefore(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    q=[0.0_real32,1.0e-4_real32]
    n=[0.0_real32,1.0e10_real32]
    rho=[1.0e-20_real32,1.0_real32]
    dz=[1.0e-20_real32,1.0e20_real32]
    vrq=[0.0_real64,1.0_real64]; vrn=[0.0_real64,1.0_real64]
    qbefore=q; nbefore=n
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,122,2,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. .NOT.ALL(ieee_is_finite(q)) .OR. .NOT.ALL(ieee_is_finite(n)) .OR. &
        ANY(q/=qbefore) .OR. ANY(n/=nbefore) .OR. ANY(fq/=0.0_real64) .OR. ANY(fn/=0.0_real64)) THEN
      PRINT '(a)','FAIL unrepresentable receiver packet was not withheld atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE finite R64 but unrepresentable / donor-invisible packet withheld'
  END SUBROUTINE finite_r64_unrepresentable_endpoint_case

  SUBROUTINE donor_invisible_receiver_subnormal_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2),qbefore(1:2),nbefore(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    q=[0.0_real32,1.0e-4_real32]; n=[0.0_real32,1.0e5_real32]
    rho=1.0_real32; dz=[1.0_real32,1.0e20_real32]
    vrq=[0.0_real64,1.4e-61_real64]; vrn=[0.0_real64,1.4e-70_real64]
    qbefore=q; nbefore=n
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,124,2,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. ANY(q/=qbefore) .OR. ANY(n/=nbefore) .OR. &
        ANY(fq/=0.0_real64) .OR. ANY(fn/=0.0_real64)) THEN
      PRINT '(a)','FAIL donor-invisible / receiver-subnormal packet was not withheld atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE donor-invisible packet / receiver subnormal atomically withheld'
  END SUBROUTINE donor_invisible_receiver_subnormal_case

  SUBROUTINE negative_huge_endpoint_backtrack_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:1),n(1:1),rho(1:1),dz(1:1),qbefore(1:1),nbefore(1:1)
    REAL(real64) :: vrq(1:1),vrn(1:1),fq(1:1),fn(1:1)
    INTEGER :: unit
    LOGICAL :: valid
    ! A finite extreme ground proposal makes qd64 negative at the full step;
    ! admission must backtrack/withhold before computing an endpoint ULP.
    q=1.0_real32; n=1.0_real32; rho=1.0_real32; dz=1.0_real32
    vrq=REAL(HUGE(0.0_real32),real64); vrn=0.0_real64
    qbefore=q; nbefore=n
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,123,2,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (.NOT.valid .OR. ANY(q/=qbefore) .OR. ANY(n/=nbefore) .OR. &
        ANY(fq/=0.0_real64) .OR. ANY(fn/=0.0_real64)) THEN
      PRINT '(a)','FAIL negative HUGE endpoint was not safely withheld'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE finite negative HUGE endpoint safely withheld'
  END SUBROUTINE negative_huge_endpoint_backtrack_case

  SUBROUTINE invalid_input_is_atomic_case(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2)
    REAL(real32) :: qbefore(1:2),nbefore(1:2)
    REAL(real64) :: vrq(1:2),vrn(1:2),fq(1:2),fn(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    q=[1.0e-4_real32,2.0e-4_real32]
    n=[1.0e3_real32,2.0e3_real32]
    qbefore=q; nbefore=n
    rho=1.0_real32; dz=100.0_real32; vrq=1.0e-3_real64; vrn=1.0e-3_real64
    rho(2)=ieee_value(0.0_real32,ieee_quiet_nan)
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,19,4,1,1.0_real32,1, &
      rho,dz,vrq,vrn,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32,fq,fn,unit,.FALSE.,valid)
    CLOSE(unit)
    IF (valid .OR. ANY(q/=qbefore) .OR. ANY(n/=nbefore)) THEN
      PRINT '(a)','FAIL invalid input did not reject atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE invalid input atomic rejection'
  END SUBROUTINE invalid_input_is_atomic_case
END PROGRAM pr85_kdm6_ice_sedimentation_source
