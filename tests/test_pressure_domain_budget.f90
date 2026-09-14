PROGRAM test_pressure_domain_budget
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,STATUS_FAILED, &
    SOURCE_BACKGROUND_MODEL,initialize_cloud_bal_state,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,validate_canonical_state
  USE cloud_bal_column_physics, ONLY: pressure_analysis_budget, &
    account_pressure_analysis
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=1,NY=1,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  INTEGER :: failures

  failures=0
  CALL test_activation
  CALL test_reverse_removal
  CALL test_default_domain_rejection
  CALL test_domain_requires_geometry
  CALL test_missing_newactive_species_rejection
  CALL test_same_mask_partial_legacy_diagnostic
  CALL test_same_mask_legacy_accounting

  IF (failures/=0) THEN
    PRINT *,'Pressure domain-budget tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Pressure domain-budget tests passed'

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

  SUBROUTINE test_activation
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: expected_dry,expected_enthalpy,expected_pressure
    REAL(real64) :: expected_species(6)
    INTEGER(int64) :: expected_cells
    INTEGER :: status

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,100010.0_real32)
    CALL check_domain(background,.FALSE.,.TRUE.,.TRUE., &
      'background pressure surface selects the upper two centers')
    CALL check_domain(candidate,.TRUE.,.TRUE.,.TRUE., &
      'candidate pressure surface activates the new bottom cell')
    CALL independent_budget(background,candidate,expected_dry,expected_species, &
      expected_enthalpy,expected_pressure,expected_cells)

    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.,.TRUE.)
    CALL check(status==STATUS_OK,'domain activation is accepted with both opt-ins')
    CALL check_budget(budget,expected_dry,expected_species,expected_enthalpy, &
      expected_pressure,expected_cells,'activation')
    ! The new bottom cell is 2510 Pa thick, but the old bottom cell loses
    ! 2499.125 Pa to the repartition. Only 10.875 Pa is added to the column.
    CALL near(budget%geometry_mass_change_kg,2000.0_real64*2200.0_real64* &
      (100010.0_real64-99999.125_real64)/GRAVITY,1.0e-6_real64,1.0e-13_real64, &
      'column pressure mass changes only by A*deltaPS/g')
    CALL check(budget%incomplete_background_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==0_int64, &
      'activation counts all six species only on valid active cells')
  END SUBROUTINE test_activation

  SUBROUTINE test_reverse_removal
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: expected_dry,expected_enthalpy,expected_pressure
    REAL(real64) :: expected_species(6)
    INTEGER(int64) :: expected_cells
    INTEGER :: status

    CALL make_state(background,100010.0_real32)
    CALL make_state(candidate,99999.125_real32)
    CALL check_domain(background,.TRUE.,.TRUE.,.TRUE., &
      'reverse background contains the bottom center')
    CALL check_domain(candidate,.FALSE.,.TRUE.,.TRUE., &
      'reverse candidate removes the bottom center')
    CALL independent_budget(background,candidate,expected_dry,expected_species, &
      expected_enthalpy,expected_pressure,expected_cells)

    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.,.TRUE.)
    CALL check(status==STATUS_OK,'domain removal is accepted with both opt-ins')
    CALL check_budget(budget,expected_dry,expected_species,expected_enthalpy, &
      expected_pressure,expected_cells,'reverse removal')
  END SUBROUTINE test_reverse_removal

  SUBROUTINE test_default_domain_rejection
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,100010.0_real32)
    CALL account_pressure_analysis(background,candidate,budget,status)

    CALL check(status==STATUS_FAILED,'domain change is rejected by default')
    CALL check(budget%accounted_cells==0_int64 .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. &
      ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64, &
      'default domain rejection returns an empty budget')
  END SUBROUTINE test_default_domain_rejection

  SUBROUTINE test_domain_requires_geometry
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,100010.0_real32)
    CALL account_pressure_analysis(background,candidate,budget,status,.FALSE.,.TRUE.)

    CALL check(status==STATUS_FAILED,'domain opt-in without geometry opt-in is rejected')
    CALL check(budget%accounted_cells==0_int64 .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. &
      ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64, &
      'incomplete domain opt-in returns an empty budget')
  END SUBROUTINE test_domain_requires_geometry

  SUBROUTINE test_missing_newactive_species_rejection
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status,reason

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,100010.0_real32)
    CALL invalidate_species_at(candidate%cloud_ice,1)
    CALL refresh_dry_air_mass_measure(candidate,reason)
    CALL check(reason==STATUS_OK,'missing new-active condensate still refreshes dry mass')
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'partial six-species candidate satisfies caller validation')
    CALL account_pressure_analysis(background,candidate,budget,status,.TRUE.,.TRUE.)

    CALL check(status==STATUS_FAILED, &
      'domain transition rejects an incomplete newly active six-species cell')
    CALL check(budget%accounted_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==0_int64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64, &
      'incomplete domain transition returns an empty budget')
  END SUBROUTINE test_missing_newactive_species_rejection

  SUBROUTINE test_same_mask_partial_legacy_diagnostic
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: budget
    INTEGER :: status,reason

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,99999.125_real32)
    CALL invalidate_species_at(candidate%cloud_ice,2)
    CALL refresh_dry_air_mass_measure(candidate,reason)
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'same-mask partial candidate satisfies caller validation')
    CALL account_pressure_analysis(background,candidate,budget,status)

    CALL check(status==STATUS_OK,'legacy same-mask partial accounting remains accepted')
    CALL check(budget%incomplete_background_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==1_int64, &
      'legacy same-mask partial accounting retains its diagnostic counter')
  END SUBROUTINE test_same_mask_partial_legacy_diagnostic

  SUBROUTINE test_same_mask_legacy_accounting
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(pressure_analysis_budget) :: legacy,explicit
    REAL(real64) :: expected_dry,expected_enthalpy,expected_pressure
    REAL(real64) :: expected_species(6)
    INTEGER(int64) :: expected_cells
    INTEGER :: status_legacy,status_explicit,reason

    CALL make_state(background,99999.125_real32)
    CALL make_state(candidate,99999.125_real32)
    CALL perturb_active_payload(candidate)
    CALL refresh_dry_air_mass_measure(candidate,reason)
    CALL check(reason==STATUS_OK,'same-mask candidate refreshes dry mass')
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status_explicit,reason)
    CALL check(status_explicit==STATUS_OK,'same-mask candidate remains canonical')
    CALL independent_budget(background,candidate,expected_dry,expected_species, &
      expected_enthalpy,expected_pressure,expected_cells)

    CALL account_pressure_analysis(background,candidate,legacy,status_legacy)
    CALL account_pressure_analysis(background,candidate,explicit,status_explicit,.TRUE.,.TRUE.)
    CALL check(status_legacy==STATUS_OK .AND. status_explicit==STATUS_OK, &
      'same-mask accounting accepts legacy and explicit calls')
    CALL check_budget(legacy,expected_dry,expected_species,expected_enthalpy, &
      expected_pressure,expected_cells,'same-mask legacy')
    CALL check(budgets_equal(legacy,explicit), &
      'same-mask explicit opt-ins leave legacy accounting unchanged')
  END SUBROUTINE test_same_mask_legacy_accounting

  SUBROUTINE check_budget(budget,expected_dry,expected_species,expected_enthalpy, &
                          expected_pressure,expected_cells,label)
    TYPE(pressure_analysis_budget), INTENT(IN) :: budget
    REAL(real64), INTENT(IN) :: expected_dry,expected_species(6),expected_enthalpy, &
      expected_pressure
    INTEGER(int64), INTENT(IN) :: expected_cells
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64) :: expected_error

    expected_error=expected_dry+SUM(expected_species)-expected_pressure
    CALL near(budget%dry_air_change_kg,expected_dry,1.0e-8_real64,1.0e-13_real64, &
      TRIM(label)//' dry-mass union total')
    CALL check(ALL(ABS(budget%species_change_kg-expected_species)<= &
      1.0e-8_real64+1.0e-13_real64*MAX(ABS(budget%species_change_kg), &
      ABS(expected_species))),TRIM(label)//' six-species union totals')
    CALL near(budget%enthalpy_change_j,expected_enthalpy,1.0e-2_real64,1.0e-13_real64, &
      TRIM(label)//' enthalpy union total')
    CALL near(budget%geometry_mass_change_kg,expected_pressure,1.0e-8_real64,1.0e-13_real64, &
      TRIM(label)//' pressure-mass union total')
    CALL check(budget%accounted_cells==expected_cells,TRIM(label)//' union cell count')
    CALL near(budget%total_mass_error_kg,expected_error,1.0e-8_real64,1.0e-13_real64, &
      TRIM(label)//' independent mass residual')
  END SUBROUTINE check_budget

  SUBROUTINE independent_budget(background,candidate,expected_dry,expected_species, &
                                 expected_enthalpy,expected_pressure,expected_cells)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    REAL(real64), INTENT(OUT) :: expected_dry,expected_species(6),expected_enthalpy, &
      expected_pressure
    INTEGER(int64), INTENT(OUT) :: expected_cells
    REAL(real64) :: before(6),after(6),mb,ma,hb,ha
    INTEGER :: i,j,k

    expected_dry=0.0_real64
    expected_species=0.0_real64
    expected_enthalpy=0.0_real64
    expected_pressure=0.0_real64
    expected_cells=0_int64
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      IF (.NOT.(background%above_ground(i,j,k) .OR. candidate%above_ground(i,j,k))) CYCLE
      expected_cells=expected_cells+1_int64
      before=0.0_real64; after=0.0_real64
      mb=0.0_real64; ma=0.0_real64; hb=0.0_real64; ha=0.0_real64
      IF (background%above_ground(i,j,k)) THEN
        before=raw_species(background,i,j,k)
        mb=background%grid%dry_air_mass_measure(i,j,k)
        hb=oracle_enthalpy(REAL(background%temperature%value(i,j,k),real64),before)
        expected_pressure=expected_pressure-background%grid%pressure_mass_measure(i,j,k)
      END IF
      IF (candidate%above_ground(i,j,k)) THEN
        after=raw_species(candidate,i,j,k)
        ma=candidate%grid%dry_air_mass_measure(i,j,k)
        ha=oracle_enthalpy(REAL(candidate%temperature%value(i,j,k),real64),after)
        expected_pressure=expected_pressure+candidate%grid%pressure_mass_measure(i,j,k)
      END IF
      expected_dry=expected_dry+ma-mb
      expected_species=expected_species+ma*after-mb*before
      expected_enthalpy=expected_enthalpy+ma*ha-mb*hb
    END DO; END DO; END DO
  END SUBROUTINE independent_budget

  PURE FUNCTION raw_species(state,i,j,k) RESULT(species)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: species(6)

    species(1)=REAL(state%vapor%value(i,j,k),real64)
    species(2)=REAL(state%cloud_water%value(i,j,k),real64)
    species(3)=REAL(state%cloud_ice%value(i,j,k),real64)
    species(4)=REAL(state%rain%value(i,j,k),real64)
    species(5)=REAL(state%snow%value(i,j,k),real64)
    species(6)=REAL(state%graupel%value(i,j,k),real64)
  END FUNCTION raw_species

  PURE REAL(real64) FUNCTION oracle_enthalpy(temperature,species)
    REAL(real64), INTENT(IN) :: temperature,species(6)
    REAL(real64), PARAMETER :: cp_dry=1004.5_real64,t0=273.15_real64
    REAL(real64), PARAMETER :: cp(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
      4190.0_real64,2106.0_real64,2106.0_real64]
    REAL(real64), PARAMETER :: h0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
      0.0_real64,-3.50e5_real64,-3.50e5_real64]

    oracle_enthalpy=(cp_dry+SUM(cp*species))*(temperature-t0)+SUM(h0*species)
  END FUNCTION oracle_enthalpy

  SUBROUTINE check_domain(state,expected1,expected2,expected3,message)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    LOGICAL, INTENT(IN) :: expected1,expected2,expected3
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check((state%above_ground(1,1,1).EQV.expected1) .AND. &
      (state%above_ground(1,1,2).EQV.expected2) .AND. &
      (state%above_ground(1,1,3).EQV.expected3),message)
  END SUBROUTINE check_domain

  LOGICAL FUNCTION budgets_equal(left,right)
    TYPE(pressure_analysis_budget), INTENT(IN) :: left,right
    budgets_equal=ALL(left%species_change_kg==right%species_change_kg) .AND. &
      ALL(left%mixing_ratio_change_kg==right%mixing_ratio_change_kg) .AND. &
      ALL(left%dry_mass_redistribution_kg==right%dry_mass_redistribution_kg) .AND. &
      left%dry_air_change_kg==right%dry_air_change_kg .AND. &
      left%enthalpy_change_j==right%enthalpy_change_j .AND. &
      left%geometry_mass_change_kg==right%geometry_mass_change_kg .AND. &
      left%enthalpy_composition_change_j==right%enthalpy_composition_change_j .AND. &
      left%enthalpy_mass_metric_change_j==right%enthalpy_mass_metric_change_j .AND. &
      left%total_mass_error_kg==right%total_mass_error_kg .AND. &
      left%max_cell_mass_error_kg==right%max_cell_mass_error_kg .AND. &
      left%accounted_cells==right%accounted_cells .AND. &
      left%incomplete_background_cells==right%incomplete_background_cells .AND. &
      left%incomplete_candidate_cells==right%incomplete_candidate_cells
  END FUNCTION budgets_equal

  SUBROUTINE make_state(state,surface_pressure)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), INTENT(IN) :: surface_pressure
    INTEGER :: status,reason

    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME, &
      'pressure-domain-budget-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64
    state%grid%dy=2200.0_real64
    state%pressure%value(1,1,:)=[100000.0_real32,95000.0_real32,90000.0_real32]
    CALL valid_real(state%pressure)
    state%surface_pressure%value=surface_pressure
    state%surface_temperature%value=290.0_real32
    CALL valid_surface_real(state%surface_pressure)
    CALL valid_surface_real(state%surface_temperature)
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'

    CALL invalidate_payload(state)
    CALL fill_active_payload(state)
    state%obs_support=0_int32
    state%hydro_support=0_int32
    state%balance_beta=0.0_real32
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    IF (status/=STATUS_OK) ERROR STOP 'domain-budget fixture is not canonical'
  END SUBROUTINE make_state

  SUBROUTINE invalidate_payload(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real32) :: missing

    missing=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL invalidate_real(state%temperature,missing)
    CALL invalidate_real(state%vapor,missing)
    CALL invalidate_real(state%u,missing)
    CALL invalidate_real(state%v,missing)
    CALL invalidate_real(state%omega,missing)
    CALL invalidate_real(state%cloud_water,missing)
    CALL invalidate_real(state%cloud_ice,missing)
    CALL invalidate_real(state%rain,missing)
    CALL invalidate_real(state%snow,missing)
    CALL invalidate_real(state%graupel,missing)
  END SUBROUTINE invalidate_payload

  SUBROUTINE fill_active_payload(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER :: k
    DO k=1,NZ
      IF (.NOT.state%above_ground(1,1,k)) CYCLE
      state%temperature%value(1,1,k)=280.0_real32+REAL(k,real32)
      state%vapor%value(1,1,k)=0.008_real32+0.001_real32*REAL(k,real32)
      state%cloud_water%value(1,1,k)=0.003_real32+0.0002_real32*REAL(k,real32)
      state%cloud_ice%value(1,1,k)=0.001_real32+0.0001_real32*REAL(k,real32)
      state%rain%value(1,1,k)=0.002_real32+0.0001_real32*REAL(k,real32)
      state%snow%value(1,1,k)=0.001_real32+0.0001_real32*REAL(k,real32)
      state%graupel%value(1,1,k)=0.001_real32+0.0001_real32*REAL(k,real32)
      state%u%value(1,1,k)=2.0_real32
      state%v%value(1,1,k)=-1.0_real32
      state%omega%value(1,1,k)=0.0_real32
      CALL mark_valid(state%temperature,k)
      CALL mark_valid(state%vapor,k)
      CALL mark_valid(state%cloud_water,k)
      CALL mark_valid(state%cloud_ice,k)
      CALL mark_valid(state%rain,k)
      CALL mark_valid(state%snow,k)
      CALL mark_valid(state%graupel,k)
      CALL mark_valid(state%u,k)
      CALL mark_valid(state%v,k)
      CALL mark_valid(state%omega,k)
    END DO
  END SUBROUTINE fill_active_payload

  SUBROUTINE perturb_active_payload(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER :: k
    DO k=1,NZ
      IF (.NOT.state%above_ground(1,1,k)) CYCLE
      state%temperature%value(1,1,k)=state%temperature%value(1,1,k)+0.75_real32
      state%vapor%value(1,1,k)=state%vapor%value(1,1,k)+0.0005_real32
      state%cloud_water%value(1,1,k)=state%cloud_water%value(1,1,k)+0.0001_real32
      state%cloud_ice%value(1,1,k)=state%cloud_ice%value(1,1,k)+0.0001_real32
      state%rain%value(1,1,k)=state%rain%value(1,1,k)+0.0001_real32
      state%snow%value(1,1,k)=state%snow%value(1,1,k)+0.0001_real32
      state%graupel%value(1,1,k)=state%graupel%value(1,1,k)+0.0001_real32
    END DO
  END SUBROUTINE perturb_active_payload

  SUBROUTINE mark_valid(field,k)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: k
    field%valid(1,1,k)=.TRUE.
    field%quality(1,1,k)=0_int32
    field%source(1,1,k)=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE mark_valid

  SUBROUTINE invalidate_real(field,missing)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: missing
    field%value=missing
    field%valid=.FALSE.
    field%quality=0_int32
    field%source=0_int32
  END SUBROUTINE invalidate_real

  SUBROUTINE invalidate_species_at(field,k)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: k
    field%value(1,1,k)=ieee_value(0.0_real32,ieee_quiet_nan)
    field%valid(1,1,k)=.FALSE.
    field%quality(1,1,k)=0_int32
    field%source(1,1,k)=0_int32
  END SUBROUTINE invalidate_species_at

  SUBROUTINE valid_real(field)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE valid_real

  SUBROUTINE valid_surface_real(field)
    USE cloud_bal_state, ONLY: field2d
    TYPE(field2d), INTENT(INOUT) :: field
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE valid_surface_real

END PROGRAM test_pressure_domain_budget
