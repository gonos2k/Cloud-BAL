! Single authority boundary for the canonical Cloud-BAL pipeline.
MODULE cloud_bal_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic,ONLY: ieee_is_finite
  USE cloud_bal_state
  USE cloud_bal_column_physics
  USE cloud_bal_balance_operator
  USE cloud_bal_grid_geometry,ONLY: bounded_grid_radius,cumulative_horizontal_distance
  IMPLICIT NONE
  PRIVATE

  TYPE, PUBLIC :: cloud_bal_pipeline_config
    INTEGER :: requested_mode=MODE_OFF
    REAL(real64) :: horizontal_support_radius_m=12000.0_real64
    REAL(real64) :: pressure_support_radius_pa=30000.0_real64
    TYPE(column_physics_config) :: column
    TYPE(balance_operator_config) :: balance
  END TYPE cloud_bal_pipeline_config

  TYPE, PUBLIC :: cloud_bal_pipeline_result
    INTEGER :: status=STATUS_FAILED
    INTEGER :: reason_code=REASON_NONE
    INTEGER :: requested_mode=MODE_OFF
    TYPE(stage_result) :: column
    TYPE(stage_result) :: balance
    TYPE(stage_result) :: overall
  END TYPE cloud_bal_pipeline_result

  PUBLIC :: run_cloud_bal_pipeline
  PUBLIC :: build_compact_balance_beta

CONTAINS

  SUBROUTINE run_cloud_bal_pipeline(state_in,candidate_out,operational_out, &
                                    result,config)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate_out,operational_out
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    TYPE(cloud_bal_state_type) :: column_candidate,balance_candidate
    INTEGER :: nx,ny,nz,localization_status

    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    candidate_out=state_in; operational_out=state_in
    result%requested_mode=config%requested_mode
    CALL initialize_stage_result(result%column,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(result%balance,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(result%overall,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_FAILED,REASON_AUTHORITY)

    IF (.NOT.pipeline_mode_valid(config%requested_mode)) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
      RETURN
    END IF

    IF (config%requested_mode==MODE_OFF) THEN
      CALL initialize_stage_result(result%overall,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                   STATUS_OK,REASON_NONE)
      result%status=STATUS_OK; result%reason_code=REASON_NONE
      RETURN
    END IF

    CALL derive_column_physics(state_in,column_candidate,result%column, &
      config%column)
    IF (result%column%status/=STATUS_OK) THEN
      result%column%changed=.FALSE.
      result%status=result%column%status
      result%reason_code=result%column%reason_code
      result%overall=result%column
      RETURN
    END IF
    candidate_out=column_candidate

    CALL build_compact_balance_beta(column_candidate,config%horizontal_support_radius_m, &
                                    config%pressure_support_radius_pa,localization_status)
    IF (localization_status/=STATUS_OK) THEN
      candidate_out=state_in; operational_out=state_in
      result%column%changed=.FALSE.
      result%balance%changed=.FALSE.
      result%status=STATUS_FAILED; result%reason_code=REASON_RANGE
      CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_RANGE)
      RETURN
    END IF

    CALL apply_localized_balance(column_candidate,balance_candidate, &
                                 result%balance,config%balance)
    IF (result%balance%status/=STATUS_OK) THEN
      candidate_out=state_in; operational_out=state_in
      result%column%changed=.FALSE.
      result%balance%changed=.FALSE.
      result%status=result%balance%status
      result%reason_code=result%balance%reason_code
      result%overall=result%balance
      result%overall%changed=.FALSE.
      RETURN
    END IF
    candidate_out=balance_candidate
    result%overall=result%balance
    result%overall%changed=result%column%changed .OR. result%balance%changed
    result%status=STATUS_OK; result%reason_code=REASON_NONE

    operational_out=state_in
  END SUBROUTINE run_cloud_bal_pipeline

  SUBROUTINE build_compact_balance_beta(state,horizontal_radius,pressure_radius,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real64), INTENT(IN) :: horizontal_radius,pressure_radius
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,is,js,ks,nx,ny,nz,iradius,jradius
    REAL(real64) :: minimum_dx,minimum_dy,hdistance,pdistance,radius,kernel
    LOGICAL, ALLOCATABLE :: source(:,:,:)
    REAL(real32), ALLOCATABLE :: beta_work(:,:,:)
    LOGICAL :: distance_ok,radius_ok

    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(horizontal_radius) .OR. horizontal_radius<=0.0_real64 .OR. &
        .NOT.ieee_is_finite(pressure_radius) .OR. pressure_radius<=0.0_real64) RETURN
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (.NOT.localization_inputs_valid(state,nx,ny,nz)) RETURN
    IF (ANY(.NOT.ieee_is_finite(state%pressure%value)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64)) RETURN
    ALLOCATE(source(nx,ny,nz),beta_work(nx,ny,nz))
    beta_work=0.0_real32
    ! Only an explicit dynamic proposal grants wind-adjustment authority.
    ! Cloud and hydrometeor presence remain provenance, never solver seeds.
    source=state%above_ground .AND. &
           dynamic_target_is_resolved(state%omega_target%value,state%omega%value, &
                                      state%omega_target%valid, &
                                      state%omega_target%quality, &
                                      state%omega_target%source) .AND. &
           cell_is_usable(state%omega%valid,state%omega%quality,state%omega%source)
    IF (.NOT.ANY(source)) THEN
      state%balance_beta=beta_work
      status=STATUS_OK
      RETURN
    END IF
    minimum_dx=MINVAL(state%grid%dx); minimum_dy=MINVAL(state%grid%dy)
    CALL bounded_grid_radius(horizontal_radius,minimum_dx,nx-1,iradius,radius_ok)
    IF (.NOT.radius_ok) RETURN
    CALL bounded_grid_radius(horizontal_radius,minimum_dy,ny-1,jradius,radius_ok)
    IF (.NOT.radius_ok) RETURN
    DO ks=1,nz; DO js=1,ny; DO is=1,nx
      IF (.NOT.source(is,js,ks)) CYCLE
      DO k=1,nz
        DO j=MAX(1,js-jradius),MIN(ny,js+jradius)
          DO i=MAX(1,is-iradius),MIN(nx,is+iradius)
            IF (.NOT.state%above_ground(i,j,k)) CYCLE
            pdistance=ABS(REAL(state%pressure%value(is,js,ks),real64)- &
                          REAL(state%pressure%value(i,j,k),real64))
            IF (pdistance>=pressure_radius) CYCLE
            CALL cumulative_horizontal_distance(state%grid%dx,state%grid%dy, &
                                                i,j,is,js,hdistance,distance_ok)
            IF (.NOT.distance_ok) RETURN
            radius=SQRT((hdistance/horizontal_radius)**2+ &
                        (pdistance/pressure_radius)**2)
            IF (radius>=1.0_real64) CYCLE
            kernel=(1.0_real64-radius)**4*(1.0_real64+4.0_real64*radius)
            beta_work(i,j,k)=MAX(beta_work(i,j,k),REAL(kernel,real32))
          END DO
        END DO
      END DO
    END DO; END DO; END DO
    WHERE(source) beta_work=1.0_real32
    IF (ANY(.NOT.ieee_is_finite(beta_work)) .OR. &
        ANY(beta_work<0.0_real32) .OR. ANY(beta_work>1.0_real32)) RETURN
    state%balance_beta=beta_work
    status=STATUS_OK
  END SUBROUTINE build_compact_balance_beta

  LOGICAL FUNCTION localization_inputs_valid(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: shape2(2),shape3(3)

    localization_inputs_valid=.FALSE.
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    shape2=(/nx,ny/); shape3=(/nx,ny,nz/)
    IF (.NOT.ALLOCATED(state%grid%dx) .OR. .NOT.ALLOCATED(state%grid%dy) .OR. &
        .NOT.ALLOCATED(state%above_ground) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%grid%dx)/=shape2) .OR. &
        ANY(SHAPE(state%grid%dy)/=shape2) .OR. &
        ANY(SHAPE(state%above_ground)/=shape3) .OR. &
        ANY(SHAPE(state%balance_beta)/=shape3)) RETURN
    IF (.NOT.field_arrays_match(state%pressure,shape3) .OR. &
        .NOT.field_arrays_match(state%omega,shape3) .OR. &
        .NOT.field_arrays_match(state%omega_target,shape3)) RETURN
    localization_inputs_valid=.TRUE.
  END FUNCTION localization_inputs_valid

  LOGICAL FUNCTION field_arrays_match(field,shape3)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: shape3(3)

    field_arrays_match=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=shape3) .OR. ANY(SHAPE(field%valid)/=shape3) .OR. &
        ANY(SHAPE(field%quality)/=shape3) .OR. ANY(SHAPE(field%source)/=shape3)) RETURN
    field_arrays_match=.TRUE.
  END FUNCTION field_arrays_match

END MODULE cloud_bal_pipeline
