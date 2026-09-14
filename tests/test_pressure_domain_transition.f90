PROGRAM test_pressure_domain_transition
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state, ONLY: cloud_bal_state_type,stage_result, &
    STATUS_OK,STATUS_FAILED,QUALITY_RAW_MISSING,SOURCE_BACKGROUND_MODEL, &
    SOURCE_COLUMN_PHYSICS,SOURCE_DYNAMIC_TARGET,SOURCE_DYNAMIC_EVIDENCE_BITS, &
    initialize_cloud_bal_state,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,validate_canonical_state, &
    canonical_states_equal
  USE cloud_bal_column_physics, ONLY: pressure_analysis_budget, &
    apply_pressure_domain_transition
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=2,NY=1,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real64), PARAMETER :: G=9.80665_real64,RD=287.05_real64,EPSW=0.622_real64
  REAL(real64), PARAMETER :: P(NZ)=[100000.0_real64,95000.0_real64,90000.0_real64]
  REAL(real64), PARAMETER :: CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
    4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: H0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
    0.0_real64,-3.50e5_real64,-3.50e5_real64]
  INTEGER :: failures
  CHARACTER(LEN=512) :: fixture_path

  failures=0
  CALL GET_COMMAND_ARGUMENT(1,fixture_path)
  CALL test_transition
  CALL test_two_column_transition
  CALL test_retained_mass_roundoff
  CALL test_rejections
  IF (failures/=0) THEN
    PRINT *,'Pressure-domain transition tests failed:',failures
    ERROR STOP 1
  END IF
  IF (LEN_TRIM(fixture_path)>0) CALL write_reference_fixture(TRIM(fixture_path))
  PRINT *,'Pressure-domain transition tests passed'

CONTAINS

  SUBROUTINE check(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE near(actual,expected,atol,rtol,message)
    REAL(real64), INTENT(IN) :: actual,expected,atol,rtol
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ABS(actual-expected)<=atol+rtol*MAX(ABS(actual),ABS(expected)),message)
  END SUBROUTINE near

  SUBROUTINE test_transition
    TYPE(cloud_bal_state_type) :: background,prior,candidate
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: target_i(NZ+1),old_m(2),old_t(2),old_q(6,2)
    REAL(real64) :: expected_m(NZ),expected_t(NZ),expected_q(6,NZ)
    REAL(real64) :: before_m,after_m,before_s(6),after_s(6)
    REAL(real64) :: expected_h,expected_p,expected_dry
    REAL(real64) :: phi_old(NZ),phi_prior(NZ),phi_final(NZ)
    INTEGER :: status,k

    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,100010.0_real32)
    CALL validate_canonical_state(background,.FALSE.,.TRUE.,status,k)
    CALL check(status==STATUS_OK,'background active hydro fields are canonical')
    CALL validate_canonical_state(prior,.FALSE.,.TRUE.,status,k)
    CALL check(status==STATUS_OK,'complete explicit prior is canonical')

    target_i=[100010.0_real64,97500.0_real64,92500.0_real64,87500.0_real64]
    old_m=[background%grid%dry_air_mass_measure(1,1,2), &
      background%grid%dry_air_mass_measure(1,1,3)]
    old_t=[REAL(background%temperature%value(1,1,2),real64), &
      REAL(background%temperature%value(1,1,3),real64)]
    old_q(:,1)=species(background,1,1,2)
    old_q(:,2)=species(background,1,1,3)
    CALL expected_remap(prior,1,old_m,old_t,old_q,target_i, &
      expected_m,expected_t,expected_q)

    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_OK,'one-center pressure-domain activation succeeds')
    CALL check(background%surface_pressure%value(1,1)==99999.125_real32 .AND. &
      prior%surface_pressure%value(1,1)==100010.0_real32, &
      'transition inputs retain their independent surface pressures')
    CALL check(ALL(candidate%above_ground(1,1,:)) .AND. &
      ALL(candidate%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      'exactly one bottom center activates and the other column is untouched')
    CALL check(ALL(candidate%grid%pressure_interface(1,1,:)==target_i), &
      'new active interfaces are the requested pressure partition')

    DO k=1,NZ
      CALL near(REAL(candidate%grid%dry_air_mass_measure(1,1,k),real64),expected_m(k), &
        2.0e-3_real64,3.0e-7_real64,'conservative remap dry mass')
      CALL near(REAL(candidate%temperature%value(1,1,k),real64),expected_t(k), &
        3.0e-5_real64,3.0e-7_real64,'conservative remap temperature')
      CALL near(REAL(candidate%vapor%value(1,1,k),real64),expected_q(1,k), &
        3.0e-7_real64,0.0_real64,'conservative remap vapor')
    END DO
    CALL check(ABS(REAL(candidate%temperature%value(1,1,1),real64)- &
      REAL(prior%temperature%value(1,1,1),real64))>1.0e-5_real64, &
      'new-cell mixture temperature is not simply the prior bottom temperature')
    CALL check(ABS(REAL(candidate%vapor%value(1,1,1),real64)- &
      REAL(prior%vapor%value(1,1,1),real64))>1.0e-8_real64, &
      'new-cell mixture vapor includes the old active overlap')
    CALL near(REAL(candidate%u%value(1,1,1),real64), &
      REAL(prior%u%value(1,1,1),real64),1.0e-6_real64,0.0_real64, &
      'new-cell u comes from the explicit prior')
    CALL near(REAL(candidate%v%value(1,1,1),real64), &
      REAL(prior%v%value(1,1,1),real64),1.0e-6_real64,0.0_real64, &
      'new-cell v comes from the explicit prior')
    CALL near(REAL(candidate%omega%value(1,1,1),real64), &
      REAL(prior%omega%value(1,1,1),real64),1.0e-6_real64,0.0_real64, &
      'new-cell omega comes from the explicit prior')
    CALL check(IAND(candidate%u%source(1,1,1),SOURCE_COLUMN_PHYSICS)/=0_int32 .AND. &
      IAND(candidate%u%source(1,1,1),SOURCE_DYNAMIC_EVIDENCE_BITS)==0_int32, &
      'new-cell wind is derived and has no dynamical evidence authority')
    CALL check(candidate%balance_beta(1,1,1)==0.0_real32 .AND. &
      candidate%obs_support(1,1,1)==0_int32 .AND. &
      .NOT.candidate%omega_target%valid(1,1,1), &
      'new-cell reconstruction carries no wind-adjustment weight or target')
    CALL check(ALL(real32_bits(candidate%u%value(1,1,2:3))== &
      real32_bits(background%u%value(1,1,2:3))) .AND. &
      ALL(real32_bits(candidate%v%value(1,1,2:3))== &
      real32_bits(background%v%value(1,1,2:3))) .AND. &
      ALL(real32_bits(candidate%omega%value(1,1,2:3))== &
      real32_bits(background%omega%value(1,1,2:3))), &
      'old-active wind remains bitwise original')
    CALL check(untouched_column_equal(background,candidate), &
      'second column remains bitwise identical in every canonical field')

    before_m=SUM(background%grid%dry_air_mass_measure(1,1,2:3))
    after_m=SUM(candidate%grid%dry_air_mass_measure(1,1,:))
    before_s=0.0_real64; after_s=0.0_real64
    DO k=2,NZ
      before_s=before_s+background%grid%dry_air_mass_measure(1,1,k)*species(background,1,1,k)
    END DO
    DO k=1,NZ
      after_s=after_s+candidate%grid%dry_air_mass_measure(1,1,k)*species(candidate,1,1,k)
    END DO
    expected_dry=after_m-before_m
    expected_h=0.0_real64
    DO k=2,NZ
      expected_h=expected_h+background%grid%dry_air_mass_measure(1,1,k)* &
        mixture_enthalpy(REAL(background%temperature%value(1,1,k),real64),species(background,1,1,k))
    END DO
    DO k=1,NZ
      expected_h=expected_h-candidate%grid%dry_air_mass_measure(1,1,k)* &
        mixture_enthalpy(REAL(candidate%temperature%value(1,1,k),real64),species(candidate,1,1,k))
    END DO
    expected_h=-expected_h
    expected_p=2000.0_real64*2200.0_real64*10.875_real64/G
    CALL near(budget%dry_air_change_kg,expected_dry,2.0e-2_real64,3.0e-7_real64, &
      'independent dry-air extensive change')
    CALL check(MAXVAL(ABS(budget%species_change_kg-(after_s-before_s)))<2.0e-2_real64, &
      'independent six-species extensive change')
    CALL near(budget%enthalpy_change_j,expected_h,2.0_real64,3.0e-7_real64, &
      'independent full-mixture enthalpy change')
    CALL near(budget%geometry_mass_change_kg,expected_p,2.0e-4_real64,3.0e-7_real64, &
      'column pressure mass is A times delta-PS divided by gravity')
    CALL near(budget%total_mass_error_kg,0.0_real64,2.0e-2_real64,3.0e-7_real64, &
      'pressure transition mass budget closes')
    CALL near(SUM(candidate%grid%pressure_mass_measure(1,1,:))- &
      SUM(background%grid%pressure_mass_measure(1,1,2:3)),expected_p, &
      1.0e-8_real64,3.0e-13_real64,'active pressure-mass column change')
    CALL near(expected_m(1)-old_m(1)*1.0_real64, &
      expected_m(1)-old_m(1),1.0e-12_real64,0.0_real64,'remap oracle is self-consistent')

    CALL hydro_profile(background,1,1,phi_old)
    CALL hydro_profile(prior,1,1,phi_prior)
    CALL hydro_profile(candidate,1,1,phi_final)
    DO k=1,NZ
      IF (k==1) THEN
        CALL near(REAL(candidate%geopotential%value(1,1,k),real64), &
          REAL(prior%geopotential%value(1,1,k),real64)+phi_final(k)-phi_prior(k), &
          3.0e-3_real64,3.0e-7_real64,'new-cell surface-anchored Phi')
      ELSE
        CALL near(REAL(candidate%geopotential%value(1,1,k),real64), &
          REAL(background%geopotential%value(1,1,k),real64)+phi_final(k)-phi_old(k), &
          3.0e-3_real64,3.0e-7_real64,'old-active residual-preserving Phi')
      END IF
      IF (k==1) THEN
        CALL check(candidate%geopotential%value(1,1,k)>0.0_real32, &
          'surface-anchored Phi is positive')
      ELSE
        CALL check(candidate%geopotential%value(1,1,k)>0.0_real32 .AND. &
          candidate%geopotential%value(1,1,k)>candidate%geopotential%value(1,1,k-1), &
          'surface-anchored Phi is monotone')
      END IF
    END DO
    CALL check(ABS(REAL(background%geopotential%value(1,1,2),real64)-phi_old(2))>1.0e-3_real64, &
      'fixture carries a nonzero old hydrostatic residual')
    CALL check(ABS(REAL(prior%geopotential%value(1,1,1),real64)-phi_prior(1))>1.0e-3_real64, &
      'fixture carries an explicit prior bottom residual')
  END SUBROUTINE test_transition

  SUBROUTINE test_two_column_transition
    TYPE(cloud_bal_state_type) :: background,prior,candidate
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: new_i(4),old_m(2),old_t(2),old_q(6,2)
    REAL(real64) :: expected_m(3),expected_t(3),expected_q(6,3)
    INTEGER :: status,reason,k

    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,100010.0_real32,.TRUE.)
    CALL validate_canonical_state(prior,.FALSE.,.TRUE.,status,reason)
    CALL check(status==STATUS_OK,'two-column explicit prior is canonical')
    new_i=[100010.0_real64,97500.0_real64,92500.0_real64,87500.0_real64]
    old_m=[background%grid%dry_air_mass_measure(2,1,2), &
      background%grid%dry_air_mass_measure(2,1,3)]
    old_t=[REAL(background%temperature%value(2,1,2),real64), &
      REAL(background%temperature%value(2,1,3),real64)]
    old_q(:,1)=species(background,2,1,2); old_q(:,2)=species(background,2,1,3)
    CALL expected_remap(prior,2,old_m,old_t,old_q,new_i,expected_m,expected_t,expected_q)
    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_OK,'independent two-column transitions succeed')
    CALL check(ALL(candidate%above_ground(:,1,:)), &
      'both columns expose exactly one new bottom center')
    DO k=1,3
      CALL near(REAL(candidate%temperature%value(2,1,k),real64),expected_t(k), &
        3.0e-5_real64,3.0e-7_real64,'second-column remap temperature')
      CALL near(REAL(candidate%vapor%value(2,1,k),real64),expected_q(1,k), &
        3.0e-7_real64,0.0_real64,'second-column remap vapor')
    END DO
    CALL check(ABS(REAL(candidate%temperature%value(1,1,1),real64)- &
      REAL(candidate%temperature%value(2,1,1),real64))>1.0e-5_real64 .AND. &
      ABS(REAL(candidate%vapor%value(1,1,1),real64)- &
      REAL(candidate%vapor%value(2,1,1),real64))>1.0e-8_real64, &
      'changed columns do not reuse one remap buffer')
  END SUBROUTINE test_two_column_transition

  SUBROUTINE test_retained_mass_roundoff
    TYPE(cloud_bal_state_type) :: background,prior,candidate
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: direction

    DO direction=-1,1,2
      CALL make_background(background,99999.125_real32)
      ! A phase step may retain pre-roundcast dry mass while its six stored
      ! mixing ratios have a slightly different sum. This is not new water.
      background%grid%dry_air_mass_measure(1,1,2)=background%grid%dry_air_mass_measure(1,1,2)* &
        (1.0_real64+REAL(direction,real64)*1.0e-9_real64)
      CALL make_prior(background,prior,100010.0_real32)
      CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
      CALL check(result%status==STATUS_OK,'bounded retained dry-mass roundoff accepted')
    END DO
    background%grid%dry_air_mass_measure(1,1,2)=background%grid%dry_air_mass_measure(1,1,2)*1.001_real64
    CALL expect_reject(background,prior,candidate,result,budget,'unbounded donor mass defect')
  END SUBROUTINE test_retained_mass_roundoff

  SUBROUTINE test_rejections
    TYPE(cloud_bal_state_type) :: background,prior,candidate,p0
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,100010.0_real32)

    p0=prior; prior%pressure%valid_time=VALID_TIME+1_int64
    CALL expect_reject(background,prior,candidate,result,budget, &
      'bad valid time')
    prior=p0

    p0=prior; prior%u%unit='bad-frame'; CALL expect_reject(background,prior,candidate, &
      result,budget,'bad wind frame metadata'); prior=p0

    p0=prior; prior%grid%dx(1,1)=prior%grid%dx(1,1)+1.0_real64
    CALL expect_reject(background,prior,candidate,result,budget,'bad geometry'); prior=p0

    p0=prior
    prior%temperature%valid(1,1,1)=.FALSE.
    prior%temperature%quality(1,1,1)=QUALITY_RAW_MISSING
    prior%temperature%source(1,1,1)=0_int32
    CALL expect_reject(background,prior,candidate,result,budget,'missing new-cell temperature'); prior=p0

    p0=prior
    prior%cloud_ice%valid(1,1,1)=.FALSE.
    prior%cloud_ice%quality(1,1,1)=QUALITY_RAW_MISSING
    prior%cloud_ice%source(1,1,1)=0_int32
    CALL expect_reject(background,prior,candidate,result,budget,'missing new-cell hydrometeor'); prior=p0

    p0=prior; prior%u%value(1,1,2)=prior%u%value(1,1,2)+1.0_real32
    CALL check(prior%u%value(1,1,2)/=background%u%value(1,1,2), &
      'unauthorized-wind fixture changes an old-active value')
    CALL expect_reject(background,prior,candidate,result,budget,'unauthorized old-cell wind change'); prior=p0

    p0=prior; prior%omega%source(1,1,1)=SOURCE_DYNAMIC_TARGET
    CALL expect_reject(background,prior,candidate,result,budget,'wind without target authority'); prior=p0

    background%balance_beta(1,1,1)=0.5_real32
    CALL expect_reject(background,prior,candidate,result,budget,'stale inactive wind-adjustment weight')
    background%balance_beta(1,1,1)=0.0_real32

    CALL make_background(background,94900.0_real32)
    CALL make_prior(background,prior,100010.0_real32)
    CALL expect_reject(background,prior,candidate,result,budget,'more than one center activates')

    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,94000.0_real32)
    CALL expect_reject(background,prior,candidate,result,budget,'unsupported center removal')
  END SUBROUTINE test_rejections

  SUBROUTINE expect_reject(background,prior,candidate,result,budget,label)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,prior
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(pressure_analysis_budget), INTENT(OUT) :: budget
    CHARACTER(LEN=*), INTENT(IN) :: label
    TYPE(cloud_bal_state_type) :: background_before,prior_before
    background_before=background; prior_before=prior
    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_FAILED,TRIM(label)//' rejects')
    CALL check(canonical_states_equal(candidate,background),TRIM(label)//' returns original candidate')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(prior,prior_before),TRIM(label)//' preserves inputs')
    CALL check(budget_zero(budget),TRIM(label)//' returns zero budget')
  END SUBROUTINE expect_reject

  SUBROUTINE make_background(state,surface_pressure)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), INTENT(IN) :: surface_pressure
    INTEGER :: status,k,reason
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME,'domain-transition',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization'
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    state%pressure%value(1,1,:)=REAL(P,real32); state%pressure%value(2,1,:)=REAL(P,real32)
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value(1,1)=surface_pressure
    state%surface_pressure%value(2,1)=99999.125_real32
    state%surface_temperature%value=290.0_real32; state%surface_vapor%value=0.006_real32
    state%surface_height%value=120.0_real32
    CALL valid_surface(state%surface_pressure); CALL valid_surface(state%surface_temperature)
    CALL valid_surface(state%surface_vapor); CALL valid_surface(state%surface_height)
    CALL configure_pressure_geometry(state,status); IF (status/=STATUS_OK) ERROR STOP 'geometry'
    DO k=1,NZ
      CALL fill_cell(state,1,1,k,280.0_real32+REAL(k,real32),0.008_real32+0.001_real32*REAL(k,real32), &
        2.0_real32,-1.0_real32,0.0_real32,state%above_ground(1,1,k),SOURCE_BACKGROUND_MODEL)
      CALL fill_cell(state,2,1,k,279.0_real32+REAL(k,real32),0.0075_real32+0.001_real32*REAL(k,real32), &
        3.0_real32,-2.0_real32,0.0_real32,state%above_ground(2,1,k),SOURCE_BACKGROUND_MODEL)
    END DO
    CALL refresh_dry_air_mass_measure(state,status); IF (status/=STATUS_OK) ERROR STOP 'dry mass'
    CALL set_phi(state,1,1); CALL set_phi(state,2,1)
    CALL validate_canonical_state(state,.FALSE.,.TRUE.,status,reason)
    IF (status==STATUS_FAILED) ERROR STOP 'background is not canonical'
  END SUBROUTINE make_background

  SUBROUTINE make_prior(background,prior,target_pressure,all_columns)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(cloud_bal_state_type), INTENT(OUT) :: prior
    REAL(real32), INTENT(IN) :: target_pressure
    LOGICAL, INTENT(IN), OPTIONAL :: all_columns
    LOGICAL :: target_all
    INTEGER :: status,reason,k,i
    target_all=.FALSE.; IF (PRESENT(all_columns)) target_all=all_columns
    prior=background
    prior%surface_pressure%value(1,1)=target_pressure
    IF (target_all) prior%surface_pressure%value(2,1)=target_pressure
    CALL configure_pressure_geometry(prior,status); IF (status/=STATUS_OK) ERROR STOP 'prior geometry'
    DO i=1,NX
      IF (.NOT.target_all .AND. i/=1) CYCLE
      DO k=1,NZ
        IF (.NOT.prior%above_ground(i,1,k) .OR. background%above_ground(i,1,k)) CYCLE
        CALL fill_cell(prior,i,1,k,300.0_real32+10.0_real32*REAL(i-1,real32)+ &
          REAL(k-1,real32),0.018_real32+0.004_real32*REAL(i-1,real32), &
          6.0_real32+2.0_real32*REAL(i-1,real32),-4.0_real32,0.25_real32,.TRUE.,SOURCE_COLUMN_PHYSICS)
      END DO
      IF (prior%above_ground(i,1,1) .AND. .NOT.background%above_ground(i,1,1)) THEN
        prior%cloud_water%value(i,1,1)=0.006_real32+0.001_real32*REAL(i-1,real32)
        prior%cloud_ice%value(i,1,1)=0.002_real32; prior%rain%value(i,1,1)=0.001_real32
        prior%snow%value(i,1,1)=0.0015_real32; prior%graupel%value(i,1,1)=0.0005_real32
      END IF
    END DO
    CALL refresh_dry_air_mass_measure(prior,status); IF (status/=STATUS_OK) ERROR STOP 'prior dry mass'
    DO i=1,NX
      IF (.NOT.target_all .AND. i/=1) CYCLE
      CALL set_phi(prior,i,1)
      DO k=1,NZ
        IF (.NOT.background%above_ground(i,1,k)) CYCLE
        prior%geopotential%value(i,1,k)=background%geopotential%value(i,1,k)
        prior%geopotential%valid(i,1,k)=background%geopotential%valid(i,1,k)
        prior%geopotential%quality(i,1,k)=background%geopotential%quality(i,1,k)
        prior%geopotential%source(i,1,k)=background%geopotential%source(i,1,k)
      END DO
    END DO
    CALL validate_canonical_state(prior,.FALSE.,.TRUE.,status,reason)
    IF (status==STATUS_FAILED) ERROR STOP 'prior is not canonical'
  END SUBROUTINE make_prior

  SUBROUTINE fill_cell(state,i,j,k,t,qv,u,v,om,active,source)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real32), INTENT(IN) :: t,qv,u,v,om
    LOGICAL, INTENT(IN) :: active
    INTEGER(int32), INTENT(IN) :: source
    IF (.NOT.active) RETURN
    state%temperature%value(i,j,k)=t; state%vapor%value(i,j,k)=qv
    state%cloud_water%value(i,j,k)=0.003_real32; state%cloud_ice%value(i,j,k)=0.001_real32
    state%rain%value(i,j,k)=0.002_real32; state%snow%value(i,j,k)=0.001_real32
    state%graupel%value(i,j,k)=0.001_real32
    state%u%value(i,j,k)=u; state%v%value(i,j,k)=v; state%omega%value(i,j,k)=om
    CALL mark_valid(state%temperature,i,j,k,source); CALL mark_valid(state%vapor,i,j,k,source)
    CALL mark_valid(state%cloud_water,i,j,k,source); CALL mark_valid(state%cloud_ice,i,j,k,source)
    CALL mark_valid(state%rain,i,j,k,source); CALL mark_valid(state%snow,i,j,k,source)
    CALL mark_valid(state%graupel,i,j,k,source); CALL mark_valid(state%u,i,j,k,source)
    CALL mark_valid(state%v,i,j,k,source); CALL mark_valid(state%omega,i,j,k,source)
  END SUBROUTINE fill_cell

  SUBROUTINE mark_valid(field,i,j,k,source)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    INTEGER(int32), INTENT(IN) :: source
    field%valid(i,j,k)=.TRUE.; field%quality(i,j,k)=0_int32; field%source(i,j,k)=source
  END SUBROUTINE mark_valid

  SUBROUTINE valid_real(field,source)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE valid_surface(field)
    USE cloud_bal_state, ONLY: field2d
    TYPE(field2d), INTENT(INOUT) :: field
    field%valid=.TRUE.; field%quality=0_int32; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE valid_surface

  SUBROUTINE set_phi(state,i,j)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j
    REAL(real64) :: h(NZ)
    INTEGER :: k
    CALL hydro_profile(state,i,j,h)
    DO k=1,NZ
      IF (.NOT.state%above_ground(i,j,k)) CYCLE
      state%geopotential%value(i,j,k)=REAL(h(k)+42.0_real64,real32)
      CALL mark_valid(state%geopotential,i,j,k,SOURCE_BACKGROUND_MODEL)
    END DO
  END SUBROUTINE set_phi

  SUBROUTINE hydro_profile(state,i,j,h)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j
    REAL(real64), INTENT(OUT) :: h(NZ)
    REAL(real64) :: alpha(NZ),surface_q(6),surface_alpha,q(6)
    INTEGER :: bottom,k
    h=0.0_real64; bottom=FINDLOC(state%above_ground(i,j,:),.TRUE.,DIM=1)
    surface_q=0.0_real64; surface_q(1)=REAL(state%surface_vapor%value(i,j),real64)
    surface_alpha=RD*REAL(state%surface_temperature%value(i,j),real64)* &
      (1.0_real64+surface_q(1)/EPSW)/(1.0_real64+surface_q(1))
    DO k=bottom,NZ
      q=species(state,i,j,k)
      alpha(k)=RD*REAL(state%temperature%value(i,j,k),real64)* &
        (1.0_real64+q(1)/EPSW) / (1.0_real64+SUM(q))
    END DO
    h(bottom)=G*REAL(state%surface_height%value(i,j),real64)+0.5_real64* &
      (surface_alpha+alpha(bottom))*LOG(REAL(state%surface_pressure%value(i,j),real64)/ &
      REAL(state%pressure%value(i,j,bottom),real64))
    DO k=bottom+1,NZ
      h(k)=h(k-1)+0.5_real64*(alpha(k-1)+alpha(k))* &
        LOG(REAL(state%pressure%value(i,j,k-1),real64)/REAL(state%pressure%value(i,j,k),real64))
    END DO
  END SUBROUTINE hydro_profile

  SUBROUTINE expected_remap(prior,column,old_m,old_t,old_q,new_i,mass,t,species_out)
    TYPE(cloud_bal_state_type), INTENT(IN) :: prior
    INTEGER, INTENT(IN) :: column
    REAL(real64), INTENT(IN) :: old_m(2),old_t(2),old_q(6,2),new_i(4)
    REAL(real64), INTENT(OUT) :: mass(3),t(3),species_out(6,3)
    REAL(real64) :: oi(4),om(3),ot(3),oq(6,3),overlap,width,dm,water(6),moment,capacity
    INTEGER :: j,k
    oi=[100010.0_real64,99999.125_real64,92500.0_real64,87500.0_real64]
    om(1)=prior%grid%dx(column,1)*prior%grid%dy(column,1)*10.875_real64/G / &
      (1.0_real64+SUM(species(prior,column,1,1)))
    om(2:3)=old_m; ot(1)=REAL(prior%temperature%value(column,1,1),real64); ot(2:3)=old_t
    oq(:,1)=species(prior,column,1,1); oq(:,2:3)=old_q
    DO j=1,3
      mass(j)=0.0_real64; water=0.0_real64; moment=0.0_real64
      DO k=1,3
        overlap=MIN(oi(k),new_i(j))-MAX(oi(k+1),new_i(j+1)); IF (overlap<=0.0_real64) CYCLE
        width=oi(k)-oi(k+1); dm=overlap/width*om(k)
        mass(j)=mass(j)+dm; water=water+dm*oq(:,k)
        capacity=1004.5_real64+SUM(CP*oq(:,k)); moment=moment+dm*capacity*ot(k)
      END DO
      species_out(:,j)=water/mass(j); capacity=1004.5_real64+SUM(CP*species_out(:,j))
      t(j)=moment/(mass(j)*capacity)
    END DO
  END SUBROUTINE expected_remap

  PURE FUNCTION species(state,i,j,k) RESULT(q)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: q(6)
    q=[REAL(state%vapor%value(i,j,k),real64),REAL(state%cloud_water%value(i,j,k),real64), &
      REAL(state%cloud_ice%value(i,j,k),real64),REAL(state%rain%value(i,j,k),real64), &
      REAL(state%snow%value(i,j,k),real64),REAL(state%graupel%value(i,j,k),real64)]
  END FUNCTION species

  PURE ELEMENTAL INTEGER(int32) FUNCTION real32_bits(value)
    REAL(real32), INTENT(IN) :: value
    real32_bits=TRANSFER(value,real32_bits)
  END FUNCTION real32_bits

  PURE REAL(real64) FUNCTION mixture_enthalpy(t,q)
    REAL(real64), INTENT(IN) :: t,q(6)
    mixture_enthalpy=(1004.5_real64+SUM(CP*q))*(t-273.15_real64)+SUM(H0*q)
  END FUNCTION mixture_enthalpy

  LOGICAL FUNCTION untouched_column_equal(left,right)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    untouched_column_equal=ALL(real32_bits(left%temperature%value(2,1,:))== &
      real32_bits(right%temperature%value(2,1,:))) .AND. &
      ALL(real32_bits(left%vapor%value(2,1,:))==real32_bits(right%vapor%value(2,1,:))) .AND. &
      ALL(left%temperature%valid(2,1,:).EQV.right%temperature%valid(2,1,:)) .AND. &
      ALL(real32_bits(left%cloud_water%value(2,1,:))==real32_bits(right%cloud_water%value(2,1,:))) .AND. &
      ALL(real32_bits(left%cloud_ice%value(2,1,:))==real32_bits(right%cloud_ice%value(2,1,:))) .AND. &
      ALL(real32_bits(left%rain%value(2,1,:))==real32_bits(right%rain%value(2,1,:))) .AND. &
      ALL(real32_bits(left%snow%value(2,1,:))==real32_bits(right%snow%value(2,1,:))) .AND. &
      ALL(real32_bits(left%graupel%value(2,1,:))==real32_bits(right%graupel%value(2,1,:))) .AND. &
      ALL(real32_bits(left%u%value(2,1,:))==real32_bits(right%u%value(2,1,:))) .AND. &
      ALL(real32_bits(left%v%value(2,1,:))==real32_bits(right%v%value(2,1,:))) .AND. &
      ALL(real32_bits(left%omega%value(2,1,:))==real32_bits(right%omega%value(2,1,:))) .AND. &
      ALL(real32_bits(left%geopotential%value(2,1,:))==real32_bits(right%geopotential%value(2,1,:))) .AND. &
      ALL(left%grid%pressure_interface(2,1,:)==right%grid%pressure_interface(2,1,:)) .AND. &
      ALL(left%grid%cell_dp(2,1,:)==right%grid%cell_dp(2,1,:)) .AND. &
      ALL(left%grid%pressure_mass_measure(2,1,:)==right%grid%pressure_mass_measure(2,1,:)) .AND. &
      ALL(left%grid%dry_air_mass_measure(2,1,:)==right%grid%dry_air_mass_measure(2,1,:)) .AND. &
      left%surface_pressure%value(2,1)==right%surface_pressure%value(2,1)
  END FUNCTION untouched_column_equal

  LOGICAL FUNCTION budget_zero(budget)
    TYPE(pressure_analysis_budget), INTENT(IN) :: budget
    budget_zero=ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64 .AND. budget%accounted_cells==0_int64
  END FUNCTION budget_zero

  SUBROUTINE write_reference_fixture(path)
    CHARACTER(*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type) :: background,prior,candidate
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: unit,ios,status

    OPEN(NEWUNIT=unit,FILE=path,STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) ERROR STOP 'open pressure transition fixture'
    WRITE(unit,'(A)') 'FORMAT SURFACE_PRESSURE_REFERENCE_FIXTURE_V1'

    ! Positive same-domain thickening: the old bottom center remains active.
    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,99999.5_real32)
    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    status=result%status
    CALL write_reference_case(unit,'same_domain',background,prior,candidate,status,1)

    ! Positive one-center activation: the prior contributes a new bottom cell.
    CALL make_background(background,99999.125_real32)
    CALL make_prior(background,prior,100010.0_real32)
    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    status=result%status
    CALL write_reference_case(unit,'one_center',background,prior,candidate,status,1)

    CLOSE(unit)
  END SUBROUTINE write_reference_fixture

  SUBROUTINE write_reference_case(unit,name,background,prior,candidate,status,column)
    INTEGER, INTENT(IN) :: unit,status,column
    CHARACTER(*), INTENT(IN) :: name
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,prior,candidate
    REAL(real64), ALLOCATABLE :: old_interfaces(:),new_interfaces(:),old_mass(:)
    REAL(real64), ALLOCATABLE :: old_temperature(:),old_species(:,:),boundary_species(:)
    REAL(real64), ALLOCATABLE :: final_mass(:),final_temperature(:),final_species(:,:)
    REAL(real64), ALLOCATABLE :: pressure(:),old_phi(:),prior_phi(:),final_phi(:)
    REAL(real64), ALLOCATABLE :: prior_temperature(:),prior_species(:,:)
    REAL(real64) :: boundary_temperature,area,old_surface_pressure,new_surface_pressure
    REAL(real64) :: surface_temperature,surface_vapor,surface_height
    REAL(real64) :: seed_geopotential,seed_temperature,seed_species(6)
    INTEGER :: bottom,prior_bottom,nold,nnew,k

    bottom=FINDLOC(background%above_ground(column,1,:),.TRUE.,DIM=1)
    prior_bottom=FINDLOC(prior%above_ground(column,1,:),.TRUE.,DIM=1)
    nold=SIZE(background%grid%pressure_interface(column,1,bottom:nz+1))-1
    nnew=SIZE(prior%grid%pressure_interface(column,1,prior_bottom:nz+1))-1
    ALLOCATE(old_interfaces(nold+1),new_interfaces(nnew+1),old_mass(nold), &
      old_temperature(nold),old_species(6,nold),boundary_species(6), &
      final_mass(nnew),final_temperature(nnew),final_species(6,nnew), &
      pressure(nnew),old_phi(nold),prior_phi(nnew),final_phi(nnew), &
      prior_temperature(nnew),prior_species(6,nnew))

    old_interfaces=background%grid%pressure_interface(column,1,bottom:nz+1)
    new_interfaces=prior%grid%pressure_interface(column,1,prior_bottom:nz+1)
    DO k=1,nold
      old_mass(k)=background%grid%dry_air_mass_measure(column,1,bottom+k-1)
      old_temperature(k)=REAL(background%temperature%value(column,1,bottom+k-1),real64)
      old_species(:,k)=species(background,column,1,bottom+k-1)
    END DO
    boundary_temperature=REAL(prior%temperature%value(column,1,prior_bottom),real64)
    boundary_species=species(prior,column,1,prior_bottom)
    area=prior%grid%dx(column,1)*prior%grid%dy(column,1)
    DO k=1,nnew
      pressure(k)=REAL(candidate%pressure%value(column,1,prior_bottom+k-1),real64)
      prior_phi(k)=REAL(prior%geopotential%value(column,1,prior_bottom+k-1),real64)
      prior_temperature(k)=REAL(prior%temperature%value(column,1,prior_bottom+k-1),real64)
      prior_species(:,k)=species(prior,column,1,prior_bottom+k-1)
      final_mass(k)=candidate%grid%dry_air_mass_measure(column,1,prior_bottom+k-1)
      final_temperature(k)=REAL(candidate%temperature%value(column,1,prior_bottom+k-1),real64)
      final_species(:,k)=species(candidate,column,1,prior_bottom+k-1)
      final_phi(k)=REAL(candidate%geopotential%value(column,1,prior_bottom+k-1),real64)
    END DO
    DO k=1,nold
      old_phi(k)=REAL(background%geopotential%value(column,1,bottom+k-1),real64)
    END DO
    surface_temperature=REAL(candidate%surface_temperature%value(column,1),real64)
    surface_vapor=REAL(candidate%surface_vapor%value(column,1),real64)
    surface_height=REAL(candidate%surface_height%value(column,1),real64)
    old_surface_pressure=REAL(background%surface_pressure%value(column,1),real64)
    new_surface_pressure=REAL(prior%surface_pressure%value(column,1),real64)

    WRITE(unit,'(A,1X,A)') 'CASE',TRIM(name)
    CALL write_vector(unit,'OLD_INTERFACES',old_interfaces)
    CALL write_vector(unit,'NEW_INTERFACES',new_interfaces)
    CALL write_vector(unit,'OLD_DRY_MASS',old_mass)
    CALL write_vector(unit,'OLD_TEMPERATURE',old_temperature)
    CALL write_matrix(unit,'OLD_SPECIES',old_species)
    WRITE(unit,'(A,1X,ES24.16)') 'BOUNDARY_TEMPERATURE',boundary_temperature
    CALL write_vector(unit,'BOUNDARY_SPECIES',boundary_species)
    WRITE(unit,'(A,1X,ES24.16)') 'AREA',area
    WRITE(unit,'(A,1X,I0)') 'RESULT',status
    CALL write_vector(unit,'FINAL_DRY_MASS',final_mass)
    CALL write_vector(unit,'FINAL_TEMPERATURE',final_temperature)
    CALL write_matrix(unit,'FINAL_SPECIES',final_species)
    CALL write_vector(unit,'PRESSURE_CENTERS',pressure)
    CALL write_vector(unit,'OLD_GEOPOTENTIAL',old_phi)
    CALL write_vector(unit,'PRIOR_GEOPOTENTIAL',prior_phi)
    CALL write_vector(unit,'FINAL_GEOPOTENTIAL',final_phi)
    CALL write_vector(unit,'PRIOR_TEMPERATURE',prior_temperature)
    CALL write_matrix(unit,'PRIOR_SPECIES',prior_species)
    WRITE(unit,'(A,1X,ES24.16)') 'OLD_SURFACE_PRESSURE',old_surface_pressure
    WRITE(unit,'(A,1X,ES24.16)') 'NEW_SURFACE_PRESSURE',new_surface_pressure
    WRITE(unit,'(A,1X,ES24.16)') 'SURFACE_TEMPERATURE',surface_temperature
    WRITE(unit,'(A,1X,ES24.16)') 'SURFACE_VAPOR',surface_vapor
    WRITE(unit,'(A,1X,ES24.16)') 'SURFACE_HEIGHT',surface_height
    IF (nnew==nold+1) THEN
      seed_geopotential=prior_phi(1)
      seed_temperature=prior_temperature(1)
      seed_species=prior_species(:,1)
      WRITE(unit,'(A,1X,ES24.16)') 'SEED_GEOPOTENTIAL',seed_geopotential
      WRITE(unit,'(A,1X,ES24.16)') 'SEED_TEMPERATURE',seed_temperature
      CALL write_vector(unit,'SEED_SPECIES',seed_species)
    END IF
    WRITE(unit,'(A)') 'ENDCASE'
    DEALLOCATE(old_interfaces,new_interfaces,old_mass,old_temperature,old_species, &
      boundary_species,final_mass,final_temperature,final_species,pressure,old_phi, &
      prior_phi,final_phi,prior_temperature,prior_species)
  END SUBROUTINE write_reference_case

  SUBROUTINE write_vector(unit,label,values)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: values(:)
    WRITE(unit,'(A,1X,I0,1X,100(ES24.16,1X))') TRIM(label),SIZE(values),values
  END SUBROUTINE write_vector

  SUBROUTINE write_matrix(unit,label,values)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: values(:,:)
    WRITE(unit,'(A,1X,2(I0,1X),100(ES24.16,1X))') TRIM(label), &
      SIZE(values,1),SIZE(values,2),values
  END SUBROUTINE write_matrix

END PROGRAM test_pressure_domain_transition
