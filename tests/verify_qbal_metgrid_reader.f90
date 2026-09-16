PROGRAM verify_qbal_metgrid_reader
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32, int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE parallel_module, ONLY: parallel_finish, parallel_start
  USE read_met_module, ONLY: read_met_close, read_met_init, read_next_met_field
  USE met_data_module, ONLY: met_data
  USE misc_definitions_module, ONLY: PROJ_LC
  IMPLICIT NONE

  TYPE :: direct_record
    INTEGER :: version, nx, ny, iproj
    REAL :: xfcst, xlvl, startlat, startlon, dx, dy, xlonc
    REAL :: truelat1, truelat2
    REAL :: earth_radius
    LOGICAL :: is_wind_grid_rel
    CHARACTER(9) :: field
    CHARACTER(24) :: hdate
    CHARACTER(25) :: units
    CHARACTER(32) :: map_source
    CHARACTER(46) :: desc
    CHARACTER(8) :: startloc
    REAL, ALLOCATABLE :: slab(:,:)
  END TYPE direct_record

  TYPE(met_data) :: actual
  TYPE(direct_record) :: expected
  CHARACTER(1024) :: prefix, lookup_date
  CHARACTER(24) :: expected_hdate
  CHARACTER(1024) :: input_name
  INTEGER :: init_status, reader_status, direct_unit, io_status
  INTEGER :: record_count
  INTEGER(int64) :: file_size, consumed_bytes
  LOGICAL :: at_eof

  IF (COMMAND_ARGUMENT_COUNT() /= 3) CALL fail( &
       'usage: verify_qbal_metgrid_reader prefix lookup_date expected_hdate')
  CALL GET_COMMAND_ARGUMENT(1, prefix)
  CALL GET_COMMAND_ARGUMENT(2, lookup_date)
  CALL GET_COMMAND_ARGUMENT(3, expected_hdate)

  input_name = TRIM(prefix)//':'//TRIM(lookup_date)
  CALL parallel_start()
  CALL read_met_init(TRIM(prefix), .FALSE., TRIM(lookup_date), init_status)
  IF (init_status /= 0) THEN
    CALL read_met_close()
    CALL fail('metgrid reader could not open WPS input')
  END IF

  OPEN(NEWUNIT=direct_unit, FILE=TRIM(input_name), STATUS='OLD', &
       ACTION='READ', FORM='UNFORMATTED', ACCESS='SEQUENTIAL', &
       IOSTAT=io_status)
  IF (io_status /= 0) THEN
    CALL read_met_close()
    CALL fail('direct WPS input open failed')
  END IF
  INQUIRE(FILE=TRIM(input_name), SIZE=file_size)

  record_count = 0
  consumed_bytes = 0_int64
  DO
    CALL read_direct_record(direct_unit, expected, at_eof)
    IF (at_eof) THEN
      IF (consumed_bytes /= file_size) THEN
        CLOSE(direct_unit)
        CALL read_met_close()
        CALL fail('WPS unexpected EOF in version record')
      END IF
      CALL read_next_met_field(actual, reader_status)
      IF (reader_status == 0) THEN
        CLOSE(direct_unit)
        CALL read_met_close()
        CALL fail('metgrid reader returned data past WPS EOF')
      END IF
      EXIT
    END IF

    CALL read_next_met_field(actual, reader_status)
    IF (reader_status /= 0) THEN
      CLOSE(direct_unit)
      CALL read_met_close()
      CALL fail('metgrid reader failed before WPS EOF')
    END IF

    record_count = record_count + 1
    CALL compare_record(actual, expected, expected_hdate, record_count)
    consumed_bytes = consumed_bytes + record_bytes(expected%nx, expected%ny)
    IF (ASSOCIATED(actual%slab)) DEALLOCATE(actual%slab)
  END DO

  CLOSE(direct_unit, IOSTAT=io_status)
  IF (io_status /= 0) THEN
    CALL read_met_close()
    CALL fail('direct WPS input close failed')
  END IF
  CALL read_met_close()
  CALL parallel_finish()

  IF (record_count == 0) CALL fail('WPS input contains no complete records')
  WRITE(*,'(A,I0)') 'PASS_SCOPED: records=', record_count

CONTAINS

  SUBROUTINE fail(message)
    CHARACTER(*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail

  LOGICAL FUNCTION same_bits(a, b)
    REAL, INTENT(IN) :: a, b
    INTEGER(int32) :: bits_a, bits_b

    bits_a = TRANSFER(a, 0_int32)
    bits_b = TRANSFER(b, 0_int32)
    same_bits = bits_a == bits_b
  END FUNCTION same_bits

  SUBROUTINE compare_real(actual_value, expected_value, label)
    REAL, INTENT(IN) :: actual_value, expected_value
    CHARACTER(*), INTENT(IN) :: label

    IF (.NOT.ieee_is_finite(actual_value) .OR. &
        .NOT.ieee_is_finite(expected_value)) CALL fail(TRIM(label)//': nonfinite')
    IF (.NOT.same_bits(actual_value, expected_value)) &
      CALL fail(TRIM(label)//': bits differ')
  END SUBROUTINE compare_real

  SUBROUTINE compare_slab(actual_slab, expected_slab, label)
    REAL, INTENT(IN) :: actual_slab(:,:), expected_slab(:,:)
    CHARACTER(*), INTENT(IN) :: label
    INTEGER :: i, j
    CHARACTER(256) :: item

    IF (ANY(SHAPE(actual_slab) /= SHAPE(expected_slab))) &
      CALL fail(TRIM(label)//': shape mismatch')
    DO j=1,SIZE(actual_slab,2)
      DO i=1,SIZE(actual_slab,1)
        IF (.NOT.ieee_is_finite(expected_slab(i,j))) &
          CALL fail(TRIM(label)//': direct slab nonfinite')
        IF (.NOT.ieee_is_finite(actual_slab(i,j))) &
          CALL fail(TRIM(label)//': reader slab nonfinite')
        IF (.NOT.same_bits(actual_slab(i,j), expected_slab(i,j))) THEN
          WRITE(item,'(A,I0,A,I0,A)') TRIM(label)//': bits differ at (',i,',',j,')'
          CALL fail(TRIM(item))
        END IF
      END DO
    END DO
  END SUBROUTINE compare_slab

  SUBROUTINE read_direct_record(unit, record, at_eof)
    INTEGER, INTENT(IN) :: unit
    TYPE(direct_record), INTENT(OUT) :: record
    LOGICAL, INTENT(OUT) :: at_eof
    INTEGER :: ios, wind_raw, alloc_status

    at_eof = .FALSE.
    IF (ALLOCATED(record%slab)) DEALLOCATE(record%slab)
    READ(unit, IOSTAT=ios) record%version
    IF (ios < 0) THEN
      at_eof = .TRUE.
      RETURN
    END IF
    IF (ios /= 0) CALL fail('WPS unexpected EOF in version record')
    IF (record%version /= 5) CALL fail('WPS version mismatch')

    READ(unit, IOSTAT=ios) record%hdate, record%xfcst, record%map_source, &
         record%field, record%units, record%desc, record%xlvl, record%nx, &
         record%ny, record%iproj
    IF (ios /= 0) CALL fail('WPS unexpected EOF in metadata record')
    IF (record%nx <= 0 .OR. record%ny <= 0) CALL fail('WPS grid dimensions invalid')
    IF (record%iproj /= 3) CALL fail('WPS projection is not Lambert (iproj 3)')
    READ(unit, IOSTAT=ios) record%startloc, record%startlat, record%startlon, &
         record%dx, record%dy, record%xlonc, record%truelat1, &
         record%truelat2, record%earth_radius
    IF (ios /= 0) CALL fail('WPS unexpected EOF in projection record')
    IF (record%startloc /= 'SWCORNER') CALL fail('WPS KNOWNLOC mismatch')
    CALL validate_geometry(record)

    READ(unit, IOSTAT=ios) wind_raw
    IF (ios /= 0) CALL fail('WPS unexpected EOF in wind metadata record')
    IF (wind_raw /= -1 .AND. wind_raw /= 0 .AND. wind_raw /= 1) &
      CALL fail('WPS wind metadata invalid')
    record%is_wind_grid_rel = wind_raw /= 0

    ALLOCATE(record%slab(record%nx,record%ny), STAT=alloc_status)
    IF (alloc_status /= 0) CALL fail('WPS slab allocation failed')
    READ(unit, IOSTAT=ios) record%slab
    IF (ios /= 0) CALL fail('WPS unexpected EOF in slab record')
    IF (ANY(.NOT.ieee_is_finite(record%slab))) &
      CALL fail('WPS slab contains nonfinite values')
  END SUBROUTINE read_direct_record

  SUBROUTINE validate_geometry(record)
    TYPE(direct_record), INTENT(IN) :: record

    IF (.NOT.ieee_is_finite(record%startlat) .OR. &
        .NOT.ieee_is_finite(record%startlon) .OR. &
        .NOT.ieee_is_finite(record%dx) .OR. &
        .NOT.ieee_is_finite(record%dy) .OR. &
        .NOT.ieee_is_finite(record%xlonc) .OR. &
        .NOT.ieee_is_finite(record%truelat1) .OR. &
        .NOT.ieee_is_finite(record%truelat2) .OR. &
        .NOT.ieee_is_finite(record%earth_radius)) &
      CALL fail('WPS geometry contains nonfinite values')
    IF (record%dx <= 0.0 .OR. record%dy <= 0.0 .OR. &
        record%earth_radius <= 0.0) CALL fail('WPS geometry scale nonpositive')
  END SUBROUTINE validate_geometry

  INTEGER(int64) FUNCTION record_bytes(nx, ny)
    INTEGER, INTENT(IN) :: nx, ny

    record_bytes = 244_int64 + 4_int64 * INT(nx,int64) * INT(ny,int64)
  END FUNCTION record_bytes

  SUBROUTINE compare_record(actual, expected, expected_hdate, record_number)
    TYPE(met_data), INTENT(IN) :: actual
    TYPE(direct_record), INTENT(IN) :: expected
    CHARACTER(24), INTENT(IN) :: expected_hdate
    INTEGER, INTENT(IN) :: record_number
    REAL :: expected_startlat, expected_startlon, expected_dx, expected_dy
    REAL :: expected_xlonc
    CHARACTER(64) :: label
    LOGICAL :: reader_time_bad, source_time_bad

    WRITE(label,'(A,I0)') 'record ', record_number
    reader_time_bad = actual%hdate /= expected_hdate
    source_time_bad = expected%hdate /= expected_hdate
    IF (reader_time_bad) THEN
      WRITE(*,'(A)') 'FAIL: metgrid reader time mismatch'
      IF (source_time_bad) WRITE(*,'(A)') 'FAIL: WPS time mismatch'
      ERROR STOP 1
    END IF
    IF (source_time_bad) CALL fail('WPS time mismatch')
    IF (actual%hdate /= expected%hdate) CALL fail('metgrid reader time mismatch')

    IF (actual%version /= expected%version) CALL fail(TRIM(label)//': version mismatch')
    IF (actual%field /= expected_field(expected%field)) &
      CALL fail(TRIM(label)//': field mismatch')
    IF (actual%units /= expected%units) CALL fail(TRIM(label)//': units mismatch')
    IF (actual%map_source /= expected%map_source) &
      CALL fail(TRIM(label)//': map_source mismatch')
    IF (actual%desc /= expected%desc) CALL fail(TRIM(label)//': description mismatch')
    IF (actual%nx /= expected%nx .OR. actual%ny /= expected%ny) &
      CALL fail(TRIM(label)//': dimensions mismatch')
    IF (actual%iproj /= PROJ_LC) CALL fail(TRIM(label)//': projection mismatch')
    IF (actual%is_wind_grid_rel .NEQV. expected%is_wind_grid_rel) &
      CALL fail(TRIM(label)//': wind metadata mismatch')
    CALL compare_real(actual%xfcst, expected%xfcst, TRIM(label)//' XFCST')
    CALL compare_real(actual%xlvl, expected%xlvl, TRIM(label)//' XLVL')

    expected_startlat = expected%startlat
    expected_startlon = expected%startlon
    expected_xlonc = expected%xlonc
    expected_dx = expected%dx
    expected_dy = expected%dy
    IF (expected_startlon > 180.0) expected_startlon = expected_startlon - 360.0
    IF (expected_xlonc > 180.0) expected_xlonc = expected_xlonc - 360.0
    IF (expected_startlat < -90.0) expected_startlat = -90.0
    IF (expected_startlat > 90.0) expected_startlat = 90.0
    expected_dx = expected_dx * 1000.0
    expected_dy = expected_dy * 1000.0

    CALL compare_real(actual%startlat, expected_startlat, TRIM(label)//' startlat')
    CALL compare_real(actual%startlon, expected_startlon, TRIM(label)//' startlon')
    CALL compare_real(actual%starti, 1.0, TRIM(label)//' starti')
    CALL compare_real(actual%startj, 1.0, TRIM(label)//' startj')
    CALL compare_real(actual%earth_radius, expected%earth_radius, &
         TRIM(label)//' earth_radius')

    CALL compare_real(actual%dx, expected_dx, TRIM(label)//' dx')
    CALL compare_real(actual%dy, expected_dy, TRIM(label)//' dy')
    CALL compare_real(actual%xlonc, expected_xlonc, TRIM(label)//' xlonc')
    CALL compare_real(actual%truelat1, expected%truelat1, TRIM(label)//' truelat1')
    CALL compare_real(actual%truelat2, expected%truelat2, TRIM(label)//' truelat2')
    CALL compare_slab(actual%slab, expected%slab, TRIM(label)//' slab')
  END SUBROUTINE compare_record

  CHARACTER(9) FUNCTION expected_field(field)
    CHARACTER(9), INTENT(IN) :: field

    expected_field = field
    IF (field == 'HGT      ') expected_field = 'GHT      '
  END FUNCTION expected_field

END PROGRAM verify_qbal_metgrid_reader
