! Compact observational support for cloud/precipitation balance increments.
MODULE cloud_bal_localization
  USE, INTRINSIC :: iso_fortran_env,ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_grid_geometry,ONLY: bounded_grid_radius,cumulative_horizontal_distance
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
    REAL :: minimum_dx, minimum_dy
    REAL :: horizontal_distance, pressure_distance, radius, kernel
    REAL(real64) :: horizontal_distance64
    REAL(real64), ALLOCATABLE :: dx64(:,:),dy64(:,:)
    LOGICAL :: distance_ok,radius_ok

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
    CALL bounded_grid_radius(REAL(horizontal_radius_m,real64), &
      REAL(minimum_dx,real64),nx-1,irad,radius_ok)
    IF (.NOT.radius_ok) RETURN
    CALL bounded_grid_radius(REAL(horizontal_radius_m,real64), &
      REAL(minimum_dy,real64),ny-1,jrad,radius_ok)
    IF (.NOT.radius_ok) RETURN
    ALLOCATE(dx64(nx,ny),dy64(nx,ny))
    dx64=REAL(dx,real64)
    dy64=REAL(dy,real64)

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
                CALL cumulative_horizontal_distance(dx64,dy64,i,j,io,jo, &
                                                    horizontal_distance64,distance_ok)
                IF (.NOT.distance_ok) THEN
                  influence = 0.0
                  status = 0
                  RETURN
                END IF
                horizontal_distance=REAL(horizontal_distance64)
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
