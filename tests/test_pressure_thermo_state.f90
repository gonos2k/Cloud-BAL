PROGRAM test_pressure_thermo_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: water_phase_budget, &
    saturation_adjust_pressure_state, &
    SATURATION_LIQUID,SATURATION_ICE
  IMPLICIT NONE

  REAL(real64), PARAMETER :: T0=273.15_real64,CP0=1004.5_real64
  REAL(real64), PARAMETER :: SPECIES_CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
                                            4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: SPECIES_H0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
                                             0.0_real64,-3.50e5_real64,-3.50e5_real64]
  INTEGER :: failures

  failures=0
  CALL test_constructed_roots(failures)
  CALL test_precipitation_heat_capacity(failures)
  CALL test_noop_and_missing(failures)
  CALL test_rejections_and_rollback(failures)
  IF (failures/=0) THEN
    PRINT *,'Pressure thermo-state tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Pressure thermo-state tests passed'

CONTAINS

  SUBROUTINE check(ok,message,failures)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.ok) THEN
      failures=failures+1; PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE near(actual,expected,atol,rtol,message,failures)
    REAL(real64), INTENT(IN) :: actual,expected,atol,rtol
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(ABS(actual-expected)<=atol+rtol*MAX(ABS(actual),ABS(expected)), &
               message,failures)
  END SUBROUTINE near

  SUBROUTINE test_constructed_roots(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,snapshot,restored
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2)
    INTEGER :: surface(3,1,2),status

    CALL make_state(input)
    CALL construct_root(input,1,1,1,SATURATION_LIQUID,310.0_real64,0.0015_real64,.TRUE.)
    CALL construct_root(input,2,1,1,SATURATION_LIQUID,300.0_real64,0.0020_real64,.FALSE.)
    CALL construct_root(input,3,1,1,SATURATION_ICE,250.0_real64,0.0005_real64,.FALSE.)
    CALL refresh_dry_air_mass_measure(input,status)
    CALL check(status==STATUS_OK,'constructed full-mixture state is canonical',failures)
    active=.FALSE.; active(:,1,1)=.TRUE.; surface=99
    surface(1,1,1)=SATURATION_LIQUID; surface(2,1,1)=SATURATION_LIQUID
    surface(3,1,1)=SATURATION_ICE; snapshot=input
    CALL saturation_adjust_pressure_state(input,output,result,active,1.0_real64,budget,surface)
    CALL check(result%status==STATUS_OK,'constructed full-mixture roots succeed',failures)
    CALL check(result%reason_code==REASON_NONE .AND. ALL(result%changed .EQV. active), &
      'successful roots publish status and changed mask',failures)
    CALL check(canonical_states_equal(input,snapshot),'input is unchanged by root transaction',failures)
    CALL check_root(input,output,1,1,1,SATURATION_LIQUID,310.0_real64,failures)
    CALL check_root(input,output,2,1,1,SATURATION_LIQUID,300.0_real64,failures)
    CALL check_root(input,output,3,1,1,SATURATION_ICE,250.0_real64,failures)
    CALL check_budget(input,output,active,budget,failures)
    CALL check_sources(input,output,active,failures)

    restored=output
    restored%temperature%value=input%temperature%value
    restored%vapor%value=input%vapor%value
    restored%cloud_water%value=input%cloud_water%value
    restored%cloud_ice%value=input%cloud_ice%value
    restored%rain%value=input%rain%value
    restored%snow%value=input%snow%value
    restored%graupel%value=input%graupel%value
    restored%temperature%source=input%temperature%source
    restored%vapor%source=input%vapor%source
    restored%cloud_water%source=input%cloud_water%source
    restored%cloud_ice%source=input%cloud_ice%source
    restored%rain%source=input%rain%source
    restored%snow%source=input%snow%source
    restored%graupel%source=input%graupel%source
    CALL check(canonical_states_equal(restored,input), &
      'only seven thermo values and provenance changed',failures)
    CALL check(ALL(output%obs_support==input%obs_support) .AND. &
      ALL(output%hydro_support==input%hydro_support) .AND. &
      ALL(output%balance_beta==input%balance_beta), &
      'support arrays are copied exactly',failures)
    CALL check(ALL(real32_bits(output%u%value)==real32_bits(input%u%value)) .AND. &
      ALL(real32_bits(output%v%value)==real32_bits(input%v%value)) .AND. &
      ALL(real32_bits(output%omega%value)==real32_bits(input%omega%value)), &
      'winds and omega are bit-preserved',failures)
  END SUBROUTINE test_constructed_roots

  SUBROUTINE test_precipitation_heat_capacity(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,saturation
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2)
    INTEGER :: surface(3,1,2),status
    REAL(real64) :: before(6),after(6)
    REAL(real64) :: final_t,transfer,qstar,full_initial,no_precip_initial

    CALL make_state(input)
    input%rain%value(1,1,1)=0.030_real32
    input%snow%value(1,1,1)=0.020_real32
    input%graupel%value(1,1,1)=0.010_real32
    final_t=305.0_real64; transfer=0.001_real64; qstar=liquid_qsat(final_t,85000.0_real64)
    input%vapor%value(1,1,1)=REAL(qstar+transfer,real32)
    before=cell_species(input,1,1,1); after=before
    after(1)=qstar; after(2)=after(2)+before(1)-qstar
    full_initial=root_temperature(after,before,final_t)
    no_precip_initial=T0+( (CP0+SUM(SPECIES_CP(1:3)*after(1:3)))*(final_t-T0) + &
      SUM(SPECIES_H0(1:3)*(after(1:3)-before(1:3))) ) / &
      (CP0+SUM(SPECIES_CP(1:3)*before(1:3)))
    input%temperature%value(1,1,1)=REAL(full_initial,real32)
    CALL refresh_dry_air_mass_measure(input,status)
    CALL check(status==STATUS_OK .AND. ABS(full_initial-no_precip_initial)>1.0e-3_real64, &
      'nonzero precipitation heat capacity changes the constructed root',failures)
    active=.FALSE.; active(1,1,1)=.TRUE.; surface=99; surface(1,1,1)=SATURATION_LIQUID
    CALL saturation_adjust_pressure_state(input,saturation,result,active,1.0_real64,budget,surface)
    CALL check(result%status==STATUS_OK,'precipitation heat-capacity root succeeds',failures)
    CALL check_root(input,saturation,1,1,1,SATURATION_LIQUID,final_t,failures)
    before=cell_species(input,1,1,1); after=cell_species(saturation,1,1,1)
    CALL check(ALL(ABS(after(4:6)-before(4:6))==0.0_real64), &
      'nonzero precipitation heat capacity species remain unchanged',failures)
    CALL check(ALL(ABS(budget%species_change_kg(4:6))<=1.0e-8_real64), &
      'unchanged precipitation has zero published budget increment',failures)
  END SUBROUTINE test_precipitation_heat_capacity

  SUBROUTINE test_noop_and_missing(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,before
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2)
    INTEGER :: surface(3,1,2),status

    CALL make_state(input); before=input; active=.FALSE.; surface=99
    CALL saturation_adjust_pressure_state(input,output,result,active,0.8_real64,budget,surface)
    CALL check(result%status==STATUS_OK .AND. .NOT.ANY(result%changed), &
      'empty mask is an exact no-op',failures)
    CALL check_zero_budget(budget,'empty mask has zero budget',failures)
    CALL check(canonical_states_equal(output,before),'empty mask preserves state',failures)

    CALL make_state(input)
    input%rain%value(3,1,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    input%rain%valid(3,1,2)=.FALSE.; input%rain%quality(3,1,2)=QUALITY_RAW_MISSING
    input%rain%source(3,1,2)=0_int32
    CALL construct_root(input,1,1,1,SATURATION_LIQUID,305.0_real64,0.001_real64,.TRUE.)
    CALL refresh_dry_air_mass_measure(input,status)
    active=.FALSE.; active(1,1,1)=.TRUE.
    surface=99; surface(1,1,1)=SATURATION_LIQUID
    CALL saturation_adjust_pressure_state(input,output,result,active,1.0_real64,budget,surface)
    CALL check(result%status==STATUS_OK,'inactive missing precipitation is ignored',failures)
    CALL check(real32_bits(output%rain%value(3,1,2))==real32_bits(input%rain%value(3,1,2)) .AND. &
      .NOT.output%rain%valid(3,1,2),'inactive missing NaN is bit-preserved',failures)
  END SUBROUTINE test_noop_and_missing

  SUBROUTINE test_rejections_and_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    TYPE(cloud_bal_state_type) :: output,before
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2),bad_shape(1,1,1)
    INTEGER :: surface(3,1,2),bad_surface(1,1,1),status,species,reason

    active=.FALSE.; active(1,1,1)=.TRUE.; surface=99; surface(1,1,1)=SATURATION_LIQUID
    DO species=1,5
      CALL make_state(state)
      SELECT CASE(species)
      CASE(1); CALL invalidate_water_cell(state%cloud_water,1,1,1)
      CASE(2); CALL invalidate_water_cell(state%cloud_ice,1,1,1)
      CASE(3); CALL invalidate_water_cell(state%rain,1,1,1)
      CASE(4); CALL invalidate_water_cell(state%snow,1,1,1)
      CASE(5); CALL invalidate_water_cell(state%graupel,1,1,1)
      END SELECT
      CALL refresh_dry_air_mass_measure(state,status)
      CALL check(status==STATUS_OK,'missing-species fixture mass remains canonical',failures)
      before=state
      CALL saturation_adjust_pressure_state(state,output,result,active,1.0_real64,budget,surface)
      CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_REQUIRED_COVERAGE, &
        'selected missing species rejects',failures)
      CALL check(.NOT.ANY(result%changed), 'missing species has no changed cells',failures)
      CALL check_zero_budget(budget,'missing species has zero budget',failures)
      CALL check(canonical_states_equal(output,before),'missing species rolls back',failures)
    END DO

    CALL make_state(state); state%temperature%value(1,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL expect_rejection(state,active,surface,'NaN selected temperature rejects',failures,REASON_NONFINITE)
    CALL make_state(state); state%cloud_water%value(1,1,1)=-1.0e-4_real32
    CALL expect_rejection(state,active,surface,'negative selected cloud rejects',failures)
    CALL make_state(state); state%pressure%unit='hPa'
    CALL expect_rejection(state,active,surface,'wrong pressure metadata rejects',failures)
    CALL make_state(state); state%grid%dry_air_mass_measure(1,1,1)= &
      state%grid%dry_air_mass_measure(1,1,1)+10000.0_real64
    CALL expect_rejection(state,active,surface,'inconsistent frozen dry mass rejects',failures,REASON_METADATA)
    CALL make_state(state); CALL expect_rejection(state,active,surface, &
      'NaN target RH rejects',failures,REASON_RANGE,ieee_value(0.0_real64,ieee_quiet_nan))
    surface(1,1,1)=99
    CALL expect_rejection(state,active,surface,'unknown selected surface rejects',failures,REASON_RANGE)
    surface(1,1,1)=SATURATION_LIQUID
    CALL invalidate_water_cell(state%vapor,1,1,1)
    CALL expect_rejection(state,active,surface,'missing required vapor rejects',failures)
    CALL make_state(state); CALL expect_rejection(state,active,surface, &
      'negative target RH rejects',failures,REASON_RANGE,-0.1_real64)
    CALL make_state(state); CALL expect_rejection(state,active,surface, &
      'target RH above one rejects',failures,REASON_RANGE,1.1_real64)

    CALL make_state(state); bad_shape=.TRUE.; before=state
    CALL saturation_adjust_pressure_state(state,output,result,bad_shape,1.0_real64,budget,surface)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
      'mask shape mismatch rejects atomically',failures)
    CALL check(canonical_states_equal(output,before),'shape mismatch rolls back',failures)
    CALL check_zero_budget(budget,'shape mismatch has zero budget',failures)

    bad_surface=SATURATION_LIQUID
    CALL saturation_adjust_pressure_state(state,output,result,active,1.0_real64,budget,bad_surface)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
      'surface shape mismatch rejects',failures)
    CALL check(canonical_states_equal(output,before),'surface shape mismatch rolls back',failures)
    CALL check_zero_budget(budget,'surface shape mismatch has zero budget',failures)

    CALL make_state(state)
    state%surface_pressure%value=75000.0_real32
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_OK,'below-ground fixture geometry',failures)
    WHERE (.NOT.state%above_ground)
      state%obs_support=0_int32; state%hydro_support=0_int32; state%balance_beta=0.0_real32
      state%omega_target%valid=.FALSE.
      state%omega_target%quality=QUALITY_RAW_MISSING; state%omega_target%source=0_int32
    END WHERE
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_OK .AND. .NOT.state%above_ground(1,1,1), &
      'selected below-ground cell is outside pressure domain',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    CALL check(status==STATUS_OK,'below-ground rejection starts from a canonical state',failures)
    CALL expect_rejection(state,active,surface,'below-ground support rejects',failures,REASON_RANGE)

    ! A valid liquid cell precedes an ice cell whose warm input violates the
    ! explicit ICE policy; the first candidate must not leak through failure.
    CALL make_state(state); active=.FALSE.; active(1,1,1)=.TRUE.; active(2,1,1)=.TRUE.
    surface=99; surface(1,1,1)=SATURATION_LIQUID; surface(2,1,1)=SATURATION_ICE
    CALL construct_root(state,1,1,1,SATURATION_LIQUID,305.0_real64,0.001_real64,.TRUE.)
    state%temperature%value(2,1,1)=280.0_real32; state%vapor%value(2,1,1)=0.01_real32
    CALL refresh_dry_air_mass_measure(state,status); before=state
    CALL saturation_adjust_pressure_state(state,output,result,active,1.0_real64,budget,surface)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SOLVER, &
      'later ice-policy solver failure rejects',failures)
    CALL check(canonical_states_equal(output,before),'later failure rolls back earlier candidate',failures)
    CALL check_zero_budget(budget,'later failure has zero budget',failures)

    ! The same later cell has an allowed cold input but needs sublimation
    ! below 150 K. This exercises the bounded root, not the warm-ice guard.
    state%temperature%value(2,1,1)=150.0_real32
    state%vapor%value(2,1,1)=0.0_real32
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_OK,'cold bound fixture mass is consistent',failures)
    CALL expect_rejection(state,active,surface,'later cold-root failure rolls back',failures,REASON_SOLVER)
  END SUBROUTINE test_rejections_and_rollback

  SUBROUTINE expect_rejection(input,active,surface,message,failures,reason,target)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    LOGICAL, INTENT(IN) :: active(:,:,:)
    INTEGER, INTENT(IN) :: surface(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    INTEGER, INTENT(IN), OPTIONAL :: reason
    REAL(real64), INTENT(IN), OPTIONAL :: target
    TYPE(cloud_bal_state_type) :: output,before
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    REAL(real64) :: rh
    rh=1.0_real64; IF (PRESENT(target)) rh=target; before=input
    CALL saturation_adjust_pressure_state(input,output,result,active,rh,budget,surface)
    CALL check(result%status==STATUS_FAILED,message,failures)
    IF (PRESENT(reason)) CALL check(result%reason_code==reason,TRIM(message)//' reason',failures)
    CALL check(.NOT.ANY(result%changed),TRIM(message)//' has no changes',failures)
    CALL check_zero_budget(budget,TRIM(message)//' budget is zero',failures)
    CALL check(canonical_states_equal(output,before),TRIM(message)//' rolls back',failures)
  END SUBROUTINE expect_rejection

  SUBROUTINE check_root(input,output,i,j,k,surface,expected_t,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    INTEGER, INTENT(IN) :: i,j,k,surface
    REAL(real64), INTENT(IN) :: expected_t
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: p,t,qstar,before(6),after(6),hi,ho
    p=REAL(input%pressure%value(i,j,k),real64); t=REAL(output%temperature%value(i,j,k),real64)
    IF (surface==SATURATION_LIQUID) THEN; qstar=liquid_qsat(t,p); ELSE; qstar=ice_qsat(t,p); END IF
    CALL near(t,expected_t,8.0e-5_real64,3.0e-7_real64,'full-mixture root temperature',failures)
    CALL near(REAL(output%vapor%value(i,j,k),real64),qstar,1.0e-6_real64,4.0e-6_real64, &
      'saturation vapor oracle',failures)
    before=cell_species(input,i,j,k); after=cell_species(output,i,j,k)
    hi=mixture_h(REAL(input%temperature%value(i,j,k),real64),before)
    ho=mixture_h(t,after)
    CALL near(ho,hi,3.0e-2_real64,2.0e-11_real64,'full-mixture enthalpy closes',failures)
    CALL near(SUM(after-before),0.0_real64,3.0e-7_real64,1.0e-8_real64,'water closes',failures)
    IF (surface==SATURATION_ICE) CALL check(t<=T0+1.0e-4_real64,'ice policy stays below freezing',failures)
  END SUBROUTINE check_root

  SUBROUTINE check_budget(input,output,active,budget,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    LOGICAL, INTENT(IN) :: active(:,:,:)
    TYPE(water_phase_budget), INTENT(IN) :: budget
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: species(6),sensible,phase,before(6),after(6),change(6)
    REAL(real64) :: ti,tf,cp,mass,i_sensible,i_phase
    INTEGER :: i,j,k
    species=0.0_real64; sensible=0.0_real64; phase=0.0_real64
    DO k=1,SIZE(active,3); DO j=1,SIZE(active,2); DO i=1,SIZE(active,1)
      IF (.NOT.active(i,j,k)) CYCLE
      before=cell_species(input,i,j,k); after=cell_species(output,i,j,k); change=after-before
      mass=input%grid%dry_air_mass_measure(i,j,k); ti=REAL(input%temperature%value(i,j,k),real64)
      tf=REAL(output%temperature%value(i,j,k),real64); cp=CP0+SUM(SPECIES_CP*after)
      i_sensible=cp*(tf-ti); i_phase=SUM(change*(SPECIES_H0+SPECIES_CP*(ti-T0)))
      species=species+mass*change; sensible=sensible+mass*i_sensible; phase=phase+mass*i_phase
    END DO; END DO; END DO
    CALL check(ALL(ABS(budget%species_change_kg-species)<=1.0e-8_real64+ &
      2.0e-11_real64*MAX(ABS(budget%species_change_kg),ABS(species))), &
      'six-species budget uses final float32 state',failures)
    CALL near(budget%sensible_change_j,sensible,1.0e-5_real64,2.0e-11_real64, &
      'sensible budget uses final float32 Cp',failures)
    CALL near(budget%phase_change_j,phase,1.0e-5_real64,2.0e-11_real64, &
      'phase budget uses initial-temperature enthalpy',failures)
    CALL near(budget%water_error_kg,SUM(species),1.0e-8_real64,2.0e-11_real64,'water residual closes',failures)
    CALL near(budget%enthalpy_error_j,sensible+phase,1.0e-5_real64,2.0e-11_real64,'enthalpy residual closes',failures)
  END SUBROUTINE check_budget

  SUBROUTINE check_sources(input,output,active,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    LOGICAL, INTENT(IN) :: active(:,:,:)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: i,j,k
    DO k=1,SIZE(active,3); DO j=1,SIZE(active,2); DO i=1,SIZE(active,1)
      CALL one_source(input%temperature%value(i,j,k),output%temperature%value(i,j,k), &
        input%temperature%source(i,j,k),output%temperature%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%vapor%value(i,j,k),output%vapor%value(i,j,k), &
        input%vapor%source(i,j,k),output%vapor%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%cloud_water%value(i,j,k),output%cloud_water%value(i,j,k), &
        input%cloud_water%source(i,j,k),output%cloud_water%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%cloud_ice%value(i,j,k),output%cloud_ice%value(i,j,k), &
        input%cloud_ice%source(i,j,k),output%cloud_ice%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%rain%value(i,j,k),output%rain%value(i,j,k), &
        input%rain%source(i,j,k),output%rain%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%snow%value(i,j,k),output%snow%value(i,j,k), &
        input%snow%source(i,j,k),output%snow%source(i,j,k),active(i,j,k),failures)
      CALL one_source(input%graupel%value(i,j,k),output%graupel%value(i,j,k), &
        input%graupel%source(i,j,k),output%graupel%source(i,j,k),active(i,j,k),failures)
    END DO; END DO; END DO
  END SUBROUTINE check_sources

  SUBROUTINE one_source(before,after,source_before,source_after,selected,failures)
    REAL(real32), INTENT(IN) :: before,after
    INTEGER(int32), INTENT(IN) :: source_before,source_after
    LOGICAL, INTENT(IN) :: selected
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.selected .OR. real32_bits(before)==real32_bits(after)) THEN
      CALL check(source_after==source_before,'unchanged field source is preserved',failures)
    ELSE
      CALL check(source_after==IOR(source_before,SOURCE_COLUMN_PHYSICS),'changed field source is marked',failures)
    END IF
  END SUBROUTINE one_source

  SUBROUTINE check_zero_budget(budget,message,failures)
    TYPE(water_phase_budget), INTENT(IN) :: budget
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(ALL(budget%species_change_kg==0.0_real64) .AND. budget%sensible_change_j==0.0_real64 .AND. &
      budget%phase_change_j==0.0_real64 .AND. budget%water_error_kg==0.0_real64 .AND. &
      budget%enthalpy_error_j==0.0_real64,message,failures)
  END SUBROUTINE check_zero_budget

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER(int64), PARAMETER :: vt=1788224400_int64
    INTEGER :: i,j,k,status,reason
    CALL initialize_cloud_bal_state(state,3,1,2,vt,'pressure-thermo-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    DO k=1,2; DO j=1,1; DO i=1,3
      state%pressure%value(i,j,k)=REAL(MERGE(85000.0_real64,65000.0_real64,k==1),real32)
      state%temperature%value(i,j,k)=280.0_real32; state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=2.0_real32; state%v%value(i,j,k)=-1.0_real32
      state%omega%value(i,j,k)=0.2_real32; state%omega_target%value(i,j,k)=0.3_real32
      state%geopotential%value(i,j,k)=100.0_real32; state%cloud_fraction%value(i,j,k)=0.2_real32
      state%radar_reflectivity%value(i,j,k)=10.0_real32; state%cloud_type%value(i,j,k)=1_int32
      state%precipitation_phase%value(i,j,k)=1_int32; state%lightning_support%value(i,j,k)=1_int32
      state%vt_z_mean%value(i,j,k)=0.5_real32; state%vt_z_sigma%value(i,j,k)=0.1_real32
      CALL set_water(state,i,j,k,0.003_real64,0.001_real64,0.002_real64,0.001_real64,0.001_real64)
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND); CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS); CALL valid_real(state%radar_reflectivity,SOURCE_RADAR_DBZ)
    CALL valid_integer(state%cloud_type,SOURCE_CLOUD_ANALYSIS); CALL valid_integer(state%precipitation_phase,SOURCE_BACKGROUND_MODEL)
    CALL valid_integer(state%lightning_support,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%vt_z_mean,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vt_z_sigma,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32; state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_temperature%quality=0_int32; state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL; state%obs_support=1_int32; state%hydro_support=1_int32
    state%balance_beta=0.35_real32
    CALL configure_pressure_geometry(state,status); IF (status/=STATUS_OK) ERROR STOP 'geometry failed'
    CALL refresh_dry_air_mass_measure(state,status); IF (status/=STATUS_OK) ERROR STOP 'mass failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) ERROR STOP 'fixture is not canonical'
  END SUBROUTINE make_state

  SUBROUTINE construct_root(state,i,j,k,surface,final_t,transfer,condense)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k,surface
    REAL(real64), INTENT(IN) :: final_t,transfer
    LOGICAL, INTENT(IN) :: condense
    REAL(real64) :: p,qstar,before(6),after(6),ti
    p=REAL(state%pressure%value(i,j,k),real64)
    IF (surface==SATURATION_LIQUID) THEN; qstar=liquid_qsat(final_t,p); ELSE; qstar=ice_qsat(final_t,p); END IF
    before=cell_species(state,i,j,k); after=before
    IF (condense) THEN
      before(1)=qstar+transfer; after(1)=qstar; after(surface+1)=after(surface+1)+transfer
    ELSE
      before(1)=qstar-transfer; after(1)=qstar; before(surface+1)=before(surface+1)+transfer
    END IF
    ti=root_temperature(after,before,final_t)
    state%temperature%value(i,j,k)=REAL(ti,real32); state%vapor%value(i,j,k)=REAL(before(1),real32)
    state%cloud_water%value(i,j,k)=REAL(before(2),real32); state%cloud_ice%value(i,j,k)=REAL(before(3),real32)
    state%rain%value(i,j,k)=REAL(before(4),real32); state%snow%value(i,j,k)=REAL(before(5),real32)
    state%graupel%value(i,j,k)=REAL(before(6),real32)
  END SUBROUTINE construct_root

  PURE REAL(real64) FUNCTION root_temperature(final_species,initial_species,final_t)
    REAL(real64), INTENT(IN) :: final_species(6),initial_species(6),final_t
    root_temperature=T0+((CP0+SUM(SPECIES_CP*final_species))*(final_t-T0)+ &
      SUM(SPECIES_H0*(final_species-initial_species)))/(CP0+SUM(SPECIES_CP*initial_species))
  END FUNCTION root_temperature

  PURE REAL(real64) FUNCTION mixture_h(t,species)
    REAL(real64), INTENT(IN) :: t,species(6)
    mixture_h=(CP0+SUM(SPECIES_CP*species))*(t-T0)+SUM(SPECIES_H0*species)
  END FUNCTION mixture_h

  PURE REAL(real64) FUNCTION liquid_qsat(t,p)
    REAL(real64), INTENT(IN) :: t,p
    REAL(real64) :: es,tc
    tc=t-T0; es=611.20_real64*EXP(17.67_real64*tc/(tc+243.5_real64))
    es=MIN(0.99_real64*p,MAX(0.0_real64,es)); liquid_qsat=0.622_real64*es/(p-es)
  END FUNCTION liquid_qsat

  PURE REAL(real64) FUNCTION ice_qsat(t,p)
    REAL(real64), INTENT(IN) :: t,p
    REAL(real64) :: es,tc
    tc=t-T0; es=611.15_real64*EXP(22.452_real64*tc/(t-0.55_real64))
    es=MIN(0.99_real64*p,MAX(0.0_real64,es)); ice_qsat=0.622_real64*es/(p-es)
  END FUNCTION ice_qsat

  PURE FUNCTION cell_species(state,i,j,k) RESULT(s)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: s(6)
    s=[REAL(state%vapor%value(i,j,k),real64),REAL(state%cloud_water%value(i,j,k),real64), &
       REAL(state%cloud_ice%value(i,j,k),real64),REAL(state%rain%value(i,j,k),real64), &
       REAL(state%snow%value(i,j,k),real64),REAL(state%graupel%value(i,j,k),real64)]
  END FUNCTION cell_species

  SUBROUTINE valid_real(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real
  SUBROUTINE valid_integer(field,source)
    TYPE(integer_field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_integer
  SUBROUTINE set_water(state,i,j,k,liquid,ice,rain,snow,graupel)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64), INTENT(IN) :: liquid,ice,rain,snow,graupel
    state%cloud_water%value(i,j,k)=REAL(liquid,real32); state%cloud_ice%value(i,j,k)=REAL(ice,real32)
    state%rain%value(i,j,k)=REAL(rain,real32); state%snow%value(i,j,k)=REAL(snow,real32)
    state%graupel%value(i,j,k)=REAL(graupel,real32)
    state%cloud_water%valid(i,j,k)=.TRUE.; state%cloud_ice%valid(i,j,k)=.TRUE.; state%rain%valid(i,j,k)=.TRUE.
    state%snow%valid(i,j,k)=.TRUE.; state%graupel%valid(i,j,k)=.TRUE.; state%cloud_water%quality(i,j,k)=0_int32
    state%cloud_ice%quality(i,j,k)=0_int32; state%rain%quality(i,j,k)=0_int32; state%snow%quality(i,j,k)=0_int32
    state%graupel%quality(i,j,k)=0_int32; state%cloud_water%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%cloud_ice%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%rain%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%snow%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%graupel%source(i,j,k)=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE set_water
  SUBROUTINE invalidate_water_cell(field,i,j,k)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    field%valid(i,j,k)=.FALSE.; field%quality(i,j,k)=QUALITY_RAW_MISSING; field%source(i,j,k)=0_int32
  END SUBROUTINE invalidate_water_cell
  PURE ELEMENTAL INTEGER(int32) FUNCTION real32_bits(x)
    REAL(real32), INTENT(IN) :: x
    real32_bits=TRANSFER(x,real32_bits)
  END FUNCTION real32_bits

END PROGRAM test_pressure_thermo_state
