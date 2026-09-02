PROGRAM real_shadow_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_pipeline
  USE cloud_bal_balance_operator
  USE cloud_bal_real_netcdf
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: input,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  TYPE(balance_operator_type) :: op
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_file,output,time_text
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status,operational_differences

  IF (COMMAND_ARGUMENT_COUNT()/=8) ERROR STOP &
    'usage: driver FUA FSF LW3 VRZ VRT STATIC OUTPUT VALID_TIME_EPOCH'
  CALL GET_COMMAND_ARGUMENT(1,fua); CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3); CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt); CALL GET_COMMAND_ARGUMENT(6,static_file)
  CALL GET_COMMAND_ARGUMENT(7,output); CALL GET_COMMAND_ARGUMENT(8,time_text)
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid-time epoch'

  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                              TRIM(static_file),valid_time,input,longitude,status,reason)
  IF (status/=STATUS_OK) THEN
    WRITE(*,'(A,I0,A,I0)') 'adapter_status=',status,',reason=',reason
    ERROR STOP 2
  END IF

  config%requested_mode=MODE_SHADOW
  config%horizontal_support_radius_m=10000.0_real64
  config%pressure_support_radius_pa=20000.0_real64
  config%balance%maximum_iterations=800
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  operational_differences=core_value_differences(input,operational)
  IF (operational_differences/=0) ERROR STOP 'SHADOW changed operational state'
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'pipeline_status=',result%status, &
    ',reason=',result%reason_code,',column=',result%column%status, &
    ',balance=',result%balance%status
  WRITE(*,'(A,I0,A,ES24.16)') 'transport_required_substeps=', &
    result%column%numerical%transport_required_substeps,',flux_ledger_error=', &
    result%column%numerical%ledger_error
  IF (result%column%status/=STATUS_OK .OR. &
      (result%balance%numerical%solver_reason/=SOLVER_CONVERGED .AND. &
       result%balance%numerical%solver_reason/=SOLVER_NOT_RUN)) &
    ERROR STOP 'no diagnostic proposal is available'

  CALL build_balance_operator(candidate,config%balance,op,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'diagnostic operator build failed'
  ALLOCATE(residual_before(input%grid%nx,input%grid%ny,input%grid%nz), &
           residual_after(input%grid%nx,input%grid%ny,input%grid%nz))
  CALL state_continuity_residual(op,input,residual_before,status)
  IF (status/=STATUS_OK) ERROR STOP 'background residual failed'
  CALL state_continuity_residual(op,candidate,residual_after,status)
  IF (status/=STATUS_OK) ERROR STOP 'candidate residual failed'
  CALL write_shadow_diagnostics(TRIM(output),input,candidate,longitude,result,config, &
                                residual_before,residual_after,status,operational)
  IF (status/=STATUS_OK) ERROR STOP 'diagnostic write failed'

  WRITE(*,'(A,I0)') 'radar_cells=',COUNT(input%radar_reflectivity%valid)
  WRITE(*,'(A,I0)') 'column_changed_cells=',COUNT(result%column%changed)
  WRITE(*,'(A,I0)') 'balance_changed_cells=',COUNT(result%balance%changed)
  WRITE(*,'(A,I0)') 'overall_changed_cells=',COUNT(result%overall%changed)
  WRITE(*,'(A,I0)') 'operational_core_differences=',operational_differences
  WRITE(*,'(A,I0,A,I0)') 'solver_reason=', &
    result%balance%numerical%solver_reason,',iterations=', &
    result%balance%numerical%solver_iterations
  WRITE(*,'(A,I0)') 'acceptance_failures=', &
    result%balance%numerical%acceptance_failures
  WRITE(*,'(A,ES24.16)') 'trust_region_fraction=', &
    result%balance%numerical%trust_region_fraction
  WRITE(*,'(A,ES24.16)') 'target_response_failure_fraction=', &
    result%balance%numerical%target_response_failure_fraction
  WRITE(*,'(A,ES24.16)') 'max_wind_increment_ms=', &
    result%balance%numerical%max_wind_increment
  WRITE(*,'(A,ES24.16)') 'max_omega_increment_pas=', &
    result%balance%numerical%max_omega_increment
  WRITE(*,'(A,ES24.16)') 'continuity_background_rms=', &
    result%balance%numerical%continuity_background_rms
  WRITE(*,'(A,ES24.16)') 'continuity_projected_increment_rms=', &
    result%balance%numerical%continuity_projected_increment_rms
  WRITE(*,'(A,ES24.16)') 'continuity_candidate_rms=', &
    result%balance%numerical%continuity_candidate_rms
  WRITE(*,'(A,ES24.16)') 'flux_ledger_error=', &
    result%column%numerical%ledger_error
  IF (result%status==STATUS_OK) THEN
    WRITE(*,'(A)') 'hydrometeor_engineering_decision=VALID'
    WRITE(*,'(A)') 'trajectory_science_decision=BLOCKED_MISSING_STORM_MOTION'
    WRITE(*,'(A)') 'dynamic_balance_decision=NOT_AUTHORIZED'
  ELSE
    WRITE(*,'(A)') 'hydrometeor_engineering_decision=REJECTED'
    ERROR STOP 3
  END IF

CONTAINS

  INTEGER FUNCTION core_value_differences(left,right)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    core_value_differences= &
      real_value_differences(left%u%value,right%u%value)+ &
      real_value_differences(left%v%value,right%v%value)+ &
      real_value_differences(left%omega%value,right%omega%value)+ &
      real_value_differences(left%cloud_water%value,right%cloud_water%value)+ &
      real_value_differences(left%cloud_ice%value,right%cloud_ice%value)+ &
      real_value_differences(left%rain%value,right%rain%value)+ &
      real_value_differences(left%snow%value,right%snow%value)+ &
      real_value_differences(left%graupel%value,right%graupel%value)
  END FUNCTION core_value_differences

  INTEGER FUNCTION real_value_differences(left,right)
    REAL(real32), INTENT(IN) :: left(:,:,:),right(:,:,:)
    INTEGER :: i,j,k
    real_value_differences=0
    DO k=1,SIZE(left,3); DO j=1,SIZE(left,2); DO i=1,SIZE(left,1)
      IF (TRANSFER(left(i,j,k),0_int32)/=TRANSFER(right(i,j,k),0_int32)) &
        real_value_differences=real_value_differences+1
    END DO; END DO; END DO
  END FUNCTION real_value_differences
END PROGRAM real_shadow_driver
