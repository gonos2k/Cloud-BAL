! Parse only the coordinator's explicit stage contract. This module does not
! verify file hashes: the detached-runtime coordinator owns that boundary.
MODULE cloud_bal_stage_context
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED,REASON_NONE,REASON_METADATA,REASON_AUTHORITY
  USE cloud_bal_stage_payload, ONLY: stage_payload_identity
  IMPLICIT NONE
  PRIVATE
  TYPE, PUBLIC :: stage_context
    CHARACTER(LEN=1024) :: source_root='',input_path='',output_path=''
    CHARACTER(LEN=9) :: stamp=''
    TYPE(stage_payload_identity) :: input_identity,output_identity
  END TYPE stage_context
  PUBLIC :: read_stage_context
CONTAINS
  SUBROUTINE read_stage_context(expected_stage,expected_mode,context,enabled,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: expected_stage,expected_mode
    TYPE(stage_context), INTENT(OUT) :: context
    LOGICAL, INTENT(OUT) :: enabled
    INTEGER, INTENT(OUT) :: status,reason
    CHARACTER(LEN=32) :: environment_mode,mode,stage
    CHARACTER(LEN=1024) :: context_path,source_root,input_path,output_path
    CHARACTER(LEN=9) :: stamp
    TYPE(stage_payload_identity) :: input_identity,output_identity
    INTEGER :: length,rc,unit
    NAMELIST /cloud_bal_stage_context_nl/ mode,stage,source_root,input_path,output_path, &
      stamp,input_identity,output_identity

    enabled=.FALSE.; status=STATUS_OK; reason=REASON_NONE
    environment_mode=''
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_STAGE_MODE',environment_mode,LENGTH=length,STATUS=rc)
    IF (rc==1 .OR. length==0) RETURN
    enabled=.TRUE.; status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (rc/=0 .OR. TRIM(environment_mode)/=expected_mode) RETURN
    context_path=''
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_STAGE_CONTEXT',context_path,LENGTH=length,STATUS=rc)
    reason=REASON_METADATA
    IF (rc/=0 .OR. length==0 .OR. context_path(1:1)/='/') RETURN
    mode=''; stage=''; source_root=''; input_path=''; output_path=''; stamp=''
    input_identity=stage_payload_identity(); output_identity=stage_payload_identity()
    OPEN(NEWUNIT=unit,FILE=TRIM(context_path),STATUS='old',ACTION='read',IOSTAT=rc)
    IF (rc/=0) RETURN
    READ(unit,NML=cloud_bal_stage_context_nl,IOSTAT=rc)
    CLOSE(unit)
    IF (rc/=0 .OR. TRIM(stage)/=expected_stage .OR. TRIM(mode)/=expected_mode) RETURN
    IF (input_identity%dynamic_target_authorized .OR. output_identity%dynamic_target_authorized) RETURN
    IF (expected_stage=='deriv') THEN
      IF (source_root(1:1)/='/' .OR. output_path(1:1)/='/') RETURN
    ELSE IF (expected_stage=='balance') THEN
      IF (input_path(1:1)/='/' .OR. output_path(1:1)/='/') RETURN
    ELSE IF (expected_stage=='lapsprep') THEN
      IF (source_root(1:1)/='/' .OR. input_path(1:1)/='/') RETURN
    ELSE
      RETURN
    END IF
    IF (LEN_TRIM(stamp)/=9 .OR. VERIFY(stamp,'0123456789')/=0) RETURN
    context%source_root=source_root; context%input_path=input_path; context%output_path=output_path
    context%stamp=stamp; context%input_identity=input_identity; context%output_identity=output_identity
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_stage_context
END MODULE cloud_bal_stage_context
