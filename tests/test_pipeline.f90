PROGRAM test_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_pipeline
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: input,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  INTEGER :: failures

  failures=0
  CALL make_state(input)
  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK,'OFF must be a successful no-op',failures)
  CALL check(same_rain_bits(input,operational),'OFF must preserve operational bits',failures)

  CALL add_radar_cell(input)
  config%requested_mode=MODE_SHADOW
  config%horizontal_support_radius_m=2500.0_real64
  config%balance%required_residual_fraction=0.50_real64
  config%balance%maximum_target_cancellation_fraction=2.0_real64
  config%balance%momentum_absolute_tolerance=1.0_real64
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. ANY(candidate%rain%value>0.0_real32), &
             'SHADOW must calculate the radar candidate',failures)
  CALL check(same_rain_bits(input,operational), &
             'SHADOW must not change operational state',failures)
  CALL check(ABS(candidate%balance_beta(2,2,3)-1.0_real32)<=TINY(1.0_real32) .AND. &
             ABS(candidate%balance_beta(4,4,3))<=TINY(1.0_real32), &
             'balance support must be compact around observed/hydro support',failures)

  config%requested_mode=2
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
             'this research build must reject every active request',failures)
  CALL check(same_rain_bits(input,operational),'authority rejection must rollback',failures)

  input%precipitation_phase%valid(2,2,3)=.TRUE.
  input%precipitation_phase%quality(2,2,3)=0_int32
  input%precipitation_phase%source(2,2,3)=SOURCE_CLOUD_ANALYSIS
  input%precipitation_phase%value(2,2,3)=99_int32
  config%requested_mode=MODE_SHADOW
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. same_rain_bits(input,operational), &
             'non-OK shadow stage must preserve operational state',failures)

  IF (failures/=0) THEN
    PRINT *,'Pipeline tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Cloud-BAL pipeline authority tests passed'

CONTAINS

  SUBROUTINE check(condition,message,count)
    LOGICAL,INTENT(IN) :: condition
    CHARACTER(LEN=*),INTENT(IN) :: message
    INTEGER,INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type),INTENT(OUT) :: state
    INTEGER :: i,j,k,status
    CALL initialize_cloud_bal_state(state,4,4,3,1788224400_int64,'pipeline-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    DO k=1,3; DO j=1,4; DO i=1,4
      state%grid%dx(i,j)=2000.0_real64
      state%grid%dy(i,j)=2200.0_real64
      state%grid%dp(i,j,k)=15000.0_real64
      state%grid%cell_measure(i,j,k)=state%grid%dx(i,j)*state%grid%dy(i,j)* &
                                     state%grid%dp(i,j,k)/9.80665_real64
      state%pressure%value(i,j,k)=REAL(95000-15000*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=0.0_real32
      state%v%value(i,j,k)=0.0_real32
      state%omega%value(i,j,k)=0.0_real32
      state%geopotential%value(i,j,k)=1000.0_real32
      state%cloud_fraction%value(i,j,k)=0.0_real32
      state%cloud_type%value(i,j,k)=0_int32
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    state%cloud_type%valid=.TRUE.; state%cloud_type%quality=0_int32
    state%cloud_type%source=SOURCE_CLOUD_ANALYSIS
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32; state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BACKGROUND_MODEL
    state%omega_bottom_boundary%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE make_state

  SUBROUTINE valid_real(field,source)
    TYPE(field3d),INTENT(INOUT) :: field
    INTEGER(int32),INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE add_radar_cell(state)
    TYPE(cloud_bal_state_type),INTENT(INOUT) :: state
    state%radar_reflectivity%valid(2,2,3)=.TRUE.
    state%radar_reflectivity%quality(2,2,3)=0_int32
    state%radar_reflectivity%source(2,2,3)=SOURCE_RADAR_DBZ
    state%radar_reflectivity%value(2,2,3)=30.0_real32
  END SUBROUTINE add_radar_cell

  LOGICAL FUNCTION same_rain_bits(left,right)
    TYPE(cloud_bal_state_type),INTENT(IN) :: left,right
    INTEGER(int32),ALLOCATABLE :: a(:),b(:)
    a=TRANSFER(left%rain%value,[0_int32],SIZE(left%rain%value))
    b=TRANSFER(right%rain%value,[0_int32],SIZE(right%rain%value))
    same_rain_bits=ALL(a==b)
  END FUNCTION same_rain_bits

END PROGRAM test_pipeline
