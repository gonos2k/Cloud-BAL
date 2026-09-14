MODULE surface_reader_test_control
  IMPLICIT NONE
  CHARACTER(LEN=256) :: lso_root = ' '
  CHARACTER(LEN=256) :: tmp_root = ' '
  CHARACTER(LEN=9) :: active_stamp = '262281200'
  LOGICAL :: bad_tmp = .FALSE.
CONTAINS
  SUBROUTINE initialize_control()
    INTEGER :: length, status
    CALL GET_ENVIRONMENT_VARIABLE('SURFACE_TEST_LSO_DIR', lso_root, length, status)
    IF (status /= 0 .OR. length <= 0) STOP 2
    CALL GET_ENVIRONMENT_VARIABLE('SURFACE_TEST_TMP_DIR', tmp_root, length, status)
    IF (status /= 0 .OR. length <= 0) STOP 2
  END SUBROUTINE initialize_control

  SUBROUTINE set_stamp(stamp)
    CHARACTER(LEN=*), INTENT(IN) :: stamp
    active_stamp = ' '
    active_stamp(1:LEN_TRIM(stamp)) = stamp(1:LEN_TRIM(stamp))
  END SUBROUTINE set_stamp

  SUBROUTINE lso_file(path)
    CHARACTER(LEN=*), INTENT(OUT) :: path
    path = TRIM(lso_root) // active_stamp // '.lso'
  END SUBROUTINE lso_file

  SUBROUTINE tmp_file(path)
    CHARACTER(LEN=*), INTENT(OUT) :: path
    path = TRIM(tmp_root) // active_stamp // '.tmp'
  END SUBROUTINE tmp_file
END MODULE surface_reader_test_control

SUBROUTINE get_directory(ext, directory, length)
  USE surface_reader_test_control
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: ext
  CHARACTER(LEN=*), INTENT(OUT) :: directory
  INTEGER, INTENT(OUT) :: length
  directory = ' '
  IF (TRIM(ext) == 'lso') THEN
    directory = lso_root
  ELSE IF (TRIM(ext) == 'tmp') THEN
    IF (bad_tmp) THEN
      directory = TRIM(tmp_root) // 'missing-directory/'
    ELSE
      directory = tmp_root
    END IF
  ELSE
    STOP 2
  END IF
  length = LEN_TRIM(directory)
END SUBROUTINE get_directory

SUBROUTINE make_fnam_lp(i4time, name, status)
  USE surface_reader_test_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time
  CHARACTER(LEN=*), INTENT(OUT) :: name
  INTEGER, INTENT(OUT) :: status
  name = active_stamp
  status = 1
END SUBROUTINE make_fnam_lp

PROGRAM test_surface_observation_reader
  USE surface_reader_test_control
  IMPLICIT NONE
  CHARACTER(LEN=16) :: actual_mode
  CHARACTER(LEN=16) :: actual_stamp
  INTEGER :: length, status

  CALL initialize_control()
  actual_mode = ' '
  CALL GET_ENVIRONMENT_VARIABLE('SURFACE_TEST_ACTUAL', actual_mode, length, status)
  IF (status == 0 .AND. TRIM(actual_mode) == '1') THEN
    actual_stamp = ' '
    CALL GET_ENVIRONMENT_VARIABLE('SURFACE_TEST_STAMP', actual_stamp, length, status)
    IF (status == 0 .AND. length > 0) THEN
      CALL run_actual_selected(TRIM(actual_stamp))
    ELSE
      CALL run_actual_cases()
    END IF
  ELSE
    CALL run_synthetic_cases()
  END IF
  WRITE(6,'(A)') 'SURFACE_READER_TEST_PASS'

CONTAINS

  SUBROUTINE run_synthetic_cases()
    CALL set_stamp('262281200')
    CALL remove_fixture()
    CALL invoke_case('missing', -1, 0, 0)

    CALL write_truncated_header()
    CALL invoke_case('truncated-header', 0, 0, 0)

    CALL write_truncated_record()
    CALL invoke_case('truncated-record', 0, 0, 0)

    CALL write_header(0, 0)
    CALL invoke_case('empty-valid', -1, 0, 0)

    CALL write_header(-1, 0)
    CALL invoke_case('negative-grid-count', 0, 0, 0)
    CALL write_header(0, -1)
    CALL invoke_case('negative-box-count', 0, 0, 0)
    CALL write_header(3, 2)
    CALL invoke_case('grid-count-greater-than-box', 0, 0, 0)
    CALL write_header(0, 1001)
    CALL invoke_case('box-count-over-maxsta', 0, 0, 0)

    CALL write_valid(2, 2, -1)
    CALL invoke_case('negative-cloud-layers', 0, 0, 0)
    CALL write_valid(2, 2, 6)
    CALL invoke_case('cloud-layers-over-five', 0, 0, 0)

    CALL write_valid(2, 2, 0)
    CALL invoke_case('valid-two-observations', 1, 2, 2)
    CALL write_valid(2, 2, 5)
    CALL invoke_case('valid-five-cloud-layers', 1, 2, 2)

    CALL write_valid(2, 2, 0)
    bad_tmp = .TRUE.
    CALL invoke_case('summary-output-open-failure', 0, 0, 0)
    bad_tmp = .FALSE.

    CALL remove_fixture()
    CALL invoke_case('repeat-after-missing', -1, 0, 0)
    CALL write_valid(2, 2, 0)
    CALL invoke_case('repeat-valid-after-failure', 1, 2, 2)
    CALL invoke_case('repeat-valid-second-read', 1, 2, 2)
  END SUBROUTINE run_synthetic_cases

  SUBROUTINE run_actual_cases()
    CALL run_actual('262281200', 816)
    CALL run_actual('262281300', 816)
    CALL run_actual('262281400', 803)
    CALL run_actual('262281500', 814)
  END SUBROUTINE run_actual_cases

  SUBROUTINE run_actual_selected(stamp)
    CHARACTER(LEN=*), INTENT(IN) :: stamp
    SELECT CASE (TRIM(stamp))
    CASE ('262281200')
      CALL run_actual('262281200', 816)
    CASE ('262281300')
      CALL run_actual('262281300', 816)
    CASE ('262281400')
      CALL run_actual('262281400', 803)
    CASE ('262281500')
      CALL run_actual('262281500', 814)
    CASE DEFAULT
      WRITE(6,'(A,1X,A)') 'UNKNOWN_SURFACE_ACTUAL_STAMP', stamp
      STOP 1
    END SELECT
  END SUBROUTINE run_actual_selected

  SUBROUTINE run_actual(stamp, expected_count)
    CHARACTER(LEN=*), INTENT(IN) :: stamp
    INTEGER, INTENT(IN) :: expected_count
    INTEGER :: n_obs_g, n_obs_b, jstatus
    REAL :: lat(1000), lon(1000), elev(1000), t(1000), td(1000)
    CALL set_stamp(stamp)
    CALL invoke_reader(n_obs_g, n_obs_b, jstatus, lat, lon, elev, t, td)
    IF (jstatus /= 1 .OR. n_obs_g /= expected_count .OR. &
        n_obs_b /= expected_count) THEN
      WRITE(6,'(A,1X,A,3(1X,I0))') 'BAD_SURFACE_ACTUAL', stamp, &
           jstatus, n_obs_g, n_obs_b
      STOP 1
    END IF
    IF (lat(1) /= lat(1) .OR. lon(1) /= lon(1) .OR. &
        elev(1) /= elev(1) .OR. t(1) /= t(1) .OR. td(1) /= td(1)) THEN
      WRITE(6,'(A,1X,A)') 'NONFINITE_SURFACE_ACTUAL', stamp
      STOP 1
    END IF
    WRITE(6,'(A,1X,A,1X,I0)') 'SURFACE_ACTUAL_PASS', stamp, n_obs_b
    CALL assert_units_closed(stamp)
  END SUBROUTINE run_actual

  SUBROUTINE invoke_case(label, expected_status, expected_ng, expected_nb)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(IN) :: expected_status, expected_ng, expected_nb
    INTEGER :: n_obs_g, n_obs_b, jstatus
    REAL :: lat(1000), lon(1000), elev(1000), t(1000), td(1000)
    CALL invoke_reader(n_obs_g, n_obs_b, jstatus, lat, lon, elev, t, td)
    IF (jstatus /= expected_status .OR. n_obs_g /= expected_ng .OR. &
        n_obs_b /= expected_nb) THEN
      WRITE(6,'(A,1X,A,5(1X,I0))') 'BAD_SURFACE_CASE', label, jstatus, &
           n_obs_g, n_obs_b, expected_status, expected_nb
      STOP 1
    END IF
    CALL assert_units_closed(label)
  END SUBROUTINE invoke_case

  SUBROUTINE invoke_reader(n_obs_g, n_obs_b, jstatus, lat, lon, elev, t, td)
    INTEGER, INTENT(OUT) :: n_obs_g, n_obs_b, jstatus
    REAL, INTENT(OUT) :: lat(1000), lon(1000), elev(1000), t(1000), td(1000)
    INTEGER :: i4time, maxsta
    INTEGER :: time(1000), wmoid(1000), delpch(1000), kkk_s(1000)
    REAL :: rh(1000), dd(1000), ff(1000), ddg(1000), ffg(1000)
    REAL :: alt(1000), stnp(1000), mslp(1000), delp(1000), vis(1000)
    REAL :: solar(1000), sfct(1000), sfcm(1000), pcp1(1000), pcp3(1000)
    REAL :: pcp6(1000), pcp24(1000), snow(1000), max24t(1000), min24t(1000)
    REAL :: t_ea(1000), td_ea(1000), rh_ea(1000), dd_ea(1000), ff_ea(1000)
    REAL :: alt_ea(1000), p_ea(1000), vis_ea(1000), solar_ea(1000)
    REAL :: sfct_ea(1000), sfcm_ea(1000), pcp_ea(1000), snow_ea(1000)
    REAL :: store_cldht(1000,5)
    CHARACTER(LEN=24) :: btime
    CHARACTER(LEN=20) :: stations(1000)
    CHARACTER(LEN=11) :: provider(1000)
    CHARACTER(LEN=25) :: wx(1000)
    CHARACTER(LEN=6) :: reptype(1000), autostntype(1000)
    CHARACTER(LEN=4) :: store_cldamt(1000,5)
    maxsta = 1000
    i4time = 0
    btime = ' '
    CALL read_surface_data(i4time,btime,n_obs_g,n_obs_b,time,wmoid,stations, &
         provider,wx,reptype,autostntype,lat,lon,elev,t,td,rh,dd,ff,ddg,ffg, &
         alt,stnp,mslp,delpch,delp,vis,solar,sfct,sfcm,pcp1,pcp3,pcp6,pcp24, &
         snow,kkk_s,max24t,min24t,t_ea,td_ea,rh_ea,dd_ea,ff_ea,alt_ea,p_ea, &
         vis_ea,solar_ea,sfct_ea,sfcm_ea,pcp_ea,snow_ea,store_cldamt, &
         store_cldht,maxsta,jstatus)
  END SUBROUTINE invoke_reader

  SUBROUTINE assert_units_closed(label)
    CHARACTER(LEN=*), INTENT(IN) :: label
    LOGICAL :: opened
    INTEGER :: io_status
    INQUIRE(UNIT=11, OPENED=opened, IOSTAT=io_status)
    IF (io_status /= 0 .OR. opened) THEN
      WRITE(6,'(A,1X,A)') 'UNIT_11_LEFT_OPEN', label
      STOP 1
    END IF
    INQUIRE(UNIT=333, OPENED=opened, IOSTAT=io_status)
    IF (io_status /= 0 .OR. opened) THEN
      WRITE(6,'(A,1X,A)') 'UNIT_333_LEFT_OPEN', label
      STOP 1
    END IF
  END SUBROUTINE assert_units_closed

  SUBROUTINE remove_fixture()
    CHARACTER(LEN=512) :: path
    CALL lso_file(path)
    CALL remove_file(path)
    CALL tmp_file(path)
    CALL remove_file(path)
  END SUBROUTINE remove_fixture

  SUBROUTINE remove_file(path)
    CHARACTER(LEN=*), INTENT(IN) :: path
    LOGICAL :: exists
    INTEGER :: io_status
    INQUIRE(FILE=TRIM(path), EXIST=exists)
    IF (exists) THEN
      OPEN(77, FILE=TRIM(path), STATUS='OLD', IOSTAT=io_status)
      IF (io_status == 0) CLOSE(77, STATUS='DELETE', IOSTAT=io_status)
    END IF
  END SUBROUTINE remove_file

  SUBROUTINE open_lso(unit_number)
    INTEGER, INTENT(OUT) :: unit_number
    CHARACTER(LEN=512) :: path
    CALL lso_file(path)
    unit_number = 77
    OPEN(unit_number, FILE=TRIM(path), STATUS='REPLACE', ACTION='WRITE')
  END SUBROUTINE open_lso

  SUBROUTINE write_header(n_obs_g, n_obs_b)
    INTEGER, INTENT(IN) :: n_obs_g, n_obs_b
    INTEGER :: unit_number
    CALL remove_fixture()
    CALL open_lso(unit_number)
    WRITE(unit_number,'(1X,A24,2X,I6,2X,I6)') &
         '16-AUG-2026 12:00:00.00', n_obs_g, n_obs_b
    CLOSE(unit_number)
  END SUBROUTINE write_header

  SUBROUTINE write_truncated_header()
    INTEGER :: unit_number
    CHARACTER(LEN=512) :: path
    CALL remove_fixture()
    CALL lso_file(path)
    unit_number = 77
    OPEN(unit_number, FILE=TRIM(path), STATUS='REPLACE', ACTION='WRITE')
    WRITE(unit_number,'(A)') 'truncated header'
    CLOSE(unit_number)
  END SUBROUTINE write_truncated_header

  SUBROUTINE write_truncated_record()
    INTEGER :: unit_number
    CALL remove_fixture()
    CALL open_lso(unit_number)
    WRITE(unit_number,'(1X,A24,2X,I6,2X,I6)') &
         '16-AUG-2026 12:00:00.00', 1, 1
    WRITE(unit_number,'(1X,A20,2X,I8,2X,A11,2X,F8.4,1X,F9.4,2X,F8.1,2X,I8)') &
         'STATION-TRUNCATED', 1, 'TESTPROVIDER', 40.0, -75.0, 100.0, 1200
    CLOSE(unit_number)
  END SUBROUTINE write_truncated_record

  SUBROUTINE write_valid(n_obs_g, n_obs_b, layers)
    INTEGER, INTENT(IN) :: n_obs_g, n_obs_b, layers
    INTEGER :: unit_number, k, layer
    CALL remove_fixture()
    CALL open_lso(unit_number)
    WRITE(unit_number,'(1X,A24,2X,I6,2X,I6)') &
         '16-AUG-2026 12:00:00.00', n_obs_g, n_obs_b
    DO k=1,MAX(0,n_obs_b)
      WRITE(unit_number,'(1X,A20,2X,I8,2X,A11,2X,F8.4,1X,F9.4,2X,F8.1,2X,I8)') &
           'STATION-TEST', 100+k, 'TESTPROVIDER', 40.0, -75.0, 100.0, 1200
      WRITE(unit_number,'(9X,A6,6X,A6,2X,A30)') 'SYNOP', 'AUTO', 'CLEAR'
      WRITE(unit_number,'(5X,F8.2,2X,F5.2,2X,F8.2,2X,F5.2,2X,F8.2,2X,F5.2)') &
           70.0, 1.0, 65.0, 1.0, 50.0, 1.0
      WRITE(unit_number,'(5X,4(F8.1,2X),2(F6.2,2X))') &
           180.0, 5.0, 190.0, 7.0, 1.0, 1.0
      WRITE(unit_number,'(5X,F8.2,2X,F8.2,2X,F8.2,2X,I4,2X,F8.2,2X,F8.2,2X,F8.2)') &
           1000.0, 990.0, 1010.0, 0, 1.0, 1.0, 1.0
      WRITE(unit_number,'(5X,F8.2,2X,F6.3,2X,F8.1,2X,F6.1,2X,4F8.2)') &
           10.0, 1.0, 100.0, 1.0, 70.0, 1.0, 1.0, 1.0
      WRITE(unit_number,'(5X,4(F8.2,2X),F6.1,2X,F8.2,2X,F4.1)') &
           0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0
      WRITE(unit_number,'(5X,I4,2X,F8.2,2X,F8.2)') layers, 80.0, 30.0
      IF (layers > 0 .AND. layers <= 5) THEN
        DO layer=1,layers
          WRITE(unit_number,'(10X,A8,2X,F8.0)') 'CLR', 1000.0*layer
        END DO
      END IF
    END DO
    CLOSE(unit_number)
  END SUBROUTINE write_valid
END PROGRAM test_surface_observation_reader
