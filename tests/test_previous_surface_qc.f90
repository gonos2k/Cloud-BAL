! Controlled tests for the previous-hour surface reader and qcdata status ABI.
! The QC build links the real fixed-form qc_data.f and stubs only the reader
! and directory lookup.  The LSO build links the real read_surface_old helpers
! and stubs only the newer-format data readers.

MODULE previous_surface_qc_control
  IMPLICIT NONE
  INTEGER :: qc_reader_status = 1
  INTEGER :: qc_previous_count = 1
  INTEGER :: lso_data_status = 1
  INTEGER :: lso_time_status = 1
  LOGICAL :: qc_open_failure = .FALSE.
END MODULE previous_surface_qc_control

#ifdef QC_DRIVER

SUBROUTINE get_directory(ext, directory, length)
  USE previous_surface_qc_control
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: ext
  CHARACTER(LEN=*), INTENT(OUT) :: directory
  INTEGER, INTENT(OUT) :: length

  directory = 'logs/'
  IF (qc_open_failure) directory = 'missing/'
  length = LEN_TRIM(directory)
END SUBROUTINE get_directory

SUBROUTINE read_surface_old(infile, maxsta, atime, n_meso_g, n_meso_pos, &
                            n_sao_g, n_sao_pos_g, n_sao_b, n_sao_pos_b, &
                            n_obs_g, n_obs_pos_g, n_obs_b, n_obs_pos_b, stn, &
                            obstype, lat, lon, elev, wx, t, td, dd, ff, ddg, &
                            ffg, pstn, pmsl, alt, kloud, ceil, lowcld, cover, &
                            rad, idp3, store_emv, store_amt, store_hgt, vis, &
                            obstime, istatus)
  USE previous_surface_qc_control
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: infile
  INTEGER, INTENT(IN) :: maxsta
  CHARACTER(LEN=*), INTENT(OUT) :: atime
  INTEGER, INTENT(OUT) :: n_meso_g, n_meso_pos, n_sao_g, n_sao_pos_g
  INTEGER, INTENT(OUT) :: n_sao_b, n_sao_pos_b, n_obs_g, n_obs_pos_g
  INTEGER, INTENT(OUT) :: n_obs_b, n_obs_pos_b
  CHARACTER(LEN=*), INTENT(OUT) :: stn(maxsta), obstype(maxsta), wx(maxsta)
  REAL, INTENT(OUT) :: lat(maxsta), lon(maxsta), elev(maxsta)
  REAL, INTENT(OUT) :: t(maxsta), td(maxsta), dd(maxsta), ff(maxsta)
  REAL, INTENT(OUT) :: ddg(maxsta), ffg(maxsta), pstn(maxsta), pmsl(maxsta)
  REAL, INTENT(OUT) :: alt(maxsta), ceil(maxsta), lowcld(maxsta)
  REAL, INTENT(OUT) :: cover(maxsta), rad(maxsta), store_hgt(maxsta,5)
  REAL, INTENT(OUT) :: vis(maxsta)
  INTEGER, INTENT(OUT) :: kloud(maxsta), idp3(maxsta), obstime(maxsta)
  CHARACTER(LEN=*), INTENT(OUT) :: store_emv(maxsta,5), store_amt(maxsta,5)
  INTEGER, INTENT(OUT) :: istatus
  INTEGER :: i, k

  atime = 'controlled previous observation'
  n_meso_g = 0
  n_meso_pos = 0
  n_sao_g = 0
  n_sao_pos_g = 0
  n_sao_b = qc_previous_count
  n_sao_pos_b = qc_previous_count
  n_obs_g = qc_previous_count
  n_obs_pos_g = qc_previous_count
  n_obs_b = qc_previous_count
  n_obs_pos_b = qc_previous_count
  stn = '   '
  obstype = '        '
  wx = '        '
  lat = 40.0
  lon = -105.0
  elev = 1600.0
  t = 10.0
  td = 5.0
  dd = 180.0
  ff = 10.0
  ddg = 180.0
  ffg = 15.0
  pstn = 900.0
  pmsl = 1000.0
  alt = 1000.0
  ceil = -99.9
  lowcld = -99.9
  cover = -99.9
  rad = -99.9
  vis = 10.0
  store_hgt = -99.9
  kloud = 0
  idp3 = -99
  obstime = 1200
  store_emv = ' '
  store_amt = '    '
  IF (qc_reader_status == 1) THEN
    DO i = 1, qc_previous_count
      stn(i) = 'ABC'
      obstype(i) = 'METAR'
      wx(i) = 'CLEAR'
    END DO
  END IF
  istatus = qc_reader_status
END SUBROUTINE read_surface_old

PROGRAM test_previous_surface_qc
  USE previous_surface_qc_control
  IMPLICIT NONE
  INTEGER, PARAMETER :: mxstn = 4, ni = 2, nj = 2
  INTEGER :: rely(26,mxstn), ii(mxstn), jj(mxstn)
  REAL :: t(mxstn), td(mxstn), dd(mxstn), ff(mxstn), ddg(mxstn)
  REAL :: ffg(mxstn), pstn(mxstn), pmsl(mxstn), alt(mxstn), vis(mxstn)
  REAL :: rii(mxstn), rjj(mxstn), t_bk(ni,nj), td_bk(ni,nj)
  REAL :: mslp_bk(ni,nj)
  CHARACTER(LEN=3) :: stn(mxstn)
  CHARACTER(LEN=256) :: infile
  CHARACTER(LEN=9) :: filename
  INTEGER :: n_obs_b, n_sao_b, n_sao_g, istatus
  INTEGER :: expected, i

  filename = 'TEST00001'
  infile = 'previous/262281200.lso'
  t = 10.0
  td = 5.0
  dd = 180.0
  ff = 10.0
  ddg = 180.0
  ffg = 15.0
  pstn = 900.0
  pmsl = 1000.0
  alt = 1000.0
  vis = 10.0
  rii = 1.0
  rjj = 1.0
  ii = 1
  jj = 1
  stn = 'ABC'
  t_bk = 10.0
  td_bk = 5.0
  mslp_bk = 1000.0

  CALL check_qc('reader_missing', -1, 1, 0)
  CALL check_qc('reader_corrupt', 0, 1, -2)
  CALL check_qc('reader_unknown', 77, 1, -2)
  CALL check_qc('current_missing', 1, 0, 0)
  CALL check_qc('previous_missing', 1, 1, 0)
  CALL check_qc('normal_with_background', 1, 1, 1)
  CALL check_open_failure()
  WRITE(6,'(A)') 'QC_TEST_PASS'

CONTAINS

  SUBROUTINE check_qc(label, reader_status, current_count, want_status)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(IN) :: reader_status, current_count, want_status
    INTEGER :: j
    LOGICAL :: opened

    qc_reader_status = reader_status
    IF (label == 'previous_missing') THEN
      qc_previous_count = 0
    ELSE
      qc_previous_count = 1
    END IF
    n_obs_b = current_count
    rely = -777
    istatus = 123
    CALL qcdata(filename, infile, rely, mxstn, t, td, dd, ff, ddg, ffg, &
                pstn, pmsl, alt, vis, stn, rii, rjj, ii, jj, n_obs_b, &
                n_sao_b, n_sao_g, ni, nj, t_bk, td_bk, mslp_bk, 20.0, &
                20.0, 20.0, 1, 1, 1, istatus)
    IF (istatus /= want_status) THEN
      WRITE(6,'(A,1X,A,2(1X,I0))') 'QC_CASE_FAIL', label, istatus, want_status
      ERROR STOP 1
    END IF
    INQUIRE(UNIT=60, OPENED=opened)
    IF (opened) ERROR STOP 'QC log unit left open'
    IF (label == 'normal_with_background') THEN
      IF (rely(7,1) /= 10 .OR. rely(8,1) /= 10 .OR. rely(14,1) /= 10) THEN
        WRITE(6,'(A)') 'QC_CASE_FAIL background reliability'
        ERROR STOP 1
      END IF
    END IF
    WRITE(6,'(A,1X,A,1X,I0)') 'QC_CASE_PASS', label, istatus
  END SUBROUTINE check_qc

  SUBROUTINE check_open_failure()
    qc_reader_status = 1
    qc_previous_count = 1
    qc_open_failure = .TRUE.
    n_obs_b = 1
    istatus = 123
    ! get_directory selects the missing/ path for this filename suffix.
    filename = 'OPENFAIL1'
    CALL qcdata(filename, infile, rely, mxstn, t, td, dd, ff, ddg, ffg, &
                pstn, pmsl, alt, vis, stn, rii, rjj, ii, jj, n_obs_b, &
                n_sao_b, n_sao_g, ni, nj, t_bk, td_bk, mslp_bk, 20.0, &
                20.0, 20.0, 1, 1, 1, istatus)
    IF (istatus /= -2) THEN
      WRITE(6,'(A,1X,I0)') 'QC_CASE_FAIL log_open_failure', istatus
      ERROR STOP 1
    END IF
    qc_open_failure = .FALSE.
    WRITE(6,'(A,1X,A,1X,I0)') 'QC_CASE_PASS', 'log_open_failure', istatus
  END SUBROUTINE check_open_failure

END PROGRAM test_previous_surface_qc

#endif

#ifdef LSO_DRIVER

SUBROUTINE read_surface_data(i4time, btime, n_obs_g, n_obs_b, time, wmoid, &
                             stations, provider, wx, reptype, autostntype, &
                             lat, lon, elev, t, td, rh, dd, ff, ddg, ffg, &
                             alt, stnp, mslp, delpch, delp, vis, solar, sfct, &
                             sfcm, pcp1, pcp3, pcp6, pcp24, snow, kkk_s, &
                             max24t, min24t, t_ea, td_ea, rh_ea, dd_ea, &
                             ff_ea, alt_ea, p_ea, vis_ea, solar_ea, sfct_ea, &
                             sfcm_ea, pcp_ea, snow_ea, store_cldamt, &
                             store_cldht, maxsta, jstatus)
  USE previous_surface_qc_control
  IMPLICIT NONE
  INTEGER*4, INTENT(OUT) :: n_obs_g, n_obs_b, jstatus
  INTEGER*4, INTENT(IN) :: i4time, maxsta
  CHARACTER(LEN=24), INTENT(OUT) :: btime
  CHARACTER(LEN=20), INTENT(OUT) :: stations(maxsta)
  CHARACTER(LEN=11), INTENT(OUT) :: provider(maxsta)
  CHARACTER(LEN=25), INTENT(OUT) :: wx(maxsta)
  CHARACTER(LEN=6), INTENT(OUT) :: reptype(maxsta), autostntype(maxsta)
  CHARACTER(LEN=4), INTENT(OUT) :: store_cldamt(maxsta,5)
  INTEGER*4, INTENT(OUT) :: time(*), wmoid(*), delpch(*), kkk_s(*)
  REAL*4, INTENT(OUT) :: lat(*), lon(*), elev(*), t(*), td(*), rh(*)
  REAL*4, INTENT(OUT) :: dd(*), ff(*), ddg(*), ffg(*), alt(*), stnp(*)
  REAL*4, INTENT(OUT) :: mslp(*), delp(*), vis(*), solar(*), sfct(*), sfcm(*)
  REAL*4, INTENT(OUT) :: pcp1(*), pcp3(*), pcp6(*), pcp24(*), snow(*)
  REAL*4, INTENT(OUT) :: max24t(*), min24t(*), t_ea(*), td_ea(*), rh_ea(*)
  REAL*4, INTENT(OUT) :: dd_ea(*), ff_ea(*), alt_ea(*), p_ea(*), vis_ea(*)
  REAL*4, INTENT(OUT) :: solar_ea(*), sfct_ea(*), sfcm_ea(*), pcp_ea(*)
  REAL*4, INTENT(OUT) :: snow_ea(*), store_cldht(maxsta,5)

  jstatus = lso_data_status
  n_obs_g = 0
  n_obs_b = 0
  IF (jstatus == 1) THEN
    btime = 'controlled LSO time'
    n_obs_g = 1
    n_obs_b = 1
    stations(1) = 'ABC'
    provider(1) = 'TEST'
    reptype(1) = 'METAR'
    autostntype(1) = 'A  '
    wx(1) = 'CLEAR'
    lat(1) = 40.0
    lon(1) = -105.0
    elev(1) = 1600.0
    t(1) = 10.0
    td(1) = 5.0
    dd(1) = 180.0
    ff(1) = 10.0
    ddg(1) = 180.0
    ffg(1) = 15.0
    alt(1) = 1000.0
    stnp(1) = 900.0
    mslp(1) = 1000.0
    vis(1) = 10.0
    kkk_s(1) = 0
  END IF
END SUBROUTINE read_surface_data

SUBROUTINE read_surface_dataqc(i4time, btime, n_obs_g, n_obs_b, time, wmoid, &
                               stations, provider, wx, reptype, autostntype, &
                               lat, lon, elev, t, td, rh, dd, ff, ddg, ffg, &
                               alt, stnp, mslp, delpch, delp, vis, solar, &
                               sfct, sfcm, pcp1, pcp3, pcp6, pcp24, snow, &
                               kkk_s, max24t, min24t, t_ea, td_ea, rh_ea, &
                               dd_ea, ff_ea, alt_ea, p_ea, vis_ea, solar_ea, &
                               sfct_ea, sfcm_ea, pcp_ea, snow_ea, store_cldamt, &
                               store_cldht, maxsta, jstatus)
  IMPLICIT NONE
  INTEGER*4, INTENT(OUT) :: n_obs_g, n_obs_b, jstatus
  INTEGER*4, INTENT(IN) :: i4time, maxsta
  CHARACTER(LEN=24), INTENT(OUT) :: btime
  CHARACTER(LEN=20), INTENT(OUT) :: stations(maxsta)
  CHARACTER(LEN=11), INTENT(OUT) :: provider(maxsta)
  CHARACTER(LEN=25), INTENT(OUT) :: wx(maxsta)
  CHARACTER(LEN=6), INTENT(OUT) :: reptype(maxsta), autostntype(maxsta)
  CHARACTER(LEN=4), INTENT(OUT) :: store_cldamt(maxsta,5)
  INTEGER*4, INTENT(OUT) :: time(*), wmoid(*), delpch(*), kkk_s(*)
  REAL*4, INTENT(OUT) :: lat(*), lon(*), elev(*), t(*), td(*), rh(*)
  REAL*4, INTENT(OUT) :: dd(*), ff(*), ddg(*), ffg(*), alt(*), stnp(*)
  REAL*4, INTENT(OUT) :: mslp(*), delp(*), vis(*), solar(*), sfct(*), sfcm(*)
  REAL*4, INTENT(OUT) :: pcp1(*), pcp3(*), pcp6(*), pcp24(*), snow(*)
  REAL*4, INTENT(OUT) :: max24t(*), min24t(*), t_ea(*), td_ea(*), rh_ea(*)
  REAL*4, INTENT(OUT) :: dd_ea(*), ff_ea(*), alt_ea(*), p_ea(*), vis_ea(*)
  REAL*4, INTENT(OUT) :: solar_ea(*), sfct_ea(*), sfcm_ea(*), pcp_ea(*)
  REAL*4, INTENT(OUT) :: snow_ea(*), store_cldht(maxsta,5)
  jstatus = -1
  n_obs_g = 0
  n_obs_b = 0
END SUBROUTINE read_surface_dataqc

SUBROUTINE s_len(string, length)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: string
  INTEGER, INTENT(OUT) :: length
  length = LEN_TRIM(string)
END SUBROUTINE s_len

SUBROUTINE i4time_fname_lp(filetime, i4time, istatus)
  USE previous_surface_qc_control
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: filetime
  INTEGER, INTENT(OUT) :: i4time
  INTEGER, INTENT(OUT) :: istatus
  i4time = 0
  istatus = lso_time_status
END SUBROUTINE i4time_fname_lp

SUBROUTINE filter_string(string)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(INOUT) :: string
END SUBROUTINE filter_string

PROGRAM test_previous_lso_reader
  USE previous_surface_qc_control
  IMPLICIT NONE
  EXTERNAL :: read_surface_old
  INTEGER, PARAMETER :: maxsta = 4
  CHARACTER(LEN=256) :: infile, atime
  CHARACTER(LEN=3) :: stn(maxsta)
  CHARACTER(LEN=8) :: obstype(maxsta), wx(maxsta)
  CHARACTER(LEN=1) :: store_emv(maxsta,5)
  CHARACTER(LEN=4) :: store_amt(maxsta,5)
  REAL :: lat(maxsta), lon(maxsta), elev(maxsta), t(maxsta), td(maxsta)
  REAL :: dd(maxsta), ff(maxsta), ddg(maxsta), ffg(maxsta), pstn(maxsta)
  REAL :: pmsl(maxsta), alt(maxsta), ceil(maxsta), lowcld(maxsta)
  REAL :: cover(maxsta), rad(maxsta), store_hgt(maxsta,5), vis(maxsta)
  INTEGER :: n_meso_g, n_meso_pos, n_sao_g, n_sao_pos_g, n_sao_b
  INTEGER :: n_sao_pos_b, n_obs_g, n_obs_pos_g, n_obs_b, n_obs_pos_b
  INTEGER :: kloud(maxsta), idp3(maxsta), obstime(maxsta), istatus

  CALL lso_case('data_success', 1, 1, 'previous/262281200.lso')
  CALL lso_case('data_missing', -1, -1, 'previous/262281200.lso')
  CALL lso_case('data_corrupt', 0, 0, 'previous/262281200.lso')
  CALL lso_case('data_unknown', 77, 0, 'previous/262281200.lso')
  CALL lso_case('short_filename', 1, 0, 'short')
  lso_time_status = 0
  CALL lso_case('invalid_time', 1, 0, 'previous/262281200.lso')
  WRITE(6,'(A)') 'LSO_TEST_PASS'

CONTAINS

  SUBROUTINE lso_case(label, source_status, expected_status, name)
    CHARACTER(LEN=*), INTENT(IN) :: label, name
    INTEGER, INTENT(IN) :: source_status, expected_status
    lso_data_status = source_status
    infile = name
    istatus = 123
    CALL read_surface_old(infile, maxsta, atime, n_meso_g, n_meso_pos, &
                          n_sao_g, n_sao_pos_g, n_sao_b, n_sao_pos_b, &
                          n_obs_g, n_obs_pos_g, n_obs_b, n_obs_pos_b, stn, &
                          obstype, lat, lon, elev, wx, t, td, dd, ff, ddg, &
                          ffg, pstn, pmsl, alt, kloud, ceil, lowcld, cover, &
                          rad, idp3, store_emv, store_amt, store_hgt, vis, &
                          obstime, istatus)
    IF (istatus /= expected_status) THEN
      WRITE(6,'(A,1X,A,1X,I0)') 'LSO_CASE_FAIL', label, istatus
      ERROR STOP 1
    END IF
    IF (expected_status == 1 .AND. (n_obs_b /= 1 .OR. &
        TRIM(stn(1)) /= 'ABC')) THEN
      WRITE(6,'(A,1X,A,1X,I0)') 'LSO_CASE_FAIL', label, istatus
      ERROR STOP 1
    END IF
    WRITE(6,'(A,1X,A,1X,I0)') 'LSO_CASE_PASS', label, istatus
  END SUBROUTINE lso_case

END PROGRAM test_previous_lso_reader

#endif
