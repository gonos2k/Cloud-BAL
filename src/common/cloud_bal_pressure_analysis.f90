! Shared pressure-analysis shadow experiment dispatch.
!
! These experiments are explicit research diagnostics.  They are not a KDM6
! phase/rate policy and they never grant new operational authority.
MODULE cloud_bal_pressure_analysis
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID
  USE cloud_bal_balance_operator, ONLY: TARGET_AUTHORITY_OBSERVATIONAL, &
    TARGET_AUTHORITY_MODEL_DYNAMICS,BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
  USE cloud_bal_pipeline
  IMPLICIT NONE
  PRIVATE

  PUBLIC :: run_pressure_analysis_shadow

CONTAINS

  SUBROUTINE run_pressure_analysis_shadow(input,candidate,operational,result, &
                                          config,experiment,status,requested_surface_pressure,single_pass, &
                                          pressure_transition_seed)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate,operational
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(OUT) :: config
    CHARACTER(LEN=*), INTENT(IN) :: experiment
    INTEGER, INTENT(OUT) :: status
    REAL(real64), INTENT(IN), OPTIONAL :: requested_surface_pressure(:,:)
    LOGICAL, INTENT(IN), OPTIONAL :: single_pass
    TYPE(cloud_bal_state_type), INTENT(IN), OPTIONAL :: pressure_transition_seed
    LOGICAL, ALLOCATABLE :: thermo_active(:,:,:)
    INTEGER, ALLOCATABLE :: thermo_surface(:,:,:)
    LOGICAL, ALLOCATABLE :: geopotential_support(:,:,:)
    INTEGER, ALLOCATABLE :: geopotential_reference(:,:)
    INTEGER :: i,j

    config=cloud_bal_pipeline_config()
    config%requested_mode=MODE_SHADOW
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    config%balance%maximum_iterations=800
    config%balance%target_authority=TARGET_AUTHORITY_OBSERVATIONAL

    candidate=input
    operational=input
    result=cloud_bal_pipeline_result()
    result%requested_mode=config%requested_mode
    result%status=STATUS_FAILED
    result%reason_code=REASON_AUTHORITY
    status=STATUS_FAILED

    IF (PRESENT(pressure_transition_seed) .AND. TRIM(experiment)/='OFF') THEN
      IF (.NOT.PRESENT(requested_surface_pressure)) RETURN
    END IF
    IF (PRESENT(requested_surface_pressure) .AND. TRIM(experiment)/='OFF') THEN
      IF (TRIM(experiment)/='LIQUID_RADAR_RH1_SURFACE_PHI') RETURN
      IF (.NOT.PRESENT(single_pass)) RETURN
      IF (.NOT.single_pass) RETURN
    END IF

    SELECT CASE (TRIM(experiment))
    CASE ('OFF')
      ! Same canonical background and writer as SHADOW, without analysis changes.
      config%requested_mode=MODE_OFF
      CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)

    CASE ('HYDRO')
      CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)

    CASE ('MODEL_DYNAMICS')
      ! The caller supplies the paired physical response and its covered halo.
      ! This preserves baseline boundary fluxes; it grants no observational
      ! target authority or absolute physical-continuity certification.
      config%balance%target_authority=TARGET_AUTHORITY_MODEL_DYNAMICS
      config%balance%boundary_increment_contract=BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
      CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)

    CASE ('LIQUID_RADAR_RH1','LIQUID_RADAR_RH1_PHI','LIQUID_RADAR_RH1_SURFACE_PHI')
      ! Liquid-only saturation is an explicit research ablation, not KDM6.
      ! The observed radar footprint is immutable and supplies no wind target.
      config%maximum_outer_iterations=16
      IF (PRESENT(single_pass)) THEN
        IF (single_pass) config%maximum_outer_iterations=1
      END IF
      ALLOCATE(thermo_active(input%grid%nx,input%grid%ny,input%grid%nz), &
               thermo_surface(input%grid%nx,input%grid%ny,input%grid%nz))
      thermo_active=input%above_ground .AND. cell_is_usable( &
        input%radar_reflectivity%valid,input%radar_reflectivity%quality, &
        input%radar_reflectivity%source)
      thermo_surface=SATURATION_LIQUID
      WRITE(*,'(A)') 'thermo_experiment=LIQUID_RADAR_RH1_NOT_KDM6'
      WRITE(*,'(A,I0)') 'thermo_selected_cells=',COUNT(thermo_active)

      IF (TRIM(experiment)/='LIQUID_RADAR_RH1') THEN
        ALLOCATE(geopotential_support(input%grid%nx,input%grid%ny,input%grid%nz), &
                 geopotential_reference(input%grid%nx,input%grid%ny))
        geopotential_support=.FALSE.
        geopotential_reference=0
        DO j=1,input%grid%ny
          DO i=1,input%grid%nx
            IF (.NOT.ANY(thermo_active(i,j,:))) CYCLE
            geopotential_support(i,j,:)=input%above_ground(i,j,:)
            IF (TRIM(experiment)=='LIQUID_RADAR_RH1_PHI') &
              geopotential_reference(i,j)=FINDLOC(input%above_ground(i,j,:),.TRUE.,DIM=1)
          END DO
        END DO
        IF (TRIM(experiment)=='LIQUID_RADAR_RH1_PHI') THEN
          WRITE(*,'(A)') 'geopotential_experiment=RADAR_COLUMNS_FIXED_LOWEST_ANALYSIS_CENTER'
        ELSE
          WRITE(*,'(A)') 'geopotential_experiment=RADAR_COLUMNS_FIXED_SURFACE'
        END IF
        CALL run_cloud_bal_pipeline(input,candidate,operational,result,config, &
          thermo_active,thermo_surface,1.0_real64,geopotential_support, &
          geopotential_reference,requested_surface_pressure,pressure_transition_seed)
      ELSE
        CALL run_cloud_bal_pipeline(input,candidate,operational,result,config, &
          thermo_active,thermo_surface,1.0_real64)
      END IF

    CASE DEFAULT
      ! Reject unknown experiments without entering the science pipeline.
      RETURN
    END SELECT

    IF (result%status==STATUS_OK .AND. &
        canonical_states_equal(input,operational)) status=STATUS_OK
  END SUBROUTINE run_pressure_analysis_shadow

END MODULE cloud_bal_pressure_analysis
