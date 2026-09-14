! Pointwise pressure-coordinate to native vertical-velocity relation.
!
! The caller supplies fields collocated on the native eta grid.  This kernel
! only evaluates the declared relation; it does not remap, extrapolate, fill
! boundaries, estimate tendencies, or apply a density shortcut.
! Pressure/omega quantities are SI (Pa and Pa s^-1), z is metres, and all
! derivatives are supplied by the caller at the same eta-grid locations.
MODULE cloud_bal_native_velocity
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_OK = 0
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_BAD_SHAPE = 1
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_NONFINITE = 2
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_BAD_PRESSURE = 3
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_BAD_METRIC = 4
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_BAD_RESULT = 5
  INTEGER, PARAMETER, PUBLIC :: NATIVE_VELOCITY_ALLOCATION = 6

  PUBLIC :: map_pressure_omega_to_native_w, map_surface_w_increment

CONTAINS

  PURE SUBROUTINE map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x, &
      pressure_y,pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    REAL(real64), INTENT(IN) :: pressure(:,:,:),pressure_t(:,:,:), &
      pressure_x(:,:,:),pressure_y(:,:,:),pressure_eta(:,:,:)
    REAL(real64), INTENT(IN) :: z(:,:,:),z_t(:,:,:),z_x(:,:,:),z_y(:,:,:), &
      z_eta(:,:,:),u(:,:,:),v(:,:,:),omega(:,:,:)
    REAL(real64), INTENT(INOUT) :: native_w(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: work(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k,allocation_status
    INTEGER :: pressure_eta_sign,z_eta_sign,pressure_step_sign,z_step_sign
    LOGICAL :: pressure_orientation,z_orientation
    REAL(real64) :: material_pressure_rate

    status=NATIVE_VELOCITY_BAD_SHAPE
    nx=SIZE(pressure,1)
    ny=SIZE(pressure,2)
    nz=SIZE(pressure,3)
    IF (nx<1 .OR. ny<1 .OR. nz<1) RETURN
    IF (ANY(SHAPE(native_w)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(pressure_t)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(pressure_x)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(pressure_y)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(pressure_eta)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(z)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(z_t)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(z_x)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(z_y)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(z_eta)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(u)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(v)/=SHAPE(pressure)) .OR. &
        ANY(SHAPE(omega)/=SHAPE(pressure))) RETURN

    status=NATIVE_VELOCITY_NONFINITE
    IF (ANY(.NOT.ieee_is_finite(pressure)) .OR. &
        ANY(.NOT.ieee_is_finite(pressure_t)) .OR. &
        ANY(.NOT.ieee_is_finite(pressure_x)) .OR. &
        ANY(.NOT.ieee_is_finite(pressure_y)) .OR. &
        ANY(.NOT.ieee_is_finite(pressure_eta)) .OR. &
        ANY(.NOT.ieee_is_finite(z)) .OR. &
        ANY(.NOT.ieee_is_finite(z_t)) .OR. &
        ANY(.NOT.ieee_is_finite(z_x)) .OR. &
        ANY(.NOT.ieee_is_finite(z_y)) .OR. &
        ANY(.NOT.ieee_is_finite(z_eta)) .OR. &
        ANY(.NOT.ieee_is_finite(u)) .OR. &
        ANY(.NOT.ieee_is_finite(v)) .OR. &
        ANY(.NOT.ieee_is_finite(omega))) RETURN

    status=NATIVE_VELOCITY_BAD_PRESSURE
    IF (ANY(pressure<=0.0_real64)) RETURN

    ! Both coordinate surfaces must be monotone in stored k order.  Their eta
    ! derivatives must retain one sign and agree on whether eta increases or
    ! decreases with k; no native level-order orientation is assumed.
    status=NATIVE_VELOCITY_BAD_METRIC
    DO j=1,ny
      DO i=1,nx
        pressure_eta_sign=sign_of(pressure_eta(i,j,1))
        z_eta_sign=sign_of(z_eta(i,j,1))
        IF (pressure_eta_sign==1) THEN
          IF (ANY(pressure_eta(i,j,:)<=0.0_real64)) RETURN
        ELSE
          IF (ANY(pressure_eta(i,j,:)>=0.0_real64)) RETURN
        END IF
        IF (z_eta_sign==1) THEN
          IF (ANY(z_eta(i,j,:)<=0.0_real64)) RETURN
        ELSE
          IF (ANY(z_eta(i,j,:)>=0.0_real64)) RETURN
        END IF
        IF (nz==1) CYCLE

        pressure_step_sign=MERGE(1,-1,pressure(i,j,2)>pressure(i,j,1))
        z_step_sign=MERGE(1,-1,z(i,j,2)>z(i,j,1))
        IF (pressure_step_sign==1) THEN
          IF (ANY(pressure(i,j,2:nz)<=pressure(i,j,1:nz-1))) RETURN
        ELSE
          IF (ANY(pressure(i,j,2:nz)>=pressure(i,j,1:nz-1))) RETURN
        END IF
        IF (z_step_sign==1) THEN
          IF (ANY(z(i,j,2:nz)<=z(i,j,1:nz-1))) RETURN
        ELSE
          IF (ANY(z(i,j,2:nz)>=z(i,j,1:nz-1))) RETURN
        END IF
        pressure_orientation=pressure_step_sign==pressure_eta_sign
        z_orientation=z_step_sign==z_eta_sign
        IF (pressure_orientation .NEQV. z_orientation) RETURN
      END DO
    END DO

    ALLOCATE(work(nx,ny,nz),STAT=allocation_status)
    IF (allocation_status/=0) THEN
      status=NATIVE_VELOCITY_ALLOCATION
      RETURN
    END IF

    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          material_pressure_rate=omega(i,j,k)-pressure_t(i,j,k)- &
            u(i,j,k)*pressure_x(i,j,k)-v(i,j,k)*pressure_y(i,j,k)
          work(i,j,k)=z_t(i,j,k)+u(i,j,k)*z_x(i,j,k)+ &
            v(i,j,k)*z_y(i,j,k)+material_pressure_rate* &
            (z_eta(i,j,k)/pressure_eta(i,j,k))
        END DO
      END DO
    END DO

    IF (ANY(.NOT.ieee_is_finite(work))) THEN
      DEALLOCATE(work)
      status=NATIVE_VELOCITY_BAD_RESULT
      RETURN
    END IF

    ! Publish only after every input and computed value has passed validation.
    native_w=work
    DEALLOCATE(work)
    status=NATIVE_VELOCITY_OK
  END SUBROUTINE map_pressure_omega_to_native_w

  ! Discrete lower-boundary operator used by WRF set_w_surface.  The caller
  ! supplies CF1/CF2/CF3-weighted staggered wind increments, so this routine
  ! only applies the nonperiodic, clamped HGT stencil on the native grid.
  ! It follows dyn_em/module_bc_em.F:set_w_surface (pinned lines 1244-1281):
  ! mapfac_x/y are msftx/y and dx/dy are the inverse rdx/rdy factors.
  PURE SUBROUTINE map_surface_w_increment(height,mapfac_x,mapfac_y,dx,dy, &
      delta_u_surface,delta_v_surface,surface_w,status)
    REAL(real64), INTENT(IN) :: height(:,:),mapfac_x(:,:),mapfac_y(:,:)
    REAL(real64), INTENT(IN) :: dx,dy,delta_u_surface(:,:),delta_v_surface(:,:)
    REAL(real64), INTENT(INOUT) :: surface_w(:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: work(:,:)
    INTEGER :: nx,ny,i,j,im,ip,jm,jp,allocation_status

    status=NATIVE_VELOCITY_BAD_SHAPE
    nx=SIZE(height,1)
    ny=SIZE(height,2)
    IF (nx<1 .OR. ny<1) RETURN
    IF (ANY(SHAPE(mapfac_x)/=SHAPE(height)) .OR. &
        ANY(SHAPE(mapfac_y)/=SHAPE(height)) .OR. &
        ANY(SHAPE(surface_w)/=SHAPE(height)) .OR. &
        SIZE(delta_u_surface,1)/=nx+1 .OR. SIZE(delta_u_surface,2)/=ny .OR. &
        SIZE(delta_v_surface,1)/=nx .OR. SIZE(delta_v_surface,2)/=ny+1) RETURN

    status=NATIVE_VELOCITY_NONFINITE
    IF (.NOT.ieee_is_finite(dx) .OR. .NOT.ieee_is_finite(dy) .OR. &
        ANY(.NOT.ieee_is_finite(height)) .OR. ANY(.NOT.ieee_is_finite(mapfac_x)) .OR. &
        ANY(.NOT.ieee_is_finite(mapfac_y)) .OR. ANY(.NOT.ieee_is_finite(delta_u_surface)) .OR. &
        ANY(.NOT.ieee_is_finite(delta_v_surface))) RETURN
    status=NATIVE_VELOCITY_BAD_METRIC
    IF (dx<=0.0_real64 .OR. dy<=0.0_real64 .OR. &
        ANY(mapfac_x<=0.0_real64) .OR. ANY(mapfac_y<=0.0_real64)) RETURN

    ALLOCATE(work(nx,ny),STAT=allocation_status)
    IF (allocation_status/=0) THEN
      status=NATIVE_VELOCITY_ALLOCATION
      RETURN
    END IF
    DO j=1,ny
      jm=MAX(j-1,1)
      jp=MIN(j+1,ny)
      DO i=1,nx
        im=MAX(i-1,1)
        ip=MIN(i+1,nx)
        work(i,j)=mapfac_x(i,j)/(2.0_real64*dx)* &
          ((height(ip,j)-height(i,j))*delta_u_surface(i+1,j)+ &
           (height(i,j)-height(im,j))*delta_u_surface(i,j)) + &
          mapfac_y(i,j)/(2.0_real64*dy)* &
          ((height(i,jp)-height(i,j))*delta_v_surface(i,j+1)+ &
           (height(i,j)-height(i,jm))*delta_v_surface(i,j))
      END DO
    END DO
    IF (ANY(.NOT.ieee_is_finite(work))) THEN
      DEALLOCATE(work)
      status=NATIVE_VELOCITY_BAD_RESULT
      RETURN
    END IF
    surface_w=work
    DEALLOCATE(work)
    status=NATIVE_VELOCITY_OK
  END SUBROUTINE map_surface_w_increment

  PURE ELEMENTAL INTEGER FUNCTION sign_of(value)
    REAL(real64), INTENT(IN) :: value
    sign_of=MERGE(1,-1,value>0.0_real64)
  END FUNCTION sign_of

END MODULE cloud_bal_native_velocity
