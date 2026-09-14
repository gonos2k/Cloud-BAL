! Controlled external routines for the upstream temperature status test.
!
! The production overlay is linked unchanged.  These routines intentionally
! do not read or write LAPS data; UPSTREAM_TEMPERATURE_CASE selects a bounded
! failure at one external call.  The test program at the end calls the real
! laps_temp routine extracted by the runner and checks the call counters.

MODULE temperature_stub_control
  IMPLICIT NONE

  CHARACTER(LEN=64) :: scenario_override = ' '
  INTEGER :: domain_calls = 0
  INTEGER :: cycle_calls = 0
  INTEGER :: sfc_t_calls = 0
  INTEGER :: sfc_ps_calls = 0
  INTEGER :: put_temp_calls = 0
  INTEGER :: ghbry_calls = 0
  INTEGER :: pres_to_ht_calls = 0
  INTEGER :: pbl_write_calls = 0

CONTAINS

  SUBROUTINE reset_stub()
    scenario_override = ' '
    domain_calls = 0
    cycle_calls = 0
    sfc_t_calls = 0
    sfc_ps_calls = 0
    put_temp_calls = 0
    ghbry_calls = 0
    pres_to_ht_calls = 0
    pbl_write_calls = 0
  END SUBROUTINE reset_stub

  SUBROUTINE set_scenario(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    scenario_override = ' '
    scenario_override(1:MIN(LEN(scenario_override), LEN_TRIM(name))) = &
      name(1:MIN(LEN(scenario_override), LEN_TRIM(name)))
  END SUBROUTINE set_scenario

  CHARACTER(LEN=64) FUNCTION scenario_name()
    CHARACTER(LEN=64) :: environment_name
    INTEGER :: length, status

    IF (LEN_TRIM(scenario_override) > 0) THEN
      scenario_name = scenario_override
      RETURN
    END IF

    environment_name = ' '
    CALL GET_ENVIRONMENT_VARIABLE('UPSTREAM_TEMPERATURE_CASE', &
         environment_name, length, status)
    IF (status == 0 .AND. length > 0) THEN
      scenario_name = environment_name
    ELSE
      scenario_name = 'success'
    END IF
  END FUNCTION scenario_name

  LOGICAL FUNCTION case_is(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    case_is = TRIM(scenario_name()) == TRIM(name)
  END FUNCTION case_is

  SUBROUTINE trace_call(name, status)
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: status
    WRITE(6,'(A,1X,A,1X,I0)') 'TRACE', TRIM(name), status
  END SUBROUTINE trace_call

END MODULE temperature_stub_control


SUBROUTINE get_systime(i4time, a9_time, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(OUT) :: i4time, istatus
  CHARACTER(LEN=*), INTENT(OUT) :: a9_time

  i4time = 2026010100
  a9_time = '260101000'
  IF (case_is('time')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('get_systime', istatus)
END SUBROUTINE get_systime


SUBROUTINE get_grid_dim_xy(nx, ny, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(OUT) :: nx, ny, istatus

  nx = 2
  ny = 2
  IF (case_is('dim')) THEN
    istatus = 0
  ELSE IF (case_is('invaliddim')) THEN
    nx = 0
    ny = 4
    istatus = 1
  ELSE IF (case_is('invaliddim_y')) THEN
    nx = 4
    ny = 0
    istatus = 1
  ELSE
    istatus = 1
  END IF
  CALL trace_call('get_grid_dim_xy', istatus)
END SUBROUTINE get_grid_dim_xy


SUBROUTINE get_laps_dimensions(nz, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(OUT) :: nz, istatus

  nz = 2
  istatus = 1
  IF (case_is('dim_z')) istatus = 0
  IF (case_is('invaliddim_z')) nz = 0
  CALL trace_call('get_laps_dimensions', istatus)
END SUBROUTINE get_laps_dimensions


SUBROUTINE get_domain_laps(nx, ny, grid_file, lat, lon, topo, spacing, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: nx, ny
  CHARACTER(LEN=*), INTENT(IN) :: grid_file
  REAL, INTENT(OUT) :: lat(nx,ny), lon(nx,ny), topo(nx,ny)
  REAL, INTENT(OUT) :: spacing
  INTEGER, INTENT(OUT) :: istatus

  domain_calls = domain_calls + 1
  lat = 35.0
  lon = 126.0
  topo = 100.0
  spacing = 1000.0
  IF (case_is('domain')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('get_domain_laps', istatus)
END SUBROUTINE get_domain_laps


SUBROUTINE get_laps_cycle_time(cycle_time, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(OUT) :: cycle_time, istatus

  cycle_calls = cycle_calls + 1
  cycle_time = 3600
  IF (case_is('cycle')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('get_laps_cycle_time', istatus)
END SUBROUTINE get_laps_cycle_time


SUBROUTINE get_laps_2dgrid(i4time, offset, nearest, ext, variable, units, &
                           comment, nx, ny, field, level, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time, offset, nx, ny, level
  INTEGER, INTENT(OUT) :: nearest
  CHARACTER(LEN=*), INTENT(IN) :: ext, variable
  CHARACTER(LEN=*), INTENT(OUT) :: units, comment
  REAL, INTENT(OUT) :: field(nx,ny)
  INTEGER, INTENT(OUT) :: istatus

  units = 'K'
  comment = 'stub field'
  nearest = i4time
  field = 280.0
  IF (TRIM(variable) == 'T') THEN
    sfc_t_calls = sfc_t_calls + 1
    IF (case_is('surf_t')) THEN
      istatus = 0
    ELSE
      istatus = 1
    END IF
  ELSE
    sfc_ps_calls = sfc_ps_calls + 1
    units = 'Pa'
    field = 90000.0
    IF (case_is('surf_ps')) THEN
      istatus = 0
    ELSE
      istatus = 1
    END IF
  END IF
  CALL trace_call('get_laps_2dgrid_'//TRIM(variable), istatus)
END SUBROUTINE get_laps_2dgrid


SUBROUTINE put_temp_anal(i4time, nx, ny, nz, heights, lat, lon, topo, &
                         temp_sfc, pres_sfc, iflag_write, cycle_time, &
                         spacing, temperature, pressure, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time, nx, ny, nz, iflag_write, cycle_time
  REAL, INTENT(OUT) :: heights(nx,ny,nz)
  REAL, INTENT(IN) :: lat(nx,ny), lon(nx,ny), topo(nx,ny)
  REAL, INTENT(IN) :: temp_sfc(nx,ny), pres_sfc(nx,ny)
  REAL, INTENT(IN) :: spacing
  REAL, INTENT(OUT) :: temperature(nx,ny,nz), pressure(nx,ny,nz)
  INTEGER, INTENT(OUT) :: istatus

  put_temp_calls = put_temp_calls + 1
  heights = 1000.0
  temperature = 280.0
  pressure = 80000.0
  IF (case_is('lt1')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('put_temp_anal', istatus)
END SUBROUTINE put_temp_anal


SUBROUTINE ghbry(i4time, p_3d, pb, sfc_t, lt1dat, htby, nx, ny, nz, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time, nx, ny, nz
  REAL, INTENT(IN) :: p_3d(nx,ny,nz), pb(nx,ny), sfc_t(nx,ny), lt1dat(nx,ny,nz)
  REAL, INTENT(OUT) :: htby(nx,ny)
  INTEGER, INTENT(OUT) :: istatus

  ghbry_calls = ghbry_calls + 1
  htby = 800.0
  IF (case_is('pbl_ghbry')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('ghbry', istatus)
END SUBROUTINE ghbry


SUBROUTINE pres_to_ht(pressure_pa, pressure_3d, heights_3d, nx, ny, nz, &
                      i, j, height_out, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: nx, ny, nz, i, j
  REAL, INTENT(IN) :: pressure_pa, pressure_3d(nx,ny,nz), heights_3d(nx,ny,nz)
  REAL, INTENT(OUT) :: height_out
  INTEGER, INTENT(OUT) :: istatus

  pres_to_ht_calls = pres_to_ht_calls + 1
  height_out = 500.0
  IF (case_is('pbl_pres_to_ht')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('pres_to_ht', istatus)
END SUBROUTINE pres_to_ht


SUBROUTINE move(source, destination, nx, ny)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: nx, ny
  REAL, INTENT(IN) :: source(nx,ny)
  REAL, INTENT(OUT) :: destination(nx,ny)
  destination = source
END SUBROUTINE move


SUBROUTINE put_laps_multi_2d(i4time, ext, variable, units, comment, field, &
                             nx, ny, nfield, istatus)
  USE temperature_stub_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time, nx, ny, nfield
  CHARACTER(LEN=*), INTENT(IN) :: ext, variable(nfield), units(nfield), comment(nfield)
  REAL, INTENT(IN) :: field(nx,ny,nfield)
  INTEGER, INTENT(OUT) :: istatus

  pbl_write_calls = pbl_write_calls + 1
  IF (case_is('pbl_write')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  CALL trace_call('put_laps_multi_2d', istatus)
END SUBROUTINE put_laps_multi_2d


INTEGER FUNCTION ishow_timer()
  USE temperature_stub_control
  IMPLICIT NONE
  ishow_timer = 0
  CALL trace_call('ishow_timer', 0)
END FUNCTION ishow_timer


PROGRAM test_laps_temp_status
  USE temperature_stub_control
  IMPLICIT NONE

  INTERFACE
    SUBROUTINE laps_temp(i4time_needed, nx, ny, nz, i_diag, nprods, &
                         iprod_number, j_status)
      INTEGER :: i4time_needed, nx, ny, nz, i_diag, nprods
      INTEGER :: iprod_number(20), j_status(20)
    END SUBROUTINE laps_temp
  END INTERFACE

  CALL check_case('domain', 4, 1, 0, 0, 0, 0, 0, 0)
  CALL check_case('cycle', 4, 1, 1, 0, 0, 0, 0, 0)
  CALL check_case('surf_t', 4, 1, 1, 1, 0, 0, 0, 0)
  CALL check_case('surf_ps', 4, 1, 1, 1, 1, 0, 0, 0)
  CALL check_case('lt1', 4, 1, 1, 1, 1, 1, 0, 0)
  CALL check_case('pbl_ghbry', 1, 1, 1, 1, 1, 1, 1, 0)
  CALL check_case('pbl_pres_to_ht', 1, 1, 1, 1, 1, 1, 1, 1)
  CALL check_case('pbl_write', 1, 1, 1, 1, 1, 1, 1, 4)
  CALL check_case('full', 1, 1, 1, 1, 1, 1, 1, 4)
  WRITE(6,'(A)') 'LAPS_TEMP_STATUS_TEST_PASS'

CONTAINS

  SUBROUTINE check_case(name, expected_status, expected_domain, expected_cycle, &
                        expected_t, expected_ps, expected_put, expected_ghbry, &
                        expected_pres)
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: expected_status, expected_domain, expected_cycle
    INTEGER, INTENT(IN) :: expected_t, expected_ps, expected_put
    INTEGER, INTENT(IN) :: expected_ghbry, expected_pres
    INTEGER :: nprods, i_diag
    INTEGER :: iprod_number(20), j_status(20)

    CALL reset_stub()
    CALL set_scenario(name)
    nprods = -1
    i_diag = 0
    iprod_number = -1
    j_status = -1
    CALL laps_temp(2026010100, 2, 2, 2, i_diag, nprods, iprod_number, j_status)

    IF (nprods /= 1 .OR. iprod_number(1) /= 28261 .OR. &
        j_status(1) /= expected_status) THEN
      WRITE(6,'(A,1X,A)') 'BAD_LAPS_RESULT', TRIM(name)
      ERROR STOP 1
    END IF
    IF (domain_calls /= expected_domain .OR. cycle_calls /= expected_cycle .OR. &
        sfc_t_calls /= expected_t .OR. sfc_ps_calls /= expected_ps .OR. &
        put_temp_calls /= expected_put .OR. ghbry_calls /= expected_ghbry .OR. &
        pres_to_ht_calls /= expected_pres) THEN
      WRITE(6,'(A,1X,A)') 'BAD_LAPS_CALL_COUNTS', TRIM(name)
      ERROR STOP 1
    END IF
    IF (pbl_write_calls /= MERGE(1, 0, expected_status == 1 .AND. &
         expected_pres == 4)) THEN
      WRITE(6,'(A,1X,A)') 'BAD_PBL_WRITE_COUNT', TRIM(name)
      ERROR STOP 1
    END IF
    WRITE(6,'(A,1X,A)') 'LAPS_CASE_PASS', TRIM(name)
  END SUBROUTINE check_case

END PROGRAM test_laps_temp_status
