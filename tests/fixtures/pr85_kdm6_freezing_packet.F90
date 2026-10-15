PROGRAM pr85_kdm6_freezing_packet_regression
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  IMPLICIT NONE
  EXTERNAL :: pr85_kdm6_freezing_packet
  INTEGER :: failures
  failures=0
  CALL captured_pinuc_packet_case()
  CALL captured_subqmin_ice_base_case()
  CALL captured_pfrz_native_inactive_base_case()
  CALL exact_native_ice_threshold_case()
  CALL representable_subqmin_ice_case()
  CALL active_out_of_cone_base_case()
  CALL captured_pfrz_packet_case()
  CALL full_packet_case()
  CALL half_ulp_rounding_case()
  CALL donor_exhaustion_case()
  CALL one_sided_storage_case()
  CALL one_zero_rate_case()
  CALL invalid_base_case()
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)', 'PR85 KDM6 freezing packet cases PASS'
CONTAINS
  SUBROUTINE captured_pinuc_packet_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: dm,dn,ma,na,theta
    LOGICAL :: base_valid,accepted
    rho=0.62613677978515625_real32
    qc=2.2054357038531203e-12_real32; nc=1.2257217168807983_real32
    qi=0.0_real32; ni=0.0_real32
    dm=1.2812267522052399e-24_real64; dn=1.4363748980053650e-10_real64
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,dm,dn, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CALL assert_deferred('captured pinuc',qc,nc,qi,ni,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
  END SUBROUTINE captured_pinuc_packet_case

  SUBROUTINE captured_pfrz_packet_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: dm,dn,ma,na,theta
    LOGICAL :: base_valid,accepted
    rho=0.62613677978515625_real32
    qc=2.2054357038531203e-12_real32; nc=1.2257217168807983_real32
    qi=0.0_real32; ni=0.0_real32
    dm=1.1594365701886628e-27_real64; dn=8.6655794136071709e-14_real64
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,dm,dn, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CALL assert_deferred('captured pfrz',qc,nc,qi,ni,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
  END SUBROUTINE captured_pfrz_packet_case

  SUBROUTINE full_packet_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    rho=0.7_real32; qc=1.0e-4_real32; nc=1.0e6_real32
    qi=1.0e-5_real32; ni=1.0e5_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,1.0e-6_real64, &
      1.0e3_real64,1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=1.0_real64 .OR. &
        qca>=qc .OR. nca>=nc .OR. qia<=qi .OR. nia<=ni) THEN
      PRINT '(a)', 'FAIL full cloud-to-ice packet should commit at theta=1'
      failures=failures+1
    ENDIF
    IF (ABS(ma-1.0e-6_real64)>1.0e-20_real64 .OR. &
        ABS(na-1.0e3_real64)>1.0e-12_real64) THEN
      PRINT '(a)', 'FAIL full packet approvals differ from source proposals'
      failures=failures+1
    ENDIF
  END SUBROUTINE full_packet_case

  SUBROUTINE half_ulp_rounding_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: dm,dn,ma,na,theta,donor_q,receiver_q,donor_n,receiver_n
    REAL(real64) :: qtolerance,ntolerance,qresidual,nresidual
    LOGICAL :: base_valid,accepted
    rho=0.7_real32; qc=1.0e-6_real32; nc=1.0e6_real32
    qi=0.0_real32; ni=0.0_real32
    dm=0.6_real64*REAL(SPACING(qc),real64)
    dn=0.6_real64*REAL(SPACING(nc),real64)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,dm,dn, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=1.0_real64) THEN
      PRINT '(a)', 'FAIL half-ULP source packet should pass endpoint-rounding bounds'
      failures=failures+1
      RETURN
    ENDIF
    donor_q=REAL(qc,real64)-REAL(qca,real64)
    receiver_q=REAL(qia,real64)-REAL(qi,real64)
    donor_n=REAL(nc,real64)-REAL(nca,real64)
    receiver_n=REAL(nia,real64)-REAL(ni,real64)
    qtolerance=0.5_real64*(REAL(SPACING(qc),real64)+REAL(SPACING(qca),real64))+ &
      32.0_real64*EPSILON(0.0_real64)*MAX(ABS(dm),ABS(donor_q),ABS(receiver_q))
    ntolerance=0.5_real64*(REAL(SPACING(nc),real64)+REAL(SPACING(nca),real64))+ &
      32.0_real64*EPSILON(0.0_real64)*MAX(ABS(dn),ABS(donor_n),ABS(receiver_n))
    qresidual=receiver_q-donor_q; nresidual=receiver_n-donor_n
    IF (ABS(donor_q-dm)>qtolerance .OR. ABS(receiver_q-dm)>qtolerance .OR. &
        ABS(donor_n-dn)>ntolerance .OR. ABS(receiver_n-dn)>ntolerance .OR. &
        qresidual==0.0_real64 .OR. nresidual==0.0_real64) THEN
      PRINT '(a)', 'FAIL accepted stored deltas must satisfy and expose endpoint-rounding bounds'
      failures=failures+1
    ENDIF
    PRINT '(a,1p,4e15.7)', 'CASE .6 ULP packet theta / Q / N residual=', &
      theta,qresidual,nresidual,ma
  END SUBROUTINE half_ulp_rounding_case

  SUBROUTINE donor_exhaustion_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    qc=1.0e-4_real32; nc=1.0e6_real32; qi=2.0e-4_real32; ni=2.0e6_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,0.7_real32,0.0_real64, &
      REAL(qc,real64),REAL(nc,real64),1.0e-16_real64,1.0e-8_real64, &
      1.0e-16_real64,1.0e-8_real64,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. qca/=0.0_real32 .OR. &
        nca/=0.0_real32 .OR. qia<=qi .OR. nia<=ni) THEN
      PRINT '(a)', 'FAIL exact donor exhaustion must remain a paired transfer'
      failures=failures+1
    ENDIF
  END SUBROUTINE donor_exhaustion_case

  SUBROUTINE one_sided_storage_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    qc=1.0e-4_real32; nc=1.0e6_real32; qi=0.0_real32; ni=0.0_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,0.7_real32,0.0_real64, &
      1.0e-12_real64,1.0e3_real64,1.0e-16_real64,1.0e-8_real64, &
      1.0e-16_real64,1.0e-8_real64,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CALL assert_deferred('one-sided storage',qc,nc,qi,ni,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
  END SUBROUTINE one_sided_storage_case

  SUBROUTINE one_zero_rate_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    qc=1.0e-4_real32; nc=1.0e6_real32; qi=0.0_real32; ni=0.0_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,0.7_real32,0.0_real64, &
      0.0_real64,1.0e3_real64,1.0e-16_real64,1.0e-8_real64, &
      1.0e-16_real64,1.0e-8_real64,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CALL assert_deferred('number-only proposal',qc,nc,qi,ni,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,0.7_real32,0.0_real64, &
      1.0e-8_real64,0.0_real64,1.0e-16_real64,1.0e-8_real64, &
      1.0e-16_real64,1.0e-8_real64,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CALL assert_deferred('mass-only proposal',qc,nc,qi,ni,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
  END SUBROUTINE one_zero_rate_case

  SUBROUTINE invalid_base_case()
    REAL(real32) :: qca,nca,qia,nia
    REAL(real64) :: ma,na,theta
    LOGICAL :: base_valid,accepted
    CALL pr85_kdm6_freezing_packet(1.0e-4_real32,1.0e6_real32, &
      1.0e-8_real32,0.0_real32,0.7_real32,0.0_real64,1.0e-8_real64,1.0e2_real64, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted .OR. qca/=1.0e-4_real32 .OR. &
        nca/=1.0e6_real32 .OR. qia/=1.0e-8_real32 .OR. nia/=0.0_real32) THEN
      PRINT '(a)', 'FAIL invalid preexisting pair must reject atomically'
      failures=failures+1
    ENDIF
    CALL pr85_kdm6_freezing_packet(1.0e-4_real32,1.0e6_real32,0.0_real32, &
      0.0_real32,0.7_real32,0.0_real64,ieee_value(0.0_real64,ieee_quiet_nan),1.0_real64, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,1.0e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted) THEN
      PRINT '(a)', 'FAIL nonfinite source proposal must reject'
      failures=failures+1
    ENDIF
    CALL pr85_kdm6_freezing_packet(1.0e-4_real32,1.0e6_real32,0.0_real32, &
      0.0_real32,0.7_real32,0.0_real64,1.0e-8_real64,1.0e2_real64,1.0e-300_real64, &
      1.0e300_real64,1.0e-16_real64,1.0e-8_real64,qca,nca,qia,nia, &
      ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted .OR. qca/=1.0e-4_real32 .OR. &
        nca/=1.0e6_real32 .OR. qia/=0.0_real32 .OR. nia/=0.0_real32) THEN
      PRINT '(a)', 'FAIL bounds outside normal REAL32 range must reject atomically'
      failures=failures+1
    ENDIF
  END SUBROUTINE invalid_base_case

  SUBROUTINE captured_subqmin_ice_base_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: dm,dn,ma,na,theta,cmin,cmax,imin,imax,mean_ice
    LOGICAL :: base_valid,accepted
    rho=0.7585625052452087_real32
    qc=1.8711555749177933e-3_real32; nc=4.83592416e8_real32
    qi=9.8972120587300359e-17_real32; ni=2.4629827066746657e-8_real32
    dm=1.7025567476387644e-12_real64; dn=3.3001345363070966e-1_real64
    cmin=1570.79638671875_real64/(500000.0_real64**3)
    cmax=1570.79638671875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    mean_ice=REAL(rho,real64)*REAL(qi,real64)/REAL(ni,real64)
    IF (qi>=1.0e-15_real32 .OR. mean_ice<=imax) THEN
      PRINT '(a)', 'FAIL captured transient base must be below qmin and outside the active ice cone'
      failures=failures+1
      RETURN
    ENDIF
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,1.0e-15_real64,dm,dn, &
      cmin,cmax,imin,imax,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. accepted .OR. qca/=qc .OR. nca/=nc .OR. &
        qia/=qi .OR. nia/=ni .OR. theta/=0.0_real64 .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL actual tiny PINU packet must be deferred when cloud-N loss is below one REAL32 ULP'
      failures=failures+1
    ENDIF
    PRINT '(a,1p,4e15.7)', 'CASE captured sub-qmin base rho / mean before / request N / alpha=', &
      rho,REAL(rho,real64)*REAL(qi,real64)/REAL(ni,real64),dn,theta
  END SUBROUTINE captured_subqmin_ice_base_case


  SUBROUTINE captured_pfrz_native_inactive_base_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: dm,dn,ma,na,theta,cmin,cmax,imin,imax,mean_before,mean_after
    LOGICAL :: base_valid,accepted
    rho=0.7712181806564331_real32
    qc=1.9647495355457067e-3_real32; nc=4.99515872e8_real32
    qi=1.2412583862906864e-15_real32; ni=2.3417695160787844e-7_real32
    dm=3.5026431601898292e-14_real64; dn=4.4525542481649461e-3_real64
    cmin=1570.79638671875_real64/(500000.0_real64**3)
    cmax=1570.79638671875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    mean_before=REAL(rho,real64)*REAL(qi,real64)/REAL(ni,real64)
    IF (qi<=1.0e-15_real32 .OR. qi>=1.0e-14_real32 .OR. mean_before<=imax) THEN
      PRINT '(a)', 'FAIL captured PFRZ base must be above qmin, below native gate, and outside ice cone'
      failures=failures+1
      RETURN
    ENDIF
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho, &
      DBLE(NEAREST(1.e-14,-1.0)),dm,dn,cmin,cmax,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL captured sub-1e-14 PFRZ base should be admitted then packet deferred atomically'
      failures=failures+1
      RETURN
    ENDIF
    mean_after=REAL(rho,real64)*REAL(qia,real64)/REAL(nia,real64)
    IF (mean_after<=imax) THEN
      PRINT '(a)', 'FAIL captured inactive base must remain distinguishable from a strict PSD endpoint'
      failures=failures+1
    ENDIF
    PRINT '(a,1p,4e15.7)', 'CASE captured native-inactive PFRZ rho / mean before / unchanged mean / theta=', &
      rho,mean_before,mean_after,theta
  END SUBROUTINE captured_pfrz_native_inactive_base_case

  SUBROUTINE exact_native_ice_threshold_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta,imax
    LOGICAL :: base_valid,accepted
    rho=0.7712181806564331_real32
    qc=1.0e-4_real32; nc=1.0e6_real32
    qi=1.0e-14_real32; ni=REAL(rho,real64)*REAL(qi,real64)/2.2e-9_real64
    imax=1570.79638671875_real64/(9080.0_real64**3)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho, &
      DBLE(NEAREST(1.e-14,-1.0)),1.0e-12_real64,1.0e2_real64, &
      1.0e-16_real64,1.0e-8_real64,1.0e-16_real64,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted .OR. qca/=qc .OR. nca/=nc .OR. &
        qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL exact native 1.e-14 threshold is active and must reject an out-of-cone base'
      failures=failures+1
    ENDIF
  END SUBROUTINE exact_native_ice_threshold_case

  SUBROUTINE representable_subqmin_ice_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta,cmin,cmax,imin,imax,mean_ice
    LOGICAL :: base_valid,accepted
    rho=0.7_real32
    qc=1.0e-4_real32; nc=1.0e6_real32
    qi=1.0e-16_real32; ni=REAL(rho,real64)*REAL(qi,real64)/3.0e-9_real64
    cmin=1570.79638671875_real64/(500000.0_real64**3)
    cmax=1570.79638671875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,1.0e-15_real64, &
      2.0e-11_real64,2000.0_real64,cmin,cmax,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. qca>=qc .OR. nca>=nc .OR. &
        qia<=qi .OR. nia<=ni .OR. theta/=1.0_real64) THEN
      PRINT '(a)', 'FAIL representable sub-qmin ice transition should commit at strict endpoints'
      failures=failures+1
      RETURN
    ENDIF
    mean_ice=REAL(rho,real64)*REAL(qia,real64)/REAL(nia,real64)
    IF (mean_ice<imin .OR. mean_ice>imax) THEN
      PRINT '(a)', 'FAIL accepted transient-base endpoint must satisfy strict ice mass bounds'
      failures=failures+1
    ENDIF
    PRINT '(a,1p,4e15.7)', 'CASE representable sub-qmin base rho / mean before / mean after / theta=', &
      rho,REAL(rho,real64)*REAL(qi,real64)/REAL(ni,real64),mean_ice,theta
  END SUBROUTINE representable_subqmin_ice_case

  SUBROUTINE active_out_of_cone_base_case()
    REAL(real32) :: qc,nc,qi,ni,qca,nca,qia,nia,rho
    REAL(real64) :: ma,na,theta,cmin,cmax,imin,imax
    LOGICAL :: base_valid,accepted
    rho=0.7585625052452087_real32
    qc=1.0e-4_real32; nc=1.0e6_real32
    qi=2.0e-14_real32; ni=REAL(rho,real64)*REAL(qi,real64)/2.2e-9_real64
    cmin=1570.79638671875_real64/(500000.0_real64**3)
    cmax=1570.79638671875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho, &
      DBLE(NEAREST(1.e-14,-1.0)), &
      1.0e-12_real64,1.0e3_real64,cmin,cmax,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted .OR. qca/=qc .OR. nca/=nc .OR. &
        qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) THEN
      PRINT '(a)', 'FAIL active out-of-cone ice base must reject atomically'
      failures=failures+1
    ENDIF
  END SUBROUTINE active_out_of_cone_base_case

  SUBROUTINE assert_deferred(label,qc,nc,qi,ni,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    CHARACTER(*), INTENT(IN) :: label
    REAL(real32), INTENT(IN) :: qc,nc,qi,ni,qca,nca,qia,nia
    REAL(real64), INTENT(IN) :: ma,na,theta
    LOGICAL, INTENT(IN) :: base_valid,accepted
    IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        ma/=0.0_real64 .OR. na/=0.0_real64 .OR. qca/=qc .OR. &
        nca/=nc .OR. qia/=qi .OR. nia/=ni) THEN
      PRINT '(a,1x,a)', 'FAIL packet should be deferred atomically:',label
      failures=failures+1
    ENDIF
  END SUBROUTINE assert_deferred
END PROGRAM pr85_kdm6_freezing_packet_regression
