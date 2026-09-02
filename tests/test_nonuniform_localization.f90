PROGRAM test_nonuniform_localization
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_grid_geometry,ONLY: cumulative_horizontal_distance
  USE cloud_bal_localization,ONLY: build_compact_influence_3d,wendland_c2
  USE cloud_bal_pipeline,ONLY: build_compact_balance_beta
  IMPLICIT NONE

  INTEGER, PARAMETER :: nx=3,ny=1,nz=2
  REAL, PARAMETER :: horizontal_radius=12000.0
  LOGICAL :: source(nx,ny,nz)
  REAL :: pressure(nz),dx(nx,ny),dy(nx,ny),influence(nx,ny,nz),expected,distance32
  REAL(real64) :: distance64
  REAL(real32) :: beta_before(nx,ny,nz)
  TYPE(cloud_bal_state_type) :: state
  INTEGER :: failures,status
  LOGICAL :: distance_ok

  failures=0
  source=.FALSE.
  source(1,1,1)=.TRUE.
  pressure=(/90000.0,80000.0/)
  dy=1000.0

  ! The endpoint approximation sees only 2 km between cells 1 and 3.  The
  ! actual adjacent-center path crosses the 100-km middle cell and is 101 km.
  dx(:,1)=(/1000.0,100000.0,1000.0/)
  CALL cumulative_horizontal_distance(dx,dy,3,1,1,1,distance32,distance_ok)
  CALL check(distance_ok .AND. ABS(distance32-101000.0)<1.0E-3, &
             'real32 geometry contract must return the 101-km path')
  CALL cumulative_horizontal_distance(REAL(dx,real64),REAL(dy,real64), &
                                      3,1,1,1,distance64,distance_ok)
  CALL check(distance_ok .AND. ABS(distance64-101000.0_real64)<1.0E-9_real64, &
             'real64 geometry contract must return the 101-km path')
  CALL build_compact_influence_3d(source,pressure,dx,dy,horizontal_radius, &
                                  20000.0,influence,status)
  CALL check(status==1,'standalone nonuniform localization must succeed')
  CALL check(influence(1,1,1)==1.0,'standalone source weight must be one')
  CALL check(influence(3,1,1)==0.0, &
             '101-km path must be outside 12-km standalone support')

  CALL initialize_pipeline_state(state,status)
  CALL check(status==STATUS_OK,'pipeline fixture initialization must succeed')
  state%grid%dx(:,1)=REAL(dx(:,1),real64)
  CALL build_compact_balance_beta(state,REAL(horizontal_radius,real64), &
                                  20000.0_real64,status)
  CALL check(status==STATUS_OK,'pipeline nonuniform localization must succeed')
  CALL check(state%balance_beta(1,1,1)==1.0_real32, &
             'pipeline source weight must be one')
  CALL check(state%balance_beta(3,1,1)==0.0_real32, &
             '101-km path must be outside 12-km pipeline support')

  ! Uniform grids retain the original index-gap times spacing result.
  dx=1000.0
  CALL build_compact_influence_3d(source,pressure,dx,dy,horizontal_radius, &
                                  20000.0,influence,status)
  expected=wendland_c2(2000.0/horizontal_radius)
  CALL check(ABS(influence(3,1,1)-expected)<1.0E-6, &
             'standalone uniform-grid weight must remain unchanged')
  state%grid%dx=1000.0_real64
  CALL build_compact_balance_beta(state,REAL(horizontal_radius,real64), &
                                  20000.0_real64,status)
  CALL check(ABS(state%balance_beta(3,1,1)-REAL(expected,real32))<1.0E-6_real32, &
             'pipeline uniform-grid weight must match standalone localization')

  ! A finite but enormous radius covers the small domain without overflowing
  ! the real-to-integer search-radius conversion.
  CALL build_compact_influence_3d(source,pressure,dx,dy,HUGE(1.0)/2.0, &
                                  20000.0,influence,status)
  CALL check(status==1 .AND. ALL(influence>=0.0) .AND. ALL(influence<=1.0), &
             'standalone huge finite radius must remain bounded')
  CALL build_compact_balance_beta(state,HUGE(1.0_real64)/2.0_real64, &
                                  20000.0_real64,status)
  CALL check(status==STATUS_OK .AND. ALL(state%balance_beta>=0.0_real32) .AND. &
             ALL(state%balance_beta<=1.0_real32), &
             'pipeline huge finite radius must remain bounded')

  ! Invalid geometry fails without publishing a partial replacement.
  dx(2,1)=0.0
  CALL build_compact_influence_3d(source,pressure,dx,dy,horizontal_radius, &
                                  20000.0,influence,status)
  CALL check(status==0 .AND. MAXVAL(influence)==0.0, &
             'standalone invalid grid must fail with no residual support')
  beta_before=state%balance_beta
  state%grid%dx(2,1)=0.0_real64
  CALL build_compact_balance_beta(state,REAL(horizontal_radius,real64), &
                                  20000.0_real64,status)
  CALL check(status==STATUS_FAILED .AND. ALL(state%balance_beta==beta_before), &
             'pipeline invalid grid must preserve the prior approved support')

  ! The public helper must reject malformed field shapes before indexing them.
  state%grid%dx=1000.0_real64
  beta_before=state%balance_beta
  DEALLOCATE(state%pressure%value)
  CALL build_compact_balance_beta(state,REAL(horizontal_radius,real64), &
                                  20000.0_real64,status)
  CALL check(status==STATUS_FAILED .AND. ALL(state%balance_beta==beta_before), &
             'pipeline malformed pressure shape must fail without mutation')

  IF (failures/=0) THEN
    PRINT *,'Nonuniform localization tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Nonuniform localization tests passed'

CONTAINS

  SUBROUTINE check(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE initialize_pipeline_state(candidate,initialization_status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    INTEGER, INTENT(OUT) :: initialization_status

    CALL initialize_cloud_bal_state(candidate,nx,ny,nz,0_int64, &
                                    'nonuniform-localization',initialization_status)
    IF (initialization_status/=STATUS_OK) RETURN
    candidate%grid%dx=1000.0_real64
    candidate%grid%dy=1000.0_real64
    candidate%pressure%value(:,:,1)=90000.0_real32
    candidate%pressure%value(:,:,2)=80000.0_real32
    candidate%omega%value=0.0_real32
    candidate%omega%valid=.TRUE.
    candidate%omega%quality=0_int32
    candidate%omega%source=SOURCE_BACKGROUND_MODEL
    candidate%omega_target%value(1,1,1)=1.0_real32
    candidate%omega_target%valid(1,1,1)=.TRUE.
    candidate%omega_target%quality(1,1,1)=0_int32
    candidate%omega_target%source(1,1,1)= &
      IOR(SOURCE_DYNAMIC_TARGET,SOURCE_CONVENTIONAL_OBS)
  END SUBROUTINE initialize_pipeline_state

END PROGRAM test_nonuniform_localization
