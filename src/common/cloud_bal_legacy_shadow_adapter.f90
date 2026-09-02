! Fail-closed adapter for a future legacy pre-QBAL caller.
!
! This module is deliberately not linked into the operational KLAPS tree.  It
! owns only legacy conventions (units, masks, and vertical order), calls the
! canonical pipeline in SHADOW mode, and never returns an operational field.
MODULE cloud_bal_legacy_shadow_adapter
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: column_physics_config
  USE cloud_bal_balance_operator, ONLY: balance_operator_config
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config, &
    cloud_bal_pipeline_result,run_cloud_bal_pipeline
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: LEGACY_BOTTOM_TO_TOP=1
  INTEGER, PARAMETER, PUBLIC :: LEGACY_TOP_TO_BOTTOM=2
  INTEGER, PARAMETER, PUBLIC :: LEGACY_WIND_GRID_RELATIVE=1
  INTEGER, PARAMETER :: UNIT_TEMPERATURE=1,UNIT_SPECIFIC_HUMIDITY=2
  INTEGER, PARAMETER :: UNIT_WIND=3,UNIT_OMEGA=4,UNIT_HEIGHT=5
  INTEGER, PARAMETER :: UNIT_FRACTION=6,UNIT_DBZ=7,UNIT_LATITUDE=8

  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_PRESSURE=ISHFT(1_int32,0)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_GRID_TERRAIN=ISHFT(1_int32,1)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_BACKGROUND_3D=ISHFT(1_int32,2)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_BACKGROUND_SURFACE=ISHFT(1_int32,3)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_ANALYSIS_THERMO=ISHFT(1_int32,4)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_ANALYSIS_HUMIDITY=ISHFT(1_int32,5)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_ANALYSIS_WIND=ISHFT(1_int32,6)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_CLOUD_FORCING=ISHFT(1_int32,7)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_ANALYSIS_SURFACE=ISHFT(1_int32,8)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_RUNTIME_CONTROL=ISHFT(1_int32,9)
  INTEGER(int32), PARAMETER, PUBLIC :: CLOSURE_REQUIRED_BITS= &
    CLOSURE_PRESSURE+CLOSURE_GRID_TERRAIN+CLOSURE_BACKGROUND_3D+ &
    CLOSURE_BACKGROUND_SURFACE+CLOSURE_ANALYSIS_THERMO+ &
    CLOSURE_ANALYSIS_HUMIDITY+CLOSURE_ANALYSIS_WIND+ &
    CLOSURE_CLOUD_FORCING+CLOSURE_ANALYSIS_SURFACE+ &
    CLOSURE_RUNTIME_CONTROL

  TYPE, PUBLIC :: legacy_pre_qbal_arrays
    INTEGER(int64) :: analysis_time=0_int64
    CHARACTER(LEN=64) :: grid_id=''
    ! Supplied only after the upstream manifest verifier has bound the ten
    ! direct QBAL roles to one immutable generation; this array adapter opens
    ! no files and cannot create that attestation itself.
    CHARACTER(LEN=64) :: closure_manifest_sha256=''
    INTEGER(int32) :: closure_bits=0_int32
    INTEGER :: vertical_order=0
    INTEGER :: wind_coordinate=0
    CHARACTER(LEN=16) :: grid_spacing_unit=''
    ! These declarations cover the optional fraction/type pair and the
    ! reflectivity/phase pair.  LCO cloud_omega remains required separately.
    LOGICAL :: cloud_analysis_declared=.FALSE.
    LOGICAL :: radar_analysis_declared=.FALSE.
    REAL(real64), ALLOCATABLE :: dx(:,:),dy(:,:)
    LOGICAL, ALLOCATABLE :: above_ground(:,:,:)
    TYPE(field3d) :: pressure
    TYPE(field3d) :: temperature
    TYPE(field3d) :: specific_humidity
    TYPE(field3d) :: u,v,omega
    TYPE(field3d) :: geopotential_height
    TYPE(field3d) :: cloud_omega
    TYPE(field3d) :: cloud_fraction
    TYPE(integer_field3d) :: cloud_type
    TYPE(field3d) :: radar_reflectivity
    TYPE(integer_field3d) :: precipitation_phase
    TYPE(field2d) :: surface_pressure
    TYPE(field2d) :: latitude
  END TYPE legacy_pre_qbal_arrays

  TYPE, PUBLIC :: legacy_shadow_config
    REAL(real64) :: horizontal_support_radius_m=12000.0_real64
    REAL(real64) :: pressure_support_radius_pa=30000.0_real64
    TYPE(column_physics_config) :: column
    TYPE(balance_operator_config) :: balance
  END TYPE legacy_shadow_config

  INTERFACE field_shape_ok
    MODULE PROCEDURE real3_shape_ok,integer3_shape_ok,real2_shape_ok
  END INTERFACE field_shape_ok

  INTERFACE field_metadata_ok
    MODULE PROCEDURE real3_metadata_ok,integer3_metadata_ok,real2_metadata_ok
  END INTERFACE field_metadata_ok

  INTERFACE field_absent
    MODULE PROCEDURE real3_absent,integer3_absent
  END INTERFACE field_absent

  PUBLIC :: run_legacy_pre_qbal_shadow

CONTAINS

  SUBROUTINE run_legacy_pre_qbal_shadow(legacy,candidate,result,config)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: result
    TYPE(legacy_shadow_config), INTENT(IN), OPTIONAL :: config
    TYPE(cloud_bal_state_type) :: normalized,operational
    TYPE(cloud_bal_pipeline_config) :: pipeline_config
    TYPE(legacy_shadow_config) :: adapter_config
    INTEGER :: status,reason,nx,ny,nz

    CALL legacy_dimensions(legacy,nx,ny,nz)
    CALL initialize_rejection(result,nx,ny,nz,REASON_METADATA)
    IF (.NOT.direct_closure_valid(legacy)) THEN
      result%reason_code=REASON_REQUIRED_COVERAGE
      result%overall%reason_code=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (.NOT.legacy_shapes_valid(legacy,nx,ny,nz)) THEN
      result%reason_code=REASON_SHAPE
      result%overall%reason_code=REASON_SHAPE
      RETURN
    END IF
    IF (.NOT.legacy_metadata_valid(legacy)) RETURN
    IF (.NOT.legacy_values_in_range(legacy)) THEN
      result%reason_code=REASON_RANGE
      result%overall%reason_code=REASON_RANGE
      RETURN
    END IF
    IF (.NOT.optional_observations_unambiguous(legacy)) THEN
      result%reason_code=REASON_RADAR_CONTRACT
      result%overall%reason_code=REASON_RADAR_CONTRACT
      RETURN
    END IF

    CALL normalize_legacy_state(legacy,normalized,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL initialize_rejection(result,nx,ny,nz,reason)
      RETURN
    END IF

    IF (PRESENT(config)) adapter_config=config
    pipeline_config%requested_mode=MODE_SHADOW
    pipeline_config%horizontal_support_radius_m= &
      adapter_config%horizontal_support_radius_m
    pipeline_config%pressure_support_radius_pa= &
      adapter_config%pressure_support_radius_pa
    pipeline_config%column=adapter_config%column
    pipeline_config%balance=adapter_config%balance
    CALL run_cloud_bal_pipeline(normalized,candidate,operational,result,pipeline_config)

    ! No operational state crosses this adapter boundary.  A non-OK pipeline
    ! result is nevertheless required to expose the normalized input, never a
    ! partially modified work state, as its diagnostic candidate.
    IF (result%status/=STATUS_OK) candidate=normalized
  END SUBROUTINE run_legacy_pre_qbal_shadow

  SUBROUTINE normalize_legacy_state(legacy,state,status,reason)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz,i,j,k,initialization_status
    LOGICAL, ALLOCATABLE :: declared_domain(:,:,:)
    REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
    REAL(real64) :: pressure_scale,surface_pressure_scale,grid_scale

    CALL legacy_dimensions(legacy,nx,ny,nz)
    status=STATUS_FAILED; reason=REASON_METADATA
    CALL initialize_cloud_bal_state(state,nx,ny,nz,legacy%analysis_time, &
                                    legacy%grid_id,initialization_status)
    IF (initialization_status/=STATUS_OK) THEN
      reason=REASON_SHAPE
      RETURN
    END IF

    pressure_scale=pressure_unit_scale(legacy%pressure%unit)
    surface_pressure_scale=pressure_unit_scale(legacy%surface_pressure%unit)
    grid_scale=distance_unit_scale(legacy%grid_spacing_unit)
    IF (pressure_scale<=0.0_real64 .OR. surface_pressure_scale<=0.0_real64 .OR. &
        grid_scale<=0.0_real64) RETURN

    state%grid%dx=grid_scale*legacy%dx; state%grid%dy=grid_scale*legacy%dy
    CALL copy_real3(legacy%pressure,state%pressure,legacy%vertical_order, &
                    pressure_scale)
    ! Pressure levels are coordinates.  A below-ground field mask must not
    ! remove the coordinate needed to construct the PSFC-clipped domain.
    state%pressure%valid=.TRUE.
    state%pressure%quality=0_int32
    state%pressure%source=SOURCE_BACKGROUND_MODEL
    CALL copy_real2(legacy%surface_pressure,state%surface_pressure, &
                    surface_pressure_scale)
    ALLOCATE(declared_domain(nx,ny,nz))
    CALL copy_domain(legacy%above_ground,declared_domain,legacy%vertical_order)
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK .OR. ANY(state%above_ground.NEQV.declared_domain)) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    CALL copy_real3(legacy%temperature,state%temperature,legacy%vertical_order, &
                    1.0_real64,state%above_ground)
    CALL copy_specific_humidity(legacy%specific_humidity,state%vapor, &
                                legacy%vertical_order,state%above_ground,status)
    IF (status/=STATUS_OK) THEN; reason=REASON_RANGE; RETURN; END IF
    CALL copy_real3(legacy%u,state%u,legacy%vertical_order,1.0_real64, &
                    state%above_ground)
    CALL copy_real3(legacy%v,state%v,legacy%vertical_order,1.0_real64, &
                    state%above_ground)
    CALL copy_real3(legacy%omega,state%omega,legacy%vertical_order,1.0_real64, &
                    state%above_ground)
    CALL copy_real3(legacy%geopotential_height,state%geopotential, &
                    legacy%vertical_order,GRAVITY,state%above_ground)
    CALL copy_real3(legacy%cloud_omega,state%omega_target,legacy%vertical_order, &
                    1.0_real64,state%above_ground)
    CALL copy_real3(legacy%cloud_fraction,state%cloud_fraction, &
                    legacy%vertical_order,1.0_real64,state%above_ground)
    CALL copy_integer3(legacy%cloud_type,state%cloud_type, &
                       legacy%vertical_order,state%above_ground)
    CALL copy_real3(legacy%radar_reflectivity,state%radar_reflectivity, &
                    legacy%vertical_order,1.0_real64,state%above_ground)
    CALL copy_integer3(legacy%precipitation_phase,state%precipitation_phase, &
                       legacy%vertical_order,state%above_ground)
    CALL copy_real2(legacy%latitude,state%latitude,1.0_real64)

    state%omega_top_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    state%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    state%omega_top_boundary%value=state%omega%value(:,:,nz)
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_bottom_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    state%omega_bottom_boundary%source=SOURCE_ANALYZED_WIND
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          IF (state%above_ground(i,j,k) .AND. &
              .NOT.ANY(state%above_ground(i,j,1:k-1))) &
            state%omega_bottom_boundary%value(i,j)=state%omega%value(i,j,k)
        END DO
      END DO
    END DO

    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) THEN; reason=REASON_METADATA; RETURN; END IF
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
  END SUBROUTINE normalize_legacy_state

  SUBROUTINE initialize_rejection(result,nx,ny,nz,reason)
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: result
    INTEGER, INTENT(IN) :: nx,ny,nz,reason
    CALL initialize_stage_result(result%column,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_FAILED,reason)
    CALL initialize_stage_result(result%balance,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_FAILED,reason)
    CALL initialize_stage_result(result%overall,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_FAILED,reason)
    result%status=STATUS_FAILED
    result%reason_code=reason
    result%requested_mode=MODE_SHADOW
  END SUBROUTINE initialize_rejection

  PURE SUBROUTINE legacy_dimensions(legacy,nx,ny,nz)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    INTEGER, INTENT(OUT) :: nx,ny,nz
    nx=0; ny=0; nz=0
    IF (ALLOCATED(legacy%dx)) THEN
      nx=SIZE(legacy%dx,1)
      ny=SIZE(legacy%dx,2)
    END IF
    IF (ALLOCATED(legacy%above_ground)) nz=SIZE(legacy%above_ground,3)
  END SUBROUTINE legacy_dimensions

  PURE LOGICAL FUNCTION direct_closure_valid(legacy)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    direct_closure_valid=legacy%analysis_time>0_int64 .AND. &
      LEN_TRIM(legacy%grid_id)>0 .AND. &
      IAND(legacy%closure_bits,CLOSURE_REQUIRED_BITS)==CLOSURE_REQUIRED_BITS .AND. &
      IAND(legacy%closure_bits,NOT(CLOSURE_REQUIRED_BITS))==0_int32 .AND. &
      sha256_text_valid(legacy%closure_manifest_sha256)
  END FUNCTION direct_closure_valid

  PURE LOGICAL FUNCTION sha256_text_valid(text)
    CHARACTER(LEN=*), INTENT(IN) :: text
    INTEGER :: i,code
    sha256_text_valid=LEN_TRIM(text)==64
    IF (.NOT.sha256_text_valid) RETURN
    DO i=1,64
      code=IACHAR(text(i:i))
      IF (.NOT.((code>=IACHAR('0') .AND. code<=IACHAR('9')) .OR. &
                (code>=IACHAR('a') .AND. code<=IACHAR('f')) .OR. &
                (code>=IACHAR('A') .AND. code<=IACHAR('F')))) THEN
        sha256_text_valid=.FALSE.
        RETURN
      END IF
    END DO
  END FUNCTION sha256_text_valid

  PURE LOGICAL FUNCTION legacy_shapes_valid(legacy,nx,ny,nz)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    INTEGER, INTENT(IN) :: nx,ny,nz
    legacy_shapes_valid=nx>=4 .AND. ny>=4 .AND. nz>=2
    IF (.NOT.legacy_shapes_valid) RETURN
    legacy_shapes_valid=.FALSE.
    IF (.NOT.ALLOCATED(legacy%dy) .OR. &
        .NOT.ALLOCATED(legacy%above_ground)) RETURN
    IF (ANY(SHAPE(legacy%dy)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(legacy%above_ground)/=(/nx,ny,nz/))) RETURN
    legacy_shapes_valid=field_shape_ok(legacy%pressure,nx,ny,nz) .AND. &
      field_shape_ok(legacy%temperature,nx,ny,nz) .AND. &
      field_shape_ok(legacy%specific_humidity,nx,ny,nz) .AND. &
      field_shape_ok(legacy%u,nx,ny,nz) .AND. &
      field_shape_ok(legacy%v,nx,ny,nz) .AND. &
      field_shape_ok(legacy%omega,nx,ny,nz) .AND. &
      field_shape_ok(legacy%geopotential_height,nx,ny,nz) .AND. &
      field_shape_ok(legacy%cloud_omega,nx,ny,nz) .AND. &
      field_shape_ok(legacy%cloud_fraction,nx,ny,nz) .AND. &
      field_shape_ok(legacy%cloud_type,nx,ny,nz) .AND. &
      field_shape_ok(legacy%radar_reflectivity,nx,ny,nz) .AND. &
      field_shape_ok(legacy%precipitation_phase,nx,ny,nz) .AND. &
      field_shape_ok(legacy%surface_pressure,nx,ny) .AND. &
      field_shape_ok(legacy%latitude,nx,ny)
  END FUNCTION legacy_shapes_valid

  PURE LOGICAL FUNCTION legacy_metadata_valid(legacy)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    LOGICAL, ALLOCATABLE :: domain(:,:,:)
    INTEGER :: nx,ny,nz
    REAL(real64) :: grid_scale

    CALL legacy_dimensions(legacy,nx,ny,nz)
    legacy_metadata_valid=.FALSE.
    IF (legacy%vertical_order/=LEGACY_BOTTOM_TO_TOP .AND. &
        legacy%vertical_order/=LEGACY_TOP_TO_BOTTOM) RETURN
    IF (legacy%wind_coordinate/=LEGACY_WIND_GRID_RELATIVE) RETURN
    grid_scale=distance_unit_scale(legacy%grid_spacing_unit)
    IF (grid_scale<=0.0_real64) RETURN
    IF (ANY(.NOT.ieee_is_finite(legacy%dx)) .OR. ANY(legacy%dx<=0.0_real64) .OR. &
        ANY(legacy%dx>1.0e7_real64/grid_scale) .OR. &
        ANY(.NOT.ieee_is_finite(legacy%dy)) .OR. ANY(legacy%dy<=0.0_real64) .OR. &
        ANY(legacy%dy>1.0e7_real64/grid_scale)) RETURN
    ALLOCATE(domain(nx,ny,nz))
    CALL copy_domain(legacy%above_ground,domain,legacy%vertical_order)
    IF (.NOT.vertical_domain_valid(domain)) RETURN

    IF (.NOT.field_metadata_ok(legacy%pressure,legacy%analysis_time, &
      pressure_unit_scale(legacy%pressure%unit)>0.0_real64, &
      legacy%above_ground,SOURCE_BACKGROUND_MODEL)) RETURN
    IF (ANY(.NOT.ieee_is_finite(legacy%pressure%value))) RETURN
    IF (.NOT.field_metadata_ok(legacy%temperature,legacy%analysis_time, &
      unit_allowed(legacy%temperature%unit,UNIT_TEMPERATURE),legacy%above_ground)) RETURN
    IF (.NOT.field_metadata_ok(legacy%specific_humidity,legacy%analysis_time, &
      unit_allowed(legacy%specific_humidity%unit,UNIT_SPECIFIC_HUMIDITY), &
      legacy%above_ground)) RETURN
    IF (.NOT.field_metadata_ok(legacy%u,legacy%analysis_time, &
      unit_allowed(legacy%u%unit,UNIT_WIND),legacy%above_ground, &
      SOURCE_ANALYZED_WIND)) RETURN
    IF (.NOT.field_metadata_ok(legacy%v,legacy%analysis_time, &
      unit_allowed(legacy%v%unit,UNIT_WIND),legacy%above_ground, &
      SOURCE_ANALYZED_WIND)) RETURN
    IF (.NOT.field_metadata_ok(legacy%omega,legacy%analysis_time, &
      unit_allowed(legacy%omega%unit,UNIT_OMEGA),legacy%above_ground, &
      SOURCE_ANALYZED_WIND)) RETURN
    IF (.NOT.field_metadata_ok(legacy%geopotential_height,legacy%analysis_time, &
      unit_allowed(legacy%geopotential_height%unit,UNIT_HEIGHT), &
      legacy%above_ground)) RETURN
    IF (.NOT.field_metadata_ok(legacy%cloud_omega,legacy%analysis_time, &
      unit_allowed(legacy%cloud_omega%unit,UNIT_OMEGA),legacy%above_ground, &
      SOURCE_CLOUD_ANALYSIS)) RETURN
    IF (ANY(legacy%above_ground .AND. &
        legacy%cloud_omega%source/=SOURCE_CLOUD_ANALYSIS)) RETURN
    IF (.NOT.field_metadata_ok(legacy%surface_pressure,legacy%analysis_time, &
      pressure_unit_scale(legacy%surface_pressure%unit)>0.0_real64,0_int32)) RETURN
    IF (.NOT.field_metadata_ok(legacy%latitude,legacy%analysis_time, &
      unit_allowed(legacy%latitude%unit,UNIT_LATITUDE),0_int32)) RETURN
    legacy_metadata_valid=.TRUE.
  END FUNCTION legacy_metadata_valid

  PURE LOGICAL FUNCTION legacy_values_in_range(legacy)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy
    REAL(real64) :: pressure_scale,surface_scale
    pressure_scale=pressure_unit_scale(legacy%pressure%unit)
    surface_scale=pressure_unit_scale(legacy%surface_pressure%unit)
    legacy_values_in_range=.FALSE.
    ! Canonical validation owns domain core-field ranges.  Keep full pressure
    ! (all levels form dp), legacy-only fields, and optional observations here.
    IF (ANY(REAL(legacy%pressure%value,real64)<100.0_real64/pressure_scale) .OR. &
        ANY(REAL(legacy%pressure%value,real64)>120000.0_real64/pressure_scale)) RETURN
    IF (ANY(legacy%above_ground .AND. &
        (legacy%geopotential_height%value<-2000.0_real32 .OR. &
         legacy%geopotential_height%value>100000.0_real32))) RETURN
    IF (ANY(REAL(legacy%surface_pressure%value,real64)<100.0_real64/surface_scale) .OR. &
        ANY(REAL(legacy%surface_pressure%value,real64)>120000.0_real64/surface_scale)) RETURN
    IF (ANY(legacy%latitude%value<-90.0_real32 .OR. &
            legacy%latitude%value>90.0_real32)) RETURN
    IF (ANY(legacy%cloud_fraction%valid .AND. &
        (legacy%cloud_fraction%value<0.0_real32 .OR. &
         legacy%cloud_fraction%value>1.0_real32))) RETURN
    IF (ANY(legacy%cloud_type%valid .AND. &
        (legacy%cloud_type%value<0_int32 .OR. &
         legacy%cloud_type%value>11_int32))) RETURN
    IF (ANY(legacy%radar_reflectivity%valid .AND. &
        (legacy%radar_reflectivity%value<0.0_real32 .OR. &
         legacy%radar_reflectivity%value>100.0_real32))) RETURN
    IF (ANY(legacy%precipitation_phase%valid .AND. &
        (legacy%precipitation_phase%value<0_int32 .OR. &
         legacy%precipitation_phase%value>5_int32))) RETURN
    legacy_values_in_range=.TRUE.
  END FUNCTION legacy_values_in_range

  PURE LOGICAL FUNCTION optional_observations_unambiguous(legacy)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: legacy

    optional_observations_unambiguous=.FALSE.
    IF (.NOT.field_metadata_ok(legacy%cloud_fraction,legacy%analysis_time, &
      unit_allowed(legacy%cloud_fraction%unit,UNIT_FRACTION)) .OR. &
        .NOT.field_metadata_ok(legacy%cloud_type,legacy%analysis_time, &
          TRIM(legacy%cloud_type%code_table)=='cloud_type_v1') .OR. &
        .NOT.field_metadata_ok(legacy%radar_reflectivity,legacy%analysis_time, &
          unit_allowed(legacy%radar_reflectivity%unit,UNIT_DBZ)) .OR. &
        .NOT.field_metadata_ok(legacy%precipitation_phase, &
          legacy%analysis_time, &
          TRIM(legacy%precipitation_phase%code_table)=='precipitation_phase_v1')) RETURN

    IF (ANY((legacy%cloud_fraction%valid .OR. legacy%cloud_type%valid .OR. &
             legacy%radar_reflectivity%valid .OR. &
             legacy%precipitation_phase%valid) .AND. &
            .NOT.legacy%above_ground)) RETURN
    IF (ANY(legacy%cloud_fraction%valid .NEQV. legacy%cloud_type%valid)) RETURN
    IF (ANY(legacy%cloud_fraction%valid .AND. &
        (legacy%cloud_fraction%source/=SOURCE_CLOUD_ANALYSIS .OR. &
         legacy%cloud_type%source/=SOURCE_CLOUD_ANALYSIS))) RETURN
    IF (ANY(legacy%radar_reflectivity%valid .AND. &
        legacy%radar_reflectivity%source/=SOURCE_RADAR_DBZ)) RETURN
    IF (ANY(legacy%precipitation_phase%valid .AND. &
        .NOT.legacy%radar_reflectivity%valid)) RETURN
    IF (ANY(legacy%precipitation_phase%valid .AND. &
        legacy%precipitation_phase%source/=SOURCE_RADAR_DBZ)) RETURN
    IF (legacy%cloud_analysis_declared .NEQV. &
        ANY(legacy%cloud_fraction%valid)) RETURN
    IF (legacy%radar_analysis_declared .NEQV. &
        ANY(legacy%radar_reflectivity%valid)) RETURN
    IF (.NOT.legacy%cloud_analysis_declared .AND. &
        (.NOT.field_absent(legacy%cloud_fraction) .OR. &
         .NOT.field_absent(legacy%cloud_type))) RETURN
    IF (.NOT.legacy%radar_analysis_declared .AND. &
        (.NOT.field_absent(legacy%radar_reflectivity) .OR. &
         .NOT.field_absent(legacy%precipitation_phase))) RETURN
    optional_observations_unambiguous=.TRUE.
  END FUNCTION optional_observations_unambiguous

  PURE LOGICAL FUNCTION real3_metadata_ok(field,analysis_time,unit_ok,domain,source_bit)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER(int64), INTENT(IN) :: analysis_time
    LOGICAL, INTENT(IN) :: unit_ok
    LOGICAL, INTENT(IN), OPTIONAL :: domain(:,:,:)
    INTEGER(int32), INTENT(IN), OPTIONAL :: source_bit

    real3_metadata_ok=.FALSE.
    IF (.NOT.unit_ok .OR. field%valid_time/=analysis_time) RETURN
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality))) RETURN
    IF (ANY(field%valid .AND. .NOT.cell_is_usable(field%valid,field%quality, &
        field%source,field%valid_time,analysis_time)) .OR. &
        ANY(field%valid .AND. .NOT.ieee_is_finite(field%value))) RETURN
    IF (PRESENT(domain)) THEN
      IF (ANY(domain .AND. .NOT.field%valid) .OR. &
          ANY((.NOT.domain) .AND. field%valid)) RETURN
      IF (PRESENT(source_bit)) THEN
        IF (source_bit/=0_int32 .AND. &
            ANY(domain .AND. IAND(field%source,source_bit)==0_int32)) RETURN
      END IF
    END IF
    real3_metadata_ok=.TRUE.
  END FUNCTION real3_metadata_ok

  PURE LOGICAL FUNCTION integer3_metadata_ok(field,analysis_time,table_ok)
    TYPE(integer_field3d), INTENT(IN) :: field
    INTEGER(int64), INTENT(IN) :: analysis_time
    LOGICAL, INTENT(IN) :: table_ok

    integer3_metadata_ok=.FALSE.
    IF (.NOT.table_ok .OR. field%valid_time/=analysis_time) RETURN
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality))) RETURN
    IF (ANY(field%valid .AND. .NOT.cell_is_usable(field%valid,field%quality, &
        field%source,field%valid_time,analysis_time))) RETURN
    integer3_metadata_ok=.TRUE.
  END FUNCTION integer3_metadata_ok

  PURE LOGICAL FUNCTION real2_metadata_ok(field,analysis_time,unit_ok,source_bit)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER(int64), INTENT(IN) :: analysis_time
    LOGICAL, INTENT(IN) :: unit_ok
    INTEGER(int32), INTENT(IN), OPTIONAL :: source_bit

    real2_metadata_ok=.FALSE.
    IF (.NOT.unit_ok .OR. field%valid_time/=analysis_time) RETURN
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality))) RETURN
    IF (.NOT.ALL(cell_is_usable(field%valid,field%quality,field%source, &
        field%valid_time,analysis_time)) .OR. &
        ANY(.NOT.ieee_is_finite(field%value))) RETURN
    IF (PRESENT(source_bit)) THEN
      IF (source_bit/=0_int32 .AND. &
          ANY(IAND(field%source,source_bit)==0_int32)) RETURN
    END IF
    real2_metadata_ok=.TRUE.
  END FUNCTION real2_metadata_ok

  PURE LOGICAL FUNCTION real3_absent(field)
    TYPE(field3d), INTENT(IN) :: field
    real3_absent=.NOT.ANY(field%valid) .AND. ALL(field%source==0_int32) .AND. &
      ALL(IAND(field%quality,QUALITY_RAW_MISSING)/=0_int32) .AND. &
      ALL(field%value==0.0_real32)
  END FUNCTION real3_absent

  PURE LOGICAL FUNCTION integer3_absent(field)
    TYPE(integer_field3d), INTENT(IN) :: field
    integer3_absent=.NOT.ANY(field%valid) .AND. ALL(field%source==0_int32) .AND. &
      ALL(IAND(field%quality,QUALITY_RAW_MISSING)/=0_int32) .AND. &
      ALL(field%value==0_int32)
  END FUNCTION integer3_absent

  PURE LOGICAL FUNCTION real3_shape_ok(field,nx,ny,nz)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    real3_shape_ok=ALLOCATED(field%value) .AND. ALLOCATED(field%valid) .AND. &
      ALLOCATED(field%quality) .AND. ALLOCATED(field%source)
    IF (.NOT.real3_shape_ok) RETURN
    real3_shape_ok=ALL(SHAPE(field%value)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%valid)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%quality)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%source)==(/nx,ny,nz/))
  END FUNCTION real3_shape_ok

  PURE LOGICAL FUNCTION integer3_shape_ok(field,nx,ny,nz)
    TYPE(integer_field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    integer3_shape_ok=ALLOCATED(field%value) .AND. ALLOCATED(field%valid) .AND. &
      ALLOCATED(field%quality) .AND. ALLOCATED(field%source)
    IF (.NOT.integer3_shape_ok) RETURN
    integer3_shape_ok=ALL(SHAPE(field%value)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%valid)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%quality)==(/nx,ny,nz/)) .AND. &
      ALL(SHAPE(field%source)==(/nx,ny,nz/))
  END FUNCTION integer3_shape_ok

  PURE LOGICAL FUNCTION real2_shape_ok(field,nx,ny)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny
    real2_shape_ok=ALLOCATED(field%value) .AND. ALLOCATED(field%valid) .AND. &
      ALLOCATED(field%quality) .AND. ALLOCATED(field%source)
    IF (.NOT.real2_shape_ok) RETURN
    real2_shape_ok=ALL(SHAPE(field%value)==(/nx,ny/)) .AND. &
      ALL(SHAPE(field%valid)==(/nx,ny/)) .AND. &
      ALL(SHAPE(field%quality)==(/nx,ny/)) .AND. &
      ALL(SHAPE(field%source)==(/nx,ny/))
  END FUNCTION real2_shape_ok

  PURE LOGICAL FUNCTION vertical_domain_valid(domain)
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    INTEGER :: i,j,k
    vertical_domain_valid=.FALSE.
    DO j=1,SIZE(domain,2); DO i=1,SIZE(domain,1)
      IF (.NOT.ANY(domain(i,j,:))) RETURN
      DO k=1,SIZE(domain,3)-1
        IF (domain(i,j,k) .AND. .NOT.domain(i,j,k+1)) RETURN
      END DO
    END DO; END DO
    vertical_domain_valid=.TRUE.
  END FUNCTION vertical_domain_valid

  PURE SUBROUTINE copy_domain(source,destination,vertical_order)
    LOGICAL, INTENT(IN) :: source(:,:,:)
    LOGICAL, INTENT(OUT) :: destination(:,:,:)
    INTEGER, INTENT(IN) :: vertical_order
    INTEGER :: k,source_k
    DO k=1,SIZE(source,3)
      source_k=vertical_index(k,SIZE(source,3),vertical_order)
      destination(:,:,k)=source(:,:,source_k)
    END DO
  END SUBROUTINE copy_domain

  PURE SUBROUTINE copy_real3(source,destination,vertical_order,scale,domain)
    TYPE(field3d), INTENT(IN) :: source
    TYPE(field3d), INTENT(INOUT) :: destination
    INTEGER, INTENT(IN) :: vertical_order
    REAL(real64), INTENT(IN) :: scale
    LOGICAL, INTENT(IN), OPTIONAL :: domain(:,:,:)
    INTEGER :: k,source_k
    destination%value=0.0_real32
    DO k=1,SIZE(source%value,3)
      source_k=vertical_index(k,SIZE(source%value,3),vertical_order)
      IF (PRESENT(domain)) THEN
        WHERE(domain(:,:,k))
          destination%value(:,:,k)= &
            REAL(scale*REAL(source%value(:,:,source_k),real64),real32)
          destination%valid(:,:,k)=source%valid(:,:,source_k)
          destination%quality(:,:,k)=source%quality(:,:,source_k)
          destination%source(:,:,k)=source%source(:,:,source_k)
        END WHERE
      ELSE
        destination%value(:,:,k)= &
          REAL(scale*REAL(source%value(:,:,source_k),real64),real32)
        destination%valid(:,:,k)=source%valid(:,:,source_k)
        destination%quality(:,:,k)=source%quality(:,:,source_k)
        destination%source(:,:,k)=source%source(:,:,source_k)
      END IF
    END DO
  END SUBROUTINE copy_real3

  PURE SUBROUTINE copy_specific_humidity(source,destination,vertical_order,domain,status)
    TYPE(field3d), INTENT(IN) :: source
    TYPE(field3d), INTENT(INOUT) :: destination
    INTEGER, INTENT(IN) :: vertical_order
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,source_k
    REAL(real64) :: q
    status=STATUS_FAILED
    destination%value=0.0_real32
    DO k=1,SIZE(source%value,3)
      source_k=vertical_index(k,SIZE(source%value,3),vertical_order)
      DO j=1,SIZE(source%value,2); DO i=1,SIZE(source%value,1)
        IF (.NOT.domain(i,j,k)) CYCLE
        q=REAL(source%value(i,j,source_k),real64)
        IF (.NOT.ieee_is_finite(q) .OR. q<0.0_real64 .OR. q>=1.0_real64) RETURN
        destination%value(i,j,k)=REAL(q/(1.0_real64-q),real32)
        destination%valid(i,j,k)=source%valid(i,j,source_k)
        destination%quality(i,j,k)=source%quality(i,j,source_k)
        destination%source(i,j,k)=source%source(i,j,source_k)
      END DO; END DO
    END DO
    status=STATUS_OK
  END SUBROUTINE copy_specific_humidity

  PURE SUBROUTINE copy_integer3(source,destination,vertical_order,domain)
    TYPE(integer_field3d), INTENT(IN) :: source
    TYPE(integer_field3d), INTENT(INOUT) :: destination
    INTEGER, INTENT(IN) :: vertical_order
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    INTEGER :: k,source_k
    destination%value=0_int32
    DO k=1,SIZE(source%value,3)
      source_k=vertical_index(k,SIZE(source%value,3),vertical_order)
      WHERE(domain(:,:,k))
        destination%value(:,:,k)=source%value(:,:,source_k)
        destination%valid(:,:,k)=source%valid(:,:,source_k)
        destination%quality(:,:,k)=source%quality(:,:,source_k)
        destination%source(:,:,k)=source%source(:,:,source_k)
      END WHERE
    END DO
  END SUBROUTINE copy_integer3

  PURE SUBROUTINE copy_real2(source,destination,scale)
    TYPE(field2d), INTENT(IN) :: source
    TYPE(field2d), INTENT(INOUT) :: destination
    REAL(real64), INTENT(IN) :: scale
    destination%value=REAL(scale*REAL(source%value,real64),real32)
    destination%valid=source%valid
    destination%quality=source%quality
    destination%source=source%source
  END SUBROUTINE copy_real2

  PURE INTEGER FUNCTION vertical_index(k,nz,vertical_order)
    INTEGER, INTENT(IN) :: k,nz,vertical_order
    IF (vertical_order==LEGACY_TOP_TO_BOTTOM) THEN
      vertical_index=nz+1-k
    ELSE
      vertical_index=k
    END IF
  END FUNCTION vertical_index

  PURE REAL(real64) FUNCTION pressure_unit_scale(unit)
    CHARACTER(LEN=*), INTENT(IN) :: unit
    SELECT CASE(TRIM(unit))
    CASE('Pa','pa')
      pressure_unit_scale=1.0_real64
    CASE('hPa','hpa','mb')
      pressure_unit_scale=100.0_real64
    CASE DEFAULT
      pressure_unit_scale=-1.0_real64
    END SELECT
  END FUNCTION pressure_unit_scale

  PURE REAL(real64) FUNCTION distance_unit_scale(unit)
    CHARACTER(LEN=*), INTENT(IN) :: unit
    SELECT CASE(TRIM(unit))
    CASE('m','meters')
      distance_unit_scale=1.0_real64
    CASE('km','kilometers')
      distance_unit_scale=1000.0_real64
    CASE DEFAULT
      distance_unit_scale=-1.0_real64
    END SELECT
  END FUNCTION distance_unit_scale

  PURE LOGICAL FUNCTION unit_allowed(unit,kind)
    CHARACTER(LEN=*), INTENT(IN) :: unit
    INTEGER, INTENT(IN) :: kind
    SELECT CASE(kind)
    CASE(UNIT_TEMPERATURE)
      unit_allowed=TRIM(unit)=='K' .OR. TRIM(unit)=='kelvins'
    CASE(UNIT_SPECIFIC_HUMIDITY)
      unit_allowed=TRIM(unit)=='kg/kg' .OR. TRIM(unit)=='kg kg-1 moist'
    CASE(UNIT_WIND)
      unit_allowed=TRIM(unit)=='m s-1' .OR. TRIM(unit)=='meters/second'
    CASE(UNIT_OMEGA)
      unit_allowed=TRIM(unit)=='Pa s-1' .OR. TRIM(unit)=='pa/s' .OR. &
        TRIM(unit)=='pascals/second'
    CASE(UNIT_HEIGHT)
      unit_allowed=TRIM(unit)=='m' .OR. TRIM(unit)=='meters'
    CASE(UNIT_FRACTION)
      unit_allowed=TRIM(unit)=='1' .OR. TRIM(unit)=='fraction'
    CASE(UNIT_DBZ)
      unit_allowed=TRIM(unit)=='dBZ' .OR. TRIM(unit)=='dbz'
    CASE(UNIT_LATITUDE)
      unit_allowed=TRIM(unit)=='degree_north' .OR. TRIM(unit)=='degrees'
    CASE DEFAULT
      unit_allowed=.FALSE.
    END SELECT
  END FUNCTION unit_allowed

END MODULE cloud_bal_legacy_shadow_adapter
