! Controlled dependencies for the upstream surface status test.
!
! The runner links the real upstream main and includes the real writer-status
! block.  These routines do not access operational files or produce LAPS data.

MODULE upstream_surface_status_control
  IMPLICIT NONE

  CHARACTER(LEN=64) :: main_case_override = ' '
  INTEGER :: writer_status_value = 1
  INTEGER :: writer_calls = 0
  INTEGER :: timer_calls = 0

CONTAINS

  SUBROUTINE reset_writer()
    writer_status_value = 1
    writer_calls = 0
    timer_calls = 0
  END SUBROUTINE reset_writer

  SUBROUTINE set_writer_status(status)
    INTEGER, INTENT(IN) :: status
    writer_status_value = status
    writer_calls = 0
    timer_calls = 0
  END SUBROUTINE set_writer_status

  CHARACTER(LEN=64) FUNCTION main_case()
    CHARACTER(LEN=64) :: environment_name
    INTEGER :: length, status

    IF (LEN_TRIM(main_case_override) > 0) THEN
      main_case = main_case_override
      RETURN
    END IF

    environment_name = ' '
    CALL GET_ENVIRONMENT_VARIABLE('UPSTREAM_SURFACE_MAIN_CASE', &
         environment_name, length, status)
    IF (status == 0 .AND. length > 0) THEN
      main_case = environment_name
    ELSE
      main_case = 'success'
    END IF
  END FUNCTION main_case

  LOGICAL FUNCTION case_is(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    case_is = TRIM(main_case()) == TRIM(name)
  END FUNCTION case_is

END MODULE upstream_surface_status_control


SUBROUTINE get_config(istatus)
  USE upstream_surface_status_control
  IMPLICIT NONE
  INTEGER, INTENT(OUT) :: istatus

  IF (case_is('config_failure')) THEN
    istatus = 0
  ELSE
    istatus = 1
    CALL initialize_surface_common()
  END IF
  WRITE(6,'(A,1X,I0)') 'SURFACE_GET_CONFIG', istatus
END SUBROUTINE get_config


SUBROUTINE find_domain_name(c_dum, laps_domain, istatus)
  USE upstream_surface_status_control
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(OUT) :: c_dum, laps_domain
  INTEGER, INTENT(OUT) :: istatus

  c_dum = 'controlled surface test'
  laps_domain = 'TESTDOM'
  IF (case_is('domain_failure')) THEN
    istatus = 0
  ELSE
    istatus = 1
  END IF
  WRITE(6,'(A,1X,I0)') 'SURFACE_FIND_DOMAIN', istatus
END SUBROUTINE find_domain_name


SUBROUTINE laps_sfc_sub(ni, nj, nk, mxstn, laps_cycle_time, grid_spacing, &
                        laps_domain)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: ni, nj, nk, mxstn, laps_cycle_time
  REAL, INTENT(IN) :: grid_spacing
  CHARACTER(LEN=*), INTENT(IN) :: laps_domain

  WRITE(6,'(A,1X,4(I0,1X),F0.1,1X,A)') 'SURFACE_MAIN_SUB', ni, nj, nk, &
       mxstn, grid_spacing, TRIM(laps_domain)
END SUBROUTINE laps_sfc_sub


SUBROUTINE get_directory(ext, directory, length)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: ext
  CHARACTER(LEN=*), INTENT(OUT) :: directory
  INTEGER, INTENT(OUT) :: length

  directory = 'controlled-surface-status'
  length = LEN_TRIM(directory)
END SUBROUTINE get_directory


SUBROUTINE write_laps_data(i4time, directory, extension, nx, ny, nz, nfield, &
                           variable, level, level_coordinate, unit, comment, &
                           data, status)
  USE upstream_surface_status_control
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: i4time, nx, ny, nz, nfield
  CHARACTER(LEN=*), INTENT(IN) :: directory, extension
  CHARACTER(LEN=*), INTENT(IN) :: variable(*), level_coordinate(*)
  CHARACTER(LEN=*), INTENT(IN) :: unit(*), comment(*)
  INTEGER, INTENT(IN) :: level(*)
  REAL, INTENT(IN) :: data(*)
  INTEGER, INTENT(OUT) :: status

  writer_calls = writer_calls + 1
  status = writer_status_value
END SUBROUTINE write_laps_data


INTEGER FUNCTION ishow_timer()
  USE upstream_surface_status_control
  IMPLICIT NONE

  timer_calls = timer_calls + 1
  ishow_timer = 0
END FUNCTION ishow_timer


PROGRAM test_upstream_surface_status
  USE upstream_surface_status_control
  IMPLICIT NONE
  EXTERNAL :: writer_status_probe

  CALL check_writer(-1, -1, 0, 0)
  CALL check_writer(0, 0, 0, 0)
  CALL check_writer(1, 1, 1, 1)
  CALL check_writer(2, 2, 0, 0)
  WRITE(6,'(A)') 'UPSTREAM_SURFACE_STATUS_TEST_PASS'

CONTAINS

  SUBROUTINE check_writer(requested_status, expected_status, expected_elapsed, &
                          expected_continued)
    INTEGER, INTENT(IN) :: requested_status, expected_status
    INTEGER, INTENT(IN) :: expected_elapsed, expected_continued
    INTEGER :: jstatus(20), elapsed_calls, continued

    CALL set_writer_status(requested_status)
    jstatus = -99
    elapsed_calls = 0
    continued = 0
    CALL writer_status_probe(requested_status, jstatus, elapsed_calls, continued)
    IF (jstatus(3) /= expected_status .OR. &
        elapsed_calls /= expected_elapsed .OR. &
        continued /= expected_continued .OR. writer_calls /= 1) THEN
      WRITE(6,'(A,1X,I0,3(1X,I0))') 'BAD_WRITER_STATUS', requested_status, &
           jstatus(3), elapsed_calls, continued
      ERROR STOP 1
    END IF
  END SUBROUTINE check_writer

END PROGRAM test_upstream_surface_status
