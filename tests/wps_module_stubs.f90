MODULE setup
  IMPLICIT NONE
  CHARACTER(LEN=256) :: laps_data_root=' ',output_prefix=' '
  CHARACTER(LEN=16) :: wind_coordinate='GRID_RELATIVE'
  INTEGER :: valid_yyyy=2026,valid_jjj=244,valid_hh=3,valid_min=32
  LOGICAL :: hotstart=.FALSE.
  REAL :: snow_thresh=0.5
END MODULE setup

MODULE laps_static
  IMPLICIT NONE
  INTEGER :: x=2,y=2,z3=1
  REAL :: la1=30.0,lo1=120.0,dx=1.0,dy=1.0,lov=126.0
  REAL :: latin1=30.0,latin2=60.0
  CHARACTER(LEN=132) :: grid_type='mercator'
END MODULE laps_static

MODULE date_pack
  IMPLICIT NONE
CONTAINS
  SUBROUTINE wrf_date_to_ymd(wrf_date,century_year,month,day)
    INTEGER,INTENT(IN) :: wrf_date
    INTEGER,INTENT(INOUT) :: century_year
    INTEGER,INTENT(OUT) :: month,day
    century_year=wrf_date/1000
    month=9
    day=1
  END SUBROUTINE wrf_date_to_ymd
END MODULE date_pack
