PROGRAM pr85_kdm6_graupel_sedimentation_source
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  IMPLICIT NONE
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
  CALL nonconvex_interior_candidate(failures)
  CALL captured_transient_receiver_deferred(failures)
  CALL invalid_bases_rejected_atomically(failures)
  CALL ground_rate_and_volume_closure(failures)
  CALL invalid_mode_rejected_atomically(failures)
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)','PR85 KDM6 graupel sedimentation cases PASS'
CONTAINS
  SUBROUTINE nonconvex_interior_candidate(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),b(1:2),rho(1:2),dz(1:2),q0(1:2),b0(1:2)
    REAL(real64) :: rate(1:2),b_rate(1:2),approved_q(1:2),approved_b(1:2)
    REAL(real64) :: qinv0,qinv1,binv0,binv1,alpha,rho_donor,rho_receiver
    INTEGER :: unit
    LOGICAL :: valid
    ! theta=0.5 leaves the receiver below Bmin; theta=1 depletes the donor
    ! below Bmin. The valid interval lies inside (2/3,0.8) at Q/B=400.
    q=[0.0_real32,8.8e-13_real32]; b=[0.0_real32,2.2e-15_real32]
    rho=1.0_real32; dz=1.0_real32
    rate=[0.0_real64,1.5_real64/2.2_real64]; b_rate=rate
    q0=q; b0=b
    qinv0=SUM(REAL(rho,real64)*REAL(q,real64)*REAL(dz,real64))
    binv0=SUM(REAL(rho,real64)*REAL(b,real64)*REAL(dz,real64))
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,201,42,1,1.0_real32,1, &
      rho,dz,rate,b_rate,q,b,2,1.0e-9_real32,1.0e-15_real32, &
      100.0_real32,900.0_real32,approved_q,approved_b,unit,.TRUE.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
    CLOSE(unit)
    qinv1=SUM(REAL(rho,real64)*REAL(q,real64)*REAL(dz,real64))
    binv1=SUM(REAL(rho,real64)*REAL(b,real64)*REAL(dz,real64))
    alpha=approved_q(2)/(REAL(rho(2),real64)*REAL(q0(2),real64)*rate(2))
    rho_receiver=REAL(q(1),real64)/REAL(b(1),real64)
    rho_donor=REAL(q(2),real64)/REAL(b(2),real64)
    IF (.NOT.valid .OR. alpha<=2.0_real64/3.0_real64 .OR. alpha>=0.8_real64 .OR. &
        q(1)<=0.0_real32 .OR. b(1)<=1.0e-15_real32 .OR. b(2)<=1.0e-15_real32 .OR. &
        ABS(rho_receiver-400.0_real64)>2.0e-3_real64 .OR. &
        ABS(rho_donor-400.0_real64)>2.0e-3_real64 .OR. &
        ABS(qinv1-qinv0)>2.0e-7_real64*qinv0 .OR. ABS(binv1-binv0)>2.0e-7_real64*binv0) THEN
      PRINT '(a)','FAIL nonconvex interior theta, paired density, or column inventory closure'
      failures=failures+1
    ENDIF
    PRINT '(a,3(es15.7,1x))','CASE nonconvex alpha/rhoRecv/rhoDonor=',alpha,rho_receiver,rho_donor
  END SUBROUTINE nonconvex_interior_candidate

  SUBROUTINE captured_transient_receiver_deferred(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:2),b(1:2),rho(1:2),dz(1:2),q0(1:2),b0(1:2)
    REAL(real64) :: rate(1:2),b_rate(1:2),approved_q(1:2),approved_b(1:2)
    REAL(real64), PARAMETER :: q_packet=4.4336086316e-14_real64
    REAL(real64), PARAMETER :: b_packet=1.1084024332e-16_real64
    REAL(real64) :: requested_q,requested_b
    INTEGER :: unit
    LOGICAL :: valid
    ! Captured-scale transfer into an empty cell has QG/BG=400 but is below
    ! both native activity thresholds, so the full packet must be deferred.
    q=[0.0_real32,1.0e-8_real32]; b=[0.0_real32,2.5e-11_real32]
    rho=1.0_real32; dz=1.0_real32
    rate=[0.0_real64,q_packet/(REAL(q(2),real64)*20.0_real64)]; b_rate=rate
    requested_q=REAL(rho(2),real64)*REAL(q(2),real64)*rate(2)*20.0_real64
    requested_b=REAL(rho(2),real64)*REAL(b(2),real64)*b_rate(2)*20.0_real64
    q0=q; b0=b
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,2,235,42,2,20.0_real32,1, &
      rho,dz,rate,b_rate,q,b,2,1.0e-9_real32,1.0e-15_real32, &
      100.0_real32,900.0_real32,approved_q,approved_b,unit,.TRUE.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
    CLOSE(unit)
    IF (.NOT.valid .OR. ABS(requested_q-q_packet)>1.0e-6_real64*q_packet .OR. &
        ABS(requested_b-b_packet)>1.0e-6_real64*b_packet .OR. ANY(q/=q0) .OR. &
        ANY(b/=b0) .OR. ANY(approved_q/=0.0_real64) .OR. ANY(approved_b/=0.0_real64)) THEN
      PRINT '(a)','FAIL transient full-packet proposal was not deferred atomically'
      failures=failures+1
    ENDIF
    PRINT '(a,3(es15.7,1x))','CASE captured-scale packet Q/B/approved=',requested_q,requested_b,MAXVAL(approved_q)
  END SUBROUTINE captured_transient_receiver_deferred

  SUBROUTINE invalid_bases_rejected_atomically(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:1),b(1:1),rho(1:1),dz(1:1),q0(1:1),b0(1:1)
    REAL(real64) :: rate(1:1),brate(1:1),aq(1:1),ab(1:1)
    INTEGER :: unit,case_id
    LOGICAL :: valid
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    DO case_id=1,2
      rho=1.0_real32; dz=1.0_real32; rate=0.1_real64; brate=rate
      IF (case_id==1) THEN
        q=4.4336086316e-14_real32; b=1.1084024332e-16_real32
      ELSE
        q=1.21e-12_real32; b=1.1e-15_real32 ! Q/B=1100, outside consumer domain
      ENDIF
      q0=q; b0=b
      CALL pr85_kdm6_paired_sediment_column(1,1,236+case_id,42,1,1.0_real32,1, &
        rho,dz,rate,brate,q,b,2,1.0e-9_real32,1.0e-15_real32, &
        100.0_real32,900.0_real32,aq,ab,unit,.FALSE.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
      IF (valid .OR. ANY(q/=q0) .OR. ANY(b/=b0) .OR. ANY(aq/=0.0_real64) .OR. &
          ANY(ab/=0.0_real64)) THEN
        PRINT '(a,i0)','FAIL invalid G base was not rejected atomically, case=',case_id
        failures=failures+1
      ENDIF
    ENDDO
    CLOSE(unit)
    PRINT '(a)','CASE transient and unsupported-density G bases rejected without mutation'
  END SUBROUTINE invalid_bases_rejected_atomically

  SUBROUTINE ground_rate_and_volume_closure(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:1),b(1:1),rho(1:1),dz(1:1),q0(1:1),b0(1:1)
    REAL(real64) :: rate(1:1),brate(1:1),aq(1:1),ab(1:1)
    REAL(real64) :: qinv0,qinv1,binv0,binv1,ground_q,ground_b,legacy_q,legacy_b
    INTEGER :: unit
    LOGICAL :: valid
    q=2.0e-9_real32; b=5.0e-12_real32
    rho=0.8_real32; dz=100.0_real32; rate=0.1_real64; brate=rate
    q0=q; b0=b
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,241,42,1,1.0_real32,2, &
      rho,dz,rate,brate,q,b,2,1.0e-9_real32,1.0e-15_real32, &
      100.0_real32,900.0_real32,aq,ab,unit,.TRUE.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
    CLOSE(unit)
    qinv0=REAL(rho(1),real64)*REAL(q0(1),real64)*REAL(dz(1),real64)
    binv0=REAL(rho(1),real64)*REAL(b0(1),real64)*REAL(dz(1),real64)
    qinv1=REAL(rho(1),real64)*REAL(q(1),real64)*REAL(dz(1),real64)
    binv1=REAL(rho(1),real64)*REAL(b(1),real64)*REAL(dz(1),real64)
    ground_q=aq(1)*REAL(dz(1),real64)
    ground_b=ab(1)*REAL(dz(1),real64)
    legacy_q=REAL(rho(1),real64)*REAL(q0(1),real64)*rate(1)/2.0_real64
    legacy_b=REAL(rho(1),real64)*REAL(b0(1),real64)*brate(1)/2.0_real64
    IF (.NOT.valid .OR. aq(1)<=0.0_real64 .OR. ab(1)<=0.0_real64 .OR. &
        ABS(aq(1)-legacy_q)>1.0e-12_real64*legacy_q .OR. &
        ABS(ab(1)-legacy_b)>1.0e-12_real64*legacy_b .OR. &
        ABS(qinv1+ground_q-qinv0)>2.0e-7_real64*qinv0 .OR. &
        ABS(binv1+ground_b-binv0)>2.0e-7_real64*binv0) THEN
      PRINT '(a)','FAIL G ground rates, stored-volume inventory, or legacy scaling'
      failures=failures+1
    ENDIF
    PRINT '(a,4(es15.7,1x))','CASE G ground rates, residual=',aq(1),ab(1),qinv1+ground_q-qinv0,binv1+ground_b-binv0
  END SUBROUTINE ground_rate_and_volume_closure

  SUBROUTINE invalid_mode_rejected_atomically(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: q(1:1),b(1:1),rho(1:1),dz(1:1),q0(1:1),b0(1:1)
    REAL(real64) :: rate(1:1),brate(1:1),aq(1:1),ab(1:1)
    INTEGER :: unit
    LOGICAL :: valid
    q=2.0e-9_real32; b=5.0e-12_real32; rho=1.0_real32; dz=1.0_real32
    rate=0.0_real64; brate=rate; q0=q; b0=b
    OPEN(NEWUNIT=unit,STATUS='scratch',FORM='formatted')
    CALL pr85_kdm6_paired_sediment_column(1,1,245,42,1,1.0_real32,1, &
      rho,dz,rate,brate,q,b,99,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &
      aq,ab,unit,.FALSE.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)
    CLOSE(unit)
    IF (valid .OR. ANY(q/=q0) .OR. ANY(b/=b0) .OR. ANY(aq/=0.0_real64) .OR. &
        ANY(ab/=0.0_real64)) THEN
      PRINT '(a)','FAIL invalid mode did not reject atomically'
      failures=failures+1
    ENDIF
    PRINT '(a)','CASE unsupported sediment mode rejected atomically'
  END SUBROUTINE invalid_mode_rejected_atomically
END PROGRAM pr85_kdm6_graupel_sedimentation_source
