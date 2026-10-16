PROGRAM witness
  USE iso_fortran_env, ONLY: real32,real64,int64
  USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64
  IMPLICIT NONE
  INTEGER,PARAMETER :: ims=0,ime=4,kms=0,kme=0,jms=0,jme=4
  REAL(real32) :: q(ims:ime,kms:kme,jms:jme),b(ims:ime,kms:kme,jms:jme)
  REAL(real32) :: mut(ims:ime,jms:jme),c1(kms:kme),c2(kms:kme)
  REAL(real32) :: ux(ims:ime,jms:jme),uy(ims:ime,jms:jme),vx(ims:ime,jms:jme),vy(ims:ime,jms:jme)
  REAL(real32) :: tx(ims:ime,jms:jme),ty(ims:ime,jms:jme),xk(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: qd(ims:ime,kms:kme,jms:jme),bd(ims:ime,kms:kme,jms:jme)
  REAL(real32) :: vals(4)
  INTEGER :: e(4),t,m,ni(4),nj(4),it,seed_size
  INTEGER, ALLOCATABLE :: seed(:)
  INTEGER(int64) :: qb,bb
  ni=[1,3,2,2]; nj=[2,2,1,3]
  q=0.0_real32; b=0.0_real32; mut=1.0_real32; c1=1.0_real32; c2=0.0_real32
  ux=1.0_real32;uy=1.0_real32;vx=1.0_real32;vy=1.0_real32;tx=1.0_real32;ty=1.0_real32;xk=1.0_real32
  CALL RANDOM_SEED(SIZE=seed_size)
  ALLOCATE(seed(seed_size)); seed=1234567; CALL RANDOM_SEED(PUT=seed)
  DO it=1,2000000
    DO t=1,4
      CALL random_number(vals(t))
      m=1+INT(vals(t)*15000.0_real32)
      CALL random_number(vals(t))
      e(t)=-20+INT(vals(t)*41.0_real32)
      vals(t)=SCALE(REAL(m,real32),e(t)-23)
      b(ni(t),0,nj(t))=vals(t)
      q(ni(t),0,nj(t))=900.0_real32*vals(t)
      IF (REAL(q(ni(t),0,nj(t)),real64)/=900.0_real64*REAL(vals(t),real64)) EXIT
    END DO
    IF (t<=4) CYCLE
    CALL horizontal_diffusion64(q,mut,c1,c2,ux,uy,vx,vy,tx,ty,xk,1.0_real32,1.0_real32, &
      ims,ime,kms,kme,jms,jme,2,2,2,2,0,0,qd)
    CALL horizontal_diffusion64(b,mut,c1,c2,ux,uy,vx,vy,tx,ty,xk,1.0_real32,1.0_real32, &
      ims,ime,kms,kme,jms,jme,2,2,2,2,0,0,bd)
    IF (bd(2,0,2)<=0.0_real64) CYCLE
    IF (qd(2,0,2)>900.0_real64*bd(2,0,2)) THEN
      qb=TRANSFER(qd(2,0,2),qb); bb=TRANSFER(bd(2,0,2),bb)
      WRITE(*,'(A,1X,I0,1X,4(ES25.17E3,1X),4(ES25.17E3,1X),2(ES25.17E3,1X),2(Z16.16,1X))') &
        'WITNESS',it,b(1,0,2),b(3,0,2),b(2,0,1),b(2,0,3),q(1,0,2),q(3,0,2),q(2,0,1),q(2,0,3), &
        qd(2,0,2),bd(2,0,2),qb,bb
      WRITE(*,'(A,1X,8(Z8.8,1X))') 'INPUT_BITS', &
        TRANSFER(b(1,0,2),m),TRANSFER(b(3,0,2),m),TRANSFER(b(2,0,1),m),TRANSFER(b(2,0,3),m), &
        TRANSFER(q(1,0,2),m),TRANSFER(q(3,0,2),m),TRANSFER(q(2,0,1),m),TRANSFER(q(2,0,3),m)
      STOP
    END IF
  END DO
  ERROR STOP 'no witness found'
END PROGRAM
