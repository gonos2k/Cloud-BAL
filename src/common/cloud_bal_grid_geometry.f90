! Shared geometry contract for compact-support localization.
MODULE cloud_bal_grid_geometry
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic,ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  PUBLIC :: cumulative_horizontal_distance
  PUBLIC :: bounded_grid_radius

  INTERFACE cumulative_horizontal_distance
    MODULE PROCEDURE cumulative_horizontal_distance_r32
    MODULE PROCEDURE cumulative_horizontal_distance_r64
  END INTERFACE cumulative_horizontal_distance

CONTAINS

  PURE SUBROUTINE bounded_grid_radius(radius,minimum_spacing,maximum_index, &
                                      radius_cells,ok)
    REAL(real64), INTENT(IN) :: radius,minimum_spacing
    INTEGER, INTENT(IN) :: maximum_index
    INTEGER, INTENT(OUT) :: radius_cells
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: full_span

    radius_cells=0
    ok=.FALSE.
    IF (.NOT.ieee_is_finite(radius) .OR. .NOT.ieee_is_finite(minimum_spacing) .OR. &
        radius<=0.0_real64 .OR. minimum_spacing<=0.0_real64 .OR. &
        maximum_index<0) RETURN
    IF (maximum_index==0) THEN
      ok=.TRUE.
      RETURN
    END IF
    IF (minimum_spacing>HUGE(full_span)/REAL(maximum_index,real64)) THEN
      radius_cells=CEILING(radius/minimum_spacing)
      ok=radius_cells>=0 .AND. radius_cells<=maximum_index
      RETURN
    END IF
    full_span=minimum_spacing*REAL(maximum_index,real64)
    IF (radius>=full_span) THEN
      radius_cells=maximum_index
    ELSE
      radius_cells=CEILING(radius/minimum_spacing)
    END IF
    ok=radius_cells>=0 .AND. radius_cells<=maximum_index
  END SUBROUTINE bounded_grid_radius

  PURE SUBROUTINE cumulative_horizontal_distance_r32(dx,dy,i,j,is,js,distance,ok)
    REAL(real32), INTENT(IN) :: dx(:,:),dy(:,:)
    INTEGER, INTENT(IN) :: i,j,is,js
    REAL(real32), INTENT(OUT) :: distance
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: distance64

    distance=0.0_real32
    CALL cumulative_horizontal_distance_r64(REAL(dx,real64),REAL(dy,real64), &
                                             i,j,is,js,distance64,ok)
    IF (.NOT.ok .OR. distance64>REAL(HUGE(distance),real64)) THEN
      ok=.FALSE.
      RETURN
    END IF
    distance=REAL(distance64,real32)
    ok=ieee_is_finite(distance)
  END SUBROUTINE cumulative_horizontal_distance_r32

  PURE SUBROUTINE cumulative_horizontal_distance_r64(dx,dy,i,j,is,js,distance,ok)
    REAL(real64), INTENT(IN) :: dx(:,:),dy(:,:)
    INTEGER, INTENT(IN) :: i,j,is,js
    REAL(real64), INTENT(OUT) :: distance
    LOGICAL, INTENT(OUT) :: ok
    INTEGER :: ii,jj
    REAL(real64) :: x_distance,y_distance,step

    distance=0.0_real64
    ok=.FALSE.
    IF (ANY(SHAPE(dx)/=SHAPE(dy))) RETURN
    IF (MIN(i,is)<1 .OR. MAX(i,is)>SIZE(dx,1) .OR. &
        MIN(j,js)<1 .OR. MAX(j,js)>SIZE(dx,2)) RETURN

    x_distance=0.0_real64
    DO ii=MIN(i,is),MAX(i,is)-1
      ! Average adjacent-center spacing on the two endpoint rows.
      step=0.25_real64*dx(ii,j)+0.25_real64*dx(ii+1,j)+ &
           0.25_real64*dx(ii,js)+0.25_real64*dx(ii+1,js)
      IF (.NOT.ieee_is_finite(step) .OR. step<=0.0_real64 .OR. &
          step>HUGE(x_distance)-x_distance) RETURN
      x_distance=x_distance+step
    END DO

    y_distance=0.0_real64
    DO jj=MIN(j,js),MAX(j,js)-1
      ! Average adjacent-center spacing on the two endpoint columns.
      step=0.25_real64*dy(i,jj)+0.25_real64*dy(i,jj+1)+ &
           0.25_real64*dy(is,jj)+0.25_real64*dy(is,jj+1)
      IF (.NOT.ieee_is_finite(step) .OR. step<=0.0_real64 .OR. &
          step>HUGE(y_distance)-y_distance) RETURN
      y_distance=y_distance+step
    END DO

    distance=HYPOT(x_distance,y_distance)
    ok=ieee_is_finite(distance)
  END SUBROUTINE cumulative_horizontal_distance_r64

END MODULE cloud_bal_grid_geometry
