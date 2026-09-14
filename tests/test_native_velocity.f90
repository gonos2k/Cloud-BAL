PROGRAM test_native_velocity
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_native_velocity, ONLY: map_pressure_omega_to_native_w, &
    map_surface_w_increment,NATIVE_VELOCITY_OK
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=2,NY=2,NZ=3
  INTEGER :: failures

  failures=0
  CALL test_moving_surfaces(failures)
  CALL test_descending_eta_orientation(failures)
  CALL test_uniform_static_state(failures)
  CALL test_invalid_jacobian_rolls_back(failures)
  CALL test_invalid_pressure_and_nonmonotone_height(failures)
  CALL test_nonfinite_and_shape_rejection(failures)
  CALL test_surface_boundary_operator(failures)
  IF (failures/=0) THEN
    PRINT '(A,I0)','Native velocity tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Native velocity tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_moving_surfaces(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ)
    INTEGER :: i,j,k,status

    DO k=1,NZ
      DO j=1,NY
        DO i=1,NX
          pressure(i,j,k)=100000.0_real64-10000.0_real64*REAL(k-1,real64)+ &
            2.0_real64*REAL(i-1,real64)+3.0_real64*REAL(j-1,real64)
          pressure_t(i,j,k)=4.0_real64
          pressure_x(i,j,k)=2.0_real64
          pressure_y(i,j,k)=3.0_real64
          pressure_eta(i,j,k)=-10000.0_real64
          z(i,j,k)=100.0_real64+50.0_real64*REAL(k-1,real64)+ &
            4.0_real64*REAL(i-1,real64)+5.0_real64*REAL(j-1,real64)
          z_t(i,j,k)=0.5_real64
          z_x(i,j,k)=4.0_real64
          z_y(i,j,k)=5.0_real64
          z_eta(i,j,k)=50.0_real64
          u(i,j,k)=10.0_real64
          v(i,j,k)=-2.0_real64
          omega(i,j,k)=118.0_real64
        END DO
      END DO
    END DO
    native_w=-999.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status==NATIVE_VELOCITY_OK,'moving surfaces accepted',failures)
    CALL check(ALL(ABS(native_w-30.0_real64)<1.0E-12_real64), &
      'moving pressure/geopotential surfaces produce analytic W',failures)
  END SUBROUTINE test_moving_surfaces

  SUBROUTINE test_descending_eta_orientation(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ)
    INTEGER :: i,j,k,status

    DO k=1,NZ
      DO j=1,NY
        DO i=1,NX
          pressure(i,j,k)=100000.0_real64-10000.0_real64*REAL(k-1,real64)+ &
            2.0_real64*REAL(i-1,real64)+3.0_real64*REAL(j-1,real64)
          pressure_t(i,j,k)=4.0_real64
          pressure_x(i,j,k)=2.0_real64
          pressure_y(i,j,k)=3.0_real64
          pressure_eta(i,j,k)=10000.0_real64
          z(i,j,k)=100.0_real64+50.0_real64*REAL(k-1,real64)+ &
            4.0_real64*REAL(i-1,real64)+5.0_real64*REAL(j-1,real64)
          z_t(i,j,k)=0.5_real64
          z_x(i,j,k)=4.0_real64
          z_y(i,j,k)=5.0_real64
          z_eta(i,j,k)=-50.0_real64
          u(i,j,k)=10.0_real64
          v(i,j,k)=-2.0_real64
          omega(i,j,k)=118.0_real64
        END DO
      END DO
    END DO
    native_w=-998.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status==NATIVE_VELOCITY_OK,'descending eta orientation accepted',failures)
    CALL check(ALL(ABS(native_w-30.0_real64)<1.0E-12_real64), &
      'descending eta orientation preserves analytic W',failures)
  END SUBROUTINE test_descending_eta_orientation

  SUBROUTINE test_uniform_static_state(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ)
    INTEGER :: k,status

    pressure_t=0.0_real64; pressure_x=0.0_real64; pressure_y=0.0_real64
    z_t=0.0_real64; z_x=0.0_real64; z_y=0.0_real64
    u=17.0_real64; v=-8.0_real64; omega=0.0_real64
    DO k=1,NZ
      pressure(:,:,k)=100000.0_real64-10000.0_real64*REAL(k-1,real64)
      pressure_eta(:,:,k)=-10000.0_real64
      z(:,:,k)=20.0_real64+1000.0_real64*REAL(k-1,real64)
      z_eta(:,:,k)=1000.0_real64
    END DO
    native_w=123.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status==NATIVE_VELOCITY_OK,'uniform static state accepted',failures)
    CALL check(ALL(native_w==0.0_real64),'uniform static state remains zero',failures)
  END SUBROUTINE test_uniform_static_state

  SUBROUTINE test_invalid_jacobian_rolls_back(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ),before(NX,NY,NZ)
    INTEGER :: status

    CALL initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    native_w=42.0_real64
    before=native_w
    pressure_eta(1,1,2)=0.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'zero pressure Jacobian rejected',failures)
    CALL check(ALL(native_w==before),'zero Jacobian leaves output untouched',failures)
  END SUBROUTINE test_invalid_jacobian_rolls_back

  SUBROUTINE test_invalid_pressure_and_nonmonotone_height(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ),before(NX,NY,NZ)
    INTEGER :: status

    CALL initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    native_w=43.0_real64
    before=native_w
    pressure(2,2,2)=-1.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'nonpositive pressure rejected',failures)
    CALL check(ALL(native_w==before),'bad pressure leaves output untouched',failures)

    CALL initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    native_w=44.0_real64
    before=native_w
    z(1,2,2)=z(1,2,1)-1.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'nonmonotone height rejected',failures)
    CALL check(ALL(native_w==before),'bad height leaves output untouched',failures)
  END SUBROUTINE test_invalid_pressure_and_nonmonotone_height

  SUBROUTINE test_nonfinite_and_shape_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(NX,NY,NZ),pressure_t(NX,NY,NZ), &
      pressure_x(NX,NY,NZ),pressure_y(NX,NY,NZ),pressure_eta(NX,NY,NZ)
    REAL(real64) :: z(NX,NY,NZ),z_t(NX,NY,NZ),z_x(NX,NY,NZ),z_y(NX,NY,NZ), &
      z_eta(NX,NY,NZ),u(NX,NY,NZ),v(NX,NY,NZ),omega(NX,NY,NZ), &
      native_w(NX,NY,NZ),before(NX,NY,NZ),short_w(NX,NY,NZ-1)
    INTEGER :: status

    CALL initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    native_w=45.0_real64
    before=native_w
    pressure(1,1,1)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,native_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'nonfinite input rejected',failures)
    CALL check(ALL(native_w==before),'nonfinite input leaves output untouched',failures)

    CALL initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    short_w=46.0_real64
    CALL map_pressure_omega_to_native_w(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega,short_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'shape mismatch rejected',failures)
    CALL check(ALL(short_w==46.0_real64),'shape mismatch leaves output untouched',failures)
  END SUBROUTINE test_nonfinite_and_shape_rejection

  SUBROUTINE test_surface_boundary_operator(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: height(NX,NY),mapx(NX,NY),mapy(NX,NY)
    REAL(real64) :: delta_u(NX+1,NY),delta_v(NX,NY+1),surface_w(NX,NY),before(NX,NY)
    REAL(real64) :: expected(NX,NY)
    INTEGER :: i,j,im,ip,jm,jp,status

    DO j=1,NY; DO i=1,NX
      height(i,j)=3.0_real64+7.0_real64*REAL(i,real64)+11.0_real64*REAL(j,real64)
      mapx(i,j)=1.0_real64+0.05_real64*REAL(i,real64)
      mapy(i,j)=0.9_real64+0.04_real64*REAL(j,real64)
    END DO; END DO
    DO j=1,NY; DO i=1,NX+1
      delta_u(i,j)=0.7_real64*REAL(i,real64)-0.2_real64*REAL(j,real64)
    END DO; END DO
    DO j=1,NY+1; DO i=1,NX
      delta_v(i,j)=-0.4_real64*REAL(i,real64)+0.9_real64*REAL(j,real64)
    END DO; END DO
    expected=0.0_real64
    DO j=1,NY
      jm=MAX(j-1,1); jp=MIN(j+1,NY)
      DO i=1,NX
        im=MAX(i-1,1); ip=MIN(i+1,NX)
        expected(i,j)=mapx(i,j)/(2.0_real64*10.0_real64)* &
          ((height(ip,j)-height(i,j))*delta_u(i+1,j)+ &
           (height(i,j)-height(im,j))*delta_u(i,j)) + &
          mapy(i,j)/(2.0_real64*20.0_real64)* &
          ((height(i,jp)-height(i,j))*delta_v(i,j+1)+ &
           (height(i,j)-height(i,jm))*delta_v(i,j))
      END DO
    END DO
    surface_w=-17.0_real64
    CALL map_surface_w_increment(height,mapx,mapy,10.0_real64,20.0_real64, &
      delta_u,delta_v,surface_w,status)
    CALL check(status==NATIVE_VELOCITY_OK,'surface boundary operator accepted',failures)
    CALL check(ALL(ABS(surface_w-expected)<1.0E-12_real64), &
      'surface boundary operator matches independent clamped stencil',failures)

    before=surface_w
    mapx(1,1)=0.0_real64
    CALL map_surface_w_increment(height,mapx,mapy,10.0_real64,20.0_real64, &
      delta_u,delta_v,surface_w,status)
    CALL check(status/=NATIVE_VELOCITY_OK,'invalid surface metric rejected',failures)
    CALL check(ALL(surface_w==before),'invalid surface metric leaves output untouched',failures)
  END SUBROUTINE test_surface_boundary_operator

  SUBROUTINE initialize_linear_case(pressure,pressure_t,pressure_x,pressure_y, &
      pressure_eta,z,z_t,z_x,z_y,z_eta,u,v,omega)
    REAL(real64), INTENT(OUT) :: pressure(:,:,:),pressure_t(:,:,:), &
      pressure_x(:,:,:),pressure_y(:,:,:),pressure_eta(:,:,:)
    REAL(real64), INTENT(OUT) :: z(:,:,:),z_t(:,:,:),z_x(:,:,:),z_y(:,:,:), &
      z_eta(:,:,:),u(:,:,:),v(:,:,:),omega(:,:,:)
    INTEGER :: i,j,k

    DO k=1,SIZE(pressure,3)
      DO j=1,SIZE(pressure,2)
        DO i=1,SIZE(pressure,1)
          pressure(i,j,k)=100000.0_real64-10000.0_real64*REAL(k-1,real64)
          pressure_t(i,j,k)=0.0_real64; pressure_x(i,j,k)=0.0_real64
          pressure_y(i,j,k)=0.0_real64; pressure_eta(i,j,k)=-10000.0_real64
          z(i,j,k)=100.0_real64+50.0_real64*REAL(k-1,real64)
          z_t(i,j,k)=0.0_real64; z_x(i,j,k)=0.0_real64; z_y(i,j,k)=0.0_real64
          z_eta(i,j,k)=50.0_real64; u(i,j,k)=0.0_real64; v(i,j,k)=0.0_real64
          omega(i,j,k)=0.0_real64
        END DO
      END DO
    END DO
  END SUBROUTINE initialize_linear_case

END PROGRAM test_native_velocity
