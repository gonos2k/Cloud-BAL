! Total-water-conserving point operations.  All arguments use dry-air mixing
! ratio (kg kg-1) so vapor and hydrometeor masses share one budget.
MODULE cloud_bal_moisture
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: evaporate_to_target
  PUBLIC :: transfer_excess
  PUBLIC :: total_water
  PUBLIC :: allocate_precipitation

CONTAINS

  SUBROUTINE evaporate_to_target(vapor, condensate, vapor_target, status)
    REAL, INTENT(INOUT) :: vapor, condensate
    REAL, INTENT(IN) :: vapor_target
    INTEGER, INTENT(OUT) :: status
    REAL :: transfer

    status = 0
    IF (.NOT. ieee_is_finite(vapor) .OR. &
        .NOT. ieee_is_finite(condensate) .OR. &
        .NOT. ieee_is_finite(vapor_target)) RETURN
    IF (vapor < 0.0 .OR. condensate < 0.0 .OR. vapor_target < 0.0) RETURN

    transfer = MIN(condensate, MAX(0.0, vapor_target - vapor))
    condensate = condensate - transfer
    vapor = vapor + transfer
    status = 1
  END SUBROUTINE evaporate_to_target

  SUBROUTINE transfer_excess(source, sink, source_cap, status)
    REAL, INTENT(INOUT) :: source, sink
    REAL, INTENT(IN) :: source_cap
    INTEGER, INTENT(OUT) :: status
    REAL :: transfer

    status = 0
    IF (.NOT. ieee_is_finite(source) .OR. .NOT. ieee_is_finite(sink) .OR. &
        .NOT. ieee_is_finite(source_cap)) RETURN
    IF (source < 0.0 .OR. sink < 0.0 .OR. source_cap < 0.0) RETURN

    transfer = MAX(0.0, source - source_cap)
    source = source - transfer
    sink = sink + transfer
    status = 1
  END SUBROUTINE transfer_excess

  REAL FUNCTION total_water(vapor, cloud_liquid, cloud_ice, rain, snow, graupel)
    REAL, INTENT(IN) :: vapor, cloud_liquid, cloud_ice, rain, snow, graupel
    total_water = vapor + cloud_liquid + cloud_ice + rain + snow + graupel
  END FUNCTION total_water

  SUBROUTINE allocate_precipitation(total, temperature, phase_code, &
                                    rain, snow, graupel, status)
    REAL, INTENT(IN) :: total, temperature
    INTEGER, INTENT(IN) :: phase_code
    REAL, INTENT(OUT) :: rain, snow, graupel
    INTEGER, INTENT(OUT) :: status
    REAL :: liquid_fraction, graupel_fraction

    rain = 0.0
    snow = 0.0
    graupel = 0.0
    status = 0
    IF (.NOT. ieee_is_finite(total) .OR. &
        .NOT. ieee_is_finite(temperature) .OR. total < 0.0) RETURN

    ! Known LAPS phase codes: 1 rain, 2 snow, 3 freezing rain,
    ! 4 sleet, 5 hail.  Mixed/unknown-but-present code 0 is diagnosed
    ! continuously from temperature; unsupported codes fail explicitly.
    SELECT CASE (phase_code)
    CASE (1)
      rain = total
    CASE (2)
      snow = total
    CASE (3)
      rain = 0.75 * total
      graupel = 0.25 * total
    CASE (4)
      snow = 0.50 * total
      graupel = 0.50 * total
    CASE (5)
      graupel = total
    CASE (0)
      liquid_fraction = MIN(1.0, MAX(0.0, (temperature - 263.15) / 10.0))
      graupel_fraction = 0.20 * (1.0 - liquid_fraction)
      rain = liquid_fraction * total
      graupel = graupel_fraction * total
      snow = total - rain - graupel
    CASE DEFAULT
      RETURN
    END SELECT
    status = 1
  END SUBROUTINE allocate_precipitation

END MODULE cloud_bal_moisture
