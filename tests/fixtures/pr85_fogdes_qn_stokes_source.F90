MODULE module_model_constants
  REAL,PARAMETER :: g=9.81,rhowater=1000.0,epsilon=1.0
END MODULE module_model_constants
MODULE pr85_fogdes_source_fixture
  USE module_model_constants
CONTAINS
  SUBROUTINE fogdes_qn_stokes_flux(vdfg,qc,qnc,qv,temp,dt,grav_scale,rho,dz,dqc,dqnc, &
       ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,      &
       its,ite,jts,jte,kts,kte)
    USE, INTRINSIC :: iso_fortran_env, ONLY: real64
    USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
    EXTERNAL :: wrf_error_fatal
    INTEGER,INTENT(IN) :: ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte
    REAL,INTENT(IN) :: qc(ims:ime,kms:kme,jms:jme),qnc(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: qv(ims:ime,kms:kme,jms:jme),temp(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(IN) :: vdfg(ims:ime,jms:jme),dt,grav_scale
    REAL,INTENT(IN) :: rho(ims:ime,kms:kme,jms:jme),dz(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(INOUT) :: dqc(ims:ime,kms:kme,jms:jme),dqnc(ims:ime,kms:kme,jms:jme)
    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)
    REAL(real64),PARAMETER :: mu_shape=2.0_real64
    ! Existing joint-Q/N cloud mean-mass cone endpoints (numerical policy).
    REAL(real64),PARAMETER :: mmin=4.188790204786391e-15_real64
    REAL(real64),PARAMETER :: mmax=3.0300855069345996e-10_real64
    REAL(real64),PARAMETER :: alpha=mu_shape+1.0_real64
    REAL(real64) :: dryrho,cmc,lambda3,lambda_inv2,mu_dyn,a,vn,vq
    REAL(real64) :: fq(kms:kte+1),fn(kms:kte+1),dq(kms:kte),dn(kms:kte)
    REAL(real64) :: base_dq(kms:kte),base_dn(kms:kte)
    REAL(real64) :: theta,lo,hi
    REAL(real64) :: qvalue,nvalue,meanmass,lower_tol,upper_tol
    REAL(real64) :: applied_q,applied_n,ground_q,ground_n,residual_q,residual_n
    REAL(real64) :: increment_q,increment_n
    INTEGER :: i,j,k,ktop,iteration,budget_unit,io_status
    LOGICAL :: feasible

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
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
          IF (qv(i,k,j)<=-1.0 .OR. dryrho<=0.0 .OR. dz(i,k,j)<=0.0 .OR. temp(i,k,j)<=0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling requires positive state')
          IF (qc(i,k,j)<0.0 .OR. qnc(i,k,j)<0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling received negative Q/N')
          IF (qc(i,k,j)==0.0 .AND. qnc(i,k,j)==0.0) CYCLE
          IF (qc(i,k,j)<=0.0 .OR. qnc(i,k,j)<=0.0) &
            CALL wrf_error_fatal('FogDES paired Stokes settling requires both cloud moments')
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
        CALL candidate(theta,feasible)
        IF (.NOT.feasible) CALL wrf_error_fatal('FogDES paired Q/N face factor failed')
        applied_q=0.0_real64; applied_n=0.0_real64
        ground_q=dt*theta*fq(kts); ground_n=dt*theta*fn(kts)
        DO k=kts,ktop
          dqc(i,k,j)=REAL(base_dq(k)+theta*dq(k))
          dqnc(i,k,j)=REAL(base_dn(k)+theta*dn(k))
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
        stored_dq=REAL(base_dq(kk)+scale*dq(kk))
        stored_dn=REAL(base_dn(kk)+scale*dn(kk))
        IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
        qstate32=qc(i,kk,j)+dt*stored_dq
        nstate32=qnc(i,kk,j)+dt*stored_dn
        qvalue=REAL(qstate32,real64)
        nvalue=REAL(nstate32,real64)
        IF (.NOT.ieee_is_finite(qvalue) .OR. .NOT.ieee_is_finite(nvalue)) RETURN
        IF (qvalue<0.0_real64 .OR. nvalue<0.0_real64) RETURN
        IF (qvalue==0.0_real64 .AND. nvalue==0.0_real64) CYCLE
        IF (qvalue<=0.0_real64 .OR. nvalue<=0.0_real64) RETURN
        meanmass=qvalue/nvalue
        IF (.NOT.ieee_is_finite(meanmass) .OR. &
            qvalue>REAL(HUGE(0.0),real64) .OR. nvalue>REAL(HUGE(0.0),real64)) RETURN
        lower_tol=8.0_real64*REAL(SPACING(REAL(mmin)),real64)
        upper_tol=8.0_real64*REAL(SPACING(REAL(mmax)),real64)
        IF (meanmass<mmin-lower_tol .OR. meanmass>mmax+upper_tol) RETURN
      ENDDO
      ok=.TRUE.
    END SUBROUTINE candidate
  END SUBROUTINE fogdes_qn_stokes_flux
END MODULE pr85_fogdes_source_fixture
PROGRAM pr85_fogdes_qn_stokes_regression
  USE pr85_fogdes_source_fixture, ONLY: fogdes_qn_stokes_flux
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  IMPLICIT NONE
  REAL :: q(1:1,1:3,1:1),n(1:1,1:3,1:1),qv(1:1,1:3,1:1),t(1:1,1:3,1:1)
  REAL :: rho(1:1,1:3,1:1),dz(1:1,1:3,1:1),dq(1:1,1:3,1:1),dn(1:1,1:3,1:1)
  REAL :: vdfg(1:1,1:1),gq(1:1,1:1),gn(1:1,1:1)
  REAL(real64) :: dry,oldq,oldn,newq,newn,balanceq,balancen,ratio,meanmass
  REAL(real64) :: alpha,lambda3,lambda_inv2,mu_dyn,a,vn,vq
  INTEGER :: i,k
  i=1; q=0.0; n=0.0; qv=0.01; t=260.0; rho=1.2; dz=100.0; dq=0.0; dn=0.0; vdfg=0.0
  ! Reproduce the dangerous source topology: lower k=1 cloud, empty upper k=2.
  ! The old centered gfluxm removed material from empty k=2. Donor-upwind is zero.
  q(1,1,1)=1.645385e-6; n(1,1,1)=q(1,1,1)/1.0e-14
  dq(1,3,1)=77.0; dn(1,3,1)=88.0
  CALL fogdes_qn_stokes_flux(vdfg,q,n,qv,t,900.0,1.0,rho,dz,dq,dn,gq,gn, &
       1,1,1,1,1,3,3,1,1,1,1,1,2)
  IF (dq(1,2,1)<0.0 .OR. dn(1,2,1)<0.0 .OR. dq(1,2,1)/=0.0 .OR. dn(1,2,1)/=0.0) &
    ERROR STOP 'empty upper cell received centered-flux loss'
  IF (dq(1,3,1)/=77.0 .OR. dn(1,3,1)/=88.0) ERROR STOP 'top ghost tendency was changed'
  PRINT '(a)', 'CASE empty upper cell protected; top ghost untouched'
  q=0.0; n=0.0; dq=0.0; dn=0.0
  q(1,2,1)=1.645385e-6
  n(1,2,1)=q(1,2,1)/1.0e-14
  dry=REAL(rho(1,1,1)/(1.0+qv(1,1,1)),real64)
  alpha=3.0_real64
  lambda3=(acos(-1.0_real64)*1000.0_real64/6.0_real64)* &
           gamma(1.0_real64+3.0_real64/alpha)*REAL(n(1,2,1),real64)/REAL(q(1,2,1),real64)
  lambda_inv2=lambda3**(-2.0_real64/3.0_real64)
  mu_dyn=1.496e-6_real64*260.0_real64*sqrt(260.0_real64)/(260.0_real64+120.0_real64)
  a=(1000.0_real64-1.2_real64)*9.81_real64/(18.0_real64*mu_dyn)
  vn=a*lambda_inv2*gamma(1.0_real64+2.0_real64/alpha)
  vq=a*lambda_inv2*gamma(1.0_real64+5.0_real64/alpha)/gamma(1.0_real64+3.0_real64/alpha)
  IF (ABS(vq/vn-5.0_real64/3.0_real64)>1.0e-12_real64) ERROR STOP 'VQ/VN is not 5/3'
  oldq=REAL(q(1,1,1),real64)+REAL(q(1,2,1),real64)
  oldn=REAL(n(1,1,1),real64)+REAL(n(1,2,1),real64)
  CALL fogdes_qn_stokes_flux(vdfg,q,n,qv,t,900.0,1.0,rho,dz,dq,dn,gq,gn, &
       1,1,1,1,1,3,3,1,1,1,1,1,2)
  IF (dq(1,1,1)<0.0 .OR. dn(1,1,1)<0.0) ERROR STOP 'empty receiving cell became negative'
  ratio=REAL(dq(1,1,1),real64)/REAL(dn(1,1,1),real64) / &
        (REAL(q(1,2,1),real64)/REAL(n(1,2,1),real64))
  IF (ABS(ratio-5.0_real64/3.0_real64)>2.0e-5_real64) ERROR STOP 'source fluxes used same Q/N speed'
  IF (REAL(q(1,2,1),real64)+900.0_real64*REAL(dq(1,2,1),real64)<-1.0e-12_real64) &
    ERROR STOP 'Q donor availability failed'
  IF (REAL(n(1,2,1),real64)+900.0_real64*REAL(dn(1,2,1),real64)<-1.0e-4_real64) &
    ERROR STOP 'N donor availability failed'
  meanmass=(REAL(q(1,1,1),real64)+900.0_real64*REAL(dq(1,1,1),real64))/ &
           (REAL(n(1,1,1),real64)+900.0_real64*REAL(dn(1,1,1),real64))
  IF (meanmass<4.188790204786391e-15_real64 .OR. meanmass>3.0300855069345996e-10_real64) &
    ERROR STOP 'receiving cell left the joint Q/N cone'
  meanmass=(REAL(q(1,2,1),real64)+900.0_real64*REAL(dq(1,2,1),real64))/ &
           (REAL(n(1,2,1),real64)+900.0_real64*REAL(dn(1,2,1),real64))
  IF (meanmass<4.188790204786391e-15_real64 .OR. meanmass>3.0300855069345996e-10_real64) &
    ERROR STOP 'donor cell left the joint Q/N cone'
  newq=0.0_real64; newn=0.0_real64
  DO k=1,2
    dry=REAL(rho(1,k,1)/(1.0+qv(1,k,1)),real64)
    newq=newq+dry*REAL(dz(1,k,1),real64)*(REAL(q(1,k,1),real64)+900.0_real64*REAL(dq(1,k,1),real64))
    newn=newn+dry*REAL(dz(1,k,1),real64)*(REAL(n(1,k,1),real64)+900.0_real64*REAL(dn(1,k,1),real64))
  ENDDO
  ! Both layers have the same dry column mass in this fixture.
  balanceq=newq-oldq*REAL(rho(1,1,1)/(1.0+qv(1,1,1)),real64)*100.0_real64
  balancen=newn-oldn*REAL(rho(1,1,1)/(1.0+qv(1,1,1)),real64)*100.0_real64
  IF (ABS(balanceq)>1.0e-10_real64 .OR. ABS(balancen)>1.0_real64) &
    ERROR STOP 'closed-column Q/N conservation failed'
  PRINT '(a,es12.4,a,es12.4,a,es12.4)', 'CASE empty-layer corrected dQ=',dq(1,1,1), &
       ' dN=',dn(1,1,1),' transfer Q/N=',ratio

  ! Exercise the independent VDFG bulk boundary sink and its exact ledger.
  q(1,1,1)=2.0e-6; n(1,1,1)=q(1,1,1)/1.0e-14; dq=0.0; dn=0.0; vdfg=10.0
  oldq=SUM(REAL(q,real64)); oldn=SUM(REAL(n,real64))
  CALL fogdes_qn_stokes_flux(vdfg,q,n,qv,t,900.0,1.0,rho,dz,dq,dn,gq,gn, &
       1,1,1,1,1,3,3,1,1,1,1,1,2)
  newq=0.0_real64; newn=0.0_real64
  DO k=1,2
    dry=REAL(rho(1,k,1)/(1.0+qv(1,k,1)),real64)
    newq=newq+dry*REAL(dz(1,k,1),real64)*(REAL(q(1,k,1),real64)+900.0_real64*REAL(dq(1,k,1),real64))
    newn=newn+dry*REAL(dz(1,k,1),real64)*(REAL(n(1,k,1),real64)+900.0_real64*REAL(dn(1,k,1),real64))
  ENDDO
  dry=REAL(rho(1,1,1)/(1.0+qv(1,1,1)),real64)
  IF (gq(1,1)<=0.0 .OR. gn(1,1)<=0.0) ERROR STOP 'ground sink ledger missing'
  IF (REAL(q(1,1,1),real64)+900.0_real64*REAL(dq(1,1,1),real64)<0.0_real64 .OR. &
      REAL(n(1,1,1),real64)+900.0_real64*REAL(dn(1,1,1),real64)<0.0_real64) &
    ERROR STOP 'one face factor failed donor availability'
  IF (ABS((newq-oldq*dry*100.0_real64)+REAL(gq(1,1),real64))>MAX(1.0e-10_real64,ABS(oldq*dry*100.0_real64)*1.0e-6_real64)) &
    ERROR STOP 'ground Q sink does not close column ledger'
  IF (ABS((newn-oldn*dry*100.0_real64)+REAL(gn(1,1),real64))>MAX(1.0_real64,ABS(oldn*dry*100.0_real64)*1.0e-6_real64)) &
    ERROR STOP 'ground N sink does not close column ledger'
  PRINT '(a,es12.4,a,es12.4)', 'CASE VDFG ground sinks Q=',gq(1,1),' N=',gn(1,1)

  ! The old mmax-scaled tolerance admitted a several-percent lower-bound
  ! violation. This near-mmin donor must reduce the shared face factor.
  q=0.0; n=0.0; dq=0.0; dn=0.0; vdfg=0.0
  q(1,2,1)=1.0e-6
  n(1,2,1)=q(1,2,1)/(4.188790204786391e-15*1.01)
  CALL fogdes_qn_stokes_flux(vdfg,q,n,qv,t,50000.0,1.0,rho,dz,dq,dn,gq,gn, &
       1,1,1,1,1,3,3,1,1,1,1,1,2)
  meanmass=(REAL(q(1,2,1),real64)+50000.0_real64*REAL(dq(1,2,1),real64))/ &
           (REAL(n(1,2,1),real64)+50000.0_real64*REAL(dn(1,2,1),real64))
  IF (meanmass<4.188790204786391e-15_real64- &
      8.0_real64*REAL(SPACING(REAL(4.188790204786391e-15_real64)),real64)) &
    ERROR STOP 'near-mmin donor escaped bound-specific cone tolerance'
  PRINT '(a,es12.4)', 'CASE near-mmin donor retained mean mass=',meanmass
  PRINT '(a)', 'PR85 source-form FogDES paired Stokes cases PASS'
END PROGRAM pr85_fogdes_qn_stokes_regression

SUBROUTINE wrf_error_fatal(message)
  CHARACTER(*),INTENT(IN) :: message
  PRINT *, TRIM(message)
  ERROR STOP 1
END SUBROUTINE wrf_error_fatal
