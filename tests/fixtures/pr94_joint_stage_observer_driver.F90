PROGRAM pr94_joint_stage_observer_driver
  USE iso_fortran_env, ONLY: real32
  IMPLICIT NONE
  INTEGER, PARAMETER :: NX=2, NK=2, NJ=2
  REAL(real32) :: al(NX,NK,NJ), alb(NX,NK,NJ)
  REAL(real32) :: q(NX,NK,NJ), qc(NX,NK,NJ), qi(NX,NK,NJ)
  REAL(real32) :: qr(NX,NK,NJ), qs(NX,NK,NJ), qg(NX,NK,NJ)
  REAL(real32) :: nn(NX,NK,NJ), nc(NX,NK,NJ), ni(NX,NK,NJ)
  REAL(real32) :: nr(NX,NK,NJ), bg(NX,NK,NJ)
  REAL(real32) :: tendencies(NX,NK,NJ)
  CHARACTER(LEN=32), PARAMETER :: labels(6) = [CHARACTER(LEN=32) :: &
       'PRE_RK', 'RK_STAGE_END', 'RK_STAGE_END', 'RK_STAGE_END', &
       'PRE_KDM6', 'POST_KDM6']
  CHARACTER(LEN=16) :: mode
  INTEGER :: step, stage, rkstep
  EXTERNAL :: pr85_joint_stage_dump, pr85_pbl_tendency_dump

  CALL GET_COMMAND_ARGUMENT(1, mode)
  al = 0.001_real32
  alb = 0.999_real32
  q = 0.001_real32
  qc = 0.002_real32
  qi = 0.003_real32
  qr = 0.004_real32
  qs = 0.005_real32
  qg = 0.006_real32
  nn = 1.0_real32
  nc = 2.0_real32
  ni = 3.0_real32
  nr = 4.0_real32
  bg = 5.0_real32
  tendencies = 6.0_real32
  IF (TRIM(mode) == 'bad-density') al = -2.0_real32

  DO step=1,180
    DO stage=1,SIZE(labels)
      rkstep = 0
      IF (stage >= 2 .AND. stage <= 4) rkstep = stage - 1
      CALL pr85_joint_stage_dump(TRIM(labels(stage)),step,rkstep, &
           1,NX,1,NJ,1,NK,1,NX,1,NJ,1,NK, &
           al,alb,q,qc,qi,qr,qs,qg,nn,nc,ni,nr,bg)
    END DO
    CALL pr85_pbl_tendency_dump('POST_PBL_TEND',step,1, &
         1,NX,1,NJ,1,NK,1,NX,1,NJ,1,NK, &
         tendencies,tendencies,tendencies,tendencies,tendencies)
  END DO
END PROGRAM pr94_joint_stage_observer_driver

SUBROUTINE wrf_error_fatal(message)
  IMPLICIT NONE
  CHARACTER(LEN=*), INTENT(IN) :: message
  WRITE(*,'(A)') TRIM(message)
  ERROR STOP 7
END SUBROUTINE wrf_error_fatal
