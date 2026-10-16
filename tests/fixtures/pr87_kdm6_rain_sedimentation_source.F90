PROGRAM pr87_kdm6_rain_sedimentation_source
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  IMPLICIT NONE
  INTEGER, PARAMETER :: PR87_SED_RAIN=3
  REAL(real32), PARAMETER :: PIDNR=12566.37109375_real32, POWER=3.0_real32
  REAL(real32), PARAMETER :: LAMBDA_MIN=961.0_real32, LAMBDA_MAX=35000.0_real32
  REAL(real64), PARAMETER :: PAIR_MIN=REAL(PIDNR,real64)/REAL(LAMBDA_MAX,real64)**REAL(POWER,real64)
  REAL(real64), PARAMETER :: PAIR_MAX=REAL(PIDNR,real64)/REAL(LAMBDA_MIN,real64)**REAL(POWER,real64)
  INTERFACE
    SUBROUTINE pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
        dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
        second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
        budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
      USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
      INTEGER, INTENT(IN) :: kts,kte,cell_i,lat,substep,mstep,mode,budget_unit
      REAL(real32), INTENT(IN) :: dt,dry_density(kts:kte),delz(kts:kte)
      REAL(real64), INTENT(IN) :: mass_rate(kts:kte),second_rate(kts:kte)
      REAL(real32), INTENT(INOUT) :: qstate(kts:kte),second_state(kts:kte)
      REAL(real32), INTENT(IN) :: q_active_min,second_active_min,density_min,density_max
      REAL(real64), INTENT(OUT) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
      LOGICAL, INTENT(IN) :: trace
      LOGICAL, INTENT(OUT) :: valid
      REAL(real32), INTENT(IN) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
    END SUBROUTINE pr85_kdm6_paired_sediment_column
  END INTERFACE
  INTEGER :: failures
  failures=0
  CALL captured_target_is_valid(failures)
  CALL stratified_receiver_uses_distinct_rates(failures)
  CALL lower_bound_limits_one_common_face_factor(failures)
  CALL subquantum_packet_allows_zero_factor(failures)
  CALL invalid_base_is_rejected_atomically(failures)
  CALL strict_ng_bounds_reject_old_helper_slack(failures)
  CALL admissible_step_stays_inside_strict_ng_bounds(failures)
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)','PR87 KDM6 rain sedimentation cases PASS'
CONTAINS
  SUBROUTINE captured_target_is_valid(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1),n(1),rho(1),dz(1)
    REAL(real64) :: qr(1),nr(1),aq(1),an(1)
    INTEGER :: unit
    LOGICAL :: valid
    q=8.1509760053e-10_real32
    rho=0.6247655153_real32
    n=rho*2.7809617519_real32
    dz=10.0_real32; qr=0.0_real64; nr=0.0_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,301,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    IF (.NOT.valid .OR. ABS(REAL(rho(1),real64)*REAL(q(1),real64)/REAL(n(1),real64)- &
       8.1509760053e-10_real64/2.7809617519_real64)>2.0e-16_real64) THEN
      PRINT '(a)','FAIL captured rain target was not accepted as a valid paired base'
      failures=failures+1
    ENDIF
    PRINT '(a,2(es15.7,1x))','CASE captured rain Q/Nvol=',q(1),n(1)
  END SUBROUTINE captured_target_is_valid

  SUBROUTINE stratified_receiver_uses_distinct_rates(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2)
    REAL(real64) :: qr(1:2),nr(1:2),aq(1:2),an(1:2),mean_recv
    INTEGER :: unit
    LOGICAL :: valid
    rho=0.6247655153_real32; dz=20.0_real32
    q=[0.0_real32,1.0e-7_real32]
    n=[0.0_real32,rho(2)*q(2)/1.0e-8_real32]
    qr=[0.0_real64,1.0e-3_real64]; nr=[0.0_real64,1.1e-3_real64]
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,302,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    mean_recv=REAL(rho(1),real64)*REAL(q(1),real64)/REAL(n(1),real64)
    IF (.NOT.valid .OR. q(1)<=0.0_real32 .OR. n(1)<=0.0_real32 .OR. &
         .NOT.rain_strict_valid(q(1),n(1),rho(1)) .OR. &
        aq(2)<=0.0_real64 .OR. an(2)<=0.0_real64 .OR. &
        ABS(aq(2)-an(2))<1.0e-8_real64*MAX(aq(2),an(2))) THEN
      PRINT '(a)','FAIL rain transfer to empty receiver lost paired-cone or distinct-rate behavior'
      failures=failures+1
    ENDIF
    PRINT '(a,3(es15.7,1x))','CASE rain receiver Q/Nmean/approvedQ=',q(1),mean_recv,aq(2)
  END SUBROUTINE stratified_receiver_uses_distinct_rates

  SUBROUTINE lower_bound_limits_one_common_face_factor(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1),n(1),rho(1),dz(1),q0,n0
    REAL(real64) :: qr(1),nr(1),aq(1),an(1),alpha
    INTEGER :: unit
    LOGICAL :: valid
    rho=0.6247655153_real32; dz=1.0_real32
    q=1.0e-7_real32
    n=REAL(rho(1),real32)*q/REAL(PAIR_MIN*1.01_real64,real32)
    q0=q(1); n0=n(1); qr=0.1_real64; nr=0.001_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,303,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    alpha=aq(1)/(REAL(rho(1),real64)*REAL(q0,real64)*qr(1))
    IF (.NOT.valid .OR. alpha<=0.0_real64 .OR. alpha>=1.0_real64 .OR. &
        an(1)<=0.0_real64 .OR. &
        REAL(n(1),real64)<REAL(rho(1),real64)*REAL(LAMBDA_MIN,real64)**REAL(POWER,real64)/ &
        REAL(PIDNR,real64)*REAL(q(1),real64)) THEN
      PRINT '(a)','FAIL rain lower-bound backtracking did not return one admissible partial factor'
      failures=failures+1
    ENDIF
    PRINT '(a,3(es15.7,1x))','CASE rain partial alpha/mean/approvedN=',alpha, &
      REAL(rho(1),real64)*REAL(q(1),real64)/REAL(n(1),real64),an(1)
  END SUBROUTINE lower_bound_limits_one_common_face_factor

  SUBROUTINE subquantum_packet_allows_zero_factor(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1),n(1),rho(1),dz(1),q0,n0
    REAL(real64) :: qr(1),nr(1),aq(1),an(1)
    INTEGER :: unit
    LOGICAL :: valid
    rho=0.6247655153_real32; q=8.1509760053e-10_real32
    n=rho*2.7809617519_real32; dz=1.0_real32; q0=q(1); n0=n(1)
    qr=1.0e-20_real64; nr=2.0e-20_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,304,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    IF (.NOT.valid .OR. q(1)/=q0 .OR. n(1)/=n0 .OR. ANY(aq/=0.0_real64) .OR. &
        ANY(an/=0.0_real64)) THEN
      PRINT '(a)','FAIL sub-quantum rain packet was not safely deferred at zero factor'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE rain sub-quantum proposal safely accepted at zero factor'
  END SUBROUTINE subquantum_packet_allows_zero_factor

  SUBROUTINE invalid_base_is_rejected_atomically(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1),n(1),rho(1),dz(1),q0,n0
    REAL(real64) :: qr(1),nr(1),aq(1),an(1)
    INTEGER :: unit
    LOGICAL :: valid
    rho=0.6247655153_real32; q=1.0e-7_real32
    n=REAL(rho(1),real32)*q/REAL(PAIR_MIN/2.0_real64,real32)
    dz=1.0_real32; q0=q(1); n0=n(1); qr=0.1_real64; nr=0.1_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,305,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    IF (valid .OR. q(1)/=q0 .OR. n(1)/=n0 .OR. ANY(aq/=0.0_real64) .OR. &
        ANY(an/=0.0_real64)) THEN
      PRINT '(a)','FAIL invalid initial rain base was not rejected atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE unsupported rain mean mass rejected atomically'
  END SUBROUTINE invalid_base_is_rejected_atomically

  PURE LOGICAL FUNCTION rain_strict_valid(q,n,rho)
    REAL(real32), INTENT(IN) :: q,n,rho
    REAL(real64) :: nmin,nmax
    rain_strict_valid=.FALSE.
    IF (q==0.0_real32 .AND. n==0.0_real32) THEN
      rain_strict_valid=.TRUE.; RETURN
    ENDIF
    IF (q<=0.0_real32 .OR. n<=0.0_real32) RETURN
    nmin=REAL(rho,real64)*REAL(LAMBDA_MIN,real64)**REAL(POWER,real64)/REAL(PIDNR,real64)
    nmax=REAL(rho,real64)*REAL(LAMBDA_MAX,real64)**REAL(POWER,real64)/REAL(PIDNR,real64)
    rain_strict_valid=REAL(n,real64)>=nmin*REAL(q,real64) .AND. &
      REAL(n,real64)<=nmax*REAL(q,real64)
  END FUNCTION rain_strict_valid

  SUBROUTINE strict_ng_bounds_reject_old_helper_slack(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1),n(1),rho(1),dz(1),q0,n0
    REAL(real64) :: qr(1),nr(1),aq(1),an(1)
    INTEGER :: unit
    LOGICAL :: valid
    q=1.2257382608904521e-11_real32
    n=0.02628232352435589_real32
    rho=0.6284514665603638_real32; dz=1.0_real32
    IF (TRANSFER(q(1),0_int32)/=INT(Z'2D57A258',int32) .OR. &
        TRANSFER(n(1),0_int32)/=INT(Z'3CD74E07',int32) .OR. &
        TRANSFER(rho(1),0_int32)/=INT(Z'3F20E232',int32)) THEN
      PRINT '(a)','FAIL captured second-PRE RAIN R32 words changed'
      failures=failures+1
      RETURN
    ENDIF
    IF (rain_strict_valid(q(1),n(1),rho(1)) .OR. &
        REAL(rho(1),real64)*REAL(q(1),real64)/REAL(n(1),real64)< &
        PAIR_MIN-8.0_real64*REAL(SPACING(REAL(PAIR_MIN,real32)),real64)) THEN
      PRINT '(a)','FAIL captured old-helper-slack state setup is invalid'
      failures=failures+1
      RETURN
    ENDIF
    q0=q(1); n0=n(1); qr=0.0_real64; nr=0.0_real64
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,306,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    IF (valid .OR. q(1)/=q0 .OR. n(1)/=n0 .OR. ANY(aq/=0.0_real64) .OR. &
        ANY(an/=0.0_real64)) THEN
      PRINT '(a)','FAIL strict NG cone accepted an endpoint inside old helper slack'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE captured second-PRE RAIN state rejected by strict NG cone'
  END SUBROUTINE strict_ng_bounds_reject_old_helper_slack

  SUBROUTINE admissible_step_stays_inside_strict_ng_bounds(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),n(1:2),rho(1:2),dz(1:2)
    REAL(real64) :: qr(1:2),nr(1:2),aq(1:2),an(1:2)
    INTEGER :: unit
    LOGICAL :: valid
    rho=1.0_real32; dz=1.0_real32
    q=[1.0e-4_real32,1.0e-3_real32]
    n=[341188.375_real32,1024.0_real32]
    qr=0.0_real64; nr=[0.0_real64,2.0_real64**(-15)]
    IF (.NOT.rain_strict_valid(q(1),n(1),rho(1)) .OR. &
        .NOT.rain_strict_valid(q(2),n(2),rho(2))) THEN
      PRINT '(a)','FAIL strict rain face regression initial states invalid'
      failures=failures+1
      RETURN
    ENDIF
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,307,42,1,1.0_real32,1, &
      rho,dz,qr,nr,q,n,PR87_SED_RAIN,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,an,unit,.FALSE.,valid,PIDNR,POWER,LAMBDA_MIN,LAMBDA_MAX)
    CLOSE(unit)
    IF (.NOT.valid .OR. .NOT.rain_strict_valid(q(1),n(1),rho(1)) .OR. &
        .NOT.rain_strict_valid(q(2),n(2),rho(2)) .OR. &
        q(1)/=1.0e-4_real32 .OR. n(1)/=341188.375_real32 .OR. &
        q(2)/=1.0e-3_real32 .OR. n(2)/=1024.0_real32 .OR. ANY(an/=0.0_real64)) THEN
      PRINT '(a)','FAIL strict NG rain cone admitted the one-ULP invalid receiver step'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE admissible rain step remains strict-NG-valid when next stored count quantum is invalid'
  END SUBROUTINE admissible_step_stays_inside_strict_ng_bounds
END PROGRAM pr87_kdm6_rain_sedimentation_source
