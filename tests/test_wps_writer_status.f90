PROGRAM test_wps_writer_status
  USE setup
  USE lapsprep_wps,ONLY: output_ungrib_format
  IMPLICIT NONE
  REAL :: p(2),a3(2,2,2),a2(2,2)
  INTEGER :: status
  CHARACTER(LEN=256) :: root

  CALL get_command_argument(1,root)
  IF (LEN_TRIM(root)==0) ERROR STOP 'test root is required'
  p=(/500.0,1000.0/)
  a3=1.0
  a2=1.0

  laps_data_root=TRIM(root)//'/missing-parent'
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status)
  IF (status/=0) ERROR STOP 'OPEN failure was reported as success'

  laps_data_root=TRIM(root)
  wind_coordinate='UNSET'
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status)
  IF (status/=0) ERROR STOP 'invalid wind metadata was reported as success'

  wind_coordinate='GRID_RELATIVE'
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status)
  IF (status/=1) ERROR STOP 'successful WPS output was reported as failure'

  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                            TRIM(root)//'/resolved-candidate.wps')
  IF (status/=1) ERROR STOP 'resolved candidate path was not honored'

  PRINT *,'WPS writer status tests passed'
END PROGRAM test_wps_writer_status
