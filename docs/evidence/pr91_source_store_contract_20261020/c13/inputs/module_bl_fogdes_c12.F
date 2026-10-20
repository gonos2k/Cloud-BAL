MODULE module_bl_fogdes

  USE module_model_constants
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64

!-------------------------------------------------------------------
  IMPLICIT NONE
!-------------------------------------------------------------------
  REAL, PARAMETER :: gno=1.0  !original value seems too aggressive: 4.64158883361278196
  REAL, PARAMETER :: gpw=5./3., qcgmin=1.e-8

CONTAINS

  SUBROUTINE bl_fogdes(&
               vdfg,qc_curr,dtbl,rho,dz8w,grav_settling,dqc,       &
               ids,ide, jds,jde, kds,kde,                          &
               ims,ime, jms,jme, kms,kme,                          &
               its,ite, jts,jte, kts,kte                           &
                                                                   )

!  This module was written by Joseph Olson (CIRES-NOAA/GSD/AMB) to allow
!  gravitational settling of cloud droplets in the atmosphere for all 
!  PBL schemes (when grav_settling > 0). Previously, this option was only 
!  available for the MYNN PBL scheme.
!
!  This module is a companion to module_sf_fogdes, which calulcates the 
!  (fog) deposition onto the surface, so it uses a consistent formulation
!  at k=1. Currently, it uses a simple form taken from Dyunkerke (1991)
!  and Dyunkerke and Driedonks (1988), but uses a lower settling 
!  velocity coefficient (gno = 1.0 instead of 4.6).
!
!    settling velocity:            Vd = gno*(qc)**(2/3)
!    cloud water flux:  gflux = Vd*qc = gno*(qc)**(5/3)
!
!  This form assumes a constant number concentration: 10**8 /m**3 for
!  gno = 4.6 and approx .2*10**8 /m**3 for gno = 1.0.
!
! References:
!
! Dyunkerke, P.G. (1991), Radiation fog: a comparison of model simulations
!     with detailed observations, Mon. Wea. Rev., 119, 324-341.
! Nakanishi, Mikio (2000), Large-eddy simulation of radiation fog,
!     Boundary Layer Meteorology, 94, 461-493. 
!
!======================================================================
! Definitions
!-----------
!-- vdfg          deposition velocity of fog (m/s)
!-- qc_curr       cloud water mixing ratio (kg/kg)
!-- dqc           cloud water mixing ratio tendency
!-- dtbl          timestep (s)
!-- rho           density of the air (kg/m^3)
!-- dp_fog        mean fog droplet diameter (m)
!-- dz8w          dz between full levels (m)
!-- grav_settling flag for fog deposition at the lowest atmos layer
!           = 2   FogDES scheme
!           = 1   use Duynkerke (1991) - same as in atmos (above k = 1)
!           = 0   No gravitational settling
!-- lwc           cloud liquid water content (kg/m^3)
!-- ims           start index for i in memory
!-- ime           end index for i in memory
!-- jms           start index for j in memory
!-- jme           end index for j in memory
!-- kms           start index for k in memory
!-- kme           end index for k in memory
!-- its           start index for i in tile
!-- ite           end index for i in tile
!-- jts           start index for j in tile
!-- jte           end index for j in tile
!-- kts           start index for k in tile
!-- kte           end index for k in tile
!------------------------------------------------------------------

   INTEGER, INTENT(IN)                       :: ims,ime,jms,jme,kms,kme &
                                               ,its,ite,jts,jte,kts,kte &
                                               ,ids,ide,jds,jde,kds,kde

   INTEGER, INTENT(IN)                       :: grav_settling

   REAL, DIMENSION( ims:ime, kms:kme, jms:jme ),                        &
                                       INTENT(IN),OPTIONAL    :: qc_curr
   REAL, DIMENSION( ims:ime, kms:kme, jms:jme ),                        &
                                       INTENT(IN)             :: rho
   REAL, DIMENSION( ims:ime, kms:kme, jms:jme ),                        &
                                       INTENT(IN   )          :: dz8w

   REAL, DIMENSION( ims:ime, jms:jme ),INTENT(IN),OPTIONAL    :: vdfg

   REAL, INTENT(INOUT),OPTIONAL                               :: dtbl

!JOE-added for Dyunkerke(1991) & Dyunkerke and Driedonks (1988)
!    gravitational settling above the surface (creates qc tendency).
   REAL,parameter :: gpw2=0.66666666666667
   REAL :: gfluxp,gfluxm
   REAL, DIMENSION( ims:ime, kms:kme, jms:jme ),                        &
                                       INTENT(INOUT),OPTIONAL :: dqc
!JOE-end

! Local variables
   INTEGER :: i,j,k,grav_settling2
!------------------------------------------------------------------

  grav_settling2 = MIN(REAL(grav_settling), 1.)

   DO j=jts,jte
     DO i=its,ite

       !!====================================================
       !! Calculate gravitational settling in the atmosphere.
       !! This uses Dyunkerke (referenced above). Note that 
       !! only the cloud mixing ratio is settled, not the
       !! number concentration. 
       !!====================================================

       k=kts

       IF (qc_curr(i,k,j) > qcgmin) THEN
          gfluxm=grav_settling2*qc_curr(i,k,j)*vdfg(i,j)
       ELSE
          gfluxm=0.
       ENDIF

       IF (.5*(qc_curr(i,k+1,j)+qc_curr(i,k,j)) > qcgmin) THEN
          gfluxp=grav_settling2*gno* &
                & (.5*(qc_curr(i,k+1,j)+qc_curr(i,k,j)))**gpw
       ELSE
          gfluxp=0.
       ENDIF

       dqc(i,k,j)=dqc(i,k,j) + (gfluxp - gfluxm)/dz8w(i,kts,j)    !*dtbl

       !print*,"in bl_fogdes: i,j=",i,j
       !print*,"vdfg=",vdfg(i,j)," qc=",qc_curr(i,k,j)," dtbl=",dtbl
       !print*,"dqc=",dqc(i,k,j)," gfluxm=",gfluxm," gfluxp=",gfluxp

       DO k=kts+1,kte-1

          IF (.5*(qc_curr(i,k+1,j)+qc_curr(i,k,j)) > qcgmin) THEN
             gfluxp=grav_settling2*gno* &
                   & (.5*(qc_curr(i,k+1,j)+qc_curr(i,k,j)))**gpw
          ELSE
             gfluxp=0.
          ENDIF

          IF (.5*(qc_curr(i,k-1,j)+qc_curr(i,k,j)) > qcgmin) THEN
             gfluxm=grav_settling2*gno* &
                   & (.5*(qc_curr(i,k-1,j)+qc_curr(i,k,j)))**gpw
          ELSE
             gfluxm=0.
          ENDIF

          dqc(i,k,j)= dqc(i,k,j) + (gfluxp - gfluxm)/dz8w(i,k,j)  !*dtbl

       ENDDO

      ! dqc(i,kte,j)=0.

     ENDDO
   ENDDO

  END SUBROUTINE bl_fogdes

! Conditional PR85 research entry point. The legacy bl_fogdes interface above
! remains unchanged for all existing callers and non-KDM6 microphysics.
  SUBROUTINE bl_fogdes_qn(                                             &
       vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,rho,dz8w,             &
       grav_settling,dqc,dqnc,                                         &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,               &
       its,ite,jts,jte,kts,kte,ground_q_sink,ground_n_sink,cloud_source_delta64,source_step)
    INTEGER,INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme
    INTEGER,INTENT(IN) :: its,ite,jts,jte,kts,kte,grav_settling
    REAL,INTENT(IN) :: vdfg(ims:ime,jms:jme),dtbl
    REAL,INTENT(IN) :: qc_curr(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: qnc_curr(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: qv_curr(ims:ime,kms:kme,jms:jme),t_curr(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: rho(ims:ime,kms:kme,jms:jme),dz8w(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(INOUT) :: dqc(ims:ime,kms:kme,jms:jme),dqnc(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)
    REAL(real64),INTENT(INOUT),OPTIONAL :: cloud_source_delta64(ims:ime,kms:kme,jms:jme,2)
    INTEGER,INTENT(IN),OPTIONAL :: source_step
    REAL :: grav_scale
    grav_scale=MIN(REAL(grav_settling),1.0)
    IF (PRESENT(cloud_source_delta64)) THEN
      CALL fogdes_qn_stokes_flux(vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,grav_scale,rho,dz8w,dqc,dqnc, &
           ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte, &
           cloud_source_delta64,source_step)
    ELSE
      CALL fogdes_qn_stokes_flux(vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,grav_scale,rho,dz8w,dqc,dqnc, &
           ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte)
    ENDIF
  END SUBROUTINE bl_fogdes_qn

  SUBROUTINE fogdes_qn_stokes_flux(vdfg,qc,qnc,qv,temp,dt,grav_scale,rho,dz,dqc,dqnc, &
       ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,      &
       its,ite,jts,jte,kts,kte,cloud_source_delta64,source_step)
    USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
    USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
    EXTERNAL :: wrf_error_fatal
    INTEGER,INTENT(IN) :: ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte
    REAL,INTENT(IN) :: qc(ims:ime,kms:kme,jms:jme),qnc(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: qv(ims:ime,kms:kme,jms:jme),temp(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: vdfg(ims:ime,jms:jme),dt,grav_scale
    REAL,INTENT(IN) :: rho(ims:ime,kms:kme,jms:jme),dz(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(INOUT) :: dqc(ims:ime,kms:kme,jms:jme),dqnc(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)
    REAL(real64),INTENT(INOUT),OPTIONAL :: cloud_source_delta64(ims:ime,kms:kme,jms:jme,2)
    INTEGER,INTENT(IN),OPTIONAL :: source_step
    REAL(real64),PARAMETER :: mu_shape=2.0_real64
    ! Existing joint-Q/N cloud mean-mass cone endpoints (numerical policy).
    REAL(real64),PARAMETER :: mmin=4.188790204786391e-15_real64
    REAL(real64),PARAMETER :: mmax=3.0300855069345996e-10_real64
    REAL(real64),PARAMETER :: cloud_pidn=REAL(523.59881591796875_real32,real64)
    REAL(real64),PARAMETER :: cloud_lambda_min=12000.0_real64,cloud_lambda_max=500000.0_real64
    REAL(real64),PARAMETER :: strict_mmin=cloud_pidn/cloud_lambda_max**3.0_real64
    REAL(real64),PARAMETER :: strict_mmax=cloud_pidn/cloud_lambda_min**3.0_real64
    REAL(real64),PARAMETER :: alpha=mu_shape+1.0_real64
    REAL(real64) :: dryrho,cmc,lambda3,lambda_inv2,mu_dyn,a,vn,vq
    REAL(real64) :: fq(kms:kte+1),fn(kms:kte+1),dq(kms:kte),dn(kms:kte)
    REAL(real64) :: base_dq(kms:kte),base_dn(kms:kte)
    REAL(real64) :: corrected_base_dq(kms:kte),corrected_base_dn(kms:kte)
    REAL(real64) :: input_delta_q(kms:kte),input_delta_n(kms:kte)
    REAL(real64) :: total_rate_q(kms:kte),total_rate_n(kms:kte)
    REAL(real64) :: legacy_rate_q(kms:kte),legacy_rate_n(kms:kte)
    REAL(real64) :: output_delta_q(kms:kte),output_delta_n(kms:kte)
    REAL :: stored_rate_q(kms:kte),stored_rate_n(kms:kte)
    REAL(real64) :: theta,lo,hi,rate_q64,rate_n64,reconstructed_q64,reconstructed_n64
    REAL(real32) :: theta32
    REAL(real64) :: qvalue,nvalue,meanmass,lower_tol,upper_tol
    REAL(real64) :: applied_q,applied_n,ground_q,ground_n,residual_q,residual_n
    REAL(real64) :: increment_q,increment_n
    REAL(real64) :: incoming_sum_q,incoming_sum_n,incoming_l1_q,incoming_l1_n
    REAL(real64) :: outgoing_sum_q,outgoing_sum_n,outgoing_l1_q,outgoing_l1_n
    REAL(real64) :: incoming_max_q,incoming_max_n,outgoing_max_q,outgoing_max_n
    REAL(real64) :: sample_in_q,sample_in_n,sample_out_q,sample_out_n
    INTEGER :: i,j,k,ktop,iteration,budget_unit,io_status,changed_count,sample_k
    LOGICAL :: feasible

    IF (PRESENT(cloud_source_delta64)) THEN
      IF (.NOT.PRESENT(source_step)) &
        CALL wrf_error_fatal('FogDES source correction requires an explicit timestep')
      IF (source_step<1) CALL wrf_error_fatal('FogDES source correction has invalid timestep')
    ENDIF
    IF (.NOT.ieee_is_finite(dt) .OR. dt<=0.0) &
      CALL wrf_error_fatal('FogDES paired Stokes settling requires positive timestep')
    IF (.NOT.ieee_is_finite(grav_scale) .OR. grav_scale<0.0) &
      CALL wrf_error_fatal('FogDES paired Stokes settling requires valid scale')
    IF (.NOT.ALL(ieee_is_finite(vdfg))) &
      CALL wrf_error_fatal('FogDES paired Stokes settling received nonfinite VDFG')
    cmc=acos(-1.0_real64)*REAL(rhowater,real64)/6.0_real64
    ground_q_sink=0.0
    ground_n_sink=0.0
    ktop=MIN(kte,kde-1)
    OPEN(NEWUNIT=budget_unit,FILE='pr85_fogdes_budget.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE',IOSTAT=io_status)
    IF (io_status/=0) CALL wrf_error_fatal('FogDES paired Q/N budget file open failed')
    WRITE(budget_unit,'(a,1x,1p,es24.16,1x,6i8)') &
      'PR85_FOGDES_BUDGET_META',REAL(dt,real64),its,ite,jts,jte,kts,ktop
    WRITE(budget_unit,'(a)') &
      'PR85_FOGDES_BUDGET_UNITS local_rho_dry_times_dz Q_kg_per_m2 N_per_m2 residual=committed_plus_ground'
    WRITE(budget_unit,'(a)') &
      'PR87_FOGDES_SOURCE_CORRECTION_UNITS Q/N are unweighted tendency-rate deltas per dry-air mass per second; summaries are not budgets'
    IF (ktop<kts) THEN
      CLOSE(budget_unit,IOSTAT=io_status)
      IF (io_status/=0) CALL wrf_error_fatal('FogDES paired Q/N budget file close failed')
      RETURN
    ENDIF
    DO j=jts,jte
      DO i=its,ite
        fq=0.0_real64; fn=0.0_real64; dq=0.0_real64; dn=0.0_real64
        DO k=kts,ktop
          IF (.NOT.ieee_is_finite(qc(i,k,j)) .OR. .NOT.ieee_is_finite(qnc(i,k,j)) .OR. &
              .NOT.ieee_is_finite(qv(i,k,j)) .OR. .NOT.ieee_is_finite(temp(i,k,j)) .OR. &
              .NOT.ieee_is_finite(rho(i,k,j)) .OR. .NOT.ieee_is_finite(dz(i,k,j)) .OR. &
              .NOT.ieee_is_finite(dqc(i,k,j)) .OR. .NOT.ieee_is_finite(dqnc(i,k,j))) &
            CALL wrf_error_fatal('FogDES paired Stokes settling received nonfinite input')
          base_dq(k)=REAL(dqc(i,k,j),real64)
          base_dn(k)=REAL(dqnc(i,k,j),real64)
          corrected_base_dq(k)=base_dq(k)
          corrected_base_dn(k)=base_dn(k)
          input_delta_q(k)=0.0_real64; input_delta_n(k)=0.0_real64
          IF (PRESENT(cloud_source_delta64)) THEN
            input_delta_q(k)=cloud_source_delta64(i,k,j,1)
            input_delta_n(k)=cloud_source_delta64(i,k,j,2)
            IF (.NOT.ALL(ieee_is_finite([input_delta_q(k),input_delta_n(k)]))) &
              CALL wrf_error_fatal('FogDES source correction is nonfinite')
            corrected_base_dq(k)=base_dq(k)+input_delta_q(k)
            corrected_base_dn(k)=base_dn(k)+input_delta_n(k)
            IF (.NOT.ALL(ieee_is_finite([corrected_base_dq(k),corrected_base_dn(k)]))) &
              CALL wrf_error_fatal('FogDES corrected base tendency is nonfinite')
          ENDIF
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
          IF (qv(i,k,j)<=-1.0 .OR. dryrho<=0.0 .OR. dz(i,k,j)<=0.0 .OR. temp(i,k,j)<=0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling requires positive state')
          IF (qc(i,k,j)<0.0 .OR. qnc(i,k,j)<0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling received negative Q/N')
          IF (qc(i,k,j)==0.0 .AND. qnc(i,k,j)==0.0) CYCLE
          IF (qc(i,k,j)<=0.0 .OR. qnc(i,k,j)<=0.0) THEN
            WRITE(*,'(a,3(1x,i0),2(1x,es24.16))') 'PR87_FOGDES_REJECT', &
                 i,j,k,REAL(qc(i,k,j),real64),REAL(qnc(i,k,j),real64)
            CALL wrf_error_fatal('FogDES paired Stokes settling requires both cloud moments')
          ENDIF
          ! Gamma PSD: alpha=muc+1=3; Q,N use the same cell PSD, not one speed.
          lambda3=cmc*gamma(1.0_real64+3.0_real64/alpha)* &
                   REAL(qnc(i,k,j),real64)/REAL(qc(i,k,j),real64)
          IF (lambda3<=0.0_real64) &
            CALL wrf_error_fatal('FogDES paired Stokes settling has invalid PSD slope')
          lambda_inv2=lambda3**(-2.0_real64/3.0_real64)
          mu_dyn=1.496e-6_real64*REAL(temp(i,k,j),real64)* &
                  SQRT(REAL(temp(i,k,j),real64))/(REAL(temp(i,k,j),real64)+120.0_real64)
          a=(REAL(rhowater,real64)-REAL(rho(i,k,j),real64))*REAL(g,real64)/ &
             (18.0_real64*mu_dyn)
          IF (a<0.0_real64) CALL wrf_error_fatal('FogDES paired Stokes settling has invalid gas density')
          vn=a*lambda_inv2*gamma(1.0_real64+2.0_real64/alpha)
          vq=a*lambda_inv2*gamma(1.0_real64+5.0_real64/alpha)/ &
               gamma(1.0_real64+3.0_real64/alpha)
          ! Ground deposition remains a separate bulk VDFG process. For this
          ! bottom face, use VDFG for both moments; atmospheric faces use VQ/VN.
          IF (k==kts) THEN
            IF (vdfg(i,j)<0.0) &
              CALL wrf_error_fatal('FogDES bulk ground deposition speed must be nonnegative')
            fq(k)=REAL(grav_scale,real64)*dryrho*REAL(qc(i,k,j),real64)*REAL(vdfg(i,j),real64)
            fn(k)=REAL(grav_scale,real64)*dryrho*REAL(qnc(i,k,j),real64)*REAL(vdfg(i,j),real64)
            CYCLE
          ENDIF
          fq(k)=REAL(grav_scale,real64)*dryrho*REAL(qc(i,k,j),real64)*vq
          fn(k)=REAL(grav_scale,real64)*dryrho*REAL(qnc(i,k,j),real64)*vn
          IF (.NOT.ieee_is_finite(fq(k)) .OR. .NOT.ieee_is_finite(fn(k))) &
            CALL wrf_error_fatal('FogDES paired Stokes settling produced nonfinite face flux')
        ENDDO
        ! Top boundary is closed; lower boundary is VDFG bulk deposition.
        DO k=kts,ktop
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
          dq(k)=(fq(k+1)-fq(k))/(dryrho*REAL(dz(i,k,j),real64))
          dn(k)=(fn(k+1)-fn(k))/(dryrho*REAL(dz(i,k,j),real64))
          IF (.NOT.ieee_is_finite(dq(k)) .OR. .NOT.ieee_is_finite(dn(k))) &
            CALL wrf_error_fatal('FogDES paired Stokes settling produced nonfinite tendency')
        ENDDO
        theta=1.0_real64
        CALL candidate(theta,feasible)
        IF (.NOT.feasible) THEN
          CALL candidate(0.0_real64,feasible)
          IF (.NOT.feasible) CALL wrf_error_fatal('FogDES paired Q/N state outside cloud PSD cone')
          lo=0.0_real64; hi=1.0_real64
          DO iteration=1,48
            theta=0.5_real64*(lo+hi)
            CALL candidate(theta,feasible)
            IF (feasible) THEN
              lo=theta
            ELSE
              hi=theta
            ENDIF
          ENDDO
          theta=lo
        ENDIF
        IF (PRESENT(cloud_source_delta64) .AND. theta>0.0_real64 .AND. theta<1.0_real64) THEN
          theta32=REAL(theta,real32)
          IF (REAL(theta32,real64)>theta) theta32=NEAREST(theta32,-1.0_real32)
          theta=REAL(theta32,real64)
        ENDIF
        CALL candidate(theta,feasible)
        IF (.NOT.feasible) CALL wrf_error_fatal('FogDES paired Q/N face factor failed')
        applied_q=0.0_real64; applied_n=0.0_real64
        ground_q=dt*theta*fq(kts); ground_n=dt*theta*fn(kts)
        IF (PRESENT(cloud_source_delta64)) THEN
          incoming_sum_q=0.0_real64; incoming_sum_n=0.0_real64
          incoming_l1_q=0.0_real64; incoming_l1_n=0.0_real64
          outgoing_sum_q=0.0_real64; outgoing_sum_n=0.0_real64
          outgoing_l1_q=0.0_real64; outgoing_l1_n=0.0_real64
          incoming_max_q=0.0_real64; incoming_max_n=0.0_real64
          outgoing_max_q=0.0_real64; outgoing_max_n=0.0_real64
          changed_count=0; sample_k=0
          sample_in_q=0.0_real64; sample_in_n=0.0_real64
          sample_out_q=0.0_real64; sample_out_n=0.0_real64
          DO k=kts,ktop
            total_rate_q(k)=corrected_base_dq(k)+theta*dq(k)
            total_rate_n(k)=corrected_base_dn(k)+theta*dn(k)
            legacy_rate_q(k)=base_dq(k)+theta*dq(k)
            legacy_rate_n(k)=base_dn(k)+theta*dn(k)
            IF (.NOT.ALL(ieee_is_finite([total_rate_q(k),total_rate_n(k), &
                                        legacy_rate_q(k),legacy_rate_n(k)]))) &
              CALL wrf_error_fatal('FogDES accepted source correction is nonfinite')
            IF (ABS(total_rate_q(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(total_rate_n(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(legacy_rate_q(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(legacy_rate_n(k))>REAL(HUGE(0.0_real32),real64)) &
              CALL wrf_error_fatal('FogDES accepted tendency exceeds REAL32 range')
            stored_rate_q(k)=REAL(legacy_rate_q(k),real32)
            stored_rate_n(k)=REAL(legacy_rate_n(k),real32)
            output_delta_q(k)=total_rate_q(k)-REAL(stored_rate_q(k),real64)
            output_delta_n(k)=total_rate_n(k)-REAL(stored_rate_n(k),real64)
            IF (.NOT.ALL(ieee_is_finite([output_delta_q(k),output_delta_n(k)]))) &
              CALL wrf_error_fatal('FogDES accepted source correction is nonfinite')
            IF (input_delta_q(k)/=0.0_real64 .OR. input_delta_n(k)/=0.0_real64 .OR. &
                output_delta_q(k)/=0.0_real64 .OR. output_delta_n(k)/=0.0_real64) THEN
              changed_count=changed_count+1
              incoming_sum_q=incoming_sum_q+input_delta_q(k)
              incoming_sum_n=incoming_sum_n+input_delta_n(k)
              incoming_l1_q=incoming_l1_q+ABS(input_delta_q(k))
              incoming_l1_n=incoming_l1_n+ABS(input_delta_n(k))
              incoming_max_q=MAX(incoming_max_q,ABS(input_delta_q(k)))
              incoming_max_n=MAX(incoming_max_n,ABS(input_delta_n(k)))
              outgoing_sum_q=outgoing_sum_q+output_delta_q(k)
              outgoing_sum_n=outgoing_sum_n+output_delta_n(k)
              outgoing_l1_q=outgoing_l1_q+ABS(output_delta_q(k))
              outgoing_l1_n=outgoing_l1_n+ABS(output_delta_n(k))
              outgoing_max_q=MAX(outgoing_max_q,ABS(output_delta_q(k)))
              outgoing_max_n=MAX(outgoing_max_n,ABS(output_delta_n(k)))
              IF (sample_k==0) THEN
                sample_k=k
                sample_in_q=input_delta_q(k); sample_in_n=input_delta_n(k)
                sample_out_q=output_delta_q(k); sample_out_n=output_delta_n(k)
              ENDIF
            ENDIF
          ENDDO
          IF (changed_count>0) THEN
            WRITE(budget_unit,'(a,5i10,1p,17es24.16)',IOSTAT=io_status) &
              'PR87_FOGDES_SOURCE_CORRECTION_RK',source_step,i,j,changed_count,sample_k,theta, &
              incoming_sum_q,incoming_sum_n,incoming_l1_q,incoming_l1_n, &
              incoming_max_q,incoming_max_n,outgoing_sum_q,outgoing_sum_n, &
              outgoing_l1_q,outgoing_l1_n,outgoing_max_q,outgoing_max_n, &
              sample_in_q,sample_in_n,sample_out_q,sample_out_n
            IF (io_status/=0) CALL wrf_error_fatal('FogDES source correction ledger write failed')
          ENDIF
          DO k=kts,ktop
            dqc(i,k,j)=stored_rate_q(k)
            dqnc(i,k,j)=stored_rate_n(k)
            cloud_source_delta64(i,k,j,1)=output_delta_q(k)
            cloud_source_delta64(i,k,j,2)=output_delta_n(k)
          ENDDO
        ELSE
          DO k=kts,ktop
            dqc(i,k,j)=REAL(base_dq(k)+theta*dq(k))
            dqnc(i,k,j)=REAL(base_dn(k)+theta*dn(k))
          ENDDO
        ENDIF
        DO k=kts,ktop
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
          increment_q=REAL(dqc(i,k,j)-REAL(base_dq(k)),real64)
          increment_n=REAL(dqnc(i,k,j)-REAL(base_dn(k)),real64)
          applied_q=applied_q+REAL(dt,real64)*dryrho*REAL(dz(i,k,j),real64)*increment_q
          applied_n=applied_n+REAL(dt,real64)*dryrho*REAL(dz(i,k,j),real64)*increment_n
        ENDDO
        residual_q=applied_q+ground_q
        residual_n=applied_n+ground_n
        IF (.NOT.ALL(ieee_is_finite([applied_q,applied_n,ground_q,ground_n,residual_q,residual_n]))) &
          CALL wrf_error_fatal('FogDES paired Q/N process budget is nonfinite')
        ! Local rho_dry*dz layer inventory; this is not native hybrid-Md closure.
        IF (theta*SUM(ABS(fq(kts:ktop+1)))>0.0_real64 .OR. &
            theta*SUM(ABS(fn(kts:ktop+1)))>0.0_real64) &
          WRITE(budget_unit,'(a,2i8,1x,1p,7es24.16)') 'PR85_FOGDES_BUDGET',i,j,theta, &
            ground_q,ground_n,applied_q,applied_n,residual_q,residual_n
        ! Exact bottom sink for the atmosphere column over this timestep.
        IF (.NOT.ieee_is_finite(dt*theta*fq(kts)) .OR. &
            .NOT.ieee_is_finite(dt*theta*fn(kts)) .OR. &
            dt*theta*fq(kts)>REAL(HUGE(0.0),real64) .OR. &
            dt*theta*fn(kts)>REAL(HUGE(0.0),real64)) &
          CALL wrf_error_fatal('FogDES paired ground ledger is nonfinite')
        ground_q_sink(i,j)=REAL(dt*theta*fq(kts))
        ground_n_sink(i,j)=REAL(dt*theta*fn(kts))
      ENDDO
    ENDDO
    CLOSE(budget_unit,IOSTAT=io_status)
    IF (io_status/=0) CALL wrf_error_fatal('FogDES paired Q/N budget file close failed')
  CONTAINS
    SUBROUTINE candidate(scale,ok)
      REAL(real64),INTENT(IN) :: scale
      LOGICAL,INTENT(OUT) :: ok
      INTEGER :: kk
      REAL :: stored_dq,stored_dn,qstate32,nstate32
      ok=.FALSE.
      DO kk=kts,ktop
        IF (PRESENT(cloud_source_delta64)) THEN
          rate_q64=corrected_base_dq(kk)+scale*dq(kk)
          rate_n64=corrected_base_dn(kk)+scale*dn(kk)
          legacy_rate_q(kk)=base_dq(kk)+scale*dq(kk)
          legacy_rate_n(kk)=base_dn(kk)+scale*dn(kk)
          IF (.NOT.ALL(ieee_is_finite([rate_q64,rate_n64,legacy_rate_q(kk),legacy_rate_n(kk)]))) RETURN
          IF (ABS(rate_q64)>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(rate_n64)>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(legacy_rate_q(kk))>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(legacy_rate_n(kk))>REAL(HUGE(0.0_real32),real64)) RETURN
          stored_dq=REAL(legacy_rate_q(kk),real32)
          stored_dn=REAL(legacy_rate_n(kk),real32)
          IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
          output_delta_q(kk)=rate_q64-REAL(stored_dq,real64)
          output_delta_n(kk)=rate_n64-REAL(stored_dn,real64)
          reconstructed_q64=REAL(stored_dq,real64)+output_delta_q(kk)
          reconstructed_n64=REAL(stored_dn,real64)+output_delta_n(kk)
          IF (.NOT.ALL(ieee_is_finite([output_delta_q(kk),output_delta_n(kk), &
                                      reconstructed_q64,reconstructed_n64]))) RETURN
          qvalue=REAL(qc(i,kk,j),real64)+REAL(dt,real64)*reconstructed_q64
          nvalue=REAL(qnc(i,kk,j),real64)+REAL(dt,real64)*reconstructed_n64
        ELSE
          stored_dq=REAL(base_dq(kk)+scale*dq(kk))
          stored_dn=REAL(base_dn(kk)+scale*dn(kk))
          IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
          qstate32=qc(i,kk,j)+dt*stored_dq
          nstate32=qnc(i,kk,j)+dt*stored_dn
          qvalue=REAL(qstate32,real64)
          nvalue=REAL(nstate32,real64)
        ENDIF
        IF (.NOT.ieee_is_finite(qvalue) .OR. .NOT.ieee_is_finite(nvalue)) RETURN
        IF (qvalue<0.0_real64 .OR. nvalue<0.0_real64) RETURN
        IF (qvalue==0.0_real64 .AND. nvalue==0.0_real64) CYCLE
        IF (qvalue<=0.0_real64 .OR. nvalue<=0.0_real64) RETURN
        meanmass=qvalue/nvalue
        IF (.NOT.ieee_is_finite(meanmass) .OR. &
            qvalue>REAL(HUGE(0.0),real64) .OR. nvalue>REAL(HUGE(0.0),real64)) RETURN
        IF (PRESENT(cloud_source_delta64)) THEN
          IF (qvalue<strict_mmin*nvalue .OR. qvalue>strict_mmax*nvalue) RETURN
        ELSE
          lower_tol=8.0_real64*REAL(SPACING(REAL(mmin)),real64)
          upper_tol=8.0_real64*REAL(SPACING(REAL(mmax)),real64)
          IF (meanmass<mmin-lower_tol .OR. meanmass>mmax+upper_tol) RETURN
        ENDIF
      ENDDO
      ok=.TRUE.
    END SUBROUTINE candidate
  END SUBROUTINE fogdes_qn_stokes_flux
! ==================================================================

END MODULE module_bl_fogdes
