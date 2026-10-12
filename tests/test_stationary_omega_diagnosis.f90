PROGRAM test_stationary_omega_diagnosis
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator, ONLY: balance_operator_type,build_diagnostic_balance_operator, &
    state_continuity_residual,state_dry_air_mass_flux_divergence,diagnose_stationary_omega, &
    DIAGNOSTIC_REASON_INCOMPATIBLE_BOUNDARY
  IMPLICIT NONE
  INTEGER, PARAMETER :: nx=6,ny=6,nz=3
  TYPE(cloud_bal_state_type) :: state,candidate,rejected,without_omega
  TYPE(balance_operator_type) :: op
  LOGICAL :: control(nx,ny,nz)
  REAL(real64) :: dry_fraction(nx,ny,nz),residual(nx,ny,nz),max_residual,boundary_mismatch
  REAL(real64) :: flux_scale
  INTEGER :: status,reason,i,j

  CALL make_state(state)
  CALL build_diagnostic_balance_operator(state,op,status,reason)
  CALL require(status==STATUS_OK,'diagnostic operator build')
  dry_fraction=state%grid%dry_air_mass_measure/state%grid%pressure_mass_measure
  state%omega%value=0.0_real32
  CALL state_continuity_residual(op,state,residual,status,dry_fraction)
  CALL require(status==STATUS_OK,'zero-omega residual')
  DO j=1,ny; DO i=1,nx
    state%omega_top_boundary%value(i,j)=REAL( &
      SUM(residual(i,j,:)*state%grid%pressure_mass_measure(i,j,:))/ &
      (state%grid%dx(i,j)*state%grid%dy(i,j)/9.80665_real64*dry_fraction(i,j,nz)),real32)
  END DO; END DO
  control=.FALSE.; control(2:5,2:5,:)=.TRUE.
  CALL diagnose_stationary_omega(state,control,candidate,max_residual,boundary_mismatch,status,reason)
  CALL require(status==STATUS_OK,'compatible fixed boundary producer')
  flux_scale=MAXVAL(ABS(candidate%omega_top_boundary%value(2:5,2:5))* &
    candidate%grid%dx(2:5,2:5)*candidate%grid%dy(2:5,2:5)/9.80665_real64* &
    dry_fraction(2:5,2:5,nz))
  CALL require(max_residual<=64.0_real64*REAL(EPSILON(1.0_real32),real64)*flux_scale, &
    'stored residual is bounded by float32 boundary-flux scale')
  CALL require(ANY(candidate%omega%value(2:5,2:5,:)/=state%omega%value(2:5,2:5,:)), &
    'nonzero spatial omega was diagnosed')
  without_omega=candidate; without_omega%omega=state%omega
  CALL require(canonical_states_equal(without_omega,state), &
    'support and all non-omega state fields are preserved')
  CALL require(ALL(candidate%omega%value(1,:,:)==state%omega%value(1,:,:)) .AND. &
    ALL(candidate%omega%value(6,:,:)==state%omega%value(6,:,:)), &
    'omega outside the control region is preserved')

  state%omega_top_boundary%value(3,3)=state%omega_top_boundary%value(3,3)+1.0_real32
  CALL diagnose_stationary_omega(state,control,rejected,max_residual,boundary_mismatch,status,reason)
  CALL require(status==STATUS_FAILED .AND. reason==DIAGNOSTIC_REASON_INCOMPATIBLE_BOUNDARY, &
    'incompatible prescribed boundaries reject')
  CALL require(boundary_mismatch>0.0_real64 .AND. canonical_states_equal(rejected,state), &
    'rejection reports mismatch and rolls back the whole state')
  PRINT '(A)','stationary omega producer tests passed: spatial profile, support identity, fixed-boundary rejection'
  PRINT '(A)','scope: analytical finite-volume fixture; no observed authority or CP06-A acceptance'
CONTAINS
  SUBROUTINE require(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      PRINT '(A)', 'FAIL: '//message
      ERROR STOP 1
    END IF
  END SUBROUTINE require

  SUBROUTINE fill(field,value,source)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    INTEGER(int32), INTENT(IN) :: source
    field%value=value; field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE fill

  SUBROUTINE make_state(result)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: result
    INTEGER :: local_status,ii,jj,kk
    CALL initialize_cloud_bal_state(result,nx,ny,nz,1786885200_int64, &
      'stationary-omega-test',local_status)
    CALL require(local_status==STATUS_OK,'initialize state')
    result%grid%dx=2000.0_real64; result%grid%dy=3000.0_real64
    DO kk=1,nz
      result%pressure%value(:,:,kk)=REAL(95000-10000*(kk-1),real32)
    END DO
    result%temperature%value=280.0_real32; result%vapor%value=0.01_real32
    DO kk=1,nz; DO jj=1,ny; DO ii=1,nx
      result%u%value(ii,jj,kk)=REAL(ii*kk,real32)
    END DO; END DO; END DO
    result%v%value=0.0_real32; result%omega%value=0.0_real32
    CALL fill(result%pressure,95000.0_real32,SOURCE_BACKGROUND_MODEL)
    DO kk=1,nz
      result%pressure%value(:,:,kk)=REAL(95000-10000*(kk-1),real32)
    END DO
    CALL fill(result%temperature,280.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill(result%vapor,0.01_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill(result%u,0.0_real32,SOURCE_ANALYZED_WIND)
    DO kk=1,nz; DO jj=1,ny; DO ii=1,nx
      result%u%value(ii,jj,kk)=REAL(ii*kk,real32)
    END DO; END DO; END DO
    CALL fill(result%v,0.0_real32,SOURCE_ANALYZED_WIND)
    CALL fill(result%omega,0.0_real32,SOURCE_BACKGROUND_MODEL)
    result%surface_pressure%value=100000.0_real32
    result%surface_pressure%valid=.TRUE.; result%surface_pressure%quality=0_int32
    result%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    result%surface_temperature%value=290.0_real32
    result%surface_temperature%valid=.TRUE.; result%surface_temperature%quality=0_int32
    result%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    result%omega_top_boundary%value=0.0_real32; result%omega_bottom_boundary%value=0.0_real32
    result%omega_top_boundary%valid=.TRUE.; result%omega_bottom_boundary%valid=.TRUE.
    result%omega_top_boundary%quality=0_int32; result%omega_bottom_boundary%quality=0_int32
    result%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    result%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(result,local_status)
    CALL require(local_status==STATUS_OK,'configure pressure geometry')
    CALL refresh_dry_air_mass_measure(result,local_status)
    CALL require(local_status==STATUS_OK,'refresh dry air mass')
  END SUBROUTINE make_state
END PROGRAM test_stationary_omega_diagnosis
