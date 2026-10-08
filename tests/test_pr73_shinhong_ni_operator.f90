PROGRAM test_pr73_shinhong_ni_operator
  USE module_bl_shinhong, ONLY: shinhong
  IMPLICIT NONE
  INTEGER, PARAMETER :: ims=0,ime=2,jms=0,jme=0,kms=1,kme=4
  INTEGER, PARAMETER :: its=1,ite=1,jts=0,jte=0,kts=1,kte=3
  REAL, PARAMETER :: ni_scale=1073741824.0, dt=60.0
  INTEGER :: kpbl(ims:ime,jms:jme), shinhong_tke_diag
  REAL :: u(ims:ime,kms:kme,jms:jme),v(ims:ime,kms:kme,jms:jme)
  REAL :: th(ims:ime,kms:kme,jms:jme),t(ims:ime,kms:kme,jms:jme)
  REAL :: qv(ims:ime,kms:kme,jms:jme),qc(ims:ime,kms:kme,jms:jme)
  REAL :: qi(ims:ime,kms:kme,jms:jme),p(ims:ime,kms:kme,jms:jme)
  REAL :: pi3d(ims:ime,kms:kme,jms:jme),pint(ims:ime,kms:kme,jms:jme)
  REAL :: dz(ims:ime,kms:kme,jms:jme),rub(ims:ime,kms:kme,jms:jme)
  REAL :: rvb(ims:ime,kms:kme,jms:jme),rth(ims:ime,kms:kme,jms:jme)
  REAL :: rqv(ims:ime,kms:kme,jms:jme),rqc(ims:ime,kms:kme,jms:jme)
  REAL :: rqi(ims:ime,kms:kme,jms:jme),rni(ims:ime,kms:kme,jms:jme)
  REAL :: exch(ims:ime,kms:kme,jms:jme),tke(ims:ime,kms:kme,jms:jme)
  REAL :: el(ims:ime,kms:kme,jms:jme),xland(ims:ime,jms:jme)
  REAL :: hfx(ims:ime,jms:jme),qfx(ims:ime,jms:jme),corf(ims:ime,jms:jme)
  REAL :: br(ims:ime,jms:jme),psfc(ims:ime,jms:jme),psim(ims:ime,jms:jme)
  REAL :: psih(ims:ime,jms:jme),u10(ims:ime,jms:jme),v10(ims:ime,jms:jme)
  REAL :: znt(ims:ime,jms:jme),ust(ims:ime,jms:jme),hpbl(ims:ime,jms:jme)
  REAL :: wspd(ims:ime,jms:jme),wstar(ims:ime,jms:jme),delta(ims:ime,jms:jme)
  REAL :: ctopo(ims:ime,jms:jme),ctopo2(ims:ime,jms:jme),regime(ims:ime,jms:jme)
  REAL :: znu(kms:kme),znw(kms:kme),qni(ims:ime,kms:kme,jms:jme)
  REAL :: qnc(ims:ime,kms:kme,jms:jme,1),rnc(ims:ime,kms:kme,jms:jme)
  REAL :: base_qi(ims:ime,kms:kme,jms:jme)
  REAL :: qni_only(ims:ime,kms:kme,jms:jme)
  INTEGER :: k

  u=5.0; v=0.0; th=280.0; t=280.0; qv=0.005
  qc=0.0; qi=0.0
  qc(:,1,:)=2.0e-4; qc(:,2,:)=1.0e-4
  qi(:,1,:)=2.0e-4; qi(:,2,:)=1.0e-4
  p=80000.0; pi3d=1.0; pint=80000.0
  DO k=kms,kme
    p(:,k,:)=95000.0-10000.0*REAL(k-kms)
    pint(:,k,:)=100000.0-10000.0*REAL(k-kms)
    dz(:,k,:)=1000.0
  END DO
  znu=[0.125,0.375,0.625,0.875]; znw=[0.0,0.25,0.50,0.75]
  qni=ni_scale*qi; qnc(:,:,:,1)=ni_scale*qc
  xland=1.0; hfx=100.0; qfx=1.0e-4; corf=1.0e-4; br=0.0
  psfc=100000.0; psim=1.0; psih=1.0; u10=5.0; v10=0.0
  znt=0.1; ust=0.2; hpbl=1000.0; wspd=5.0; wstar=1.0; delta=1.0
  ctopo=0.0; ctopo2=0.0; regime=1.0; exch=0.0; tke=0.1; el=10.0
  rub=0.0; rvb=0.0; rth=0.0; rqv=0.0; rqc=0.0; rqi=0.0; rni=0.0
  shinhong_tke_diag=0
  CALL shinhong(u,v,th,t,qv,qc,qi,p,pint,pi3d,rub,rvb,rth,rqv,rqc,rqi,.TRUE., &
       1004.5,9.81,287.04/1004.5,287.04,9.81,0.608,0.622,0.4,2.5e6,461.5, &
       dz,psfc,znu,znw,10000.0,znt,ust,hpbl,psim,psih,xland,hfx,qfx,wspd,br, &
       60.0,kpbl,exch,u10,v10,shinhong_tke_diag,tke,el,corf,1000.0,1000.0, &
       1,2,0,0,1,4,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ctopo,ctopo2,wstar,delta,regime)
  base_qi=rqi

  rub=0.0; rvb=0.0; rth=0.0; rqv=0.0; rqc=0.0; rqi=0.0; rni=-777.0
  exch=0.0; tke=0.1; el=10.0; u10=5.0; v10=0.0
  znt=0.1; ust=0.2; hpbl=1000.0; wspd=5.0
  CALL shinhong(u,v,th,t,qv,qc,qi,p,pint,pi3d,rub,rvb,rth,rqv,rqc,rqi,.TRUE., &
       1004.5,9.81,287.04/1004.5,287.04,9.81,0.608,0.622,0.4,2.5e6,461.5, &
       dz,psfc,znu,znw,10000.0,znt,ust,hpbl,psim,psih,xland,hfx,qfx,wspd,br, &
       60.0,kpbl,exch,u10,v10,shinhong_tke_diag,tke,el,corf,1000.0,1000.0, &
       1,2,0,0,1,4,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ctopo,ctopo2,wstar,delta,regime,qni_scalar=qni,qni_enabled=.TRUE., &
       p_qni=1,rqniblten=rni)

  IF (MAXVAL(ABS(base_qi(its:ite,kts:kte,jts:jte))) <= 0.0) ERROR STOP 1
  IF (MAXVAL(ABS(rni(its:ite,kts:kte,jts:jte))) <= 0.0) ERROR STOP 2
  IF (MAXVAL(ABS(base_qi(its:ite,kts:kte,jts:jte)-rni(its:ite,kts:kte,jts:jte)/ni_scale)) > &
      2.0*EPSILON(1.0)*MAXVAL(ABS(base_qi(its:ite,kts:kte,jts:jte)))) THEN
    ERROR STOP 3
  END IF
  IF (base_qi(1,3,0) <= 0.0 .OR. rni(1,3,0) <= 0.0) ERROR STOP 5
  IF (MINVAL(qi(its:ite,kts:kte,jts:jte)+dt*base_qi(its:ite,kts:kte,jts:jte)) < 0.0 .OR. &
      MINVAL(qni(its:ite,kts:kte,jts:jte)+dt*rni(its:ite,kts:kte,jts:jte)) < 0.0) ERROR STOP 6
  IF (ANY(rni(0,:,:)/=0.0) .OR. ANY(rni(2,:,:)/=0.0)) ERROR STOP 4
  qni_only=rni

  ! Exercise the fifth channel with both NC and QNI active. The QNI result
  ! must remain the same independent-channel solution as the QI tendency.
  rub=0.0; rvb=0.0; rth=0.0; rqv=0.0; rqc=0.0; rqi=0.0; rni=-777.0; rnc=-777.0
  exch=0.0; tke=0.1; el=10.0; u10=5.0; v10=0.0
  znt=0.1; ust=0.2; hpbl=1000.0; wspd=5.0
  CALL shinhong(u,v,th,t,qv,qc,qi,p,pint,pi3d,rub,rvb,rth,rqv,rqc,rqi,.TRUE., &
       1004.5,9.81,287.04/1004.5,287.04,9.81,0.608,0.622,0.4,2.5e6,461.5, &
       dz,psfc,znu,znw,10000.0,znt,ust,hpbl,psim,psih,xland,hfx,qfx,wspd,br, &
       60.0,kpbl,exch,u10,v10,shinhong_tke_diag,tke,el,corf,1000.0,1000.0, &
       1,2,0,0,1,4,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ctopo,ctopo2,wstar,delta,regime,qnc_scalar=qnc,qnc_enabled=.TRUE., &
       p_qnc=1,rqncblten=rnc,qni_scalar=qni,qni_enabled=.TRUE.,p_qni=1,rqniblten=rni)
  IF (MAXVAL(ABS(rni(its:ite,kts:kte,jts:jte)-qni_only(its:ite,kts:kte,jts:jte))) > 0.0) ERROR STOP 7
  IF (MAXVAL(ABS(rnc(its:ite,kts:kte,jts:jte))) <= 0.0) ERROR STOP 8

  ! A present but disabled optional QNI output is initialized, not stale.
  rub=0.0; rvb=0.0; rth=0.0; rqv=0.0; rqc=0.0; rqi=0.0; rni=-777.0
  exch=0.0; tke=0.1; el=10.0; u10=5.0; v10=0.0
  znt=0.1; ust=0.2; hpbl=1000.0; wspd=5.0
  CALL shinhong(u,v,th,t,qv,qc,qi,p,pint,pi3d,rub,rvb,rth,rqv,rqc,rqi,.TRUE., &
       1004.5,9.81,287.04/1004.5,287.04,9.81,0.608,0.622,0.4,2.5e6,461.5, &
       dz,psfc,znu,znw,10000.0,znt,ust,hpbl,psim,psih,xland,hfx,qfx,wspd,br, &
       60.0,kpbl,exch,u10,v10,shinhong_tke_diag,tke,el,corf,1000.0,1000.0, &
       1,2,0,0,1,4,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ctopo,ctopo2,wstar,delta,regime,qni_scalar=qni,qni_enabled=.FALSE., &
       p_qni=1,rqniblten=rni)
  IF (ANY(rni/=0.0)) ERROR STOP 9

  ! QNI must remain inactive if the paired QI tendency interface is absent.
  rni=-777.0
  CALL call_without_qi_tendency()
  IF (ANY(rni/=0.0)) ERROR STOP 10

  WRITE(*,'(A,1X,ES24.16,1X,ES24.16,1X,ES24.16,1X,ES24.16)') 'PR73_SHINHONG_QNI_SAME_OPERATOR_PASS', &
       MAXVAL(ABS(base_qi(its:ite,kts:kte,jts:jte))), &
       MAXVAL(ABS(base_qi(its:ite,kts:kte,jts:jte)-qni_only(its:ite,kts:kte,jts:jte)/ni_scale)), &
       base_qi(1,3,0),qni_only(1,3,0)/ni_scale
CONTAINS
  SUBROUTINE call_without_qi_tendency()
    rub=0.0; rvb=0.0; rth=0.0; rqv=0.0; rqc=0.0
    exch=0.0; tke=0.1; el=10.0; u10=5.0; v10=0.0
    znt=0.1; ust=0.2; hpbl=1000.0; wspd=5.0
    CALL shinhong(u3d=u,v3d=v,th3d=th,t3d=t,qv3d=qv,qc3d=qc,qi3d=qi, &
         p3d=p,p3di=pint,pi3d=pi3d,rublten=rub,rvblten=rvb,rthblten=rth, &
         rqvblten=rqv,rqcblten=rqc,flag_qi=.TRUE.,cp=1004.5,g=9.81, &
         rovcp=287.04/1004.5,rd=287.04,rovg=9.81,ep1=0.608,ep2=0.622, &
         karman=0.4,xlv=2.5e6,rv=461.5,dz8w=dz,psfc=psfc,znu=znu,znw=znw, &
         p_top=10000.0,znt=znt,ust=ust,hpbl=hpbl,psim=psim,psih=psih, &
         xland=xland,hfx=hfx,qfx=qfx,wspd=wspd,br=br,dt=60.0,kpbl2d=kpbl, &
         exch_h=exch,u10=u10,v10=v10,shinhong_tke_diag=shinhong_tke_diag, &
         tke_pbl=tke,el_pbl=el,corf=corf,dx=1000.0,dy=1000.0, &
         ids=1,ide=2,jds=0,jde=0,kds=1,kde=4,ims=ims,ime=ime,jms=jms,jme=jme, &
         kms=kms,kme=kme,its=its,ite=ite,jts=jts,jte=jte,kts=kts,kte=kte, &
         ctopo=ctopo,ctopo2=ctopo2,wstar=wstar,delta=delta,regime=regime, &
         qni_scalar=qni,qni_enabled=.TRUE.,p_qni=1,rqniblten=rni)
  END SUBROUTINE call_without_qi_tendency
END PROGRAM test_pr73_shinhong_ni_operator
