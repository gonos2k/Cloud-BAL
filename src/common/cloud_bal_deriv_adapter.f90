! Export only after the separate producer invocation has terminated and its
! coordinator has verified/detached the complete direct-product closure.
MODULE cloud_bal_deriv_adapter
  USE, INTRINSIC :: iso_fortran_env, ONLY: int64
  USE cloud_bal_state
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,read_lco_evidence
  USE cloud_bal_stage_payload
  USE cloud_bal_stage_context
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: run_cloud_bal_deriv_payload
  PUBLIC :: cloud_bal_deriv_entry
CONTAINS
  SUBROUTINE cloud_bal_deriv_entry(enabled,status)
    LOGICAL, INTENT(OUT) :: enabled
    INTEGER, INTENT(OUT) :: status
    TYPE(stage_context) :: context
    INTEGER :: reason
    CALL read_stage_context('deriv','EXPORT_OFF',context,enabled,status,reason)
    IF (status/=STATUS_OK .OR. .NOT.enabled) RETURN
    CALL run_cloud_bal_deriv_payload(TRIM(context%source_root),context%stamp, &
      TRIM(context%output_path),context%output_identity,status,reason)
    IF (status==STATUS_OK) PRINT *, 'DERIV_EXPORT_OFF_PAYLOAD_WRITTEN'
  END SUBROUTINE cloud_bal_deriv_entry
  SUBROUTINE run_cloud_bal_deriv_payload(source_root,stamp,output_path,expected,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: source_root,stamp,output_path
    TYPE(stage_payload_identity), INTENT(IN) :: expected
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(cloud_bal_stage_payload_type) :: payload
    CHARACTER(LEN=:), ALLOCATABLE :: products

    status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (expected%dynamic_target_authorized) RETURN
    reason=REASON_METADATA
    IF (LEN_TRIM(stamp)/=9 .OR. VERIFY(TRIM(stamp),'0123456789')/=0) RETURN
    IF (LEN_TRIM(source_root)<2 .OR. source_root(1:1)/='/') RETURN
    products=TRIM(source_root)//'/lapsprd/'
    ! Analysis products build this state. The separately verified FUA/FSF roles
    ! remain provenance/background evidence, never substituted into analysis.
    CALL read_real_shadow_state('','', &
      products//'lw3/'//stamp//'.lw3',products//'vrz/'//stamp//'.vrz', &
      products//'vrt/'//stamp//'.vrt',TRIM(source_root)//'/static/static.nest7grid', &
      expected%valid_time,payload%state,payload%longitude,status,reason, &
      lt1_path=products//'lt1/'//stamp//'.lt1',lq3_path=products//'lq3/'//stamp//'.lq3', &
      lwc_path=products//'lwc/'//stamp//'.lwc',lsx_path=products//'lsx/'//stamp//'.lsx', &
      lcp_path=products//'lcp/'//stamp//'.lcp',lty_path=products//'lty/'//stamp//'.lty')
    IF (status/=STATUS_OK) RETURN
    CALL read_lco_evidence(products//'lco/'//stamp//'.lco',expected%valid_time, &
                          payload%state,payload%cloud_omega_evidence,status,reason)
    IF (status/=STATUS_OK) RETURN
    payload%identity=expected
    CALL write_cloud_bal_stage_payload(output_path,payload,status,reason)
  END SUBROUTINE run_cloud_bal_deriv_payload
END MODULE cloud_bal_deriv_adapter
