PROGRAM test_wps_writer_status
  USE setup
  USE lapsprep_wps,ONLY: output_ungrib_format
  IMPLICIT NONE
  REAL :: p(2),a3(2,2,2),a2(2,2)
  INTEGER :: status,unit,io_status,file_size,version,second
  CHARACTER(24) :: timestamp
  CHARACTER(2) :: seconds_text
  CHARACTER(LEN=256) :: root
  CHARACTER(LEN=257) :: long_path
  CHARACTER(LEN=256) :: create_new_path,existing_path,legacy_path
  CHARACTER(LEN=8) :: sentinel
  LOGICAL :: file_exists

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

  create_new_path=TRIM(root)//'/create-new.wps'
  INQUIRE(FILE=TRIM(create_new_path),EXIST=file_exists)
  IF (file_exists) ERROR STOP 'create_new fixture unexpectedly exists'
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                            resolved_output_file=TRIM(create_new_path),create_new=.TRUE.)
  IF (status/=1) ERROR STOP 'create_new absent output was rejected'
  INQUIRE(FILE=TRIM(create_new_path),EXIST=file_exists)
  IF (.NOT.file_exists) ERROR STOP 'create_new did not create absent output'

  existing_path=TRIM(root)//'/create-new-existing.wps'
  OPEN(NEWUNIT=unit,FILE=TRIM(existing_path),STATUS='NEW',FORM='FORMATTED', &
       ACTION='WRITE',IOSTAT=io_status)
  IF (io_status/=0) ERROR STOP 'could not seed create_new sentinel'
  WRITE(unit,'(A)') 'sentinel'
  CLOSE(unit)
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                            resolved_output_file=TRIM(existing_path),create_new=.TRUE.)
  IF (status/=0) ERROR STOP 'create_new replaced a preexisting output'
  OPEN(NEWUNIT=unit,FILE=TRIM(existing_path),STATUS='OLD',FORM='FORMATTED', &
       ACTION='READ',IOSTAT=io_status)
  IF (io_status/=0) ERROR STOP 'create_new sentinel could not be reopened'
  READ(unit,'(A)',IOSTAT=io_status) sentinel
  CLOSE(unit)
  IF (io_status/=0 .OR. sentinel/='sentinel') &
    ERROR STOP 'create_new changed a preexisting output'

  legacy_path=TRIM(root)//'/legacy-replace.wps'
  OPEN(NEWUNIT=unit,FILE=TRIM(legacy_path),STATUS='NEW',FORM='FORMATTED', &
       ACTION='WRITE',IOSTAT=io_status)
  IF (io_status/=0) ERROR STOP 'could not seed legacy replacement'
  WRITE(unit,'(A)') 'sentinel'
  CLOSE(unit)
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                            resolved_output_file=TRIM(legacy_path))
  IF (status/=1) ERROR STOP 'default legacy replacement failed'
  INQUIRE(FILE=TRIM(legacy_path),EXIST=file_exists,SIZE=file_size)
  IF (.NOT.file_exists .OR. file_size<=LEN_TRIM('sentinel')) &
    ERROR STOP 'default legacy replacement left the sentinel'
  OPEN(NEWUNIT=unit,FILE=TRIM(legacy_path),STATUS='OLD',FORM='UNFORMATTED', &
       ACTION='READ',IOSTAT=io_status)
  IF (io_status/=0) ERROR STOP 'legacy replacement output could not be reopened'
  READ(unit,IOSTAT=io_status) version
  CLOSE(unit)
  IF (io_status/=0 .OR. version/=5) ERROR STOP 'legacy replacement did not write WPS data'

  ! A truncated path must never replace the file at its 256-character prefix.
  long_path=TRIM(root)//'/'//REPEAT('x',256-LEN_TRIM(root))
  OPEN(NEWUNIT=unit,FILE=long_path(:256),STATUS='NEW')
  WRITE(unit,'(A)') 'sentinel'
  CLOSE(unit)
  CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status,long_path)
  IF (status/=0) ERROR STOP 'overlong WPS output path was accepted'
  OPEN(NEWUNIT=unit,FILE=long_path(:256),STATUS='OLD',ACTION='READ')
  READ(unit,'(A)') sentinel
  CLOSE(unit)
  IF (sentinel/='sentinel') ERROR STOP 'truncated WPS output path replaced another file'

  ! Seconds are data, not a tolerance or a rounded filename component.
  DO second=0,59
    IF (second/=0 .AND. second/=20 .AND. second/=59) CYCLE
    CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                              resolved_output_file=TRIM(legacy_path),valid_second=second)
    IF (status/=1) ERROR STOP 'valid WPS seconds rejected'
    OPEN(NEWUNIT=unit,FILE=TRIM(legacy_path),STATUS='OLD',FORM='UNFORMATTED',ACTION='READ')
    READ(unit) version
    READ(unit) timestamp
    CLOSE(unit)
    WRITE(seconds_text,'(I2.2)') second
    IF (timestamp(18:19)/=seconds_text) ERROR STOP 'WPS seconds not preserved'
  END DO
  DO second=-1,60,61
    CALL output_ungrib_format(p,a3,a3,a3,a3,a3,a2,a2,a3,a3,a3,a3,a3,a2,a2,status, &
                              resolved_output_file=TRIM(existing_path),valid_second=second)
    IF (status/=0) ERROR STOP 'invalid WPS seconds accepted'
    OPEN(NEWUNIT=unit,FILE=TRIM(existing_path),STATUS='OLD',ACTION='READ')
    READ(unit,'(A)') sentinel
    CLOSE(unit)
    IF (sentinel/='sentinel') ERROR STOP 'invalid seconds replaced output'
  END DO

  PRINT *,'WPS writer status tests passed'
END PROGRAM test_wps_writer_status
