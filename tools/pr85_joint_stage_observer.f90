! Diagnostic-only snapshots for PR85 Q/N/B stage replay.
! These routines write completed active tiles and never modify model arrays.
SUBROUTINE pr85_joint_stage_dump(stage,itimestep,rkstep, &
     ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
     al,alb,q,qc,qi,qr,qs,qg,nn,nc,ni,nr,bg)
  USE iso_fortran_env, ONLY: real32
  IMPLICIT NONE
  CHARACTER(LEN=*),INTENT(IN) :: stage
  INTEGER,INTENT(IN) :: itimestep,rkstep
  INTEGER,INTENT(IN) :: ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  REAL,INTENT(IN) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: q(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qc(ims:ime,kms:kme,jms:jme),qi(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qr(ims:ime,kms:kme,jms:jme),qs(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qg(ims:ime,kms:kme,jms:jme),nn(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: nc(ims:ime,kms:kme,jms:jme),ni(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: nr(ims:ime,kms:kme,jms:jme),bg(ims:ime,kms:kme,jms:jme)
  REAL(real32),ALLOCATABLE :: dry_density(:,:,:)
  REAL(real32) :: density_value
  INTEGER :: u,i,j,k
  LOGICAL :: density_valid
  CHARACTER(LEN=32) :: label
  EXTERNAL :: pr85_dry_density_from_al_alb,wrf_error_fatal

  IF (its < ims .OR. ite > ime .OR. jts < jms .OR. jte > jme .OR. &
      kts < kms .OR. kte > kme .OR. its > ite .OR. jts > jte .OR. kts > kte) RETURN
  ALLOCATE(dry_density(its:ite,kts:kte,jts:jte))
  DO j=jts,jte
    DO k=kts,kte
      DO i=its,ite
        CALL pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),density_value,density_valid)
        IF (.NOT.density_valid) CALL wrf_error_fatal('PR85 invalid AL+ALB stage density')
        dry_density(i,k,j)=density_value
      END DO
    END DO
  END DO
  label = stage
  OPEN(NEWUNIT=u,FILE='pr85_joint_moment_stages.raw',ACCESS='STREAM', &
       FORM='UNFORMATTED',STATUS='UNKNOWN',POSITION='APPEND',ACTION='WRITE')
  WRITE(u) 'PR85QND2'
  WRITE(u) label
  WRITE(u) 1,itimestep,rkstep,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  WRITE(u) dry_density
  WRITE(u) q(its:ite,kts:kte,jts:jte)
  WRITE(u) qc(its:ite,kts:kte,jts:jte)
  WRITE(u) qi(its:ite,kts:kte,jts:jte)
  WRITE(u) qr(its:ite,kts:kte,jts:jte)
  WRITE(u) qs(its:ite,kts:kte,jts:jte)
  WRITE(u) qg(its:ite,kts:kte,jts:jte)
  WRITE(u) nn(its:ite,kts:kte,jts:jte)
  WRITE(u) nc(its:ite,kts:kte,jts:jte)
  WRITE(u) ni(its:ite,kts:kte,jts:jte)
  WRITE(u) nr(its:ite,kts:kte,jts:jte)
  WRITE(u) bg(its:ite,kts:kte,jts:jte)
  CLOSE(u)
  DEALLOCATE(dry_density)
END SUBROUTINE pr85_joint_stage_dump

SUBROUTINE pr85_dry_density_from_al_alb(al,alb,dry_density,valid)
  USE iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  REAL,INTENT(IN) :: al,alb
  REAL(real32),INTENT(OUT) :: dry_density
  LOGICAL,INTENT(OUT) :: valid
  REAL(real64) :: inverse_density64
  REAL(real32) :: inverse_density32

  valid=.FALSE.
  dry_density=0.0_real32
  IF (.NOT.ieee_is_finite(al) .OR. .NOT.ieee_is_finite(alb)) RETURN
  inverse_density64=REAL(al,real64)+REAL(alb,real64)
  IF (.NOT.ieee_is_finite(inverse_density64) .OR. inverse_density64<=0.0_real64 .OR. &
      inverse_density64>REAL(HUGE(0.0_real32),real64)) RETURN
  inverse_density32=al+alb
  IF (.NOT.ieee_is_finite(inverse_density32) .OR. inverse_density32<=0.0_real32) RETURN
  inverse_density64=1.0_real64/REAL(inverse_density32,real64)
  IF (.NOT.ieee_is_finite(inverse_density64) .OR. &
      inverse_density64>REAL(HUGE(0.0_real32),real64)) RETURN
  dry_density=1.0_real32/inverse_density32
  IF (.NOT.ieee_is_finite(dry_density) .OR. dry_density<=0.0_real32) THEN
    dry_density=0.0_real32
    RETURN
  ENDIF
  valid=.TRUE.
END SUBROUTINE pr85_dry_density_from_al_alb

SUBROUTINE pr85_pbl_tendency_dump(stage,itimestep,rkstep, &
     ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
     qv_tend,qc_tend,qi_tend,qnc_tend,qni_tend)
  IMPLICIT NONE
  CHARACTER(LEN=*),INTENT(IN) :: stage
  INTEGER,INTENT(IN) :: itimestep,rkstep
  INTEGER,INTENT(IN) :: ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  REAL,INTENT(IN) :: qv_tend(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qc_tend(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qi_tend(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qnc_tend(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: qni_tend(ims:ime,kms:kme,jms:jme)
  INTEGER :: u
  CHARACTER(LEN=32) :: label

  IF (its < ims .OR. ite > ime .OR. jts < jms .OR. jte > jme .OR. &
      kts < kms .OR. kte > kme .OR. its > ite .OR. jts > jte .OR. kts > kte) RETURN
  label = stage
  OPEN(NEWUNIT=u,FILE='pr85_joint_moment_stages.raw',ACCESS='STREAM', &
       FORM='UNFORMATTED',STATUS='UNKNOWN',POSITION='APPEND',ACTION='WRITE')
  WRITE(u) 'PR85PLB1'
  WRITE(u) label
  WRITE(u) 2,itimestep,rkstep,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
  WRITE(u) qv_tend(its:ite,kts:kte,jts:jte)
  WRITE(u) qc_tend(its:ite,kts:kte,jts:jte)
  WRITE(u) qi_tend(its:ite,kts:kte,jts:jte)
  WRITE(u) qnc_tend(its:ite,kts:kte,jts:jte)
  WRITE(u) qni_tend(its:ite,kts:kte,jts:jte)
  CLOSE(u)
END SUBROUTINE pr85_pbl_tendency_dump
