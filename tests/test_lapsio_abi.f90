PROGRAM test_lapsio_abi
  IMPLICIT NONE
  INTERFACE
    SUBROUTINE get_laps_3d_analysis_data(i4time,nx,ny,nz,phi,t,u,v,sh,omo,status)
      INTEGER :: i4time,nx,ny,nz,status
      REAL :: phi(nx,ny,nz),t(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz)
      REAL :: sh(nx,ny,nz),omo(nx,ny,nz)
    END SUBROUTINE get_laps_3d_analysis_data
    SUBROUTINE get_laps_3d_analysis_data_ex(i4time,nx,ny,nz,phi,t,u,v,sh,omo, &
                                             omo_status,status)
      INTEGER :: i4time,nx,ny,nz,omo_status,status
      REAL :: phi(nx,ny,nz),t(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz)
      REAL :: sh(nx,ny,nz),omo(nx,ny,nz)
    END SUBROUTINE get_laps_3d_analysis_data_ex
  END INTERFACE
  INTEGER, PARAMETER :: nx=1,ny=1,nz=2
  INTEGER :: status,omo_status
  REAL :: phi(nx,ny,nz),temperature(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz)
  REAL :: humidity(nx,ny,nz),omo(nx,ny,nz)

  CALL get_laps_3d_analysis_data(1,nx,ny,nz,phi,temperature,u,v,humidity,omo,status)
  IF (status/=1) ERROR STOP 'legacy get_laps ABI failed'

  status=0; omo_status=0
  CALL get_laps_3d_analysis_data_ex(1,nx,ny,nz,phi,temperature,u,v,humidity,omo, &
                                     omo_status,status)
  IF (status/=1 .OR. omo_status/=1) ERROR STOP 'extended get_laps ABI failed'

  status=0; omo_status=0
  CALL get_laps_3d_analysis_data_ex(2,nx,ny,nz,phi,temperature,u,v,humidity,omo, &
                                     omo_status,status)
  IF (status/=1 .OR. omo_status/=1 .OR. &
      MAXVAL(ABS(humidity-humidity(1,1,nz)))>EPSILON(1.0)) &
    ERROR STOP 'top-only humidity column failed'

  status=1; omo_status=1
  CALL get_laps_3d_analysis_data_ex(3,nx,ny,nz,phi,temperature,u,v,humidity,omo, &
                                     omo_status,status)
  IF (status/=0 .OR. omo_status/=0) ERROR STOP 'missing humidity status failed'

  status=1
  CALL get_laps_3d_analysis_data(3,nx,ny,nz,phi,temperature,u,v,humidity,omo,status)
  IF (status/=0) ERROR STOP 'legacy missing humidity status failed'
  PRINT *,'LAPS analysis reader ABI tests passed'
END PROGRAM test_lapsio_abi

SUBROUTINE get_r_missing_data(value,status)
  IMPLICIT NONE
  REAL, INTENT(OUT) :: value
  INTEGER, INTENT(OUT) :: status
  value=1.0e37
  status=1
END SUBROUTINE get_r_missing_data

SUBROUTINE get_directory(extension,directory,length)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: extension
  CHARACTER(*), INTENT(OUT) :: directory
  INTEGER, INTENT(OUT) :: length
  directory='.'
  length=LEN_TRIM(extension)
END SUBROUTINE get_directory

SUBROUTINE get_laps_3d(i4time,nx,ny,nz,extension,variable,units,comment,data,status)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time,nx,ny,nz
  CHARACTER(*), INTENT(IN) :: extension,variable
  CHARACTER(*), INTENT(OUT) :: units,comment
  REAL, INTENT(OUT) :: data(*)
  INTEGER, INTENT(OUT) :: status
  INTEGER :: point
  DO point=1,nx*ny*nz
    data(point)=1.0
  END DO
  IF (TRIM(variable)=='sh' .AND. i4time==2) THEN
    data(1:nx*ny*(nz-1))=1.0e37
    data(nx*ny*nz)=0.01
  ELSE IF (TRIM(variable)=='sh' .AND. i4time==3) THEN
    data(1:nx*ny*nz)=1.0e37
  END IF
  units='test'
  comment='test fixture'
  status=MERGE(1,0,i4time>=0 .AND. LEN_TRIM(extension)>0 .AND. LEN(variable)>0)
END SUBROUTINE get_laps_3d
