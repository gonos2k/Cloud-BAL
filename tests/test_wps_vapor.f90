PROGRAM test_wps_vapor
  USE, INTRINSIC :: ieee_arithmetic
  USE setup
  USE laps_static
  USE lapsprep_wps, ONLY: output_ungrib_format
  IMPLICIT NONE

  INTEGER, PARAMETER :: nx_test=3, ny_test=2, nz_test=3
  CHARACTER(LEN=512) :: root
  REAL, ALLOCATABLE :: p(:),t(:,:,:),ht(:,:,:),u(:,:,:),v(:,:,:),rh(:,:,:)
  REAL, ALLOCATABLE :: slp(:,:),psfc(:,:),lwc(:,:,:),rai(:,:,:),sno(:,:,:)
  REAL, ALLOCATABLE :: ice(:,:,:),pic(:,:,:),snocov(:,:),tskin(:,:)
  REAL, ALLOCATABLE :: qv(:,:,:),qv_bad_shape(:,:,:),qv_nan(:,:,:)
  REAL, ALLOCATABLE :: qv_inf(:,:,:),qv_negative(:,:,:)
  REAL, ALLOCATABLE :: p_saved(:),t_saved(:,:,:),ht_saved(:,:,:)
  REAL, ALLOCATABLE :: u_saved(:,:,:),v_saved(:,:,:),rh_saved(:,:,:)
  REAL, ALLOCATABLE :: slp_saved(:,:),psfc_saved(:,:),lwc_saved(:,:,:)
  REAL, ALLOCATABLE :: rai_saved(:,:,:),sno_saved(:,:,:),ice_saved(:,:,:)
  REAL, ALLOCATABLE :: pic_saved(:,:,:),snocov_saved(:,:),tskin_saved(:,:)
  REAL, ALLOCATABLE :: qv_saved(:,:,:),qv_bad_shape_saved(:,:,:)
  REAL, ALLOCATABLE :: qv_negative_saved(:,:,:)
  INTEGER :: status
  LOGICAL :: file_exists
  INTEGER :: qv_nan_bits(nx_test*ny_test*(nz_test+1))
  INTEGER :: qv_inf_bits(nx_test*ny_test*(nz_test+1))
  INTEGER :: i,j,k

  CALL get_command_argument(1,root)
  IF (LEN_TRIM(root)==0) ERROR STOP 'test root is required'

  x=nx_test
  y=ny_test
  z3=nz_test
  wind_coordinate='GRID_RELATIVE'
  snow_thresh=0.5

  ALLOCATE(p(nz_test+1),t(nx_test,ny_test,nz_test+1), &
           ht(nx_test,ny_test,nz_test+1),u(nx_test,ny_test,nz_test+1), &
           v(nx_test,ny_test,nz_test+1),rh(nx_test,ny_test,nz_test+1), &
           slp(nx_test,ny_test),psfc(nx_test,ny_test), &
           lwc(nx_test,ny_test,nz_test),rai(nx_test,ny_test,nz_test), &
           sno(nx_test,ny_test,nz_test),ice(nx_test,ny_test,nz_test), &
           pic(nx_test,ny_test,nz_test),snocov(nx_test,ny_test), &
           tskin(nx_test,ny_test),qv(nx_test,ny_test,nz_test+1), &
           qv_bad_shape(nx_test-1,ny_test,nz_test+1), &
           qv_nan(nx_test,ny_test,nz_test+1), &
           qv_inf(nx_test,ny_test,nz_test+1), &
           qv_negative(nx_test,ny_test,nz_test+1))

  p=(/850.0,1050.0,700.0,2001.0/)
  DO k=1,nz_test+1
    DO j=1,ny_test
      DO i=1,nx_test
        t(i,j,k)=250.0+REAL(100*k+10*i+j)/100.0
        ht(i,j,k)=1000.0*REAL(k)+100.0*REAL(i)+10.0*REAL(j)
        u(i,j,k)=REAL(100*k+10*i+j)/10.0
        v(i,j,k)=-REAL(100*k+10*i+j)/10.0
        rh(i,j,k)=30.0+REAL(10*k+i+j)
        qv(i,j,k)=REAL(1000*k+100*i+10*j)/1000000.0
      END DO
    END DO
  END DO
  DO j=1,ny_test
    DO i=1,nx_test
      slp(i,j)=100000.0+100.0*REAL(i)+10.0*REAL(j)
      psfc(i,j)=90000.0+100.0*REAL(i)+10.0*REAL(j)
      tskin(i,j)=280.0+REAL(10*i+j)/10.0
      snocov(i,j)=-1.0
    END DO
  END DO
  DO k=1,nz_test
    DO j=1,ny_test
      DO i=1,nx_test
        lwc(i,j,k)=REAL(10*k+i+j)/100000.0
        rai(i,j,k)=REAL(20*k+i+j)/100000.0
        sno(i,j,k)=REAL(30*k+i+j)/100000.0
        ice(i,j,k)=REAL(40*k+i+j)/100000.0
        pic(i,j,k)=REAL(50*k+i+j)/100000.0
      END DO
    END DO
  END DO

  qv_bad_shape=0.0
  qv(1,1,1)=0.0
  qv_nan=qv
  qv_inf=qv
  qv_negative=qv
  qv_nan(1,1,1)=ieee_value(qv_nan(1,1,1),ieee_quiet_nan)
  qv_inf(1,1,1)=ieee_value(qv_inf(1,1,1),ieee_positive_inf)
  qv_negative(2,2,3)=-0.001

  p_saved=p
  t_saved=t
  ht_saved=ht
  u_saved=u
  v_saved=v
  rh_saved=rh
  slp_saved=slp
  psfc_saved=psfc
  lwc_saved=lwc
  rai_saved=rai
  sno_saved=sno
  ice_saved=ice
  pic_saved=pic
  snocov_saved=snocov
  tskin_saved=tskin
  qv_saved=qv
  qv_bad_shape_saved=qv_bad_shape
  qv_negative_saved=qv_negative
  qv_nan_bits=TRANSFER(qv_nan,qv_nan_bits,SIZE(qv_nan_bits))
  qv_inf_bits=TRANSFER(qv_inf,qv_inf_bits,SIZE(qv_inf_bits))

  hotstart=.FALSE.
  CALL write_case(path(root,'legacy_off.wps'),status)
  IF (status/=1) ERROR STOP 'legacy off output failed'
  CALL write_case(path(root,'vapor_off.wps'),status,qv)
  IF (status/=1) ERROR STOP 'vapor off output failed'

  hotstart=.TRUE.
  CALL write_case(path(root,'legacy_on.wps'),status)
  IF (status/=1) ERROR STOP 'legacy on output failed'
  CALL write_case(path(root,'vapor_on.wps'),status,qv)
  IF (status/=1) ERROR STOP 'vapor on output failed'

  hotstart=.FALSE.
  CALL check_invalid(path(root,'invalid_shape.wps'),qv_bad_shape,'invalid shape')
  CALL check_invalid(path(root,'invalid_nan.wps'),qv_nan,'NaN')
  CALL check_invalid(path(root,'invalid_inf.wps'),qv_inf,'Inf')
  CALL check_invalid(path(root,'invalid_negative.wps'),qv_negative,'negative')
  CALL write_case(path(root,'invalid_absent.wps'),status,qv_negative)
  IF (status/=0) ERROR STOP 'invalid absent-path call returned success'
  INQUIRE(FILE=TRIM(path(root,'invalid_absent.wps')),EXIST=file_exists)
  IF (file_exists) ERROR STOP 'invalid vapor created an output file'

  IF (ANY(p/=p_saved) .OR. ANY(t/=t_saved) .OR. ANY(ht/=ht_saved) .OR. &
      ANY(u/=u_saved) .OR. ANY(v/=v_saved) .OR. ANY(rh/=rh_saved) .OR. &
      ANY(slp/=slp_saved) .OR. ANY(psfc/=psfc_saved) .OR. &
      ANY(lwc/=lwc_saved) .OR. ANY(rai/=rai_saved) .OR. ANY(sno/=sno_saved) .OR. &
      ANY(ice/=ice_saved) .OR. ANY(pic/=pic_saved) .OR. &
      ANY(snocov/=snocov_saved) .OR. ANY(tskin/=tskin_saved) .OR. &
      ANY(qv/=qv_saved) .OR. ANY(qv_bad_shape/=qv_bad_shape_saved) .OR. &
      ANY(qv_negative/=qv_negative_saved)) ERROR STOP 'writer changed caller input'
  IF (ANY(TRANSFER(qv_nan,qv_nan_bits,SIZE(qv_nan_bits))/=qv_nan_bits) .OR. &
      ANY(TRANSFER(qv_inf,qv_inf_bits,SIZE(qv_inf_bits))/=qv_inf_bits)) &
    ERROR STOP 'writer changed invalid caller input'

  PRINT *, 'WPS vapor writer tests passed'

CONTAINS

  FUNCTION path(directory,name) RESULT(value)
    CHARACTER(LEN=*), INTENT(IN) :: directory,name
    CHARACTER(LEN=512) :: value
    value=TRIM(directory)//'/'//TRIM(name)
  END FUNCTION path

  SUBROUTINE write_case(output_path,write_status,vapor)
    CHARACTER(LEN=*), INTENT(IN) :: output_path
    INTEGER, INTENT(OUT) :: write_status
    REAL, OPTIONAL, INTENT(IN) :: vapor(:,:,:)
    IF (PRESENT(vapor)) THEN
      CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
           snocov,tskin,write_status,resolved_output_file=TRIM(output_path), &
           vapor_mixing_ratio=vapor)
    ELSE
      CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
           snocov,tskin,write_status,resolved_output_file=TRIM(output_path))
    END IF
  END SUBROUTINE write_case

  SUBROUTINE check_invalid(output_path,vapor,label)
    CHARACTER(LEN=*), INTENT(IN) :: output_path,label
    REAL, INTENT(IN) :: vapor(:,:,:)
    INTEGER :: write_status
    CALL write_case(output_path,write_status)
    IF (write_status/=1) ERROR STOP 'failed to seed invalid-output sentinel'
    CALL write_case(output_path,write_status,vapor)
    IF (write_status/=0) ERROR STOP 'invalid vapor input returned success'
    PRINT *, 'Rejected vapor input: ',TRIM(label)
  END SUBROUTINE check_invalid

END PROGRAM test_wps_vapor
