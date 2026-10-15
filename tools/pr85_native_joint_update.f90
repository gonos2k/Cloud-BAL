! Contained procedure inserted into the retained module_em research copy.
SUBROUTINE rk_update_joint_moments(q1,q2,n1,n2,qt,nt,nmoist,nscalar,qindex,nindex,qsindex,nnindex, &
     ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,rdx,rdy,rdnw,al,alb,dt,rk,itimestep,spec_zone, &
     ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte)
  USE iso_fortran_env, ONLY: real32,real64
  USE cloud_bal_joint_transport, ONLY: joint_moment_is_valid, joint_qnb_update
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  INTEGER,INTENT(IN) :: nmoist,nscalar,qindex(4),nindex(4),rk,itimestep,spec_zone
  INTEGER,INTENT(IN) :: qsindex,nnindex
  INTEGER,INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme
  INTEGER,INTENT(IN) :: its,ite,jts,jte,kts,kte
  REAL,INTENT(INOUT) :: q1(ims:ime,kms:kme,jms:jme,nmoist),q2(ims:ime,kms:kme,jms:jme,nmoist)
  REAL,INTENT(INOUT) :: n1(ims:ime,kms:kme,jms:jme,nscalar),n2(ims:ime,kms:kme,jms:jme,nscalar)
  REAL,INTENT(IN) :: qt(ims:ime,kms:kme,jms:jme,nmoist),nt(ims:ime,kms:kme,jms:jme,nscalar)
  REAL,INTENT(IN) :: ru(ims:ime,kms:kme,jms:jme),rv(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: ww(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: muold(ims:ime,jms:jme),munew(ims:ime,jms:jme),mub(ims:ime,jms:jme)
  REAL,INTENT(IN) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
  REAL,INTENT(IN) :: c1(kms:kme),c2(kms:kme),rdnw(kms:kme),rdx,rdy,dt
  REAL(real32),ALLOCATABLE :: qb(:,:),nb(:,:),qc(:,:),nc(:,:),qs(:,:),ns(:,:),qa(:,:),na(:,:)
  REAL(real32),ALLOCATABLE :: oldcarrier(:),newcarrier(:),drydensity(:)
  REAL(real32),ALLOCATABLE :: snow_candidate(:),ccn_candidate(:)
  REAL(real64) :: theta,rejected_q(4),rejected_n(4),minmass(4),maxmass(4),rate(2)
  REAL(real64) :: outflow,cfl,maxcfl,weight,source_candidate(2)
  REAL(real32) :: source_stored(2)
  INTEGER :: il,ih,jl,jh,kl,kh,i,j,k,p,cell,cells,u,iq,in,source_failures
  LOGICAL :: feasible,density_valid
  EXTERNAL :: pr85_pbl_tendency_dump,pr85_dry_density_from_al_alb

  ! Current experiment: one specified domain, one tile, no implicit vertical advection.
  ! The outer donor ring remains available; only the first native consumer overlap changes.
  il=MAX(its,ids+1); ih=MIN(ite,ide-2)
  jl=MAX(jts,jds+1); jh=MIN(jte,jde-2)
  kl=MAX(kts,kds); kh=MIN(kte,kde-1)
  IF (ANY(qindex<1).OR.ANY(qindex>nmoist).OR.ANY(nindex<1).OR.ANY(nindex>nscalar)) &
    CALL wrf_error_fatal('PR85 invalid grouped scalar registry slots')
  IF (qsindex<1.OR.qsindex>nmoist.OR.nnindex<1.OR.nnindex>nscalar) &
    CALL wrf_error_fatal('PR85 invalid unpaired scalar registry slots')
  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &
    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')
  IF (rk==1) CALL pr85_pbl_tendency_dump('PRE_GROUPED_PHYSICS_TEND',itimestep,0, &
      ims,ime,jms,jme,kms,kme,il,ih,jl,jh,kl,kh, &
      qt(ims,kms,jms,P_QV),qt(ims,kms,jms,qindex(1)),qt(ims,kms,jms,qindex(2)), &
      nt(ims,kms,jms,nindex(1)),nt(ims,kms,jms,nindex(2)))
  IF (rk==1) THEN
    DO p=1,4
      q1(:,:,:,qindex(p))=q2(:,:,:,qindex(p))
      n1(:,:,:,nindex(p))=n2(:,:,:,nindex(p))
    END DO
    q1(:,:,:,qsindex)=q2(:,:,:,qsindex)
    n1(:,:,:,nnindex)=n2(:,:,:,nnindex)
  END IF
  cells=(ih-il+1)*(jh-jl+1)*(kh-kl+1)
  ALLOCATE(qb(cells,4),nb(cells,4),qc(cells,4),nc(cells,4),qs(cells,4),ns(cells,4), &
           qa(cells,4),na(cells,4),oldcarrier(cells),newcarrier(cells),drydensity(cells))
  ALLOCATE(snow_candidate(cells),ccn_candidate(cells))
  ! Q/N mean particle mass; Q/B is graupel bulk density in kg m-3.
  minmass=[4.188790204786391e-15_real64, &
           1570.79638671875_real64/1820000.0_real64**3, &
           2.930931921716425e-10_real64,100.0_real64]
  maxmass=[3.0300855069345996e-10_real64, &
           1570.79638671875_real64/9080.0_real64**3, &
           1.4159232106169906e-5_real64,900.0_real64]
  cell=0; maxcfl=0.0_real64
  DO j=jl,jh
  DO k=kl,kh
  DO i=il,ih
    cell=cell+1
    oldcarrier(cell)=c1(k)*(muold(i,j)+mub(i,j))+c2(k)
    newcarrier(cell)=c1(k)*(munew(i,j)+mub(i,j))+c2(k)
    CALL pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j), &
                                      drydensity(cell),density_valid)
    IF (.NOT.density_valid) CALL wrf_error_fatal('PR85 invalid AL+ALB dry density')
    IF (.NOT.ieee_is_finite(oldcarrier(cell)).OR.oldcarrier(cell)<=0.0) &
      CALL wrf_error_fatal('PR85 nonpositive old dry carrier')
    outflow=REAL(msftx(i,j)*msfty(i,j)*rdx,real64)* &
      (MAX(REAL(ru(i+1,k,j),real64),0.0_real64)+MAX(-REAL(ru(i,k,j),real64),0.0_real64)) &
      +REAL(msftx(i,j)*msfty(i,j)*rdy,real64)* &
      (MAX(REAL(rv(i,k,j+1),real64),0.0_real64)+MAX(-REAL(rv(i,k,j),real64),0.0_real64))
    ! eta decreases upwards: a positive ww at k+1 enters cell k from above.
    IF (k>kl) outflow=outflow+REAL(msfty(i,j)*(-rdnw(k)),real64)* &
      MAX(REAL(ww(i,k,j),real64),0.0_real64)
    IF (k<kh) outflow=outflow+REAL(msfty(i,j)*(-rdnw(k)),real64)* &
      MAX(-REAL(ww(i,k+1,j),real64),0.0_real64)
    cfl=REAL(dt,real64)*outflow/REAL(oldcarrier(cell),real64)
    maxcfl=MAX(maxcfl,cfl)
    DO p=1,4
      iq=qindex(p); in=nindex(p)
      qb(cell,p)=q1(i,k,j,iq); nb(cell,p)=n1(i,k,j,in)
      qc(cell,p)=q2(i,k,j,iq); nc(cell,p)=n2(i,k,j,in)
      qs(cell,p)=qt(i,k,j,iq); ns(cell,p)=nt(i,k,j,in)
      ! Use one old-time upwind donor map for both moments, not centered scalar fluxes.
      rate=air_tendency(q1(:,:,:,iq),n1(:,:,:,in),i,k,j)
      qa(cell,p)=REAL(rate(1),real32); na(cell,p)=REAL(rate(2),real32)
    END DO
    rate=air_tendency(q1(:,:,:,qsindex),q1(:,:,:,qsindex),i,k,j)
    snow_candidate(cell)=singleton_candidate(q1(i,k,j,qsindex),qt(i,k,j,qsindex),rate(1), &
                                             oldcarrier(cell),newcarrier(cell),drydensity(cell),.FALSE.)
    rate=air_tendency(n1(:,:,:,nnindex),n1(:,:,:,nnindex),i,k,j)
    ccn_candidate(cell)=singleton_candidate(n1(i,k,j,nnindex),nt(i,k,j,nnindex),rate(1), &
                                            oldcarrier(cell),newcarrier(cell),drydensity(cell),.TRUE.)
  END DO
  END DO
  END DO
  IF (.NOT.ieee_is_finite(maxcfl).OR.maxcfl>1.0_real64) &
    CALL wrf_error_fatal('PR85 common donor-cell carrier CFL exceeded')
  CALL joint_qnb_update(qb,nb,qc,nc,qs,ns,qa,na,oldcarrier,newcarrier,drydensity, &
                       dt,minmass,maxmass,theta,rejected_q,rejected_n,feasible)
  OPEN(NEWUNIT=u,FILE='pr85_joint_transport_budget.raw',STATUS='UNKNOWN',POSITION='APPEND')
  WRITE(u,*) 'JOINT_RK',rk,cells,maxcfl,theta,feasible
  WRITE(u,*) 'REJECTED_PRESSURE_COORDINATE_Q',rejected_q
  WRITE(u,*) 'REJECTED_PRESSURE_COORDINATE_MOMENT',rejected_n
  CLOSE(u)
  IF (.NOT.feasible) THEN
    OPEN(NEWUNIT=u,FILE='pr85_joint_source_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')
    cell=0; source_failures=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,4
        IF (.NOT.ieee_is_finite(oldcarrier(cell)).OR.oldcarrier(cell)<=0.0_real32.OR. &
            .NOT.ieee_is_finite(newcarrier(cell)).OR.newcarrier(cell)<=0.0_real32.OR. &
            .NOT.ieee_is_finite(qb(cell,p)).OR..NOT.ieee_is_finite(nb(cell,p)).OR. &
            .NOT.ieee_is_finite(qs(cell,p)).OR..NOT.ieee_is_finite(ns(cell,p)).OR. &
            .NOT.ieee_is_finite(dt)) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE_INVALID_OPERAND',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs(cell,p),ns(cell,p),drydensity(cell),dt
          CYCLE
        END IF
        source_candidate=(REAL(oldcarrier(cell),real64)* &
          [REAL(qb(cell,p),real64),REAL(nb(cell,p),real64)]+REAL(dt,real64)* &
          [REAL(qs(cell,p),real64),REAL(ns(cell,p),real64)])/REAL(newcarrier(cell),real64)
        IF (ANY(.NOT.ieee_is_finite(source_candidate)).OR. &
            ANY(ABS(source_candidate)>REAL(HUGE(0.0_real32),real64))) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE_NOT_STORABLE_R32',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs(cell,p),ns(cell,p),source_candidate,drydensity(cell)
          CYCLE
        END IF
        source_stored=REAL(source_candidate,real32)
        IF (.NOT.joint_moment_is_valid(source_stored(1),source_stored(2),drydensity(cell), &
                                       minmass(p),maxmass(p))) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs(cell,p),ns(cell,p),source_candidate,source_stored,drydensity(cell)
        END IF
      END DO
    END DO
    END DO
    END DO
    WRITE(u,*) 'SOURCE_FAILURE_COUNT',source_failures
    CLOSE(u)
    IF (source_failures>0) &
      CALL wrf_error_fatal('PR85 source-only joint moment state infeasible')
    CALL wrf_error_fatal('PR85 grouped source-plus-transport candidate infeasible')
  END IF
  IF (theta<=0.0_real64) CALL wrf_error_fatal('PR85 refusing zero common air transport')
  IF (theta/=1.0_real64) &
    CALL wrf_error_fatal('PR85 low-order donor map requires a conservative face limiter')
  ! Commit the complete candidate only after all four pair columns pass.
  cell=0
  DO j=jl,jh
  DO k=kl,kh
  DO i=il,ih
    cell=cell+1
    DO p=1,4
      q2(i,k,j,qindex(p))=qc(cell,p)
      n2(i,k,j,nindex(p))=nc(cell,p)
    END DO
    q2(i,k,j,qsindex)=snow_candidate(cell)
    n2(i,k,j,nnindex)=ccn_candidate(cell)
  END DO
  END DO
  END DO
CONTAINS
  FUNCTION singleton_candidate(base,source,transport,oldmass,newmass,density,isnumber) RESULT(stored)
    REAL,INTENT(IN) :: base,source,oldmass,newmass,density
    REAL(real64),INTENT(IN) :: transport
    LOGICAL,INTENT(IN) :: isnumber
    REAL :: stored
    REAL(real64) :: value,product
    IF (.NOT.ieee_is_finite(base).OR..NOT.ieee_is_finite(source).OR. &
        .NOT.ieee_is_finite(newmass).OR.newmass<=0.0) &
      CALL wrf_error_fatal('PR85 invalid unpaired source or dry carrier')
    value=(REAL(oldmass,real64)*REAL(base,real64)+ &
           REAL(dt,real64)*(REAL(source,real64)+transport))/REAL(newmass,real64)
    IF (.NOT.ieee_is_finite(value).OR.value<0.0_real64.OR.value>REAL(HUGE(stored),real64)) &
      CALL wrf_error_fatal('PR85 unpaired completed source/transport state infeasible')
    stored=REAL(value,real32)
    IF (isnumber.AND.stored>0.0) THEN
      product=REAL(stored,real64)*REAL(density,real64)
      IF (.NOT.ieee_is_finite(product).OR.product>REAL(HUGE(stored),real64).OR. &
          product<=0.5_real64*2.0_real64**(-149)) &
        CALL wrf_error_fatal('PR85 ambient number density conversion infeasible')
    END IF
  END FUNCTION singleton_candidate
  FUNCTION air_tendency(mass,moment,i,k,j) RESULT(value)
    REAL,INTENT(IN) :: mass(ims:ime,kms:kme,jms:jme),moment(ims:ime,kms:kme,jms:jme)
    INTEGER,INTENT(IN) :: i,k,j
    REAL(real64) :: value(2),east(2),west(2),north(2),south(2),upper(2),lower(2)
    INTEGER :: donor
    donor=MERGE(i,i+1,ru(i+1,k,j)>=0.0)
    east=REAL(ru(i+1,k,j),real64)*[REAL(mass(donor,k,j),real64),REAL(moment(donor,k,j),real64)]
    donor=MERGE(i-1,i,ru(i,k,j)>=0.0)
    west=REAL(ru(i,k,j),real64)*[REAL(mass(donor,k,j),real64),REAL(moment(donor,k,j),real64)]
    donor=MERGE(j,j+1,rv(i,k,j+1)>=0.0)
    north=REAL(rv(i,k,j+1),real64)*[REAL(mass(i,k,donor),real64),REAL(moment(i,k,donor),real64)]
    donor=MERGE(j-1,j,rv(i,k,j)>=0.0)
    south=REAL(rv(i,k,j),real64)*[REAL(mass(i,k,donor),real64),REAL(moment(i,k,donor),real64)]
    upper=0.0_real64; lower=0.0_real64
    IF (k<kh) THEN
      donor=MERGE(k+1,k,ww(i,k+1,j)>=0.0)
      upper=REAL(ww(i,k+1,j),real64)*[REAL(mass(i,donor,j),real64),REAL(moment(i,donor,j),real64)]
    END IF
    IF (k>kl) THEN
      donor=MERGE(k,k-1,ww(i,k,j)>=0.0)
      lower=REAL(ww(i,k,j),real64)*[REAL(mass(i,donor,j),real64),REAL(moment(i,donor,j),real64)]
    END IF
    value=-REAL(msfty(i,j),real64)*( &
      REAL(msftx(i,j)*rdx,real64)*(east-west)+ &
      REAL(msftx(i,j)*rdy,real64)*(north-south)+REAL(rdnw(k),real64)*(upper-lower))
  END FUNCTION air_tendency
END SUBROUTINE rk_update_joint_moments
