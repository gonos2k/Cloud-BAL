! Cloud-BAL field-level data contract.
!
! A value array is never used as its own missing-data indicator.  The
! metadata and cell validity mask travel together so that a partially valid
! field is distinguishable from both an absent field and a physical zero.
MODULE cloud_bal_field_contracts
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: FIELD_FAILED   = 0
  INTEGER, PARAMETER, PUBLIC :: FIELD_OK       = 1
  INTEGER, PARAMETER, PUBLIC :: FIELD_DEGRADED = 2

  INTEGER, PARAMETER, PUBLIC :: SOURCE_NONE       = 0
  INTEGER, PARAMETER, PUBLIC :: SOURCE_BACKGROUND = 1
  INTEGER, PARAMETER, PUBLIC :: SOURCE_CLOUD      = 2
  INTEGER, PARAMETER, PUBLIC :: SOURCE_RADAR_3D   = 4
  INTEGER, PARAMETER, PUBLIC :: SOURCE_RADAR_2D   = 8
  INTEGER, PARAMETER, PUBLIC :: SOURCE_MODEL      = 16
  INTEGER, PARAMETER, PUBLIC :: SOURCE_LIGHTNING  = 32
  INTEGER, PARAMETER, PUBLIC :: SOURCE_THIN_CLOUD = 64
  INTEGER, PARAMETER, PUBLIC :: SOURCE_FALLBACK   = 128

  TYPE, PUBLIC :: field_contract
    CHARACTER(LEN=16) :: name = ''
    CHARACTER(LEN=32) :: valid_time = ''
    CHARACTER(LEN=24) :: units = ''
    INTEGER :: nx = 0
    INTEGER :: ny = 0
    INTEGER :: nz = 0
    INTEGER :: status = FIELD_FAILED
    INTEGER :: source = SOURCE_NONE
    LOGICAL, ALLOCATABLE :: valid(:,:,:)
  END TYPE field_contract

  PUBLIC :: initialize_field_contract
  PUBLIC :: capture_field_validity
  PUBLIC :: contract_metadata_ok
  PUBLIC :: refresh_field_status
  PUBLIC :: valid_fraction

  INTERFACE capture_field_validity
    MODULE PROCEDURE capture_field_validity_1d
    MODULE PROCEDURE capture_field_validity_2d
    MODULE PROCEDURE capture_field_validity_3d
  END INTERFACE capture_field_validity

CONTAINS

  SUBROUTINE initialize_field_contract(field, name, valid_time, units, &
                                       nx, ny, nz, source)
    TYPE(field_contract), INTENT(OUT) :: field
    CHARACTER(LEN=*), INTENT(IN) :: name, valid_time, units
    INTEGER, INTENT(IN) :: nx, ny, nz, source

    field%name = name
    field%valid_time = valid_time
    field%units = units
    field%nx = nx
    field%ny = ny
    field%nz = nz
    field%source = source
    field%status = FIELD_FAILED
    ALLOCATE(field%valid(nx,ny,nz))
    field%valid = .FALSE.
  END SUBROUTINE initialize_field_contract

  SUBROUTINE capture_field_validity_3d(field, values, read_status, lower, upper, &
                                       missing_abs)
    TYPE(field_contract), INTENT(INOUT) :: field
    REAL, INTENT(IN) :: values(:,:,:)
    INTEGER, INTENT(IN) :: read_status
    REAL, INTENT(IN) :: lower, upper, missing_abs
    IF (.NOT. ALLOCATED(field%valid)) RETURN
    field%valid = .FALSE.
    IF (read_status /= 0) THEN
      field%status = FIELD_FAILED
      RETURN
    END IF
    IF (ANY(SHAPE(values) /= (/field%nx, field%ny, field%nz/))) THEN
      field%status = FIELD_FAILED
      RETURN
    END IF

    field%valid = scalar_is_valid(values,lower,upper,missing_abs)
    CALL refresh_field_status(field)
  END SUBROUTINE capture_field_validity_3d

  SUBROUTINE capture_field_validity_2d(field, values, read_status, lower, upper, &
                                       missing_abs)
    TYPE(field_contract), INTENT(INOUT) :: field
    REAL, INTENT(IN) :: values(:,:)
    INTEGER, INTENT(IN) :: read_status
    REAL, INTENT(IN) :: lower, upper, missing_abs

    IF (.NOT. ALLOCATED(field%valid)) RETURN
    field%valid = .FALSE.
    IF (read_status /= 0 .OR. field%nz /= 1 .OR. &
        ANY(SHAPE(values) /= (/field%nx,field%ny/))) THEN
      field%status = FIELD_FAILED
      RETURN
    END IF
    field%valid(:,:,1) = scalar_is_valid(values,lower,upper,missing_abs)
    CALL refresh_field_status(field)
  END SUBROUTINE capture_field_validity_2d

  SUBROUTINE capture_field_validity_1d(field, values, read_status, lower, upper, &
                                       missing_abs)
    TYPE(field_contract), INTENT(INOUT) :: field
    REAL, INTENT(IN) :: values(:)
    INTEGER, INTENT(IN) :: read_status
    REAL, INTENT(IN) :: lower, upper, missing_abs

    IF (.NOT. ALLOCATED(field%valid)) RETURN
    field%valid = .FALSE.
    IF (read_status /= 0 .OR. field%ny /= 1 .OR. field%nz /= 1 .OR. &
        SIZE(values) /= field%nx) THEN
      field%status = FIELD_FAILED
      RETURN
    END IF
    field%valid(:,1,1) = scalar_is_valid(values,lower,upper,missing_abs)
    CALL refresh_field_status(field)
  END SUBROUTINE capture_field_validity_1d

  PURE ELEMENTAL LOGICAL FUNCTION scalar_is_valid(value,lower,upper,missing_abs)
    REAL, INTENT(IN) :: value,lower,upper,missing_abs
    scalar_is_valid=.FALSE.
    IF (.NOT.ieee_is_finite(value)) RETURN
    scalar_is_valid=value>=lower .AND. value<=upper .AND. &
                    ABS(value)<missing_abs
  END FUNCTION scalar_is_valid

  SUBROUTINE refresh_field_status(field)
    TYPE(field_contract), INTENT(INOUT) :: field
    INTEGER :: valid_count, total_count

    field%status = FIELD_FAILED
    IF (.NOT. ALLOCATED(field%valid)) RETURN
    total_count = SIZE(field%valid)
    IF (total_count == 0) RETURN

    valid_count = COUNT(field%valid)
    IF (valid_count == total_count) THEN
      field%status = FIELD_OK
    ELSE IF (valid_count > 0) THEN
      field%status = FIELD_DEGRADED
    END IF
  END SUBROUTINE refresh_field_status

  LOGICAL FUNCTION contract_metadata_ok(field, valid_time, units, nx, ny, nz)
    TYPE(field_contract), INTENT(IN) :: field
    CHARACTER(LEN=*), INTENT(IN) :: valid_time, units
    INTEGER, INTENT(IN) :: nx, ny, nz

    contract_metadata_ok = TRIM(field%valid_time) == TRIM(valid_time) .AND. &
                           TRIM(field%units) == TRIM(units) .AND. &
                           field%nx == nx .AND. field%ny == ny .AND. &
                           field%nz == nz
  END FUNCTION contract_metadata_ok

  REAL FUNCTION valid_fraction(field)
    TYPE(field_contract), INTENT(IN) :: field

    valid_fraction = 0.0
    IF (.NOT. ALLOCATED(field%valid)) RETURN
    IF (SIZE(field%valid) == 0) RETURN
    valid_fraction = REAL(COUNT(field%valid)) / REAL(SIZE(field%valid))
  END FUNCTION valid_fraction

END MODULE cloud_bal_field_contracts
