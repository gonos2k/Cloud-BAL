! Deterministic radar/precipitation coupling for cloud-derived omega.
MODULE cloud_bal_radar_downdraft
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_moisture, ONLY: allocate_precipitation
  IMPLICIT NONE
  PRIVATE

  REAL, PARAMETER :: GRAVITY = 9.80665
  REAL, PARAMETER :: RD_AIR = 287.05
  REAL, PARAMETER :: CP_AIR = 1004.7
  REAL, PARAMETER :: LV = 2.50E6
  REAL, PARAMETER :: LS = 2.834E6
  REAL, PARAMETER :: LF = 3.34E5
  REAL, PARAMETER :: SCALE_HEIGHT_M = 8000.0

  TYPE, PUBLIC :: radar_downdraft_config
    ! Operational KLAPS volume reflectivity is S band (nominal wavelength 10 cm).
    REAL :: radar_wavelength_cm = 10.0
    REAL :: storm_motion_u_ms = 0.0
    REAL :: storm_motion_v_ms = 0.0
    LOGICAL :: storm_motion_available = .FALSE.
    ! The operational mosaic uses -10 dBZ as its no-echo base.  It is not an
    ! observed precipitation value; radar_mosaic.nl sets REF_BASE_USEABLE=0.
    REAL :: minimum_dbz = 0.0
    REAL :: full_confidence_dbz = 30.0
    REAL :: reference_concentration = 1.0E-4
    REAL :: minimum_fall_speed = 0.5
    REAL :: evaporation_efficiency = 0.12
    REAL :: sublimation_efficiency = 0.08
    REAL :: melting_efficiency = 0.15
    REAL :: downdraft_efficiency = 0.10
    REAL :: maximum_downdraft_ms = 5.0
    REAL :: maximum_innovation_ms = 3.0
    REAL :: entrainment_depth_m = 2000.0
    REAL :: surface_taper_depth_m = 500.0
    REAL :: under_relaxation = 0.40
    INTEGER :: maximum_iterations = 3
    REAL :: convergence_ms = 0.05
  END TYPE radar_downdraft_config

  PUBLIC :: couple_radar_precipitation
  PUBLIC :: linear_reflectivity
  PUBLIC :: phase_terminal_velocity

CONTAINS

  PURE REAL FUNCTION linear_reflectivity(dbz)
    REAL, INTENT(IN) :: dbz
    linear_reflectivity = 0.0
    IF (.NOT. ieee_is_finite(dbz)) RETURN
    IF (dbz < -100.0 .OR. dbz > 100.0) RETURN
    linear_reflectivity = 10.0**(0.1*dbz)
  END FUNCTION linear_reflectivity

  REAL FUNCTION phase_terminal_velocity(phase, pressure_pa, &
                                         temperature_k, dbz, status)
    INTEGER, INTENT(IN) :: phase
    REAL, INTENT(IN) :: pressure_pa, temperature_k, dbz
    INTEGER, INTENT(OUT) :: status
    REAL :: density_ratio, z_linear, base_speed

    status = 0
    phase_terminal_velocity = 0.0
    IF (.NOT. ieee_is_finite(pressure_pa)) RETURN
    IF (pressure_pa <= 0.0) RETURN
    IF (.NOT. ieee_is_finite(temperature_k)) RETURN
    IF (temperature_k <= 0.0) RETURN
    z_linear = linear_reflectivity(dbz)
    IF (z_linear <= 0.0) RETURN

    SELECT CASE (phase)
    CASE (1,3,4)                 ! rain, freezing rain, sleet
      base_speed = 4.32*z_linear**0.0714286
    CASE (2)                     ! snow
      base_speed = MIN(2.5, 0.80 + 0.12*z_linear**0.10)
    CASE (5)                     ! hail / precipitating ice
      base_speed = MIN(15.0, 7.0 + 0.30*z_linear**0.08)
    CASE DEFAULT
      RETURN
    END SELECT
    density_ratio = (pressure_pa/101300.0)*(273.15/temperature_k)
    phase_terminal_velocity = base_speed/SQRT(MAX(density_ratio,1.0E-4))
    phase_terminal_velocity = MIN(20.0,MAX(0.1,phase_terminal_velocity))
    IF (.NOT. ieee_is_finite(phase_terminal_velocity)) THEN
      phase_terminal_velocity = 0.0
      RETURN
    END IF
    status = 1
  END FUNCTION phase_terminal_velocity

  SUBROUTINE couple_radar_precipitation(dbz, temperature_k, rh_percent, &
       height_m, pressure_pa, u_ms, v_ms, dx_m, dy_m, missing, &
       cloud_precip_type, wind_available, rain, snow, graupel, omega, &
       source_valid, status, config)
    REAL, INTENT(IN) :: dbz(:,:,:), temperature_k(:,:,:), rh_percent(:,:,:)
    REAL, INTENT(IN) :: height_m(:,:,:), pressure_pa(:,:,:)
    REAL, INTENT(IN) :: u_ms(:,:,:), v_ms(:,:,:), dx_m, dy_m, missing
    INTEGER, INTENT(IN) :: cloud_precip_type(:,:,:)
    LOGICAL, INTENT(IN) :: wind_available
    REAL, INTENT(INOUT) :: rain(:,:,:), snow(:,:,:), graupel(:,:,:)
    REAL, INTENT(INOUT) :: omega(:,:,:)
    LOGICAL, INTENT(OUT) :: source_valid(:,:,:)
    INTEGER, INTENT(OUT) :: status
    TYPE(radar_downdraft_config), INTENT(IN), OPTIONAL :: config

    TYPE(radar_downdraft_config) :: cfg
    INTEGER :: nx, ny, nz, iteration, valid_change_count
    REAL, ALLOCATABLE :: rain_work(:,:,:), snow_work(:,:,:)
    REAL, ALLOCATABLE :: graupel_work(:,:,:), omega_work(:,:,:)
    REAL, ALLOCATABLE :: omega_next(:,:,:), z_proxy(:,:,:)
    LOGICAL, ALLOCATABLE :: observed(:,:,:)
    REAL :: maximum_change
    LOGICAL :: converged, used_omega_fallback

    status = 0
    source_valid = .FALSE.
    IF (PRESENT(config)) cfg = config
    nx = SIZE(dbz,1); ny = SIZE(dbz,2); nz = SIZE(dbz,3)
    IF (.NOT. same_shape_3d(dbz,temperature_k) .OR. &
        .NOT. same_shape_3d(dbz,rh_percent) .OR. &
        .NOT. same_shape_3d(dbz,height_m) .OR. &
        .NOT. same_shape_3d(dbz,pressure_pa) .OR. &
        .NOT. same_shape_3d(dbz,u_ms) .OR. &
        .NOT. same_shape_3d(dbz,v_ms) .OR. &
        .NOT. same_shape_3d(dbz,rain) .OR. &
        .NOT. same_shape_3d(dbz,snow) .OR. &
        .NOT. same_shape_3d(dbz,graupel) .OR. &
        .NOT. same_shape_3d(dbz,omega) .OR. &
        SIZE(cloud_precip_type,1) /= nx .OR. &
        SIZE(cloud_precip_type,2) /= ny .OR. &
        SIZE(cloud_precip_type,3) /= nz .OR. &
        SIZE(source_valid,1) /= nx .OR. SIZE(source_valid,2) /= ny .OR. &
        SIZE(source_valid,3) /= nz .OR. nx < 2 .OR. ny < 2 .OR. nz < 2) RETURN
    IF (.NOT. config_is_valid(cfg)) RETURN
    IF (.NOT. ieee_is_finite(missing)) RETURN
    IF (.NOT. ieee_is_finite(dx_m)) RETURN
    IF (.NOT. ieee_is_finite(dy_m)) RETURN
    IF (dx_m <= 0.0 .OR. dy_m <= 0.0) RETURN
    IF (.NOT. meteorology_is_valid(temperature_k,rh_percent,height_m, &
                                   pressure_pa,rain,snow,graupel,omega, &
                                   missing)) RETURN
    IF (ANY(cloud_precip_type < 0) .OR. &
        ANY(cloud_precip_type/16 > 5)) RETURN
    IF (wind_available) THEN
      IF (ANY(.NOT. ieee_is_finite(u_ms)) .OR. &
          ANY(.NOT. ieee_is_finite(v_ms))) RETURN
    END IF

    ALLOCATE(rain_work(nx,ny,nz),snow_work(nx,ny,nz), &
             graupel_work(nx,ny,nz),omega_work(nx,ny,nz), &
             omega_next(nx,ny,nz),z_proxy(nx,ny,nz), &
             observed(nx,ny,nz))
    CALL build_observed_mask(dbz,rain,snow,graupel,missing,cfg,observed)
    IF (.NOT. ANY(observed)) THEN
      status = 2
      DEALLOCATE(rain_work,snow_work,graupel_work,omega_work,omega_next, &
                 z_proxy,observed)
      RETURN
    END IF

    omega_work = omega
    converged = .FALSE.
    used_omega_fallback = .FALSE.
    DO iteration = 1, cfg%maximum_iterations
      rain_work = rain
      snow_work = snow
      graupel_work = graupel
      z_proxy = dbz
      CALL fill_lower_gaps(rain_work,snow_work,graupel_work,z_proxy, &
           observed,cloud_precip_type,temperature_k,rh_percent,height_m, &
           pressure_pa,u_ms,v_ms,omega_work,dx_m,dy_m,wind_available,cfg, &
           used_omega_fallback)
      CALL diagnose_bounded_downdraft(rain_work,snow_work,graupel_work, &
           z_proxy,observed,cloud_precip_type,temperature_k,rh_percent, &
           height_m,pressure_pa,omega,cfg,omega_next)
      CALL maximum_valid_w_change(omega_next,omega_work,pressure_pa,missing, &
                                  maximum_change,valid_change_count)
      WHERE (valid_omega(omega_next,missing) .AND. &
             valid_omega(omega_work,missing))
        omega_next = (1.0-cfg%under_relaxation)*omega_work + &
                     cfg%under_relaxation*omega_next
      END WHERE
      omega_work = omega_next
      IF (valid_change_count > 0 .AND. maximum_change <= cfg%convergence_ms) THEN
        converged = .TRUE.
        EXIT
      END IF
    END DO

    IF (ANY(.NOT. ieee_is_finite(rain_work)) .OR. MINVAL(rain_work) < 0.0 .OR. &
        ANY(.NOT. ieee_is_finite(snow_work)) .OR. MINVAL(snow_work) < 0.0 .OR. &
        ANY(.NOT. ieee_is_finite(graupel_work)) .OR. &
        MINVAL(graupel_work) < 0.0) THEN
      DEALLOCATE(rain_work,snow_work,graupel_work,omega_work,omega_next, &
                 z_proxy,observed)
      RETURN
    END IF

    rain = rain_work
    snow = snow_work
    graupel = graupel_work
    omega = omega_work
    source_valid = observed .OR. (rain+snow+graupel > 0.0) .OR. &
                   valid_omega(omega,missing)
    status = MERGE(1,2,converged .AND. wind_available .AND. &
                         cfg%storm_motion_available .AND. &
                         .NOT. used_omega_fallback)
    DEALLOCATE(rain_work,snow_work,graupel_work,omega_work,omega_next, &
               z_proxy,observed)
  END SUBROUTINE couple_radar_precipitation

  SUBROUTINE fill_lower_gaps(rain,snow,graupel,z_proxy,observed, &
       cloud_precip_type,temperature_k,rh_percent,height_m,pressure_pa, &
       u_ms,v_ms,omega,dx_m,dy_m,wind_available,cfg,used_omega_fallback)
    REAL, INTENT(INOUT) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:),z_proxy(:,:,:)
    LOGICAL, INTENT(IN) :: observed(:,:,:),wind_available
    INTEGER, INTENT(IN) :: cloud_precip_type(:,:,:)
    REAL, INTENT(IN) :: temperature_k(:,:,:),rh_percent(:,:,:),height_m(:,:,:)
    REAL, INTENT(IN) :: pressure_pa(:,:,:),u_ms(:,:,:),v_ms(:,:,:),omega(:,:,:)
    REAL, INTENT(IN) :: dx_m,dy_m
    TYPE(radar_downdraft_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(INOUT) :: used_omega_fallback
    INTEGER :: k

    IF (.NOT. wind_available) RETURN
    DO k=SIZE(rain,3),2,-1
      CALL transport_one_level(rain,z_proxy,observed,1,k,temperature_k, &
           rh_percent,height_m,pressure_pa,u_ms,v_ms,omega,dx_m,dy_m,cfg, &
           used_omega_fallback)
      CALL transport_one_level(snow,z_proxy,observed,2,k,temperature_k, &
           rh_percent,height_m,pressure_pa,u_ms,v_ms,omega,dx_m,dy_m,cfg, &
           used_omega_fallback)
      CALL transport_one_level(graupel,z_proxy,observed,5,k,temperature_k, &
           rh_percent,height_m,pressure_pa,u_ms,v_ms,omega,dx_m,dy_m,cfg, &
           used_omega_fallback)
      CALL repartition_unobserved_level(rain,snow,graupel,observed, &
           cloud_precip_type,temperature_k,k-1)
    END DO
  END SUBROUTINE fill_lower_gaps

  SUBROUTINE repartition_unobserved_level(rain,snow,graupel,observed, &
                                           cloud_precip_type,temperature_k,k)
    REAL, INTENT(INOUT) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    LOGICAL, INTENT(IN) :: observed(:,:,:)
    INTEGER, INTENT(IN) :: cloud_precip_type(:,:,:),k
    REAL, INTENT(IN) :: temperature_k(:,:,:)
    INTEGER :: i,j,phase,allocation_status
    REAL :: total,new_rain,new_snow,new_graupel

    DO j=1,SIZE(rain,2)
      DO i=1,SIZE(rain,1)
        IF (observed(i,j,k)) CYCLE
        total=rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)
        IF (total<=0.0) CYCLE
        phase=cloud_precip_type(i,j,k)/16
        IF (phase<0 .OR. phase>5) phase=0
        CALL allocate_precipitation(total,temperature_k(i,j,k),phase, &
             new_rain,new_snow,new_graupel,allocation_status)
        IF (allocation_status==1) THEN
          rain(i,j,k)=new_rain
          snow(i,j,k)=new_snow
          graupel(i,j,k)=new_graupel
        END IF
      END DO
    END DO
  END SUBROUTINE repartition_unobserved_level

  SUBROUTINE transport_one_level(q,z_proxy,observed,phase,k,temperature_k, &
       rh_percent,height_m,pressure_pa,u_ms,v_ms,omega,dx_m,dy_m,cfg, &
       used_omega_fallback)
    REAL, INTENT(INOUT) :: q(:,:,:),z_proxy(:,:,:)
    LOGICAL, INTENT(IN) :: observed(:,:,:)
    INTEGER, INTENT(IN) :: phase,k
    REAL, INTENT(IN) :: temperature_k(:,:,:),rh_percent(:,:,:),height_m(:,:,:)
    REAL, INTENT(IN) :: pressure_pa(:,:,:),u_ms(:,:,:),v_ms(:,:,:),omega(:,:,:)
    REAL, INTENT(IN) :: dx_m,dy_m
    TYPE(radar_downdraft_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(INOUT) :: used_omega_fallback
    INTEGER :: nx,ny,i,j,ii,jj,di,dj,vt_status
    REAL :: dz,fall_speed,w_air,dt,x_target,y_target,fx,fy,weight
    REAL :: survival,deficit,deposit,source_dbz,target_speed

    nx=SIZE(q,1); ny=SIZE(q,2)
    DO j=1,ny
      DO i=1,nx
        IF (q(i,j,k) <= 0.0) CYCLE
        dz=height_m(i,j,k)-height_m(i,j,k-1)
        IF (dz <= 0.0) CYCLE
        source_dbz=z_proxy(i,j,k)
        IF (.NOT. ieee_is_finite(source_dbz)) THEN
          source_dbz=cfg%minimum_dbz
        ELSE IF (source_dbz < -100.0) THEN
          source_dbz=cfg%minimum_dbz
        END IF
        fall_speed=phase_terminal_velocity(phase,pressure_pa(i,j,k), &
                                           temperature_k(i,j,k),source_dbz, &
                                           vt_status)
        IF (vt_status /= 1) CYCLE
        IF (valid_scalar_omega(omega(i,j,k))) THEN
          w_air=-SCALE_HEIGHT_M*omega(i,j,k)/pressure_pa(i,j,k)
        ELSE
          ! Missing omega never enters trajectory arithmetic.  Zero is the
          ! explicit background-unavailable fallback and degrades the result.
          w_air=0.0
          used_omega_fallback=.TRUE.
        END IF
        dt=dz/MAX(fall_speed-w_air,cfg%minimum_fall_speed)
        x_target=REAL(i)+(u_ms(i,j,k)-cfg%storm_motion_u_ms)*dt/dx_m
        y_target=REAL(j)+(v_ms(i,j,k)-cfg%storm_motion_v_ms)*dt/dy_m
        ii=FLOOR(x_target); jj=FLOOR(y_target)
        fx=x_target-REAL(ii); fy=y_target-REAL(jj)
        deficit=MAX(0.0,MIN(1.0,1.0-rh_percent(i,j,k-1)/100.0))
        survival=EXP(-phase_loss_rate(phase)*deficit*dt)
        target_speed=phase_terminal_velocity(phase,pressure_pa(i,j,k-1), &
             temperature_k(i,j,k-1),source_dbz,vt_status)
        IF (vt_status /= 1) CYCLE
        deposit=q(i,j,k)*fall_speed/MAX(target_speed,cfg%minimum_fall_speed)* &
                survival
        DO dj=0,1
          DO di=0,1
            IF (ii+di < 1 .OR. ii+di > nx .OR. &
                jj+dj < 1 .OR. jj+dj > ny) CYCLE
            IF (observed(ii+di,jj+dj,k-1)) CYCLE
            weight=MERGE(1.0-fx,fx,di==0)*MERGE(1.0-fy,fy,dj==0)
            q(ii+di,jj+dj,k-1)=q(ii+di,jj+dj,k-1)+deposit*weight
            z_proxy(ii+di,jj+dj,k-1)=MAX(cfg%minimum_dbz,source_dbz)
          END DO
        END DO
      END DO
    END DO
  END SUBROUTINE transport_one_level

  SUBROUTINE diagnose_bounded_downdraft(rain,snow,graupel,z_proxy,observed, &
       cloud_precip_type,temperature_k,rh_percent,height_m,pressure_pa, &
       omega_original,cfg,omega_new)
    REAL, INTENT(IN) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:),z_proxy(:,:,:)
    LOGICAL, INTENT(IN) :: observed(:,:,:)
    INTEGER, INTENT(IN) :: cloud_precip_type(:,:,:)
    REAL, INTENT(IN) :: temperature_k(:,:,:),rh_percent(:,:,:),height_m(:,:,:)
    REAL, INTENT(IN) :: pressure_pa(:,:,:),omega_original(:,:,:)
    TYPE(radar_downdraft_config), INTENT(IN) :: cfg
    REAL, INTENT(OUT) :: omega_new(:,:,:)
    INTEGER :: i,j,k,nx,ny,nz,cloud_type
    REAL :: rho_air,ql,qi,deficit,melt_factor,bneg,bprev,energy,dz
    REAL :: w_cloud,w_target,w_new,confidence,cq,cz,surface_taper,decay

    nx=SIZE(rain,1); ny=SIZE(rain,2); nz=SIZE(rain,3)
    omega_new=omega_original
    DO j=1,ny
      DO i=1,nx
        energy=0.0
        bprev=0.0
        DO k=nz,1,-1
          rho_air=pressure_pa(i,j,k)/(RD_AIR*temperature_k(i,j,k))
          ql=rain(i,j,k)/rho_air
          qi=(snow(i,j,k)+graupel(i,j,k))/rho_air
          deficit=MAX(0.0,MIN(1.0,1.0-rh_percent(i,j,k)/100.0))
          melt_factor=EXP(-0.5*((temperature_k(i,j,k)-273.15)/2.0)**2)
          bneg=GRAVITY*(ql+qi+LV/(CP_AIR*temperature_k(i,j,k))* &
               cfg%evaporation_efficiency*deficit*ql+ &
               LS/(CP_AIR*temperature_k(i,j,k))* &
               cfg%sublimation_efficiency*deficit*qi+ &
               LF/(CP_AIR*temperature_k(i,j,k))* &
               cfg%melting_efficiency*melt_factor*qi)
          IF (k < nz) THEN
            dz=height_m(i,j,k+1)-height_m(i,j,k)
            decay=EXP(-dz/cfg%entrainment_depth_m)
            energy=energy*decay+0.5*(bprev+bneg)*dz
          END IF
          bprev=bneg
          IF (rain(i,j,k)+snow(i,j,k)+graupel(i,j,k) <= 0.0 .AND. &
              energy <= 0.0) CYCLE
          cq=(rain(i,j,k)+snow(i,j,k)+graupel(i,j,k))/ &
             (rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)+ &
              cfg%reference_concentration)
          IF (observed(i,j,k)) THEN
            cz=smoothstep((z_proxy(i,j,k)-cfg%minimum_dbz)/ &
                 MAX(cfg%full_confidence_dbz-cfg%minimum_dbz,1.0))
          ELSE
            cz=cq
          END IF
          confidence=SQRT(MAX(0.0,MIN(1.0,cz*cq)))
          surface_taper=MIN(1.0,MAX(0.0,(height_m(i,j,k)- &
               height_m(i,j,1))/cfg%surface_taper_depth_m))
          w_target=-surface_taper*MIN(cfg%maximum_downdraft_ms, &
               SQRT(MAX(0.0,2.0*cfg%downdraft_efficiency*energy)))
          IF (valid_scalar_omega(omega_original(i,j,k))) THEN
            w_cloud=-SCALE_HEIGHT_M*omega_original(i,j,k)/pressure_pa(i,j,k)
          ELSE
            w_cloud=0.0
          END IF
          cloud_type=MOD(cloud_precip_type(i,j,k),16)
          IF ((cloud_type == 3 .OR. cloud_type == 10 .OR. &
               cloud_type == 11) .AND. w_cloud > 0.0) &
            CYCLE
          w_new=w_cloud+confidence*MAX(-cfg%maximum_innovation_ms, &
                                      MIN(0.0,w_target-w_cloud))
          omega_new(i,j,k)=-pressure_pa(i,j,k)*w_new/SCALE_HEIGHT_M
        END DO
      END DO
    END DO
  END SUBROUTINE diagnose_bounded_downdraft

  SUBROUTINE build_observed_mask(dbz,rain,snow,graupel,missing,cfg,observed)
    REAL, INTENT(IN) :: dbz(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL, INTENT(IN) :: missing
    TYPE(radar_downdraft_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(OUT) :: observed(:,:,:)
    INTEGER :: i,j,k

    observed=.FALSE.
    DO k=1,SIZE(dbz,3)
      DO j=1,SIZE(dbz,2)
        DO i=1,SIZE(dbz,1)
          IF (.NOT. ieee_is_finite(dbz(i,j,k))) CYCLE
          IF (ABS(dbz(i,j,k)-missing) <= 1.0E-5) CYCLE
          IF (dbz(i,j,k) < cfg%minimum_dbz .OR. dbz(i,j,k) > 100.0) CYCLE
          IF (rain(i,j,k)+snow(i,j,k)+graupel(i,j,k) <= 0.0) CYCLE
          observed(i,j,k)=.TRUE.
        END DO
      END DO
    END DO
  END SUBROUTINE build_observed_mask

  SUBROUTINE maximum_valid_w_change(omega_new,omega_old,pressure,missing, &
                                    maximum_change,valid_count)
    REAL, INTENT(IN) :: omega_new(:,:,:),omega_old(:,:,:),pressure(:,:,:)
    REAL, INTENT(IN) :: missing
    REAL, INTENT(OUT) :: maximum_change
    INTEGER, INTENT(OUT) :: valid_count
    INTEGER :: i,j,k
    REAL :: old_w,new_w

    maximum_change=0.0
    valid_count=0
    DO k=1,SIZE(omega_new,3)
      DO j=1,SIZE(omega_new,2)
        DO i=1,SIZE(omega_new,1)
          IF (.NOT. valid_omega(omega_new(i,j,k),missing)) CYCLE
          IF (.NOT. ieee_is_finite(pressure(i,j,k))) CYCLE
          IF (pressure(i,j,k) <= 0.0) CYCLE
          new_w=omega_to_w(omega_new(i,j,k),pressure(i,j,k))
          old_w=0.0
          IF (valid_omega(omega_old(i,j,k),missing)) &
            old_w=omega_to_w(omega_old(i,j,k),pressure(i,j,k))
          maximum_change=MAX(maximum_change,ABS(new_w-old_w))
          valid_count=valid_count+1
        END DO
      END DO
    END DO
  END SUBROUTINE maximum_valid_w_change

  PURE ELEMENTAL REAL FUNCTION omega_to_w(omega,pressure)
    REAL, INTENT(IN) :: omega,pressure
    omega_to_w=0.0
    IF (.NOT. ieee_is_finite(omega)) RETURN
    IF (.NOT. ieee_is_finite(pressure)) RETURN
    IF (pressure <= 0.0) RETURN
    IF (ABS(omega) >= 1.0E30) RETURN
    omega_to_w=-SCALE_HEIGHT_M*omega/pressure
  END FUNCTION omega_to_w

  PURE ELEMENTAL LOGICAL FUNCTION valid_omega(omega,missing)
    REAL, INTENT(IN) :: omega,missing
    valid_omega=.FALSE.
    IF (.NOT. ieee_is_finite(omega)) RETURN
    IF (.NOT. ieee_is_finite(missing)) RETURN
    IF (ABS(omega-missing) <= 1.0E-5) RETURN
    IF (ABS(omega) > 100.0) RETURN
    valid_omega=.TRUE.
  END FUNCTION valid_omega

  PURE LOGICAL FUNCTION valid_scalar_omega(omega)
    REAL, INTENT(IN) :: omega
    valid_scalar_omega=.FALSE.
    IF (.NOT. ieee_is_finite(omega)) RETURN
    IF (ABS(omega) > 100.0) RETURN
    valid_scalar_omega=.TRUE.
  END FUNCTION valid_scalar_omega

  PURE REAL FUNCTION smoothstep(x)
    REAL, INTENT(IN) :: x
    REAL :: y
    y=MAX(0.0,MIN(1.0,x))
    smoothstep=y*y*(3.0-2.0*y)
  END FUNCTION smoothstep

  PURE REAL FUNCTION phase_loss_rate(phase)
    INTEGER, INTENT(IN) :: phase
    SELECT CASE(phase)
    CASE(1); phase_loss_rate=2.0E-4
    CASE(2); phase_loss_rate=1.0E-4
    CASE DEFAULT; phase_loss_rate=5.0E-5
    END SELECT
  END FUNCTION phase_loss_rate

  PURE LOGICAL FUNCTION same_shape_3d(a,b)
    REAL, INTENT(IN) :: a(:,:,:),b(:,:,:)
    same_shape_3d=ALL(SHAPE(a)==SHAPE(b))
  END FUNCTION same_shape_3d

  PURE LOGICAL FUNCTION config_is_valid(cfg)
    TYPE(radar_downdraft_config), INTENT(IN) :: cfg
    config_is_valid=.FALSE.
    IF (.NOT. ieee_is_finite(cfg%radar_wavelength_cm)) RETURN
    IF (cfg%radar_wavelength_cm < 8.0 .OR. &
        cfg%radar_wavelength_cm > 12.0) RETURN
    IF (.NOT. ieee_is_finite(cfg%storm_motion_u_ms)) RETURN
    IF (.NOT. ieee_is_finite(cfg%storm_motion_v_ms)) RETURN
    IF (.NOT. ieee_is_finite(cfg%minimum_dbz)) RETURN
    IF (.NOT. ieee_is_finite(cfg%full_confidence_dbz)) RETURN
    IF (.NOT. ieee_is_finite(cfg%reference_concentration)) RETURN
    IF (.NOT. ieee_is_finite(cfg%minimum_fall_speed)) RETURN
    IF (.NOT. ieee_is_finite(cfg%evaporation_efficiency)) RETURN
    IF (.NOT. ieee_is_finite(cfg%sublimation_efficiency)) RETURN
    IF (.NOT. ieee_is_finite(cfg%melting_efficiency)) RETURN
    IF (.NOT. ieee_is_finite(cfg%downdraft_efficiency)) RETURN
    IF (.NOT. ieee_is_finite(cfg%maximum_downdraft_ms)) RETURN
    IF (.NOT. ieee_is_finite(cfg%maximum_innovation_ms)) RETURN
    IF (.NOT. ieee_is_finite(cfg%entrainment_depth_m)) RETURN
    IF (.NOT. ieee_is_finite(cfg%surface_taper_depth_m)) RETURN
    IF (.NOT. ieee_is_finite(cfg%under_relaxation)) RETURN
    IF (.NOT. ieee_is_finite(cfg%convergence_ms)) RETURN
    IF (cfg%full_confidence_dbz <= cfg%minimum_dbz) RETURN
    IF (cfg%reference_concentration <= 0.0) RETURN
    IF (cfg%minimum_fall_speed <= 0.0) RETURN
    IF (cfg%evaporation_efficiency < 0.0 .OR. &
        cfg%evaporation_efficiency > 1.0) RETURN
    IF (cfg%sublimation_efficiency < 0.0 .OR. &
        cfg%sublimation_efficiency > 1.0) RETURN
    IF (cfg%melting_efficiency < 0.0 .OR. &
        cfg%melting_efficiency > 1.0) RETURN
    IF (cfg%downdraft_efficiency < 0.0 .OR. &
        cfg%downdraft_efficiency > 1.0) RETURN
    IF (cfg%maximum_downdraft_ms <= 0.0) RETURN
    IF (cfg%maximum_innovation_ms <= 0.0) RETURN
    IF (cfg%entrainment_depth_m <= 0.0) RETURN
    IF (cfg%surface_taper_depth_m <= 0.0) RETURN
    IF (cfg%under_relaxation <= 0.0 .OR. cfg%under_relaxation > 0.5) RETURN
    IF (cfg%maximum_iterations < 1 .OR. cfg%maximum_iterations > 10) RETURN
    IF (cfg%convergence_ms <= 0.0) RETURN
    config_is_valid=.TRUE.
  END FUNCTION config_is_valid

  LOGICAL FUNCTION meteorology_is_valid(temperature_k,rh_percent,height_m, &
                                         pressure_pa,rain,snow,graupel,omega, &
                                         missing)
    REAL, INTENT(IN) :: temperature_k(:,:,:),rh_percent(:,:,:),height_m(:,:,:)
    REAL, INTENT(IN) :: pressure_pa(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL, INTENT(IN) :: omega(:,:,:),missing
    INTEGER :: i,j,k
    meteorology_is_valid=.FALSE.
    IF (ANY(.NOT. ieee_is_finite(temperature_k))) RETURN
    IF (ANY(temperature_k < 180.0) .OR. ANY(temperature_k > 340.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(rh_percent))) RETURN
    IF (ANY(rh_percent < 0.0) .OR. ANY(rh_percent > 120.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(height_m))) RETURN
    IF (ANY(.NOT. ieee_is_finite(pressure_pa))) RETURN
    IF (ANY(pressure_pa <= 0.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(rain))) RETURN
    IF (ANY(rain < 0.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(snow))) RETURN
    IF (ANY(snow < 0.0)) RETURN
    IF (ANY(.NOT. ieee_is_finite(graupel))) RETURN
    IF (ANY(graupel < 0.0)) RETURN
    DO j=1,SIZE(height_m,2)
      DO i=1,SIZE(height_m,1)
        DO k=2,SIZE(height_m,3)
          IF (height_m(i,j,k) <= height_m(i,j,k-1) .OR. &
              pressure_pa(i,j,k) >= pressure_pa(i,j,k-1)) RETURN
        END DO
      END DO
    END DO
    IF (ANY(.NOT. ieee_is_finite(omega))) RETURN
    DO k=1,SIZE(omega,3)
      DO j=1,SIZE(omega,2)
        DO i=1,SIZE(omega,1)
          IF (.NOT. valid_omega(omega(i,j,k),missing) .AND. &
              ABS(omega(i,j,k)-missing) > 1.0E-5) RETURN
        END DO
      END DO
    END DO
    meteorology_is_valid=.TRUE.
  END FUNCTION meteorology_is_valid

END MODULE cloud_bal_radar_downdraft
