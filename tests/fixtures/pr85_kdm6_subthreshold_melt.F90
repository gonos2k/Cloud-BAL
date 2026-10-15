PROGRAM pr85_kdm6_subthreshold_melt_regression
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  IMPLICIT NONE
  EXTERNAL :: pr85_kdm6_subthreshold_melt
  INTEGER :: failures
  failures=0
  CALL captured_underflow_case()
  CALL rain_route_case()
  CALL unsupported_case()
  CALL invalid_input_case()
  CALL unpaired_existing_case()
  IF (failures/=0) ERROR STOP 1
  PRINT '(a)', 'PR85 KDM6 subthreshold melt cases PASS'
CONTAINS
  SUBROUTINE captured_underflow_case()
    REAL(real32) :: qc,nc,qr,nr,qca,nca,qra,nra,rho,dz,qmelt,mbar
    REAL(real32) :: cms,g1pdsms,g1pms,rsloped
    REAL(real64) :: requested_n,stored_mass_delta,stored_number_delta
    INTEGER :: route
    LOGICAL :: accepted
    rho=0.7227509617805481_real32; dz=303.97412109375_real32
    qmelt=1.9782829888126408e-12_real32
    cms=52.35987854_real32; g1pdsms=6.0_real32; g1pms=1.0_real32
    rsloped=1.7146776471866460e-16_real32
    mbar=cms*(g1pdsms/g1pms)*rsloped
    qc=0.0_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
    CALL pr85_kdm6_subthreshold_melt(qc,nc,qr,nr,rho,dz,qmelt,mbar, &
         4.18879e-15_real32,3.0300855e-10_real32, &
         2.9309319217e-10_real32,1.4159232106e-5_real32, &
         qca,nca,qra,nra,requested_n,route,accepted)
    IF (.NOT.accepted .OR. route/=1 .OR. qca<=0.0_real32 .OR. nca<=0.0_real32) THEN
      PRINT '(a)', 'FAIL captured underflow source should route an atomic cloud pair'
      failures=failures+1
      RETURN
    ENDIF
    IF (qra/=qr .OR. nra/=nr .OR. ABS(qca-qmelt)>2.0e-19_real32) THEN
      PRINT '(a,4(es14.6,1x))', 'FAIL captured underflow liquid target ',qca,nca,qra,nra
      failures=failures+1
    ENDIF
    IF (ABS(requested_n-26.5426779343_real64)>1.0e-5_real64) THEN
      PRINT '(a,1p,e15.7)', 'FAIL source-normalized N differs from captured dry-carrier result: ',requested_n
      failures=failures+1
    ENDIF
    IF (ABS(REAL(rho,real64)*REAL(qca-qc,real64)*REAL(dz,real64)- &
        REAL(rho,real64)*REAL(qmelt,real64)*REAL(dz,real64))>1.0e-18_real64) THEN
      PRINT '(a)', 'FAIL captured underflow stored mass increment differs from proposal'
      failures=failures+1
    ENDIF
    stored_mass_delta=REAL(rho,real64)*REAL(qca-qc,real64)*REAL(dz,real64)
    stored_number_delta=REAL(nca-nc,real64)*REAL(dz,real64)
    IF (ABS(stored_mass_delta-REAL(rho,real64)*REAL(qmelt,real64)*REAL(dz,real64))>1.0e-18_real64 .OR. &
        ABS(stored_number_delta-requested_n*REAL(dz,real64))>1.0e-3_real64) THEN
      PRINT '(a)', 'FAIL captured underflow stored deltas / R32 residual accounting'
      failures=failures+1
    ENDIF
    PRINT '(a,1p,6e15.7)', 'CASE captured_underflow route, proposedN, QC/NC, QR/NR=', &
      REAL(route,real64),requested_n,REAL(qca,real64),REAL(nca,real64), &
      REAL(qra,real64),REAL(nra,real64)
  END SUBROUTINE captured_underflow_case

  SUBROUTINE rain_route_case()
    REAL(real32) :: qc,nc,qr,nr,qca,nca,qra,nra
    REAL(real64) :: requested_n
    INTEGER :: route
    LOGICAL :: accepted
    qc=0.0_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
    CALL pr85_kdm6_subthreshold_melt(qc,nc,qr,nr,0.95_real32,100.0_real32, &
         1.0e-9_real32,1.0e-6_real32,4.18879e-15_real32,3.0300855e-10_real32, &
         2.9309319217e-10_real32,1.4159232106e-5_real32, &
         qca,nca,qra,nra,requested_n,route,accepted)
    IF (.NOT.accepted .OR. route/=2 .OR. qra<=0.0_real32 .OR. nra<=0.0_real32 .OR. &
        qca/=qc .OR. nca/=nc) THEN
      PRINT '(a)', 'FAIL source particle mean supported by rain should route rain pair'
      failures=failures+1
    ENDIF
  END SUBROUTINE rain_route_case

  SUBROUTINE unsupported_case()
    REAL(real32) :: qc,nc,qr,nr,qca,nca,qra,nra
    REAL(real64) :: requested_n
    INTEGER :: route
    LOGICAL :: accepted
    qc=0.0_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
    CALL pr85_kdm6_subthreshold_melt(qc,nc,qr,nr,0.95_real32,100.0_real32, &
         1.0e-9_real32,2.0e-5_real32,4.18879e-15_real32,3.0300855e-10_real32, &
         2.9309319217e-10_real32,1.4159232106e-5_real32, &
         qca,nca,qra,nra,requested_n,route,accepted)
    IF (accepted .OR. route/=0 .OR. requested_n<=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qra/=qr .OR. nra/=nr) THEN
      PRINT '(a)', 'FAIL unsupported source mean must withhold the complete melt pair'
      failures=failures+1
    ENDIF
  END SUBROUTINE unsupported_case

  SUBROUTINE invalid_input_case()
    REAL(real32) :: qc,nc,qr,nr,qca,nca,qra,nra
    REAL(real64) :: requested_n
    INTEGER :: route
    LOGICAL :: accepted
    qc=0.0_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
    CALL pr85_kdm6_subthreshold_melt(qc,nc,qr,nr,0.95_real32,100.0_real32, &
         1.0e-9_real32,ieee_value(0.0_real32,ieee_quiet_nan), &
         4.18879e-15_real32,3.0300855e-10_real32,2.9309319217e-10_real32, &
         1.4159232106e-5_real32,qca,nca,qra,nra,requested_n,route,accepted)
    IF (accepted .OR. route/=0 .OR. qca/=qc .OR. nca/=nc .OR. qra/=qr .OR. nra/=nr) THEN
      PRINT '(a)', 'FAIL nonfinite melt PSD operand must reject atomically'
      failures=failures+1
    ENDIF
  END SUBROUTINE invalid_input_case

  SUBROUTINE unpaired_existing_case()
    REAL(real32) :: qc,nc,qr,nr,qca,nca,qra,nra
    REAL(real64) :: requested_n
    INTEGER :: route
    LOGICAL :: accepted
    qc=1.0e-4_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
    CALL pr85_kdm6_subthreshold_melt(qc,nc,qr,nr,0.95_real32,100.0_real32, &
         1.0e-9_real32,5.3868e-14_real32,4.18879e-15_real32,3.0300855e-10_real32, &
         2.9309319217e-10_real32,1.4159232106e-5_real32, &
         qca,nca,qra,nra,requested_n,route,accepted)
    IF (accepted .OR. qca/=qc .OR. nca/=nc .OR. qra/=qr .OR. nra/=nr) THEN
      PRINT '(a)', 'FAIL invalid preexisting liquid pair must reject atomically'
      failures=failures+1
    ENDIF
  END SUBROUTINE unpaired_existing_case
END PROGRAM pr85_kdm6_subthreshold_melt_regression
