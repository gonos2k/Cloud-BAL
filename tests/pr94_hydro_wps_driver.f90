PROGRAM pr94_hydro_wps_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,int64,real32
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  USE pr94_hydro_wps_hook, ONLY: write_pr94_hydro_wps
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: background
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  CHARACTER(LEN=2048) :: arg(16)
  INTEGER :: i,status,reason
  INTEGER(int64) :: valid_time

  IF (COMMAND_ARGUMENT_COUNT()/=16) ERROR STOP &
    'usage: pr94-hydro-wps FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH HYDRO.nc OUTPUT.wps WITNESS.raw'
  DO i=1,16
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*) valid_time
  IF (valid_time/=1786885200_int64) ERROR STOP 'input epoch is not 2026-08-16 13 UTC'
  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)),TRIM(arg(4)), &
    TRIM(arg(5)),TRIM(arg(6)),valid_time,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) ERROR STOP 'same13 frozen producer background reader failed'
  CALL write_pr94_hydro_wps(TRIM(arg(14)),background,TRIM(arg(15)),TRIM(arg(16)),status)
  IF (status/=STATUS_OK) ERROR STOP 'actual HYDRO candidate failed existing WPS mapper/writer'
  WRITE(*,'(A)') 'status=PASS_PR94_HYDRO_WPS'
  WRITE(*,'(A)') 'science_authority=NONE'
END PROGRAM pr94_hydro_wps_driver
