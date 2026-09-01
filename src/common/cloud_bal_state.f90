! Canonical Cloud-BAL state and transaction contract.
!
! Physical routines receive only these types.  Missing-value sentinels and
! legacy integer statuses are converted by I/O adapters before entry here.
MODULE cloud_bal_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32, real64, int32, int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: CLOUD_BAL_SCHEMA_VERSION = 1
  INTEGER, PARAMETER, PUBLIC :: STATUS_FAILED = 0
  INTEGER, PARAMETER, PUBLIC :: STATUS_DEGRADED = 1
  INTEGER, PARAMETER, PUBLIC :: STATUS_OK = 2

  INTEGER, PARAMETER, PUBLIC :: MODE_OFF = 0
  INTEGER, PARAMETER, PUBLIC :: MODE_SHADOW = 1

  INTEGER, PARAMETER, PUBLIC :: REASON_NONE = 0
  INTEGER, PARAMETER, PUBLIC :: REASON_SHAPE = 1
  INTEGER, PARAMETER, PUBLIC :: REASON_METADATA = 2
  INTEGER, PARAMETER, PUBLIC :: REASON_REQUIRED_COVERAGE = 3
  INTEGER, PARAMETER, PUBLIC :: REASON_NONFINITE = 4
  INTEGER, PARAMETER, PUBLIC :: REASON_RANGE = 5
  INTEGER, PARAMETER, PUBLIC :: REASON_SOLVER = 6
  INTEGER, PARAMETER, PUBLIC :: REASON_GATE = 7
  INTEGER, PARAMETER, PUBLIC :: REASON_RADAR_CONTRACT = 8
  INTEGER, PARAMETER, PUBLIC :: REASON_AUTHORITY = 9

  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_BACKGROUND_MODEL = ISHFT(1_int32,0)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_CONVENTIONAL_OBS = ISHFT(1_int32,1)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_CLOUD_ANALYSIS = ISHFT(1_int32,2)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_RADAR_DBZ = ISHFT(1_int32,3)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_RADAR_VRAD = ISHFT(1_int32,4)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_LIGHTNING = ISHFT(1_int32,5)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_ANALYZED_WIND = ISHFT(1_int32,6)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_COLUMN_PHYSICS = ISHFT(1_int32,7)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_BALANCE_OPERATOR = ISHFT(1_int32,8)
  INTEGER(int32), PARAMETER, PUBLIC :: SOURCE_OUTPUT_ADAPTER = ISHFT(1_int32,9)

  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_RAW_MISSING = ISHFT(1_int32,0)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_QC_REJECTED = ISHFT(1_int32,1)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_TIME_MISMATCH = ISHFT(1_int32,2)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_BELOW_GROUND_FILLED = ISHFT(1_int32,3)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_PHASE_UNCERTAIN = ISHFT(1_int32,4)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_BRIGHT_BAND_OR_MIXED = ISHFT(1_int32,5)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_FALL_SPEED_UNCERTAIN = ISHFT(1_int32,6)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_GEOMETRY_POOR = ISHFT(1_int32,7)
  INTEGER(int32), PARAMETER, PUBLIC :: QUALITY_LEGACY_PROVENANCE = ISHFT(1_int32,8)

  INTEGER(int32), PARAMETER, PUBLIC :: LOS_REJECTED = 0_int32
  INTEGER(int32), PARAMETER, PUBLIC :: LOS_ASSIMILATED = 1_int32
  INTEGER(int32), PARAMETER, PUBLIC :: LOS_HELD_OUT = 2_int32

  REAL(real64), PARAMETER :: RD_AIR = 287.05_real64
  REAL(real64), PARAMETER :: GRAVITY = 9.80665_real64

  TYPE, PUBLIC :: field3d
    REAL(real32), ALLOCATABLE :: value(:,:,:)
    LOGICAL, ALLOCATABLE :: valid(:,:,:)
    INTEGER(int32), ALLOCATABLE :: quality(:,:,:)
    INTEGER(int32), ALLOCATABLE :: source(:,:,:)
    INTEGER(int64) :: valid_time = 0_int64
    CHARACTER(LEN=16) :: unit = ''
  END TYPE field3d

  TYPE, PUBLIC :: field2d
    REAL(real32), ALLOCATABLE :: value(:,:)
    LOGICAL, ALLOCATABLE :: valid(:,:)
    INTEGER(int32), ALLOCATABLE :: quality(:,:)
    INTEGER(int32), ALLOCATABLE :: source(:,:)
    INTEGER(int64) :: valid_time = 0_int64
    CHARACTER(LEN=16) :: unit = ''
  END TYPE field2d

  TYPE, PUBLIC :: field4d
    REAL(real32), ALLOCATABLE :: value(:,:,:,:)
    LOGICAL, ALLOCATABLE :: valid(:,:,:,:)
    INTEGER(int32), ALLOCATABLE :: quality(:,:,:,:)
    INTEGER(int32), ALLOCATABLE :: source(:,:,:,:)
    INTEGER(int64) :: valid_time = 0_int64
    CHARACTER(LEN=16) :: unit = ''
  END TYPE field4d

  TYPE, PUBLIC :: integer_field3d
    INTEGER(int32), ALLOCATABLE :: value(:,:,:)
    LOGICAL, ALLOCATABLE :: valid(:,:,:)
    INTEGER(int32), ALLOCATABLE :: quality(:,:,:)
    INTEGER(int32), ALLOCATABLE :: source(:,:,:)
    INTEGER(int64) :: valid_time = 0_int64
    CHARACTER(LEN=32) :: code_table = ''
  END TYPE integer_field3d

  TYPE, PUBLIC :: grid_spec
    INTEGER :: nx = 0, ny = 0, nz = 0
    CHARACTER(LEN=64) :: grid_id = ''
    REAL(real64), ALLOCATABLE :: dx(:,:), dy(:,:), dp(:,:,:)
    ! Finite-volume dry-air cell mass used by all state and operator budgets.
    REAL(real64), ALLOCATABLE :: cell_measure(:,:,:)
  END TYPE grid_spec

  TYPE, PUBLIC :: radar_los_observation_set
    LOGICAL :: is_present = .FALSE.
    INTEGER :: nradar = 0
    TYPE(field4d) :: vrad, nyquist, sigma_vrad
    REAL(real32), ALLOCATABLE :: beam(:,:,:,:,:)
    INTEGER(int64), ALLOCATABLE :: observation_id_hi(:,:,:,:)
    INTEGER(int64), ALLOCATABLE :: observation_id_lo(:,:,:,:)
    INTEGER(int32), ALLOCATABLE :: usage(:,:,:,:)
    INTEGER(int32), ALLOCATABLE :: radar_id(:)
    INTEGER(int64), ALLOCATABLE :: observation_time(:)
    REAL(real64), ALLOCATABLE :: site_lat(:), site_lon(:), site_height(:)
    REAL(real64), ALLOCATABLE :: wavelength(:)
    INTEGER(int32), ALLOCATABLE :: los_support(:,:,:,:)
    LOGICAL :: has_colocated_dbz = .FALSE.
    TYPE(field4d) :: colocated_dbz
    REAL(real32), ALLOCATABLE :: geometry_condition(:,:,:)
    INTEGER(int32), ALLOCATABLE :: geometry_rank(:,:,:)
    LOGICAL :: has_spectrum_width = .FALSE.
    TYPE(field4d) :: spectrum_width
  END TYPE radar_los_observation_set

  TYPE, PUBLIC :: cloud_bal_state_type
    INTEGER :: schema_version = CLOUD_BAL_SCHEMA_VERSION
    TYPE(grid_spec) :: grid
    TYPE(field3d) :: pressure, temperature, vapor, u, v, omega, omega_target
    TYPE(field3d) :: geopotential
    TYPE(field3d) :: cloud_fraction, radar_reflectivity
    TYPE(integer_field3d) :: cloud_type, precipitation_phase, lightning_support
    TYPE(field3d) :: cloud_water, cloud_ice, rain, snow, graupel
    TYPE(field3d) :: vt_z_mean, vt_z_sigma
    TYPE(field2d) :: surface_pressure, surface_temperature, latitude
    TYPE(field2d) :: omega_top_boundary, omega_bottom_boundary
    INTEGER(int32), ALLOCATABLE :: obs_support(:,:,:)
    INTEGER(int32), ALLOCATABLE :: hydro_support(:,:,:)
    REAL(real32), ALLOCATABLE :: balance_beta(:,:,:)
    TYPE(radar_los_observation_set) :: radar_los
  END TYPE cloud_bal_state_type

  TYPE, PUBLIC :: coverage_summary
    INTEGER(int64) :: required = 0_int64
    INTEGER(int64) :: usable = 0_int64
    INTEGER(int64) :: excluded = 0_int64
    INTEGER(int64) :: los_assimilated = 0_int64
    INTEGER(int64) :: los_held_out = 0_int64
    REAL(real64) :: usable_fraction = 0.0_real64
  END TYPE coverage_summary

  TYPE, PUBLIC :: numerical_diagnostics
    INTEGER :: solver_reason = REASON_NONE
    INTEGER :: solver_iterations = 0
    REAL(real64) :: continuity_background_rms = 0.0_real64
    REAL(real64) :: continuity_forced_rms = 0.0_real64
    REAL(real64) :: continuity_final_rms = 0.0_real64
    REAL(real64) :: momentum_background_rms = 0.0_real64
    REAL(real64) :: momentum_forced_rms = 0.0_real64
    REAL(real64) :: momentum_final_rms = 0.0_real64
    REAL(real64) :: max_wind_increment = 0.0_real64
    REAL(real64) :: max_omega_increment = 0.0_real64
    REAL(real64) :: water_error = 0.0_real64
    REAL(real64) :: phase_error = 0.0_real64
    REAL(real64) :: ledger_error = 0.0_real64
    REAL(real64) :: flux_input = 0.0_real64
    REAL(real64) :: flux_deposited = 0.0_real64
    REAL(real64) :: flux_suspended = 0.0_real64
    REAL(real64) :: flux_boundary_exit = 0.0_real64
    REAL(real64) :: flux_observation_blocked = 0.0_real64
    REAL(real64) :: flux_microphysical_loss = 0.0_real64
    REAL(real64) :: radar_analysis_increment = 0.0_real64
    REAL(real64) :: enthalpy_error = 0.0_real64
    REAL(real64) :: rotational_rms = 0.0_real64
    REAL(real64) :: divergent_rms = 0.0_real64
  END TYPE numerical_diagnostics

  TYPE, PUBLIC :: stage_result
    INTEGER :: status = STATUS_FAILED
    INTEGER :: reason_code = REASON_NONE
    LOGICAL, ALLOCATABLE :: changed(:,:,:)
    TYPE(coverage_summary) :: coverage
    REAL(real64) :: los_rms_input = 0.0_real64
    REAL(real64) :: los_rms_candidate = 0.0_real64
    REAL(real64) :: los_threshold = 0.0_real64
    LOGICAL :: los_gate_applied = .FALSE.
    LOGICAL :: los_gate_passed = .FALSE.
    TYPE(numerical_diagnostics) :: numerical
  END TYPE stage_result

  ! The actual NetCDF/legacy reader owns construction of this object.  The
  ! public read operation validates and deep-copies it transactionally.
  TYPE, PUBLIC :: canonical_input_spec
    TYPE(cloud_bal_state_type), ALLOCATABLE :: supplied_state
  END TYPE canonical_input_spec

  PUBLIC :: initialize_cloud_bal_state
  PUBLIC :: initialize_field
  PUBLIC :: initialize_integer_field
  PUBLIC :: initialize_stage_result
  PUBLIC :: read_canonical_state
  PUBLIC :: validate_canonical_state
  PUBLIC :: validate_los_observations
  PUBLIC :: commit_candidate
  PUBLIC :: reject_candidate
  PUBLIC :: omega_to_w
  PUBLIC :: w_to_omega
  PUBLIC :: field_coverage
  PUBLIC :: pipeline_mode_valid

  INTERFACE initialize_field
    MODULE PROCEDURE initialize_field2d
    MODULE PROCEDURE initialize_field3d
    MODULE PROCEDURE initialize_field4d
  END INTERFACE initialize_field

CONTAINS

  SUBROUTINE initialize_field3d(field,nx,ny,nz,valid_time,unit)
    TYPE(field3d), INTENT(OUT) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    ALLOCATE(field%value(nx,ny,nz),field%valid(nx,ny,nz), &
             field%quality(nx,ny,nz),field%source(nx,ny,nz))
    field%value=0.0_real32
    field%valid=.FALSE.
    field%quality=QUALITY_RAW_MISSING
    field%source=0_int32
    field%valid_time=valid_time
    field%unit=unit
  END SUBROUTINE initialize_field3d

  SUBROUTINE initialize_field2d(field,nx,ny,valid_time,unit)
    TYPE(field2d), INTENT(OUT) :: field
    INTEGER, INTENT(IN) :: nx,ny
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    ALLOCATE(field%value(nx,ny),field%valid(nx,ny),field%quality(nx,ny), &
             field%source(nx,ny))
    field%value=0.0_real32
    field%valid=.FALSE.
    field%quality=QUALITY_RAW_MISSING
    field%source=0_int32
    field%valid_time=valid_time
    field%unit=unit
  END SUBROUTINE initialize_field2d

  SUBROUTINE initialize_field4d(field,nx,ny,nz,nradar,valid_time,unit)
    TYPE(field4d), INTENT(OUT) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz,nradar
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    ALLOCATE(field%value(nx,ny,nz,nradar),field%valid(nx,ny,nz,nradar), &
             field%quality(nx,ny,nz,nradar),field%source(nx,ny,nz,nradar))
    field%value=0.0_real32
    field%valid=.FALSE.
    field%quality=QUALITY_RAW_MISSING
    field%source=0_int32
    field%valid_time=valid_time
    field%unit=unit
  END SUBROUTINE initialize_field4d

  SUBROUTINE initialize_integer_field(field,nx,ny,nz,valid_time,code_table)
    TYPE(integer_field3d), INTENT(OUT) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: code_table
    ALLOCATE(field%value(nx,ny,nz),field%valid(nx,ny,nz), &
             field%quality(nx,ny,nz),field%source(nx,ny,nz))
    field%value=0_int32
    field%valid=.FALSE.
    field%quality=QUALITY_RAW_MISSING
    field%source=0_int32
    field%valid_time=valid_time
    field%code_table=code_table
  END SUBROUTINE initialize_integer_field

  SUBROUTINE initialize_cloud_bal_state(state,nx,ny,nz,valid_time,grid_id,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: grid_id
    INTEGER, INTENT(OUT) :: status

    status=STATUS_FAILED
    IF (nx < 1 .OR. ny < 1 .OR. nz < 1 .OR. LEN_TRIM(grid_id) == 0) RETURN
    state%schema_version=CLOUD_BAL_SCHEMA_VERSION
    state%grid%nx=nx; state%grid%ny=ny; state%grid%nz=nz
    state%grid%grid_id=grid_id
    ALLOCATE(state%grid%dx(nx,ny),state%grid%dy(nx,ny), &
             state%grid%dp(nx,ny,nz),state%grid%cell_measure(nx,ny,nz))
    state%grid%dx=0.0_real64; state%grid%dy=0.0_real64
    state%grid%dp=0.0_real64; state%grid%cell_measure=0.0_real64

    CALL initialize_field(state%pressure,nx,ny,nz,valid_time,'Pa')
    CALL initialize_field(state%temperature,nx,ny,nz,valid_time,'K')
    CALL initialize_field(state%vapor,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%u,nx,ny,nz,valid_time,'m s-1')
    CALL initialize_field(state%v,nx,ny,nz,valid_time,'m s-1')
    CALL initialize_field(state%omega,nx,ny,nz,valid_time,'Pa s-1')
    CALL initialize_field(state%omega_target,nx,ny,nz,valid_time,'Pa s-1')
    CALL initialize_field(state%geopotential,nx,ny,nz,valid_time,'m2 s-2')
    CALL initialize_field(state%cloud_fraction,nx,ny,nz,valid_time,'1')
    CALL initialize_field(state%radar_reflectivity,nx,ny,nz,valid_time,'dBZ')
    CALL initialize_integer_field(state%cloud_type,nx,ny,nz,valid_time, &
                                  'cloud_type_v1')
    CALL initialize_integer_field(state%precipitation_phase,nx,ny,nz,valid_time, &
                                  'precipitation_phase_v1')
    CALL initialize_integer_field(state%lightning_support,nx,ny,nz,valid_time, &
                                  'binary_v1')
    CALL initialize_field(state%cloud_water,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%cloud_ice,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%rain,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%snow,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%graupel,nx,ny,nz,valid_time,'kg kg-1 dryair')
    CALL initialize_field(state%vt_z_mean,nx,ny,nz,valid_time,'m s-1')
    CALL initialize_field(state%vt_z_sigma,nx,ny,nz,valid_time,'m s-1')
    CALL initialize_field(state%surface_pressure,nx,ny,valid_time,'Pa')
    CALL initialize_field(state%surface_temperature,nx,ny,valid_time,'K')
    CALL initialize_field(state%latitude,nx,ny,valid_time,'degree_north')
    CALL initialize_field(state%omega_top_boundary,nx,ny,valid_time,'Pa s-1')
    CALL initialize_field(state%omega_bottom_boundary,nx,ny,valid_time,'Pa s-1')
    ALLOCATE(state%obs_support(nx,ny,nz),state%hydro_support(nx,ny,nz), &
             state%balance_beta(nx,ny,nz))
    state%obs_support=0_int32; state%hydro_support=0_int32
    state%balance_beta=0.0_real32
    status=STATUS_OK
  END SUBROUTINE initialize_cloud_bal_state

  SUBROUTINE initialize_stage_result(result,nx,ny,nz,status,reason)
    TYPE(stage_result), INTENT(OUT) :: result
    INTEGER, INTENT(IN) :: nx,ny,nz,status,reason
    ALLOCATE(result%changed(nx,ny,nz))
    result%changed=.FALSE.
    result%status=status
    result%reason_code=reason
  END SUBROUTINE initialize_stage_result

  SUBROUTINE read_canonical_state(input_spec,state_out,result)
    TYPE(canonical_input_spec), INTENT(IN) :: input_spec
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    INTEGER :: status,reason,nx,ny,nz

    nx=0; ny=0; nz=0
    IF (.NOT. ALLOCATED(input_spec%supplied_state)) THEN
      CALL initialize_stage_result(result,0,0,0,STATUS_FAILED,REASON_METADATA)
      RETURN
    END IF
    nx=input_spec%supplied_state%grid%nx
    ny=input_spec%supplied_state%grid%ny
    nz=input_spec%supplied_state%grid%nz
    CALL validate_canonical_state(input_spec%supplied_state,.FALSE.,.FALSE., &
                                  status,reason)
    CALL initialize_stage_result(result,MAX(0,nx),MAX(0,ny),MAX(0,nz),status,reason)
    IF (status == STATUS_FAILED) RETURN
    state_out=input_spec%supplied_state
  END SUBROUTINE read_canonical_state

  SUBROUTINE validate_canonical_state(state,require_cloud,require_hydro,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    LOGICAL, INTENT(IN) :: require_cloud,require_hydro
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: field_status,nx,ny,nz
    INTEGER(int64) :: valid_time

    status=STATUS_FAILED; reason=REASON_SHAPE
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (state%schema_version /= CLOUD_BAL_SCHEMA_VERSION .OR. &
        nx < 1 .OR. ny < 1 .OR. nz < 1 .OR. LEN_TRIM(state%grid%grid_id) == 0) RETURN
    IF (.NOT. grid_arrays_valid(state%grid)) RETURN
    valid_time=state%pressure%valid_time
    status=STATUS_OK; reason=REASON_NONE

    CALL require_real_field(state%pressure,nx,ny,nz,valid_time,'Pa', &
                            100.0_real32,120000.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_real_field(state%temperature,nx,ny,nz,valid_time,'K', &
                            150.0_real32,350.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_real_field(state%vapor,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                            0.0_real32,0.2_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_real_field(state%u,nx,ny,nz,valid_time,'m s-1', &
                            -200.0_real32,200.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_real_field(state%v,nx,ny,nz,valid_time,'m s-1', &
                            -200.0_real32,200.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_real_field(state%omega,nx,ny,nz,valid_time,'Pa s-1', &
                            -100.0_real32,100.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    IF (.NOT.field3d_shape_metadata_ok(state%omega_target,nx,ny,nz,valid_time, &
                                       'Pa s-1')) THEN
      status=STATUS_FAILED; reason=REASON_METADATA; RETURN
    END IF
    IF (ANY(state%omega_target%quality<0_int32) .OR. &
        ANY(state%omega_target%source<0_int32) .OR. &
        ANY(state%omega_target%valid .AND. &
            .NOT.ieee_is_finite(state%omega_target%value))) THEN
      status=STATUS_FAILED; reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(state%omega_target%valid .AND. &
            ABS(state%omega_target%value)>100.0_real32)) THEN
      status=STATUS_FAILED; reason=REASON_RANGE; RETURN
    END IF

    CALL require_surface_field(state%surface_pressure,nx,ny,valid_time,'Pa', &
                               100.0_real32,120000.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    CALL require_surface_field(state%surface_temperature,nx,ny,valid_time,'K', &
                               150.0_real32,350.0_real32,field_status,reason)
    CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN

    IF (.NOT. support_arrays_valid(state,nx,ny,nz)) THEN
      status=STATUS_FAILED; reason=REASON_SHAPE; RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(state%balance_beta)) .OR. &
        ANY(state%balance_beta < 0.0_real32) .OR. &
        ANY(state%balance_beta > 1.0_real32)) THEN
      status=STATUS_FAILED; reason=REASON_RANGE; RETURN
    END IF

    IF (require_cloud) THEN
      CALL require_real_field(state%cloud_fraction,nx,ny,nz,valid_time,'1', &
                              0.0_real32,1.0_real32,field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      CALL require_integer_field(state%cloud_type,nx,ny,nz,valid_time, &
                                 'cloud_type_v1',field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      IF (ANY(state%cloud_type%valid .AND. &
              (state%cloud_type%value<0_int32 .OR. &
               state%cloud_type%value>11_int32))) THEN
        status=STATUS_FAILED; reason=REASON_RANGE; RETURN
      END IF
    END IF
    IF (require_hydro) THEN
      CALL require_real_field(state%cloud_water,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                              0.0_real32,HUGE(1.0_real32),field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      CALL require_real_field(state%cloud_ice,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                              0.0_real32,HUGE(1.0_real32),field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      CALL require_real_field(state%rain,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                              0.0_real32,HUGE(1.0_real32),field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      CALL require_real_field(state%snow,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                              0.0_real32,HUGE(1.0_real32),field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
      CALL require_real_field(state%graupel,nx,ny,nz,valid_time,'kg kg-1 dryair', &
                              0.0_real32,HUGE(1.0_real32),field_status,reason)
      CALL merge_status(status,field_status); IF (field_status==STATUS_FAILED) RETURN
    END IF
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time, &
                                   field_status,reason)
    CALL merge_status(status,field_status)
  END SUBROUTINE validate_canonical_state

  SUBROUTINE validate_los_observations(los,nx,ny,nz,valid_time,status,reason)
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nr,i,j,k,r
    REAL(real64) :: beam_norm

    status=STATUS_FAILED; reason=REASON_RADAR_CONTRACT
    nr=los%nradar
    IF (.NOT. los%is_present) THEN
      IF (nr /= 0 .OR. los_core_allocated(los)) RETURN
      status=STATUS_OK; reason=REASON_NONE; RETURN
    END IF
    IF (nr < 1) RETURN
    IF (.NOT. field4d_shape_metadata_ok(los%vrad,nx,ny,nz,nr,valid_time,'m s-1') .OR. &
        .NOT. field4d_shape_metadata_ok(los%nyquist,nx,ny,nz,nr,valid_time,'m s-1') .OR. &
        .NOT. field4d_shape_metadata_ok(los%sigma_vrad,nx,ny,nz,nr,valid_time,'m s-1')) RETURN
    IF (.NOT. ALLOCATED(los%beam) .OR. &
        ANY(SHAPE(los%beam) /= (/nx,ny,nz,nr,3/))) RETURN
    IF (.NOT. ALLOCATED(los%observation_id_hi) .OR. &
        .NOT. ALLOCATED(los%observation_id_lo) .OR. .NOT. ALLOCATED(los%usage) .OR. &
        .NOT. ALLOCATED(los%los_support)) RETURN
    IF (ANY(SHAPE(los%observation_id_hi) /= (/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(los%observation_id_lo) /= (/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(los%usage) /= (/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(los%los_support) /= (/nx,ny,nz,nr/))) RETURN
    IF (.NOT. radar_vectors_allocated(los,nr)) RETURN
    IF (.NOT. ALLOCATED(los%geometry_condition) .OR. &
        .NOT. ALLOCATED(los%geometry_rank)) RETURN
    IF (ANY(SHAPE(los%geometry_condition) /= (/nx,ny,nz/)) .OR. &
        ANY(SHAPE(los%geometry_rank) /= (/nx,ny,nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(los%beam)) .OR. &
        ANY(.NOT.ieee_is_finite(los%geometry_condition))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(los%usage < LOS_REJECTED) .OR. ANY(los%usage > LOS_HELD_OUT) .OR. &
        ANY(los%los_support < 0_int32) .OR. ANY(los%los_support > 1_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (ANY(los%vrad%quality<0_int32) .OR. ANY(los%vrad%source<0_int32) .OR. &
        ANY(los%nyquist%quality<0_int32) .OR. ANY(los%nyquist%source<0_int32) .OR. &
        ANY(los%sigma_vrad%quality<0_int32) .OR. &
        ANY(los%sigma_vrad%source<0_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (ANY(los%vrad%valid .AND. .NOT.ieee_is_finite(los%vrad%value))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(los%nyquist%valid .AND. (los%nyquist%value <= 0.0_real32 .OR. &
                                    .NOT.ieee_is_finite(los%nyquist%value))) .OR. &
        ANY(los%sigma_vrad%valid .AND. (los%sigma_vrad%value <= 0.0_real32 .OR. &
                                       .NOT.ieee_is_finite(los%sigma_vrad%value)))) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (ANY(los%radar_id<=0_int32) .OR. ANY(los%observation_time<=0_int64) .OR. &
        ANY(.NOT.ieee_is_finite(los%site_lat)) .OR. &
        ANY(.NOT.ieee_is_finite(los%site_lon)) .OR. &
        ANY(.NOT.ieee_is_finite(los%site_height)) .OR. &
        ANY(.NOT.ieee_is_finite(los%wavelength)) .OR. &
        ANY(ABS(los%site_lat)>90.0_real64) .OR. &
        ANY(los%site_lon< -180.0_real64) .OR. ANY(los%site_lon>360.0_real64) .OR. &
        ANY(los%site_height< -500.0_real64) .OR. &
        ANY(los%site_height>10000.0_real64) .OR. &
        ANY(los%wavelength<0.08_real64) .OR. ANY(los%wavelength>0.12_real64) .OR. &
        ANY(los%geometry_condition<1.0_real32) .OR. &
        ANY(los%geometry_rank<0_int32) .OR. ANY(los%geometry_rank>3_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    DO r=1,nr; DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF ((los%los_support(i,j,k,r)==1_int32) .NEQV. &
          (los%usage(i,j,k,r)/=LOS_REJECTED)) THEN
        reason=REASON_RADAR_CONTRACT; RETURN
      END IF
      IF (los%los_support(i,j,k,r)/=1_int32) CYCLE
      IF (.NOT.los%vrad%valid(i,j,k,r) .OR. &
          .NOT.los%nyquist%valid(i,j,k,r) .OR. &
          .NOT.los%sigma_vrad%valid(i,j,k,r)) THEN
        reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      IF (IAND(los%vrad%quality(i,j,k,r),IOR(QUALITY_RAW_MISSING, &
          IOR(QUALITY_QC_REJECTED,QUALITY_TIME_MISMATCH)))/=0_int32 .OR. &
          IAND(los%nyquist%quality(i,j,k,r),IOR(QUALITY_RAW_MISSING, &
          IOR(QUALITY_QC_REJECTED,QUALITY_TIME_MISMATCH)))/=0_int32 .OR. &
          IAND(los%sigma_vrad%quality(i,j,k,r),IOR(QUALITY_RAW_MISSING, &
          IOR(QUALITY_QC_REJECTED,QUALITY_TIME_MISMATCH)))/=0_int32 .OR. &
          IAND(los%vrad%source(i,j,k,r),SOURCE_RADAR_VRAD)==0_int32) THEN
        reason=REASON_RADAR_CONTRACT; RETURN
      END IF
      IF (los%observation_id_hi(i,j,k,r)==0_int64 .AND. &
          los%observation_id_lo(i,j,k,r)==0_int64) THEN
        reason=REASON_RADAR_CONTRACT; RETURN
      END IF
      beam_norm=SQRT(SUM(REAL(los%beam(i,j,k,r,:),real64)**2))
      IF (ABS(beam_norm-1.0_real64)>1.0e-3_real64) THEN
        reason=REASON_RANGE; RETURN
      END IF
    END DO; END DO; END DO; END DO
    IF (los%has_colocated_dbz) THEN
      IF (.NOT. field4d_shape_metadata_ok(los%colocated_dbz,nx,ny,nz,nr, &
                                          valid_time,'dBZ')) RETURN
    END IF
    IF (los%has_spectrum_width) THEN
      IF (.NOT. field4d_shape_metadata_ok(los%spectrum_width,nx,ny,nz,nr, &
                                          valid_time,'m s-1')) RETURN
    END IF
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_los_observations

  SUBROUTINE commit_candidate(state_in,candidate,candidate_result,state_out,result)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate
    TYPE(stage_result), INTENT(IN) :: candidate_result
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result

    IF (candidate_result%status == STATUS_OK) THEN
      state_out=candidate
    ELSE
      state_out=state_in
    END IF
    result=candidate_result
  END SUBROUTINE commit_candidate

  SUBROUTINE reject_candidate(state_in,state_out,result,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    INTEGER, INTENT(IN) :: status,reason
    state_out=state_in
    CALL initialize_stage_result(result,MAX(0,state_in%grid%nx), &
                                 MAX(0,state_in%grid%ny), &
                                 MAX(0,state_in%grid%nz),status,reason)
  END SUBROUTINE reject_candidate

  SUBROUTINE omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    REAL(real32), INTENT(IN) :: omega(:,:,:),pressure(:,:,:),temperature(:,:,:), &
                                vapor(:,:,:)
    LOGICAL, INTENT(IN) :: valid(:,:,:)
    REAL(real32), INTENT(OUT) :: w(:,:,:)
    LOGICAL, INTENT(OUT) :: w_valid(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    REAL(real64) :: tv,rho

    w=0.0_real32; w_valid=.FALSE.; status=STATUS_FAILED
    IF (.NOT. same_shape_3d(omega,pressure,temperature,vapor,valid,w,w_valid)) RETURN
    DO k=1,SIZE(omega,3); DO j=1,SIZE(omega,2); DO i=1,SIZE(omega,1)
      IF (.NOT.valid(i,j,k)) CYCLE
      IF (.NOT.ieee_is_finite(omega(i,j,k)) .OR. &
          .NOT.ieee_is_finite(pressure(i,j,k)) .OR. pressure(i,j,k)<=100.0_real32 .OR. &
          .NOT.ieee_is_finite(temperature(i,j,k)) .OR. temperature(i,j,k)<=0.0_real32 .OR. &
          .NOT.ieee_is_finite(vapor(i,j,k)) .OR. vapor(i,j,k)<0.0_real32) RETURN
      tv=REAL(temperature(i,j,k),real64)*(1.0_real64+0.61_real64*REAL(vapor(i,j,k),real64))
      rho=REAL(pressure(i,j,k),real64)/(RD_AIR*tv)
      w(i,j,k)=REAL(-REAL(omega(i,j,k),real64)/(rho*GRAVITY),real32)
      IF (.NOT.ieee_is_finite(w(i,j,k))) RETURN
      w_valid(i,j,k)=.TRUE.
    END DO; END DO; END DO
    status=STATUS_OK
  END SUBROUTINE omega_to_w

  SUBROUTINE w_to_omega(w,pressure,temperature,vapor,valid,omega,omega_valid,status)
    REAL(real32), INTENT(IN) :: w(:,:,:),pressure(:,:,:),temperature(:,:,:), &
                                vapor(:,:,:)
    LOGICAL, INTENT(IN) :: valid(:,:,:)
    REAL(real32), INTENT(OUT) :: omega(:,:,:)
    LOGICAL, INTENT(OUT) :: omega_valid(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    REAL(real64) :: tv,rho

    omega=0.0_real32; omega_valid=.FALSE.; status=STATUS_FAILED
    IF (.NOT. same_shape_3d(w,pressure,temperature,vapor,valid,omega,omega_valid)) RETURN
    DO k=1,SIZE(w,3); DO j=1,SIZE(w,2); DO i=1,SIZE(w,1)
      IF (.NOT.valid(i,j,k)) CYCLE
      IF (.NOT.ieee_is_finite(w(i,j,k)) .OR. &
          .NOT.ieee_is_finite(pressure(i,j,k)) .OR. pressure(i,j,k)<=100.0_real32 .OR. &
          .NOT.ieee_is_finite(temperature(i,j,k)) .OR. temperature(i,j,k)<=0.0_real32 .OR. &
          .NOT.ieee_is_finite(vapor(i,j,k)) .OR. vapor(i,j,k)<0.0_real32) RETURN
      tv=REAL(temperature(i,j,k),real64)*(1.0_real64+0.61_real64*REAL(vapor(i,j,k),real64))
      rho=REAL(pressure(i,j,k),real64)/(RD_AIR*tv)
      omega(i,j,k)=REAL(-rho*GRAVITY*REAL(w(i,j,k),real64),real32)
      IF (.NOT.ieee_is_finite(omega(i,j,k))) RETURN
      omega_valid(i,j,k)=.TRUE.
    END DO; END DO; END DO
    status=STATUS_OK
  END SUBROUTINE w_to_omega

  PURE REAL(real64) FUNCTION field_coverage(field)
    TYPE(field3d), INTENT(IN) :: field
    field_coverage=0.0_real64
    IF (.NOT.ALLOCATED(field%valid)) RETURN
    IF (SIZE(field%valid)>0) field_coverage=REAL(COUNT(field%valid),real64)/ &
                                             REAL(SIZE(field%valid),real64)
  END FUNCTION field_coverage

  PURE LOGICAL FUNCTION pipeline_mode_valid(mode)
    INTEGER, INTENT(IN) :: mode
    pipeline_mode_valid=mode==MODE_OFF .OR. mode==MODE_SHADOW
  END FUNCTION pipeline_mode_valid

  SUBROUTINE require_real_field(field,nx,ny,nz,valid_time,unit,lower,upper,status,reason)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    REAL(real32), INTENT(IN) :: lower,upper
    INTEGER, INTENT(OUT) :: status,reason

    status=STATUS_FAILED; reason=REASON_SHAPE
    IF (.NOT.field3d_shape_metadata_ok(field,nx,ny,nz,valid_time,unit)) RETURN
    IF (ANY(field%quality<0_int32) .OR. ANY(field%source<0_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (COUNT(field%valid)==0) THEN
      reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    IF (ANY(field%valid .AND. .NOT.ieee_is_finite(field%value))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(field%valid .AND. (field%value<lower .OR. field%value>upper))) THEN
      reason=REASON_RANGE; RETURN
    END IF
    reason=REASON_NONE
    IF (COUNT(field%valid)==SIZE(field%valid)) THEN
      status=STATUS_OK
    ELSE
      status=STATUS_DEGRADED
    END IF
  END SUBROUTINE require_real_field

  SUBROUTINE require_surface_field(field,nx,ny,valid_time,unit,lower,upper,status,reason)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    REAL(real32), INTENT(IN) :: lower,upper
    INTEGER, INTENT(OUT) :: status,reason

    status=STATUS_FAILED; reason=REASON_SHAPE
    IF (.NOT.field2d_shape_metadata_ok(field,nx,ny,valid_time,unit)) RETURN
    IF (ANY(field%quality<0_int32) .OR. ANY(field%source<0_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (COUNT(field%valid)==0) THEN; reason=REASON_REQUIRED_COVERAGE; RETURN; END IF
    IF (ANY(field%valid .AND. .NOT.ieee_is_finite(field%value))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(field%valid .AND. (field%value<lower .OR. field%value>upper))) THEN
      reason=REASON_RANGE; RETURN
    END IF
    reason=REASON_NONE
    IF (COUNT(field%valid)==SIZE(field%valid)) THEN
      status=STATUS_OK
    ELSE
      status=STATUS_DEGRADED
    END IF
  END SUBROUTINE require_surface_field

  SUBROUTINE require_integer_field(field,nx,ny,nz,valid_time,code_table,status,reason)
    TYPE(integer_field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: code_table
    INTEGER, INTENT(OUT) :: status,reason

    status=STATUS_FAILED; reason=REASON_SHAPE
    IF (.NOT.integer_field_shape_metadata_ok(field,nx,ny,nz,valid_time,code_table)) RETURN
    IF (COUNT(field%valid)==0) THEN; reason=REASON_REQUIRED_COVERAGE; RETURN; END IF
    IF (ANY(field%quality<0_int32) .OR. ANY(field%source<0_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    reason=REASON_NONE
    IF (COUNT(field%valid)==SIZE(field%valid)) THEN
      status=STATUS_OK
    ELSE
      status=STATUS_DEGRADED
    END IF
  END SUBROUTINE require_integer_field

  PURE LOGICAL FUNCTION grid_arrays_valid(grid)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real64), ALLOCATABLE :: expected_mass(:,:,:)
    grid_arrays_valid=.FALSE.
    IF (.NOT.ALLOCATED(grid%dx) .OR. .NOT.ALLOCATED(grid%dy) .OR. &
        .NOT.ALLOCATED(grid%dp) .OR. .NOT.ALLOCATED(grid%cell_measure)) RETURN
    IF (ANY(SHAPE(grid%dx)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%dy)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%dp)/=(/grid%nx,grid%ny,grid%nz/)) .OR. &
        ANY(SHAPE(grid%cell_measure)/=(/grid%nx,grid%ny,grid%nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(grid%dx)) .OR. ANY(grid%dx<=0.0_real64) .OR. &
        ANY(.NOT.ieee_is_finite(grid%dy)) .OR. ANY(grid%dy<=0.0_real64) .OR. &
        ANY(.NOT.ieee_is_finite(grid%dp)) .OR. ANY(grid%dp<=0.0_real64) .OR. &
        ANY(.NOT.ieee_is_finite(grid%cell_measure)) .OR. &
        ANY(grid%cell_measure<=0.0_real64)) RETURN
    expected_mass=SPREAD(grid%dx*grid%dy,3,grid%nz)*grid%dp/GRAVITY
    IF (ANY(ABS(grid%cell_measure-expected_mass)> &
            1.0e-10_real64*MAX(expected_mass,1.0_real64))) RETURN
    grid_arrays_valid=.TRUE.
  END FUNCTION grid_arrays_valid

  PURE LOGICAL FUNCTION support_arrays_valid(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    support_arrays_valid=.FALSE.
    IF (.NOT.ALLOCATED(state%obs_support) .OR. &
        .NOT.ALLOCATED(state%hydro_support) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%obs_support)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%hydro_support)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%balance_beta)/=(/nx,ny,nz/))) RETURN
    IF (ANY(state%obs_support<0_int32) .OR. ANY(state%obs_support>1_int32) .OR. &
        ANY(state%hydro_support<0_int32) .OR. ANY(state%hydro_support>1_int32)) RETURN
    support_arrays_valid=.TRUE.
  END FUNCTION support_arrays_valid

  PURE LOGICAL FUNCTION field3d_shape_metadata_ok(field,nx,ny,nz,valid_time,unit)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field3d_shape_metadata_ok=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%valid)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%quality)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%source)/=(/nx,ny,nz/))) RETURN
    field3d_shape_metadata_ok=field%valid_time==valid_time .AND. &
                              TRIM(field%unit)==TRIM(unit)
  END FUNCTION field3d_shape_metadata_ok

  PURE LOGICAL FUNCTION field2d_shape_metadata_ok(field,nx,ny,valid_time,unit)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field2d_shape_metadata_ok=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(field%valid)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(field%quality)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(field%source)/=(/nx,ny/))) RETURN
    field2d_shape_metadata_ok=field%valid_time==valid_time .AND. &
                              TRIM(field%unit)==TRIM(unit)
  END FUNCTION field2d_shape_metadata_ok

  PURE LOGICAL FUNCTION field4d_shape_metadata_ok(field,nx,ny,nz,nr,valid_time,unit)
    TYPE(field4d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz,nr
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field4d_shape_metadata_ok=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=(/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(field%valid)/=(/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(field%quality)/=(/nx,ny,nz,nr/)) .OR. &
        ANY(SHAPE(field%source)/=(/nx,ny,nz,nr/))) RETURN
    field4d_shape_metadata_ok=field%valid_time==valid_time .AND. &
                              TRIM(field%unit)==TRIM(unit)
  END FUNCTION field4d_shape_metadata_ok

  PURE LOGICAL FUNCTION integer_field_shape_metadata_ok(field,nx,ny,nz,valid_time,code_table)
    TYPE(integer_field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: code_table
    integer_field_shape_metadata_ok=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%valid)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%quality)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(field%source)/=(/nx,ny,nz/))) RETURN
    integer_field_shape_metadata_ok=field%valid_time==valid_time .AND. &
                                    TRIM(field%code_table)==TRIM(code_table)
  END FUNCTION integer_field_shape_metadata_ok

  PURE LOGICAL FUNCTION los_core_allocated(los)
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    los_core_allocated=ALLOCATED(los%vrad%value) .OR. ALLOCATED(los%nyquist%value) .OR. &
      ALLOCATED(los%sigma_vrad%value) .OR. ALLOCATED(los%beam) .OR. &
      ALLOCATED(los%observation_id_hi) .OR. ALLOCATED(los%observation_id_lo) .OR. &
      ALLOCATED(los%usage) .OR. ALLOCATED(los%radar_id) .OR. &
      ALLOCATED(los%observation_time) .OR. ALLOCATED(los%site_lat) .OR. &
      ALLOCATED(los%site_lon) .OR. ALLOCATED(los%site_height) .OR. &
      ALLOCATED(los%wavelength) .OR. ALLOCATED(los%los_support) .OR. &
      ALLOCATED(los%geometry_condition) .OR. ALLOCATED(los%geometry_rank) .OR. &
      ALLOCATED(los%colocated_dbz%value) .OR. &
      ALLOCATED(los%spectrum_width%value) .OR. los%has_colocated_dbz .OR. &
      los%has_spectrum_width
  END FUNCTION los_core_allocated

  PURE LOGICAL FUNCTION radar_vectors_allocated(los,nr)
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    INTEGER, INTENT(IN) :: nr
    radar_vectors_allocated=.FALSE.
    IF (.NOT.ALLOCATED(los%radar_id) .OR. .NOT.ALLOCATED(los%observation_time) .OR. &
        .NOT.ALLOCATED(los%site_lat) .OR. .NOT.ALLOCATED(los%site_lon) .OR. &
        .NOT.ALLOCATED(los%site_height) .OR. .NOT.ALLOCATED(los%wavelength)) RETURN
    IF (SIZE(los%radar_id)/=nr .OR. SIZE(los%observation_time)/=nr .OR. &
        SIZE(los%site_lat)/=nr .OR. SIZE(los%site_lon)/=nr .OR. &
        SIZE(los%site_height)/=nr .OR. SIZE(los%wavelength)/=nr) RETURN
    IF (ANY(.NOT.ieee_is_finite(los%site_lat)) .OR. &
        ANY(.NOT.ieee_is_finite(los%site_lon)) .OR. &
        ANY(.NOT.ieee_is_finite(los%site_height)) .OR. &
        ANY(.NOT.ieee_is_finite(los%wavelength)) .OR. &
        ANY(los%wavelength<=0.0_real64)) RETURN
    radar_vectors_allocated=.TRUE.
  END FUNCTION radar_vectors_allocated

  PURE LOGICAL FUNCTION same_shape_3d(a,b,c,d,mask,out,outmask)
    REAL(real32), INTENT(IN) :: a(:,:,:),b(:,:,:),c(:,:,:),d(:,:,:)
    LOGICAL, INTENT(IN) :: mask(:,:,:)
    REAL(real32), INTENT(IN) :: out(:,:,:)
    LOGICAL, INTENT(IN) :: outmask(:,:,:)
    INTEGER :: target(3)
    target=SHAPE(a)
    same_shape_3d=ALL(SHAPE(b)==target) .AND. ALL(SHAPE(c)==target) .AND. &
                  ALL(SHAPE(d)==target) .AND. ALL(SHAPE(mask)==target) .AND. &
                  ALL(SHAPE(out)==target) .AND. ALL(SHAPE(outmask)==target)
  END FUNCTION same_shape_3d

  PURE SUBROUTINE merge_status(overall,item)
    INTEGER, INTENT(INOUT) :: overall
    INTEGER, INTENT(IN) :: item
    IF (item<overall) overall=item
  END SUBROUTINE merge_status

END MODULE cloud_bal_state
