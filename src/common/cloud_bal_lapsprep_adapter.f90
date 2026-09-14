! A typed payload must match the direct host-input reader before OFF transport.
MODULE cloud_bal_lapsprep_adapter
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32
  USE cloud_bal_state
  USE cloud_bal_stage_payload
  USE cloud_bal_stage_context
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: read_cloud_bal_lapsprep_payload
  PUBLIC :: cloud_bal_lapsprep_entry
CONTAINS
  SUBROUTINE cloud_bal_lapsprep_entry(context,state,longitude,status,reason)
    TYPE(stage_context), INTENT(IN) :: context
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real32), ALLOCATABLE, INTENT(INOUT) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status,reason
    CALL read_cloud_bal_lapsprep_payload(TRIM(context%input_path),context%input_identity, &
                                       state,longitude,status,reason)
    IF (status==STATUS_OK) PRINT *, 'LAPSPREP_CANONICAL_PAYLOAD_CONSUMED'
  END SUBROUTINE cloud_bal_lapsprep_entry
  SUBROUTINE read_cloud_bal_lapsprep_payload(input_path,expected,state,longitude,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: input_path
    TYPE(stage_payload_identity), INTENT(IN) :: expected
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real32), ALLOCATABLE, INTENT(INOUT) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(cloud_bal_stage_payload_type) :: payload

    CALL read_cloud_bal_stage_payload(input_path,expected,payload,status,reason)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (expected%dynamic_target_authorized) RETURN
    IF (ANY(payload%state%omega_target%valid) .OR. &
        ANY(payload%state%omega_target_sigma%valid)) RETURN
    reason=REASON_SHAPE
    IF (.NOT.ALLOCATED(longitude)) RETURN
    IF (.NOT.ALLOCATED(payload%longitude)) RETURN
    IF (ANY(SHAPE(longitude)/=SHAPE(payload%longitude))) RETURN
    reason=REASON_GATE
    IF (ANY(longitude/=payload%longitude)) RETURN
    IF (.NOT.canonical_states_equal(state,payload%state)) RETURN
    ! Use the verified exchange as the canonical input; host slabs are separate.
    state=payload%state
    longitude=payload%longitude
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_cloud_bal_lapsprep_payload
END MODULE cloud_bal_lapsprep_adapter
