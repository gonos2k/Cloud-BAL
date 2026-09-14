! CP01 independent pressure-interval overlap diagnostic.
!
! This is a pressure-diagnostic geometry test only.  It exercises the actual
! configure_pressure_geometry output and computes interval intersections with a
! local dense oracle against the sparse geometry implementation.  It does not
! call the balance operator or verify native dry-mass fluxes.
PROGRAM test_pressure_partial_face_oracle
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value, &
    ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state
  USE cloud_bal_grid_geometry, ONLY: pressure_face_segment,partition_pressure_face
  IMPLICIT NONE

  CALL test_six_column_geometry()
  CALL test_thin_center_domain_geometry()
  CALL test_partition_edges()
  PRINT *,'Pressure partial-face oracle passed: sparse partition, cross-level and independent tables'
  PRINT *,'Scope: pressure geometry; balance/native flux integration is not assessed'

CONTAINS

  SUBROUTINE test_six_column_geometry()
    INTEGER, PARAMETER :: nx=6,ny=1,nz=3
    REAL(real32), PARAMETER :: center32(3)=[100000.0_real32,95000.0_real32,90000.0_real32]
    REAL(real32), PARAMETER :: surface32(6)=[ &
      100000.0_real32,99000.0_real32,95500.0_real32,95000.0_real32, &
      92500.0_real32,91000.0_real32]
    REAL(real64), PARAMETER :: expected_interface(4,6)=RESHAPE([ &
      100000.0_real64,97500.0_real64,92500.0_real64,87500.0_real64, &
      99000.0_real64,99000.0_real64,92500.0_real64,87500.0_real64, &
      95500.0_real64,95500.0_real64,92500.0_real64,87500.0_real64, &
      95000.0_real64,95000.0_real64,92500.0_real64,87500.0_real64, &
      92500.0_real64,92500.0_real64,92500.0_real64,87500.0_real64, &
      91000.0_real64,91000.0_real64,91000.0_real64,87500.0_real64],[4,6])
    REAL(real64), PARAMETER :: expected_dp(3,6)=RESHAPE([ &
      2500.0_real64,5000.0_real64,5000.0_real64, &
      0.0_real64,6500.0_real64,5000.0_real64, &
      0.0_real64,3000.0_real64,5000.0_real64, &
      0.0_real64,2500.0_real64,5000.0_real64, &
      0.0_real64,0.0_real64,5000.0_real64, &
      0.0_real64,0.0_real64,3500.0_real64],[3,6])
    LOGICAL, PARAMETER :: expected_domain(3,6)=RESHAPE([ &
      .TRUE.,.TRUE.,.TRUE., &
      .FALSE.,.TRUE.,.TRUE., &
      .FALSE.,.TRUE.,.TRUE., &
      .FALSE.,.TRUE.,.TRUE., &
      .FALSE.,.FALSE.,.TRUE., &
      .FALSE.,.FALSE.,.TRUE.],[3,6])
    TYPE(cloud_bal_state_type) :: state
    INTEGER :: status,i,k
    REAL(real64) :: overlap,mean_dp
    TYPE(pressure_face_segment), ALLOCATABLE :: segments(:)
    LOGICAL :: ok

    CALL initialize_cloud_bal_state(state,nx,ny,nz,1786885200_int64, &
                                    'pressure-partial-face',status)
    IF (status/=STATUS_OK) ERROR STOP 'six-column initialize'
    state%grid%dx=2000.0_real64
    state%grid%dy=3000.0_real64
    state%pressure%value(:,1,1)=center32(1)
    state%pressure%value(:,1,2)=center32(2)
    state%pressure%value(:,1,3)=center32(3)
    state%pressure%valid=.TRUE.
    state%pressure%quality=0_int32
    state%pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_pressure%value(:,1)=surface32
    state%surface_pressure%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL

    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'six-column configure'

    DO i=1,nx
      DO k=1,nz+1
        CALL close_value(state%grid%pressure_interface(i,1,k), &
                         expected_interface(k,i),'six-column interface')
      END DO
      DO k=1,nz
        CALL close_value(state%grid%cell_dp(i,1,k),expected_dp(k,i), &
                         'six-column cell dp')
        IF (state%above_ground(i,1,k).NEQV.expected_domain(k,i)) THEN
          PRINT *,'FAIL six-column domain',i,k
          ERROR STOP 1
        END IF
      END DO
      DO k=1,nz-1
        CALL close_value(state%grid%level_spacing_dp(i,1,k),5000.0_real64, &
                         'six-column center spacing')
      END DO
    END DO

    ! PSFC=99000 and PSFC=95500 have layer-2 intervals [92500,99000]
    ! and [92500,95500].  Their literal common thickness is 3000 Pa,
    ! whereas the two cell_dp arithmetic mean is 4750 Pa.
    overlap=overlap_dp(state%grid%pressure_interface(2,1,3), &
                       state%grid%pressure_interface(2,1,2), &
                       state%grid%pressure_interface(3,1,3), &
                       state%grid%pressure_interface(3,1,2))
    CALL close_value(overlap,3000.0_real64,'unequal surface extension overlap')
    mean_dp=0.5_real64*(state%grid%cell_dp(2,1,2)+ &
                        state%grid%cell_dp(3,1,2))
    CALL close_value(mean_dp,4750.0_real64,'unequal surface extension mean')
    IF (ABS(overlap-mean_dp)<=analytic_tolerance(mean_dp)) THEN
      ERROR STOP 'overlap unexpectedly equals cell dp mean'
    END IF

    ! The inactive layer-1 interval for the PSFC=99000 column is zero width.
    IF (state%above_ground(2,1,1)) ERROR STOP 'inactive zero-width layer marked active'
    CALL close_value(state%grid%cell_dp(2,1,1),0.0_real64, &
                     'inactive zero-width cell dp')
    overlap=overlap_dp(state%grid%pressure_interface(2,1,2), &
                       state%grid%pressure_interface(2,1,1), &
                       state%grid%pressure_interface(1,1,2), &
                       state%grid%pressure_interface(1,1,1))
    CALL close_value(overlap,0.0_real64,'zero-width inactive overlap')

    ! Actual configured adjacent vertical cells touch at 97500 Pa.
    overlap=overlap_dp(state%grid%pressure_interface(1,1,2), &
                       state%grid%pressure_interface(1,1,1), &
                       state%grid%pressure_interface(1,1,3), &
                       state%grid%pressure_interface(1,1,2))
    CALL close_value(overlap,0.0_real64,'touching interval overlap')

    ! Non-adjacent actual configured cells have a pressure gap.
    overlap=overlap_dp(state%grid%pressure_interface(1,1,2), &
                       state%grid%pressure_interface(1,1,1), &
                       state%grid%pressure_interface(1,1,4), &
                       state%grid%pressure_interface(1,1,3))
    CALL close_value(overlap,0.0_real64,'disjoint interval overlap')

    ! The terrain-cut bottom of column 2 spans TWO levels in column 1.
    ! A same-k face calculation would silently omit the 1500 Pa segment.
    CALL partition_pressure_face(state%grid%pressure_interface(1,1,:), &
      state%grid%pressure_interface(2,1,:),segments,ok)
    IF (.NOT.ok) ERROR STOP 'configured cross-level partition rejected'
    IF (SIZE(segments)/=3) ERROR STOP 'configured cross-level segment count'
    CALL check_segment(segments(1),1,2,1500.0_real64)
    CALL check_segment(segments(2),2,2,5000.0_real64)
    CALL check_segment(segments(3),3,3,5000.0_real64)
    DO i=1,nx-1
      CALL check_dense_partition(state%grid%pressure_interface(i,1,:), &
        state%grid%pressure_interface(i+1,1,:))
    END DO
  END SUBROUTINE test_six_column_geometry

  SUBROUTINE test_thin_center_domain_geometry()
    INTEGER, PARAMETER :: nx=3,ny=1,nz=3
    REAL(real32), PARAMETER :: center32(3)=[95000.0_real32,94999.0_real32, &
                                            94998.0_real32]
    REAL(real32), PARAMETER :: surface32(3)=[95000.0_real32,94999.5_real32, &
                                             94999.0_real32]
    REAL(real64), PARAMETER :: expected_interface(4,3)=RESHAPE([ &
      95000.0_real64,94999.5_real64,94998.5_real64,94997.5_real64, &
      94999.5_real64,94999.5_real64,94998.5_real64,94997.5_real64, &
      94999.0_real64,94999.0_real64,94998.5_real64,94997.5_real64],[4,3])
    REAL(real64), PARAMETER :: expected_dp(3,3)=RESHAPE([ &
      0.5_real64,1.0_real64,1.0_real64, &
      0.0_real64,1.0_real64,1.0_real64, &
      0.0_real64,0.5_real64,1.0_real64],[3,3])
    LOGICAL, PARAMETER :: expected_domain(3,3)=RESHAPE([ &
      .TRUE.,.TRUE.,.TRUE., &
      .FALSE.,.TRUE.,.TRUE., &
      .FALSE.,.TRUE.,.TRUE.],[3,3])
    TYPE(cloud_bal_state_type) :: state
    INTEGER :: status,i,k
    REAL(real64) :: overlap

    CALL initialize_cloud_bal_state(state,nx,ny,nz,1786885200_int64, &
                                    'pressure-thin-center',status)
    IF (status/=STATUS_OK) ERROR STOP 'thin-center initialize'
    state%grid%dx=2000.0_real64
    state%grid%dy=3000.0_real64
    state%pressure%value(:,1,1)=center32(1)
    state%pressure%value(:,1,2)=center32(2)
    state%pressure%value(:,1,3)=center32(3)
    state%pressure%valid=.TRUE.
    state%pressure%quality=0_int32
    state%pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_pressure%value(:,1)=surface32
    state%surface_pressure%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL

    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'thin-center configure'
    DO i=1,nx
      IF (COUNT(state%above_ground(i,1,:))<2) THEN
        ERROR STOP 'thin-center case must retain at least two active centers'
      END IF
      DO k=1,nz+1
        CALL close_value(state%grid%pressure_interface(i,1,k), &
                         expected_interface(k,i),'thin-center interface')
      END DO
      DO k=1,nz
        CALL close_value(state%grid%cell_dp(i,1,k),expected_dp(k,i), &
                         'thin-center cell dp')
        IF (state%above_ground(i,1,k).NEQV.expected_domain(k,i)) THEN
          PRINT *,'FAIL thin-center domain',i,k
          ERROR STOP 1
        END IF
      END DO
      DO k=1,nz-1
        CALL close_value(state%grid%level_spacing_dp(i,1,k),1.0_real64, &
                         'thin-center spacing')
      END DO
    END DO

    ! Thin intervals are also checked through the independent helper, using
    ! the configured interfaces and literal expected intersections.
    overlap=overlap_dp(state%grid%pressure_interface(1,1,3), &
                       state%grid%pressure_interface(1,1,2), &
                       state%grid%pressure_interface(2,1,3), &
                       state%grid%pressure_interface(2,1,2))
    CALL close_value(overlap,1.0_real64,'thin-center full overlap')
    overlap=overlap_dp(state%grid%pressure_interface(2,1,3), &
                       state%grid%pressure_interface(2,1,2), &
                       state%grid%pressure_interface(3,1,3), &
                       state%grid%pressure_interface(3,1,2))
    CALL close_value(overlap,0.5_real64,'thin-center PSFC-cut overlap')
    DO i=1,nx-1
      CALL check_dense_partition(state%grid%pressure_interface(i,1,:), &
        state%grid%pressure_interface(i+1,1,:))
    END DO
  END SUBROUTINE test_thin_center_domain_geometry

  SUBROUTINE test_partition_edges()
    TYPE(pressure_face_segment), ALLOCATABLE :: segments(:)
    REAL(real64) :: bad(3)
    LOGICAL :: ok
    INTEGER :: side,mutation

    CALL partition_pressure_face([10.0_real64,7.0_real64,2.0_real64], &
      [9.0_real64,8.0_real64,5.0_real64,1.0_real64],segments,ok)
    IF (.NOT.ok) ERROR STOP 'unequal grids rejected'
    IF (SIZE(segments)/=4) ERROR STOP 'unequal grids segment count'
    CALL check_segment(segments(1),1,1,1.0_real64)
    CALL check_segment(segments(2),1,2,1.0_real64)
    CALL check_segment(segments(3),2,2,2.0_real64)
    CALL check_segment(segments(4),2,3,3.0_real64)
    CALL check_dense_partition([10.0_real64,7.0_real64,2.0_real64], &
      [9.0_real64,8.0_real64,5.0_real64,1.0_real64])
    CALL check_dense_partition([10.0_real64,10.0_real64,7.0_real64,7.0_real64,2.0_real64], &
      [9.0_real64,8.0_real64,8.0_real64,5.0_real64,1.0_real64])
    CALL check_dense_partition([10.0_real64,8.0_real64], [8.0_real64,2.0_real64])
    CALL check_dense_partition([10.0_real64,8.0_real64], [7.0_real64,2.0_real64])
    CALL check_dense_partition([8.0_real64,8.0_real64], [9.0_real64,2.0_real64])

    ! Check both input sides under -fpe0.  Invalid calls must clear old output.
    DO side=1,2
      DO mutation=1,5
        bad=[10.0_real64,7.0_real64,2.0_real64]
        SELECT CASE(mutation)
        CASE(1); bad(2)=ieee_value(0.0_real64,ieee_quiet_nan)
        CASE(2); bad(2)=ieee_value(0.0_real64,ieee_positive_inf)
        CASE(3); bad(2)=11.0_real64
        CASE(4); bad(3)=0.0_real64
        CASE(5); bad(3)=-1.0_real64
        END SELECT
        IF (side==1) THEN
          CALL partition_pressure_face(bad,[9.0_real64,1.0_real64],segments,ok)
        ELSE
          CALL partition_pressure_face([9.0_real64,1.0_real64],bad,segments,ok)
        END IF
        IF (ok) ERROR STOP 'invalid pressure interfaces accepted'
        IF (.NOT.ALLOCATED(segments)) ERROR STOP 'invalid output must be empty allocated array'
        IF (SIZE(segments)/=0) ERROR STOP 'invalid input retained segments'
      END DO
    END DO
    CALL partition_pressure_face([10.0_real64],[9.0_real64,1.0_real64],segments,ok)
    IF (ok .OR. SIZE(segments)/=0) ERROR STOP 'short left interfaces accepted'
    CALL partition_pressure_face([9.0_real64,1.0_real64],[10.0_real64],segments,ok)
    IF (ok .OR. SIZE(segments)/=0) ERROR STOP 'short right interfaces accepted'
    CALL partition_pressure_face([REAL(real64) ::],[9.0_real64,1.0_real64],segments,ok)
    IF (ok .OR. SIZE(segments)/=0) ERROR STOP 'empty interfaces accepted'
  END SUBROUTINE test_partition_edges

  SUBROUTINE check_segment(segment,left,right,thickness)
    TYPE(pressure_face_segment), INTENT(IN) :: segment
    INTEGER, INTENT(IN) :: left,right
    REAL(real64), INTENT(IN) :: thickness
    IF (segment%left_level/=left .OR. segment%right_level/=right) &
      ERROR STOP 'wrong pressure face connectivity'
    CALL close_value(segment%pressure_thickness,thickness,'segment thickness')
  END SUBROUTINE check_segment

  SUBROUTINE check_dense_partition(left,right)
    REAL(real64), INTENT(IN) :: left(:),right(:)
    TYPE(pressure_face_segment), ALLOCATABLE :: segments(:),reverse(:)
    REAL(real64) :: dense(SIZE(left)-1,SIZE(right)-1),actual(SIZE(left)-1,SIZE(right)-1)
    INTEGER :: i,j,s
    LOGICAL :: ok

    ! Independent O(n*m) reference, not the production two-pointer algorithm.
    DO j=1,SIZE(right)-1; DO i=1,SIZE(left)-1
      dense(i,j)=overlap_dp(left(i+1),left(i),right(j+1),right(j))
    END DO; END DO
    CALL partition_pressure_face(left,right,segments,ok)
    IF (.NOT.ok) ERROR STOP 'valid dense reference rejected'
    IF (SIZE(segments)/=COUNT(dense>0.0_real64)) ERROR STOP 'dense reference segment count'
    actual=0.0_real64
    DO s=1,SIZE(segments)
      i=segments(s)%left_level; j=segments(s)%right_level
      IF (i<1 .OR. i>=SIZE(left) .OR. j<1 .OR. j>=SIZE(right)) ERROR STOP 'invalid segment index'
      IF (actual(i,j)/=0.0_real64) ERROR STOP 'duplicate segment'
      actual(i,j)=segments(s)%pressure_thickness
      IF (actual(i,j)<=0.0_real64) ERROR STOP 'empty face segment emitted'
    END DO
    DO j=1,SIZE(right)-1; DO i=1,SIZE(left)-1
      CALL close_value(actual(i,j),dense(i,j),'dense reference overlap')
    END DO; END DO
    CALL close_value(SUM(actual),overlap_dp(left(SIZE(left)),left(1), &
      right(SIZE(right)),right(1)),'complete common-face pressure measure')
    CALL partition_pressure_face(right,left,reverse,ok)
    IF (.NOT.ok) ERROR STOP 'reversed partition rejected'
    IF (SIZE(reverse)/=SIZE(segments)) ERROR STOP 'reversed partition count'
    DO s=1,SIZE(segments)
      CALL check_segment(reverse(s),segments(s)%right_level, &
        segments(s)%left_level,segments(s)%pressure_thickness)
    END DO
  END SUBROUTINE check_dense_partition

  PURE REAL(real64) FUNCTION overlap_dp(top_left,bottom_left,top_right,bottom_right)
    REAL(real64), INTENT(IN) :: top_left,bottom_left,top_right,bottom_right
    overlap_dp=MAX(0.0_real64,MIN(bottom_left,bottom_right)- &
                   MAX(top_left,top_right))
  END FUNCTION overlap_dp

  PURE REAL(real64) FUNCTION analytic_tolerance(reference)
    REAL(real64), INTENT(IN) :: reference
    analytic_tolerance=1.0e-8_real64+64.0_real64*EPSILON(1.0_real64)* &
                        ABS(reference)
  END FUNCTION analytic_tolerance

  SUBROUTINE close_value(value,reference,label)
    REAL(real64), INTENT(IN) :: value,reference
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.ieee_is_finite(value) .OR. &
        ABS(value-reference)>analytic_tolerance(reference)) THEN
      PRINT *,'FAIL ',TRIM(label),value,reference
      ERROR STOP 1
    END IF
  END SUBROUTINE close_value

END PROGRAM test_pressure_partial_face_oracle
