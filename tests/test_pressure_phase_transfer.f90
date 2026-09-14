PROGRAM test_pressure_phase_transfer
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: apply_pressure_phase_transfer,water_phase_budget
  IMPLICIT NONE

  REAL(real64), PARAMETER :: T0=273.15_real64,CP0=1004.5_real64
  REAL(real64), PARAMETER :: SPECIES_CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
                                            4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: SPECIES_H0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
                                             0.0_real64,-3.50e5_real64,-3.50e5_real64]
  INTEGER :: failures=0

  CALL test_mixed_transfers()
  CALL test_empty_selection_and_inactive_nan()
  CALL test_rejection_rollback()
  IF (failures/=0) THEN
    PRINT *, 'Pressure phase-transfer tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *, 'Pressure phase-transfer tests passed'

CONTAINS

  SUBROUTINE check(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *, 'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_near(actual,expected,atol,rtol,message)
    REAL(real64), INTENT(IN) :: actual,expected,atol,rtol
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ABS(actual-expected)<=atol+rtol*MAX(ABS(actual),ABS(expected)),message)
  END SUBROUTINE check_near

  SUBROUTINE test_mixed_transfers()
    TYPE(cloud_bal_state_type) :: input,output,snapshot,restored
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2)
    REAL(real64) :: delta(3,1,2,6)
    INTEGER :: i,j,k

    CALL make_state(input)
    snapshot=input
    active=.FALSE.; active(1:2,1,1)=.TRUE.; active(1:2,1,2)=.TRUE.; active(3,1,1)=.TRUE.
    delta=0.0_real64
    ! vapor, cloud liquid, cloud ice, rain, snow, graupel
    delta(1,1,1,:)=[ 5.0e-4_real64, 0.0_real64, 0.0_real64,-5.0e-4_real64, 0.0_real64, 0.0_real64]
    delta(2,1,1,:)=[ 3.0e-4_real64, 0.0_real64, 0.0_real64, 0.0_real64,-3.0e-4_real64, 0.0_real64]
    delta(3,1,1,:)=[ 0.0_real64, 4.0e-4_real64,-4.0e-4_real64,0.0_real64, 0.0_real64, 0.0_real64]
    delta(1,1,2,:)=[ 0.0_real64,-2.0e-4_real64, 2.0e-4_real64,0.0_real64, 0.0_real64, 0.0_real64]
    delta(2,1,2,:)=[-2.0e-4_real64, 0.0_real64, 0.0_real64,0.0_real64, 0.0_real64, 2.0e-4_real64]
    delta(3,1,2,:)=ieee_value(0.0_real64,ieee_quiet_nan)

    CALL apply_pressure_phase_transfer(input,output,result,active,delta,budget)
    CALL check(result%status==STATUS_OK,'mixed six-species transfer succeeds')
    CALL check(result%reason_code==REASON_NONE,'successful transfer has no rejection reason')
    CALL check(ALL(result%changed .EQV. active),'changed mask is limited to actual selected transfers')
    CALL check(canonical_states_equal(input,snapshot),'input is unchanged by the transaction')
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
      'only the seven thermo values change; metadata, geometry, support and diagnostics copy exactly')
    CALL check(ALL(output%obs_support==input%obs_support) .AND. &
               ALL(output%hydro_support==input%hydro_support) .AND. &
               ALL(output%balance_beta==input%balance_beta), &
      'copied support diagnostics are not refreshed')
    CALL check_source_provenance(input,output,active)

    DO k=1,2; DO j=1,1; DO i=1,3
      IF (.NOT.active(i,j,k)) CYCLE
      CALL check_cell_oracle(input,output,i,j,k,delta(i,j,k,:))
    END DO; END DO; END DO
    CALL check_budget(input,output,active,budget)
    CALL check(REAL(output%vapor%value(3,1,2),real64)== &
               REAL(input%vapor%value(3,1,2),real64), 'inactive vapor is bit-preserved')
    CALL check(REAL(output%rain%value(3,1,2),real64)== &
               REAL(input%rain%value(3,1,2),real64), 'inactive rain is bit-preserved')
  END SUBROUTINE test_mixed_transfers

  SUBROUTINE test_empty_selection_and_inactive_nan()
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2)
    REAL(real64) :: delta(3,1,2,6)

    CALL make_state(input)
    active=.FALSE.; delta=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL apply_pressure_phase_transfer(input,output,result,active,delta,budget)
    CALL check(result%status==STATUS_OK .AND. result%reason_code==REASON_NONE, &
      'empty selection accepts opaque NaN deltas')
    CALL check(.NOT.ANY(result%changed),'empty selection has no changed cells')
    CALL check_zero_budget(budget,'empty selection has zero budget')
    CALL check(canonical_states_equal(output,input),'empty selection is an exact no-op')
  END SUBROUTINE test_empty_selection_and_inactive_nan

  SUBROUTINE test_rejection_rollback()
    TYPE(cloud_bal_state_type) :: input,output,before
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    LOGICAL :: active(3,1,2),bad_active(1,1,1)
    REAL(real64) :: delta(3,1,2,6),bad_delta(3,1,2,5)
    INTEGER :: species
    REAL(real64) :: before_species(6),proposed_species(6),input_t,cp,phase,predicted_t

    active=.FALSE.; active(1:2,1,1)=.TRUE.; active(1:2,1,2)=.TRUE.; active(3,1,1)=.TRUE.

    DO species=0,5
      CALL make_state(input); delta=0.0_real64
      delta(1,1,1,:)=[ 5.0e-4_real64, 0.0_real64, 0.0_real64,-5.0e-4_real64, 0.0_real64, 0.0_real64]
      SELECT CASE(species)
      CASE(0); input%vapor%valid(1,1,1)=.FALSE.
      CASE(1); input%cloud_water%valid(1,1,1)=.FALSE.
      CASE(2); input%cloud_ice%valid(1,1,1)=.FALSE.
      CASE(3); input%rain%valid(1,1,1)=.FALSE.
      CASE(4); input%snow%valid(1,1,1)=.FALSE.
      CASE(5); input%graupel%valid(1,1,1)=.FALSE.
      END SELECT
      before=input
      CALL expect_rejection(input,active,delta,'each missing selected water species rejects',before)
    END DO

    CALL make_state(input); before=input; delta=0.0_real64
    delta(1,1,1,:)=[ 5.0e-4_real64,0.0_real64,0.0_real64,-5.0e-4_real64,0.0_real64,0.0_real64]
    delta(2,1,1,1)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_rejection(input,active,delta,'selected NaN delta rejects',before)

    CALL make_state(input); before=input; delta=0.0_real64
    delta(1,1,1,:)=[ 5.0e-4_real64,0.0_real64,0.0_real64,-5.0e-4_real64,0.0_real64,0.0_real64]
    delta(2,1,1,1)=1.0e-4_real64
    CALL expect_rejection(input,active,delta,'external water delta rejects',before)

    CALL make_state(input); before=input; delta=0.0_real64
    delta(1,1,1,:)=[ 5.0e-4_real64,0.0_real64,0.0_real64,-5.0e-4_real64,0.0_real64,0.0_real64]
    delta(2,1,1,:)=[ 0.0_real64,0.0_real64,0.0_real64,-0.020_real64,0.0_real64,0.020_real64]
    CALL expect_rejection(input,active,delta,'late-cell overdraw rolls back earlier cell',before)

    CALL make_state(input); delta=0.0_real64
    input%vapor%value(1,1,1)=0.15_real32
    CALL refresh_dry_air_mass_measure(input,species)
    CALL check(species==STATUS_OK,'high-vapor out-of-range-temperature fixture remains canonical')
    before=input
    delta(1,1,1,:)=[-0.10_real64,0.0_real64,0.10_real64,0.0_real64,0.0_real64,0.0_real64]
    before_species=[REAL(input%vapor%value(1,1,1),real64),REAL(input%cloud_water%value(1,1,1),real64), &
      REAL(input%cloud_ice%value(1,1,1),real64),REAL(input%rain%value(1,1,1),real64), &
      REAL(input%snow%value(1,1,1),real64),REAL(input%graupel%value(1,1,1),real64)]
    proposed_species=before_species+delta(1,1,1,:)
    input_t=REAL(input%temperature%value(1,1,1),real64)
    cp=CP0+SUM(SPECIES_CP*proposed_species)
    phase=SUM(delta(1,1,1,:)*(SPECIES_H0+SPECIES_CP*(input_t-T0)))
    predicted_t=input_t-phase/cp
    CALL check(ALL(proposed_species>=0.0_real64) .AND. predicted_t>350.0_real64, &
      'out-of-range final temperature is caused by a valid nonnegative transfer')
    CALL expect_rejection(input,active,delta,'invalid final temperature rolls back',before)

    CALL make_state(input); before=input; delta=0.0_real64
    delta(1,1,1,:)=[ 5.0e-4_real64,0.0_real64,0.0_real64,-5.0e-4_real64,0.0_real64,0.0_real64]
    bad_active=.TRUE.; CALL apply_pressure_phase_transfer(input,output,result,bad_active,delta,budget)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
      'active-mask shape mismatch rejects')
    CALL check(canonical_states_equal(output,before),'shape rejection rolls back state')
    CALL check_zero_budget(budget,'shape rejection has zero budget')
    bad_delta=0.0_real64
    CALL apply_pressure_phase_transfer(input,output,result,active,bad_delta,budget)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
      'delta shape mismatch rejects')
    CALL check(canonical_states_equal(output,before),'delta-shape rejection rolls back state')
    CALL check_zero_budget(budget,'delta-shape rejection has zero budget')
  END SUBROUTINE test_rejection_rollback

  SUBROUTINE expect_rejection(input,active,delta,message,before)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,before
    LOGICAL, INTENT(IN) :: active(:,:,:)
    REAL(real64), INTENT(IN) :: delta(:,:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    TYPE(cloud_bal_state_type) :: output
    TYPE(stage_result) :: result
    TYPE(water_phase_budget) :: budget
    CALL apply_pressure_phase_transfer(input,output,result,active,delta,budget)
    CALL check(result%status==STATUS_FAILED,message)
    CALL check(.NOT.ANY(result%changed),TRIM(message)//' has no changed cells')
    CALL check_zero_budget(budget,TRIM(message)//' has zero budget')
    CALL check(canonical_states_equal(output,before),TRIM(message)//' rolls back all state')
  END SUBROUTINE expect_rejection

  SUBROUTINE check_cell_oracle(input,output,i,j,k,requested)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64), INTENT(IN) :: requested(6)
    REAL(real64) :: before(6),after(6),expected_after(6),expected_t,cp,phase
    REAL(real64) :: initial_t,stored_t

    before=[REAL(input%vapor%value(i,j,k),real64),REAL(input%cloud_water%value(i,j,k),real64), &
            REAL(input%cloud_ice%value(i,j,k),real64),REAL(input%rain%value(i,j,k),real64), &
            REAL(input%snow%value(i,j,k),real64),REAL(input%graupel%value(i,j,k),real64)]
    after=[REAL(output%vapor%value(i,j,k),real64),REAL(output%cloud_water%value(i,j,k),real64), &
           REAL(output%cloud_ice%value(i,j,k),real64),REAL(output%rain%value(i,j,k),real64), &
           REAL(output%snow%value(i,j,k),real64),REAL(output%graupel%value(i,j,k),real64)]
    expected_after=before+requested
    initial_t=REAL(input%temperature%value(i,j,k),real64)
    cp=CP0+SUM(SPECIES_CP*expected_after)
    phase=SUM(requested*(SPECIES_H0+SPECIES_CP*(initial_t-T0)))
    expected_t=initial_t-phase/cp
    stored_t=REAL(output%temperature%value(i,j,k),real64)
    CALL check_near(stored_t,expected_t,5.0e-5_real64,2.0e-7_real64, &
      'analytic full-mixture temperature is energy conserving')
    CALL check(ALL(ABS(after-expected_after)<=2.0e-7_real64), &
      'requested six-species transfer is stored')
    CALL check(stored_t>=150.0_real64 .AND. stored_t<=350.0_real64 .AND. ALL(after>=0.0_real64), &
      'selected output remains in canonical physical bounds')
    CALL check(ABS(SUM(after-before))<=2.0e-7_real64,'selected-cell water closes')
  END SUBROUTINE check_cell_oracle

  SUBROUTINE check_budget(input,output,active,budget)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    LOGICAL, INTENT(IN) :: active(:,:,:)
    TYPE(water_phase_budget), INTENT(IN) :: budget
    REAL(real64) :: species(6),sensible,phase,mass,before(6),after(6),change(6)
    REAL(real64) :: initial_t,final_t,cp,cell_sensible,cell_phase
    INTEGER :: i,j,k

    species=0.0_real64; sensible=0.0_real64; phase=0.0_real64
    DO k=1,SIZE(active,3); DO j=1,SIZE(active,2); DO i=1,SIZE(active,1)
      IF (.NOT.active(i,j,k)) CYCLE
      before=[REAL(input%vapor%value(i,j,k),real64),REAL(input%cloud_water%value(i,j,k),real64), &
              REAL(input%cloud_ice%value(i,j,k),real64),REAL(input%rain%value(i,j,k),real64), &
              REAL(input%snow%value(i,j,k),real64),REAL(input%graupel%value(i,j,k),real64)]
      after=[REAL(output%vapor%value(i,j,k),real64),REAL(output%cloud_water%value(i,j,k),real64), &
             REAL(output%cloud_ice%value(i,j,k),real64),REAL(output%rain%value(i,j,k),real64), &
             REAL(output%snow%value(i,j,k),real64),REAL(output%graupel%value(i,j,k),real64)]
      change=after-before; mass=input%grid%dry_air_mass_measure(i,j,k)
      initial_t=REAL(input%temperature%value(i,j,k),real64)
      final_t=REAL(output%temperature%value(i,j,k),real64)
      cp=CP0+SUM(SPECIES_CP*after)
      cell_sensible=cp*(final_t-initial_t)
      cell_phase=SUM(change*(SPECIES_H0+SPECIES_CP*(initial_t-T0)))
      species=species+mass*change
      sensible=sensible+mass*cell_sensible
      phase=phase+mass*cell_phase
    END DO; END DO; END DO
    CALL check_near(budget%species_change_kg(1),species(1),1.0e-9_real64,2.0e-11_real64, &
      'budget vapor change uses final float32 state')
    CALL check(ALL(ABS(budget%species_change_kg-species)<=1.0e-9_real64+ &
                   2.0e-11_real64*MAX(ABS(budget%species_change_kg),ABS(species))), &
      'all six budget species changes use final float32 state')
    CALL check_near(budget%sensible_change_j,sensible,1.0e-5_real64,2.0e-11_real64, &
      'budget sensible change uses final float32 temperature')
    CALL check_near(budget%phase_change_j,phase,1.0e-5_real64,2.0e-11_real64, &
      'budget phase change uses input-temperature species enthalpy')
    CALL check_near(budget%water_error_kg,SUM(species),1.0e-9_real64,2.0e-11_real64, &
      'budget water residual is recomputed from final float32 state')
    CALL check(ABS(budget%enthalpy_error_j-(sensible+phase))<=1.0e-8_real64+ &
      64.0_real64*EPSILON(1.0_real64)*(ABS(sensible)+ABS(phase)), &
      'budget enthalpy residual is sensible plus phase change')
  END SUBROUTINE check_budget

  SUBROUTINE check_source_provenance(input,output,active)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,output
    LOGICAL, INTENT(IN) :: active(:,:,:)
    INTEGER :: i,j,k
    DO k=1,SIZE(active,3); DO j=1,SIZE(active,2); DO i=1,SIZE(active,1)
      CALL check_one_source(input%temperature%value(i,j,k),output%temperature%value(i,j,k), &
        input%temperature%source(i,j,k),output%temperature%source(i,j,k),'temperature',active(i,j,k))
      CALL check_one_source(input%vapor%value(i,j,k),output%vapor%value(i,j,k), &
        input%vapor%source(i,j,k),output%vapor%source(i,j,k),'vapor',active(i,j,k))
      CALL check_one_source(input%cloud_water%value(i,j,k),output%cloud_water%value(i,j,k), &
        input%cloud_water%source(i,j,k),output%cloud_water%source(i,j,k),'cloud liquid',active(i,j,k))
      CALL check_one_source(input%cloud_ice%value(i,j,k),output%cloud_ice%value(i,j,k), &
        input%cloud_ice%source(i,j,k),output%cloud_ice%source(i,j,k),'cloud ice',active(i,j,k))
      CALL check_one_source(input%rain%value(i,j,k),output%rain%value(i,j,k), &
        input%rain%source(i,j,k),output%rain%source(i,j,k),'rain',active(i,j,k))
      CALL check_one_source(input%snow%value(i,j,k),output%snow%value(i,j,k), &
        input%snow%source(i,j,k),output%snow%source(i,j,k),'snow',active(i,j,k))
      CALL check_one_source(input%graupel%value(i,j,k),output%graupel%value(i,j,k), &
        input%graupel%source(i,j,k),output%graupel%source(i,j,k),'graupel',active(i,j,k))
    END DO; END DO; END DO
  END SUBROUTINE check_source_provenance

  SUBROUTINE check_one_source(before,after,source_before,source_after,name,selected)
    REAL(real32), INTENT(IN) :: before,after
    INTEGER(int32), INTENT(IN) :: source_before,source_after
    CHARACTER(LEN=*), INTENT(IN) :: name
    LOGICAL, INTENT(IN) :: selected
    IF (.NOT.selected .OR. real32_bits(before)==real32_bits(after)) THEN
      CALL check(source_after==source_before,TRIM(name)//' source is unchanged when its value is unchanged')
    ELSE
      CALL check(source_after==IOR(source_before,SOURCE_COLUMN_PHYSICS), &
        TRIM(name)//' changed value carries column-physics provenance')
    END IF
  END SUBROUTINE check_one_source

  SUBROUTINE check_zero_budget(budget,message)
    TYPE(water_phase_budget), INTENT(IN) :: budget
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%sensible_change_j==0.0_real64 .AND. budget%phase_change_j==0.0_real64 .AND. &
      budget%water_error_kg==0.0_real64 .AND. budget%enthalpy_error_j==0.0_real64,message)
  END SUBROUTINE check_zero_budget

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    INTEGER :: i,j,k,status,reason
    CALL initialize_cloud_bal_state(state,3,1,2,valid_time,'pressure-phase-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'phase-transfer fixture initialization failed'
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    DO k=1,2; DO j=1,1; DO i=1,3
      state%pressure%value(i,j,k)=REAL(MERGE(90000.0_real64,70000.0_real64,k==1),real32)
      state%temperature%value(i,j,k)=REAL(250.0_real64+8.0_real64*i+4.0_real64*k,real32)
      state%vapor%value(i,j,k)=REAL(0.012_real64+0.001_real64*i,real32)
      state%u%value(i,j,k)=2.0_real32; state%v%value(i,j,k)=-1.0_real32
      state%omega%value(i,j,k)=0.0_real32; state%omega_target%value(i,j,k)=0.0_real32
      state%geopotential%value(i,j,k)=0.0_real32; state%cloud_fraction%value(i,j,k)=0.0_real32
      state%radar_reflectivity%value(i,j,k)=0.0_real32
      CALL set_water_cell(state,i,j,k,0.002_real64+0.0001_real64*i, &
        0.0015_real64+0.0001_real64*k,0.0020_real64+0.0002_real64*i, &
        0.0010_real64+0.0001_real64*k,0.0012_real64+0.0001_real64*i)
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_ANALYZED_WIND); CALL valid_real(state%v,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%omega_target,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    CALL valid_real(state%radar_reflectivity,SOURCE_RADAR_DBZ)
    CALL valid_integer(state%cloud_type,SOURCE_CLOUD_ANALYSIS)
    CALL valid_integer(state%precipitation_phase,SOURCE_BACKGROUND_MODEL)
    CALL valid_integer(state%lightning_support,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vt_z_mean,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%vt_z_sigma,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32; state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL; state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%obs_support=1_int32; state%hydro_support=1_int32; state%balance_beta=0.35_real32
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'phase-transfer fixture geometry failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'phase-transfer fixture dry mass failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) ERROR STOP 'phase-transfer fixture is not canonical'
  END SUBROUTINE make_state

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

  SUBROUTINE set_water_cell(state,i,j,k,liquid,ice,rain,snow,graupel)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64), INTENT(IN) :: liquid,ice,rain,snow,graupel
    state%cloud_water%value(i,j,k)=REAL(liquid,real32); state%cloud_ice%value(i,j,k)=REAL(ice,real32)
    state%rain%value(i,j,k)=REAL(rain,real32); state%snow%value(i,j,k)=REAL(snow,real32)
    state%graupel%value(i,j,k)=REAL(graupel,real32)
    state%cloud_water%valid(i,j,k)=.TRUE.; state%cloud_ice%valid(i,j,k)=.TRUE.
    state%rain%valid(i,j,k)=.TRUE.; state%snow%valid(i,j,k)=.TRUE.; state%graupel%valid(i,j,k)=.TRUE.
    state%cloud_water%quality(i,j,k)=0_int32; state%cloud_ice%quality(i,j,k)=0_int32
    state%rain%quality(i,j,k)=0_int32; state%snow%quality(i,j,k)=0_int32; state%graupel%quality(i,j,k)=0_int32
    state%cloud_water%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%cloud_ice%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%rain%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%snow%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%graupel%source(i,j,k)=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE set_water_cell

  PURE ELEMENTAL INTEGER(int32) FUNCTION real32_bits(value)
    REAL(real32), INTENT(IN) :: value
    real32_bits=TRANSFER(value,real32_bits)
  END FUNCTION real32_bits

END PROGRAM test_pressure_phase_transfer
