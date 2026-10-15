PROGRAM test_pr85_native_air_operator
  USE iso_fortran_env, ONLY: real32, real64, int32
  USE native_joint_adapter, ONLY: rk_update_joint_moments
  IMPLICIT NONE
  INTEGER,PARAMETER :: ims=1,ime=4,kms=1,kme=2,jms=1,jme=4,nm=5,ns=5
  INTEGER,PARAMETER :: ids=1,ide=5,jds=1,jde=5,kds=1,kde=3
  INTEGER,PARAMETER :: its=1,ite=3,jts=1,jte=3,kts=1,kte=2
  REAL :: q1(ims:ime,kms:kme,jms:jme,nm),q2(ims:ime,kms:kme,jms:jme,nm)
  REAL :: n1(ims:ime,kms:kme,jms:jme,ns),n2(ims:ime,kms:kme,jms:jme,ns)
  REAL :: qt(ims:ime,kms:kme,jms:jme,nm),nt(ims:ime,kms:kme,jms:jme,ns)
  REAL :: ru(ims:ime,kms:kme,jms:jme),rv(ims:ime,kms:kme,jms:jme)
  REAL :: ww(ims:ime,kms:kme,jms:jme),al(ims:ime,kms:kme,jms:jme)
  REAL :: alb(ims:ime,kms:kme,jms:jme)
  REAL :: muold(ims:ime,jms:jme),munew(ims:ime,jms:jme),mub(ims:ime,jms:jme)
  REAL :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
  REAL :: c1(kms:kme),c2(kms:kme),rdnw(kms:kme)
  REAL :: dt,initial_q(4),initial_n(4),density_result,tiny_denominator,next_denominator
  INTEGER,PARAMETER :: qindex(4)=[1,2,3,4], nindex(4)=[1,2,3,4]
  INTEGER :: i,j,k,p
  CHARACTER(LEN=32) :: test_mode
  EXTERNAL :: pr85_joint_stage_dump
  EXTERNAL :: pr85_dry_density_from_al_alb
  LOGICAL :: density_valid

  dt=0.1
  tiny_denominator=TRANSFER(INT(Z'00200000',int32),0.0)
  next_denominator=NEAREST(tiny_denominator,1.0)
  CALL pr85_dry_density_from_al_alb(tiny_denominator,0.0,density_result,density_valid)
  IF (density_valid) ERROR STOP 'unrepresentable reciprocal density was accepted'
  CALL pr85_dry_density_from_al_alb(next_denominator,0.0,density_result,density_valid)
  IF (.NOT.density_valid .OR. .NOT.(density_result>0.0)) &
       ERROR STOP 'next representable denominator was rejected'
  q1=0.0; n1=0.0; qt=0.0; nt=0.0
  q2(:,:,:,1)=1.0e-5; q2(:,:,:,2)=1.0e-5
  q2(:,:,:,3)=1.0e-5; q2(:,:,:,4)=1.0e-4
  q2(:,:,:,5)=1.0e-5
  n2(:,:,:,1)=1.0e7; n2(:,:,:,2)=1.0e7
  n2(:,:,:,3)=1.0e4; n2(:,:,:,4)=1.0e-6
  n2(:,:,:,5)=1.0e7
  initial_q=[1.0e-5,1.0e-5,1.0e-5,1.0e-4]
  initial_n=[1.0e7,1.0e7,1.0e4,1.0e-6]

  ! A 2x2x2 active interior exercises east/west boundary exchange, a
  ! shared north/south face and a shared transformed eta face. With
  ! msftx/=msfty and rdnw<0, paired y/eta fluxes cancel cellwise while the
  ! open x boundaries change the captured column carrier.
  ru=0.0; rv=0.0; ww=0.0
  DO j=2,3
    DO k=1,2
      ru(2,k,j)=0.1
      ru(4,k,j)=0.05
    END DO
  END DO
  DO i=2,3
    rv(i,1,3)=0.05
    rv(i,2,3)=-0.05
  END DO
  DO i=2,3
    ww(i,2,2)=0.1
    ww(i,2,3)=-0.1
  END DO
  muold=10.0; munew=muold; mub=0.0
  msftx=2.0; msfty=0.5; c1=1.0; c2=0.0; rdnw=[-1.0,-1.0]
  ! A dry density of 2 kg m-3 exercises 1/(AL+ALB) in the joint validator.
  test_mode=''
  IF (COMMAND_ARGUMENT_COUNT() > 0) CALL GET_COMMAND_ARGUMENT(1,test_mode)
  IF (COMMAND_ARGUMENT_COUNT() == 0) THEN
    al=-0.25; alb=0.75
  ELSE
    al=0.25; alb=-0.25
  ENDIF
  IF (COMMAND_ARGUMENT_COUNT() == 0 .OR. TRIM(test_mode) == 'invalid-observer') THEN
    CALL pr85_joint_stage_dump('PRE_RK',1,0,ims,ime,jms,jme,kms,kme, &
         its,ite,jts,jte,kts,kte,al,alb,q1(:,:,:,1),q1(:,:,:,1), &
         q1(:,:,:,2),q1(:,:,:,3),q1(:,:,:,4),q2(:,:,:,4), &
         n1(:,:,:,1),n2(:,:,:,1),n1(:,:,:,2),n1(:,:,:,3),n1(:,:,:,4))
  ENDIF
  DO j=2,3
    munew(2,j)=munew(2,j)+dt*0.1
    munew(3,j)=munew(3,j)-dt*0.05
  END DO

  CALL rk_update_joint_moments(q1,q2,n1,n2,qt,nt,nm,ns, &
       qindex,nindex,5,5,ru,rv,ww,muold,munew,mub,c1,c2, &
       msftx,msfty,1.0,1.0,rdnw,al,alb,dt,1,1,1, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
       its,ite,jts,jte,kts,kte)

  DO p=1,4
    IF (ANY(q2(:,:,:,p) /= initial_q(p))) ERROR STOP 'constant Q changed under carrier transport'
    IF (ANY(n2(:,:,:,p) /= initial_n(p))) ERROR STOP 'constant N/B changed under carrier transport'
    IF (ABS(SUM(q2(2:3,1:2,2:3,p)*SPREAD(munew(2:3,2:3),2,2)) - &
            SUM(initial_q(p)*SPREAD(muold(2:3,2:3),2,2)) - &
            dt*4.0*0.05*initial_q(p)) > 1.0e-8) &
         ERROR STOP 'Q boundary transport budget mismatch'
    IF (ABS(SUM(n2(2:3,1:2,2:3,p)*SPREAD(munew(2:3,2:3),2,2)) - &
            SUM(initial_n(p)*SPREAD(muold(2:3,2:3),2,2)) - &
            dt*4.0*0.05*initial_n(p)) > &
            16.0*EPSILON(0.0)*ABS(SUM(initial_n(p)*SPREAD(muold(2:3,2:3),2,2)))) THEN
      PRINT *, 'N_BUDGET',p, &
           SUM(n2(2:3,1:2,2:3,p)*SPREAD(munew(2:3,2:3),2,2)) - &
           SUM(initial_n(p)*SPREAD(muold(2:3,2:3),2,2)), &
           dt*4.0*0.05*initial_n(p), &
           16.0*EPSILON(0.0)*ABS(SUM(initial_n(p)*SPREAD(muold(2:3,2:3),2,2)))
      ERROR STOP 'N/B boundary transport budget mismatch'
    END IF
  END DO
  IF (ANY(q2(:,:,:,5) /= 1.0e-5)) ERROR STOP 'constant snow tracer changed under carrier transport'
  IF (ANY(n2(:,:,:,5) /= 1.0e7)) ERROR STOP 'constant unpaired number tracer changed under carrier transport'
  IF (ABS(SUM(munew(2:3,2:3))-SUM(muold(2:3,2:3))-dt*2.0*0.05) > 1.0e-5) &
       ERROR STOP 'captured dry-carrier boundary budget mismatch'
  PRINT *, 'PR85_NATIVE_AIR_OPERATOR_PASS',dt,SUM(muold(2:3,2:3)),SUM(munew(2:3,2:3))
END PROGRAM test_pr85_native_air_operator

SUBROUTINE wrf_error_fatal(message)
  CHARACTER(*),INTENT(IN) :: message
  PRINT *,TRIM(message)
  ERROR STOP 1
END SUBROUTINE wrf_error_fatal
