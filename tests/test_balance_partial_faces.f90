! Independent dense overlap oracle for the pressure-diagnostic balance path.
! No native dry-mass or observational dynamic authority is established here.
PROGRAM test_balance_partial_faces
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE
  INTEGER, PARAMETER :: nx=6,ny=6,nz=3,nt=nx*ny*nz
  REAL(real64), PARAMETER :: gravity=9.80665_real64
  INTEGER :: axis

  DO axis=1,2
    CALL test_partial_faces(axis,.FALSE.)
    CALL test_partial_faces(axis,.TRUE.)
    CALL test_partial_faces(axis,.FALSE.,.TRUE.)
  END DO
  CALL test_uniform_dry_fraction(1)
  CALL test_varying_dry_fraction()
  CALL test_dry_boundary_budget()
  CALL test_vertical_boundary_fraction()
  CALL test_stale_dry_mass_rejected()
  CALL test_condensate_changes_fraction()
  CALL test_dry_preserves_operator_volume()
  PRINT *,'Balance partial-face tests passed: cross-level flux, dry flux, adjoint, support, components, final state'

CONTAINS

  SUBROUTINE require(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      PRINT *,'FAIL: ',message
      ERROR STOP 1
    END IF
  END SUBROUTINE require

  SUBROUTINE usable(field)
    TYPE(field3d), INTENT(INOUT) :: field
    field%valid=.TRUE.; field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE usable

  SUBROUTINE make_state(state,axis,hole)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN) :: axis
    LOGICAL, INTENT(IN) :: hole
    INTEGER :: status,k

    CALL initialize_cloud_bal_state(state,nx,ny,nz,1786885200_int64,'partial-face-balance',status)
    CALL require(status==STATUS_OK,'initialize')
    state%grid%dx=2000.0_real64; state%grid%dy=3000.0_real64
    DO k=1,nz
      state%pressure%value(:,:,k)=100000.0_real32-5000.0_real32*(k-1)
    END DO
    state%temperature%value=280.0_real32; state%vapor%value=0.01_real32
    state%u%value=0.0_real32; state%v%value=0.0_real32; state%omega%value=0.0_real32
    CALL usable(state%pressure); CALL usable(state%temperature); CALL usable(state%vapor)
    CALL usable(state%u); CALL usable(state%v); CALL usable(state%omega)
    state%omega_target%valid=.FALSE.
    state%surface_pressure%value=100000.0_real32
    IF (axis==1) THEN
      state%surface_pressure%value(4:,:)=99000.0_real32
    ELSE
      state%surface_pressure%value(:,4:)=99000.0_real32
    END IF
    state%surface_pressure%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32; state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32; state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,status)
    CALL require(status==STATUS_OK,'configure geometry')
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'refresh diagnostic dry mass')
    state%balance_beta=1.0_real32
    WHERE(.NOT.state%above_ground) state%balance_beta=0.0_real32
    IF (hole) state%balance_beta(3,3,1)=0.0_real32
  END SUBROUTINE make_state

  SUBROUTINE make_flat_state(state,axis)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN) :: axis
    INTEGER :: status

    CALL make_state(state,axis,.FALSE.)
    state%surface_pressure%value=100000.0_real32
    CALL configure_pressure_geometry(state,status)
    CALL require(status==STATUS_OK,'flat pressure geometry')
    state%balance_beta=1.0_real32
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'flat diagnostic dry mass')
  END SUBROUTINE make_flat_state

  SUBROUTINE build_test_operator(state,op,view)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_type), INTENT(OUT) :: op
    TYPE(balance_operator_snapshot), INTENT(OUT) :: view
    TYPE(balance_operator_config) :: cfg
    INTEGER :: status,reason

    CALL build_balance_operator(state,cfg,op,status,reason)
    IF (status/=STATUS_OK) PRINT *,'build reason=',reason
    CALL require(status==STATUS_OK,'build dry-flux operator')
    CALL snapshot_balance_operator(op,view,status)
    CALL require(status==STATUS_OK,'snapshot dry-flux operator')
  END SUBROUTINE build_test_operator

  SUBROUTINE test_uniform_dry_fraction(axis)
    INTEGER, INTENT(IN) :: axis
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: total(nx,ny,nz),dry(nx,ny,nz),expected(nx,ny,nz)
    REAL(real64) :: fraction,scale
    INTEGER :: i,j,k,status

    CALL make_state(state,axis,.FALSE.)
    state%u%value=0.0_real32; state%u%value(3,3,1)=2.0_real32
    CALL build_test_operator(state,op,view)
    CALL state_continuity_residual(op,state,total,status)
    CALL require(status==STATUS_OK,'uniform-fraction total residual')
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'uniform-fraction dry divergence')
    fraction=1.0_real64/(1.0_real64+REAL(state%vapor%value(1,1,1),real64))
    expected=0.0_real64
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (view%cell_active(i,j,k)) expected(i,j,k)=fraction*total(i,j,k)*view%volume(i,j,k)
    END DO; END DO; END DO
    scale=MAX(1.0_real64,MAXVAL(ABS(expected)))
    CALL require(MAXVAL(ABS(dry-expected))<1.0e-11_real64*scale, &
      'uniform dry fraction scales total residual in kg/s')
  END SUBROUTINE test_uniform_dry_fraction

  SUBROUTINE test_varying_dry_fraction()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: total(nx,ny,nz),dry(nx,ny,nz),expected(nx,ny,nz)
    REAL(real64) :: fraction(nx,ny,nz),area,wl,wr,flux
    INTEGER :: i,j,k,status

    CALL make_flat_state(state,1)
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%vapor%value(i,j,k)=REAL(0.005_real64+0.003_real64*i,real32)
    END DO; END DO; END DO
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'varying-vapor dry mass refresh')
    state%u%value=1.0_real32; state%v%value=0.0_real32; state%omega%value=0.0_real32
    CALL build_test_operator(state,op,view)
    CALL state_continuity_residual(op,state,total,status)
    CALL require(status==STATUS_OK,'uniform carrier residual')
    CALL require(MAXVAL(ABS(total))<1.0e-12_real64,'uniform carrier is divergence free')
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'varying-vapor dry divergence')
    CALL require(MAXVAL(ABS(dry(2:nx-1,:,:)))>1.0e-6_real64, &
      'varying vapor gives nonzero dry divergence')

    ! Vary both f_d and u.  This catches an implementation that computes
    ! (interpolated f_d)*(interpolated u) instead of interpolating f_d*u.
    DO i=1,nx
      state%u%value(i,:,:)=REAL(0.25_real64+0.4_real64*i,real32)
    END DO
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'varying-vapor varying-wind dry divergence')
    fraction=0.0_real64
    WHERE(state%above_ground)
      fraction=state%grid%dry_air_mass_measure/state%grid%pressure_mass_measure
    END WHERE
    expected=0.0_real64
    DO j=1,ny; DO k=1,nz
      DO i=1,nx-1
        area=0.5_real64*(state%grid%dy(i,j)+state%grid%dy(i+1,j))* &
          state%grid%cell_dp(i,j,k)/gravity
        wl=state%grid%dx(i+1,j)/(state%grid%dx(i,j)+state%grid%dx(i+1,j))
        wr=1.0_real64-wl
        flux=area*(wl*fraction(i,j,k)*REAL(state%u%value(i,j,k),real64)+ &
          wr*fraction(i+1,j,k)*REAL(state%u%value(i+1,j,k),real64))
        expected(i,j,k)=expected(i,j,k)+flux
        expected(i+1,j,k)=expected(i+1,j,k)-flux
      END DO
    END DO; END DO
    DO j=1,ny; DO k=1,nz
        area=state%grid%dy(1,j)*state%grid%cell_dp(1,j,k)/gravity
        expected(1,j,k)=expected(1,j,k)-area*fraction(1,j,k)* &
          REAL(state%u%value(1,j,k),real64)
        area=state%grid%dy(nx,j)*state%grid%cell_dp(nx,j,k)/gravity
        expected(nx,j,k)=expected(nx,j,k)+area*fraction(nx,j,k)* &
          REAL(state%u%value(nx,j,k),real64)
    END DO; END DO
    CALL require(MAXVAL(ABS(dry-expected))<1.0e-11_real64*MAX(1.0_real64,MAXVAL(ABS(expected))), &
      'analytic f_d*u face interpolation')
  END SUBROUTINE test_varying_dry_fraction

  SUBROUTINE test_dry_boundary_budget()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: dry(nx,ny,nz),fraction(nx,ny,nz),expected,area
    INTEGER :: i,j,k,status

    CALL make_flat_state(state,1)
    DO i=1,nx
      state%vapor%value(i,:,:)=REAL(0.005_real64+0.004_real64*i,real32)
    END DO
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'boundary-budget dry mass refresh')
    state%u%value=1.0_real32; state%v%value=0.0_real32; state%omega%value=0.0_real32
    CALL build_test_operator(state,op,view)
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'boundary-budget dry divergence')
    fraction=0.0_real64
    WHERE(state%above_ground)
      fraction=state%grid%dry_air_mass_measure/state%grid%pressure_mass_measure
    END WHERE
    expected=0.0_real64
    DO k=1,nz; DO j=1,ny
      area=state%grid%dy(1,j)*state%grid%cell_dp(1,j,k)/gravity
      expected=expected-area*fraction(1,j,k)*REAL(state%u%value(1,j,k),real64)
      area=state%grid%dy(nx,j)*state%grid%cell_dp(nx,j,k)/gravity
      expected=expected+area*fraction(nx,j,k)*REAL(state%u%value(nx,j,k),real64)
    END DO; END DO
    CALL require(ABS(SUM(dry)-expected)<1.0e-11_real64*MAX(1.0_real64,ABS(expected)), &
      'dry divergence closes to analytic boundary budget')
  END SUBROUTINE test_dry_boundary_budget

  SUBROUTINE test_vertical_boundary_fraction()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: dry(nx,ny,nz),expected(nx,ny,nz),fraction(nx,ny,nz),area
    INTEGER :: i,j,k,status

    CALL make_flat_state(state,1)
    DO k=1,nz
      state%vapor%value(:,:,k)=REAL(0.005_real64+0.003_real64*k,real32)
    END DO
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'vertical-boundary dry mass refresh')
    state%omega%value=0.0_real32
    state%omega_top_boundary%value=1.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    CALL build_test_operator(state,op,view)
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'vertical-boundary dry divergence')
    fraction=0.0_real64
    WHERE(state%above_ground)
      fraction=state%grid%dry_air_mass_measure/state%grid%pressure_mass_measure
    END WHERE
    expected=0.0_real64
    DO j=1,ny; DO i=1,nx
      area=state%grid%dx(i,j)*state%grid%dy(i,j)/gravity
      expected(i,j,nz)=-area*fraction(i,j,nz)* &
        REAL(state%omega_top_boundary%value(i,j),real64)
    END DO; END DO
    CALL require(MAXVAL(ABS(dry-expected))<1.0e-11_real64*MAX(1.0_real64,MAXVAL(ABS(expected))), &
      'vertical boundary uses nearest interior dry fraction')
  END SUBROUTINE test_vertical_boundary_fraction

  SUBROUTINE test_stale_dry_mass_rejected()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: dry(nx,ny,nz)
    INTEGER :: status

    CALL make_state(state,1,.FALSE.)
    CALL build_test_operator(state,op,view)
    state%grid%dry_air_mass_measure(2,2,1)= &
      0.5_real64*state%grid%dry_air_mass_measure(2,2,1)
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status/=STATUS_OK,'stale dry mass rejected')
    CALL require(ALL(dry==0.0_real64),'rejected dry mass leaves no flux')
  END SUBROUTINE test_stale_dry_mass_rejected

  SUBROUTINE test_condensate_changes_fraction()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: dry(nx,ny,nz),fraction,scale
    INTEGER :: status

    CALL make_flat_state(state,1)
    CALL usable(state%cloud_water)
    state%cloud_water%value=0.10_real32
    CALL refresh_dry_air_mass_measure(state,status)
    CALL require(status==STATUS_OK,'condensate dry mass refresh')
    fraction=1.0_real64/(1.0_real64+REAL(state%vapor%value(1,1,1),real64)+ &
      REAL(state%cloud_water%value(1,1,1),real64))
    scale=MAX(1.0_real64,MAXVAL(state%grid%pressure_mass_measure))
    CALL require(MAXVAL(ABS(state%grid%dry_air_mass_measure- &
      fraction*state%grid%pressure_mass_measure))<1.0e-7_real64*scale, &
      'condensate changes dry fraction')
    CALL build_test_operator(state,op,view)
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK .AND. ALL(dry==0.0_real64), &
      'condensate alone creates no dry-air transport')
    state%u%value=0.0_real32; state%u%value(3,3,1)=2.0_real32
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'condensate dry divergence')
  END SUBROUTINE test_condensate_changes_fraction

  SUBROUTINE test_dry_preserves_operator_volume()
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: before(nx,ny,nz),dry(nx,ny,nz)
    INTEGER :: status

    CALL make_state(state,1,.FALSE.)
    CALL build_test_operator(state,op,view)
    before=view%volume
    CALL state_dry_air_mass_flux_divergence(op,state,dry,status)
    CALL require(status==STATUS_OK,'volume-preservation dry divergence')
    CALL snapshot_balance_operator(op,view,status)
    CALL require(status==STATUS_OK,'snapshot after dry divergence')
    CALL require(ALL(view%volume==before),'dry divergence preserves operator volume')
    CALL require(ALL(state%grid%pressure_mass_measure==before), &
      'dry divergence preserves pressure mass metric')
  END SUBROUTINE test_dry_preserves_operator_volume

  SUBROUTINE test_partial_faces(axis,hole,nonuniform)
    INTEGER, INTENT(IN) :: axis
    LOGICAL, INTENT(IN) :: hole
    LOGICAL, INTENT(IN), OPTIONAL :: nonuniform
    TYPE(cloud_bal_state_type) :: state,candidate
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64) :: u(nx,ny,nz),v(nx,ny,nz),omega(nx,ny,nz),lambda(nx,ny,nz)
    REAL(real64) :: du(nx,ny,nz),dv(nx,ny,nz),dw(nx,ny,nz),actual(nx,ny,nz),expected(nx,ny,nz)
    REAL(real64) :: atu(nx,ny,nz),atv(nx,ny,nz),atw(nx,ny,nz),normal(nx,ny,nz)
    REAL(real64) :: lhs,rhs,scale
    INTEGER :: i,j,k,status,reason
    LOGICAL :: varying_metric

    CALL make_state(state,axis,hole)
    varying_metric=.FALSE.
    IF (PRESENT(nonuniform)) varying_metric=nonuniform
    IF (varying_metric) THEN
      ! Genuine nonzero center coefficients must survive the roundoff rule.
      DO j=1,ny; DO i=1,nx
        state%grid%dx(i,j)=2000.0_real64+5.0_real64*i+j
        state%grid%dy(i,j)=3000.0_real64+17.0_real64*i+2.0_real64*j
      END DO; END DO
      CALL configure_pressure_geometry(state,status)
      CALL require(status==STATUS_OK,'nonuniform pressure geometry')
      CALL refresh_dry_air_mass_measure(state,status)
      CALL require(status==STATUS_OK,'nonuniform diagnostic dry mass')
    END IF
    CALL build_balance_operator(state,cfg,op,status,reason)
    IF (status/=STATUS_OK) PRINT *,'build reason=',reason
    CALL require(status==STATUS_OK,'build partial-face operator')
    CALL snapshot_balance_operator(op,view,status)
    CALL require(status==STATUS_OK,'snapshot')
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      lambda(i,j,k)=SIN(0.7_real64*i+0.3_real64*j-0.5_real64*k)
    END DO; END DO; END DO
    u=0.0_real64; v=0.0_real64; omega=0.0_real64
    IF (.NOT.hole) THEN
      IF (axis==1) THEN
        u(4,3,2)=1.0_real64
      ELSE
        v(3,4,2)=1.0_real64
      END IF
      CALL dense_horizontal_residual(state,view%cell_active,u,v,expected)
      ! 1500 Pa shared face / 2500 Pa cell; interpolation weight 1/2.
      scale=MERGE(2000.0_real64,3000.0_real64,axis==1)
      IF (.NOT.varying_metric) CALL require(ABS(expected(3,3,1)-0.3_real64/scale)<1.0e-15_real64, &
        'literal cross-level flux')
      CALL apply_continuity_operator(op,u,v,omega,actual,status)
      CALL require(status==STATUS_OK,'cross-level continuity')
      CALL require(MAXVAL(ABS(actual-expected))<1.0e-13_real64,'continuity versus dense overlap')
      CALL apply_adjoint_metric(op,lambda,atu,atv,atw,status)
      CALL require(status==STATUS_OK,'cross-level adjoint')
      lhs=SUM(view%volume*lambda*expected)
      rhs=SUM(atu*u+atv*v)
      CALL require(ABS(lhs-rhs)<1.0e-12_real64*MAX(1.0_real64,ABS(lhs)), &
        'independent metric adjoint identity')
    END IF

    CALL apply_balance_correction(op,lambda,du,dv,dw,status)
    CALL require(status==STATUS_OK,'partial-face correction')
    CALL require(ALL(dw==0.0_real64),'no omega authority no omega increment')
    CALL require(ALL(du(1,:,:)==0.0_real64) .AND. ALL(du(nx,:,:)==0.0_real64), &
      'exterior x-normal increment')
    CALL require(ALL(dv(:,1,:)==0.0_real64) .AND. ALL(dv(:,ny,:)==0.0_real64), &
      'exterior y-normal increment')
    CALL require(ALL(PACK(du,.NOT.view%cell_active)==0.0_real64) .AND. &
      ALL(PACK(dv,.NOT.view%cell_active)==0.0_real64),'outside-support identity')
    IF (hole) THEN
      IF (axis==1) THEN
        CALL require(du(4,3,2)==0.0_real64,'cross-level x support face must be closed')
      ELSE
        CALL require(dv(3,4,2)==0.0_real64,'cross-level y support face must be closed')
      END IF
    END IF
    scale=MAX(MAXVAL(ABS(du)),MAXVAL(ABS(dv)),1.0_real64)
    du=du/scale; dv=dv/scale
    CALL dense_horizontal_residual(state,view%cell_active,du,dv,expected)
    CALL apply_continuity_operator(op,du,dv,dw,actual,status)
    CALL require(status==STATUS_OK,'correction continuity')
    CALL require(MAXVAL(ABS(actual-expected))<1.0e-12_real64,'support closure dense oracle')
    CALL require(ABS(SUM(view%volume*actual))<1.0e-10_real64* &
      MAX(1.0_real64,SUM(ABS(view%volume*actual))),'equal/opposite internal flux budget')
    CALL apply_normal_operator(op,lambda,normal,status)
    CALL require(status==STATUS_OK,'normal operator')
    CALL require(MAXVAL(ABS(normal+scale*actual))<1.0e-11_real64* &
      MAX(1.0_real64,MAXVAL(ABS(normal))),'normal equals negative divergence of correction')
    CALL require(SUM(view%volume*lambda*normal)>=0.0_real64,'nonnegative normal energy')

    ! Compare the actual serialized precision, not the unrounded increment.
    candidate=state
    candidate%u%value=REAL(du,real32); candidate%v%value=REAL(dv,real32)
    u=REAL(candidate%u%value,real64); v=REAL(candidate%v%value,real64)
    CALL dense_horizontal_residual(candidate,view%cell_active,u,v,expected)
    CALL state_continuity_residual(op,candidate,actual,status)
    CALL require(status==STATUS_OK,'final float32 state residual')
    CALL require(MAXVAL(ABS(actual-expected))<1.0e-12_real64,'final state versus independent overlap')
    CALL check_components(op,state,view)
  END SUBROUTINE test_partial_faces

  SUBROUTINE dense_horizontal_residual(state,active,u,v,residual)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    LOGICAL, INTENT(IN) :: active(nx,ny,nz)
    REAL(real64), INTENT(IN) :: u(nx,ny,nz),v(nx,ny,nz)
    REAL(real64), INTENT(OUT) :: residual(nx,ny,nz)
    INTEGER :: i,j,k,m
    REAL(real64) :: dp,area,flux,wl,wr

    ! Deliberately use all cell pairs, never partition_pressure_face or op areas.
    ! Inputs are closed increments: domain exterior velocity and omega are zero.
    residual=0.0_real64
    DO j=1,ny; DO i=1,nx-1; DO k=1,nz; DO m=1,nz
      IF (.NOT.(state%above_ground(i,j,k) .AND. state%above_ground(i+1,j,m))) CYCLE
      dp=MAX(0.0_real64,MIN(state%grid%pressure_interface(i,j,k), &
        state%grid%pressure_interface(i+1,j,m))-MAX(state%grid%pressure_interface(i,j,k+1), &
        state%grid%pressure_interface(i+1,j,m+1)))
      area=0.5_real64*(state%grid%dy(i,j)+state%grid%dy(i+1,j))*dp/gravity
      wl=state%grid%dx(i+1,j)/(state%grid%dx(i,j)+state%grid%dx(i+1,j)); wr=1.0_real64-wl
      flux=area*(wl*u(i,j,k)+wr*u(i+1,j,m))
      IF (active(i,j,k)) residual(i,j,k)=residual(i,j,k)+flux/state%grid%pressure_mass_measure(i,j,k)
      IF (active(i+1,j,m)) residual(i+1,j,m)=residual(i+1,j,m)-flux/state%grid%pressure_mass_measure(i+1,j,m)
    END DO; END DO; END DO; END DO
    DO j=1,ny-1; DO i=1,nx; DO k=1,nz; DO m=1,nz
      IF (.NOT.(state%above_ground(i,j,k) .AND. state%above_ground(i,j+1,m))) CYCLE
      dp=MAX(0.0_real64,MIN(state%grid%pressure_interface(i,j,k), &
        state%grid%pressure_interface(i,j+1,m))-MAX(state%grid%pressure_interface(i,j,k+1), &
        state%grid%pressure_interface(i,j+1,m+1)))
      area=0.5_real64*(state%grid%dx(i,j)+state%grid%dx(i,j+1))*dp/gravity
      wl=state%grid%dy(i,j+1)/(state%grid%dy(i,j)+state%grid%dy(i,j+1)); wr=1.0_real64-wl
      flux=area*(wl*v(i,j,k)+wr*v(i,j+1,m))
      IF (active(i,j,k)) residual(i,j,k)=residual(i,j,k)+flux/state%grid%pressure_mass_measure(i,j,k)
      IF (active(i,j+1,m)) residual(i,j+1,m)=residual(i,j+1,m)-flux/state%grid%pressure_mass_measure(i,j+1,m)
    END DO; END DO; END DO; END DO
  END SUBROUTINE dense_horizontal_residual

  SUBROUTINE check_components(op,state,view)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_snapshot), INTENT(IN) :: view
    REAL(real64) :: matrix(nt,nt),lambda(nx,ny,nz),du(nx,ny,nz),dv(nx,ny,nz),dw(nx,ny,nz)
    REAL(real64) :: residual(nx,ny,nz),basis(nt),tol
    LOGICAL :: active(nt),visited(nt)
    INTEGER :: column,node,neighbor,queue(nt),first,last,ncomponent,status

    active=RESHAPE(view%cell_active,[nt]); matrix=0.0_real64
    DO column=1,nt
      IF (.NOT.active(column)) CYCLE
      basis=0.0_real64; basis(column)=1.0_real64; lambda=RESHAPE(basis,[nx,ny,nz])
      CALL apply_balance_correction(op,lambda,du,dv,dw,status)
      CALL require(status==STATUS_OK,'component reference correction')
      CALL dense_horizontal_residual(state,view%cell_active,du,dv,residual)
      matrix(:,column)=-RESHAPE(residual,[nt])
    END DO
    tol=1.0e-12_real64*MAXVAL(ABS(matrix))
    visited=.FALSE.; ncomponent=0
    DO node=1,nt
      IF (.NOT.active(node) .OR. visited(node)) CYCLE
      ncomponent=ncomponent+1; first=1; last=1; queue(1)=node; visited(node)=.TRUE.
      DO WHILE(first<=last)
        DO neighbor=1,nt
          IF (.NOT.active(neighbor) .OR. visited(neighbor)) CYCLE
          IF (MAX(ABS(matrix(neighbor,queue(first))),ABS(matrix(queue(first),neighbor)))<=tol) CYCLE
          last=last+1; queue(last)=neighbor; visited(neighbor)=.TRUE.
        END DO
        first=first+1
      END DO
    END DO
    CALL require(ncomponent==view%ncomponent,'components versus independent dense normal matrix')
  END SUBROUTINE check_components
END PROGRAM test_balance_partial_faces
