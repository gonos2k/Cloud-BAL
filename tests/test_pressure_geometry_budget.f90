PROGRAM test_pressure_geometry_budget
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,STATUS_FAILED, &
    SOURCE_BACKGROUND_MODEL,SOURCE_ANALYZED_WIND,initialize_cloud_bal_state, &
    configure_pressure_geometry,refresh_dry_air_mass_measure, &
    validate_canonical_state,canonical_states_equal,represented_water_species
  USE cloud_bal_column_physics, ONLY: pressure_analysis_budget, &
    account_pressure_analysis,moist_species_enthalpy
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=1,NY=1,NZ=2
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  INTEGER :: failures

  failures=0
  CALL test_zero_geometry_change
  CALL test_geometry_change_accounting
  CALL test_default_geometry_rejection
  CALL test_opt_in_invariant_rejection

  IF (failures/=0) THEN
    PRINT *,'Pressure geometry-budget tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Pressure geometry-budget tests passed'

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
    CALL check(ABS(actual-expected)<=atol+rtol*MAX(ABS(actual),ABS(expected)), &
      message)
  END SUBROUTINE near

  SUBROUTINE test_zero_geometry_change
    TYPE(cloud_bal_state_type) :: background,candidate,background_before,candidate_before
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status

    CALL make_state(background)
    candidate=background
    background_before=background
    candidate_before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status)

    CALL check(status==STATUS_OK,'unchanged geometry retains legacy accounting')
    CALL check(budget%accounted_cells==2_int64,'unchanged geometry accounts both cells')
    CALL check(ALL(budget%species_change_kg==0.0_real64) .AND. &
      ALL(budget%mixing_ratio_change_kg==0.0_real64) .AND. &
      ALL(budget%dry_mass_redistribution_kg==0.0_real64) .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. &
      budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64 .AND. &
      budget%enthalpy_composition_change_j==0.0_real64 .AND. &
      budget%enthalpy_mass_metric_change_j==0.0_real64 .AND. &
      budget%total_mass_error_kg==0.0_real64 .AND. &
      budget%max_cell_mass_error_kg==0.0_real64, &
      'unchanged geometry has a zero budget')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(candidate,candidate_before), &
      'zero-change accounting preserves both input states')
  END SUBROUTINE test_zero_geometry_change

  SUBROUTINE test_geometry_change_accounting
    TYPE(cloud_bal_state_type) :: background,candidate,background_before,candidate_before
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: before(6),after(6),mb,ma,hb,ha,dm,geometry_expected
    REAL(real64) :: species_expected(6),mixing_expected(6),metric_expected(6)
    REAL(real64) :: dry_expected,enthalpy_expected,composition_expected,metric_h_expected
    REAL(real64) :: total_mass_expected
    INTEGER :: status,reason

    CALL make_state(background)
    candidate=background
    candidate%surface_pressure%value(1,1)=candidate%surface_pressure%value(1,1)+20.0_real32
    CALL configure_pressure_geometry(candidate,status)
    CALL check(status==STATUS_OK,'PSFC increment reconfigures pressure geometry')
    CALL refresh_dry_air_mass_measure(candidate,status)
    CALL check(status==STATUS_OK,'PSFC increment refreshes dry-air mass')

    ! Add one represented-mixture change so both enthalpy terms are exercised.
    candidate%temperature%value(1,1,1)=282.0_real32
    candidate%vapor%value(1,1,1)=0.009_real32
    CALL refresh_dry_air_mass_measure(candidate,status)
    CALL check(status==STATUS_OK,'mixture change keeps candidate dry mass consistent')
    CALL validate_canonical_state(background,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'background geometry-budget fixture is canonical')
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'geometry-changed candidate is canonical')

    background_before=background
    candidate_before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.)
    CALL check(status==STATUS_OK,'explicit geometry opt-in accepts pressure-mass change')
    CALL check(ALL(background%above_ground .EQV. candidate%above_ground) .AND. &
      ALL(background%pressure%value==candidate%pressure%value) .AND. &
      ALL(background%grid%dx==candidate%grid%dx) .AND. &
      ALL(background%grid%dy==candidate%grid%dy), &
      'geometry opt-in keeps active mask, centers, and horizontal grid fixed')

    before=represented_water_species(background,1,1,1)
    after=represented_water_species(candidate,1,1,1)
    mb=background%grid%dry_air_mass_measure(1,1,1)
    ma=candidate%grid%dry_air_mass_measure(1,1,1)
    hb=moist_species_enthalpy(REAL(background%temperature%value(1,1,1),real64),before)
    ha=moist_species_enthalpy(REAL(candidate%temperature%value(1,1,1),real64),after)
    dm=ma-mb
    species_expected=ma*after-mb*before
    mixing_expected=mb*(after-before)
    metric_expected=dm*after
    dry_expected=dm
    geometry_expected=background%grid%dx(1,1)*background%grid%dy(1,1)*20.0_real64/GRAVITY
    enthalpy_expected=ma*ha-mb*hb
    composition_expected=mb*(ha-hb)
    metric_h_expected=dm*ha
    total_mass_expected=dry_expected+SUM(species_expected)-geometry_expected

    CALL near(budget%geometry_mass_change_kg,geometry_expected,1.0e-5_real64,1.0e-13_real64, &
      'geometry mass change equals A*dPSFC/g')
    CALL near(budget%dry_air_change_kg,dry_expected,1.0e-5_real64,1.0e-13_real64, &
      'dry-air change uses refreshed dry mass')
    CALL near(budget%species_change_kg(1),species_expected(1),1.0e-5_real64,1.0e-13_real64, &
      'vapor species mass change uses both geometry and mixing-ratio metrics')
    CALL near(budget%mixing_ratio_change_kg(1),mixing_expected(1),1.0e-5_real64,1.0e-13_real64, &
      'vapor mixing-ratio metric is mb times delta mixing ratio')
    CALL near(budget%dry_mass_redistribution_kg(1),metric_expected(1),1.0e-5_real64,1.0e-13_real64, &
      'vapor mass metric is dm times candidate mixing ratio')
    CALL near(budget%enthalpy_change_j,enthalpy_expected,1.0e-2_real64,1.0e-13_real64, &
      'total enthalpy change is the represented-mass difference')
    CALL near(budget%enthalpy_composition_change_j,composition_expected,1.0e-2_real64,1.0e-13_real64, &
      'enthalpy composition term is mb times delta enthalpy')
    CALL near(budget%enthalpy_mass_metric_change_j,metric_h_expected,1.0e-2_real64,1.0e-13_real64, &
      'enthalpy mass metric term is dm times candidate enthalpy')
    CALL near(budget%enthalpy_composition_change_j+budget%enthalpy_mass_metric_change_j, &
      budget%enthalpy_change_j,1.0e-2_real64,1.0e-13_real64, &
      'enthalpy split closes exactly')
    CALL near(budget%total_mass_error_kg,total_mass_expected,1.0e-5_real64,1.0e-13_real64, &
      'total mass error uses dry plus species minus geometry mass')
    CALL near(budget%total_mass_error_kg,0.0_real64,1.0e-5_real64,1.0e-13_real64, &
      'geometry-aware mass budget closes')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(candidate,candidate_before), &
      'successful accounting preserves both input states')
  END SUBROUTINE test_geometry_change_accounting

  SUBROUTINE test_default_geometry_rejection
    TYPE(cloud_bal_state_type) :: background,candidate,background_before,candidate_before
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status

    CALL make_state(background)
    candidate=background
    candidate%surface_pressure%value(1,1)=candidate%surface_pressure%value(1,1)+20.0_real32
    CALL configure_pressure_geometry(candidate,status)
    CALL refresh_dry_air_mass_measure(candidate,status)
    background_before=background
    candidate_before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status)

    CALL check(status==STATUS_FAILED,'geometry change is rejected without explicit opt-in')
    CALL check(budget%geometry_mass_change_kg==0.0_real64 .AND. &
      budget%total_mass_error_kg==0.0_real64,'rejected geometry change leaves zero budget')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(candidate,candidate_before), &
      'default geometry rejection preserves both input states')
  END SUBROUTINE test_default_geometry_rejection

  SUBROUTINE test_opt_in_invariant_rejection
    TYPE(cloud_bal_state_type) :: background,candidate,before
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status

    CALL make_state(background)
    candidate=background
    candidate%above_ground(1,1,1)=.FALSE.
    before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.)
    CALL check(status==STATUS_FAILED,'changed active mask is rejected even with opt-in')
    CALL check(canonical_states_equal(candidate,before),'active-mask rejection preserves candidate')

    candidate=background
    candidate%pressure%value(1,1,1)=candidate%pressure%value(1,1,1)+1.0_real32
    before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.)
    CALL check(status==STATUS_FAILED,'changed pressure centers are rejected with opt-in')
    CALL check(canonical_states_equal(candidate,before),'center rejection preserves candidate')

    candidate=background
    candidate%grid%dx(1,1)=candidate%grid%dx(1,1)+1.0_real64
    before=candidate
    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.)
    CALL check(status==STATUS_FAILED,'changed horizontal grid is rejected with opt-in')
    CALL check(canonical_states_equal(candidate,before),'grid rejection preserves candidate')
  END SUBROUTINE test_opt_in_invariant_rejection

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: status,reason

    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME, &
      'pressure-geometry-budget-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'

    state%grid%dx=2000.0_real64
    state%grid%dy=2200.0_real64
    state%pressure%value(:,:,1)=95000.0_real32
    state%pressure%value(:,:,2)=80000.0_real32
    state%temperature%value=280.0_real32
    state%vapor%value=0.008_real32
    state%cloud_water%value=0.003_real32
    state%cloud_ice%value=0.001_real32
    state%rain%value=0.002_real32
    state%snow%value=0.001_real32
    state%graupel%value=0.001_real32
    state%u%value=2.0_real32
    state%v%value=-1.0_real32
    state%omega%value=0.0_real32
    state%omega_target%value=0.0_real32
    state%omega_target_sigma%value=1.0_real32

    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%graupel,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target_sigma,SOURCE_BACKGROUND_MODEL)

    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.
    state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%obs_support=1_int32
    state%hydro_support=1_int32
    state%balance_beta=0.35_real32

    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    IF (status/=STATUS_OK) ERROR STOP 'fixture is not canonical'
  END SUBROUTINE make_state

  SUBROUTINE valid_real(field,source)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE valid_real

END PROGRAM test_pressure_geometry_budget
