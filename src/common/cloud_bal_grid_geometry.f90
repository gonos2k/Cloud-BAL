! Shared geometry contract for compact-support localization.
MODULE cloud_bal_grid_geometry
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic,ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  PUBLIC :: cumulative_horizontal_distance
  PUBLIC :: bounded_grid_radius
  PUBLIC :: pressure_face_segment
  PUBLIC :: partition_pressure_face

  TYPE :: pressure_face_segment
    INTEGER :: left_level
    INTEGER :: right_level
    REAL(real64) :: pressure_thickness
  END TYPE pressure_face_segment

  INTERFACE cumulative_horizontal_distance
    MODULE PROCEDURE cumulative_horizontal_distance_r32
    MODULE PROCEDURE cumulative_horizontal_distance_r64
  END INTERFACE cumulative_horizontal_distance

CONTAINS

  PURE SUBROUTINE partition_pressure_face(left_interface,right_interface, &
                                           segments,ok)
    REAL(real64), INTENT(IN) :: left_interface(:),right_interface(:)
    TYPE(pressure_face_segment), ALLOCATABLE, INTENT(OUT) :: segments(:)
    LOGICAL, INTENT(OUT) :: ok
    TYPE(pressure_face_segment), ALLOCATABLE :: compact_segments(:)
    INTEGER :: left_level,right_level,nleft,nright,nsegments,upper_bound,i
    REAL(real64) :: left_top,right_top,left_bottom,right_bottom,overlap

    ok=.FALSE.
    ALLOCATE(segments(0))
    nleft=SIZE(left_interface)-1
    nright=SIZE(right_interface)-1
    IF (nleft<1 .OR. nright<1) RETURN

    ! Keep all IEEE finite checks separate from ordered comparisons.  This
    ! avoids evaluating a pressure ordering relation while an input is NaN.
    DO i=1,SIZE(left_interface)
      IF (.NOT.ieee_is_finite(left_interface(i))) RETURN
    END DO
    DO i=1,SIZE(right_interface)
      IF (.NOT.ieee_is_finite(right_interface(i))) RETURN
    END DO

    DO i=1,SIZE(left_interface)
      IF (left_interface(i)<=0.0_real64) RETURN
    END DO
    DO i=1,SIZE(right_interface)
      IF (right_interface(i)<=0.0_real64) RETURN
    END DO
    DO i=2,SIZE(left_interface)
      IF (left_interface(i)>left_interface(i-1)) RETURN
    END DO
    DO i=2,SIZE(right_interface)
      IF (right_interface(i)>right_interface(i-1)) RETURN
    END DO

    upper_bound=nleft+nright-1
    DEALLOCATE(segments)
    ALLOCATE(segments(upper_bound))
    nsegments=0
    left_level=1
    right_level=1

    DO WHILE (left_level<=nleft .AND. right_level<=nright)
      left_bottom=left_interface(left_level)
      left_top=left_interface(left_level+1)
      right_bottom=right_interface(right_level)
      right_top=right_interface(right_level+1)
      overlap=MIN(left_bottom,right_bottom)-MAX(left_top,right_top)
      IF (overlap>0.0_real64) THEN
        nsegments=nsegments+1
        segments(nsegments)%left_level=left_level
        segments(nsegments)%right_level=right_level
        segments(nsegments)%pressure_thickness=overlap
      END IF

      IF (left_top>right_top) THEN
        left_level=left_level+1
      ELSE IF (right_top>left_top) THEN
        right_level=right_level+1
      ELSE
        left_level=left_level+1
        right_level=right_level+1
      END IF
    END DO

    IF (nsegments<upper_bound) THEN
      ALLOCATE(compact_segments(nsegments))
      IF (nsegments>0) compact_segments=segments(:nsegments)
      CALL MOVE_ALLOC(compact_segments,segments)
    END IF
    ok=.TRUE.
  END SUBROUTINE partition_pressure_face

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
