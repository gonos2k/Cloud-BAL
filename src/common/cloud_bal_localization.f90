! Compact observational support for cloud/precipitation balance increments.
MODULE cloud_bal_localization
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  PUBLIC :: build_compact_influence_3d
  PUBLIC :: wendland_c2

CONTAINS

  PURE REAL FUNCTION wendland_c2(radius)
    REAL, INTENT(IN) :: radius
    REAL :: one_minus

    IF (.NOT. ieee_is_finite(radius) .OR. radius < 0.0 .OR. radius >= 1.0) THEN
      wendland_c2 = 0.0
      RETURN
    END IF
    one_minus = 1.0 - radius
    wendland_c2 = one_minus**4 * (1.0 + 4.0*radius)
  END FUNCTION wendland_c2

  SUBROUTINE build_compact_influence_3d(source_valid, pressure, dx, dy, &
                                        horizontal_radius_m, &
                                        pressure_radius_pa, influence, status)
    LOGICAL, INTENT(IN) :: source_valid(:,:,:)
    REAL, INTENT(IN) :: pressure(:), dx(:,:), dy(:,:)
    REAL, INTENT(IN) :: horizontal_radius_m, pressure_radius_pa
    REAL, INTENT(OUT) :: influence(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx, ny, nz, i, j, k, io, jo, ko, irad, jrad
    INTEGER :: imin, imax, jmin, jmax
    REAL :: minimum_dx, minimum_dy, local_dx, local_dy
    REAL :: horizontal_distance, pressure_distance, radius, kernel

    status = 0
    influence = 0.0
    nx = SIZE(source_valid,1)
    ny = SIZE(source_valid,2)
    nz = SIZE(source_valid,3)
    IF (SIZE(influence,1) /= nx .OR. SIZE(influence,2) /= ny .OR. &
        SIZE(influence,3) /= nz .OR. SIZE(pressure) /= nz .OR. &
        SIZE(dx,1) /= nx .OR. SIZE(dx,2) /= ny .OR. &
        SIZE(dy,1) /= nx .OR. SIZE(dy,2) /= ny) RETURN
    IF (nx < 1 .OR. ny < 1 .OR. nz < 1) RETURN
    IF (.NOT. ieee_is_finite(horizontal_radius_m) .OR. &
        .NOT. ieee_is_finite(pressure_radius_pa) .OR. &
        horizontal_radius_m <= 0.0 .OR. pressure_radius_pa <= 0.0) RETURN
    IF (ANY(.NOT. ieee_is_finite(pressure)) .OR. ANY(pressure <= 0.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(dx)) .OR. ANY(dx <= 0.0) .OR. &
        ANY(.NOT. ieee_is_finite(dy)) .OR. ANY(dy <= 0.0)) RETURN

    IF (.NOT. ANY(source_valid)) THEN
      status = 2
      RETURN
    END IF

    minimum_dx = MINVAL(dx)
    minimum_dy = MINVAL(dy)
    irad = MIN(nx-1, CEILING(horizontal_radius_m/minimum_dx))
    jrad = MIN(ny-1, CEILING(horizontal_radius_m/minimum_dy))

    DO ko = 1, nz
      DO jo = 1, ny
        DO io = 1, nx
          IF (.NOT. source_valid(io,jo,ko)) CYCLE
          imin = MAX(1,io-irad)
          imax = MIN(nx,io+irad)
          jmin = MAX(1,jo-jrad)
          jmax = MIN(ny,jo+jrad)
          DO k = 1, nz
            pressure_distance = ABS(pressure(k)-pressure(ko))
            IF (pressure_distance >= pressure_radius_pa) CYCLE
            DO j = jmin, jmax
              DO i = imin, imax
                local_dx = 0.5*(dx(i,j)+dx(io,jo))
                local_dy = 0.5*(dy(i,j)+dy(io,jo))
                horizontal_distance = SQRT(((i-io)*local_dx)**2 + &
                                                   ((j-jo)*local_dy)**2)
                IF (horizontal_distance >= horizontal_radius_m) CYCLE
                radius = SQRT((horizontal_distance/horizontal_radius_m)**2 + &
                              (pressure_distance/pressure_radius_pa)**2)
                kernel = wendland_c2(radius)
                influence(i,j,k) = MAX(influence(i,j,k),kernel)
              END DO
            END DO
          END DO
        END DO
      END DO
    END DO

    WHERE (source_valid) influence = 1.0
    IF (ANY(.NOT. ieee_is_finite(influence)) .OR. &
        MINVAL(influence) < 0.0 .OR. MAXVAL(influence) > 1.0) THEN
      influence = 0.0
      status = 0
      RETURN
    END IF
    status = 1
  END SUBROUTINE build_compact_influence_3d

END MODULE cloud_bal_localization
