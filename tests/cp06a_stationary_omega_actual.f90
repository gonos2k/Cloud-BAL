PROGRAM cp06a_stationary_omega_actual
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator, ONLY: diagnose_stationary_omega,DIAGNOSTIC_REASON_INCOMPATIBLE_BOUNDARY
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE
  INTEGER, PARAMETER :: I0=100,I1=107,J0=130,J1=137
  TYPE(cloud_bal_state_type) :: background,candidate
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  LOGICAL, ALLOCATABLE :: control(:,:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_path,time_text,output_path
  CHARACTER(LEN=32) :: output_schema
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status,nx,ny,nz,output_unit,io_write
  REAL(real64) :: maximum_residual,boundary_mismatch,maximum_increment
  INTEGER(int64) :: changed_cells

  IF (COMMAND_ARGUMENT_COUNT()/=8) ERROR STOP &
    'usage: producer FUA FSF LW3 VRZ VRT STATIC VALID_TIME_EPOCH OMEGA_OUTPUT'
  CALL GET_COMMAND_ARGUMENT(1,fua); CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3); CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt); CALL GET_COMMAND_ARGUMENT(6,static_path)
  CALL GET_COMMAND_ARGUMENT(7,time_text); CALL GET_COMMAND_ARGUMENT(8,output_path)
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid time'
  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
    TRIM(static_path),valid_time,background,longitude,status,reason)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) THEN
    WRITE(*,'(A,I0,A,I0)') 'input_status=',status,' reason=',reason
    ERROR STOP 'real background reader failed'
  END IF
  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  IF (I1>nx .OR. J1>ny) ERROR STOP 'predeclared spatial support exceeds input grid'
  ALLOCATE(control(nx,ny,nz)); control=.FALSE.
  control(I0:I1,J0:J1,:)=background%above_ground(I0:I1,J0:J1,:)
  CALL diagnose_stationary_omega(background,control,candidate,maximum_residual, &
    boundary_mismatch,status,reason)
  changed_cells=COUNT(control .AND. &
    (candidate%omega%value/=background%omega%value),KIND=int64)
  maximum_increment=MAXVAL(ABS(REAL(candidate%omega%value-background%omega%value,real64)), &
    MASK=control)
  WRITE(*,'(A,I0,A,I0,A,I0)') 'grid=',nx,'x',ny,'x',nz
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'fixed_control=i:',I0,':',I1,',j:',J0,':',J1
  WRITE(*,'(A,I0,A,I0)') 'producer_status=',status,' reason=',reason
  WRITE(*,'(A,I0)') 'control_cells=',COUNT(control,KIND=int64)
  WRITE(*,'(A,I0)') 'changed_omega_cells=',changed_cells
  WRITE(*,'(A,ES24.16)') 'maximum_omega_increment_Pa_s-1=',maximum_increment
  IF (reason==DIAGNOSTIC_REASON_INCOMPATIBLE_BOUNDARY) THEN
    WRITE(*,'(A)') 'stored_continuity_residual=NOT_ASSESSED (fixed-boundary fail-fast)'
    WRITE(*,'(A,ES24.16)') 'fixed_boundary_mismatch_through_first_failure_kg_s=',boundary_mismatch
  ELSE
    WRITE(*,'(A,ES24.16)') 'maximum_stored_continuity_residual_kg_s=',maximum_residual
    WRITE(*,'(A,ES24.16)') 'maximum_fixed_boundary_mismatch_kg_s=',boundary_mismatch
  END IF
  WRITE(*,'(A)') 'authority=background_Barnes_winds_and_fixed_input_boundaries'
  WRITE(*,'(A)') 'tendency=stationary_zero; measure=represented_dry_air_mass_flux'
  WRITE(*,'(A)') 'acceptance=diagnostic_only; no_observed_omega_target_or_sigma'
  IF (status/=STATUS_OK) THEN
    IF (.NOT.canonical_states_equal(background,candidate)) &
      ERROR STOP 'failed producer did not roll back the whole state'
    WRITE(*,'(A)') 'candidate_outcome=REJECTED; no candidate artifact written'
    STOP
  END IF
  IF (changed_cells==0_int64) ERROR STOP 'accepted spatial producer returned zero increment'
  output_schema='CP06A_OMEGA_V1'
  OPEN(NEWUNIT=output_unit,FILE=TRIM(output_path),STATUS='REPLACE', &
    FORM='UNFORMATTED',ACCESS='STREAM',ACTION='WRITE',IOSTAT=io_write)
  IF (io_write/=0) ERROR STOP 'unable to create candidate artifact'
  WRITE(output_unit,IOSTAT=io_write) output_schema,nx,ny,nz,valid_time
  IF (io_write==0) WRITE(output_unit,IOSTAT=io_write) control, &
    candidate%omega%value,candidate%omega%valid,candidate%omega%quality,candidate%omega%source
  CLOSE(output_unit)
  IF (io_write/=0) ERROR STOP 'candidate artifact write failed'
  WRITE(*,'(A)') 'candidate_outcome=DIAGNOSTIC_ONLY; no observational authority inferred'
  WRITE(*,'(A)') 'artifact_schema=CP06A_OMEGA_V1; stores full omega field and control mask'
END PROGRAM cp06a_stationary_omega_actual
