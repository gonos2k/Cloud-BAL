MODULE writer_failure_control
  IMPLICIT NONE
  INTEGER :: call_count=0,failure_at=0
END MODULE writer_failure_control

PROGRAM test_writeballaps_status
  USE writer_failure_control
  IMPLICIT NONE
  REAL :: phi(2,2,2),u(2,2,2),v(2,2,2),t(2,2,2),omega(2,2,2)
  REAL :: rh(2,2,2),sh(2,2,2),p(2)
  INTEGER :: status,point
  EXTERNAL :: write_bal_laps

  phi=1.0; u=1.0; v=1.0; t=280.0; omega=0.0
  rh=50.0; sh=0.005; p=(/50000.0,85000.0/)
  DO point=1,4
    call_count=0; failure_at=point; status=-1
    CALL write_bal_laps(0,phi,u,v,t,omega,rh,sh,2,2,2,p,status)
    IF (status/=0 .OR. call_count/=point) ERROR STOP 'writer failure was hidden'
  END DO
  call_count=0; failure_at=0; status=-1
  CALL write_bal_laps(0,phi,u,v,t,omega,rh,sh,2,2,2,p,status)
  IF (status/=1 .OR. call_count/=4) ERROR STOP 'complete writer set did not succeed'
  PRINT *,'Balanced output status tests passed'
END PROGRAM test_writeballaps_status

SUBROUTINE get_directory(ext,directory,length)
  CHARACTER(LEN=*),INTENT(IN) :: ext
  CHARACTER(LEN=*),INTENT(OUT) :: directory
  INTEGER,INTENT(OUT) :: length
  directory='/candidate/root/'
  length=LEN_TRIM(directory)
END SUBROUTINE get_directory

SUBROUTINE make_fnam_lp(i4time,name,status)
  INTEGER,INTENT(IN) :: i4time
  CHARACTER(LEN=*),INTENT(OUT) :: name
  INTEGER,INTENT(OUT) :: status
  name='test-name'; status=1
END SUBROUTINE make_fnam_lp

SUBROUTINE write_laps_data(i4time,directory,extension,nx,ny,nz,nfield, &
                           variable,level,level_coordinate,unit,comment,data,status)
  USE writer_failure_control
  INTEGER,INTENT(IN) :: i4time,nx,ny,nz,nfield
  CHARACTER(LEN=*),INTENT(IN) :: directory,extension
  CHARACTER(LEN=*),INTENT(IN) :: variable(*),level_coordinate(*),unit(*),comment(*)
  INTEGER,INTENT(IN) :: level(*)
  REAL,INTENT(IN) :: data(*)
  INTEGER,INTENT(OUT) :: status
  call_count=call_count+1
  IF (failure_at==call_count) THEN
    status=0
  ELSE
    status=1
  END IF
END SUBROUTINE write_laps_data
