! Explicit state-carrying OFF transport; no legacy QBAL numerical entry.
MODULE cloud_bal_balance_adapter
  USE cloud_bal_state
  USE cloud_bal_pipeline
  USE cloud_bal_stage_payload
  USE cloud_bal_stage_context
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: run_cloud_bal_balance_payload
  PUBLIC :: cloud_bal_balance_entry
CONTAINS
  SUBROUTINE cloud_bal_balance_entry(enabled,status)
    LOGICAL, INTENT(OUT) :: enabled
    INTEGER, INTENT(OUT) :: status
    TYPE(stage_context) :: context
    INTEGER :: reason
    CALL read_stage_context('balance','OFF',context,enabled,status,reason)
    IF (status/=STATUS_OK .OR. .NOT.enabled) RETURN
    CALL run_cloud_bal_balance_payload(TRIM(context%input_path),TRIM(context%output_path), &
      context%input_identity,context%output_identity,status,reason)
    IF (status==STATUS_OK) PRINT *, 'BALANCE_CANONICAL_OFF_PAYLOAD_WRITTEN'
  END SUBROUTINE cloud_bal_balance_entry
  SUBROUTINE run_cloud_bal_balance_payload(input_path,output_path,expected_input, &
                                            expected_output,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: input_path,output_path
    TYPE(stage_payload_identity), INTENT(IN) :: expected_input,expected_output
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(cloud_bal_stage_payload_type) :: incoming,outgoing
    TYPE(cloud_bal_state_type) :: candidate,operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result

    status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (expected_input%dynamic_target_authorized .OR. &
        expected_output%dynamic_target_authorized) RETURN
    CALL read_cloud_bal_stage_payload(input_path,expected_input,incoming,status,reason)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (ANY(incoming%state%omega_target%valid) .OR. &
        ANY(incoming%state%omega_target_sigma%valid)) RETURN
    config%requested_mode=MODE_OFF
    CALL run_cloud_bal_pipeline(incoming%state,candidate,operational,result,config)
    status=STATUS_FAILED; reason=result%reason_code
    IF (result%status/=STATUS_OK) RETURN
    reason=REASON_GATE
    IF (.NOT.canonical_states_equal(incoming%state,candidate) .OR. &
        .NOT.canonical_states_equal(incoming%state,operational)) RETURN
    outgoing=incoming
    outgoing%state=candidate
    outgoing%identity=expected_output
    CALL write_cloud_bal_stage_payload(output_path,outgoing,status,reason)
  END SUBROUTINE run_cloud_bal_balance_payload
END MODULE cloud_bal_balance_adapter
