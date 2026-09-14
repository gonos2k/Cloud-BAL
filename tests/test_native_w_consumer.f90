PROGRAM test_native_w_consumer
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE netcdf
  USE cloud_bal_native_w_consumer, ONLY: apply_native_w_increment, &
    NATIVE_W_CONSUMER_OK,NATIVE_W_CONSUMER_OFF
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=2,NY=2,NZ=3,DATE_LENGTH=19
  CHARACTER(LEN=DATE_LENGTH), PARAMETER :: VALID_TIME='2026-08-16_12:00:00'
  CHARACTER(LEN=DATE_LENGTH), PARAMETER :: WRONG_TIME='2026-08-16_13:00:00'
  CHARACTER(LEN=512) :: root,wrfin,candidate,bad_wrfin,bad_candidate
  CHARACTER(LEN=512) :: surface_wrfin,surface_candidate,zero_surface_candidate, &
    bad_surface_candidate
  REAL(real32) :: baseline_w(NX,NY,NZ,1),updated_w(NX,NY,NZ,1),expected_w(NX,NY,NZ,1)
  REAL(real32) :: baseline_extra(NX,NY,NZ,1),updated_extra(NX,NY,NZ,1)
  REAL(real64) :: baseline_lat(NX,NY,1),baseline_lon(NX,NY,1)
  REAL(real64) :: updated_lat(NX,NY,1),updated_lon(NX,NY,1)
  INTEGER(int32) :: update_mask(NX,NY,NZ,1)
  CHARACTER(LEN=DATE_LENGTH) :: updated_start_date
  INTEGER :: status,failures

  CALL get_command_argument(1,root)
  IF (LEN_TRIM(root)==0) ERROR STOP 'test root is required'
  wrfin=TRIM(root)//'/wrfinput_d01'
  candidate=TRIM(root)//'/native_w_increment.nc'
  bad_wrfin=TRIM(root)//'/wrfinput_d01_bad'
  bad_candidate=TRIM(root)//'/native_w_increment_bad.nc'
  surface_wrfin=TRIM(root)//'/wrfinput_d01_surface'
  surface_candidate=TRIM(root)//'/native_w_increment_surface.nc'
  zero_surface_candidate=TRIM(root)//'/native_w_increment_surface_zero.nc'
  bad_surface_candidate=TRIM(root)//'/native_w_increment_surface_bad.nc'

  failures=0
  CALL create_wrfinput(TRIM(wrfin))
  CALL create_candidate(TRIM(candidate),VALID_TIME)
  CALL read_wrf_snapshot(TRIM(wrfin),baseline_w,baseline_extra,baseline_lat, &
    baseline_lon,updated_start_date)
    update_mask=0_int32
  update_mask(1,1,:,1)=1_int32
  update_mask(2,2,:,1)=1_int32

  CALL apply_native_w_increment(TRIM(wrfin),'missing-candidate.nc',VALID_TIME,.FALSE.,status)
  CALL check(status==NATIVE_W_CONSUMER_OFF,'OFF returns before opening inputs',failures)
  CALL read_wrf_snapshot(TRIM(wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  CALL check(ALL(updated_w==baseline_w),'OFF leaves W unchanged',failures)
  CALL check(ALL(updated_extra==baseline_extra) .AND. ALL(updated_lat==baseline_lat) .AND. &
    ALL(updated_lon==baseline_lon),'OFF leaves other fields unchanged',failures)

  CALL apply_native_w_increment(TRIM(wrfin),TRIM(candidate),VALID_TIME,.TRUE.,status)
  CALL check(status==NATIVE_W_CONSUMER_OK,'valid candidate applied to staged wrfinput',failures)
  CALL read_wrf_snapshot(TRIM(wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  expected_w=baseline_w
  expected_w(:,:,:,1)=baseline_w(:,:,:,1)-6.61_real32
  expected_w(2,1,:,1)=baseline_w(2,1,:,1)
  expected_w(1,2,:,1)=baseline_w(1,2,:,1)
  CALL check(MAXVAL(ABS(updated_w-expected_w))<2.0e-6_real32,'masked W increment is exact',failures)
  CALL check(ALL(updated_w(2,1,:,1)==baseline_w(2,1,:,1)) .AND. &
    ALL(updated_w(1,2,:,1)==baseline_w(1,2,:,1)),'inactive W levels are unchanged',failures)
  CALL check(ALL(updated_extra==baseline_extra) .AND. ALL(updated_lat==baseline_lat) .AND. &
    ALL(updated_lon==baseline_lon),'only W changed in staged wrfinput',failures)
  CALL check(updated_start_date==VALID_TIME,'global attributes remain intact',failures)

  CALL create_wrfinput(TRIM(bad_wrfin))
  CALL create_candidate(TRIM(bad_candidate),WRONG_TIME)
  CALL read_wrf_snapshot(TRIM(bad_wrfin),baseline_w,baseline_extra,baseline_lat, &
    baseline_lon,updated_start_date)
  CALL apply_native_w_increment(TRIM(bad_wrfin),TRIM(bad_candidate),VALID_TIME,.TRUE.,status)
  CALL check(status/=NATIVE_W_CONSUMER_OK,'time mismatch rejected',failures)
  CALL read_wrf_snapshot(TRIM(bad_wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  CALL check(ALL(updated_w==baseline_w),'rejected candidate leaves W untouched',failures)
  CALL check(ALL(updated_extra==baseline_extra) .AND. ALL(updated_lat==baseline_lat) .AND. &
    ALL(updated_lon==baseline_lon),'rejected candidate leaves other fields untouched',failures)

  CALL create_wrfinput(TRIM(surface_wrfin))
  CALL create_surface_candidate(TRIM(surface_candidate),VALID_TIME,1.0_real64)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),baseline_w,baseline_extra,baseline_lat, &
    baseline_lon,updated_start_date)
  CALL apply_native_w_increment(TRIM(surface_wrfin),TRIM(surface_candidate),VALID_TIME, &
    .TRUE.,status)
  CALL check(status==NATIVE_W_CONSUMER_OK,'surface v2 candidate applied',failures)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  expected_w=baseline_w
  CALL expected_surface_increment(expected_w,baseline_w)
  CALL check(MAXVAL(ABS(updated_w-expected_w))<2.0e-6_real32, &
    'surface v2 uses the clamped host boundary stencil',failures)
  CALL check(ALL(updated_extra==baseline_extra) .AND. ALL(updated_lat==baseline_lat) .AND. &
    ALL(updated_lon==baseline_lon),'surface v2 changes only W',failures)

  CALL create_wrfinput(TRIM(surface_wrfin))
  CALL create_surface_candidate(TRIM(zero_surface_candidate),VALID_TIME,0.0_real64)
  CALL apply_native_w_increment(TRIM(surface_wrfin),TRIM(zero_surface_candidate), &
    VALID_TIME,.TRUE.,status)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  CALL check(status==NATIVE_W_CONSUMER_OK,'zero surface response accepted',failures)
  CALL check(ALL(updated_w==baseline_w),'zero surface response leaves W unchanged',failures)

  CALL create_wrfinput(TRIM(surface_wrfin))
  CALL create_surface_candidate(TRIM(bad_surface_candidate),VALID_TIME,1.0_real64,.TRUE.)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),baseline_w,baseline_extra,baseline_lat, &
    baseline_lon,updated_start_date)
  CALL apply_native_w_increment(TRIM(surface_wrfin),TRIM(bad_surface_candidate), &
    VALID_TIME,.TRUE.,status)
  CALL check(status/=NATIVE_W_CONSUMER_OK,'surface mask contract failure rejected',failures)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  CALL check(ALL(updated_w==baseline_w),'surface failure leaves W untouched',failures)

  CALL create_wrfinput(TRIM(surface_wrfin))
  CALL set_map_factor_units(TRIM(surface_wrfin),'Pa')
  CALL create_surface_candidate(TRIM(surface_candidate),VALID_TIME,1.0_real64)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),baseline_w,baseline_extra,baseline_lat, &
    baseline_lon,updated_start_date)
  CALL apply_native_w_increment(TRIM(surface_wrfin),TRIM(surface_candidate), &
    VALID_TIME,.TRUE.,status)
  CALL check(status/=NATIVE_W_CONSUMER_OK,'invalid map-factor units rejected',failures)
  CALL read_wrf_snapshot(TRIM(surface_wrfin),updated_w,updated_extra,updated_lat, &
    updated_lon,updated_start_date)
  CALL check(ALL(updated_w==baseline_w),'invalid map-factor units leave W untouched',failures)

  IF (failures/=0) THEN
    PRINT '(A,I0)','Native W consumer tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Native W consumer tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE create_wrfinput(path)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER :: ncid,tdim,ddim,xdim,ydim,zdim,ustagdim,vstagdim
    INTEGER :: wvar,times_var,lat_var,lon_var,extra_var,hgt_var,mapx_var,mapy_var
    REAL(real32) :: w(NX,NY,NZ,1),extra(NX,NY,NZ,1)
    REAL(real32) :: lat(NX,NY,1),lon(NX,NY,1),hgt(NX,NY,1), &
      mapx(NX,NY,1),mapy(NX,NY,1)
    CHARACTER(LEN=DATE_LENGTH) :: times(1)
    INTEGER :: i,j,k

    CALL nc_assert(nf90_create(path,NF90_CLOBBER,ncid),'create wrfinput')
    CALL nc_assert(nf90_def_dim(ncid,'Time',1,tdim),'wrf Time dimension')
    CALL nc_assert(nf90_def_dim(ncid,'DateStrLen',DATE_LENGTH,ddim),'wrf date dimension')
    CALL nc_assert(nf90_def_dim(ncid,'west_east',NX,xdim),'wrf x dimension')
    CALL nc_assert(nf90_def_dim(ncid,'south_north',NY,ydim),'wrf y dimension')
    CALL nc_assert(nf90_def_dim(ncid,'bottom_top_stag',NZ,zdim),'wrf z dimension')
    CALL nc_assert(nf90_def_dim(ncid,'west_east_stag',NX+1,ustagdim),'wrf u dimension')
    CALL nc_assert(nf90_def_dim(ncid,'south_north_stag',NY+1,vstagdim),'wrf v dimension')
    CALL nc_assert(nf90_def_var(ncid,'W',NF90_FLOAT,[xdim,ydim,zdim,tdim],wvar),'define W')
    CALL nc_assert(nf90_def_var(ncid,'Times',NF90_CHAR,[ddim,tdim],times_var),'define Times')
    CALL nc_assert(nf90_def_var(ncid,'XLAT',NF90_FLOAT,[xdim,ydim,tdim],lat_var),'define XLAT')
    CALL nc_assert(nf90_def_var(ncid,'XLONG',NF90_FLOAT,[xdim,ydim,tdim],lon_var),'define XLONG')
    CALL nc_assert(nf90_def_var(ncid,'U_TEST',NF90_FLOAT,[xdim,ydim,zdim,tdim],extra_var),'define extra')
    CALL nc_assert(nf90_def_var(ncid,'HGT',NF90_FLOAT,[xdim,ydim,tdim],hgt_var),'define HGT')
    CALL nc_assert(nf90_def_var(ncid,'MAPFAC_MX',NF90_FLOAT,[xdim,ydim,tdim],mapx_var),'define MAPFAC_MX')
    CALL nc_assert(nf90_def_var(ncid,'MAPFAC_MY',NF90_FLOAT,[xdim,ydim,tdim],mapy_var),'define MAPFAC_MY')
    CALL nc_assert(nf90_put_att(ncid,wvar,'units','m s-1'),'W units')
    CALL nc_assert(nf90_put_att(ncid,lat_var,'units','degree_north'),'XLAT units')
    CALL nc_assert(nf90_put_att(ncid,lon_var,'units','degree_east'),'XLONG units')
    CALL nc_assert(nf90_put_att(ncid,extra_var,'units','m s-1'),'extra units')
    CALL nc_assert(nf90_put_att(ncid,hgt_var,'units','m'),'HGT units')
    ! WRF writes these dimensionless units as a single NUL byte.
    CALL nc_assert(nf90_put_att(ncid,mapx_var,'units',CHAR(0)),'MAPFAC_MX units')
    CALL nc_assert(nf90_put_att(ncid,mapy_var,'units',CHAR(0)),'MAPFAC_MY units')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'START_DATE',VALID_TIME),'start date')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'GRID_ID',1_int32),'grid id')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'DX',10.0_real64),'DX')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'DY',20.0_real64),'DY')
    CALL nc_assert(nf90_enddef(ncid),'end wrf definition')

    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      w(i,j,k,1)=10.0_real32+REAL(i+2*j+3*k,real32)
      extra(i,j,k,1)=70.0_real32+REAL(2*i+j+k,real32)
    END DO; END DO; END DO
    DO j=1,NY; DO i=1,NX
      lat(i,j,1)=35.0_real32+0.25_real32*REAL(i,real32)+0.5_real32*REAL(j,real32)
      lon(i,j,1)=-120.0_real32+0.75_real32*REAL(i,real32)-0.25_real32*REAL(j,real32)
      hgt(i,j,1)=REAL(3+7*i+11*j,real32)
      mapx(i,j,1)=1.0_real32+0.05_real32*REAL(i,real32)
      mapy(i,j,1)=0.9_real32+0.04_real32*REAL(j,real32)
    END DO; END DO
    times(1)=VALID_TIME
    CALL nc_assert(nf90_put_var(ncid,wvar,w),'write W')
    CALL nc_assert(nf90_put_var(ncid,times_var,times),'write Times')
    CALL nc_assert(nf90_put_var(ncid,lat_var,lat),'write XLAT')
    CALL nc_assert(nf90_put_var(ncid,lon_var,lon),'write XLONG')
    CALL nc_assert(nf90_put_var(ncid,extra_var,extra),'write extra')
    CALL nc_assert(nf90_put_var(ncid,hgt_var,hgt),'write HGT')
    CALL nc_assert(nf90_put_var(ncid,mapx_var,mapx),'write MAPFAC_MX')
    CALL nc_assert(nf90_put_var(ncid,mapy_var,mapy),'write MAPFAC_MY')
    CALL nc_assert(nf90_close(ncid),'close wrfinput')
  END SUBROUTINE create_wrfinput

  SUBROUTINE create_candidate(path,timestamp)
    CHARACTER(LEN=*), INTENT(IN) :: path,timestamp
    INTEGER :: ncid,tdim,ddim,xdim,ydim,zdim
    INTEGER :: times_var,lat_var,lon_var,varid(11),mask_var
    REAL(real32) :: lat(NX,NY,1),lon(NX,NY,1),fields(NX,NY,NZ,1,11)
    INTEGER(int32) :: mask(NX,NY,NZ,1)
    CHARACTER(LEN=DATE_LENGTH) :: times(1)
    CHARACTER(LEN=16), PARAMETER :: names(11)=[CHARACTER(LEN=16) :: 'P','P_X','P_Y', &
      'P_ETA','Z','Z_X','Z_Y','Z_ETA','DELTA_U','DELTA_V','DELTA_OMEGA']
    CHARACTER(LEN=16), PARAMETER :: units(11)=[CHARACTER(LEN=16) :: 'Pa','Pa m-1','Pa m-1', &
      'Pa','m','1','1','m','m s-1','m s-1','Pa s-1']
    INTEGER :: i,j,k,n

    CALL nc_assert(nf90_create(path,NF90_CLOBBER,ncid),'create candidate')
    CALL nc_assert(nf90_def_dim(ncid,'Time',1,tdim),'candidate Time dimension')
    CALL nc_assert(nf90_def_dim(ncid,'DateStrLen',DATE_LENGTH,ddim),'candidate date dimension')
    CALL nc_assert(nf90_def_dim(ncid,'west_east',NX,xdim),'candidate x dimension')
    CALL nc_assert(nf90_def_dim(ncid,'south_north',NY,ydim),'candidate y dimension')
    CALL nc_assert(nf90_def_dim(ncid,'bottom_top_stag',NZ,zdim),'candidate z dimension')
    CALL nc_assert(nf90_def_var(ncid,'Times',NF90_CHAR,[ddim,tdim],times_var),'candidate Times')
    CALL nc_assert(nf90_def_var(ncid,'XLAT',NF90_FLOAT,[xdim,ydim,tdim],lat_var),'candidate XLAT')
    CALL nc_assert(nf90_def_var(ncid,'XLONG',NF90_FLOAT,[xdim,ydim,tdim],lon_var),'candidate XLONG')
    DO n=1,11
      CALL nc_assert(nf90_def_var(ncid,TRIM(names(n)),NF90_FLOAT,[xdim,ydim,zdim,tdim], &
        varid(n)),'candidate field')
      CALL nc_assert(nf90_put_att(ncid,varid(n),'units',TRIM(units(n))),'candidate units')
    END DO
    CALL nc_assert(nf90_def_var(ncid,'UPDATE_MASK',NF90_INT,[xdim,ydim,zdim,tdim],mask_var),'candidate mask')
    CALL nc_assert(nf90_put_att(ncid,mask_var,'units','1'),'candidate mask units')
    CALL nc_assert(nf90_put_att(ncid,lat_var,'units','degree_north'),'candidate XLAT units')
    CALL nc_assert(nf90_put_att(ncid,lon_var,'units','degree_east'),'candidate XLONG units')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'contract','native_w_increment_v1'),'candidate contract')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'wind_coordinate','GRID_RELATIVE'),'candidate frame')
    CALL nc_assert(nf90_enddef(ncid),'end candidate definition')

    DO j=1,NY; DO i=1,NX
      lat(i,j,1)=35.0_real32+0.25_real32*REAL(i,real32)+0.5_real32*REAL(j,real32)
      lon(i,j,1)=-120.0_real32+0.75_real32*REAL(i,real32)-0.25_real32*REAL(j,real32)
    END DO; END DO
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      fields(i,j,k,1,1)=100000.0_real32-10000.0_real32*REAL(k-1,real32)
      fields(i,j,k,1,2)=2.0_real32
      fields(i,j,k,1,3)=3.0_real32
      fields(i,j,k,1,4)=10000.0_real32
      fields(i,j,k,1,5)=100.0_real32+50.0_real32*REAL(k-1,real32)
      fields(i,j,k,1,6)=4.0_real32
      fields(i,j,k,1,7)=5.0_real32
      fields(i,j,k,1,8)=-50.0_real32
      fields(i,j,k,1,9)=1.0_real32
      fields(i,j,k,1,10)=-2.0_real32
      fields(i,j,k,1,11)=118.0_real32
      mask(i,j,k,1)=MERGE(1_int32,0_int32,(i==1 .AND. j==1) .OR. (i==2 .AND. j==2))
    END DO; END DO; END DO
    fields(2,1,:,:,9:11)=ieee_value(0.0_real32,ieee_quiet_nan)
    fields(1,2,:,:,9:11)=ieee_value(0.0_real32,ieee_quiet_nan)
    times(1)=timestamp
    CALL nc_assert(nf90_put_var(ncid,times_var,times),'write candidate Times')
    CALL nc_assert(nf90_put_var(ncid,lat_var,lat),'write candidate XLAT')
    CALL nc_assert(nf90_put_var(ncid,lon_var,lon),'write candidate XLONG')
    DO n=1,11
      CALL nc_assert(nf90_put_var(ncid,varid(n),fields(:,:,:,:,n)),'write candidate field')
    END DO
    CALL nc_assert(nf90_put_var(ncid,mask_var,mask),'write candidate mask')
    CALL nc_assert(nf90_close(ncid),'close candidate')
  END SUBROUTINE create_candidate

  SUBROUTINE create_surface_candidate(path,timestamp,surface_factor,bad_top)
    CHARACTER(LEN=*), INTENT(IN) :: path,timestamp
    REAL(real64), INTENT(IN) :: surface_factor
    LOGICAL, INTENT(IN), OPTIONAL :: bad_top
    INTEGER :: ncid,tdim,ddim,xdim,ydim,zdim,ustagdim,vstagdim
    INTEGER :: times_var,lat_var,lon_var,varid(11),mask_var,du_var,dv_var
    REAL(real32) :: lat(NX,NY,1),lon(NX,NY,1),fields(NX,NY,NZ,1,11)
    REAL(real32) :: delta_u_surface(NX+1,NY,1),delta_v_surface(NX,NY+1,1)
    INTEGER(int32) :: mask(NX,NY,NZ,1)
    CHARACTER(LEN=DATE_LENGTH) :: times(1)
    CHARACTER(LEN=16), PARAMETER :: names(11)=[CHARACTER(LEN=16) :: 'P','P_X','P_Y', &
      'P_ETA','Z','Z_X','Z_Y','Z_ETA','DELTA_U','DELTA_V','DELTA_OMEGA']
    CHARACTER(LEN=16), PARAMETER :: units(11)=[CHARACTER(LEN=16) :: 'Pa','Pa m-1','Pa m-1', &
      'Pa','m','1','1','m','m s-1','m s-1','Pa s-1']
    INTEGER :: i,j,k,n

    CALL nc_assert(nf90_create(path,NF90_CLOBBER,ncid),'create surface candidate')
    CALL nc_assert(nf90_def_dim(ncid,'Time',1,tdim),'surface candidate Time dimension')
    CALL nc_assert(nf90_def_dim(ncid,'DateStrLen',DATE_LENGTH,ddim),'surface candidate date dimension')
    CALL nc_assert(nf90_def_dim(ncid,'west_east',NX,xdim),'surface candidate x dimension')
    CALL nc_assert(nf90_def_dim(ncid,'south_north',NY,ydim),'surface candidate y dimension')
    CALL nc_assert(nf90_def_dim(ncid,'bottom_top_stag',NZ,zdim),'surface candidate z dimension')
    CALL nc_assert(nf90_def_dim(ncid,'west_east_stag',NX+1,ustagdim),'surface candidate u dimension')
    CALL nc_assert(nf90_def_dim(ncid,'south_north_stag',NY+1,vstagdim),'surface candidate v dimension')
    CALL nc_assert(nf90_def_var(ncid,'Times',NF90_CHAR,[ddim,tdim],times_var),'surface candidate Times')
    CALL nc_assert(nf90_def_var(ncid,'XLAT',NF90_FLOAT,[xdim,ydim,tdim],lat_var),'surface candidate XLAT')
    CALL nc_assert(nf90_def_var(ncid,'XLONG',NF90_FLOAT,[xdim,ydim,tdim],lon_var),'surface candidate XLONG')
    DO n=1,11
      CALL nc_assert(nf90_def_var(ncid,TRIM(names(n)),NF90_FLOAT,[xdim,ydim,zdim,tdim], &
        varid(n)),'surface candidate field')
      CALL nc_assert(nf90_put_att(ncid,varid(n),'units',TRIM(units(n))),'surface candidate units')
    END DO
    CALL nc_assert(nf90_def_var(ncid,'UPDATE_MASK',NF90_INT,[xdim,ydim,zdim,tdim],mask_var), &
      'surface candidate mask')
    CALL nc_assert(nf90_def_var(ncid,'DELTA_U_SURFACE',NF90_FLOAT, &
      [ustagdim,ydim,tdim],du_var),'surface candidate surface U')
    CALL nc_assert(nf90_def_var(ncid,'DELTA_V_SURFACE',NF90_FLOAT, &
      [xdim,vstagdim,tdim],dv_var),'surface candidate surface V')
    CALL nc_assert(nf90_put_att(ncid,mask_var,'units','1'),'surface candidate mask units')
    CALL nc_assert(nf90_put_att(ncid,du_var,'units','m s-1'),'surface candidate surface U units')
    CALL nc_assert(nf90_put_att(ncid,dv_var,'units','m s-1'),'surface candidate surface V units')
    CALL nc_assert(nf90_put_att(ncid,lat_var,'units','degree_north'),'surface candidate XLAT units')
    CALL nc_assert(nf90_put_att(ncid,lon_var,'units','degree_east'),'surface candidate XLONG units')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'contract', &
      'native_w_increment_surface_v2'),'surface candidate contract')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'surface_boundary_contract', &
      'NATIVE_CF123_NONPERIODIC_FIXED_GEOMETRY_ZERO_ETA_DOT'), &
      'surface candidate boundary contract')
    CALL nc_assert(nf90_put_att(ncid,NF90_GLOBAL,'wind_coordinate','GRID_RELATIVE'), &
      'surface candidate frame')
    CALL nc_assert(nf90_enddef(ncid),'end surface candidate definition')

    DO j=1,NY; DO i=1,NX
      lat(i,j,1)=35.0_real32+0.25_real32*REAL(i,real32)+0.5_real32*REAL(j,real32)
      lon(i,j,1)=-120.0_real32+0.75_real32*REAL(i,real32)-0.25_real32*REAL(j,real32)
    END DO; END DO
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      fields(i,j,k,1,1)=100000.0_real32-10000.0_real32*REAL(k-1,real32)
      fields(i,j,k,1,2)=0.0_real32
      fields(i,j,k,1,3)=0.0_real32
      fields(i,j,k,1,4)=-10000.0_real32
      fields(i,j,k,1,5)=100.0_real32+50.0_real32*REAL(k-1,real32)
      fields(i,j,k,1,6)=0.0_real32
      fields(i,j,k,1,7)=0.0_real32
      fields(i,j,k,1,8)=50.0_real32
      fields(i,j,k,1,9)=0.0_real32
      fields(i,j,k,1,10)=0.0_real32
      fields(i,j,k,1,11)=0.0_real32
      mask(i,j,k,1)=MERGE(1_int32,0_int32,k<NZ)
    END DO; END DO; END DO
    IF (PRESENT(bad_top)) THEN
      IF (bad_top) mask(1,1,NZ,1)=1_int32
    END IF
    DO j=1,NY; DO i=1,NX+1
      delta_u_surface(i,j,1)=REAL(surface_factor,real32)* &
        (0.7_real32*REAL(i,real32)-0.2_real32*REAL(j,real32))
    END DO; END DO
    DO j=1,NY+1; DO i=1,NX
      delta_v_surface(i,j,1)=REAL(surface_factor,real32)* &
        (-0.4_real32*REAL(i,real32)+0.9_real32*REAL(j,real32))
    END DO; END DO
    times(1)=timestamp
    CALL nc_assert(nf90_put_var(ncid,times_var,times),'write surface candidate Times')
    CALL nc_assert(nf90_put_var(ncid,lat_var,lat),'write surface candidate XLAT')
    CALL nc_assert(nf90_put_var(ncid,lon_var,lon),'write surface candidate XLONG')
    DO n=1,11
      CALL nc_assert(nf90_put_var(ncid,varid(n),fields(:,:,:,:,n)), &
        'write surface candidate field')
    END DO
    CALL nc_assert(nf90_put_var(ncid,mask_var,mask),'write surface candidate mask')
    CALL nc_assert(nf90_put_var(ncid,du_var,delta_u_surface),'write surface candidate U')
    CALL nc_assert(nf90_put_var(ncid,dv_var,delta_v_surface),'write surface candidate V')
    CALL nc_assert(nf90_close(ncid),'close surface candidate')
  END SUBROUTINE create_surface_candidate

  SUBROUTINE set_map_factor_units(path,units)
    CHARACTER(LEN=*), INTENT(IN) :: path,units
    INTEGER :: ncid,varid

    CALL nc_assert(nf90_open(path,NF90_WRITE,ncid),'open map-factor units fixture')
    CALL nc_assert(nf90_inq_varid(ncid,'MAPFAC_MX',varid),'map-factor units id')
    CALL nc_assert(nf90_put_att(ncid,varid,'units',units),'write map-factor units')
    CALL nc_assert(nf90_close(ncid),'close map-factor units fixture')
  END SUBROUTINE set_map_factor_units

  SUBROUTINE expected_surface_increment(expected_w,baseline_w)
    REAL(real32), INTENT(INOUT) :: expected_w(:,:,:,:),baseline_w(:,:,:,:)
    REAL(real64) :: height(NX,NY),mapx(NX,NY),mapy(NX,NY)
    REAL(real64) :: delta_u_surface(NX+1,NY),delta_v_surface(NX,NY+1)
    INTEGER :: i,j,im,ip,jm,jp

    DO j=1,NY; DO i=1,NX
      height(i,j)=REAL(3+7*i+11*j,real64)
      mapx(i,j)=1.0_real64+0.05_real64*REAL(i,real64)
      mapy(i,j)=0.9_real64+0.04_real64*REAL(j,real64)
    END DO; END DO
    DO j=1,NY; DO i=1,NX+1
      delta_u_surface(i,j)=0.7_real64*REAL(i,real64)-0.2_real64*REAL(j,real64)
    END DO; END DO
    DO j=1,NY+1; DO i=1,NX
      delta_v_surface(i,j)=-0.4_real64*REAL(i,real64)+0.9_real64*REAL(j,real64)
    END DO; END DO
    expected_w=baseline_w
    DO j=1,NY
      jm=MAX(j-1,1); jp=MIN(j+1,NY)
      DO i=1,NX
        im=MAX(i-1,1); ip=MIN(i+1,NX)
        expected_w(i,j,1,1)=baseline_w(i,j,1,1)+REAL( &
          mapx(i,j)/(2.0_real64*10.0_real64)* &
            ((height(ip,j)-height(i,j))*delta_u_surface(i+1,j)+ &
             (height(i,j)-height(im,j))*delta_u_surface(i,j)) + &
          mapy(i,j)/(2.0_real64*20.0_real64)* &
            ((height(i,jp)-height(i,j))*delta_v_surface(i,j+1)+ &
             (height(i,j)-height(i,jm))*delta_v_surface(i,j)),real32)
      END DO
    END DO
  END SUBROUTINE expected_surface_increment

  SUBROUTINE read_wrf_snapshot(path,w,extra,lat,lon,start_date)
    CHARACTER(LEN=*), INTENT(IN) :: path
    REAL(real32), INTENT(OUT) :: w(:,:,:,:),extra(:,:,:,:)
    REAL(real64), INTENT(OUT) :: lat(:,:,:),lon(:,:,:)
    CHARACTER(LEN=DATE_LENGTH), INTENT(OUT) :: start_date
    INTEGER :: ncid,varid
    CHARACTER(LEN=128) :: raw_date

    CALL nc_assert(nf90_open(path,NF90_NOWRITE,ncid),'open snapshot')
    CALL nc_assert(nf90_inq_varid(ncid,'W',varid),'snapshot W id')
    CALL nc_assert(nf90_get_var(ncid,varid,w),'read snapshot W')
    CALL nc_assert(nf90_inq_varid(ncid,'U_TEST',varid),'snapshot extra id')
    CALL nc_assert(nf90_get_var(ncid,varid,extra),'read snapshot extra')
    CALL nc_assert(nf90_inq_varid(ncid,'XLAT',varid),'snapshot XLAT id')
    CALL nc_assert(nf90_get_var(ncid,varid,lat),'read snapshot XLAT')
    CALL nc_assert(nf90_inq_varid(ncid,'XLONG',varid),'snapshot XLONG id')
    CALL nc_assert(nf90_get_var(ncid,varid,lon),'read snapshot XLONG')
    raw_date=' '
    CALL nc_assert(nf90_get_att(ncid,NF90_GLOBAL,'START_DATE',raw_date),'read start date')
    start_date=raw_date(1:DATE_LENGTH)
    CALL nc_assert(nf90_close(ncid),'close snapshot')
  END SUBROUTINE read_wrf_snapshot

  SUBROUTINE nc_assert(code,where)
    INTEGER, INTENT(IN) :: code
    CHARACTER(LEN=*), INTENT(IN) :: where
    IF (code/=NF90_NOERR) ERROR STOP TRIM(where)//': '//TRIM(nf90_strerror(code))
  END SUBROUTINE nc_assert

END PROGRAM test_native_w_consumer
