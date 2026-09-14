! Test-only support for the actual lapsprep caller regression.
! The fixture is numerical and intentionally does not model a full KLAPS grid.

MODULE constants
  IMPLICIT NONE
  REAL, PARAMETER :: rdry = 287.1
  REAL, PARAMETER :: g = 9.81
  REAL, PARAMETER :: autoconv_lwc2rai = 0.0005
  REAL, PARAMETER :: autoconv_ice2sno = 0.0005
  REAL, PARAMETER :: pi = 3.14159265358
END MODULE constants

MODULE date_pack
  IMPLICIT NONE
CONTAINS
  SUBROUTINE wrf_date_to_ymd(wrf_date, century_year, month, day)
    INTEGER, INTENT(IN) :: wrf_date
    INTEGER, INTENT(INOUT) :: century_year
    INTEGER, INTENT(OUT) :: month, day
    century_year = wrf_date / 1000
    month = 1
    day = 1
  END SUBROUTINE wrf_date_to_ymd
END MODULE date_pack

MODULE laps_static
  IMPLICIT NONE
  INTEGER :: x, y, z2, z3
  REAL :: la1, lo1, la2, lo2, dx, dy, lov, latin1, latin2
  REAL, ALLOCATABLE :: topo(:,:), lats(:,:), lons(:,:)
  CHARACTER(LEN=132) :: grid_type
CONTAINS
  SUBROUTINE get_horiz_grid_spec(laps_data_root)
    CHARACTER(LEN=*), INTENT(IN) :: laps_data_root
    x = 2
    y = 2
    z2 = 1
    la1 = 35.0
    lo1 = 126.0
    la2 = 36.0
    lo2 = 127.0
    dx = 1.0
    dy = 1.0
    lov = 126.0
    latin1 = 30.0
    latin2 = 60.0
    grid_type = 'mercator'
    ALLOCATE(topo(x,y))
    topo = 100.0
  END SUBROUTINE get_horiz_grid_spec
END MODULE laps_static

MODULE lapsprep_mm5
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_pregrid_format
CONTAINS
  SUBROUTINE output_pregrid_format(p,t,ht,u,v,rh,slp,lwc,rai,sno,ice,pic,snocov,tskin)
    REAL, INTENT(IN) :: p(:), t(:,:,:), ht(:,:,:), u(:,:,:), v(:,:,:), rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:), lwc(:,:,:), rai(:,:,:), sno(:,:,:), ice(:,:,:), pic(:,:,:)
    REAL, INTENT(IN) :: snocov(:,:), tskin(:,:)
    ERROR STOP 'unexpected mm5 output stub call'
  END SUBROUTINE output_pregrid_format
END MODULE lapsprep_mm5

MODULE lapsprep_wrf
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_gribprep_format
CONTAINS
  SUBROUTINE output_gribprep_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic,snocov,tskin)
    REAL, INTENT(IN) :: p(:), t(:,:,:), ht(:,:,:), u(:,:,:), v(:,:,:), rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:), psfc(:,:), lwc(:,:,:), rai(:,:,:), sno(:,:,:)
    REAL, INTENT(IN) :: ice(:,:,:), pic(:,:,:), snocov(:,:), tskin(:,:)
    ERROR STOP 'unexpected wrf output stub call'
  END SUBROUTINE output_gribprep_format
END MODULE lapsprep_wrf

MODULE lapsprep_rams
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_ralph2_format
CONTAINS
  SUBROUTINE output_ralph2_format(p,u,v,t,ht,rh,slp,psfc,snocov,tskin)
    REAL, INTENT(IN) :: p(:), u(:,:,:), v(:,:,:), t(:,:,:), ht(:,:,:), rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:), psfc(:,:), snocov(:,:), tskin(:,:)
    ERROR STOP 'unexpected rams output stub call'
  END SUBROUTINE output_ralph2_format
END MODULE lapsprep_rams

MODULE lapsprep_netcdf
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_netcdf_format
CONTAINS
  SUBROUTINE output_netcdf_format(pr,ht,tp,mr,uw,vw,ww,slp,spr,lwc,ice,rai,sno,pic)
    REAL, INTENT(IN) :: pr(:), ht(:,:,:), tp(:,:,:), mr(:,:,:), uw(:,:,:), vw(:,:,:)
    REAL, INTENT(IN) :: ww(:,:,:), slp(:,:), spr(:,:), lwc(:,:,:), ice(:,:,:)
    REAL, INTENT(IN) :: rai(:,:,:), sno(:,:,:), pic(:,:,:)
    ERROR STOP 'unexpected cdf output stub call'
  END SUBROUTINE output_netcdf_format
END MODULE lapsprep_netcdf

SUBROUTINE get_systime(i4time, laps_file_time, istatus)
  INTEGER, INTENT(OUT) :: i4time, istatus
  CHARACTER(LEN=*), INTENT(OUT) :: laps_file_time
  i4time = 0
  laps_file_time = '260010300'
  istatus = 1
END SUBROUTINE get_systime

! The experimental SHADOW path needs the legacy filename-to-clock bridge, but
! the numerical vapor fixtures do not otherwise exercise the upstream library.
! Keep this tiny test-only implementation here so the default caller test has
! no dependency on the full KLAPS utility library.
SUBROUTINE i4time_fname_lp(fname_in, i4time, istatus)
  CHARACTER(LEN=*), INTENT(IN) :: fname_in
  INTEGER, INTENT(OUT) :: i4time, istatus
  INTEGER :: year2, jday, hour, minute, year, prior_year, days, ios
  LOGICAL :: leap

  i4time = 0
  istatus = 0
  READ(fname_in, '(I2.2,I3.3,I2.2,I2.2)', IOSTAT=ios) year2, jday, hour, minute
  IF (ios /= 0 .OR. jday < 1 .OR. jday > 366 .OR. hour < 0 .OR. hour > 23 .OR. &
      minute < 0 .OR. minute > 59) RETURN
  IF (year2 < 80) THEN
    year = 2000 + year2
  ELSE
    year = 1900 + year2
  END IF
  days = 0
  DO prior_year = 1960, year - 1
    leap = MOD(prior_year, 4) == 0 .AND. &
           (MOD(prior_year, 100) /= 0 .OR. MOD(prior_year, 400) == 0)
    IF (leap) THEN
      days = days + 366
    ELSE
      days = days + 365
    END IF
  END DO
  i4time = (days + jday - 1) * 86400 + hour * 3600 + minute * 60
  istatus = 1
END SUBROUTINE i4time_fname_lp

REAL FUNCTION make_rh(p,tc,mr,flag)
  REAL, INTENT(IN) :: p, tc, mr, flag
  ERROR STOP 'unexpected JAX make_rh call'
END FUNCTION make_rh

SUBROUTINE saturate_ice_points(t,p,thresh,sh_m,rh_m)
  REAL, INTENT(IN) :: t,p,thresh
  REAL, INTENT(OUT) :: sh_m,rh_m
  ERROR STOP 'unexpected JAX saturate_ice_points call'
END SUBROUTINE saturate_ice_points
