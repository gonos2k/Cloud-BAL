! Isolated pressure-level candidate to WPS-array adapter.
!
! This module has no file or writer dependency.  It validates the complete
! retained WPS inventory before constructing a new inventory, and publishes
! that inventory only after every mapping check succeeds.
MODULE cloud_bal_wps_adapter
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,real128,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,field2d, &
    STATUS_FAILED,STATUS_OK, &
    SOURCE_MANUFACTURED_TEST,SOURCE_DYNAMIC_TARGET,SOURCE_ANALYZED_WIND, &
    SOURCE_OUTPUT_ADAPTER,SOURCE_COLUMN_PHYSICS,QUALITY_LEGACY_PROVENANCE,QUALITY_BELOW_GROUND_FILLED, &
    QUALITY_RAW_MISSING,source_bits_known,quality_bits_known, &
    cell_is_usable,validate_canonical_state,field3d_shape_metadata_ok, &
    dry_air_density,configure_pressure_geometry,refresh_dry_air_mass_measure
  IMPLICIT NONE
  PRIVATE

  REAL(real64), PARAMETER :: GRAVITY = 9.80665_real64
  REAL(real64), PARAMETER :: CANONICAL_GRAVITY = 9.80665_real64
  REAL(real32), PARAMETER :: SURFACE_MARKER_HPA = 2001.0_real32

  ! WPS pressure arrays use hPa.  The first nz entries are pressure levels;
  ! p(nz+1) is the explicit surface slab marker (2001 hPa).
  ! Omega is intentionally not represented: this bridge makes no native
  ! vertical-velocity or thermodynamic-authority claim.
  TYPE, PUBLIC :: pressure_wps_fields
    REAL(real32), ALLOCATABLE :: p(:)                 ! hPa, nz+1
    REAL(real32), ALLOCATABLE :: t(:,:,:)             ! K, nz+1
    REAL(real32), ALLOCATABLE :: ht(:,:,:)            ! m, nz+1
    REAL(real32), ALLOCATABLE :: u(:,:,:)              ! m s-1, nz+1
    REAL(real32), ALLOCATABLE :: v(:,:,:)              ! m s-1, nz+1
    REAL(real32), ALLOCATABLE :: rh(:,:,:)             ! %, nz+1; retained/non-authoritative
    REAL(real32), ALLOCATABLE :: qv(:,:,:)             ! kg kg-1 dry air, nz+1
    REAL(real32), ALLOCATABLE :: qc(:,:,:)             ! kg kg-1 dry air, nz
    REAL(real32), ALLOCATABLE :: qi(:,:,:)             ! kg kg-1 dry air, nz
    REAL(real32), ALLOCATABLE :: qr(:,:,:)             ! kg kg-1 dry air, nz
    REAL(real32), ALLOCATABLE :: qs(:,:,:)             ! kg kg-1 dry air, nz
    REAL(real32), ALLOCATABLE :: qg(:,:,:)             ! kg kg-1 dry air, nz
    REAL(real32), ALLOCATABLE :: psfc(:,:)             ! Pa
    REAL(real32), ALLOCATABLE :: slp(:,:)              ! Pa
    REAL(real32), ALLOCATABLE :: skin_temperature(:,:) ! K
    REAL(real32), ALLOCATABLE :: snow_cover(:,:)       ! fraction [0,1]
    INTEGER(int64) :: valid_time = 0_int64
    CHARACTER(LEN=64) :: grid_id = ''
    CHARACTER(LEN=16) :: wind_coordinate = ''
  END TYPE pressure_wps_fields

  PUBLIC :: map_pressure_candidate_to_wps
  PUBLIC :: host_vapor_pressure_column
  PUBLIC :: solve_host_surface_pressure
  PUBLIC :: build_source_host_pressure_request
  PUBLIC :: evaluate_source_host_pressure_residual
  PUBLIC :: build_pressure_transition_prior

CONTAINS

  SUBROUTINE build_pressure_transition_prior(background,retained,retained_omega, &
      requested_surface_pressure,prior,status,failed_column)
    ! Reuse the actual retained LAPSPREP slabs and the same LW3 omega read.
    ! This constructs explicit reconstruction input, not an accepted analysis.
    ! The conservative domain transition remains a separate physics operation.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(pressure_wps_fields), INTENT(IN) :: retained
    TYPE(field3d), INTENT(IN) :: retained_omega
    REAL(real64), INTENT(IN) :: requested_surface_pressure(:,:)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: prior
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(OUT), OPTIONAL :: failed_column(2)
    TYPE(cloud_bal_state_type) :: work
    LOGICAL, ALLOCATABLE :: domain(:,:,:)
    LOGICAL :: ascending,any_change
    INTEGER :: nx,ny,nz,i,j,k,l,bottom,local_status,reason
    REAL(real64) :: old_ps,new_ps

    prior=background; status=STATUS_FAILED
    IF (PRESENT(failed_column)) failed_column=0
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    CALL validate_canonical_state(background,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status==STATUS_FAILED) RETURN
    IF (ANY(SHAPE(requested_surface_pressure)/=[nx,ny])) RETURN
    IF (ANY(.NOT.ieee_is_finite(requested_surface_pressure))) RETURN
    IF (ANY(requested_surface_pressure<100.0_real64) .OR. &
        ANY(requested_surface_pressure>120000.0_real64)) RETURN
    IF (.NOT.wps_shapes_ok(retained,nx,ny,nz)) RETURN
    IF (.NOT.wps_metadata_ok(retained,background%pressure%valid_time,background%grid%grid_id)) RETURN
    IF (.NOT.wps_values_ok(retained)) RETURN
    IF (.NOT.wps_pressure_order_ok(retained%p,nz,ascending)) RETURN
    IF (ANY(retained%psfc/=background%surface_pressure%value)) RETURN
    IF (.NOT.field3d_shape_metadata_ok(retained_omega,nx,ny,nz, &
        background%pressure%valid_time,'Pa s-1')) RETURN
    DO k=1,nz
      l=k
      IF (ascending) l=nz+1-k
      IF (ANY(background%pressure%value(:,:,k)/= &
          REAL(100.0_real64*REAL(retained%p(l),real64),real32))) RETURN
    END DO

    work=background; domain=background%above_ground
    any_change=.FALSE.
    DO j=1,ny; DO i=1,nx
      old_ps=REAL(background%surface_pressure%value(i,j),real64)
      new_ps=requested_surface_pressure(i,j)
      IF (new_ps==old_ps) CYCLE
      IF (PRESENT(failed_column)) failed_column=[i,j]
      IF (new_ps<old_ps .OR. new_ps-old_ps>100.0_real64) RETURN
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      IF (bottom<1) RETURN
      new_ps=REAL(REAL(new_ps,real32),real64)
      IF (new_ps-old_ps>100.0_real64) RETURN
      IF (new_ps==old_ps) CYCLE
      work%surface_pressure%value(i,j)=REAL(new_ps,real32)
      work%surface_pressure%source(i,j)=IOR(work%surface_pressure%source(i,j),SOURCE_OUTPUT_ADAPTER)
      any_change=.TRUE.
      ! A pressure increase can thicken the existing bottom cell without
      ! exposing another center. Its boundary donor is the accepted bottom
      ! state, so no retained underground field is needed for this column.
      IF (bottom==1) CYCLE
      k=bottom-1
      ! A center already below PS but excluded by terrain stays excluded.
      ! Increasing pressure alone does not move that center above terrain.
      IF (old_ps>=REAL(background%pressure%value(i,j,k),real64)) CYCLE
      IF (requested_surface_pressure(i,j)<REAL(background%pressure%value(i,j,k),real64)) THEN
        IF (new_ps>=REAL(background%pressure%value(i,j,k),real64)) RETURN
        CYCLE
      END IF
      ! Both the request and its public float32 representation must expose
      ! exactly this center. Never manufacture a crossing through rounding.
      IF (new_ps<REAL(background%pressure%value(i,j,k),real64)) RETURN
      IF (new_ps<REAL(background%pressure%value(i,j,k),real64) .OR. &
          new_ps-old_ps>100.0_real64) RETURN
      IF (k>1) THEN
        IF (requested_surface_pressure(i,j)>=REAL(background%pressure%value(i,j,k-1),real64) .OR. &
            new_ps>=REAL(background%pressure%value(i,j,k-1),real64)) RETURN
      END IF
      IF (.NOT.cell_is_usable(retained_omega%valid(i,j,k),retained_omega%quality(i,j,k), &
          retained_omega%source(i,j,k))) RETURN
      IF (.NOT.ieee_is_finite(retained_omega%value(i,j,k))) RETURN
      IF (ABS(retained_omega%value(i,j,k))>100.0_real32) RETURN
      IF (IAND(retained_omega%source(i,j,k),SOURCE_ANALYZED_WIND)==0_int32 .OR. &
          IAND(retained_omega%source(i,j,k),IOR(SOURCE_MANUFACTURED_TEST,SOURCE_DYNAMIC_TARGET))/=0_int32) RETURN
      l=k
      IF (ascending) l=nz+1-k
      IF (retained%t(i,j,l)<150.0_real32 .OR. retained%t(i,j,l)>350.0_real32 .OR. &
          retained%qv(i,j,l)>0.2_real32 .OR. ABS(retained%u(i,j,l))>200.0_real32 .OR. &
          ABS(retained%v(i,j,l))>200.0_real32 .OR. &
          retained%ht(i,j,l)<-1000.0_real32 .OR. retained%ht(i,j,l)>100000.0_real32) RETURN
      CALL reconstruct(work%temperature,retained%t(i,j,l))
      CALL reconstruct(work%vapor,retained%qv(i,j,l))
      CALL reconstruct(work%cloud_water,retained%qc(i,j,l))
      CALL reconstruct(work%cloud_ice,retained%qi(i,j,l))
      CALL reconstruct(work%rain,retained%qr(i,j,l))
      CALL reconstruct(work%snow,retained%qs(i,j,l))
      CALL reconstruct(work%graupel,retained%qg(i,j,l))
      CALL reconstruct(work%u,retained%u(i,j,l))
      CALL reconstruct(work%v,retained%v(i,j,l))
      CALL reconstruct(work%geopotential,REAL(GRAVITY*REAL(retained%ht(i,j,l),real64),real32))
      CALL reconstruct(work%omega,retained_omega%value(i,j,k))
      work%omega%quality(i,j,k)=retained_omega%quality(i,j,k)
      work%omega%source(i,j,k)=retained_omega%source(i,j,k)
      domain(i,j,k)=.TRUE.
      work%obs_support(i,j,k)=0_int32; work%hydro_support(i,j,k)=0_int32
      work%balance_beta(i,j,k)=0.0_real32
      work%omega_target%valid(i,j,k)=.FALSE.; work%omega_target%source(i,j,k)=0_int32
      work%omega_target%quality(i,j,k)=QUALITY_RAW_MISSING
      work%omega_target_sigma%valid(i,j,k)=.FALSE.; work%omega_target_sigma%source(i,j,k)=0_int32
      work%omega_target_sigma%quality(i,j,k)=QUALITY_RAW_MISSING
    END DO; END DO
    IF (PRESENT(failed_column)) failed_column=0
    IF (.NOT.any_change) THEN
      status=STATUS_OK
      RETURN
    END IF
    ! Geometry requires the full pressure coordinate. Its retained values
    ! were matched above; restore original metadata outside newly active cells.
    work%pressure%valid=.TRUE.; work%pressure%quality=0_int32
    work%pressure%source=SOURCE_OUTPUT_ADAPTER
    CALL configure_pressure_geometry(work,local_status,domain)
    IF (local_status/=STATUS_OK) RETURN
    work%pressure=background%pressure
    WHERE (domain .AND. .NOT.background%above_ground)
      work%pressure%valid=.TRUE.; work%pressure%quality=0_int32
      work%pressure%source=SOURCE_OUTPUT_ADAPTER
    END WHERE
    CALL refresh_dry_air_mass_measure(work,local_status)
    IF (local_status/=STATUS_OK) RETURN
    ! Preserve retained phase-step dry mass only where geometry is unchanged.
    ! A repartitioned prior cell needs its own pressure-mass denominator; the
    ! conservative transition still takes immutable donors from background.
    WHERE (work%grid%pressure_mass_measure==background%grid%pressure_mass_measure)
      work%grid%dry_air_mass_measure=background%grid%dry_air_mass_measure
    END WHERE
    CALL validate_canonical_state(work,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status==STATUS_FAILED) RETURN
    prior=work; status=STATUS_OK
  CONTAINS
    SUBROUTINE reconstruct(field,value)
      TYPE(field3d), INTENT(INOUT) :: field
      REAL(real32), INTENT(IN) :: value
      field%value(i,j,k)=value; field%valid(i,j,k)=.TRUE.
      field%quality(i,j,k)=IOR(QUALITY_LEGACY_PROVENANCE,QUALITY_BELOW_GROUND_FILLED)
      field%source(i,j,k)=IOR(SOURCE_OUTPUT_ADAPTER,SOURCE_COLUMN_PHYSICS)
    END SUBROUTINE reconstruct
  END SUBROUTINE build_pressure_transition_prior

  ! WRF integ_moist discrete vapor integral (Pa), not total-water mass.
  ! Surface is first; remaining pressure levels may have either ordering.
  ! No moisture tail is added above the highest supplied level. Constants
  ! belong to the caller's host model, not the canonical gravity convention.
  PURE SUBROUTINE host_vapor_pressure_column(pressure,temperature,vapor,height, &
                                            gas_constant,gravity,integrated_vapor_pa,ok)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity
    REAL(real64), INTENT(OUT) :: integrated_vapor_pa
    LOGICAL, INTENT(OUT) :: ok
    INTEGER :: n,k,first,last,stride,lower,upper
    ! Wide intermediates allow invalid extreme inputs to fail without an
    ! overflow trap in the pinned diagnostic build. Public values stay real64.
    REAL(real128) :: total,dz

    integrated_vapor_pa=0.0_real64
    ok=.FALSE.
    n=SIZE(pressure)
    IF (n<3) RETURN
    IF (SIZE(temperature)/=n .OR. SIZE(vapor)/=n .OR. SIZE(height)/=n) RETURN
    IF (.NOT.ALL(ieee_is_finite(pressure))) RETURN
    IF (.NOT.ALL(ieee_is_finite(temperature))) RETURN
    IF (.NOT.ALL(ieee_is_finite(vapor))) RETURN
    IF (.NOT.ALL(ieee_is_finite(height))) RETURN
    IF (.NOT.ieee_is_finite(gas_constant) .OR. .NOT.ieee_is_finite(gravity)) RETURN
    IF (ANY(pressure<=0.0_real64) .OR. ANY(temperature<=0.0_real64)) RETURN
    IF (ANY(vapor<0.0_real64) .OR. ANY(vapor>=1.0_real64)) RETURN
    IF (gas_constant<=0.0_real64 .OR. gravity<=0.0_real64) RETURN

    first=2; last=n; stride=1
    IF (pressure(2)<pressure(n)) THEN
      first=n; last=2; stride=-1
    END IF
    DO k=first,last-stride,stride
      IF (pressure(k)<=pressure(k+stride)) RETURN
    END DO
    ! Traverse top down, matching the host's layer accumulation order.
    total=0.0_real128
    upper=0
    DO k=last,first,-stride
      IF (pressure(k)>=pressure(1)) CYCLE
      IF (upper/=0) THEN
        lower=k
        dz=REAL(height(upper),real128)-REAL(height(lower),real128)
        IF (dz<=0.0_real128) RETURN
        total=total+layer_integral(lower,upper,dz)
      END IF
      upper=k
    END DO
    IF (upper==0) RETURN
    dz=REAL(height(upper),real128)-REAL(height(1),real128)
    IF (dz>REAL(0.1_real64,real128)) total=total+layer_integral(1,upper,dz)
    IF (total>REAL(HUGE(integrated_vapor_pa),real128)) RETURN
    integrated_vapor_pa=REAL(total,real64)
    ok=.TRUE.
  CONTAINS
    PURE FUNCTION layer_integral(a,b,thickness) RESULT(integral)
      INTEGER, INTENT(IN) :: a,b
      REAL(real128), INTENT(IN) :: thickness
      REAL(real128) :: integral,rhobar,qbar
      rhobar=0.5_real128*(REAL(pressure(a),real128)/ &
        (REAL(gas_constant,real128)*REAL(temperature(a),real128))+ &
        REAL(pressure(b),real128)/(REAL(gas_constant,real128)*REAL(temperature(b),real128)))
      qbar=0.5_real128*(REAL(vapor(a),real128)+REAL(vapor(b),real128))
      integral=REAL(gravity,real128)*qbar/(1.0_real128+qbar)*rhobar*thickness
    END FUNCTION layer_integral
  END SUBROUTINE host_vapor_pressure_column

  ! Solve the host dry-surface-pressure relation while keeping the same
  ! represented pressure levels and supplied thermodynamic/height profiles.
  ! surface_scale is the caller's sfcprs2 terrain factor; target includes
  ! model-top pressure (it is not MU alone). This does not mutate a state or
  ! authorize a pressure increment. A changed domain needs a coupled remap.
  ! Callers must revalidate after storage rounding and geometry/EOS refresh.
  ! With the optional height response, solve PSFC and the surface-anchored
  ! height change together instead of using the fixed-height linear solution.
  PURE SUBROUTINE solve_host_surface_pressure(pressure,temperature,vapor,height, &
      gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa, &
      max_increment_pa,surface_pressure_pa,ok,height_log_ps_response,adjusted_height)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity,surface_scale
    REAL(real64), INTENT(IN) :: target_dry_surface_pressure_pa,max_increment_pa
    REAL(real64), INTENT(OUT) :: surface_pressure_pa
    LOGICAL, INTENT(OUT) :: ok
    ! Fixed-thermodynamic surface anchoring shifts every represented height
    ! by c*log(new_ps/old_ps), c=(alpha_surface+alpha_bottom)/(2*g), where
    ! alpha=p/rho_total uses all six species, not the host vapor integral.
    ! The caller supplies c in metres, after constructing the thermo increment
    ! at old_ps. Surface and unrepresented levels have zero response. This
    ! optional coupled solve does not authorize or serialize a state change.
    REAL(real64), INTENT(IN), OPTIONAL :: height_log_ps_response(:)
    REAL(real64), INTENT(INOUT), OPTIONAL :: adjusted_height(:)
    REAL(real64) :: integral,trial_integral,trial(SIZE(pressure)),proposed,tolerance
    REAL(real128) :: slope,qbar,dz,denominator,solution,residual,current_dry_surface
    INTEGER :: k,first_above
    LOGICAL :: valid

    ok=.FALSE.; surface_pressure_pa=0.0_real64
    IF (SIZE(pressure)<1) RETURN
    IF (ieee_is_finite(pressure(1))) surface_pressure_pa=pressure(1)
    CALL host_vapor_pressure_column(pressure,temperature,vapor,height, &
      gas_constant,gravity,integral,valid)
    IF (.NOT.valid) RETURN
    IF (.NOT.ALL(ieee_is_finite([surface_scale,target_dry_surface_pressure_pa,max_increment_pa]))) RETURN
    IF (surface_scale<=0.0_real64 .OR. target_dry_surface_pressure_pa<=0.0_real64) RETURN
    IF (max_increment_pa<0.0_real64) RETURN

    IF (PRESENT(height_log_ps_response) .OR. PRESENT(adjusted_height)) THEN
      IF (.NOT.PRESENT(height_log_ps_response) .OR. .NOT.PRESENT(adjusted_height)) RETURN
      CALL solve_coupled_height(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,max_increment_pa, &
        integral,surface_pressure_pa,adjusted_height,ok)
      RETURN
    END IF

    first_above=0
    DO k=2,SIZE(pressure)
      IF (pressure(k)>=pressure(1)) CYCLE
      IF (first_above==0) THEN
        first_above=k
      ELSE IF (pressure(k)>pressure(first_above)) THEN
        first_above=k
      END IF
    END DO
    ! For a fixed first above-ground level, I(p_s)=slope*p_s+constant.
    slope=0.0_real128
    dz=REAL(height(first_above),real128)-REAL(height(1),real128)
    IF (dz>REAL(0.1_real64,real128)) THEN
      qbar=0.5_real128*(REAL(vapor(1),real128)+REAL(vapor(first_above),real128))
      slope=REAL(gravity,real128)*qbar/(1.0_real128+qbar)*0.5_real128*dz/ &
        (REAL(gas_constant,real128)*REAL(temperature(1),real128))
    END IF
    denominator=REAL(surface_scale,real128)-slope
    IF (denominator<=0.0_real128) RETURN
    current_dry_surface=REAL(surface_scale,real128)*REAL(pressure(1),real128)- &
      REAL(integral,real128)
    IF (ABS(current_dry_surface)<=REAL(HUGE(integral),real128)) THEN
      IF (target_dry_surface_pressure_pa==REAL(current_dry_surface,real64)) THEN
        ok=.TRUE.
        RETURN
      END IF
    END IF
    solution=(REAL(target_dry_surface_pressure_pa,real128)+REAL(integral,real128)- &
      slope*REAL(pressure(1),real128))/denominator
    IF (solution<=0.0_real128 .OR. solution>REAL(HUGE(proposed),real128)) RETURN
    proposed=REAL(solution,real64)
    IF (ABS(REAL(proposed,real128)-REAL(pressure(1),real128))>REAL(max_increment_pa,real128)) RETURN
    IF (ANY((pressure(2:)<proposed) .NEQV. (pressure(2:)<pressure(1)))) RETURN
    trial=pressure; trial(1)=proposed
    CALL host_vapor_pressure_column(trial,temperature,vapor,height, &
      gas_constant,gravity,trial_integral,valid)
    IF (.NOT.valid) RETURN
    residual=REAL(surface_scale,real128)*REAL(proposed,real128)- &
      REAL(trial_integral,real128)-REAL(target_dry_surface_pressure_pa,real128)
    tolerance=32.0_real64*EPSILON(1.0_real64)* &
      MAX(1.0_real64,target_dry_surface_pressure_pa,trial_integral)
    IF (ABS(residual)>REAL(tolerance,real128)) RETURN
    surface_pressure_pa=proposed
    ok=.TRUE.
  END SUBROUTINE solve_host_surface_pressure

  ! Build a source-grid host PSFC proposal from a mapped pressure candidate.
  ! The background is the immutable mapped OFF inventory: its host dry-surface
  ! pressure is the target, while the candidate supplies the thermodynamic
  ! column and its already surface-anchored heights.  This routine proposes
  ! initial PSFC only; it does not preserve or infer a native-grid correction.
  ! No caller output is changed until every selected column, including its
  ! real32 storage check, succeeds.
  SUBROUTINE build_source_host_pressure_request(background,candidate,selected, &
      gas_constant,gravity,max_increment_pa,requested,status,failed_column)
    TYPE(pressure_wps_fields), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(IN) :: selected(:,:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity,max_increment_pa
    REAL(real64), INTENT(INOUT) :: requested(:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(OUT) :: failed_column(2)
    REAL(real64), ALLOCATABLE :: background_pressure(:),background_temperature(:)
    REAL(real64), ALLOCATABLE :: background_vapor(:),background_height(:)
    REAL(real64), ALLOCATABLE :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), ALLOCATABLE :: response(:),adjusted_height(:),trial_pressure(:)
    REAL(real64), ALLOCATABLE :: stored_height(:),expected_height(:)
    REAL(real64), ALLOCATABLE :: work_requested(:,:)
    REAL(real64) :: target,background_integral,solved_pressure,stored_pressure
    REAL(real64) :: trial_integral,expected_integral,residual,residual_budget
    REAL(real64) :: height_rounding_budget,response_coefficient
    REAL(real64) :: alpha_surface,alpha_lowest
    REAL(real64) :: surface_condensate(5),lowest_condensate(5)
    LOGICAL :: ascending,background_ok,candidate_ok,ok,valid,has_active
    INTEGER :: nx,ny,nz,i,j,k,lowest_active

    status=STATUS_FAILED
    failed_column=(/0,0/)

    ! Derive dimensions only from allocated descriptors.  This keeps all
    ! shape checks below safe even for a partially constructed WPS object.
    IF (.NOT.wps_dimensions_available(background,nx,ny,nz)) RETURN
    IF (.NOT.wps_shapes_ok(background,nx,ny,nz)) RETURN
    IF (.NOT.wps_dimensions_available(candidate,i,j,k)) RETURN
    IF (i/=nx .OR. j/=ny .OR. k/=nz) RETURN
    IF (.NOT.wps_shapes_ok(candidate,nx,ny,nz)) RETURN
    IF (.NOT.wps_values_ok(background) .OR. .NOT.wps_values_ok(candidate)) RETURN
    IF (.NOT.wps_pressure_order_ok(background%p,nz,background_ok)) RETURN
    IF (.NOT.wps_pressure_order_ok(candidate%p,nz,candidate_ok)) RETURN
    ascending=background_ok
    IF (candidate_ok .NEQV. ascending) RETURN

    IF (.NOT.wps_metadata_ok(background,background%valid_time,background%grid_id)) RETURN
    IF (.NOT.wps_metadata_ok(candidate,background%valid_time,background%grid_id)) RETURN
    IF (candidate%valid_time/=background%valid_time .OR. &
        TRIM(candidate%grid_id)/=TRIM(background%grid_id) .OR. &
        TRIM(candidate%wind_coordinate)/=TRIM(background%wind_coordinate)) RETURN
    IF (ANY(background%p/=candidate%p) .OR. ANY(background%psfc/=candidate%psfc)) RETURN
    ! Surface WPS height is the source terrain. Pressure-level heights may
    ! differ because the candidate has already received its surface anchor.
    IF (ANY(background%ht(:,:,nz+1)/=candidate%ht(:,:,nz+1))) RETURN
    IF (ANY(SHAPE(selected)/=(/nx,ny/)) .OR. ANY(SHAPE(requested)/=(/nx,ny/))) RETURN
    IF (.NOT.ieee_is_finite(gas_constant) .OR. .NOT.ieee_is_finite(gravity) .OR. &
        .NOT.ieee_is_finite(max_increment_pa) .OR. gas_constant<=0.0_real64 .OR. &
        gravity<=0.0_real64 .OR. max_increment_pa<0.0_real64) RETURN

    ALLOCATE(work_requested(nx,ny))
    work_requested=REAL(candidate%psfc,real64)
    ALLOCATE(background_pressure(nz+1),background_temperature(nz+1), &
             background_vapor(nz+1),background_height(nz+1), &
             pressure(nz+1),temperature(nz+1),vapor(nz+1),height(nz+1), &
             response(nz+1),adjusted_height(nz+1),trial_pressure(nz+1), &
             stored_height(nz+1),expected_height(nz+1))

    ! The request is initialized globally from candidate PSFC.  Only selected
    ! columns enter the host solve; unselected columns remain exact copies.
    DO j=1,ny
      DO i=1,nx
        IF (.NOT.selected(i,j)) CYCLE
        failed_column=(/i,j/)
        CALL build_wps_column(background,i,j,nz,background_pressure, &
          background_temperature,background_vapor,background_height)
        CALL build_wps_column(candidate,i,j,nz,pressure,temperature,vapor,height)
        CALL host_vapor_pressure_column(background_pressure,background_temperature, &
          background_vapor,background_height,gas_constant,gravity, &
          background_integral,valid)
        IF (.NOT.valid) RETURN
        target=REAL(background%psfc(i,j),real64)-background_integral

        ! The response coefficient is p/rho_total at the surface and at the
        ! lowest represented active pressure level.  WPS surface condensates
        ! are explicit zeros; surface QV is the supplied dry-air ratio.
        surface_condensate=0.0_real64
        alpha_surface=full_mixture_alpha(pressure(1),temperature(1),vapor(1), &
                                          surface_condensate)
        lowest_active=0
        DO k=2,nz+1
          IF (pressure(k)<pressure(1)) THEN
            IF (lowest_active==0) THEN
              lowest_active=k
            ELSE IF (pressure(k)>pressure(lowest_active)) THEN
              lowest_active=k
            END IF
          END IF
        END DO
        IF (lowest_active==0) RETURN
        lowest_condensate=[REAL(candidate%qc(i,j,lowest_active-1),real64), &
          REAL(candidate%qi(i,j,lowest_active-1),real64), &
          REAL(candidate%qr(i,j,lowest_active-1),real64), &
          REAL(candidate%qs(i,j,lowest_active-1),real64), &
          REAL(candidate%qg(i,j,lowest_active-1),real64)]
        alpha_lowest=full_mixture_alpha(pressure(lowest_active), &
          temperature(lowest_active),vapor(lowest_active),lowest_condensate)
        IF (alpha_surface<=0.0_real64 .OR. alpha_lowest<=0.0_real64) RETURN
        response_coefficient=(alpha_surface+alpha_lowest)/(2.0_real64*CANONICAL_GRAVITY)
        IF (.NOT.ieee_is_finite(response_coefficient) .OR. response_coefficient<0.0_real64) RETURN
        response=0.0_real64
        has_active=.FALSE.
        DO k=2,nz+1
          IF (pressure(k)<pressure(1)) THEN
            response(k)=response_coefficient
            has_active=.TRUE.
          END IF
        END DO
        IF (.NOT.has_active) RETURN

        CALL solve_host_surface_pressure(pressure,temperature,vapor,height, &
          gas_constant,gravity,1.0_real64,target,max_increment_pa, &
          solved_pressure,ok,response,adjusted_height)
        IF (.NOT.ok) THEN
          ! One rejected column is enough to reproduce the bounded solve;
          ! do not dump the full grid or silently drop the failed column.
          WRITE(*,*) 'source_host_failed_target_cap=',target,max_increment_pa
          WRITE(*,*) 'source_host_failed_pressure=',pressure
          WRITE(*,*) 'source_host_failed_temperature=',temperature
          WRITE(*,*) 'source_host_failed_vapor=',vapor
          WRITE(*,*) 'source_host_failed_height=',height
          WRITE(*,*) 'source_host_failed_height_response=',response
          RETURN
        END IF
        IF (.NOT.ieee_is_finite(solved_pressure)) RETURN
        stored_pressure=REAL(solved_pressure,real32)
        IF (.NOT.ieee_is_finite(stored_pressure) .OR. stored_pressure<=0.0_real64) RETURN
        IF (ABS(stored_pressure-pressure(1))>max_increment_pa) RETURN
        ! The host solver protects the real64 proposal. Repeat that contract
        ! after the value is stored in the WPS real32 PSFC field.
        IF (ANY((pressure(2:)<stored_pressure) .NEQV. &
                (pressure(2:)<pressure(1))) .OR. &
            ANY((pressure(2:)<=stored_pressure) .NEQV. &
                (pressure(2:)<=pressure(1)))) RETURN

        expected_height=height+response*LOG(stored_pressure/pressure(1))
        stored_height=REAL(REAL(expected_height,real32),real64)
        trial_pressure=pressure; trial_pressure(1)=stored_pressure
        CALL host_vapor_pressure_column(trial_pressure,temperature,vapor, &
          expected_height,gas_constant,gravity,expected_integral,valid)
        IF (.NOT.valid) RETURN
        CALL host_vapor_pressure_column(trial_pressure,temperature,vapor, &
          stored_height,gas_constant,gravity,trial_integral,valid)
        IF (.NOT.valid) RETURN
        residual=stored_pressure-trial_integral-target
        height_rounding_budget=ABS(trial_integral-expected_integral)
        residual_budget=2.0_real64*REAL(SPACING(REAL(stored_pressure,real32)),real64)+ &
          height_rounding_budget+128.0_real64*EPSILON(1.0_real64)* &
          MAX(1.0_real64,ABS(stored_pressure),ABS(trial_integral),ABS(target))
        ! This is a storage-rounding budget, not an exact-target promise.  In
        ! particular, do not accept a solver's exact-target fast path without
        ! this forward evaluation on the rounded profile.
        IF (.NOT.ieee_is_finite(residual) .OR. ABS(residual)>residual_budget) RETURN
        work_requested(i,j)=solved_pressure
      END DO
    END DO

    requested=work_requested
    failed_column=(/0,0/)
    status=STATUS_OK
  END SUBROUTINE build_source_host_pressure_request

  SUBROUTINE evaluate_source_host_pressure_residual(background,candidate,selected, &
      gas_constant,gravity,residual,status)
    ! Evaluate the actual mapped candidate, including remapped T/Q/height.
    ! This signed source-grid residual is neither a native conservation gate
    ! nor permission to change pressure. The caller owns the solve tolerance.
    TYPE(pressure_wps_fields), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(IN) :: selected(:,:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity
    REAL(real64), INTENT(INOUT) :: residual(:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: work(:,:),pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64) :: background_integral,candidate_integral
    INTEGER :: nx,ny,nz,i,j,k
    LOGICAL :: ascending,other_order,ok

    status=STATUS_FAILED
    IF (.NOT.wps_dimensions_available(background,nx,ny,nz)) RETURN
    IF (.NOT.wps_shapes_ok(background,nx,ny,nz)) RETURN
    IF (.NOT.wps_dimensions_available(candidate,i,j,k)) RETURN
    IF (i/=nx .OR. j/=ny .OR. k/=nz) RETURN
    IF (.NOT.wps_shapes_ok(candidate,nx,ny,nz)) RETURN
    IF (ANY(SHAPE(selected)/=[nx,ny]) .OR. ANY(SHAPE(residual)/=[nx,ny])) RETURN
    IF (.NOT.wps_values_ok(background) .OR. .NOT.wps_values_ok(candidate)) RETURN
    IF (.NOT.wps_pressure_order_ok(background%p,nz,ascending)) RETURN
    IF (.NOT.wps_pressure_order_ok(candidate%p,nz,other_order)) RETURN
    IF (ascending.NEQV.other_order) RETURN
    IF (ANY(background%p/=candidate%p)) RETURN
    IF (.NOT.wps_metadata_ok(background,background%valid_time,background%grid_id)) RETURN
    IF (.NOT.wps_metadata_ok(candidate,background%valid_time,background%grid_id)) RETURN
    IF (TRIM(background%wind_coordinate)/=TRIM(candidate%wind_coordinate)) RETURN
    IF (ANY(background%ht(:,:,nz+1)/=candidate%ht(:,:,nz+1))) RETURN
    IF (.NOT.ieee_is_finite(gas_constant) .OR. .NOT.ieee_is_finite(gravity)) RETURN
    IF (gas_constant<=0.0_real64 .OR. gravity<=0.0_real64) RETURN
    ALLOCATE(work(nx,ny),pressure(nz+1),temperature(nz+1),vapor(nz+1),height(nz+1))
    work=0.0_real64
    DO j=1,ny; DO i=1,nx
      IF (.NOT.selected(i,j)) CYCLE
      CALL build_wps_column(background,i,j,nz,pressure,temperature,vapor,height)
      CALL host_vapor_pressure_column(pressure,temperature,vapor,height, &
        gas_constant,gravity,background_integral,ok)
      IF (.NOT.ok) RETURN
      CALL build_wps_column(candidate,i,j,nz,pressure,temperature,vapor,height)
      CALL host_vapor_pressure_column(pressure,temperature,vapor,height, &
        gas_constant,gravity,candidate_integral,ok)
      IF (.NOT.ok) RETURN
      IF (REAL(background%psfc(i,j),real64)<=background_integral .OR. &
          REAL(candidate%psfc(i,j),real64)<=candidate_integral) RETURN
      work(i,j)=(REAL(candidate%psfc(i,j),real64)-REAL(background%psfc(i,j),real64))- &
        (candidate_integral-background_integral)
      IF (.NOT.ieee_is_finite(work(i,j))) RETURN
    END DO; END DO
    residual=work
    status=STATUS_OK
  END SUBROUTINE evaluate_source_host_pressure_residual

  LOGICAL FUNCTION wps_dimensions_available(fields,nx,ny,nz)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    INTEGER, INTENT(OUT) :: nx,ny,nz
    nx=0; ny=0; nz=0; wps_dimensions_available=.FALSE.
    IF (.NOT.ALLOCATED(fields%p) .OR. .NOT.ALLOCATED(fields%psfc)) RETURN
    IF (SIZE(fields%p)<3 .OR. SIZE(fields%psfc,1)<1 .OR. SIZE(fields%psfc,2)<1) RETURN
    nx=SIZE(fields%psfc,1); ny=SIZE(fields%psfc,2); nz=SIZE(fields%p)-1
    wps_dimensions_available=nz>=2
  END FUNCTION wps_dimensions_available

  SUBROUTINE build_wps_column(fields,i,j,nz,pressure,temperature,vapor,height)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    INTEGER, INTENT(IN) :: i,j,nz
    REAL(real64), INTENT(OUT) :: pressure(:),temperature(:),vapor(:),height(:)
    INTEGER :: k
    pressure(1)=REAL(fields%psfc(i,j),real64)
    temperature(1)=REAL(fields%t(i,j,nz+1),real64)
    vapor(1)=REAL(fields%qv(i,j,nz+1),real64)
    height(1)=REAL(fields%ht(i,j,nz+1),real64)
    DO k=1,nz
      pressure(k+1)=100.0_real64*REAL(fields%p(k),real64)
      temperature(k+1)=REAL(fields%t(i,j,k),real64)
      vapor(k+1)=REAL(fields%qv(i,j,k),real64)
      height(k+1)=REAL(fields%ht(i,j,k),real64)
    END DO
  END SUBROUTINE build_wps_column

  PURE REAL(real64) FUNCTION full_mixture_alpha(pressure,temperature,vapor,condensate)
    REAL(real64), INTENT(IN) :: pressure,temperature,vapor,condensate(:)
    REAL(real64) :: dry_density,total_density
    full_mixture_alpha=-1.0_real64
    IF (SIZE(condensate)/=5) RETURN
    IF (.NOT.ieee_is_finite(pressure) .OR. .NOT.ieee_is_finite(temperature) .OR. &
        .NOT.ieee_is_finite(vapor) .OR. .NOT.ALL(ieee_is_finite(condensate))) RETURN
    IF (ANY(condensate<0.0_real64)) RETURN
    dry_density=dry_air_density(pressure,temperature,vapor)
    IF (dry_density<=0.0_real64) RETURN
    total_density=dry_density*(1.0_real64+vapor+SUM(condensate))
    IF (.NOT.ieee_is_finite(total_density) .OR. total_density<=0.0_real64) RETURN
    full_mixture_alpha=pressure/total_density
    IF (.NOT.ieee_is_finite(full_mixture_alpha) .OR. full_mixture_alpha<=0.0_real64) &
      full_mixture_alpha=-1.0_real64
  END FUNCTION full_mixture_alpha

    PURE SUBROUTINE solve_coupled_height(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,max_increment_pa, &
        integral,solved_ps,solved_height,solved_ok)
      REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:),height_log_ps_response(:)
      REAL(real64), INTENT(IN) :: gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa
      REAL(real64), INTENT(IN) :: max_increment_pa,integral
      REAL(real64), INTENT(INOUT) :: solved_ps,solved_height(:)
      LOGICAL, INTENT(OUT) :: solved_ok
      REAL(real64) :: lo,hi,mid,flo,fhi,fmid,coefficient
      REAL(real64) :: tolerance,trial_height(SIZE(height))
      REAL(real128) :: low_wide,high_wide
      INTEGER :: iteration,j
      LOGICAL :: evaluated

      solved_ok=.FALSE.
      IF (SIZE(height_log_ps_response)/=SIZE(height) .OR. &
          SIZE(solved_height)/=SIZE(height)) RETURN
      IF (.NOT.ALL(ieee_is_finite(height_log_ps_response))) RETURN
      IF (height_log_ps_response(1)/=0.0_real64) RETURN
      coefficient=-1.0_real64
      DO j=2,SIZE(pressure)
        IF (pressure(j)>=pressure(1)) THEN
          IF (height_log_ps_response(j)/=0.0_real64) RETURN
        ELSE
          IF (height_log_ps_response(j)<0.0_real64) RETURN
          IF (coefficient<0.0_real64) coefficient=height_log_ps_response(j)
          IF (height_log_ps_response(j)/=coefficient) RETURN
        END IF
      END DO
      tolerance=64.0_real64*EPSILON(1.0_real64)* &
        MAX(1.0_real64,target_dry_surface_pressure_pa,integral)
      CALL evaluate_coupled_pressure(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa, &
        pressure(1),fmid,trial_height,evaluated)
      IF (.NOT.evaluated) RETURN
      IF (ABS(fmid)<=tolerance) THEN
        solved_height=height
        solved_ok=.TRUE.
        RETURN
      END IF
      ! Intersect the caller's pressure cap with the existing active-level
      ! interval. A newly exposed/buried level requires a separate remap.
      low_wide=MAX(REAL(TINY(lo),real128), &
        REAL(pressure(1),real128)-REAL(max_increment_pa,real128))
      high_wide=MIN(REAL(HUGE(hi),real128), &
        REAL(pressure(1),real128)+REAL(max_increment_pa,real128))
      lo=REAL(low_wide,real64); hi=REAL(high_wide,real64)
      DO j=2,SIZE(pressure)
        IF (pressure(j)<pressure(1)) THEN
          lo=MAX(lo,NEAREST(pressure(j),1.0_real64))
        ELSE
          hi=MIN(hi,pressure(j))
        END IF
      END DO
      IF (lo>=hi) RETURN
      CALL evaluate_coupled_pressure(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,lo,flo,trial_height,evaluated)
      IF (.NOT.evaluated) RETURN
      CALL evaluate_coupled_pressure(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,hi,fhi,trial_height,evaluated)
      IF (.NOT.evaluated) RETURN
      IF ((flo>0.0_real64 .AND. fhi>0.0_real64) .OR. &
          (flo<0.0_real64 .AND. fhi<0.0_real64)) RETURN
      DO iteration=1,100
        mid=lo+0.5_real64*(hi-lo)
        CALL evaluate_coupled_pressure(pressure,temperature,vapor,height,height_log_ps_response, &
          gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,mid,fmid,trial_height,evaluated)
        IF (.NOT.evaluated) RETURN
        IF (ABS(fmid)<=tolerance) THEN
          IF (ABS(REAL(mid,real128)-REAL(pressure(1),real128))>REAL(max_increment_pa,real128)) RETURN
          IF (ANY((pressure(2:)<mid) .NEQV. (pressure(2:)<pressure(1)))) RETURN
          IF (ANY(pressure(2:)==mid)) RETURN
          solved_ps=mid
          solved_height=trial_height
          solved_ok=.TRUE.
          RETURN
        END IF
        IF (mid==lo .OR. mid==hi) RETURN
        IF ((flo<0.0_real64 .AND. fmid<0.0_real64) .OR. &
            (flo>0.0_real64 .AND. fmid>0.0_real64)) THEN
          lo=mid; flo=fmid
        ELSE
          hi=mid; fhi=fmid
        END IF
      END DO
      ! Reaching the iteration cap is failure, with caller outputs unchanged.
    END SUBROUTINE solve_coupled_height

    PURE SUBROUTINE evaluate_coupled_pressure(pressure,temperature,vapor,height,height_log_ps_response, &
        gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa,ps,residual_value,trial_height,evaluated)
      REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:),height_log_ps_response(:)
      REAL(real64), INTENT(IN) :: gas_constant,gravity,surface_scale,target_dry_surface_pressure_pa
      REAL(real64), INTENT(IN) :: ps
      REAL(real64), INTENT(OUT) :: residual_value
      REAL(real64), INTENT(OUT) :: trial_height(:)
      LOGICAL, INTENT(OUT) :: evaluated
      REAL(real64) :: work_height(SIZE(height)),vapor_integral
      REAL(real64) :: trial(SIZE(pressure))
      REAL(real128) :: wide_height(SIZE(height)),wide_residual

      evaluated=.FALSE.; residual_value=0.0_real64
      wide_height=REAL(height,real128)+REAL(height_log_ps_response,real128)* &
        LOG(REAL(ps,real128)/REAL(pressure(1),real128))
      IF (ANY(ABS(wide_height)>REAL(HUGE(1.0_real64),real128))) RETURN
      work_height=REAL(wide_height,real64)
      IF (ANY(work_height(2:)<=work_height(1) .AND. pressure(2:)<ps)) RETURN
      trial=pressure; trial(1)=ps
      CALL host_vapor_pressure_column(trial,temperature,vapor,work_height, &
        gas_constant,gravity,vapor_integral,evaluated)
      IF (.NOT.evaluated) RETURN
      wide_residual=REAL(surface_scale,real128)*REAL(ps,real128)- &
        REAL(vapor_integral,real128)-REAL(target_dry_surface_pressure_pa,real128)
      evaluated=.FALSE.
      IF (ABS(wide_residual)>REAL(HUGE(residual_value),real128)) RETURN
      residual_value=REAL(wide_residual,real64)
      trial_height=work_height
      evaluated=.TRUE.
    END SUBROUTINE evaluate_coupled_pressure

  SUBROUTINE map_pressure_candidate_to_wps(candidate,background,mapped,status, &
                                            candidate_wind_coordinate)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(pressure_wps_fields), INTENT(IN) :: background
    TYPE(pressure_wps_fields), INTENT(INOUT) :: mapped
    INTEGER, INTENT(OUT) :: status
    CHARACTER(LEN=*), INTENT(IN) :: candidate_wind_coordinate
    TYPE(pressure_wps_fields) :: work
    INTEGER :: canonical_status,canonical_reason,nx,ny,nz,l,i,j
    LOGICAL :: ascending
    INTEGER :: canonical_level
    REAL(real64) :: pressure_reference

    status=STATUS_FAILED
    nx=candidate%grid%nx; ny=candidate%grid%ny; nz=candidate%grid%nz
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN

    ! The canonical validator owns the full state transaction contract.
    CALL validate_canonical_state(candidate,.FALSE.,.TRUE.,canonical_status, &
                                  canonical_reason,.TRUE.)
    IF (canonical_status/=STATUS_OK) RETURN
    IF (candidate%pressure%valid_time<=0_int64 .OR. &
        LEN_TRIM(candidate%grid%grid_id)==0) RETURN
    ! The state has no frame member: an explicit caller declaration is required.
    ! This adapter performs no rotation and currently supports grid-relative winds.
    IF (TRIM(candidate_wind_coordinate)/='GRID_RELATIVE') RETURN
    IF (.NOT.candidate_required_fields_ok(candidate,nx,ny,nz)) RETURN

    IF (.NOT.wps_shapes_ok(background,nx,ny,nz)) RETURN
    IF (.NOT.wps_metadata_ok(background,candidate%pressure%valid_time, &
                             candidate%grid%grid_id)) RETURN
    IF (.NOT.wps_values_ok(background)) RETURN
    IF (.NOT.wps_pressure_order_ok(background%p,nz,ascending)) RETURN

    ! Every WPS level must match exactly one canonical pressure coordinate.
    ! The legacy writer omits pressure levels above 1001 hPa.  Permit these
    ! only when they contain no represented candidate cells; retain their
    ! explicit fills in memory rather than shrinking the analysis domain.
    DO l=1,nz
      IF (ascending) THEN
        canonical_level=nz+1-l
      ELSE
        canonical_level=l
      END IF
      pressure_reference=REAL(100.0_real64*REAL(background%p(l),real64),real32)
      IF (candidate%pressure%value(1,1,canonical_level)/=pressure_reference) RETURN
      DO j=1,ny; DO i=1,nx
        IF (candidate%pressure%value(i,j,canonical_level)/=pressure_reference) RETURN
      END DO; END DO
      IF (pressure_reference>100100.0_real64) THEN
        IF (ANY(candidate%above_ground(:,:,canonical_level))) RETURN
      END IF
    END DO

    ! All checks above precede allocation.  The local work object is the only
    ! object mutated until the complete mapped product is ready.
    work=background
    ! RH/QV and all retained slabs are copied as supplied.  RH is not
    ! recomputed from QV and carries no thermodynamic/native authority here.
    ! The canonical FSF surface temperature is the WPS surface TT slab.
    ! Retain supplied surface slabs wherever canonical boundary data are absent.
    work%t(:,:,nz+1)=candidate%surface_temperature%value
    work%psfc=candidate%surface_pressure%value
    WHERE (candidate%surface_vapor%valid)
      work%qv(:,:,nz+1)=candidate%surface_vapor%value
    END WHERE
    WHERE (candidate%surface_height%valid)
      work%ht(:,:,nz+1)=candidate%surface_height%value
    END WHERE
    work%valid_time=candidate%pressure%valid_time
    work%grid_id=candidate%grid%grid_id
    work%wind_coordinate='GRID_RELATIVE'

    DO l=1,nz
      IF (ascending) THEN
        canonical_level=nz+1-l
      ELSE
        canonical_level=l
      END IF
      DO j=1,ny; DO i=1,nx
        IF (.NOT.candidate%above_ground(i,j,canonical_level)) CYCLE
        work%t(i,j,l)=candidate%temperature%value(i,j,canonical_level)
        work%ht(i,j,l)=REAL(REAL(candidate%geopotential%value(i,j,canonical_level),real64)/GRAVITY,real32)
        work%u(i,j,l)=candidate%u%value(i,j,canonical_level)
        work%v(i,j,l)=candidate%v%value(i,j,canonical_level)
        work%qv(i,j,l)=candidate%vapor%value(i,j,canonical_level)
        work%qc(i,j,l)=candidate%cloud_water%value(i,j,canonical_level)
        work%qi(i,j,l)=candidate%cloud_ice%value(i,j,canonical_level)
        work%qr(i,j,l)=candidate%rain%value(i,j,canonical_level)
        work%qs(i,j,l)=candidate%snow%value(i,j,canonical_level)
        work%qg(i,j,l)=candidate%graupel%value(i,j,canonical_level)
      END DO; END DO
    END DO

    mapped=work
    status=STATUS_OK
  END SUBROUTINE map_pressure_candidate_to_wps

  LOGICAL FUNCTION candidate_required_fields_ok(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    LOGICAL, ALLOCATABLE :: domain(:,:,:)
    INTEGER(int64) :: time
    candidate_required_fields_ok=.FALSE.
    IF (.NOT.ALLOCATED(state%above_ground)) RETURN
    IF (ANY(SHAPE(state%above_ground)/=(/nx,ny,nz/))) RETURN
    domain=state%above_ground
    IF (.NOT.ANY(domain)) RETURN
    time=state%pressure%valid_time
    IF (.NOT.field3d_complete_ok(state%geopotential,nx,ny,nz,time,'m2 s-2',domain, &
                                 -HUGE(1.0_real32),HUGE(1.0_real32),.FALSE.)) RETURN
    IF (.NOT.field3d_no_manufactured(state%pressure,nx,ny,nz,time,'Pa')) RETURN
    IF (.NOT.field3d_no_manufactured(state%temperature,nx,ny,nz,time,'K')) RETURN
    IF (.NOT.field3d_no_manufactured(state%u,nx,ny,nz,time,'m s-1')) RETURN
    IF (.NOT.field3d_no_manufactured(state%v,nx,ny,nz,time,'m s-1')) RETURN
    IF (.NOT.field3d_no_manufactured(state%vapor,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field3d_no_manufactured(state%cloud_water,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field3d_no_manufactured(state%cloud_ice,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field3d_no_manufactured(state%rain,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field3d_no_manufactured(state%snow,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field3d_no_manufactured(state%graupel,nx,ny,nz,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field2d_no_manufactured(state%surface_pressure,nx,ny,time,'Pa')) RETURN
    IF (.NOT.field2d_no_manufactured(state%surface_temperature,nx,ny,time,'K')) RETURN
    IF (.NOT.field2d_no_manufactured(state%surface_vapor,nx,ny,time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field2d_no_manufactured(state%surface_height,nx,ny,time,'m')) RETURN
    candidate_required_fields_ok=.TRUE.
  END FUNCTION candidate_required_fields_ok

  LOGICAL FUNCTION field3d_complete_ok(field,nx,ny,nz,time,unit,domain,lower,upper,all_valid)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    REAL(real32), INTENT(IN) :: lower,upper
    LOGICAL, INTENT(IN) :: all_valid
    INTEGER :: i,j,k
    field3d_complete_ok=.FALSE.
    IF (.NOT.field3d_shape_metadata_ok(field,nx,ny,nz,time,unit)) RETURN
    IF (all_valid) THEN
      IF (ANY(.NOT.ieee_is_finite(field%value))) RETURN
    ELSE IF (ANY(domain .AND. .NOT.ieee_is_finite(field%value))) THEN
      RETURN
    END IF
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality)) .OR. &
        ANY(IAND(field%source,SOURCE_MANUFACTURED_TEST)/=0_int32)) RETURN
    IF (all_valid) THEN
      IF (.NOT.ALL(field%valid) .OR. ANY(.NOT.cell_is_usable(field%valid, &
          field%quality,field%source))) RETURN
    ELSE IF (ANY(domain .AND. .NOT.cell_is_usable(field%valid,field%quality,field%source))) THEN
      RETURN
    END IF
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.domain(i,j,k)) CYCLE
      IF (field%value(i,j,k)<lower .OR. field%value(i,j,k)>upper) RETURN
    END DO; END DO; END DO
    field3d_complete_ok=.TRUE.
  END FUNCTION field3d_complete_ok

  LOGICAL FUNCTION field3d_no_manufactured(field,nx,ny,nz,time,unit)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER(int64), INTENT(IN) :: time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field3d_no_manufactured=.FALSE.
    IF (.NOT.field3d_shape_metadata_ok(field,nx,ny,nz,time,unit)) RETURN
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality)) .OR. &
        ANY(IAND(field%source,SOURCE_MANUFACTURED_TEST)/=0_int32)) RETURN
    field3d_no_manufactured=.TRUE.
  END FUNCTION field3d_no_manufactured

  LOGICAL FUNCTION field2d_no_manufactured(field,nx,ny,time,unit)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny
    INTEGER(int64), INTENT(IN) :: time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field2d_no_manufactured=.FALSE.
    IF (.NOT.field2d_shape_ok(field,nx,ny,time,unit)) RETURN
    IF (ANY(.NOT.source_bits_known(field%source)) .OR. &
        ANY(.NOT.quality_bits_known(field%quality)) .OR. &
        ANY(IAND(field%source,SOURCE_MANUFACTURED_TEST)/=0_int32)) RETURN
    field2d_no_manufactured=.TRUE.
  END FUNCTION field2d_no_manufactured

  LOGICAL FUNCTION field2d_shape_ok(field,nx,ny,time,unit)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny
    INTEGER(int64), INTENT(IN) :: time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    field2d_shape_ok=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=(/nx,ny/)) .OR. ANY(SHAPE(field%valid)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(field%quality)/=(/nx,ny/)) .OR. ANY(SHAPE(field%source)/=(/nx,ny/))) RETURN
    field2d_shape_ok=field%valid_time==time .AND. TRIM(field%unit)==TRIM(unit)
  END FUNCTION field2d_shape_ok

  LOGICAL FUNCTION wps_shapes_ok(fields,nx,ny,nz)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    INTEGER, INTENT(IN) :: nx,ny,nz
    wps_shapes_ok=.FALSE.
    IF (.NOT.ALLOCATED(fields%p) .OR. .NOT.ALLOCATED(fields%t) .OR. &
        .NOT.ALLOCATED(fields%ht) .OR. .NOT.ALLOCATED(fields%u) .OR. &
        .NOT.ALLOCATED(fields%v) .OR. .NOT.ALLOCATED(fields%rh) .OR. &
        .NOT.ALLOCATED(fields%qv) .OR. .NOT.ALLOCATED(fields%qc) .OR. &
        .NOT.ALLOCATED(fields%qi) .OR. .NOT.ALLOCATED(fields%qr) .OR. &
        .NOT.ALLOCATED(fields%qs) .OR. .NOT.ALLOCATED(fields%qg) .OR. &
        .NOT.ALLOCATED(fields%psfc) .OR. .NOT.ALLOCATED(fields%slp) .OR. &
        .NOT.ALLOCATED(fields%skin_temperature) .OR. .NOT.ALLOCATED(fields%snow_cover)) RETURN
    IF (SIZE(fields%p)/=nz+1 .OR. ANY(SHAPE(fields%t)/=(/nx,ny,nz+1/)) .OR. &
        ANY(SHAPE(fields%ht)/=(/nx,ny,nz+1/)) .OR. ANY(SHAPE(fields%u)/=(/nx,ny,nz+1/)) .OR. &
        ANY(SHAPE(fields%v)/=(/nx,ny,nz+1/)) .OR. ANY(SHAPE(fields%rh)/=(/nx,ny,nz+1/)) .OR. &
        ANY(SHAPE(fields%qv)/=(/nx,ny,nz+1/)) .OR. ANY(SHAPE(fields%qc)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(fields%qi)/=(/nx,ny,nz/)) .OR. ANY(SHAPE(fields%qr)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(fields%qs)/=(/nx,ny,nz/)) .OR. ANY(SHAPE(fields%qg)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(fields%psfc)/=(/nx,ny/)) .OR. ANY(SHAPE(fields%slp)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(fields%skin_temperature)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(fields%snow_cover)/=(/nx,ny/))) RETURN
    wps_shapes_ok=.TRUE.
  END FUNCTION wps_shapes_ok

  LOGICAL FUNCTION wps_metadata_ok(fields,time,grid_id)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    INTEGER(int64), INTENT(IN) :: time
    CHARACTER(LEN=*), INTENT(IN) :: grid_id
    wps_metadata_ok=fields%valid_time==time .AND. time>0_int64 .AND. &
      LEN_TRIM(fields%grid_id)>0 .AND. TRIM(fields%grid_id)==TRIM(grid_id) .AND. &
      TRIM(fields%wind_coordinate)=='GRID_RELATIVE'
  END FUNCTION wps_metadata_ok

  LOGICAL FUNCTION wps_values_ok(fields)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    wps_values_ok=.FALSE.
    IF (ANY(.NOT.ieee_is_finite(fields%p)) .OR. ANY(.NOT.ieee_is_finite(fields%t)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%ht)) .OR. ANY(.NOT.ieee_is_finite(fields%u)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%v)) .OR. ANY(.NOT.ieee_is_finite(fields%rh)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%qv)) .OR. ANY(.NOT.ieee_is_finite(fields%qc)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%qi)) .OR. ANY(.NOT.ieee_is_finite(fields%qr)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%qs)) .OR. ANY(.NOT.ieee_is_finite(fields%qg)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%psfc)) .OR. ANY(.NOT.ieee_is_finite(fields%slp)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%skin_temperature)) .OR. &
        ANY(.NOT.ieee_is_finite(fields%snow_cover))) RETURN
    IF (ANY(fields%t<100.0_real32) .OR. ANY(fields%t>400.0_real32) .OR. &
        ANY(fields%rh<0.0_real32) .OR. ANY(fields%rh>200.0_real32) .OR. &
        ANY(fields%qv<0.0_real32) .OR. ANY(fields%qc<0.0_real32) .OR. &
        ANY(fields%qi<0.0_real32) .OR. ANY(fields%qr<0.0_real32) .OR. &
        ANY(fields%qs<0.0_real32) .OR. ANY(fields%qg<0.0_real32) .OR. &
        ANY(fields%psfc<100.0_real32) .OR. ANY(fields%psfc>120000.0_real32) .OR. &
        ANY(fields%slp<100.0_real32) .OR. ANY(fields%slp>120000.0_real32) .OR. &
        ANY(fields%skin_temperature<100.0_real32) .OR. ANY(fields%skin_temperature>400.0_real32) .OR. &
        ANY(fields%snow_cover<0.0_real32) .OR. ANY(fields%snow_cover>1.0_real32)) RETURN
    wps_values_ok=.TRUE.
  END FUNCTION wps_values_ok

  LOGICAL FUNCTION wps_pressure_order_ok(p,nz,ascending)
    REAL(real32), INTENT(IN) :: p(:)
    INTEGER, INTENT(IN) :: nz
    LOGICAL, INTENT(OUT) :: ascending
    INTEGER :: k
    ascending=.FALSE.; wps_pressure_order_ok=.FALSE.
    IF (SIZE(p)/=nz+1) RETURN
    IF (p(nz+1)/=SURFACE_MARKER_HPA) RETURN
    IF (nz<2) RETURN
    IF (p(1)<p(2)) THEN
      ascending=.TRUE.
    ELSE IF (p(1)>p(2)) THEN
      ascending=.FALSE.
    ELSE
      RETURN
    END IF
    DO k=1,nz-1
      IF (ascending) THEN
        IF (p(k)>=p(k+1)) RETURN
      ELSE
        IF (p(k)<=p(k+1)) RETURN
      END IF
    END DO
    IF (ANY(p(1:nz)<=0.0_real32) .OR. ANY(p(1:nz)>1200.0_real32)) RETURN
    wps_pressure_order_ok=.TRUE.
  END FUNCTION wps_pressure_order_ok

END MODULE cloud_bal_wps_adapter
