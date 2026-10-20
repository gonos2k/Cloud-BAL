PROGRAM pr93_freezing_packet_contract
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  IMPLICIT NONE
  EXTERNAL :: pr85_kdm6_freezing_packet
  INTEGER :: failures
  failures=0
  CALL invalid_active_t24_base()
  CALL valid_t24_fixed_packet_is_deferred()
  CALL valid_zero_packet_is_accepted()
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)', 'PR93 freezing packet contract cases PASS'
CONTAINS
  SUBROUTINE invalid_active_t24_base()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta,cmin,cmax,imin,imax
    LOGICAL :: base_valid,accepted
    rho=0.5360217094421387_real32
    qc=1.3505793504009489e-5_real32; nc=42574184.0_real32
    qi=2.4385062715737149e-6_real32; ni=622.93597412109375_real32
    cmin=523.59881591796875_real64/(500000.0_real64**3)
    cmax=523.59881591796875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      2.1296498102647661e-13_real64,0.50349597749963093_real64, &
      cmin,cmax,imin,imax,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL actual T24 active-ice base must classify invalid atomically'
      failures=failures+1
    ENDIF
  END SUBROUTINE invalid_active_t24_base

  SUBROUTINE valid_t24_fixed_packet_is_deferred()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta,cmin,cmax,imin,imax,mass_request,number_request
    LOGICAL :: base_valid,accepted
    rho=0.5360217094421387_real32
    qc=1.3505793504009489e-5_real32; nc=42574184.0_real32
    qi=0.0_real32; ni=0.0_real32
    mass_request=2.1296498102647661e-13_real64
    number_request=0.50349597749963093_real64
    cmin=523.59881591796875_real64/(500000.0_real64**3)
    cmax=523.59881591796875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    IF (mass_request/REAL(SPACING(qc),real64)>=0.5_real64 .OR. &
        number_request/REAL(SPACING(nc),real64)>=0.5_real64) THEN
      PRINT '(a)', 'FAIL captured request must be below half an ULP at each cloud donor'
      failures=failures+1
      RETURN
    ENDIF
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      mass_request,number_request,cmin,cmax,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL valid T24 donor state must defer the fixed packet unchanged'
      failures=failures+1
    ENDIF
  END SUBROUTINE valid_t24_fixed_packet_is_deferred

  SUBROUTINE valid_zero_packet_is_accepted()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    rho=0.7_real32; qc=1.0e-4_real32; nc=1.0e6_real32
    qi=1.0e-5_real32; ni=1.0e5_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,0.0_real64,0.0_real64, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL valid zero packet must be accepted with unchanged state'
      failures=failures+1
    ENDIF
  END SUBROUTINE valid_zero_packet_is_accepted
END PROGRAM pr93_freezing_packet_contract
