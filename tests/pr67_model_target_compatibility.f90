PROGRAM pr67_model_target_compatibility
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,model_dynamic_target_is_resolved
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,read_model_omega_increment
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state,before
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  INTEGER(int64) :: valid_time,target_cells,coverage_cells,authorized_cells,sigma_cells
  INTEGER :: input_status,input_reason,target_status,expected_acceptance
  CHARACTER(LEN=2048) :: fua,fsf,lw3,vrz,vrt,static_path,time_text,target_path,expected_text

  IF (COMMAND_ARGUMENT_COUNT()/=9) ERROR STOP &
    'usage: pr67-model-target FUA FSF LW3 VRZ VRT STATIC VALID_TIME TARGET EXPECT_ACCEPT'
  CALL GET_COMMAND_ARGUMENT(1,fua); CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3); CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt); CALL GET_COMMAND_ARGUMENT(6,static_path)
  CALL GET_COMMAND_ARGUMENT(7,time_text); CALL GET_COMMAND_ARGUMENT(8,target_path)
  CALL GET_COMMAND_ARGUMENT(9,expected_text)
  READ(time_text,*) valid_time
  READ(expected_text,*) expected_acceptance
  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
    TRIM(static_path),valid_time,state,longitude,input_status,input_reason)
  IF (input_status/=STATUS_OK) ERROR STOP 'retained real input reader failed'
  before=state
  CALL read_model_omega_increment(TRIM(target_path),state,longitude,target_status)
  PRINT '(A,I0)', 'model_target_reader_status=',target_status

  IF (expected_acceptance==1) THEN
    IF (target_status/=STATUS_OK) ERROR STOP 'expected paired model target was rejected'
    target_cells=COUNT(model_dynamic_target_is_resolved(state%omega_target%value, &
      state%omega_target%valid,state%omega_target%quality,state%omega_target%source) .AND. &
      state%above_ground,KIND=int64)
    authorized_cells=COUNT(model_dynamic_target_is_resolved(state%omega_target%value, &
      state%omega_target%valid,state%omega_target%quality,state%omega_target%source) .AND. &
      state%model_target_coverage,KIND=int64)
    coverage_cells=COUNT(state%model_target_coverage,KIND=int64)
    sigma_cells=COUNT(state%omega_target_sigma%valid .AND. state%above_ground,KIND=int64)
    IF (target_cells/=892338_int64 .OR. authorized_cells/=target_cells) &
      ERROR STOP 'accepted model target mask or authority count changed'
    IF (coverage_cells/=1150134_int64) ERROR STOP 'model target coverage count changed'
    IF (sigma_cells/=0_int64) ERROR STOP 'model target invented observational sigma'
    PRINT '(A,I0)', 'model_target_authorized_cells=',authorized_cells
    PRINT '(A,I0)', 'model_target_coverage_cells=',coverage_cells
    PRINT '(A,I0)', 'model_target_observational_sigma_cells=',sigma_cells
    PRINT '(A)', 'model_target_integration=PASS_SCOPED'
  ELSE
    IF (target_status==STATUS_OK) ERROR STOP 'invalid paired model target was accepted'
    IF (ANY(state%omega_target%value/=before%omega_target%value) .OR. &
        ANY(state%omega_target%valid .NEQV. before%omega_target%valid) .OR. &
        ANY(state%omega_target%quality/=before%omega_target%quality) .OR. &
        ANY(state%omega_target%source/=before%omega_target%source) .OR. &
        ANY(state%model_target_coverage .NEQV. before%model_target_coverage)) &
      ERROR STOP 'rejected paired model target mutated the retained state'
    PRINT '(A,I0)', 'rejected_model_target_status=',target_status
    PRINT '(A)', 'rejected_model_target_transaction=PASS'
  END IF
  PRINT '(A)', 'scope=paired-model-target reader compatibility only; no radar source, phase, or physical joint contract admitted'
END PROGRAM pr67_model_target_compatibility
