PROGRAM test_balance_omega_authority
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_middle_target_keeps_other_omega(failures)
  CALL test_partial_authority_operator_identity(failures)
  CALL test_alternating_target_rejects(failures)
  CALL test_near_alternating_target_rejects(failures)
  CALL test_malformed_storage_rejects(failures)
  IF (failures/=0) THEN
    PRINT *,'Balance omega-authority tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Balance omega-authority tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, PARAMETER :: nx=6,ny=5,nz=4
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    INTEGER :: i,j,k,status

    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time, &
                                    'omega-authority-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64
    state%grid%dy=2000.0_real64
    state%grid%dp=10000.0_real64
    state%grid%pressure_mass_measure=SPREAD(state%grid%dx*state%grid%dy,3,nz)* &
      state%grid%dp/9.80665_real64
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%pressure%value(i,j,k)=REAL(95000-15000*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=0.0_real32
      state%v%value(i,j,k)=0.0_real32
      state%omega%value(i,j,k)=0.0_real32
      state%geopotential%value(i,j,k)=1000.0_real32
    END DO; END DO; END DO
    CALL mark_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%u,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%v,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    state%omega_target%value=0.0_real32
    state%omega_target%valid=.FALSE.
    state%omega_target%quality=0_int32
    state%omega_target%source=0_int32
    state%balance_beta=1.0_real32
    state%latitude%value=36.0_real32
    state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32
    state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32
    state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BACKGROUND_MODEL
    state%omega_bottom_boundary%source=SOURCE_BACKGROUND_MODEL
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'mass initialization failed'
  END SUBROUTINE make_state

  SUBROUTINE mark_valid(field,source_bit)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source_bit
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source_bit
  END SUBROUTINE mark_valid

  SUBROUTINE authorize_target(state,i,j,k,value)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real32), INTENT(IN) :: value
    state%omega_target%value(i,j,k)=value
    state%omega_target%valid(i,j,k)=.TRUE.
    state%omega_target%quality(i,j,k)=0_int32
    state%omega_target%source(i,j,k)=IOR(SOURCE_ANALYZED_WIND, &
                                        SOURCE_DYNAMIC_TARGET)
  END SUBROUTINE authorize_target

  SUBROUTINE permissive_config(cfg)
    TYPE(balance_operator_config), INTENT(OUT) :: cfg
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64
  END SUBROUTINE permissive_config

  SUBROUTINE test_middle_target_keeps_other_omega(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER :: i,j,k
    LOGICAL :: other_cells_unchanged

    CALL make_state(input)
    CALL authorize_target(input,3,3,3,0.08_real32)
    CALL permissive_config(cfg)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               result%numerical%solver_iterations>0, &
      'middle-level target must produce an accepted projection',failures)
    CALL check(TRANSFER(output%omega%value(3,3,3),0_int32)/= &
               TRANSFER(input%omega%value(3,3,3),0_int32), &
      'authorized middle-level omega must retain a projected response',failures)
    other_cells_unchanged=.TRUE.
    DO k=1,input%grid%nz; DO j=1,input%grid%ny; DO i=1,input%grid%nx
      IF (i==3 .AND. j==3 .AND. k==3) CYCLE
      other_cells_unchanged=other_cells_unchanged .AND. &
        TRANSFER(output%omega%value(i,j,k),0_int32)== &
        TRANSFER(input%omega%value(i,j,k),0_int32) .AND. &
        (output%omega%valid(i,j,k).EQV.input%omega%valid(i,j,k)) .AND. &
        output%omega%quality(i,j,k)==input%omega%quality(i,j,k) .AND. &
        output%omega%source(i,j,k)==input%omega%source(i,j,k)
    END DO; END DO; END DO
    other_cells_unchanged=other_cells_unchanged .AND. &
      output%omega%valid_time==input%omega%valid_time .AND. &
      output%omega%unit==input%omega%unit
    CALL check(other_cells_unchanged, &
      'omega field must be unchanged without explicit target authority',failures)
  END SUBROUTINE test_middle_target_keeps_other_omega

  SUBROUTINE test_partial_authority_operator_identity(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_config) :: cfg
    REAL(real64), ALLOCATABLE :: lambda(:,:,:),du(:,:,:),dv(:,:,:),domega(:,:,:)
    REAL(real64), ALLOCATABLE :: divergence(:,:,:),normal(:,:,:)
    REAL(real64) :: error,scale,quadratic
    INTEGER :: i,j,k,status,reason

    CALL make_state(input)
    CALL authorize_target(input,3,3,3,0.08_real32)
    CALL permissive_config(cfg)
    CALL build_balance_operator(input,cfg,op,status,reason)
    ALLOCATE(lambda(6,5,4),du(6,5,4),dv(6,5,4),domega(6,5,4), &
             divergence(6,5,4),normal(6,5,4))
    DO k=1,4; DO j=1,5; DO i=1,6
      lambda(i,j,k)=SIN(0.17_real64*i+0.23_real64*j-0.31_real64*k)
    END DO; END DO; END DO
    CALL apply_balance_correction(op,lambda,du,dv,domega,status)
    CALL check(status==STATUS_OK .AND. &
               ALL(domega==0.0_real64 .OR. op%omega_authorized), &
      'partial-authority correction must not create unauthorized omega',failures)
    CALL apply_continuity_operator(op,du,dv,domega,divergence,status)
    CALL apply_normal_operator(op,lambda,normal,status)
    scale=MAX(MAXVAL(ABS(normal),MASK=op%cell_active),1.0e-30_real64)
    error=MAXVAL(ABS(normal+divergence),MASK=op%cell_active)/scale
    quadratic=SUM(op%volume*lambda*normal,MASK=op%cell_active)
    CALL check(status==STATUS_OK .AND. error<5.0e-13_real64, &
      'partial-authority L must equal minus divergence of correction',failures)
    CALL check(quadratic>=-1.0e-12_real64*MAX(1.0_real64,ABS(quadratic)), &
      'partial-authority normal operator must remain positive semidefinite',failures)
  END SUBROUTINE test_partial_authority_operator_identity

  SUBROUTINE test_alternating_target_rejects(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER :: k

    CALL make_state(input)
    DO k=1,input%grid%nz
      CALL authorize_target(input,3,3,k, &
        MERGE(0.08_real32,-0.08_real32,MOD(k,2)==1))
    END DO
    CALL permissive_config(cfg)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. &
               result%reason_code==REASON_GATE .AND. &
               result%numerical%solver_iterations==0, &
      'vertically unobservable target must fail closed before solve',failures)
    CALL check(same_field(output%u,input%u) .AND. &
               same_field(output%v,input%v) .AND. &
               same_field(output%omega,input%omega) .AND. &
               same_field(output%omega_target,input%omega_target), &
      'unobservable-target rejection must rollback dynamic fields exactly',failures)
  END SUBROUTINE test_alternating_target_rejects

  SUBROUTINE test_near_alternating_target_rejects(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_state(input)
    CALL authorize_target(input,3,3,1, 0.080_real32)
    CALL authorize_target(input,3,3,2,-0.079_real32)
    CALL authorize_target(input,3,3,3, 0.080_real32)
    CALL authorize_target(input,3,3,4,-0.079_real32)
    CALL permissive_config(cfg)
    cfg%minimum_target_response_ratio=0.05_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. &
               result%reason_code==REASON_GATE .AND. &
               result%numerical%solver_iterations==0, &
      'null-dominated near-alternating target must fail closed',failures)
    CALL check(same_field(output%omega,input%omega), &
      'near-null rejection must rollback omega field exactly',failures)
  END SUBROUTINE test_near_alternating_target_rejects

  SUBROUTINE test_malformed_storage_rejects(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_config) :: cfg
    INTEGER :: status,reason

    CALL make_state(input)
    DEALLOCATE(input%omega_target%source)
    CALL permissive_config(cfg)
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
      'malformed target metadata storage must fail closed',failures)
    CALL make_state(input)
    DEALLOCATE(input%u%quality)
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
      'malformed core-field metadata storage must fail closed',failures)
  END SUBROUTINE test_malformed_storage_rejects

  LOGICAL FUNCTION same_field(left,right)
    TYPE(field3d), INTENT(IN) :: left,right
    same_field=ALL(TRANSFER(left%value,[0_int32],SIZE(left%value))== &
                   TRANSFER(right%value,[0_int32],SIZE(right%value))) .AND. &
      ALL(left%valid .EQV. right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_field

END PROGRAM test_balance_omega_authority
