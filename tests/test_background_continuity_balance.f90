PROGRAM test_background_continuity_balance
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=7,NY=7,NZ=4
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  INTEGER :: failures
  TYPE(cloud_bal_state_type) :: background,input,output,before,invalid_background
  TYPE(balance_operator_config) :: config
  TYPE(stage_result) :: result
  INTEGER :: status
  LOGICAL :: support(NX,NY,NZ),shell(NX,NY,NZ)
  LOGICAL :: local_shell(NX,NY,NZ)
  REAL(real64) :: ratio

  failures=0
  CALL make_state(background)
  CALL set_copied_boundaries(background)
  background%pressure%source=SOURCE_OUTPUT_ADAPTER
  background%u%source=SOURCE_ANALYZED_WIND
  background%v%source=SOURCE_ANALYZED_WIND
  background%omega%source=SOURCE_ANALYZED_WIND
  background%vapor%source=SOURCE_OUTPUT_ADAPTER
  background%cloud_water%source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
  background%cloud_ice%source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
  background%rain%source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
  background%snow%source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
  background%graupel%source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
  input=background
  support=.FALSE.
  support(3:5,3:5,:)=.TRUE.
  shell=.TRUE.
  ! A composition-only change creates a dry-air flux-divergence mismatch.
  input%vapor%value(4,4,2)=0.030_real32
  input%vapor%value(4,4,3)=0.018_real32
  CALL refresh_dry_air_mass_measure(input,status)
  CALL check(status==STATUS_OK,'candidate dry-air mass refreshed')
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_OK,'composition mismatch projects against background dry tendency')
  IF (result%status==STATUS_OK) THEN
    CALL check(ANY(output%u%value/=input%u%value),'projection changes horizontal u')
    CALL check(ANY(output%v%value/=input%v%value),'projection changes horizontal v')
    CALL check(ANY(output%omega%value/=input%omega%value),'projection changes omega')
    CALL check(ALL(support .OR. output%u%value==input%u%value) .AND. &
      ALL(support .OR. output%v%value==input%v%value) .AND. &
      ALL(support .OR. output%omega%value==input%omega%value), &
      'winds are unchanged outside control support')
    CALL check(ALL(output%u%valid .EQV. input%u%valid) .AND. &
      ALL(output%u%quality==input%u%quality) .AND. &
      ALL(output%v%valid .EQV. input%v%valid) .AND. &
      ALL(output%v%quality==input%v%quality) .AND. &
      ALL(output%omega%valid .EQV. input%omega%valid) .AND. &
      ALL(output%omega%quality==input%omega%quality), &
      'wind validity and quality metadata are unchanged')
    CALL check(ALL(output%omega_top_boundary%source==input%omega_top_boundary%source) .AND. &
      ALL(output%omega_bottom_boundary%source==input%omega_bottom_boundary%source) .AND. &
      ALL(output%omega_top_boundary%valid .EQV. input%omega_top_boundary%valid) .AND. &
      ALL(output%omega_bottom_boundary%valid .EQV. input%omega_bottom_boundary%valid), &
      'pressure boundary metadata is unchanged')
    CALL check(ALL(output%omega_top_boundary%value==input%omega_top_boundary%value) .AND. &
      ALL(output%omega_bottom_boundary%value==input%omega_bottom_boundary%value), &
      'fixed pressure boundary fields are unchanged')
    CALL check(ALL((IAND(output%u%source,SOURCE_BALANCE_OPERATOR)/=0_int32) .EQV. &
      (output%u%value/=input%u%value)), 'u provenance is added only at changed cells')
    CALL check(ALL((IAND(output%v%source,SOURCE_BALANCE_OPERATOR)/=0_int32) .EQV. &
      (output%v%value/=input%v%value)), 'v provenance is added only at changed cells')
    CALL check(ALL((IAND(output%omega%source,SOURCE_BALANCE_OPERATOR)/=0_int32) .EQV. &
      (output%omega%value/=input%omega%value)), 'omega provenance is added only at changed cells')
    ratio=result%numerical%continuity_candidate_rms / &
      MAX(result%numerical%continuity_background_rms,1.0e-30_real64)
    CALL check(ratio<=2.0e-3_real64,'rounded flux residual meets strict relative gate')
    CALL check(result%numerical%max_wind_increment<=10.0_real64 .AND. &
      result%numerical%max_omega_increment<=5.0_real64,'increment caps are honored')
  END IF

  config%fixed_omega_for_export=.TRUE.
  input=background
  input%u%value(4,4,2)=input%u%value(4,4,2)+0.1_real32
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_OK .AND. &
    (ANY(output%u%value/=input%u%value) .OR. ANY(output%v%value/=input%v%value)) .AND. &
    ALL(output%omega%value==input%omega%value), &
    'compatible continuity mismatch projects on exported U/V while omega stays fixed')

  input=background
  input%omega%value(4,4,2)=0.1_real32
  before=input
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SOLVER .AND. &
    result%numerical%solver_reason==SOLVER_INCOMPATIBLE_RHS .AND. &
    canonical_states_equal(output,before), &
    'omega-only continuity mismatch is rejected when exported horizontal DOFs cannot close it')
  config%fixed_omega_for_export=.FALSE.
  input=background

  invalid_background=background
  invalid_background%u%valid(4,4,2)=.FALSE.
  before=input
  CALL apply_background_continuity_balance(invalid_background,input,output,result,config,support,shell)
  CALL check(result%status/=STATUS_OK .AND. canonical_states_equal(output,before), &
    'input-valid but background-invalid wind cannot define a frozen tendency')

  invalid_background=background
  invalid_background%u%source=IOR(SOURCE_ANALYZED_WIND,SOURCE_COLUMN_PHYSICS)
  before=input
  CALL apply_background_continuity_balance(invalid_background,input,output,result,config, &
    support,shell)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
    canonical_states_equal(output,before), &
    'column-physics generated winds are rejected as a background prior')
  config%target_authority=TARGET_AUTHORITY_MANUFACTURED_TEST
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
    canonical_states_equal(output,before), 'manufactured-test target authority is rejected')
  config%target_authority=TARGET_AUTHORITY_OBSERVATIONAL

  input%omega_top_boundary%value(4,4)=input%omega_top_boundary%value(4,4)+0.1_real32
  before=input
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
    canonical_states_equal(output,before), 'changed copied boundary value rejects atomically')

  ! A remote composition change has zero flux tendency here because winds are
  ! zero there. The producer must still reject it instead of taking the
  ! local-shell no-op path while leaving an unrepresented dry-air fraction.
  input=background
  input%vapor%value(1,1,2)=0.025_real32
  CALL refresh_dry_air_mass_measure(input,status)
  CALL check(status==STATUS_OK,'refresh remote composition fixture')
  local_shell=.FALSE.; local_shell(2:6,2:6,:)=.TRUE.
  before=input
  CALL apply_background_continuity_balance(background,input,output,result,config, &
    support,local_shell)
  CALL check(result%status==STATUS_DEGRADED .AND. result%reason_code==REASON_GATE .AND. &
    canonical_states_equal(output,before), &
    'outside-shell dry-fraction change rejects atomically before a local no-op')

  input=background
  before=input
  CALL apply_background_continuity_balance(background,input,output,result,config, &
    support(:,:,:NZ-1),shell)
  CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(output,before), &
    'malformed support shape rejects atomically')

  before=input
  background%grid%dx(1,1)=background%grid%dx(1,1)*1.01_real64
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(output,before), &
    'incompatible background geometry rejects atomically')
  background=input

  input%vapor%value(4,4,2)=ieee_value(0.0_real32,ieee_quiet_nan)
  before=input
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(output,before), &
    'nonfinite candidate rejects atomically')
  input=before

  before=input
  shell=.FALSE.; shell(4,4,:)=.TRUE.
  CALL apply_background_continuity_balance(background,input,output,result,config,support,shell)
  CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(output,before), &
    'incomplete face validation shell rejects atomically')

  IF (failures/=0) THEN
    PRINT '(A,I0)','Background continuity balance tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Background continuity balance tests passed'

CONTAINS

  SUBROUTINE check(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      failures=failures+1
      PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: status,i,j,k
    REAL(real64) :: pi

    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME,'background-continuity-test',status)
    CALL check(status==STATUS_OK,'initialize state')
    IF (status/=STATUS_OK) RETURN
    pi=ACOS(-1.0_real64)
    state%grid%dx=1500.0_real64
    state%grid%dy=1800.0_real64
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0; state%surface_temperature%quality=0
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0; state%omega_bottom_boundary%quality=0
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      state%pressure%value(i,j,k)=REAL(95000.0_real64-10000.0_real64*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=0.0_real32
      state%v%value(i,j,k)=0.0_real32
      state%omega%value(i,j,k)=0.0_real32
      state%geopotential%value(i,j,k)=1000.0_real32
      IF (i==4 .AND. j==4) THEN
        state%u%value(i,j,k)=REAL(3.0_real64*SIN(pi*k/NZ),real32)
        state%v%value(i,j,k)=REAL(-2.0_real64*COS(pi*k/(NZ+1)),real32)
        state%omega%value(i,j,k)=REAL(0.7_real64*SIN(pi*k/(NZ+1)),real32)
      END IF
    END DO; END DO; END DO
    CALL mark_valid(state%pressure); CALL mark_valid(state%temperature)
    CALL mark_valid(state%vapor); CALL mark_valid(state%u); CALL mark_valid(state%v)
    CALL mark_valid(state%omega); CALL mark_valid(state%geopotential)
    state%cloud_water%value=0.0_real32; state%cloud_ice%value=0.0_real32
    state%rain%value=0.0_real32; state%snow%value=0.0_real32
    state%graupel%value=0.0_real32
    CALL mark_valid(state%cloud_water); CALL mark_valid(state%cloud_ice)
    CALL mark_valid(state%rain); CALL mark_valid(state%snow); CALL mark_valid(state%graupel)
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_OK,'configure pressure geometry')
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_OK,'refresh background dry-air mass')
  END SUBROUTINE make_state

  SUBROUTINE mark_valid(field)
    TYPE(field3d), INTENT(INOUT) :: field
    field%valid=.TRUE.; field%quality=0_int32; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE mark_valid

  SUBROUTINE set_copied_boundaries(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER :: i,j,k,bottom_level
    INTEGER(int32), PARAMETER :: copied_quality= &
      IOR(QUALITY_LEGACY_PROVENANCE,QUALITY_BOUNDARY_INTERIOR_COPY)
    DO j=1,NY; DO i=1,NX
      state%omega_top_boundary%value(i,j)=state%omega%value(i,j,NZ)
      bottom_level=0
      DO k=1,NZ
        IF (state%above_ground(i,j,k)) THEN
          bottom_level=k
          EXIT
        END IF
      END DO
      IF (bottom_level==0) ERROR STOP 'no usable bottom omega level'
      state%omega_bottom_boundary%value(i,j)=state%omega%value(i,j,bottom_level)
    END DO; END DO
    state%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    state%omega_bottom_boundary%source=SOURCE_ANALYZED_WIND
    state%omega_top_boundary%quality=copied_quality
    state%omega_bottom_boundary%quality=copied_quality
  END SUBROUTINE set_copied_boundaries

END PROGRAM test_background_continuity_balance
