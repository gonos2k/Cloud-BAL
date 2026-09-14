! Thin NetCDF adapter for the prepared KLAPS real-data SHADOW cases.
!
! The adapter owns every legacy convention: file layout, fill values,
! specific-humidity conversion and the top-to-bottom file ordering.  Physics
! receives only the canonical bottom-to-top state from cloud_bal_state.
MODULE cloud_bal_real_netcdf
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: column_changed_mask,column_config_valid, &
    saturation_adjust_pressure_state,water_phase_budget,pressure_analysis_budget,account_pressure_analysis, &
    apply_pressure_hydrostatic_increment,PHASE_UNKNOWN,PHASE_RAIN,PHASE_SNOW, &
    PHASE_FREEZING_RAIN,PHASE_SLEET,validate_optional_cloud_pair,precipitation_phase_contract_valid
  USE cloud_bal_balance_operator, ONLY: balance_beta_active,boundary_contract_valid, &
    physical_boundary_contract_valid,model_boundary_increment_contract_valid, &
    TARGET_AUTHORITY_OBSERVATIONAL,BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL, &
    TARGET_AUTHORITY_MODEL_DYNAMICS,target_is_resolved, &
    balance_operator_type,build_balance_operator,state_dry_air_mass_flux_divergence, &
    state_continuity_residual,assess_pressure_geostrophic_change
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER :: NX=235,NY=283,NZ=22
  INTEGER, PARAMETER :: TIME_POLICY_ANALYSIS=1,TIME_POLICY_FORECAST=2
  REAL(real64), PARAMETER :: TIME_TOLERANCE_SECONDS=0.5_real64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  REAL(real64), PARAMETER :: RD_AIR=287.05_real64
  REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
  REAL(real32), PARAMETER :: RAW_MISSING_LIMIT=1.0e30_real32
  REAL(real32), PARAMETER :: MINIMUM_USABLE_DBZ=0.0_real32
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_CONTRACT_V1= &
    'pressure_hydrostatic_increment_v1'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_CONTRACT_SURFACE= &
    'pressure_hydrostatic_surface_increment_v1'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_REFERENCE_V1= &
    'lowest_represented_center'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_REFERENCE_SURFACE= &
    'fixed_terrain_surface'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE= &
    'WPS_SURFACE_ZERO_CONDENSATE'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTR= &
    'pressure_geopotential_surface_condensate_convention'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_DRY_AIR_FLUX_CONTRACT_FIXED= &
    'pressure_fixed_dry_advection_v1'
  CHARACTER(LEN=*), PARAMETER :: PRESSURE_DRY_AIR_FLUX_CONTRACT_STATE= &
    'pressure_state_geometry_dry_advection_v1'

  PUBLIC :: read_lco_evidence
  PUBLIC :: read_real_shadow_state
  PUBLIC :: read_model_omega_increment
  PUBLIC :: set_real_numerical_test_boundaries
  PUBLIC :: write_shadow_diagnostics
  PUBLIC :: validate_shadow_write_contract
  PUBLIC :: pipeline_result_replays
  PUBLIC :: put_pressure_transition_extension
  PUBLIC :: put_radar_reconstruction_inputs

CONTAINS
  SUBROUTINE read_model_omega_increment(path,state,longitude,status)
    ! Read one externally validated paired-model increment without partially
    ! mutating the canonical state.  omega_target is an absolute value formed
    ! from the unchanged background omega plus delta_omega on target_mask;
    ! coverage_mask also includes any explicitly supplied closed halo.
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real32), INTENT(IN) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx,ny,nz,ncid,state_status,state_reason
    INTEGER(int64) :: payload_time
    CHARACTER(LEN=128) :: text
    REAL(real32), ALLOCATABLE :: delta(:,:,:),pressure(:,:,:),lat(:,:),lon(:,:)
    INTEGER(int32), ALLOCATABLE :: target_mask(:,:,:),coverage_mask(:,:,:)
    LOGICAL, ALLOCATABLE :: target(:,:,:),coverage(:,:,:)
    TYPE(cloud_bal_state_type) :: candidate
    INTEGER :: i,j,k
    REAL(real64) :: target_value

    status=STATUS_FAILED
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    IF (ANY(SHAPE(longitude)/=(/nx,ny/))) RETURN
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) RETURN
    IF (.NOT.model_target_coverage_contract_valid(state)) RETURN
    IF (TRIM(state%grid%grid_id)/='NE57_LAPS_PRESSURE') RETURN
    IF (ANY(.NOT.ieee_is_finite(longitude))) RETURN
    IF (.NOT.nc_ok(nf90_open(TRIM(path),NF90_NOWRITE,ncid))) RETURN
    IF (.NOT.model_payload_dimensions_valid(ncid,nx,ny,nz)) GOTO 900
    IF (.NOT.read_model_int64_attribute(ncid,'valid_time_epoch',payload_time)) GOTO 900
    IF (payload_time/=state%pressure%valid_time) GOTO 900
    IF (.NOT.read_model_text_attribute(ncid,'grid_id',text)) GOTO 900
    IF (TRIM(text)/='NE57_LAPS_PRESSURE') GOTO 900
    IF (.NOT.read_model_text_attribute(ncid,'wind_coordinate',text)) GOTO 900
    IF (TRIM(text)/='GRID_RELATIVE') GOTO 900
    IF (.NOT.read_model_text_attribute(ncid,'target_origin',text)) GOTO 900
    IF (TRIM(text)/='MODEL_DYNAMICS') GOTO 900
    IF (.NOT.read_model_text_attribute(ncid,'boundary_mode',text)) GOTO 900
    IF (TRIM(text)/='ZERO_INCREMENT_PRESERVE_BASELINE') GOTO 900
    ALLOCATE(delta(nx,ny,nz),pressure(nx,ny,nz),lat(nx,ny),lon(nx,ny), &
             target_mask(nx,ny,nz),coverage_mask(nx,ny,nz), &
             target(nx,ny,nz),coverage(nx,ny,nz))
    IF (.NOT.read_model_real3(ncid,'delta_omega','Pa s-1',delta)) GOTO 900
    IF (.NOT.read_model_real3(ncid,'pressure','Pa',pressure)) GOTO 900
    IF (.NOT.read_model_real2(ncid,'latitude','degree_north',lat)) GOTO 900
    IF (.NOT.read_model_real2(ncid,'longitude','degree_east',lon)) GOTO 900
    IF (.NOT.read_model_int3(ncid,'target_mask',target_mask)) GOTO 900
    IF (.NOT.read_model_int3(ncid,'coverage_mask',coverage_mask)) GOTO 900
    IF (.NOT.nc_ok(nf90_close(ncid))) THEN
      ncid=-1
      RETURN
    END IF
    ncid=-1
    IF (ANY(pressure/=state%pressure%value)) RETURN
    IF (ANY(lat/=state%latitude%value) .OR. ANY(lon/=longitude)) RETURN
    IF (ANY((target_mask/=0_int32) .AND. (target_mask/=1_int32)) .OR. &
        ANY((coverage_mask/=0_int32) .AND. (coverage_mask/=1_int32))) RETURN
    target=target_mask==1_int32
    coverage=coverage_mask==1_int32
    IF (.NOT.ANY(target) .OR. ANY(target .AND. .NOT.coverage) .OR. &
        ANY(coverage .AND. .NOT.state%above_ground)) RETURN
    candidate=state
    candidate%model_target_coverage=coverage
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (target(i,j,k) .AND. .NOT.state%above_ground(i,j,k)) RETURN
      IF (target(i,j,k) .AND. .NOT.model_target_level_is_interior(candidate,i,j,k)) RETURN
      IF (target(i,j,k)) THEN
        target_value=REAL(state%omega%value(i,j,k),real64)+REAL(delta(i,j,k),real64)
        IF (.NOT.ieee_is_finite(target_value) .OR. ABS(target_value)>100.0_real64) RETURN
      END IF
    END DO; END DO; END DO
    candidate%omega_target%value=0.0_real32
    candidate%omega_target%valid=.FALSE.
    candidate%omega_target%quality=QUALITY_RAW_MISSING
    candidate%omega_target%source=0_int32
    WHERE(target)
      candidate%omega_target%value=REAL(REAL(state%omega%value,real64)+REAL(delta,real64),real32)
      candidate%omega_target%valid=.TRUE.
      candidate%omega_target%quality=0_int32
      candidate%omega_target%source=IOR(SOURCE_BACKGROUND_MODEL,SOURCE_DYNAMIC_TARGET)
    END WHERE
    ! Model authority has no empirical error field. Keep sigma explicitly
    ! missing so a stale observational uncertainty cannot be interpreted.
    candidate%omega_target_sigma%value=0.0_real32
    candidate%omega_target_sigma%valid=.FALSE.
    candidate%omega_target_sigma%quality=QUALITY_RAW_MISSING
    candidate%omega_target_sigma%source=0_int32
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) RETURN
    state=candidate
    status=STATUS_OK
    RETURN
900 CONTINUE
    CALL close_file(ncid)
  END SUBROUTINE read_model_omega_increment

  LOGICAL FUNCTION model_payload_dimensions_valid(ncid,nx,ny,nz)
    INTEGER, INTENT(IN) :: ncid,nx,ny,nz
    model_payload_dimensions_valid=dimension_is(ncid,'x',nx) .AND. &
      dimension_is(ncid,'y',ny) .AND. dimension_is(ncid,'z',nz)
  END FUNCTION model_payload_dimensions_valid

  LOGICAL FUNCTION read_model_int64_attribute(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER(int64), INTENT(OUT) :: value
    value=0_int64
    read_model_int64_attribute=nc_ok(nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),value))
  END FUNCTION read_model_int64_attribute

  LOGICAL FUNCTION read_model_text_attribute(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(OUT) :: value
    value=''
    read_model_text_attribute=nc_ok(nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),value))
  END FUNCTION read_model_text_attribute

  LOGICAL FUNCTION read_model_real3(ncid,name,unit,data)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit
    REAL(real32), INTENT(OUT) :: data(:,:,:)
    INTEGER :: varid
    read_model_real3=.FALSE.; data=0.0_real32
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=1) :: 'x','y','z']) .OR. &
        .NOT.variable_unit_is(ncid,varid,unit,unit)) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,data))) RETURN
    read_model_real3=ALL(ieee_is_finite(data))
  END FUNCTION read_model_real3

  LOGICAL FUNCTION read_model_real2(ncid,name,unit,data)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit
    REAL(real32), INTENT(OUT) :: data(:,:)
    INTEGER :: varid
    read_model_real2=.FALSE.; data=0.0_real32
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=1) :: 'x','y']) .OR. &
        .NOT.variable_unit_is(ncid,varid,unit,unit)) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,data))) RETURN
    read_model_real2=ALL(ieee_is_finite(data))
  END FUNCTION read_model_real2

  LOGICAL FUNCTION read_model_int3(ncid,name,data)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER(int32), INTENT(OUT) :: data(:,:,:)
    INTEGER :: varid
    read_model_int3=.FALSE.; data=0_int32
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_INT, &
        [CHARACTER(LEN=1) :: 'x','y','z'])) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,data))) RETURN
    read_model_int3=.TRUE.
  END FUNCTION read_model_int3

  SUBROUTINE read_lco_evidence(path,valid_time,state,evidence,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER(int64), INTENT(IN) :: valid_time
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(field3d), INTENT(OUT) :: evidence
    INTEGER, INTENT(OUT) :: status,reason
    REAL(real32), ALLOCATABLE :: raw(:,:,:)
    LOGICAL, ALLOCATABLE :: raw_valid(:,:,:)
    REAL(real64) :: levels(NZ),dx,dy
    INTEGER :: ncid,k,source_k,local_status

    status=STATUS_FAILED; reason=REASON_METADATA
    IF (state%grid%nx/=NX .OR. state%grid%ny/=NY .OR. state%grid%nz/=NZ) RETURN
    CALL open_case_file(path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                        ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    ALLOCATE(raw(NX,NY,NZ),raw_valid(NX,NY,NZ))
    CALL read_real3(ncid,'com','pascals/second','pa/s',raw,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN
    IF (ANY(dx/=state%grid%dx) .OR. ANY(dy/=state%grid%dy)) RETURN
    evidence=state%omega_target
    evidence%unit='Pa s-1'; evidence%valid_time=valid_time
    DO k=1,NZ
      source_k=NZ+1-k
      IF (ANY(state%pressure%value(:,:,k)/=REAL(levels(source_k)*100.0_real64,real32))) RETURN
      evidence%value(:,:,k)=0.0_real32
      WHERE(raw_valid(:,:,source_k)) evidence%value(:,:,k)=raw(:,:,source_k)
      CALL mark_real_field(evidence,k,raw_valid(:,:,source_k),SOURCE_CLOUD_ANALYSIS)
      WHERE(evidence%valid(:,:,k)) &
        evidence%quality(:,:,k)=IOR(evidence%quality(:,:,k),QUALITY_LEGACY_PROVENANCE)
    END DO
    ! COM remains separate legacy evidence, with no target or sigma assignment.
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_lco_evidence


  SUBROUTINE read_real_shadow_state(fua_path,fsf_path,lw3_path,vrz_path,vrt_path, &
                                    static_path,valid_time,state,longitude,status,reason, &
                                    lt1_path,lq3_path,lwc_path,lsx_path,retained_omega, &
                                    lcp_path,lty_path)
    CHARACTER(LEN=*), INTENT(IN) :: fua_path,fsf_path,lw3_path,vrz_path,vrt_path
    CHARACTER(LEN=*), INTENT(IN) :: static_path
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: lt1_path,lq3_path,lwc_path,lsx_path
    CHARACTER(LEN=*), OPTIONAL, INTENT(IN) :: lcp_path,lty_path
    INTEGER(int64), INTENT(IN) :: valid_time
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    TYPE(field3d), ALLOCATABLE, OPTIONAL, INTENT(OUT) :: retained_omega
    TYPE(field3d) :: omega_work
    REAL(real32), ALLOCATABLE, INTENT(OUT) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status,reason
    REAL(real32), ALLOCATABLE :: raw(:,:,:),surface(:,:),surface_vapor(:,:),tid(:,:,:), &
                                  topography(:,:)
    LOGICAL, ALLOCATABLE :: raw_valid(:,:,:),surface_valid(:,:),surface_vapor_valid(:,:), &
                            terrain_domain(:,:,:)
    LOGICAL, ALLOCATABLE :: latitude_valid(:,:),longitude_valid(:,:),topography_valid(:,:)
    REAL(real64) :: levels(NZ),dx,dy,forecast_reftime,file_reftime
    INTEGER :: ncid,k,source_k,local_status,mr_varid,rc,i,j,code
    INTEGER(int32) :: surface_source,thermo_source,hydro_source
    LOGICAL :: direct_products,processed_cloud,usable(NX,NY)

    status=STATUS_FAILED; reason=REASON_METADATA
    direct_products=PRESENT(lt1_path) .OR. PRESENT(lq3_path) .OR. &
                    PRESENT(lwc_path) .OR. PRESENT(lsx_path)
    IF (direct_products .AND. .NOT.(PRESENT(lt1_path) .AND. PRESENT(lq3_path) .AND. &
                                   PRESENT(lwc_path) .AND. PRESENT(lsx_path))) RETURN
    processed_cloud=PRESENT(lcp_path) .OR. PRESENT(lty_path)
    IF (processed_cloud .AND. .NOT.(PRESENT(lcp_path) .AND. PRESENT(lty_path))) RETURN
    surface_source=SOURCE_BACKGROUND_MODEL
    thermo_source=SOURCE_BACKGROUND_MODEL
    hydro_source=SOURCE_BACKGROUND_MODEL
    IF (direct_products) THEN
      surface_source=SOURCE_OUTPUT_ADAPTER
      thermo_source=SOURCE_OUTPUT_ADAPTER
      hydro_source=IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_OUTPUT_ADAPTER)
    END IF
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,valid_time, &
                                    'NE57_LAPS_PRESSURE',local_status)
    IF (local_status/=STATUS_OK) RETURN
    ALLOCATE(raw(NX,NY,NZ),raw_valid(NX,NY,NZ),surface(NX,NY), &
             surface_vapor(NX,NY),surface_valid(NX,NY),surface_vapor_valid(NX,NY), &
             latitude_valid(NX,NY),longitude_valid(NX,NY), &
             topography_valid(NX,NY),terrain_domain(NX,NY,NZ), &
             tid(NX,NY,NZ),longitude(NX,NY), &
             topography(NX,NY))
    raw=0.0_real32; raw_valid=.FALSE.
    surface=0.0_real32; surface_valid=.FALSE.
    surface_vapor=0.0_real32; surface_vapor_valid=.FALSE.
    latitude_valid=.FALSE.; longitude_valid=.FALSE.; topography_valid=.FALSE.
    terrain_domain=.FALSE.; tid=0.0_real32
    longitude=0.0_real32; topography=0.0_real32

    ! Surface pressure and the pressure coordinate own the physical domain.
    ! Omega is a required field inside that domain, never the domain mask.
    IF (direct_products) THEN
      CALL open_surface_file(lsx_path,valid_time,TIME_POLICY_ANALYSIS, &
                             ncid,dx,dy,local_status)
    ELSE
      CALL open_surface_file(fsf_path,valid_time,TIME_POLICY_FORECAST, &
                             ncid,dx,dy,local_status,forecast_reftime)
    END IF
    IF (local_status==STATUS_OK) THEN
      IF (direct_products) THEN
        CALL read_real2(ncid,'t','degrees kelvin','k',surface,surface_valid,local_status)
      ELSE
        CALL read_real2(ncid,'tsf','kelvins','k',surface,surface_valid,local_status)
      END IF
    END IF
    IF (local_status==STATUS_OK .AND. .NOT.ALL(surface_valid)) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_temperature,surface_source)

    ! Surface vapor is optional in this shared reader; consumers that need
    ! a surface vapor anchor enforce complete coverage. The pinned FSF
    ! schema has no MR field, so do not infer vapor from RH or
    ! dewpoint.  If an MR variable is present, however, it is part of the
    ! file contract: malformed units, layout, coverage, or range reject the
    ! reader rather than silently treating it as absent.  Keep its validity
    ! mask separate from surface_valid because the latter owns PSFC geometry.
    IF (local_status==STATUS_OK) THEN
      rc=nf90_inq_varid(ncid,'mr',mr_varid)
      IF (rc==NF90_NOERR) THEN
        IF (variable_unit_is(ncid,mr_varid,'grams/kikogram','grams/kilogram')) THEN
          CALL read_real2(ncid,'mr','grams/kikogram','grams/kilogram', &
                          surface_vapor,surface_vapor_valid,local_status)
        ELSE IF (variable_unit_is(ncid,mr_varid,'g/kg','g kg-1')) THEN
          CALL read_real2(ncid,'mr','g/kg','g kg-1',surface_vapor, &
                          surface_vapor_valid,local_status)
        ELSE
          reason=REASON_METADATA
          local_status=STATUS_FAILED
        END IF
        IF (local_status==STATUS_OK .AND. .NOT.ALL(surface_vapor_valid)) THEN
          local_status=STATUS_FAILED
          reason=REASON_REQUIRED_COVERAGE
        END IF
        IF (local_status==STATUS_OK) THEN
          IF (ANY(surface_vapor<0.0_real32) .OR. &
              ANY(surface_vapor>100.0_real32)) THEN
            local_status=STATUS_FAILED
            reason=REASON_RANGE
          END IF
        END IF
        IF (local_status==STATUS_OK) THEN
          surface_vapor=0.001_real32*surface_vapor
          CALL assign_surface(surface_vapor,surface_vapor_valid, &
            state%surface_vapor,surface_source)
        END IF
      ELSE IF (rc/=NF90_ENOTVAR) THEN
        local_status=STATUS_FAILED
        reason=REASON_METADATA
      END IF
    END IF
    IF (local_status==STATUS_OK) THEN
      IF (direct_products) THEN
        CALL read_real2(ncid,'ps','pascals','pa',surface,surface_valid,local_status)
      ELSE
        CALL read_real2(ncid,'psf','pascals','pa',surface,surface_valid,local_status)
      END IF
    END IF
    IF (local_status==STATUS_OK .AND. .NOT.ALL(surface_valid)) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_pressure,surface_source)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_case_file(lw3_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                        ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real3(ncid,'om','pascals/second','pa/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    state%grid%dx=dx; state%grid%dy=dy
    DO k=1,NZ
      source_k=NZ+1-k
      state%pressure%value(:,:,k)=REAL(100.0_real64*levels(source_k),real32)
      CALL mark_real_field(state%pressure,k,surface_valid,surface_source)
    END DO
    CALL configure_pressure_geometry(state,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (.NOT.vertical_domain_is_contiguous(state%above_ground)) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%omega, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    IF (PRESENT(retained_omega)) THEN
      ! WPS omits omega. Retain this same LW3 read for an explicit future
      ! pressure-domain reconstruction, without expanding the canonical
      ! domain or granting target authority. Publish only after full ingest.
      omega_work=state%omega
      DO k=1,NZ
        source_k=NZ+1-k
        omega_work%value(:,:,k)=MERGE(raw(:,:,source_k),0.0_real32,raw_valid(:,:,source_k))
        CALL mark_real_field(omega_work,k,raw_valid(:,:,source_k),SOURCE_ANALYZED_WIND)
        WHERE (raw_valid(:,:,source_k) .AND. ABS(omega_work%value(:,:,k))>100.0_real32)
          omega_work%valid(:,:,k)=.FALSE.
          omega_work%quality(:,:,k)=QUALITY_QC_REJECTED
          omega_work%source(:,:,k)=0_int32
        END WHERE
      END DO
    END IF
    CALL read_real3(ncid,'u3','meters/second','m/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%u, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL read_real3(ncid,'v3','meters/second','m/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%v, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) reason=REASON_REQUIRED_COVERAGE
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    IF (direct_products) THEN
      ! The analyzed thermo products are split by field family.  Open and
      ! validate each file only for the fields it owns; no FUA fallback is
      ! permitted once the direct paths are supplied.
      CALL open_case_file(lt1_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                          ncid,levels,dx,dy,local_status)
      IF (local_status/=STATUS_OK) RETURN
      CALL read_real3(ncid,'t3','degrees kelvin','k',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%temperature, &
        thermo_source,1.0_real64,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      CALL read_real3(ncid,'ht','meters','m',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%geopotential, &
        thermo_source,GRAVITY,local_status)
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) THEN
        reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF

      CALL open_case_file(lq3_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                          ncid,levels,dx,dy,local_status)
      IF (local_status/=STATUS_OK) RETURN
      CALL read_real3(ncid,'sh','kg/kg','kgkg-1',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      IF (.NOT.reversed_coverage_is_complete(raw_valid,state%above_ground)) THEN
        CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      CALL assign_specific_humidity(raw,raw_valid,state,local_status,thermo_source)
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) THEN
        reason=REASON_RANGE; RETURN
      END IF

      CALL open_case_file(lwc_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                          ncid,levels,dx,dy,local_status)
      IF (local_status/=STATUS_OK) RETURN
      CALL read_and_assign_hydrometeor(ncid,'lwc',state,state%cloud_water,raw, &
        raw_valid,local_status,hydro_source,.TRUE.)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'ice', &
        state,state%cloud_ice,raw,raw_valid,local_status,hydro_source,.TRUE.)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'rai', &
        state,state%rain,raw,raw_valid,local_status,hydro_source,.TRUE.)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'sno', &
        state,state%snow,raw,raw_valid,local_status,hydro_source,.TRUE.)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'pic', &
        state,state%graupel,raw,raw_valid,local_status,hydro_source,.TRUE.)
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) RETURN
    ELSE
      CALL open_case_file(fua_path,NZ,valid_time,TIME_POLICY_FORECAST, &
                          ncid,levels,dx,dy,local_status,file_reftime)
      IF (local_status/=STATUS_OK) RETURN
      IF (ABS(file_reftime-forecast_reftime)>TIME_TOLERANCE_SECONDS) THEN
        WRITE(*,'(A)') 'adapter_error=forecast-cycle-mismatch:'//TRIM(fua_path)
        CALL close_file(ncid,local_status)
        RETURN
      END IF
      CALL read_real3(ncid,'t3','kelvins','k',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%temperature, &
        thermo_source,1.0_real64,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      CALL read_real3(ncid,'sh','kg/kg','kgkg-1',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      IF (.NOT.reversed_coverage_is_complete(raw_valid,state%above_ground)) THEN
        CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      CALL assign_specific_humidity(raw,raw_valid,state,local_status,thermo_source)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status); reason=REASON_RANGE; RETURN
      END IF
      CALL read_real3(ncid,'ht','meters','m',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
      CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%geopotential, &
        thermo_source,GRAVITY,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
      END IF
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'lwc', &
        state,state%cloud_water,raw,raw_valid,local_status,hydro_source)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'ice', &
        state,state%cloud_ice,raw,raw_valid,local_status,hydro_source)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'rai', &
        state,state%rain,raw,raw_valid,local_status,hydro_source)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'sno', &
        state,state%snow,raw,raw_valid,local_status,hydro_source)
      IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'pic', &
        state,state%graupel,raw,raw_valid,local_status,hydro_source)
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) RETURN
    END IF

    IF (processed_cloud) THEN
      ! LCP is stored as a fractional cloud cover field.  The legacy CDL
      ! advertises a broad 0--100 range, but the processed product's
      ! fractional values are the canonical 0--1 quantity; do not rescale.
      CALL open_case_file(lcp_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                          ncid,levels,dx,dy,local_status)
      IF (local_status/=STATUS_OK) RETURN
      CALL read_real3(ncid,'lcp','fractional','fractional',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status)
        RETURN
      END IF
      IF (ANY(raw_valid .AND. (raw<0.0_real32 .OR. raw>1.0_real32))) THEN
        CALL close_file(ncid,local_status)
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE (.NOT.raw_valid) raw=0.0_real32
      DO k=1,NZ
        source_k=NZ+1-k
        usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k)
        state%cloud_fraction%value(:,:,k)=0.0_real32
        WHERE (usable) state%cloud_fraction%value(:,:,k)=raw(:,:,source_k)
        CALL mark_real_field(state%cloud_fraction,k,usable,SOURCE_CLOUD_ANALYSIS)
      END DO
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) RETURN

      ! LTY writes PTY and CTY as float variables containing integer codes.
      ! Read and validate the exact codes before assigning canonical integer
      ! fields; no precipitation mass or target authority is inferred here.
      CALL open_case_file(lty_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                          ncid,levels,dx,dy,local_status)
      IF (local_status/=STATUS_OK) RETURN
      CALL read_real3(ncid,'pty','none','none',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status)
        RETURN
      END IF
      IF (ANY(raw_valid .AND. (raw<0.0_real32 .OR. raw>5.0_real32))) THEN
        CALL close_file(ncid,local_status)
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE (.NOT.raw_valid) raw=0.0_real32
      IF (ANY(raw/=REAL(NINT(raw),real32))) THEN
        CALL close_file(ncid,local_status)
        reason=REASON_RANGE
        RETURN
      END IF
      DO k=1,NZ
        source_k=NZ+1-k
        usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k)
        state%precipitation_phase%value(:,:,k)=PHASE_UNKNOWN
        state%precipitation_phase%valid(:,:,k)=usable
        state%precipitation_phase%quality(:,:,k)=MERGE(0_int32, &
          QUALITY_RAW_MISSING,usable)
        state%precipitation_phase%source(:,:,k)=MERGE(SOURCE_CLOUD_ANALYSIS, &
          0_int32,usable)
        DO j=1,NY
          DO i=1,NX
            IF (.NOT.usable(i,j)) CYCLE
            code=NINT(raw(i,j,source_k))
            SELECT CASE(code)
            CASE(0)
              state%precipitation_phase%value(i,j,k)=PHASE_UNKNOWN
            CASE(1)
              state%precipitation_phase%value(i,j,k)=PHASE_RAIN
            CASE(2)
              state%precipitation_phase%value(i,j,k)=PHASE_SNOW
            CASE(3)
              state%precipitation_phase%value(i,j,k)=PHASE_FREEZING_RAIN
            CASE(4)
              state%precipitation_phase%value(i,j,k)=PHASE_SLEET
            CASE(5)
              ! Legacy PTY 5 is hail.  Canonical code 5 is graupel, so
              ! preserve the observation as uncertain unknown rather than
              ! inventing an equivalence.
              state%precipitation_phase%value(i,j,k)=PHASE_UNKNOWN
              state%precipitation_phase%quality(i,j,k)=QUALITY_PHASE_UNCERTAIN
            END SELECT
          END DO
        END DO
      END DO
      CALL read_real3(ncid,'cty','none','none',raw,raw_valid,local_status)
      IF (local_status/=STATUS_OK) THEN
        CALL close_file(ncid,local_status)
        RETURN
      END IF
      IF (ANY(raw_valid .AND. (raw<0.0_real32 .OR. raw>11.0_real32))) THEN
        CALL close_file(ncid,local_status)
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE (.NOT.raw_valid) raw=0.0_real32
      IF (ANY(raw/=REAL(NINT(raw),real32))) THEN
        CALL close_file(ncid,local_status)
        reason=REASON_RANGE
        RETURN
      END IF
      DO k=1,NZ
        source_k=NZ+1-k
        usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k)
        state%cloud_type%value(:,:,k)=0_int32
        state%cloud_type%valid(:,:,k)=usable
        state%cloud_type%quality(:,:,k)=MERGE(0_int32,QUALITY_RAW_MISSING,usable)
        state%cloud_type%source(:,:,k)=MERGE(SOURCE_CLOUD_ANALYSIS,0_int32,usable)
        WHERE (usable) state%cloud_type%value(:,:,k)=NINT(raw(:,:,source_k))
      END DO
      CALL close_file(ncid,local_status)
      IF (local_status/=STATUS_OK) RETURN
    END IF

    CALL open_case_file(vrz_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                        ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'ref','dbz','dbz', &
                                                 raw,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      state%radar_reflectivity%valid(:,:,k)=state%above_ground(:,:,k) .AND. &
        raw_valid(:,:,source_k) .AND. raw(:,:,source_k)>=MINIMUM_USABLE_DBZ .AND. &
        raw(:,:,source_k)<=100.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
          .NOT.(raw(:,:,source_k)==RADAR_NO_ECHO_DBZ .OR. &
                (raw(:,:,source_k)>=MINIMUM_USABLE_DBZ .AND. &
                 raw(:,:,source_k)<=100.0_real32)))) THEN
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE(state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
            (state%radar_reflectivity%valid(:,:,k) .OR. &
             raw(:,:,source_k)==RADAR_NO_ECHO_DBZ))
        state%radar_reflectivity%value(:,:,k)=raw(:,:,source_k)
        state%radar_reflectivity%quality(:,:,k)=0_int32
        state%radar_reflectivity%source(:,:,k)=SOURCE_RADAR_DBZ
      END WHERE
    END DO

    CALL open_case_file(vrt_path,NZ,valid_time,TIME_POLICY_ANALYSIS, &
                        ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'tid','nul','1', &
                                                 tid,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      IF (ANY(state%above_ground(:,:,k) .AND. &
              .NOT.radar_tid_value_valid(tid(:,:,source_k), &
                                         raw_valid(:,:,source_k)))) THEN
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE(state%radar_reflectivity%valid(:,:,k) .AND. &
            radar_tid_is_mixed(tid(:,:,source_k),raw_valid(:,:,source_k)))
        state%radar_reflectivity%quality(:,:,k)= &
          IOR(state%radar_reflectivity%quality(:,:,k),QUALITY_BRIGHT_BAND_OR_MIXED)
      END WHERE
    END DO

    CALL open_static_file(static_path,ncid,local_status)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'lat','degrees','degree_north', &
                                                 surface,latitude_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(latitude_valid .AND. (surface < -90.0_real32 .OR. &
                                  surface > 90.0_real32))) local_status=STATUS_FAILED
    IF (local_status==STATUS_OK) CALL assign_surface(surface,latitude_valid, &
      state%latitude,SOURCE_BACKGROUND_MODEL)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'lon','degrees','degree_east', &
                                                 longitude,longitude_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(longitude_valid .AND. (longitude < -180.0_real32 .OR. &
                                   longitude > 180.0_real32))) local_status=STATUS_FAILED
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'avg','meters msl','m', &
      topography,topography_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(topography_valid .AND. (topography < -500.0_real32 .OR. &
                                    topography > 9000.0_real32))) &
      local_status=STATUS_FAILED
    IF (local_status==STATUS_OK) CALL assign_surface(topography,topography_valid, &
      state%surface_height,SOURCE_BACKGROUND_MODEL)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK .OR. .NOT.ALL(latitude_valid) .OR. &
        .NOT.ALL(longitude_valid) .OR. .NOT.ALL(topography_valid)) RETURN
    terrain_domain=state%above_ground .AND. state%geopotential%valid .AND. &
      ieee_is_finite(state%geopotential%value) .AND. &
      state%geopotential%value/REAL(GRAVITY,real32)>= &
        SPREAD(topography-128.0_real32*EPSILON(1.0_real32)* &
          MAX(1.0_real32,ABS(topography)),3,NZ)
    CALL configure_pressure_geometry(state,local_status,terrain_domain)
    IF (local_status/=STATUS_OK) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    CALL restrict_state_to_domain(state)
    IF (.NOT.terrain_mask_is_consistent(state,topography)) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF

    CALL set_copied_interior_omega_boundaries(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    IF (.NOT.real_radar_contract_valid(state)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    CALL validate_canonical_state(state,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status/=STATUS_OK) RETURN
    IF (PRESENT(retained_omega)) retained_omega=omega_work
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_real_shadow_state

  SUBROUTINE set_real_numerical_test_boundaries( &
      state,fsf_before_path,fsf_center_path,fsf_after_path,status,reason)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    CHARACTER(LEN=*), INTENT(IN) :: fsf_before_path,fsf_center_path,fsf_after_path
    INTEGER, INTENT(OUT) :: status,reason
    REAL(real32) :: ps_before(NX,NY),ps_center(NX,NY),ps_after(NX,NY)
    REAL(real32) :: us(NX,NY),vs(NX,NY),bottom_work(NX,NY)
    LOGICAL :: valid_before(NX,NY),valid_center(NX,NY),valid_after(NX,NY)
    LOGICAL :: valid_us(NX,NY),valid_vs(NX,NY)
    REAL(real64) :: dx_before,dy_before,dx_center,dy_center,dx_after,dy_after
    REAL(real64) :: reftime_before,reftime_center,reftime_after
    REAL(real64) :: dpdx,dpdy,x_distance,y_distance,omega
    INTEGER(int64) :: center_time
    INTEGER :: ncid,local_status,i,j

    status=STATUS_FAILED; reason=REASON_METADATA
    center_time=state%pressure%valid_time
    IF (state%grid%nx/=NX .OR. state%grid%ny/=NY .OR. &
        .NOT.ALLOCATED(state%grid%dx) .OR. .NOT.ALLOCATED(state%grid%dy) .OR. &
        .NOT.ALLOCATED(state%surface_pressure%value) .OR. &
        .NOT.ALLOCATED(state%surface_pressure%valid) .OR. &
        .NOT.ALLOCATED(state%surface_pressure%quality) .OR. &
        .NOT.ALLOCATED(state%surface_pressure%source)) THEN
      reason=REASON_SHAPE
      RETURN
    END IF
    IF (ANY(SHAPE(state%grid%dx)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(state%grid%dy)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(state%surface_pressure%value)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(state%surface_pressure%valid)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(state%surface_pressure%quality)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(state%surface_pressure%source)/=(/NX,NY/))) THEN
      reason=REASON_SHAPE
      RETURN
    END IF
    IF (.NOT.boundary_contract_valid(state) .OR. &
        state%surface_pressure%valid_time/=center_time .OR. &
        state%surface_pressure%unit/='Pa' .OR. &
        .NOT.ALL(cell_is_usable(state%surface_pressure%valid, &
          state%surface_pressure%quality,state%surface_pressure%source))) RETURN
    IF (ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64) .OR. &
        ANY(.NOT.ieee_is_finite(state%surface_pressure%value)) .OR. &
        ANY(state%surface_pressure%value<50000.0_real32) .OR. &
        ANY(state%surface_pressure%value>110000.0_real32)) THEN
      reason=REASON_RANGE
      RETURN
    END IF

    CALL open_surface_file(fsf_before_path,center_time-3600_int64, &
                           TIME_POLICY_FORECAST,ncid,dx_before,dy_before,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real2(ncid,'psf','pascals','pa',ps_before,valid_before,local_status)
    IF (local_status==STATUS_OK .AND. &
        .NOT.read_scalar(ncid,'reftime',reftime_before)) local_status=STATUS_FAILED
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_surface_file(fsf_center_path,center_time,TIME_POLICY_FORECAST,ncid, &
                           dx_center,dy_center,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real2(ncid,'psf','pascals','pa',ps_center,valid_center,local_status)
    IF (local_status==STATUS_OK) &
      CALL read_real2(ncid,'usf','meters/second','m/s',us,valid_us,local_status)
    IF (local_status==STATUS_OK) &
      CALL read_real2(ncid,'vsf','meters/second','m/s',vs,valid_vs,local_status)
    IF (local_status==STATUS_OK .AND. &
        .NOT.read_scalar(ncid,'reftime',reftime_center)) local_status=STATUS_FAILED
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_surface_file(fsf_after_path,center_time+3600_int64, &
                           TIME_POLICY_FORECAST,ncid,dx_after,dy_after,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real2(ncid,'psf','pascals','pa',ps_after,valid_after,local_status)
    IF (local_status==STATUS_OK .AND. &
        .NOT.read_scalar(ncid,'reftime',reftime_after)) local_status=STATUS_FAILED
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    IF (.NOT.ALL(valid_before .AND. valid_center .AND. valid_after .AND. &
                 valid_us .AND. valid_vs)) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (ABS(reftime_before-reftime_center)>0.5_real64 .OR. &
        ABS(reftime_after-reftime_center)>0.5_real64) RETURN
    IF (MAX(ABS(dx_before-dx_center),ABS(dx_after-dx_center), &
            ABS(dy_before-dy_center),ABS(dy_after-dy_center))>1.0e-6_real64 .OR. &
        ANY(ABS(state%grid%dx-dx_center)>1.0e-6_real64) .OR. &
        ANY(ABS(state%grid%dy-dy_center)>1.0e-6_real64)) RETURN
    IF (ANY(ABS(REAL(ps_center,real64)- &
        REAL(state%surface_pressure%value,real64))>0.5_real64)) RETURN
    IF (ANY(ps_before<50000.0_real32) .OR. ANY(ps_before>110000.0_real32) .OR. &
        ANY(ps_center<50000.0_real32) .OR. ANY(ps_center>110000.0_real32) .OR. &
        ANY(ps_after<50000.0_real32) .OR. ANY(ps_after>110000.0_real32) .OR. &
        ANY(ABS(us)>100.0_real32) .OR. ANY(ABS(vs)>100.0_real32)) THEN
      reason=REASON_RANGE
      RETURN
    END IF

    DO j=1,NY; DO i=1,NX
      IF (i==1) THEN
        x_distance=0.5_real64*(state%grid%dx(i,j)+state%grid%dx(i+1,j))
        dpdx=(REAL(ps_center(i+1,j),real64)-REAL(ps_center(i,j),real64))/x_distance
      ELSE IF (i==NX) THEN
        x_distance=0.5_real64*(state%grid%dx(i-1,j)+state%grid%dx(i,j))
        dpdx=(REAL(ps_center(i,j),real64)-REAL(ps_center(i-1,j),real64))/x_distance
      ELSE
        x_distance=0.5_real64*state%grid%dx(i-1,j)+state%grid%dx(i,j)+ &
                   0.5_real64*state%grid%dx(i+1,j)
        dpdx=(REAL(ps_center(i+1,j),real64)-REAL(ps_center(i-1,j),real64))/x_distance
      END IF
      IF (j==1) THEN
        y_distance=0.5_real64*(state%grid%dy(i,j)+state%grid%dy(i,j+1))
        dpdy=(REAL(ps_center(i,j+1),real64)-REAL(ps_center(i,j),real64))/y_distance
      ELSE IF (j==NY) THEN
        y_distance=0.5_real64*(state%grid%dy(i,j-1)+state%grid%dy(i,j))
        dpdy=(REAL(ps_center(i,j),real64)-REAL(ps_center(i,j-1),real64))/y_distance
      ELSE
        y_distance=0.5_real64*state%grid%dy(i,j-1)+state%grid%dy(i,j)+ &
                   0.5_real64*state%grid%dy(i,j+1)
        dpdy=(REAL(ps_center(i,j+1),real64)-REAL(ps_center(i,j-1),real64))/y_distance
      END IF
      omega=(REAL(ps_after(i,j),real64)-REAL(ps_before(i,j),real64))/7200.0_real64+ &
            REAL(us(i,j),real64)*dpdx+REAL(vs(i,j),real64)*dpdy
      IF (.NOT.ieee_is_finite(omega) .OR. ABS(omega)>20.0_real64) THEN
        reason=REASON_RANGE
        RETURN
      END IF
      bottom_work(i,j)=REAL(omega,real32)
    END DO; END DO

    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=bottom_work
    state%omega_top_boundary%valid=.TRUE.
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32
    state%omega_bottom_boundary%quality=0_int32
    ! The FSF files do not declare whether USF/VSF are grid-relative or
    ! earth-relative.  These real-data kinematic boundaries therefore have
    ! numerical-test authority only; they cannot authorize an observational
    ! balance target in the normal pipeline.
    state%omega_top_boundary%source= &
      IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)
    state%omega_bottom_boundary%source= &
      IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE set_real_numerical_test_boundaries

  SUBROUTINE write_shadow_diagnostics(path,state_in,candidate,longitude,result,config, &
                                      residual_before,residual_after,status,operational_state, &
                                      pressure_analysis_candidate)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate
    REAL(real32), INTENT(IN) :: longitude(:,:)
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    INTEGER, INTENT(OUT) :: status
    TYPE(cloud_bal_state_type), INTENT(IN) :: operational_state
    LOGICAL, INTENT(IN), OPTIONAL :: pressure_analysis_candidate
    LOGICAL :: pressure_candidate,variable_geometry
    LOGICAL, ALLOCATABLE :: geostrophic_support(:,:,:),geostrophic_stencil_support(:,:,:)
    REAL(real64) :: reference_geostrophic_rms,final_geostrophic_rms
    INTEGER :: ncid,xdim,ydim,zdim,zinterface_dim,zspacing_dim
    INTEGER :: level_var,lat_var,lon_var,interface_var,cell_dp_var,spacing_var
    INTEGER :: pressure_mass_var,dry_mass_var,surface_pressure_var
    INTEGER :: omega_top_var,omega_bottom_var,omega_top_valid_var,omega_bottom_valid_var
    INTEGER :: omega_top_quality_var,omega_top_source_var
    INTEGER :: omega_bottom_quality_var,omega_bottom_source_var
    INTEGER :: varid(37),rc,k,contract_reason,nx,ny,nz
    INTEGER(int32), ALLOCATABLE :: mask(:,:,:),boundary_mask(:,:)
    REAL(real32), ALLOCATABLE :: levels(:)
    CHARACTER(LEN=32), PARAMETER :: names(37)=[CHARACTER(LEN=32) :: &
      'radar_dbz','background_u','background_v','background_omega', &
      'candidate_u','candidate_v','candidate_omega','omega_target', &
      'background_cloud_water','background_cloud_ice','background_rain', &
      'background_snow','background_graupel','candidate_cloud_water', &
      'candidate_cloud_ice','candidate_rain','candidate_snow', &
      'candidate_graupel','balance_beta', &
      'continuity_background','continuity_candidate','above_ground', &
      'radar_valid','omega_target_valid','omega_target_quality', &
      'omega_target_source','omega_target_authority','candidate_balance_support', &
      'column_changed','balance_changed','overall_changed','obs_support','hydro_support', &
      'radar_coverage','radar_no_echo','radar_missing','model_target_coverage']
    CHARACTER(LEN=32), PARAMETER :: units(37)=[CHARACTER(LEN=32) :: &
      'dBZ','m s-1','m s-1','Pa s-1','m s-1','m s-1','Pa s-1','Pa s-1', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','1','s-1','s-1', &
      '1','1','1','1','1','1','1','1','1','1','1','1','1','1','1','1']

    status=STATUS_FAILED
    pressure_candidate=.FALSE.
    IF (PRESENT(pressure_analysis_candidate)) pressure_candidate=pressure_analysis_candidate
    variable_geometry=ALLOCATED(result%requested_surface_pressure)
    CALL validate_shadow_write_contract(state_in,candidate,operational_state, &
      result,config,status,contract_reason,pressure_candidate)
    IF (status/=STATUS_OK) THEN
      WRITE(*,'(A,I0)') 'shadow_write_contract_reason=',contract_reason
      RETURN
    END IF
    status=STATUS_FAILED
    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    IF (ANY(SHAPE(longitude)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(residual_before)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(residual_after)/=(/nx,ny,nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(state_in%latitude%value)) .OR. &
        ANY(state_in%latitude%value < -90.0_real32) .OR. &
        ANY(state_in%latitude%value > 90.0_real32) .OR. &
        ANY(.NOT.ieee_is_finite(longitude)) .OR. &
        ANY(longitude < -180.0_real32) .OR. ANY(longitude > 180.0_real32) .OR. &
        ANY(.NOT.ieee_is_finite(residual_before)) .OR. &
        ANY(.NOT.ieee_is_finite(residual_after))) RETURN
    IF (ALLOCATED(result%geopotential_support)) THEN
      CALL assess_pressure_geostrophic_change(state_in,candidate,config%balance, &
        result%geopotential_support,geostrophic_support, &
        reference_geostrophic_rms,final_geostrophic_rms,status,geostrophic_stencil_support, &
        allow_surface_pressure_geometry=ALLOCATED(result%requested_surface_pressure), &
        transition_seed=result%pressure_transition_seed)
      IF (status/=STATUS_OK) THEN
        WRITE(*,'(A)') 'shadow_write_geostrophic_assessment_failed'
        RETURN
      END IF
      status=STATUS_FAILED
    END IF
    rc=nf90_create(TRIM(path),IOR(NF90_NOCLOBBER,NF90_NETCDF4),ncid)
    IF (rc/=NF90_NOERR) RETURN
    IF (.NOT.nc_ok(nf90_def_dim(ncid,'x',nx,xdim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'y',ny,ydim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z',nz,zdim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z_interface',nz+1,zinterface_dim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z_spacing',nz-1,zspacing_dim))) GOTO 900
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure',NF90_FLOAT,(/zdim/),level_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'latitude',NF90_FLOAT,(/xdim,ydim/),lat_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'longitude',NF90_FLOAT,(/xdim,ydim/),lon_var))) GOTO 900
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure_interface',NF90_DOUBLE, &
          (/xdim,ydim,zinterface_dim/),interface_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'cell_dp',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),cell_dp_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'level_spacing_dp',NF90_DOUBLE, &
          (/xdim,ydim,zspacing_dim/),spacing_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'pressure_mass_measure',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),pressure_mass_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'dry_air_mass_measure',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),dry_mass_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'surface_pressure',NF90_FLOAT, &
          (/xdim,ydim/),surface_pressure_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary',NF90_FLOAT, &
          (/xdim,ydim/),omega_top_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary',NF90_FLOAT, &
          (/xdim,ydim/),omega_bottom_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_valid',NF90_INT, &
          (/xdim,ydim/),omega_top_valid_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_valid',NF90_INT, &
          (/xdim,ydim/),omega_bottom_valid_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_quality',NF90_INT, &
          (/xdim,ydim/),omega_top_quality_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_source',NF90_INT, &
          (/xdim,ydim/),omega_top_source_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_quality',NF90_INT, &
          (/xdim,ydim/),omega_bottom_quality_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_source',NF90_INT, &
          (/xdim,ydim/),omega_bottom_source_var))) GOTO 900
    DO k=1,19
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_FLOAT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=20,21
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_DOUBLE, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=22,37
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_INT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=1,36
      IF (.NOT.nc_ok(nf90_put_att(ncid,varid(k),'units',TRIM(units(k))))) GOTO 900
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,varid(k),1,1,1))) GOTO 900
    END DO
    IF (.NOT.nc_ok(nf90_put_att(ncid,interface_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,cell_dp_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,spacing_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,pressure_mass_var,'units','kg')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,dry_mass_var,'units','kg dryair')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,surface_pressure_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_var,'units','Pa s-1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_var,'units','Pa s-1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_valid_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_valid_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_quality_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_source_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_quality_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_source_var,'units','1'))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,varid(28),'long_name', &
      'candidate balance localization support')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,varid(28),'legacy_name','balance_active'))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,varid(37),'long_name', &
      'paired model native target and closed halo coverage'))) GOTO 900
    IF (.NOT.put_global_metadata(ncid,result,config,state_in%pressure%valid_time)) GOTO 900
    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_target_error_contract', &
        'MODEL_ABSOLUTE_TARGET_NO_SIGMA'))) GOTO 900
    ELSE
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_target_error_contract', &
        'diagonal_pressure_omega_v1'))) GOTO 900
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'surface_boundary_contract', &
      'CANONICAL_SURFACE_BOUNDARY_V1'))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_id', &
                                TRIM(state_in%grid%grid_id))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_vertical_order', &
                                'bottom_to_top')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'netcdf_variable_order', &
                                'z,y,x')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dx_m', &
                                state_in%grid%dx(1,1))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dy_m', &
                                state_in%grid%dy(1,1)))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,level_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lat_var,'units','degree_north')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lon_var,'units','degree_east'))) GOTO 900
    IF (.NOT.nc_ok(nf90_enddef(ncid))) GOTO 900
    ALLOCATE(levels(nz))
    DO k=1,nz
      levels(k)=state_in%pressure%value(1,1,k)
    END DO
    IF (.NOT.nc_ok(nf90_put_var(ncid,level_var,levels)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lat_var,state_in%latitude%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lon_var,longitude)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,interface_var, &
          state_in%grid%pressure_interface)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,cell_dp_var,state_in%grid%cell_dp)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,spacing_var, &
          state_in%grid%level_spacing_dp)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,pressure_mass_var, &
          state_in%grid%pressure_mass_measure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,dry_mass_var, &
          state_in%grid%dry_air_mass_measure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,surface_pressure_var, &
          state_in%surface_pressure%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_var, &
          state_in%omega_top_boundary%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_var, &
          state_in%omega_bottom_boundary%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_quality_var, &
          state_in%omega_top_boundary%quality)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_source_var, &
          state_in%omega_top_boundary%source)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_quality_var, &
          state_in%omega_bottom_boundary%quality)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_source_var, &
          state_in%omega_bottom_boundary%source))) GOTO 900
    ALLOCATE(boundary_mask(nx,ny))
    boundary_mask=MERGE(1_int32,0_int32,state_in%omega_top_boundary%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,omega_top_valid_var,boundary_mask))) GOTO 900
    boundary_mask=MERGE(1_int32,0_int32,state_in%omega_bottom_boundary%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,omega_bottom_valid_var,boundary_mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(1),state_in%radar_reflectivity%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(2),state_in%u%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(3),state_in%v%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(4),state_in%omega%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(5),candidate%u%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(6),candidate%v%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(7),candidate%omega%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(8),candidate%omega_target%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(9),state_in%cloud_water%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(10),state_in%cloud_ice%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(11),state_in%rain%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(12),state_in%snow%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(13),state_in%graupel%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(14),candidate%cloud_water%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(15),candidate%cloud_ice%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(16),candidate%rain%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(17),candidate%snow%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(18),candidate%graupel%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(19),candidate%balance_beta)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(20),residual_before)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(21),residual_after))) GOTO 900
    ALLOCATE(mask(nx,ny,nz))
    mask=MERGE(1_int32,0_int32,state_in%above_ground)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(22),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_echo_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(23),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,candidate%omega_target%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(24),mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(25),candidate%omega_target%quality))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(26),candidate%omega_target%source))) GOTO 900
    mask=MERGE(1_int32,0_int32,target_is_resolved(candidate, &
      config%balance%target_authority))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(27),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,candidate%above_ground .AND. &
      balance_beta_active(candidate%balance_beta,config%balance%minimum_beta))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(28),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%column%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(29),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%balance%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(30),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%overall%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(31),mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(32),candidate%obs_support))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(33),candidate%hydro_support))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. &
      (radar_echo_cell(state_in%radar_reflectivity%value, &
         state_in%radar_reflectivity%valid,state_in%radar_reflectivity%quality, &
         state_in%radar_reflectivity%source) .OR. &
       radar_no_echo_cell(state_in%radar_reflectivity%value, &
         state_in%radar_reflectivity%valid,state_in%radar_reflectivity%quality, &
         state_in%radar_reflectivity%source)))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(34),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_no_echo_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(35),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_missing_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(36),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,candidate%model_target_coverage)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(37),mask))) GOTO 900
    IF (.NOT.put_thermo_field(ncid,(/xdim,ydim,zdim/),'omega_target_sigma', &
      candidate%omega_target_sigma)) GOTO 900
    IF (ALLOCATED(result%thermo_support)) THEN
      IF (.NOT.put_thermo_extension(ncid,(/xdim,ydim,zdim/), &
        state_in,candidate,result)) GOTO 900
    END IF
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'background_surface_pressure', &
      state_in%surface_pressure)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'candidate_surface_pressure', &
      candidate%surface_pressure)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'background_surface_temperature', &
      state_in%surface_temperature)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'candidate_surface_temperature', &
      candidate%surface_temperature)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'background_surface_vapor', &
      state_in%surface_vapor)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'candidate_surface_vapor', &
      candidate%surface_vapor)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'background_surface_height', &
      state_in%surface_height)) GOTO 900
    IF (.NOT.put_surface_field(ncid,(/xdim,ydim/),'candidate_surface_height', &
      candidate%surface_height)) GOTO 900
    IF (variable_geometry) THEN
      IF (.NOT.put_pressure_geometry_extension(ncid,(/xdim,ydim/), &
        (/xdim,ydim,zdim/),(/xdim,ydim,zinterface_dim/),candidate,result)) GOTO 900
    END IF
    IF (ALLOCATED(result%pressure_transition_seed)) THEN
      IF (.NOT.put_pressure_transition_extension(ncid,(/xdim,ydim/), &
        (/xdim,ydim,zdim/),state_in,candidate,result)) GOTO 900
    END IF
    IF (config%maximum_outer_iterations>1) THEN
      IF (.NOT.put_outer_extension(ncid,result,config)) GOTO 900
    END IF
    IF (config%maximum_outer_iterations>1 .OR. ALLOCATED(result%pressure_transition_seed) .OR. &
        cloud_provenance_present(state_in)) THEN
      ! A remapped final precipitation field is not the original radar proposal.
      ! Preserve the inputs needed to reconstruct that earlier state.
      IF (.NOT.put_radar_reconstruction_inputs(ncid,(/xdim,ydim,zdim/),state_in,config)) GOTO 900
    END IF
    IF (pressure_candidate) THEN
      IF (.NOT.put_pressure_candidate_extension(ncid,(/xdim,ydim,zdim/), &
        state_in,candidate,result,config)) GOTO 900
      IF (ALLOCATED(result%thermo_support)) THEN
        IF (.NOT.put_dry_air_flux_extension(ncid,(/xdim,ydim,zdim/),state_in,candidate,config, &
          variable_geometry)) GOTO 900
      END IF
      IF (ALLOCATED(geostrophic_support)) THEN
        IF (.NOT.put_pressure_geostrophic_extension(ncid,(/xdim,ydim,zdim/), &
          geostrophic_support,geostrophic_stencil_support, &
          reference_geostrophic_rms,final_geostrophic_rms, &
          ALLOCATED(result%pressure_transition_seed))) GOTO 900
      END IF
    END IF
    rc=nf90_close(ncid)
    IF (rc==NF90_NOERR) status=STATUS_OK
    RETURN
900 CONTINUE
    rc=nf90_close(ncid)
  END SUBROUTINE write_shadow_diagnostics

  LOGICAL FUNCTION put_pressure_geostrophic_extension(ncid,dims,support,stencil_support, &
                                                       before_rms,after_rms,transition_reference)
    INTEGER, INTENT(IN) :: ncid,dims(3)
    LOGICAL, INTENT(IN) :: support(:,:,:),stencil_support(:,:,:)
    REAL(real64), INTENT(IN) :: before_rms,after_rms
    LOGICAL, INTENT(IN) :: transition_reference
    INTEGER :: support_var,stencil_var
    ! Retained cells use the immutable original; new cells use an explicit seed.
    ! This diagnostic grants no scientific or native-initialization approval.
    put_pressure_geostrophic_extension=.FALSE.
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (transition_reference) THEN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_contract', &
        'pressure_geostrophic_original_seed_final_v3'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_reference', &
        'original_retained_seed_added_cells_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'reference_full_geostrophic_rms',before_rms))) RETURN
    ELSE
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_contract', &
        'pressure_geostrophic_original_final_v2'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'original_full_geostrophic_rms',before_rms))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_scope', &
      'balance_support_union_phi_support_horizontal_cross_halo_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_units','m s-2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_science_assessed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_requested_cells', &
      INT(COUNT(support),int32)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_evaluated_cells', &
      INT(COUNT(stencil_support),int32)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geostrophic_partial_coverage', &
      MERGE(1_int32,0_int32,ANY(support .AND. .NOT.stencil_support))))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'candidate_full_geostrophic_rms',after_rms))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'geostrophic_validation_support',NF90_INT,dims,support_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,support_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,support_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'geostrophic_stencil_support',NF90_INT,dims,stencil_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,stencil_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,stencil_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,support_var,MERGE(1_int32,0_int32,support)))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,stencil_var,MERGE(1_int32,0_int32,stencil_support)))) RETURN
    put_pressure_geostrophic_extension=.TRUE.
  END FUNCTION put_pressure_geostrophic_extension

  LOGICAL FUNCTION put_pressure_candidate_extension(ncid,dims,background,candidate,result,config)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid,dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER :: support_var,reference_var
    LOGICAL :: surface_variant,model_dynamics
    put_pressure_candidate_extension=.FALSE.
    model_dynamics=config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS
    IF (.NOT.put_thermo_field(ncid,dims,'original_omega_target',background%omega_target)) RETURN
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (model_dynamics) THEN
      ! The model branch is an increment experiment.  This extension may be
      ! requested by the pressure-analysis caller, but it must not relabel the
      ! paired-model target as an observational or physical-boundary product.
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_analysis_candidate_contract', &
        'pressure_analysis_candidate_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract','model_dynamics_shadow_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class', &
        'MODEL_DYNAMICS_SHADOW_PROPOSAL'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id','model-dynamics-shadow-v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_boundary_provenance', &
        'HOMOGENEOUS_MODEL_INCREMENT_PRESERVE_BASELINE'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'boundary_mode', &
        'ZERO_INCREMENT_PRESERVE_BASELINE'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'boundary_increment_contract', &
        BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'physical_continuity_assessed', &
        0_int32))) RETURN
    ELSE
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_analysis_candidate_contract', &
        'pressure_analysis_candidate_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract','pressure_analysis_shadow_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class', &
        'PRESSURE_ANALYSIS_SHADOW_PROPOSAL'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id','pressure-analysis-shadow-v1'))) RETURN
      IF (physical_boundary_contract_valid(background)) THEN
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_boundary_provenance', &
          'PHYSICAL_INPUT_DIAGNOSTIC_ONLY'))) RETURN
      END IF
    END IF
    IF (ALLOCATED(result%geopotential_support)) THEN
      surface_variant=ANY(result%geopotential_reference_level==0 .AND. &
        ANY(result%geopotential_support,DIM=3))
      IF (surface_variant) THEN
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geopotential_contract', &
          PRESSURE_GEOPOTENTIAL_CONTRACT_SURFACE))) RETURN
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geopotential_reference', &
          PRESSURE_GEOPOTENTIAL_REFERENCE_SURFACE))) RETURN
      ELSE
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geopotential_contract', &
          PRESSURE_GEOPOTENTIAL_CONTRACT_V1))) RETURN
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geopotential_reference', &
          PRESSURE_GEOPOTENTIAL_REFERENCE_V1))) RETURN
      END IF
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geopotential_native_assessed', &
        0_int32))) RETURN
      IF (surface_variant) THEN
        IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL, &
          PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTR, &
          PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE))) RETURN
      END IF
      IF (.NOT.nc_ok(nf90_def_var(ncid,'geopotential_support',NF90_INT,dims,support_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'geopotential_reference_level',NF90_INT, &
        (/dims(1),dims(2)/),reference_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,support_var,1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,reference_var,1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,support_var,'units','1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,reference_var,'units','1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,reference_var,'index_base',1_int32))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,reference_var,'inactive_value',0_int32))) RETURN
      IF (surface_variant) THEN
        IF (.NOT.nc_ok(nf90_put_att(ncid,reference_var,'semantics', &
          PRESSURE_GEOPOTENTIAL_REFERENCE_SURFACE))) RETURN
      ELSE
        IF (.NOT.nc_ok(nf90_put_att(ncid,reference_var,'semantics', &
          PRESSURE_GEOPOTENTIAL_REFERENCE_V1))) RETURN
      END IF
    END IF
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (ALLOCATED(result%geopotential_support)) THEN
      IF (.NOT.nc_ok(nf90_put_var(ncid,support_var, &
        MERGE(1_int32,0_int32,result%geopotential_support)))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,reference_var, &
        result%geopotential_reference_level))) RETURN
      IF (.NOT.put_thermo_field(ncid,dims,'background_geopotential', &
        background%geopotential)) RETURN
      IF (.NOT.put_thermo_field(ncid,dims,'candidate_geopotential', &
        candidate%geopotential)) RETURN
    END IF
    put_pressure_candidate_extension=.TRUE.
  END FUNCTION put_pressure_candidate_extension

  LOGICAL FUNCTION put_pressure_geometry_extension(ncid,surface_dims,volume_dims, &
                                                    interface_dims,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    INTEGER, INTENT(IN) :: ncid,surface_dims(2),volume_dims(3),interface_dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER :: requested_var,interface_var,cell_dp_var,pressure_mass_var,dry_mass_var
    INTEGER :: rc

    put_pressure_geometry_extension=.FALSE.
    IF (.NOT.ALLOCATED(result%requested_surface_pressure)) RETURN
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_geometry_contract', &
      'prescribed_surface_pressure_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_geometry_scope', &
      'candidate_balance_stage_geometry_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_species_change_kg', &
      result%geometry_budget%species_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_mixing_ratio_change_kg', &
      result%geometry_budget%mixing_ratio_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_dry_mass_redistribution_kg', &
      result%geometry_budget%dry_mass_redistribution_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_dry_air_change_kg', &
      result%geometry_budget%dry_air_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_enthalpy_change_j', &
      result%geometry_budget%enthalpy_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_geometry_mass_change_kg', &
      result%geometry_budget%geometry_mass_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_enthalpy_composition_change_j', &
      result%geometry_budget%enthalpy_composition_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_enthalpy_mass_metric_change_j', &
      result%geometry_budget%enthalpy_mass_metric_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_total_mass_error_kg', &
      result%geometry_budget%total_mass_error_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_max_cell_mass_error_kg', &
      result%geometry_budget%max_cell_mass_error_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_accounted_cells', &
      result%geometry_budget%accounted_cells))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_incomplete_background_cells', &
      result%geometry_budget%incomplete_background_cells))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geometry_analysis_incomplete_candidate_cells', &
      result%geometry_budget%incomplete_candidate_cells))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'requested_surface_pressure',NF90_DOUBLE, &
      surface_dims,requested_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_pressure_interface',NF90_DOUBLE, &
      interface_dims,interface_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_cell_dp',NF90_DOUBLE, &
      volume_dims,cell_dp_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_pressure_mass_measure',NF90_DOUBLE, &
      volume_dims,pressure_mass_var))) RETURN
    rc=nf90_inq_varid(ncid,'candidate_dry_air_mass_measure',dry_mass_var)
    IF (rc==NF90_ENOTVAR) THEN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_dry_air_mass_measure',NF90_DOUBLE, &
        volume_dims,dry_mass_var))) RETURN
    ELSE IF (rc/=NF90_NOERR) THEN
      RETURN
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,requested_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,interface_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,cell_dp_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,pressure_mass_var,'units','kg')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,dry_mass_var,'units','kg dryair'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,requested_var,1,1,1)) .OR. &
        .NOT.nc_ok(nf90_def_var_deflate(ncid,interface_var,1,1,1)) .OR. &
        .NOT.nc_ok(nf90_def_var_deflate(ncid,cell_dp_var,1,1,1)) .OR. &
        .NOT.nc_ok(nf90_def_var_deflate(ncid,pressure_mass_var,1,1,1))) RETURN
    IF (rc==NF90_ENOTVAR) THEN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,dry_mass_var,1,1,1))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,requested_var,result%requested_surface_pressure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,interface_var,candidate%grid%pressure_interface)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,cell_dp_var,candidate%grid%cell_dp)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,pressure_mass_var,candidate%grid%pressure_mass_measure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,dry_mass_var,candidate%grid%dry_air_mass_measure))) RETURN
    put_pressure_geometry_extension=.TRUE.
  END FUNCTION put_pressure_geometry_extension

  LOGICAL FUNCTION put_pressure_transition_extension(ncid,surface_dims,volume_dims, &
                                                       background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    INTEGER, INTENT(IN) :: ncid,surface_dims(2),volume_dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER :: candidate_domain_var,seed_domain_var,dry_mass_var

    put_pressure_transition_extension=.FALSE.
    IF (.NOT.ALLOCATED(result%pressure_transition_seed)) RETURN
    ASSOCIATE(seed=>result%pressure_transition_seed)
      IF (.NOT.ALLOCATED(candidate%above_ground) .OR. &
          .NOT.ALLOCATED(seed%above_ground) .OR. &
          .NOT.ALLOCATED(seed%grid%dry_air_mass_measure)) RETURN
      IF (ANY(SHAPE(candidate%above_ground)/= &
          (/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/)) .OR. &
          ANY(SHAPE(seed%above_ground)/= &
            (/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/)) .OR. &
          ANY(SHAPE(seed%grid%dry_air_mass_measure)/= &
            (/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/))) RETURN
      IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_transition_contract', &
        'pressure_transition_seed_v2'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL, &
        'pressure_transition_support_semantics', &
        'background_support_plus_candidate_new_cells_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_above_ground',NF90_INT, &
        volume_dims,candidate_domain_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'transition_seed_above_ground',NF90_INT, &
        volume_dims,seed_domain_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'transition_seed_dry_air_mass_measure', &
        NF90_DOUBLE,volume_dims,dry_mass_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,candidate_domain_var,1,1,1)) .OR. &
          .NOT.nc_ok(nf90_def_var_deflate(ncid,seed_domain_var,1,1,1)) .OR. &
          .NOT.nc_ok(nf90_def_var_deflate(ncid,dry_mass_var,1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,candidate_domain_var,'units','1')) .OR. &
          .NOT.nc_ok(nf90_put_att(ncid,seed_domain_var,'units','1')) .OR. &
          .NOT.nc_ok(nf90_put_att(ncid,dry_mass_var,'units','kg dryair'))) RETURN
      IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,candidate_domain_var, &
        MERGE(1_int32,0_int32,candidate%above_ground))) .OR. &
          .NOT.nc_ok(nf90_put_var(ncid,seed_domain_var, &
            MERGE(1_int32,0_int32,seed%above_ground))) .OR. &
          .NOT.nc_ok(nf90_put_var(ncid,dry_mass_var,seed%grid%dry_air_mass_measure))) RETURN
      IF (.NOT.put_surface_field(ncid,surface_dims,'transition_seed_surface_pressure', &
        seed%surface_pressure)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_pressure',seed%pressure)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_temperature',seed%temperature)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_vapor',seed%vapor)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_cloud_water', &
        seed%cloud_water)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_cloud_ice',seed%cloud_ice)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_rain',seed%rain)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_snow',seed%snow)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_graupel',seed%graupel)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_u',seed%u)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_v',seed%v)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_omega',seed%omega)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_seed_geopotential', &
        seed%geopotential)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_background_pressure', &
        background%pressure)) RETURN
      IF (.NOT.put_thermo_field(ncid,volume_dims,'transition_candidate_pressure', &
        candidate%pressure)) RETURN
      put_pressure_transition_extension=.TRUE.
    END ASSOCIATE
  END FUNCTION put_pressure_transition_extension

  LOGICAL FUNCTION put_dry_air_flux_extension(ncid,dims,background,candidate,config,variable_geometry)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid,dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    LOGICAL, INTENT(IN) :: variable_geometry
    TYPE(balance_operator_type) :: background_op,candidate_op
    TYPE(cloud_bal_state_type) :: background_for_flux
    REAL(real64), ALLOCATABLE :: before(:,:,:),after(:,:,:),original_continuity(:,:,:)
    INTEGER :: ids(2),continuity_var,status,reason,i
    CHARACTER(LEN=64) :: dry_flux_contract
    CHARACTER(LEN=40), PARAMETER :: names(2)=[CHARACTER(LEN=40) :: &
      'background_dry_air_flux_divergence','candidate_dry_air_flux_divergence']

    put_dry_air_flux_extension=.FALSE.
    ! Persist the represented advective term, not an invented mass tendency.
    ! A prescribed PSFC request owns candidate geometry, so each state must be
    ! evaluated with its own pressure-coordinate operator. The legacy path
    ! intentionally keeps its fixed-geometry behavior unchanged.
    CALL build_balance_operator(candidate,config%balance,candidate_op,status,reason)
    IF (status/=STATUS_OK) RETURN
    IF (variable_geometry) THEN
      ! Keep the candidate-side diagnostic support mask while rebuilding the
      ! original operator on original pressure geometry.
      background_for_flux=background
      background_for_flux%balance_beta=candidate%balance_beta
      CALL build_balance_operator(background_for_flux,config%balance,background_op,status,reason)
    ELSE
      ! Preserve the legacy fixed-geometry operator authority exactly.
      CALL build_balance_operator(candidate,config%balance,background_op,status,reason)
    END IF
    IF (status/=STATUS_OK) RETURN
    ALLOCATE(before(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
             after(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz))
    IF (variable_geometry) ALLOCATE(original_continuity(candidate%grid%nx, &
                                                        candidate%grid%ny, &
                                                        candidate%grid%nz))
    CALL state_dry_air_mass_flux_divergence(background_op,background,before,status)
    IF (status/=STATUS_OK) RETURN
    CALL state_dry_air_mass_flux_divergence(candidate_op,candidate,after,status)
    IF (status/=STATUS_OK) RETURN
    IF (variable_geometry) THEN
      CALL state_continuity_residual(background_op,background,original_continuity,status)
      IF (status/=STATUS_OK) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    dry_flux_contract=PRESSURE_DRY_AIR_FLUX_CONTRACT_FIXED
    IF (variable_geometry) dry_flux_contract=PRESSURE_DRY_AIR_FLUX_CONTRACT_STATE
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'dry_air_flux_contract', &
      TRIM(dry_flux_contract)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'dry_air_flux_boundary', &
      'nearest_interior_composition'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'dry_air_mass_tendency_assessed',0))) RETURN
    DO i=1,2
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(i)),NF90_DOUBLE,dims,ids(i)))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,ids(i),1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,ids(i),'units','kg s-1'))) RETURN
    END DO
    IF (variable_geometry) THEN
      IF (.NOT.nc_ok(nf90_def_var(ncid,'continuity_original_background',NF90_DOUBLE, &
        dims,continuity_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,continuity_var,1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,continuity_var,'units','s-1'))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(1),before))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(2),after))) RETURN
    IF (variable_geometry) THEN
      IF (.NOT.nc_ok(nf90_put_var(ncid,continuity_var,original_continuity))) RETURN
    END IF
    put_dry_air_flux_extension=.TRUE.
  END FUNCTION put_dry_air_flux_extension

  LOGICAL FUNCTION put_radar_reconstruction_inputs(ncid,dims,background,config)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid,dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    CHARACTER(LEN=40), PARAMETER :: names(4)=[CHARACTER(LEN=40) :: &
      'background_precipitation_phase','background_precipitation_phase_valid', &
      'background_precipitation_phase_quality','background_precipitation_phase_source']
    CHARACTER(LEN=40), PARAMETER :: fraction_names(4)=[CHARACTER(LEN=40) :: &
      'background_cloud_fraction','background_cloud_fraction_valid', &
      'background_cloud_fraction_quality','background_cloud_fraction_source']
    CHARACTER(LEN=40), PARAMETER :: type_names(4)=[CHARACTER(LEN=40) :: &
      'background_cloud_type','background_cloud_type_valid', &
      'background_cloud_type_quality','background_cloud_type_source']
    INTEGER :: ids(4),fraction_ids(4),type_ids(4),i
    LOGICAL :: cloud_present
    put_radar_reconstruction_inputs=.FALSE.
    cloud_present=cloud_provenance_present(background)
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_reconstruction_contract', &
      'pressure_radar_reconstruction_v2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'column_minimum_dbz',config%column%minimum_dbz))) RETURN
    DO i=1,4
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(i)),NF90_INT,dims,ids(i)))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,ids(i),1,1,1))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,ids(i),'units','1'))) RETURN
    END DO
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids(1),'valid_time',background%precipitation_phase%valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids(1),'code_table',TRIM(background%precipitation_phase%code_table)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids(2),'mask_encoding','0=invalid,1=valid'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids(3),'mask_encoding','canonical_quality_bits_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids(4),'mask_encoding','canonical_source_bits_v1'))) RETURN
    IF (cloud_present) THEN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_present',1_int32))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_contract', &
        'cloud_analysis_provenance_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_mask_encoding', &
        'valid:0=invalid,1=valid;quality:canonical_quality_bits_v1;source:canonical_source_bits_v1'))) RETURN
      DO i=1,4
        IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(fraction_names(i)), &
          MERGE(NF90_FLOAT,NF90_INT,i==1),dims,fraction_ids(i)))) RETURN
        IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,fraction_ids(i),1,1,1))) RETURN
        IF (.NOT.nc_ok(nf90_put_att(ncid,fraction_ids(i),'units','1'))) RETURN
      END DO
      IF (.NOT.nc_ok(nf90_put_att(ncid,fraction_ids(1),'valid_time', &
        background%cloud_fraction%valid_time))) RETURN
      DO i=1,4
        IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(type_names(i)),NF90_INT,dims,type_ids(i)))) RETURN
        IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,type_ids(i),1,1,1))) RETURN
        IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(i),'units','1'))) RETURN
      END DO
      IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(1),'valid_time', &
        background%cloud_type%valid_time))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(1),'code_table', &
        TRIM(background%cloud_type%code_table)))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,fraction_ids(2),'mask_encoding','0=invalid,1=valid'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,fraction_ids(3),'mask_encoding','canonical_quality_bits_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,fraction_ids(4),'mask_encoding','canonical_source_bits_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(2),'mask_encoding','0=invalid,1=valid'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(3),'mask_encoding','canonical_quality_bits_v1'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,type_ids(4),'mask_encoding','canonical_source_bits_v1'))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(1),background%precipitation_phase%value))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(2), &
      MERGE(1_int32,0_int32,background%precipitation_phase%valid)))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(3),background%precipitation_phase%quality))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,ids(4),background%precipitation_phase%source))) RETURN
    IF (cloud_present) THEN
      IF (.NOT.nc_ok(nf90_put_var(ncid,fraction_ids(1),background%cloud_fraction%value))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,fraction_ids(2), &
        MERGE(1_int32,0_int32,background%cloud_fraction%valid)))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,fraction_ids(3),background%cloud_fraction%quality))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,fraction_ids(4),background%cloud_fraction%source))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,type_ids(1),background%cloud_type%value))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,type_ids(2), &
        MERGE(1_int32,0_int32,background%cloud_type%valid)))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,type_ids(3),background%cloud_type%quality))) RETURN
      IF (.NOT.nc_ok(nf90_put_var(ncid,type_ids(4),background%cloud_type%source))) RETURN
    END IF
    put_radar_reconstruction_inputs=.TRUE.
  END FUNCTION put_radar_reconstruction_inputs

  LOGICAL FUNCTION put_outer_extension(ncid,result,config)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER :: count
    put_outer_extension=.FALSE.
    count=result%outer_iterations
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'diagnostic_schema_version',8))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract','real_radar_thermo_shadow_v3'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id','pressure-thermo-shadow-v3'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'schema_extensions', &
      'verified_operational_identity_v1,radar_no_echo_masks_v1,'// &
      'pressure_geometry_v2,omega_boundary_contract_v2,pressure_thermo_v1,pressure_analysis_v1,pressure_outer_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_contract', &
      'pressure_fixed_feedback_producer_replay_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_maximum_iterations',config%maximum_outer_iterations))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_iterations',count))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_converged',1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_feedback_fields','temperature,vapor,u,v,omega'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_feedback_units', &
      'K,kg kg-1 dryair,m s-1,m s-1,Pa s-1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'outer_max_abs_delta', &
      RESHAPE(result%outer_max_abs_delta(:,1:count),[5*count])))) RETURN
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    put_outer_extension=.TRUE.
  END FUNCTION put_outer_extension

  LOGICAL FUNCTION put_thermo_extension(ncid,dims,background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    INTEGER, INTENT(IN) :: ncid,dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER :: support_var,surface_var,mass_var
    put_thermo_extension=.FALSE.
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'thermo_support',NF90_INT,dims,support_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'thermo_surface',NF90_INT,dims,surface_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'candidate_dry_air_mass_measure', &
      NF90_DOUBLE,dims,mass_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,support_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,surface_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,mass_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,support_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,surface_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,mass_var,'units','kg dryair'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'diagnostic_schema_version',7))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract','real_radar_thermo_shadow_v2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class','PRESSURE_THERMO_SHADOW_PROPOSAL'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id','pressure-thermo-shadow-v2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'schema_extensions', &
      'verified_operational_identity_v1,radar_no_echo_masks_v1,'// &
      'pressure_geometry_v2,omega_boundary_contract_v2,pressure_thermo_v1,pressure_analysis_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_contract', &
      'pressure_fixed_represented_mixture_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_species_change_kg', &
      result%analysis_budget%species_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_mixing_ratio_change_kg', &
      result%analysis_budget%mixing_ratio_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_dry_mass_redistribution_kg', &
      result%analysis_budget%dry_mass_redistribution_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_dry_air_change_kg', &
      result%analysis_budget%dry_air_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_enthalpy_change_j', &
      result%analysis_budget%enthalpy_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_total_mass_error_kg', &
      result%analysis_budget%total_mass_error_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_max_cell_mass_error_kg', &
      result%analysis_budget%max_cell_mass_error_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_accounted_cells', &
      result%analysis_budget%accounted_cells))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_incomplete_background_cells', &
      result%analysis_budget%incomplete_background_cells))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'analysis_incomplete_candidate_cells', &
      result%analysis_budget%incomplete_candidate_cells))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_contract', &
      'explicit_cloud_saturation_mixture_v1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_target_rh',result%thermo_target_rh))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_species_change_kg', &
      result%thermo_budget%species_change_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_sensible_change_j', &
      result%thermo_budget%sensible_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_phase_change_j', &
      result%thermo_budget%phase_change_j))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_water_error_kg', &
      result%thermo_budget%water_error_kg))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'thermo_enthalpy_error_j', &
      result%thermo_budget%enthalpy_error_j))) RETURN
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,support_var,MERGE(1_int32,0_int32,result%thermo_support)))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,surface_var,result%thermo_surface))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,mass_var,candidate%grid%dry_air_mass_measure))) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_temperature',background%temperature)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_temperature',candidate%temperature)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_vapor',background%vapor)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_vapor',candidate%vapor)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_cloud_water',background%cloud_water)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_cloud_water',candidate%cloud_water)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_cloud_ice',background%cloud_ice)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_cloud_ice',candidate%cloud_ice)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_rain',background%rain)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_rain',candidate%rain)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_snow',background%snow)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_snow',candidate%snow)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'background_graupel',background%graupel)) RETURN
    IF (.NOT.put_thermo_field(ncid,dims,'candidate_graupel',candidate%graupel)) RETURN
    put_thermo_extension=.TRUE.
  END FUNCTION put_thermo_extension

  LOGICAL FUNCTION put_thermo_field(ncid,dims,name,field)
    INTEGER, INTENT(IN) :: ncid,dims(3)
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field3d), INTENT(IN) :: field
    INTEGER :: value_var,valid_var,quality_var,source_var,allocation_status
    INTEGER(int32), ALLOCATABLE :: valid_mask(:,:,:)
    put_thermo_field=.FALSE.
    ALLOCATE(valid_mask(SIZE(field%valid,1),SIZE(field%valid,2),SIZE(field%valid,3)), &
      STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    valid_mask=MERGE(1_int32,0_int32,field%valid)
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    ! Hydrometeor value arrays already exist in the base diagnostic schema.
    IF (nf90_inq_varid(ncid,name,value_var)/=NF90_NOERR) THEN
      IF (.NOT.nc_ok(nf90_def_var(ncid,name,NF90_FLOAT,dims,value_var))) RETURN
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,value_var,1,1,1))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,value_var,'units',TRIM(field%unit)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,value_var,'valid_time',field%valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_valid',NF90_INT,dims,valid_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_quality',NF90_INT,dims,quality_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_source',NF90_INT,dims,source_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,valid_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,quality_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,source_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,valid_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,quality_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,source_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,value_var,field%value))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,valid_var,valid_mask))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,quality_var,field%quality))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,source_var,field%source))) RETURN
    put_thermo_field=.TRUE.
  END FUNCTION put_thermo_field

  LOGICAL FUNCTION put_surface_field(ncid,dims,name,field)
    INTEGER, INTENT(IN) :: ncid,dims(2)
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field2d), INTENT(IN) :: field
    INTEGER :: value_var,valid_var,quality_var,source_var,allocation_status
    INTEGER(int32), ALLOCATABLE :: valid_mask(:,:)
    put_surface_field=.FALSE.
    ALLOCATE(valid_mask(SIZE(field%valid,1),SIZE(field%valid,2)), &
      STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    valid_mask=MERGE(1_int32,0_int32,field%valid)
    IF (.NOT.nc_ok(nf90_redef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name,NF90_FLOAT,dims,value_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_valid',NF90_INT,dims,valid_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_quality',NF90_INT,dims,quality_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,name//'_source',NF90_INT,dims,source_var))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,value_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,valid_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,quality_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,source_var,1,1,1))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,value_var,'units',TRIM(field%unit)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,value_var,'valid_time',field%valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,valid_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,quality_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,source_var,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_enddef(ncid))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,value_var,field%value))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,valid_var,valid_mask))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,quality_var,field%quality))) RETURN
    IF (.NOT.nc_ok(nf90_put_var(ncid,source_var,field%source))) RETURN
    put_surface_field=.TRUE.
  END FUNCTION put_surface_field

  SUBROUTINE validate_shadow_write_contract(state_in,candidate,operational_state, &
                                            result,config,status,reason,pressure_analysis_candidate)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate,operational_state
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER, INTENT(OUT) :: status,reason
    LOGICAL, INTENT(IN), OPTIONAL :: pressure_analysis_candidate
    LOGICAL :: pressure_candidate,variable_geometry,transition,cloud_present
    INTEGER :: state_status,state_reason
    REAL(real64) :: flux_terms(7),flux_accounted,flux_error,flux_limit

    status=STATUS_FAILED; reason=REASON_AUTHORITY
    pressure_candidate=.FALSE.
    transition=ALLOCATED(result%pressure_transition_seed)
    ! Serialization binds a candidate to its producing pipeline. Independent
    ! physical validation and publication remain separate downstream gates.
    IF (ALLOCATED(result%thermo_support).NEQV.ALLOCATED(result%thermo_surface)) RETURN
    variable_geometry=ALLOCATED(result%requested_surface_pressure)
    ! The existing sidecar stores only background pressure geometry. Variable
    ! geometry is admitted solely through the explicit prescribed-PSFC path.
    IF (.NOT.variable_geometry) THEN
      IF (.NOT.ieee_is_finite(result%geometry_budget%geometry_mass_change_kg)) RETURN
      IF (result%geometry_budget%geometry_mass_change_kg/=0.0_real64) RETURN
    ELSE
      IF (.NOT.pressure_geometry_request_valid(state_in,candidate,result)) THEN
        reason=REASON_METADATA
        RETURN
      END IF
    END IF
    IF (PRESENT(pressure_analysis_candidate)) pressure_candidate=pressure_analysis_candidate
    IF (config%requested_mode/=MODE_SHADOW .OR. &
        result%requested_mode/=MODE_SHADOW .OR. &
        (config%balance%target_authority/=TARGET_AUTHORITY_OBSERVATIONAL .AND. &
         config%balance%target_authority/=TARGET_AUTHORITY_MODEL_DYNAMICS)) RETURN
    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      ! A writer cannot turn an absent or contaminated paired target into a
      ! physical proposal. Both endpoints must retain the model authority.
      IF (.NOT.ANY(target_is_resolved(state_in,TARGET_AUTHORITY_MODEL_DYNAMICS)) .OR. &
          .NOT.ANY(target_is_resolved(candidate,TARGET_AUTHORITY_MODEL_DYNAMICS))) THEN
        reason=REASON_AUTHORITY
        RETURN
      END IF
      IF (config%balance%boundary_increment_contract/= &
          BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL .OR. &
          .NOT.model_target_coverage_contract_valid(state_in) .OR. &
          .NOT.model_target_coverage_contract_valid(candidate) .OR. &
          .NOT.model_target_coverage_contract_valid(operational_state)) THEN
        reason=REASON_AUTHORITY
        RETURN
      END IF
    END IF
    IF (config%maximum_outer_iterations<1 .OR. config%maximum_outer_iterations>32) RETURN
    IF (ANY(.NOT.ieee_is_finite(result%outer_max_abs_delta))) RETURN
    IF (variable_geometry .AND. &
        (config%maximum_outer_iterations/=1 .OR. &
         .NOT.ALLOCATED(result%thermo_support) .OR. &
         .NOT.ALLOCATED(result%thermo_surface))) THEN
      ! The prescribed-PSFC extension is an explicit schema-7, single-pass
      ! thermo artifact.  Do not create a schema-5/8 file with a partial
      ! geometry extension when the coupled thermo payload is unavailable.
      reason=REASON_METADATA
      RETURN
    END IF
    IF (config%maximum_outer_iterations==1) THEN
      IF (result%outer_iterations<0 .OR. result%outer_iterations>1 .OR. result%outer_converged .OR. &
          ANY(result%outer_max_abs_delta/=0.0_real64)) RETURN
    ELSE
      ! Schema 8 needs explicit thermo fields and an accepted bounded solve.
      IF (.NOT.ALLOCATED(result%thermo_support)) RETURN
      IF (.NOT.result%outer_converged .OR. result%status/=STATUS_OK) RETURN
      IF (result%outer_iterations<1 .OR. &
          result%outer_iterations>config%maximum_outer_iterations) RETURN
      IF (ANY(result%outer_max_abs_delta<0.0_real64)) RETURN
    END IF
    IF (.NOT.column_config_valid(config%column)) THEN
      reason=REASON_RANGE
      RETURN
    END IF
    IF (.NOT.pressure_geopotential_request_valid(state_in,candidate,result, &
                                                 pressure_candidate,variable_geometry)) RETURN
    IF (.NOT.pipeline_result_is_coherent(result)) RETURN
    ! If no request was accepted, a candidate Phi mutation is never hidden.
    IF (.NOT.ALLOCATED(result%geopotential_support) .AND. &
        .NOT.geopotential_is_unchanged(state_in,candidate)) RETURN
    flux_terms=[result%column%numerical%flux_deposited, &
      result%column%numerical%flux_suspended, &
      result%column%numerical%flux_boundary_exit, &
      result%column%numerical%flux_terrain_intercept, &
      result%column%numerical%flux_observation_blocked, &
      result%column%numerical%flux_no_echo_blocked, &
      result%column%numerical%flux_microphysical_loss]
    IF (.NOT.ieee_is_finite(result%column%numerical%flux_input) .OR. &
        result%column%numerical%flux_input<0.0_real64 .OR. &
        ANY(.NOT.ieee_is_finite(flux_terms)) .OR. ANY(flux_terms<0.0_real64) .OR. &
        .NOT.ieee_is_finite(result%column%numerical%ledger_error) .OR. &
        result%column%numerical%ledger_error<0.0_real64) THEN
      reason=REASON_GATE
      RETURN
    END IF
    flux_accounted=SUM(flux_terms)
    flux_error=ABS(result%column%numerical%flux_input-flux_accounted)
    flux_limit=config%column%ledger_absolute_tolerance+ &
      config%column%ledger_relative_tolerance* &
      MAX(ABS(result%column%numerical%flux_input),ABS(flux_accounted))
    IF (flux_error>flux_limit .OR. &
        ABS(result%column%numerical%ledger_error-flux_error)> &
          64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,flux_error) .OR. &
        result%column%numerical%transport_required_substeps<0 .OR. &
        result%column%numerical%transport_required_substeps> &
          config%column%maximum_transport_substeps) THEN
      reason=REASON_GATE
      RETURN
    END IF
    IF (.NOT.stage_masks_valid(result,state_in%grid%nx,state_in%grid%ny, &
                              state_in%grid%nz)) THEN
      reason=REASON_SHAPE
      RETURN
    END IF

    CALL validate_canonical_state(state_in,.FALSE.,.TRUE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    IF (.NOT.writer_geometry_is_representable(state_in)) THEN
      reason=REASON_METADATA
      RETURN
    END IF
    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      IF (.NOT.boundary_contract_valid(state_in) .OR. &
          .NOT.boundary_contract_valid(candidate) .OR. &
          .NOT.boundary_contract_valid(operational_state) .OR. &
          .NOT.model_boundary_increment_contract_valid(state_in,candidate) .OR. &
          .NOT.model_boundary_increment_contract_valid(state_in,operational_state)) THEN
        reason=REASON_AUTHORITY
        RETURN
      END IF
    ELSE IF (.NOT.copied_diagnostic_boundary_contract_valid(state_in) .OR. &
             .NOT.copied_diagnostic_boundary_contract_valid(candidate) .OR. &
             .NOT.copied_diagnostic_boundary_contract_valid(operational_state)) THEN
      reason=REASON_METADATA
      IF (.NOT.pressure_candidate) RETURN
      IF (.NOT.physical_boundary_contract_valid(state_in) .OR. &
          .NOT.physical_boundary_contract_valid(candidate) .OR. &
          .NOT.physical_boundary_contract_valid(operational_state)) RETURN
      reason=REASON_AUTHORITY
    END IF
    IF (.NOT.real_radar_contract_valid(state_in) .OR. &
        .NOT.real_radar_contract_valid(candidate) .OR. &
        .NOT.real_radar_contract_valid(operational_state)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    IF (.NOT.los_is_empty(state_in%radar_los) .OR. &
        .NOT.los_is_empty(candidate%radar_los) .OR. &
        .NOT.los_is_empty(operational_state%radar_los)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    CALL validate_optional_cloud_pair(state_in,cloud_present,state_status,state_reason)
    IF (state_status/=STATUS_OK) RETURN
    IF (.NOT.precipitation_phase_contract_valid(state_in) .OR. &
        .NOT.precipitation_phase_contract_valid(candidate) .OR. &
        .NOT.precipitation_phase_contract_valid(operational_state)) RETURN
    cloud_present=cloud_provenance_present(state_in)
    ! The SHADOW authority boundary is stricter than ordinary state validity:
    ! operational fields must be identical and candidate changes are limited to
    ! the explicitly permitted pipeline fields.  Radar/LOS contracts are checked
    ! first so their dedicated reason code is preserved.
    IF (.NOT.canonical_states_equal(state_in,operational_state)) RETURN
    ! Cloud QC may change legitimately; the full replay below validates it.
    IF (.NOT.transition .AND. .NOT.cloud_present .AND. .NOT.ALLOCATED(result%thermo_support)) THEN
      IF (.NOT.thermo_candidate_is_coherent(state_in,candidate,result)) RETURN
    END IF
    CALL validate_canonical_state(candidate,.FALSE.,.TRUE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    IF (.NOT.transition .AND. .NOT.cloud_present .AND. ALLOCATED(result%thermo_support)) THEN
      IF (.NOT.thermo_candidate_is_coherent(state_in,candidate,result)) RETURN
    END IF
    CALL validate_canonical_state(operational_state,.FALSE.,.TRUE.,state_status, &
                                  state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    IF (state_has_manufactured_source(state_in) .OR. &
        state_has_manufactured_source(candidate) .OR. &
        state_has_manufactured_source(operational_state)) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (transition) THEN
      CALL validate_canonical_state(result%pressure_transition_seed,.FALSE.,.TRUE., &
        state_status,state_reason,.FALSE.)
      IF (state_status/=STATUS_OK) THEN
        reason=state_reason
        RETURN
      END IF
      IF (state_has_manufactured_source(result%pressure_transition_seed)) RETURN
    END IF
    ! Remap and cloud diagnostics need the full pipeline replay. The radar-only
    ! shortcut treats every no-echo diagnostic change as a precipitation change.
    IF (.NOT.transition .AND. .NOT.cloud_present) THEN
      IF (.NOT.candidate_result_is_coherent(state_in,candidate,result)) RETURN
    END IF
    IF (transition .OR. config%maximum_outer_iterations>1 .OR. pressure_candidate .OR. &
        variable_geometry .OR. cloud_present) THEN
      IF (.NOT.pipeline_result_replays(state_in,candidate,result,config)) RETURN
    END IF

    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_shadow_write_contract

  LOGICAL FUNCTION pipeline_result_replays(background,candidate,result,config)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config,run_cloud_bal_pipeline
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    TYPE(cloud_bal_state_type) :: replay,operational
    TYPE(cloud_bal_pipeline_result) :: replay_result
    LOGICAL, ALLOCATABLE :: requested_support(:,:,:)
    ! Producer replay verifies lineage, not an independent scientific oracle.
    ! Every trial remains anchored to the supplied immutable background.
    pipeline_result_replays=.FALSE.
    IF (ALLOCATED(result%thermo_support).NEQV.ALLOCATED(result%thermo_surface)) RETURN
    IF (ALLOCATED(result%geopotential_support).NEQV. &
        ALLOCATED(result%geopotential_reference_level)) RETURN
    IF (ALLOCATED(result%pressure_transition_seed)) THEN
      IF (.NOT.ALLOCATED(result%requested_surface_pressure) .OR. &
          .NOT.ALLOCATED(result%geopotential_support) .OR. &
          .NOT.ALLOCATED(result%geopotential_reference_level)) RETURN
      IF (.NOT.ALLOCATED(background%above_ground)) RETURN
      IF (ANY(SHAPE(result%geopotential_support)/=SHAPE(background%above_ground))) RETURN
      ! The receipt includes newly represented cells. The original request
      ! only covered the background; transition reconstructs the added support.
      requested_support=result%geopotential_support .AND. background%above_ground
      IF (ALLOCATED(result%thermo_support)) THEN
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          result%thermo_support,result%thermo_surface,result%thermo_target_rh, &
          requested_support,result%geopotential_reference_level, &
          result%requested_surface_pressure,result%pressure_transition_seed)
      ELSE
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          geopotential_support=requested_support, &
          geopotential_reference_level=result%geopotential_reference_level, &
          requested_surface_pressure=result%requested_surface_pressure, &
          pressure_transition_seed=result%pressure_transition_seed)
      END IF
    ELSE IF (ALLOCATED(result%thermo_support) .AND. &
        ALLOCATED(result%geopotential_support)) THEN
      IF (ALLOCATED(result%requested_surface_pressure)) THEN
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          result%thermo_support,result%thermo_surface,result%thermo_target_rh, &
          result%geopotential_support,result%geopotential_reference_level, &
          result%requested_surface_pressure)
      ELSE
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          result%thermo_support,result%thermo_surface,result%thermo_target_rh, &
          result%geopotential_support,result%geopotential_reference_level)
      END IF
    ELSE IF (ALLOCATED(result%thermo_support)) THEN
      CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
        result%thermo_support,result%thermo_surface,result%thermo_target_rh)
    ELSE IF (ALLOCATED(result%geopotential_support)) THEN
      IF (ALLOCATED(result%requested_surface_pressure)) THEN
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          geopotential_support=result%geopotential_support, &
          geopotential_reference_level=result%geopotential_reference_level, &
          requested_surface_pressure=result%requested_surface_pressure)
      ELSE
        CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config, &
          geopotential_support=result%geopotential_support, &
          geopotential_reference_level=result%geopotential_reference_level)
      END IF
    ELSE
      CALL run_cloud_bal_pipeline(background,replay,operational,replay_result,config)
    END IF
    IF (replay_result%status/=STATUS_OK) RETURN
    IF (replay_result%requested_mode/=result%requested_mode .OR. &
        replay_result%status/=result%status .OR. &
        replay_result%reason_code/=result%reason_code) RETURN
    IF (.NOT.stage_results_equal(replay_result%column,result%column) .OR. &
        .NOT.stage_results_equal(replay_result%balance,result%balance) .OR. &
        .NOT.stage_results_equal(replay_result%geopotential,result%geopotential) .OR. &
        .NOT.stage_results_equal(replay_result%overall,result%overall)) RETURN
    IF (.NOT.pressure_analysis_budgets_equal(replay_result%analysis_budget,result%analysis_budget)) RETURN
    IF (ANY(replay_result%thermo_budget%species_change_kg/=result%thermo_budget%species_change_kg) .OR. &
        replay_result%thermo_budget%sensible_change_j/=result%thermo_budget%sensible_change_j .OR. &
        replay_result%thermo_budget%phase_change_j/=result%thermo_budget%phase_change_j .OR. &
        replay_result%thermo_budget%water_error_kg/=result%thermo_budget%water_error_kg .OR. &
        replay_result%thermo_budget%enthalpy_error_j/=result%thermo_budget%enthalpy_error_j) RETURN
    IF (replay_result%outer_converged .NEQV. result%outer_converged) RETURN
    IF (replay_result%outer_iterations/=result%outer_iterations) RETURN
    IF (ANY(replay_result%outer_max_abs_delta/=result%outer_max_abs_delta)) RETURN
    IF (ALLOCATED(replay_result%thermo_support).NEQV. &
        ALLOCATED(result%thermo_support)) RETURN
    IF (ALLOCATED(replay_result%thermo_surface).NEQV. &
        ALLOCATED(result%thermo_surface)) RETURN
    IF (ALLOCATED(replay_result%thermo_support)) THEN
      IF (ANY(replay_result%thermo_support .NEQV. result%thermo_support) .OR. &
          ANY(replay_result%thermo_surface/=result%thermo_surface) .OR. &
          replay_result%thermo_target_rh/=result%thermo_target_rh) RETURN
    END IF
    IF (ALLOCATED(replay_result%requested_surface_pressure).NEQV. &
        ALLOCATED(result%requested_surface_pressure)) RETURN
    IF (ALLOCATED(replay_result%requested_surface_pressure)) THEN
      IF (ANY(replay_result%requested_surface_pressure/= &
              result%requested_surface_pressure)) RETURN
      IF (.NOT.pressure_analysis_budgets_equal(replay_result%geometry_budget, &
                                               result%geometry_budget)) RETURN
    END IF
    IF (ALLOCATED(replay_result%geopotential_support).NEQV. &
        ALLOCATED(result%geopotential_support)) RETURN
    IF (ALLOCATED(replay_result%geopotential_support)) THEN
      IF (ANY(replay_result%geopotential_support .NEQV. &
              result%geopotential_support) .OR. &
          ANY(replay_result%geopotential_reference_level/= &
              result%geopotential_reference_level)) RETURN
    END IF
    IF (.NOT.numerical_diagnostics_equal(replay_result%column%numerical, &
                                         result%column%numerical)) RETURN
    IF (.NOT.numerical_diagnostics_equal(replay_result%balance%numerical, &
                                         result%balance%numerical)) RETURN
    IF (.NOT.numerical_diagnostics_equal(replay_result%geopotential%numerical, &
                                         result%geopotential%numerical)) RETURN
    IF (.NOT.numerical_diagnostics_equal(replay_result%overall%numerical, &
                                         result%overall%numerical)) RETURN
    IF (.NOT.canonical_states_equal(background,operational)) RETURN
    IF (.NOT.canonical_states_equal(replay,candidate)) RETURN
    pipeline_result_replays=.TRUE.
  END FUNCTION pipeline_result_replays

  LOGICAL FUNCTION stage_results_equal(left,right)
    TYPE(stage_result), INTENT(IN) :: left,right
    stage_results_equal=.FALSE.
    IF (left%status/=right%status .OR. left%reason_code/=right%reason_code) RETURN
    IF (.NOT.ALLOCATED(left%changed) .OR. .NOT.ALLOCATED(right%changed)) RETURN
    IF (ANY(SHAPE(left%changed)/=SHAPE(right%changed))) RETURN
    IF (ANY(left%changed .NEQV. right%changed)) RETURN
    IF (left%coverage%required/=right%coverage%required .OR. &
        left%coverage%usable/=right%coverage%usable .OR. &
        left%coverage%excluded/=right%coverage%excluded .OR. &
        left%coverage%los_assimilated/=right%coverage%los_assimilated .OR. &
        left%coverage%los_held_out/=right%coverage%los_held_out .OR. &
        left%coverage%usable_fraction/=right%coverage%usable_fraction) RETURN
    stage_results_equal=.TRUE.
  END FUNCTION stage_results_equal

  PURE LOGICAL FUNCTION pressure_analysis_budgets_equal(left,right)
    TYPE(pressure_analysis_budget), INTENT(IN) :: left,right
    pressure_analysis_budgets_equal= &
      ALL(left%species_change_kg==right%species_change_kg) .AND. &
      ALL(left%mixing_ratio_change_kg==right%mixing_ratio_change_kg) .AND. &
      ALL(left%dry_mass_redistribution_kg==right%dry_mass_redistribution_kg) .AND. &
      left%dry_air_change_kg==right%dry_air_change_kg .AND. &
      left%enthalpy_change_j==right%enthalpy_change_j .AND. &
      left%geometry_mass_change_kg==right%geometry_mass_change_kg .AND. &
      left%enthalpy_composition_change_j==right%enthalpy_composition_change_j .AND. &
      left%enthalpy_mass_metric_change_j==right%enthalpy_mass_metric_change_j .AND. &
      left%total_mass_error_kg==right%total_mass_error_kg .AND. &
      left%max_cell_mass_error_kg==right%max_cell_mass_error_kg .AND. &
      left%accounted_cells==right%accounted_cells .AND. &
      left%incomplete_background_cells==right%incomplete_background_cells .AND. &
      left%incomplete_candidate_cells==right%incomplete_candidate_cells
  END FUNCTION pressure_analysis_budgets_equal

  PURE LOGICAL FUNCTION numerical_diagnostics_equal(left,right)
    TYPE(numerical_diagnostics), INTENT(IN) :: left,right
    numerical_diagnostics_equal=left%solver_reason==right%solver_reason .AND. &
      left%solver_iterations==right%solver_iterations .AND. &
      left%acceptance_failures==right%acceptance_failures .AND. &
      left%transport_required_substeps==right%transport_required_substeps .AND. &
      left%continuity_background_rms==right%continuity_background_rms .AND. &
      left%continuity_background_max==right%continuity_background_max .AND. &
      left%continuity_proposed_increment_rms==right%continuity_proposed_increment_rms .AND. &
      left%continuity_proposed_increment_max==right%continuity_proposed_increment_max .AND. &
      left%continuity_projected_increment_rms==right%continuity_projected_increment_rms .AND. &
      left%continuity_projected_increment_max==right%continuity_projected_increment_max .AND. &
      left%continuity_candidate_rms==right%continuity_candidate_rms .AND. &
      left%continuity_candidate_max==right%continuity_candidate_max .AND. &
      left%continuity_operator_identity_max==right%continuity_operator_identity_max .AND. &
      left%geostrophic_background_rms==right%geostrophic_background_rms .AND. &
      left%geostrophic_candidate_rms==right%geostrophic_candidate_rms .AND. &
      left%max_wind_increment==right%max_wind_increment .AND. &
      left%max_omega_increment==right%max_omega_increment .AND. &
      left%phase_error==right%phase_error .AND. &
      left%ledger_error==right%ledger_error .AND. &
      left%flux_input==right%flux_input .AND. &
      left%flux_deposited==right%flux_deposited .AND. &
      left%flux_suspended==right%flux_suspended .AND. &
      left%flux_boundary_exit==right%flux_boundary_exit .AND. &
      left%flux_terrain_intercept==right%flux_terrain_intercept .AND. &
      left%flux_observation_blocked==right%flux_observation_blocked .AND. &
      left%flux_no_echo_blocked==right%flux_no_echo_blocked .AND. &
      left%flux_microphysical_loss==right%flux_microphysical_loss .AND. &
      left%radar_analysis_increment==right%radar_analysis_increment .AND. &
      left%enthalpy_error==right%enthalpy_error .AND. &
      left%rotational_rms==right%rotational_rms .AND. &
      left%divergent_rms==right%divergent_rms .AND. &
      left%trust_region_fraction==right%trust_region_fraction .AND. &
      left%unscaled_max_wind_increment==right%unscaled_max_wind_increment .AND. &
      left%unscaled_max_omega_increment==right%unscaled_max_omega_increment .AND. &
      left%target_response_failure_fraction==right%target_response_failure_fraction
  END FUNCTION numerical_diagnostics_equal

  LOGICAL FUNCTION thermo_candidate_is_coherent(background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_state_type) :: proposal,expected
    TYPE(stage_result) :: stage
    TYPE(stage_result) :: geopotential_stage
    TYPE(water_phase_budget) :: budget
    TYPE(pressure_analysis_budget) :: analysis,geometry
    REAL(real64) :: reported(10),recomputed(10)
    REAL(real64) :: reported_analysis(22),recomputed_analysis(22)
    INTEGER :: status

    thermo_candidate_is_coherent=.FALSE.
    reported=[result%thermo_budget%species_change_kg, &
      result%thermo_budget%sensible_change_j,result%thermo_budget%phase_change_j, &
      result%thermo_budget%water_error_kg,result%thermo_budget%enthalpy_error_j]
    IF (ANY(.NOT.ieee_is_finite(reported))) RETURN
    IF (ALLOCATED(result%thermo_support).NEQV.ALLOCATED(result%thermo_surface)) RETURN
    IF (.NOT.ALLOCATED(result%thermo_support)) THEN
      IF (ANY(reported/=0.0_real64)) RETURN
      expected=background
      IF (ALLOCATED(result%geopotential_support)) THEN
        IF (ALLOCATED(result%requested_surface_pressure)) THEN
          CALL apply_pressure_hydrostatic_increment(background,expected,proposal, &
            geopotential_stage,result%geopotential_support, &
            result%geopotential_reference_level,result%requested_surface_pressure,geometry)
          IF (.NOT.pressure_analysis_budgets_equal(geometry,result%geometry_budget)) RETURN
        ELSE
          CALL apply_pressure_hydrostatic_increment(background,expected,proposal, &
            geopotential_stage,result%geopotential_support, &
            result%geopotential_reference_level)
        END IF
        IF (.NOT.stage_results_equal(geopotential_stage,result%geopotential)) RETURN
        expected=proposal
      END IF
      thermo_candidate_is_coherent=canonical_states_equal(expected,candidate,.TRUE.)
      IF (thermo_candidate_is_coherent .AND. ALLOCATED(result%requested_surface_pressure)) THEN
        thermo_candidate_is_coherent=ALL(expected%grid%dry_air_mass_measure== &
                                         candidate%grid%dry_air_mass_measure)
      END IF
      RETURN
    END IF
    IF (.NOT.ANY(result%thermo_support)) RETURN
    ! Saturation exchanges only vapor/cloud liquid/cloud ice. Pre-thermo
    ! precipitation is therefore exactly the final precipitation proposal.
    ! Reproduce the authorized transfer, not an arbitrary permission to edit T/q.
    proposal=background
    proposal%rain=candidate%rain
    proposal%snow=candidate%snow
    proposal%graupel=candidate%graupel
    CALL refresh_dry_air_mass_measure(proposal,status)
    IF (status/=STATUS_OK) RETURN
    CALL account_pressure_analysis(background,proposal,analysis,status)
    IF (status/=STATUS_OK) RETURN
    reported_analysis=[result%analysis_budget%species_change_kg, &
      result%analysis_budget%mixing_ratio_change_kg,result%analysis_budget%dry_mass_redistribution_kg, &
      result%analysis_budget%dry_air_change_kg,result%analysis_budget%enthalpy_change_j, &
      result%analysis_budget%total_mass_error_kg,result%analysis_budget%max_cell_mass_error_kg]
    recomputed_analysis=[analysis%species_change_kg,analysis%mixing_ratio_change_kg, &
      analysis%dry_mass_redistribution_kg,analysis%dry_air_change_kg,analysis%enthalpy_change_j, &
      analysis%total_mass_error_kg,analysis%max_cell_mass_error_kg]
    IF (ANY(.NOT.ieee_is_finite(reported_analysis))) RETURN
    IF (ANY(reported_analysis/=recomputed_analysis)) RETURN
    IF (result%analysis_budget%accounted_cells/=analysis%accounted_cells .OR. &
        result%analysis_budget%incomplete_background_cells/=analysis%incomplete_background_cells .OR. &
        result%analysis_budget%incomplete_candidate_cells/=analysis%incomplete_candidate_cells) RETURN
    CALL saturation_adjust_pressure_state(proposal,expected,stage, &
      result%thermo_support,result%thermo_target_rh,budget,result%thermo_surface)
    IF (stage%status/=STATUS_OK) RETURN
    IF (ALLOCATED(result%geopotential_support)) THEN
      IF (ALLOCATED(result%requested_surface_pressure)) THEN
        CALL apply_pressure_hydrostatic_increment(background,expected,proposal, &
          geopotential_stage,result%geopotential_support, &
          result%geopotential_reference_level,result%requested_surface_pressure,geometry)
        IF (.NOT.pressure_analysis_budgets_equal(geometry,result%geometry_budget)) RETURN
      ELSE
        CALL apply_pressure_hydrostatic_increment(background,expected,proposal, &
          geopotential_stage,result%geopotential_support, &
          result%geopotential_reference_level)
      END IF
      IF (.NOT.stage_results_equal(geopotential_stage,result%geopotential)) RETURN
      expected=proposal
    END IF
    IF (.NOT.canonical_states_equal(expected,candidate,.TRUE.)) RETURN
    IF (ANY(expected%grid%dry_air_mass_measure/=candidate%grid%dry_air_mass_measure)) RETURN
    recomputed=[budget%species_change_kg,budget%sensible_change_j,budget%phase_change_j, &
      budget%water_error_kg,budget%enthalpy_error_j]
    IF (ANY(reported/=recomputed)) RETURN
    thermo_candidate_is_coherent=.TRUE.
  END FUNCTION thermo_candidate_is_coherent

  LOGICAL FUNCTION state_has_manufactured_source(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER(int32), PARAMETER :: bit=SOURCE_MANUFACTURED_TEST
    state_has_manufactured_source= &
      ANY(IAND(state%pressure%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%temperature%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%vapor%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%u%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%v%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%omega%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%omega_target%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%omega_target_sigma%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%geopotential%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%cloud_fraction%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%radar_reflectivity%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%cloud_type%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%precipitation_phase%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%lightning_support%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%cloud_water%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%cloud_ice%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%rain%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%snow%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%graupel%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%vt_z_mean%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%vt_z_sigma%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%surface_pressure%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%surface_temperature%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%surface_vapor%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%surface_height%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%latitude%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%omega_top_boundary%source,bit)/=0_int32) .OR. &
      ANY(IAND(state%omega_bottom_boundary%source,bit)/=0_int32)
  END FUNCTION state_has_manufactured_source

  LOGICAL FUNCTION pipeline_result_is_coherent(result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    pipeline_result_is_coherent=.FALSE.
    IF (result%column%status/=STATUS_OK .OR. &
        result%column%reason_code/=REASON_NONE) RETURN
    IF (ALLOCATED(result%geopotential_support)) THEN
      IF (result%geopotential%status/=STATUS_OK .OR. &
          result%geopotential%reason_code/=REASON_NONE) RETURN
    END IF
    SELECT CASE(result%status)
    CASE(STATUS_OK)
      IF (result%reason_code/=REASON_NONE .OR. &
          result%balance%status/=STATUS_OK .OR. &
          result%balance%reason_code/=REASON_NONE .OR. &
          result%overall%status/=STATUS_OK .OR. &
          result%overall%reason_code/=REASON_NONE) RETURN
    CASE(STATUS_DEGRADED)
      IF (result%reason_code/=REASON_GATE .OR. &
          result%balance%status/=STATUS_DEGRADED .OR. &
          result%balance%reason_code/=REASON_GATE .OR. &
          result%overall%status/=STATUS_DEGRADED .OR. &
          result%overall%reason_code/=REASON_GATE) RETURN
    CASE DEFAULT
      RETURN
    END SELECT
    pipeline_result_is_coherent=.TRUE.
  END FUNCTION pipeline_result_is_coherent

  PURE LOGICAL FUNCTION cloud_provenance_present(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    ! Called after the existing cloud/phase contracts validate field storage.
    cloud_provenance_present=ANY(state%cloud_fraction%valid) .OR. &
      ANY(state%cloud_type%valid) .OR. &
      ANY(state%precipitation_phase%valid .AND. &
          IAND(state%precipitation_phase%source,SOURCE_CLOUD_ANALYSIS)/=0_int32)
  END FUNCTION cloud_provenance_present

  SUBROUTINE open_case_file(path,expected_z,valid_time,time_policy,ncid,levels,dx,dy, &
                            status,reftime)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(IN) :: expected_z,time_policy
    INTEGER(int64), INTENT(IN) :: valid_time
    INTEGER, INTENT(OUT) :: ncid,status
    REAL(real64), INTENT(OUT) :: levels(NZ),dx,dy
    REAL(real64), OPTIONAL, INTENT(OUT) :: reftime
    REAL(real64) :: file_time,file_reftime
    status=STATUS_FAILED; ncid=-1; levels=0.0_real64; dx=0.0_real64; dy=0.0_real64
    IF (PRESENT(reftime)) reftime=0.0_real64
    IF (.NOT.nc_ok(nf90_open(TRIM(path),NF90_NOWRITE,ncid))) THEN
      WRITE(*,'(A)') 'adapter_error=open:'//TRIM(path); RETURN
    END IF
    IF (.NOT.dimensions_are(ncid,expected_z)) THEN
      WRITE(*,'(A)') 'adapter_error=dimensions:'//TRIM(path); GOTO 900
    END IF
    IF (.NOT.read_scalar(ncid,'valtime',file_time)) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-read:'//TRIM(path); GOTO 900
    END IF
    IF (ABS(file_time-REAL(valid_time,real64))>0.5_real64) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-mismatch:'//TRIM(path); GOTO 900
    END IF
    IF (.NOT.read_scalar(ncid,'reftime',file_reftime)) THEN
      WRITE(*,'(A)') 'adapter_error=reftime-read:'//TRIM(path); GOTO 900
    END IF
    SELECT CASE(time_policy)
    CASE(TIME_POLICY_ANALYSIS)
      IF (ABS(file_reftime-REAL(valid_time,real64))>TIME_TOLERANCE_SECONDS) THEN
        WRITE(*,'(A)') 'adapter_error=reftime-mismatch:'//TRIM(path); GOTO 900
      END IF
    CASE(TIME_POLICY_FORECAST)
      IF (file_reftime-REAL(valid_time,real64)>TIME_TOLERANCE_SECONDS) THEN
        WRITE(*,'(A)') 'adapter_error=reftime-future:'//TRIM(path); GOTO 900
      END IF
    CASE DEFAULT
      WRITE(*,'(A)') 'adapter_error=reftime-policy:'//TRIM(path); GOTO 900
    END SELECT
    IF (PRESENT(reftime)) reftime=file_reftime
    IF (expected_z==NZ) THEN
      IF (.NOT.read_vector(ncid,'level',levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-read:'//TRIM(path); GOTO 900
      END IF
      IF (.NOT.levels_are_native(levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-order:'//TRIM(path); GOTO 900
      END IF
    END IF
    IF (.NOT.read_grid_spacing_m(ncid,'Dx',dx) .OR. &
        .NOT.read_grid_spacing_m(ncid,'Dy',dy)) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-read:'//TRIM(path); GOTO 900
    END IF
    IF (ABS(dx-5000.0_real64)>1.0e-6_real64 .OR. &
        ABS(dy-5000.0_real64)>1.0e-6_real64) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-value:'//TRIM(path); GOTO 900
    END IF
    status=STATUS_OK
    RETURN
900 CONTINUE
    CALL close_file(ncid,status)
  END SUBROUTINE open_case_file

  SUBROUTINE open_surface_file(path,valid_time,time_policy,ncid,dx,dy,status,reftime)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER(int64), INTENT(IN) :: valid_time
    INTEGER, INTENT(IN) :: time_policy
    INTEGER, INTENT(OUT) :: ncid,status
    REAL(real64), INTENT(OUT) :: dx,dy
    REAL(real64), OPTIONAL, INTENT(OUT) :: reftime
    REAL(real64) :: unused_levels(NZ)
    CALL open_case_file(path,1,valid_time,time_policy,ncid,unused_levels,dx,dy,status,reftime)
  END SUBROUTINE open_surface_file

  SUBROUTINE open_static_file(path,ncid,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: ncid,status
    status=STATUS_FAILED; ncid=-1
    IF (.NOT.nc_ok(nf90_open(TRIM(path),NF90_NOWRITE,ncid))) RETURN
    IF (.NOT.dimensions_are(ncid,1)) THEN
      CALL close_file(ncid,status)
      RETURN
    END IF
    status=STATUS_OK
  END SUBROUTINE open_static_file

  SUBROUTINE close_file(ncid,status)
    INTEGER, INTENT(INOUT) :: ncid
    INTEGER, INTENT(INOUT), OPTIONAL :: status
    INTEGER :: close_status
    IF (ncid>=0) THEN
      close_status=nf90_close(ncid)
      IF (close_status/=NF90_NOERR .AND. PRESENT(status)) status=STATUS_FAILED
      ncid=-1
    END IF
  END SUBROUTINE close_file

  LOGICAL FUNCTION stage_masks_valid(result,nx,ny,nz)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: expected(3)
    expected=(/nx,ny,nz/)
    stage_masks_valid=.FALSE.
    IF (.NOT.ALLOCATED(result%column%changed) .OR. &
        .NOT.ALLOCATED(result%balance%changed) .OR. &
        .NOT.ALLOCATED(result%overall%changed)) RETURN
    IF (ALLOCATED(result%geopotential_support)) THEN
      IF (.NOT.ALLOCATED(result%geopotential%changed)) RETURN
      IF (ANY(SHAPE(result%geopotential%changed)/=expected)) RETURN
    END IF
    stage_masks_valid=ALL(SHAPE(result%column%changed)==expected) .AND. &
      ALL(SHAPE(result%balance%changed)==expected) .AND. &
      ALL(SHAPE(result%overall%changed)==expected)
  END FUNCTION stage_masks_valid

  LOGICAL FUNCTION real_radar_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: expected(3)
    real_radar_contract_valid=.FALSE.
    expected=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    IF (.NOT.ALLOCATED(state%radar_reflectivity%value) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%valid) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%quality) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%source)) RETURN
    IF (ANY(SHAPE(state%radar_reflectivity%value)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%valid)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%quality)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%source)/=expected)) RETURN
    IF (state%radar_reflectivity%valid_time/=state%pressure%valid_time .OR. &
        TRIM(state%radar_reflectivity%unit)/='dBZ') RETURN
    IF (ANY(state%radar_reflectivity%valid .AND. .NOT.state%above_ground) .OR. &
        ANY(state%radar_reflectivity%valid .AND. .NOT.radar_echo_cell( &
          state%radar_reflectivity%value,state%radar_reflectivity%valid, &
          state%radar_reflectivity%quality,state%radar_reflectivity%source))) RETURN
    IF (ANY(state%radar_reflectivity%valid .AND. &
            (.NOT.ieee_is_finite(state%radar_reflectivity%value) .OR. &
             state%radar_reflectivity%value<MINIMUM_USABLE_DBZ .OR. &
             state%radar_reflectivity%value>100.0_real32))) RETURN
    IF (ANY(.NOT.state%radar_reflectivity%valid .AND. &
        .NOT.((state%above_ground .AND. radar_no_echo_cell( &
          state%radar_reflectivity%value,state%radar_reflectivity%valid, &
          state%radar_reflectivity%quality,state%radar_reflectivity%source)) .OR. &
          radar_missing_cell(state%radar_reflectivity%value, &
            state%radar_reflectivity%valid,state%radar_reflectivity%quality, &
            state%radar_reflectivity%source)))) RETURN
    real_radar_contract_valid=.TRUE.
  END FUNCTION real_radar_contract_valid

  PURE ELEMENTAL LOGICAL FUNCTION radar_tid_value_valid(value,has_value)
    REAL(real32), INTENT(IN) :: value
    LOGICAL, INTENT(IN) :: has_value
    INTEGER :: code
    radar_tid_value_valid=.TRUE.
    IF (.NOT.has_value) RETURN
    IF (.NOT.ieee_is_finite(value) .OR. ABS(value)>10.5_real32) THEN
      radar_tid_value_valid=.FALSE.
      RETURN
    END IF
    code=NINT(value)
    radar_tid_value_valid=ABS(value-REAL(code,real32))<= &
      16.0_real32*EPSILON(1.0_real32) .AND. &
      (code==NINT(RADAR_NO_ECHO_DBZ) .OR. (code>=0 .AND. code<=2))
  END FUNCTION radar_tid_value_valid

  PURE ELEMENTAL LOGICAL FUNCTION radar_tid_is_mixed(value,has_value)
    REAL(real32), INTENT(IN) :: value
    LOGICAL, INTENT(IN) :: has_value
    radar_tid_is_mixed=.FALSE.
    IF (.NOT.radar_tid_value_valid(value,has_value) .OR. .NOT.has_value) RETURN
    radar_tid_is_mixed=NINT(value)==2
  END FUNCTION radar_tid_is_mixed

  LOGICAL FUNCTION candidate_result_is_coherent(background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    LOGICAL, ALLOCATABLE :: expected(:,:,:)
    INTEGER :: nx,ny,nz

    candidate_result_is_coherent=.FALSE.
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    ALLOCATE(expected(nx,ny,nz))

    expected=real_value_changed(background%u%value,candidate%u%value) .OR. &
             real_value_changed(background%v%value,candidate%v%value) .OR. &
             real_value_changed(background%omega%value,candidate%omega%value)
    IF (ANY(expected .NEQV. result%balance%changed)) RETURN
    IF (.NOT.dynamic_field_is_coherent(background%u,candidate%u) .OR. &
        .NOT.dynamic_field_is_coherent(background%v,candidate%v) .OR. &
        .NOT.dynamic_field_is_coherent(background%omega,candidate%omega)) RETURN

    expected=column_changed_mask(background,candidate)
    IF (ANY(expected .NEQV. result%column%changed)) RETURN
    IF (ALLOCATED(result%thermo_support)) THEN
      ! No-echo constrains precipitation, not vapor/cloud phase equilibrium.
      expected=(expected .AND. .NOT.result%thermo_support) .OR. &
        column_changed_mask(background,candidate,include_thermo=.FALSE.)
    END IF
    IF (ANY(expected .AND. radar_no_echo_cell( &
        background%radar_reflectivity%value,background%radar_reflectivity%valid, &
        background%radar_reflectivity%quality,background%radar_reflectivity%source))) RETURN
    expected=result%column%changed .OR. result%balance%changed
    IF (ALLOCATED(result%geopotential_support)) expected=expected .OR. result%geopotential%changed
    IF (ANY(expected .NEQV. result%overall%changed)) RETURN
    candidate_result_is_coherent=.TRUE.
  END FUNCTION candidate_result_is_coherent

  LOGICAL FUNCTION dynamic_field_is_coherent(background,candidate)
    TYPE(field3d), INTENT(IN) :: background,candidate
    LOGICAL, ALLOCATABLE :: changed(:,:,:)
    INTEGER(int32), ALLOCATABLE :: expected_source(:,:,:)

    dynamic_field_is_coherent=.FALSE.
    IF (background%valid_time/=candidate%valid_time .OR. &
        background%unit/=candidate%unit) RETURN
    IF (ANY(background%valid .NEQV. candidate%valid) .OR. &
        ANY(background%quality/=candidate%quality)) RETURN
    ALLOCATE(changed, SOURCE=real_value_changed(background%value,candidate%value))
    ALLOCATE(expected_source, SOURCE=background%source)
    WHERE(changed)
      expected_source=IOR(expected_source,SOURCE_BALANCE_OPERATOR)
    END WHERE
    IF (ANY(candidate%source/=expected_source)) RETURN
    dynamic_field_is_coherent=.TRUE.
  END FUNCTION dynamic_field_is_coherent

  PURE ELEMENTAL LOGICAL FUNCTION real_value_changed(left,right)
    REAL(real32), INTENT(IN) :: left,right
    real_value_changed=TRANSFER(left,0_int32)/=TRANSFER(right,0_int32)
  END FUNCTION real_value_changed

  LOGICAL FUNCTION writer_geometry_is_representable(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: i,j,k
    writer_geometry_is_representable=.FALSE.
    DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (TRANSFER(state%grid%dx(i,j),0_int64)/= &
          TRANSFER(state%grid%dx(1,1),0_int64) .OR. &
          TRANSFER(state%grid%dy(i,j),0_int64)/= &
          TRANSFER(state%grid%dy(1,1),0_int64)) RETURN
      DO k=1,state%grid%nz
        IF (TRANSFER(state%pressure%value(i,j,k),0_int32)/= &
            TRANSFER(state%pressure%value(1,1,k),0_int32)) RETURN
      END DO
    END DO; END DO
    writer_geometry_is_representable=.TRUE.
  END FUNCTION writer_geometry_is_representable

  LOGICAL FUNCTION pressure_geometry_request_valid(background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER :: nx,ny

    pressure_geometry_request_valid=.FALSE.
    IF (.NOT.ALLOCATED(result%requested_surface_pressure)) RETURN
    nx=background%grid%nx; ny=background%grid%ny
    IF (ANY(SHAPE(result%requested_surface_pressure)/=(/nx,ny/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(result%requested_surface_pressure))) RETURN
    IF (.NOT.ALLOCATED(result%geopotential_support) .OR. &
        .NOT.ALLOCATED(result%geopotential_reference_level)) RETURN
    IF (.NOT.ALLOCATED(candidate%surface_pressure%value)) RETURN
    IF (ANY(SHAPE(candidate%surface_pressure%value)/=(/nx,ny/))) RETURN
    IF (ANY(candidate%surface_pressure%value/= &
           REAL(result%requested_surface_pressure,real32))) RETURN
    IF (.NOT.ieee_is_finite(result%geometry_budget%dry_air_change_kg) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%enthalpy_change_j) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%geometry_mass_change_kg) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%enthalpy_composition_change_j) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%enthalpy_mass_metric_change_j) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%total_mass_error_kg) .OR. &
        .NOT.ieee_is_finite(result%geometry_budget%max_cell_mass_error_kg) .OR. &
        ANY(.NOT.ieee_is_finite(result%geometry_budget%species_change_kg)) .OR. &
        ANY(.NOT.ieee_is_finite(result%geometry_budget%mixing_ratio_change_kg)) .OR. &
        ANY(.NOT.ieee_is_finite(result%geometry_budget%dry_mass_redistribution_kg))) RETURN
    IF (result%geometry_budget%accounted_cells<0_int64 .OR. &
        result%geometry_budget%incomplete_background_cells<0_int64 .OR. &
        result%geometry_budget%incomplete_candidate_cells<0_int64) RETURN
    pressure_geometry_request_valid=.TRUE.
  END FUNCTION pressure_geometry_request_valid

  LOGICAL FUNCTION pressure_geopotential_request_valid(background,candidate,result, &
                                                        pressure_candidate,variable_geometry)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    LOGICAL, INTENT(IN) :: pressure_candidate,variable_geometry
    INTEGER :: nx,ny,nz,i,j,bottom
    LOGICAL :: surface_variant,selected_column,transition

    pressure_geopotential_request_valid=.FALSE.
    transition=ALLOCATED(result%pressure_transition_seed)
    IF (ALLOCATED(result%geopotential_support).NEQV. &
        ALLOCATED(result%geopotential_reference_level)) RETURN
    IF (.NOT.ALLOCATED(result%geopotential_support)) THEN
      pressure_geopotential_request_valid=.TRUE.
      RETURN
    END IF
    ! A geopotential request is meaningful only on the pressure-candidate
    ! schema.  The pipeline stores only nonempty requests, so an allocated
    ! request with no active support is malformed rather than an inactive
    ! extension.
    IF (.NOT.pressure_candidate .OR. .NOT.ANY(result%geopotential_support)) RETURN
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    IF (ANY(SHAPE(result%geopotential_support)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(result%geopotential_reference_level)/=(/nx,ny/))) RETURN
    IF (.NOT.ALLOCATED(background%above_ground)) RETURN
    IF (ANY(SHAPE(background%above_ground)/=(/nx,ny,nz/))) RETURN
    IF (transition) THEN
      IF (.NOT.variable_geometry .OR. .NOT.ALLOCATED(candidate%above_ground)) RETURN
      IF (ANY(SHAPE(candidate%above_ground)/=(/nx,ny,nz/))) RETURN
      IF (ANY(background%above_ground .AND. .NOT.candidate%above_ground)) RETURN
      IF (ANY(result%geopotential_reference_level/=0)) RETURN
    END IF
    IF (.NOT.ALLOCATED(candidate%geopotential%value)) RETURN
    IF (ANY(SHAPE(candidate%geopotential%value)/=(/nx,ny,nz/))) RETURN
    IF (.NOT.ALLOCATED(result%thermo_support) .OR. &
        .NOT.ALLOCATED(result%thermo_surface)) THEN
      IF (.NOT.variable_geometry) RETURN
    ELSE IF (ANY(SHAPE(result%thermo_support)/=(/nx,ny,nz/)) .OR. &
             ANY(SHAPE(result%thermo_surface)/=(/nx,ny,nz/))) THEN
      RETURN
    END IF
    surface_variant=.FALSE.
    DO j=1,ny; DO i=1,nx
      selected_column=ANY(result%geopotential_support(i,j,:))
      IF (selected_column .AND. result%geopotential_reference_level(i,j)==0) &
        surface_variant=.TRUE.
    END DO; END DO
    DO j=1,ny; DO i=1,nx
      IF (transition) THEN
        IF (ANY(result%geopotential_support(i,j,:) .AND. &
               .NOT.candidate%above_ground(i,j,:))) RETURN
      ELSE
        IF (ANY(result%geopotential_support(i,j,:) .AND. &
               .NOT.background%above_ground(i,j,:))) RETURN
      END IF
      selected_column=ANY(result%geopotential_support(i,j,:))
      IF (surface_variant) THEN
        ! The surface contract is intentionally all-or-nothing: zero is a
        ! fixed-terrain anchor on selected columns, while inactive columns
        ! also retain the declared inactive value zero.
        IF (selected_column .AND. result%geopotential_reference_level(i,j)/=0) RETURN
        IF (.NOT.selected_column .AND. result%geopotential_reference_level(i,j)/=0) RETURN
      ELSE IF (selected_column) THEN
        bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
        IF (bottom<=0) RETURN
        IF (result%geopotential_reference_level(i,j)/=bottom) RETURN
      ELSE
        IF (result%geopotential_reference_level(i,j)/=0) RETURN
      END IF
    END DO; END DO
    pressure_geopotential_request_valid=.TRUE.
  END FUNCTION pressure_geopotential_request_valid

  LOGICAL FUNCTION geopotential_is_unchanged(background,candidate)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    geopotential_is_unchanged=.FALSE.
    IF (background%geopotential%valid_time/=candidate%geopotential%valid_time .OR. &
        background%geopotential%unit/=candidate%geopotential%unit) RETURN
    IF (.NOT.ALLOCATED(background%geopotential%value) .OR. &
        .NOT.ALLOCATED(candidate%geopotential%value) .OR. &
        .NOT.ALLOCATED(background%geopotential%valid) .OR. &
        .NOT.ALLOCATED(candidate%geopotential%valid) .OR. &
        .NOT.ALLOCATED(background%geopotential%quality) .OR. &
        .NOT.ALLOCATED(candidate%geopotential%quality) .OR. &
        .NOT.ALLOCATED(background%geopotential%source) .OR. &
        .NOT.ALLOCATED(candidate%geopotential%source)) RETURN
    IF (ANY(SHAPE(background%geopotential%value)/= &
            SHAPE(candidate%geopotential%value)) .OR. &
        ANY(SHAPE(background%geopotential%valid)/= &
            SHAPE(candidate%geopotential%valid)) .OR. &
        ANY(SHAPE(background%geopotential%quality)/= &
            SHAPE(candidate%geopotential%quality)) .OR. &
        ANY(SHAPE(background%geopotential%source)/= &
            SHAPE(candidate%geopotential%source))) RETURN
    IF (ANY(real_value_changed(background%geopotential%value, &
                               candidate%geopotential%value)) .OR. &
        ANY(background%geopotential%valid .NEQV. candidate%geopotential%valid) .OR. &
        ANY(background%geopotential%quality/=candidate%geopotential%quality) .OR. &
        ANY(background%geopotential%source/=candidate%geopotential%source)) RETURN
    geopotential_is_unchanged=.TRUE.
  END FUNCTION geopotential_is_unchanged

  LOGICAL FUNCTION los_is_empty(los)
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    los_is_empty=.FALSE.
    IF (los%is_present .OR. los%nradar/=0 .OR. &
        los%vrad_representation/=0_int32 .OR. los%has_colocated_dbz .OR. &
        los%has_spectrum_width .OR. &
        los%vrad%valid_time/=0_int64 .OR. LEN_TRIM(los%vrad%unit)/=0 .OR. &
        los%nyquist%valid_time/=0_int64 .OR. LEN_TRIM(los%nyquist%unit)/=0 .OR. &
        los%sigma_vrad%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%sigma_vrad%unit)/=0 .OR. &
        los%colocated_dbz%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%colocated_dbz%unit)/=0 .OR. &
        los%spectrum_width%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%spectrum_width%unit)/=0) RETURN
    IF (.NOT.field4d_is_empty(los%vrad) .OR. &
        .NOT.field4d_is_empty(los%nyquist) .OR. &
        .NOT.field4d_is_empty(los%sigma_vrad) .OR. &
        .NOT.field4d_is_empty(los%colocated_dbz) .OR. &
        .NOT.field4d_is_empty(los%spectrum_width)) RETURN
    IF (ALLOCATED(los%beam) .OR. ALLOCATED(los%observation_id_hi) .OR. &
        ALLOCATED(los%observation_id_lo) .OR. ALLOCATED(los%usage) .OR. &
        ALLOCATED(los%radar_id) .OR. ALLOCATED(los%observation_time) .OR. &
        ALLOCATED(los%site_lat) .OR. ALLOCATED(los%site_lon) .OR. &
        ALLOCATED(los%site_height) .OR. ALLOCATED(los%wavelength) .OR. &
        ALLOCATED(los%los_support) .OR. ALLOCATED(los%geometry_condition) .OR. &
        ALLOCATED(los%geometry_rank)) RETURN
    los_is_empty=.TRUE.
  END FUNCTION los_is_empty

  LOGICAL FUNCTION field4d_is_empty(field)
    TYPE(field4d), INTENT(IN) :: field
    field4d_is_empty=.NOT.ALLOCATED(field%value) .AND. &
      .NOT.ALLOCATED(field%valid) .AND. .NOT.ALLOCATED(field%quality) .AND. &
      .NOT.ALLOCATED(field%source)
  END FUNCTION field4d_is_empty

  SUBROUTINE read_real3(ncid,name,unit_a,unit_b,data,valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit_a,unit_b
    REAL(real32), INTENT(OUT) :: data(NX,NY,NZ)
    LOGICAL, INTENT(OUT) :: valid(NX,NY,NZ)
    INTEGER, INTENT(OUT) :: status
    REAL(real32), ALLOCATABLE :: work(:,:,:,:)
    INTEGER :: varid,rc
    status=STATUS_FAILED; data=0.0_real32; valid=.FALSE.
    rc=nf90_inq_varid(ncid,TRIM(name),varid)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=missing-variable:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_unit_is(ncid,varid,unit_a,unit_b)) THEN
      WRITE(*,'(A)') 'adapter_error=units:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=6) :: 'x','y','z','record'])) THEN
      WRITE(*,'(A)') 'adapter_error=layout:'//TRIM(name); RETURN
    END IF
    ALLOCATE(work(NX,NY,NZ,1))
    rc=nf90_get_var(ncid,varid,work)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=read:'//TRIM(name)//':'//TRIM(nf90_strerror(rc)); RETURN
    END IF
    data=work(:,:,:,1)
    ! Keep missing coverage, but remove nonfinite operands before arithmetic.
    ! Fortran does not guarantee short-circuit evaluation of logical AND.
    valid=ieee_is_finite(data)
    WHERE (.NOT.valid) data=0.0_real32
    valid=valid .AND. ABS(data)<RAW_MISSING_LIMIT
    status=STATUS_OK
  END SUBROUTINE read_real3

  SUBROUTINE read_real2(ncid,name,unit_a,unit_b,data,valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit_a,unit_b
    REAL(real32), INTENT(OUT) :: data(NX,NY)
    LOGICAL, INTENT(OUT) :: valid(NX,NY)
    INTEGER, INTENT(OUT) :: status
    REAL(real32), ALLOCATABLE :: work(:,:,:,:)
    INTEGER :: varid,rc
    status=STATUS_FAILED; data=0.0_real32; valid=.FALSE.
    rc=nf90_inq_varid(ncid,TRIM(name),varid)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=missing-variable:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_unit_is(ncid,varid,unit_a,unit_b)) THEN
      WRITE(*,'(A)') 'adapter_error=units:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=6) :: 'x','y','z','record'])) THEN
      WRITE(*,'(A)') 'adapter_error=layout:'//TRIM(name); RETURN
    END IF
    ALLOCATE(work(NX,NY,1,1))
    rc=nf90_get_var(ncid,varid,work)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=read:'//TRIM(name)//':'//TRIM(nf90_strerror(rc)); RETURN
    END IF
    data=work(:,:,1,1)
    ! Keep missing coverage, but remove nonfinite operands before arithmetic.
    ! Fortran does not guarantee short-circuit evaluation of logical AND.
    valid=ieee_is_finite(data)
    WHERE (.NOT.valid) data=0.0_real32
    valid=valid .AND. ABS(data)<RAW_MISSING_LIMIT
    status=STATUS_OK
  END SUBROUTINE read_real2

  SUBROUTINE assign_reversed_core(raw,raw_valid,domain,field,source,scale,status)
    REAL(real32), INTENT(IN) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ),domain(NX,NY,NZ)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    REAL(real64), INTENT(IN) :: scale
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k,source_k
    LOGICAL :: usable(NX,NY)
    status=STATUS_FAILED
    DO k=1,NZ
      source_k=NZ+1-k; usable=domain(:,:,k) .AND. raw_valid(:,:,source_k)
      IF (ANY(domain(:,:,k) .AND. .NOT.usable)) RETURN
      ! Excluded cells must not enter the scaled real32 conversion.
      field%value(:,:,k)=0.0_real32
      WHERE (usable)
        field%value(:,:,k)=REAL(scale*REAL(raw(:,:,source_k),real64),real32)
      END WHERE
      CALL mark_real_field(field,k,usable,source)
    END DO
    status=STATUS_OK
  END SUBROUTINE assign_reversed_core

  PURE LOGICAL FUNCTION reversed_coverage_is_complete(raw_valid,domain)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ),domain(NX,NY,NZ)
    INTEGER :: k,source_k
    reversed_coverage_is_complete=.FALSE.
    DO k=1,NZ
      source_k=NZ+1-k
      IF (ANY(domain(:,:,k) .AND. .NOT.raw_valid(:,:,source_k))) RETURN
    END DO
    reversed_coverage_is_complete=.TRUE.
  END FUNCTION reversed_coverage_is_complete

  SUBROUTINE assign_specific_humidity(raw,raw_valid,state,status,source)
    REAL(real32), INTENT(IN) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER(int32), INTENT(IN), OPTIONAL :: source
    INTEGER :: k,source_k
    INTEGER(int32) :: field_source
    LOGICAL :: usable(NX,NY)
    REAL(real32) :: q(NX,NY)
    status=STATUS_FAILED
    field_source=SOURCE_BACKGROUND_MODEL
    IF (PRESENT(source)) field_source=source
    DO k=1,NZ
      source_k=NZ+1-k; q=raw(:,:,source_k)
      usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
             q>=0.0_real32 .AND. q<1.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. .NOT.usable)) RETURN
      WHERE(usable) state%vapor%value(:,:,k)=q/(1.0_real32-q)
      CALL mark_real_field(state%vapor,k,usable,field_source)
    END DO
    status=STATUS_OK
  END SUBROUTINE assign_specific_humidity

  SUBROUTINE read_and_assign_hydrometeor(ncid,name,state,field,raw,raw_valid,status, &
                                         source,allow_legacy_lwc_units)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(INOUT) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(INOUT) :: raw_valid(NX,NY,NZ)
    INTEGER, INTENT(OUT) :: status
    INTEGER(int32), INTENT(IN), OPTIONAL :: source
    LOGICAL, INTENT(IN), OPTIONAL :: allow_legacy_lwc_units
    INTEGER :: k,source_k,i,j
    INTEGER(int32) :: field_source
    LOGICAL :: use_legacy_lwc_units
    REAL(real64) :: rho_d
    LOGICAL :: usable(NX,NY)
    field_source=SOURCE_BACKGROUND_MODEL
    IF (PRESENT(source)) field_source=source
    use_legacy_lwc_units=.FALSE.
    IF (PRESENT(allow_legacy_lwc_units)) use_legacy_lwc_units=allow_legacy_lwc_units
    IF (use_legacy_lwc_units) THEN
      CALL read_real3(ncid,name,'kg/meter**3','kgm-3',raw,raw_valid,status)
    ELSE
      CALL read_real3(ncid,name,'kg/m**3','kgm-3',raw,raw_valid,status)
    END IF
    IF (status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
             raw(:,:,source_k)>=0.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. .NOT.usable)) THEN
        status=STATUS_FAILED; RETURN
      END IF
      DO j=1,NY; DO i=1,NX
        IF (.NOT.usable(i,j)) CYCLE
        rho_d=dry_density(REAL(state%pressure%value(i,j,k),real64), &
          REAL(state%temperature%value(i,j,k),real64), &
          REAL(state%vapor%value(i,j,k),real64))
        IF (rho_d<=0.0_real64) THEN; status=STATUS_FAILED; RETURN; END IF
        field%value(i,j,k)=REAL(REAL(raw(i,j,source_k),real64)/rho_d,real32)
      END DO; END DO
      CALL mark_real_field(field,k,usable,field_source)
    END DO
    status=STATUS_OK
  END SUBROUTINE read_and_assign_hydrometeor

  SUBROUTINE assign_surface(raw,valid,field,source)
    REAL(real32), INTENT(IN) :: raw(NX,NY)
    LOGICAL, INTENT(IN) :: valid(NX,NY)
    TYPE(field2d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%value=MERGE(raw,0.0_real32,valid)
    field%valid=valid
    field%quality=MERGE(0_int32,QUALITY_RAW_MISSING,valid)
    field%source=MERGE(source,0_int32,valid)
  END SUBROUTINE assign_surface

  SUBROUTINE mark_real_field(field,k,valid,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: k
    LOGICAL, INTENT(IN) :: valid(NX,NY)
    INTEGER(int32), INTENT(IN) :: source
    field%valid(:,:,k)=valid
    field%quality(:,:,k)=MERGE(0_int32,QUALITY_RAW_MISSING,valid)
    field%source(:,:,k)=MERGE(source,0_int32,valid)
  END SUBROUTINE mark_real_field

  SUBROUTINE restrict_state_to_domain(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    CALL restrict_coordinate_field(state%pressure,state%above_ground)
    CALL restrict_real_field(state%temperature,state%above_ground)
    CALL restrict_real_field(state%vapor,state%above_ground)
    CALL restrict_real_field(state%u,state%above_ground)
    CALL restrict_real_field(state%v,state%above_ground)
    CALL restrict_real_field(state%omega,state%above_ground)
    CALL restrict_real_field(state%omega_target,state%above_ground)
    CALL restrict_real_field(state%omega_target_sigma,state%above_ground)
    CALL restrict_real_field(state%geopotential,state%above_ground)
    CALL restrict_real_field(state%cloud_fraction,state%above_ground)
    CALL restrict_real_field(state%radar_reflectivity,state%above_ground)
    CALL restrict_real_field(state%cloud_water,state%above_ground)
    CALL restrict_real_field(state%cloud_ice,state%above_ground)
    CALL restrict_real_field(state%rain,state%above_ground)
    CALL restrict_real_field(state%snow,state%above_ground)
    CALL restrict_real_field(state%graupel,state%above_ground)
    CALL restrict_real_field(state%vt_z_mean,state%above_ground)
    CALL restrict_real_field(state%vt_z_sigma,state%above_ground)
    CALL restrict_integer_field(state%cloud_type,state%above_ground)
    CALL restrict_integer_field(state%precipitation_phase,state%above_ground)
    CALL restrict_integer_field(state%lightning_support,state%above_ground)
    WHERE(.NOT.state%above_ground)
      state%obs_support=0_int32
      state%hydro_support=0_int32
      state%balance_beta=0.0_real32
      state%model_target_coverage=.FALSE.
    END WHERE
  END SUBROUTINE restrict_state_to_domain

  SUBROUTINE restrict_coordinate_field(field,domain)
    TYPE(field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_coordinate_field

  SUBROUTINE restrict_real_field(field,domain)
    TYPE(field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%value=0.0_real32
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_real_field

  SUBROUTINE restrict_integer_field(field,domain)
    TYPE(integer_field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%value=0_int32
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_integer_field

  SUBROUTINE set_copied_interior_omega_boundaries(state,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    status=STATUS_FAILED
    DO j=1,NY; DO i=1,NX
      IF (.NOT.state%omega%valid(i,j,NZ)) RETURN
      state%omega_top_boundary%value(i,j)=state%omega%value(i,j,NZ)
      state%omega_top_boundary%valid(i,j)=.TRUE.
      state%omega_top_boundary%quality(i,j)=IOR(QUALITY_LEGACY_PROVENANCE, &
        QUALITY_BOUNDARY_INTERIOR_COPY)
      state%omega_top_boundary%source(i,j)=SOURCE_ANALYZED_WIND
      DO k=1,NZ
        IF (.NOT.state%above_ground(i,j,k)) CYCLE
        state%omega_bottom_boundary%value(i,j)=state%omega%value(i,j,k)
        state%omega_bottom_boundary%valid(i,j)=.TRUE.
        state%omega_bottom_boundary%quality(i,j)=IOR(QUALITY_LEGACY_PROVENANCE, &
          QUALITY_BOUNDARY_INTERIOR_COPY)
        state%omega_bottom_boundary%source(i,j)=SOURCE_ANALYZED_WIND
        EXIT
      END DO
      IF (.NOT.state%omega_bottom_boundary%valid(i,j)) RETURN
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE set_copied_interior_omega_boundaries

  LOGICAL FUNCTION dimensions_are(ncid,nz)
    INTEGER, INTENT(IN) :: ncid,nz
    dimensions_are=dimension_is(ncid,'x',NX) .AND. dimension_is(ncid,'y',NY) .AND. &
                   dimension_is(ncid,'z',nz) .AND. dimension_is(ncid,'record',1)
  END FUNCTION dimensions_are

  LOGICAL FUNCTION dimension_is(ncid,name,expected)
    INTEGER, INTENT(IN) :: ncid,expected
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER :: dimid,length
    dimension_is=.FALSE.
    IF (.NOT.nc_ok(nf90_inq_dimid(ncid,TRIM(name),dimid))) RETURN
    IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimid,LEN=length))) RETURN
    dimension_is=length==expected
  END FUNCTION dimension_is

  LOGICAL FUNCTION read_scalar(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value
    INTEGER :: varid
    REAL(real64) :: work(1)
    read_scalar=.FALSE.; value=0.0_real64
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    SELECT CASE(TRIM(name))
    CASE('valtime','reftime')
      IF (.NOT.variable_layout_is(ncid,varid,NF90_DOUBLE, &
          [CHARACTER(LEN=6) :: 'record']) .OR. &
          .NOT.variable_unit_is(ncid,varid, &
            'seconds since (1970-1-1 00:00:00.0)', &
            'seconds since 1970-01-01 00:00:00')) RETURN
    CASE DEFAULT
      RETURN
    END SELECT
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,work))) RETURN
    value=work(1); read_scalar=ieee_is_finite(value)
  END FUNCTION read_scalar

  LOGICAL FUNCTION read_grid_spacing_m(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value
    REAL(real32) :: raw(1)
    INTEGER :: varid

    read_grid_spacing_m=.FALSE.; value=0.0_real64
    IF (TRIM(name)/='Dx' .AND. TRIM(name)/='Dy') RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=3) :: 'nav']) .OR. &
        .NOT.variable_unit_is(ncid,varid,'kilometers','km')) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,raw))) RETURN
    IF (.NOT.ieee_is_finite(raw(1))) RETURN
    IF (ABS(raw(1)-5.0_real32)<=1.0e-6_real32) THEN
      value=1000.0_real64*REAL(raw(1),real64)
    ELSE IF (ABS(raw(1)-5000.0_real32)<=1.0e-3_real32) THEN
      ! The pinned legacy KLAPS files label numerical metres as kilometres.
      value=REAL(raw(1),real64)
    ELSE
      RETURN
    END IF
    read_grid_spacing_m=.TRUE.
  END FUNCTION read_grid_spacing_m

  LOGICAL FUNCTION read_vector(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value(:)
    INTEGER :: varid
    read_vector=.FALSE.; value=0.0_real64
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (TRIM(name)/='level') RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=1) :: 'z']) .OR. &
        .NOT.variable_unit_is(ncid,varid,'hectopascals','hpa')) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,value))) RETURN
    read_vector=ALL(ieee_is_finite(value))
  END FUNCTION read_vector

  LOGICAL FUNCTION variable_layout_is(ncid,varid,expected_type,dimension_names)
    INTEGER, INTENT(IN) :: ncid,varid,expected_type
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    CHARACTER(LEN=NF90_MAX_NAME) :: actual_name
    INTEGER :: actual_type,ndims,dimids(NF90_MAX_VAR_DIMS),k
    variable_layout_is=.FALSE.
    IF (.NOT.nc_ok(nf90_inquire_variable(ncid,varid,XTYPE=actual_type, &
        NDIMS=ndims,DIMIDS=dimids))) RETURN
    IF (actual_type/=expected_type .OR. ndims/=SIZE(dimension_names)) RETURN
    DO k=1,ndims
      actual_name=''
      IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimids(k),NAME=actual_name))) RETURN
      IF (TRIM(actual_name)/=TRIM(dimension_names(k))) RETURN
    END DO
    variable_layout_is=.TRUE.
  END FUNCTION variable_layout_is

  LOGICAL FUNCTION variable_unit_is(ncid,varid,unit_a,unit_b)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: unit_a,unit_b
    CHARACTER(LEN=128) :: actual
    variable_unit_is=.FALSE.; actual=''
    IF (.NOT.nc_ok(nf90_get_att(ncid,varid,'units',actual))) RETURN
    variable_unit_is=normalize_unit(actual)==normalize_unit(unit_a) .OR. &
                     normalize_unit(actual)==normalize_unit(unit_b)
  END FUNCTION variable_unit_is

  PURE CHARACTER(LEN=128) FUNCTION normalize_unit(value)
    CHARACTER(LEN=*), INTENT(IN) :: value
    INTEGER :: i,n,code
    normalize_unit=''; n=0
    DO i=1,LEN_TRIM(value)
      IF (value(i:i)==' ' .OR. value(i:i)=='_' .OR. value(i:i)=='{'.OR. &
          value(i:i)=='}') CYCLE
      n=n+1; code=IACHAR(value(i:i))
      IF (code>=IACHAR('A') .AND. code<=IACHAR('Z')) code=code+32
      normalize_unit(n:n)=ACHAR(code)
    END DO
  END FUNCTION normalize_unit

  PURE LOGICAL FUNCTION levels_are_native(levels)
    REAL(real64), INTENT(IN) :: levels(NZ)
    INTEGER :: k
    levels_are_native=.TRUE.
    DO k=1,NZ
      IF (ABS(levels(k)-50.0_real64*REAL(k,real64))>1.0e-5_real64) THEN
        levels_are_native=.FALSE.; RETURN
      END IF
    END DO
  END FUNCTION levels_are_native

  PURE LOGICAL FUNCTION vertical_domain_is_contiguous(domain)
    LOGICAL, INTENT(IN) :: domain(NX,NY,NZ)
    INTEGER :: i,j,k
    vertical_domain_is_contiguous=.FALSE.
    DO j=1,NY; DO i=1,NX
      IF (.NOT.ANY(domain(i,j,:))) RETURN
      DO k=1,NZ-1
        IF (domain(i,j,k) .AND. .NOT.domain(i,j,k+1)) RETURN
      END DO
    END DO; END DO
    vertical_domain_is_contiguous=.TRUE.
  END FUNCTION vertical_domain_is_contiguous

  LOGICAL FUNCTION terrain_mask_is_consistent(state,topography)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real32), INTENT(IN) :: topography(NX,NY)
    INTEGER :: i,j,k,bottom
    REAL(real64) :: height,tolerance
    terrain_mask_is_consistent=.FALSE.
    DO j=1,NY; DO i=1,NX
      bottom=0
      DO k=1,NZ
        IF (state%above_ground(i,j,k)) THEN
          bottom=k
          EXIT
        END IF
      END DO
      IF (bottom==0) RETURN
      tolerance=128.0_real64*REAL(EPSILON(1.0_real32),real64)* &
        MAX(1.0_real64,ABS(REAL(topography(i,j),real64)))
      DO k=bottom,NZ
        IF (.NOT.cell_is_usable(state%geopotential%valid(i,j,k), &
              state%geopotential%quality(i,j,k), &
              state%geopotential%source(i,j,k))) RETURN
        height=REAL(state%geopotential%value(i,j,k),real64)/GRAVITY
        IF (.NOT.ieee_is_finite(height) .OR. height < -1000.0_real64 .OR. &
            height > 50000.0_real64 .OR. &
            height<REAL(topography(i,j),real64)-tolerance) RETURN
        IF (k>bottom) THEN
          IF (state%geopotential%value(i,j,k)<= &
              state%geopotential%value(i,j,k-1)) RETURN
        END IF
      END DO
    END DO; END DO
    terrain_mask_is_consistent=.TRUE.
  END FUNCTION terrain_mask_is_consistent

  PURE LOGICAL FUNCTION copied_diagnostic_boundary_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    copied_diagnostic_boundary_contract_valid=boundary_contract_valid(state)
    IF (.NOT.copied_diagnostic_boundary_contract_valid) RETURN
    copied_diagnostic_boundary_contract_valid= &
      ALL(IAND(state%omega_top_boundary%quality, &
               QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32) .AND. &
      ALL(IAND(state%omega_bottom_boundary%quality, &
               QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32) .AND. &
      ALL(IAND(state%omega_top_boundary%source,SOURCE_ANALYZED_WIND)/=0_int32) .AND. &
      ALL(IAND(state%omega_bottom_boundary%source,SOURCE_ANALYZED_WIND)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega_top_boundary%source, &
                    SOURCE_BOUNDARY_CONDITION)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega_bottom_boundary%source, &
                    SOURCE_BOUNDARY_CONDITION)/=0_int32)
  END FUNCTION copied_diagnostic_boundary_contract_valid

  PURE REAL(real64) FUNCTION dry_density(pressure,temperature,vapor)
    REAL(real64), INTENT(IN) :: pressure,temperature,vapor
    dry_density=0.0_real64
    IF (.NOT.ieee_is_finite(pressure) .OR. .NOT.ieee_is_finite(temperature) .OR. &
        .NOT.ieee_is_finite(vapor) .OR. pressure<=0.0_real64 .OR. &
        temperature<=0.0_real64 .OR. vapor<0.0_real64) RETURN
    dry_density=pressure/(RD_AIR*temperature*(1.0_real64+vapor/EPSILON_WATER))
  END FUNCTION dry_density

  LOGICAL FUNCTION put_global_metadata(ncid,result,config,valid_time)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=64) :: evidence_class,configuration_id,target_provenance, &
      boundary_provenance,contract_name
    put_global_metadata=.FALSE.
    contract_name='real_radar_only_shadow_v3'
    evidence_class='REAL_RADAR_ONLY_SHADOW_PROPOSAL'
    configuration_id='real-radar-only-shadow-v3'
    target_provenance='OBSERVATIONAL_DYNAMIC_TARGET'
    boundary_provenance='COPIED_INTERIOR_DIAGNOSTIC_ONLY'
    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      contract_name='model_dynamics_shadow_v1'
      evidence_class='MODEL_DYNAMICS_SHADOW_PROPOSAL'
      configuration_id='model-dynamics-shadow-v1'
      target_provenance='PAIRED_MODEL_DYNAMIC_TARGET_ABSOLUTE'
      boundary_provenance='HOMOGENEOUS_MODEL_INCREMENT_PRESERVE_BASELINE'
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract', &
                                TRIM(contract_name)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'diagnostic_schema_version', &
                                5_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'schema_extensions', &
      'verified_operational_identity_v1,radar_no_echo_masks_v1,'// &
      'pressure_geometry_v2,omega_boundary_contract_v2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_bal_schema_version', &
                                CLOUD_BAL_SCHEMA_VERSION))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class', &
                                TRIM(evidence_class)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id', &
                                TRIM(configuration_id)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'target_authority', &
                                config%balance%target_authority))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'boundary_increment_contract', &
                                config%balance%boundary_increment_contract))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_target_provenance', &
      TRIM(target_provenance)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'result_authority', &
                                'DIAGNOSTIC_PROPOSAL_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'requested_mode', &
                                config%requested_mode))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'science_assessed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'promotion_eligible',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operational_state_verified', &
                                1_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operational_state_changed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_present',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_los_used',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'above_ground_mask_provenance', &
      'PSFC_PRESSURE_CENTER_AND_STATIC_TERRAIN_HEIGHT'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_spacing_adapter_policy', &
      'KM_TO_M_OR_PINNED_LEGACY_NUMERIC_METERS'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_interface_semantics', &
      'SURFACE_CLIPPED_CONTROL_VOLUME_BOUNDARY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'physical_continuity_assessed', &
      0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_boundary_provenance', &
      TRIM(boundary_provenance)))) RETURN
    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'boundary_mode', &
        'ZERO_INCREMENT_PRESERVE_BASELINE'))) RETURN
      IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'model_target_coverage_provenance', &
        'EXTERNAL_PAIRED_MODEL_NATIVE_INTERIOR_AND_CLOSED_HALO'))) RETURN
    END IF
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'balance_support_variable', &
                                'candidate_balance_support'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_usable_dbz', &
                                MINIMUM_USABLE_DBZ))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_no_echo_dbz', &
                                RADAR_NO_ECHO_DBZ))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_no_echo_transport_policy', &
                                'DESTINATION_HARD_BLOCK_SEPARATE_LEDGER'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_valid_semantics', &
                                'ECHO_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL, &
                                'configured_assumed_radar_wavelength_m', &
                                config%column%radar_wavelength_m))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_wavelength_provenance', &
                                'CONFIGURED_ASSUMPTION_NOT_OBSERVATION'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'trajectory_horizontal_frame', &
                                'INPUT_WIND_NATIVE_UNRESOLVED'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'storm_motion_provenance', &
                                'NOT_AVAILABLE_ZERO_TRANSLATION_ASSUMPTION'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_usable_dbz', &
                                config%column%maximum_dbz))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'reference_mass_concentration', &
                                config%column%reference_mass_concentration))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_relative_fall_speed', &
                                config%column%minimum_relative_fall_speed))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_horizontal_substep', &
                                config%column%maximum_horizontal_substep))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_transport_substeps', &
                                config%column%maximum_transport_substeps))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'precipitation_loading_efficiency', &
                                config%column%precipitation_loading_efficiency))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_downdraft_ms', &
                                config%column%maximum_downdraft_ms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_downdraft_innovation_ms', &
                                config%column%maximum_downdraft_innovation_ms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'ledger_relative_tolerance', &
                                config%column%ledger_relative_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'ledger_absolute_tolerance', &
                                config%column%ledger_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'horizontal_support_radius_m', &
                                config%horizontal_support_radius_m))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_support_radius_pa', &
                                config%pressure_support_radius_pa))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_balance_beta', &
                                config%balance%minimum_beta))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_u', &
                                config%balance%kappa_u))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_v', &
                                config%balance%kappa_v))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_omega', &
                                config%balance%kappa_omega))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_wind_increment_ms', &
                                config%balance%maximum_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_omega_increment_pas', &
                                config%balance%maximum_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'increment_headroom', &
                                config%balance%increment_headroom))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_residual_fraction', &
                                config%balance%solver_residual_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'required_residual_fraction', &
                                config%balance%required_residual_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_target_response_ratio', &
                    config%balance%minimum_target_response_ratio))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_target_response_ratio', &
                    config%balance%maximum_target_response_ratio))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_trust_region_fraction', &
                    config%balance%minimum_trust_region_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'physical_residual_tolerance', &
                                config%balance%physical_residual_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_physical_residual', &
                                config%balance%maximum_physical_residual))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_solver_iterations', &
                                config%balance%maximum_iterations))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_relative_tolerance', &
                                config%balance%geostrophic_relative_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_absolute_tolerance', &
                                config%balance%geostrophic_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'valid_time_epoch',valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pipeline_status',result%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pipeline_reason',result%reason_code))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'column_status',result%column%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'balance_status',result%balance%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_reason', &
                                result%balance%numerical%solver_reason))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_iterations', &
                                result%balance%numerical%solver_iterations))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'acceptance_failures', &
                                result%balance%numerical%acceptance_failures))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_background_rms', &
                       result%balance%numerical%continuity_background_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_background_max', &
                       result%balance%numerical%continuity_background_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_proposed_increment_rms', &
                       result%balance%numerical%continuity_proposed_increment_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_proposed_increment_max', &
                       result%balance%numerical%continuity_proposed_increment_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_projected_increment_rms', &
                       result%balance%numerical%continuity_projected_increment_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_projected_increment_max', &
                       result%balance%numerical%continuity_projected_increment_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_candidate_rms', &
                       result%balance%numerical%continuity_candidate_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_candidate_max', &
                       result%balance%numerical%continuity_candidate_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_operator_identity_max', &
              result%balance%numerical%continuity_operator_identity_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operator_identity_tolerance', &
                       config%balance%solver_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_background_rms', &
                       result%balance%numerical%geostrophic_background_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_candidate_rms', &
                       result%balance%numerical%geostrophic_candidate_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'max_wind_increment_ms', &
                       result%balance%numerical%max_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'max_omega_increment_pas', &
                       result%balance%numerical%max_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'trust_region_fraction', &
                       result%balance%numerical%trust_region_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'unscaled_max_wind_increment_ms', &
                       result%balance%numerical%unscaled_max_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'unscaled_max_omega_increment_pas', &
                       result%balance%numerical%unscaled_max_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'target_response_failure_fraction', &
              result%balance%numerical%target_response_failure_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_ledger_error', &
                       result%column%numerical%ledger_error))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'transport_required_substeps', &
                       result%column%numerical%transport_required_substeps))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_input', &
                       result%column%numerical%flux_input))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_deposited', &
                       result%column%numerical%flux_deposited))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_suspended', &
                       result%column%numerical%flux_suspended))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_boundary_exit', &
                       result%column%numerical%flux_boundary_exit))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_terrain_intercept', &
                       result%column%numerical%flux_terrain_intercept))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_observation_blocked', &
                       result%column%numerical%flux_observation_blocked))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_no_echo_blocked', &
                       result%column%numerical%flux_no_echo_blocked))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_microphysical_loss', &
                       result%column%numerical%flux_microphysical_loss))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'lower_boundary_note', &
      'copied lowest resolved omega; diagnostic only, not terrain kinematic omega'))) RETURN
    put_global_metadata=.TRUE.
  END FUNCTION put_global_metadata

  PURE LOGICAL FUNCTION nc_ok(code)
    INTEGER, INTENT(IN) :: code
    nc_ok=code==NF90_NOERR
  END FUNCTION nc_ok

END MODULE cloud_bal_real_netcdf
