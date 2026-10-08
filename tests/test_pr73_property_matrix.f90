PROGRAM test_pr73_property_matrix
  USE module_mp_kdm6, ONLY: kdm6, kdm6init, fpvs
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  REAL, PARAMETER :: pi=ACOS(-1.0), cloud_q=2.0e-4, cloud_lambda=1.0e5
  REAL, PARAMETER :: ice_q=2.0e-5, ice_lambda=2.0e4, rain_q=1.0e-4, rain_lambda=5.0e3
  REAL, PARAMETER :: graupel_q=2.0e-5, graupel_b=5.0e-8
  REAL, PARAMETER :: nr0=rain_q*rain_lambda**3/((pi*1000.0/6.0)*24.0)
  REAL, PARAMETER :: nc0=cloud_q*cloud_lambda**3/(pi*1000.0/6.0)
  REAL, PARAMETER :: ni0=ice_q*ice_lambda**3/((pi*500.0/6.0)*6.0)
  REAL :: th(0:4,1:1,0:0), q(0:4,1:1,0:0), qc(0:4,1:1,0:0)
  REAL :: qr(0:4,1:1,0:0), qi(0:4,1:1,0:0), qs(0:4,1:1,0:0), qg(0:4,1:1,0:0)
  REAL :: nn(0:4,1:1,0:0), nc(0:4,1:1,0:0), ni(0:4,1:1,0:0), nr(0:4,1:1,0:0)
  REAL :: bg(0:4,1:1,0:0), diag_rhog(0:4,1:1,0:0), den(0:4,1:1,0:0)
  REAL :: pii(0:4,1:1,0:0), p(0:4,1:1,0:0), delz(0:4,1:1,0:0)
  REAL :: xland(0:4,0:0), rain(0:4,0:0), rainncv(0:4,0:0), snow(0:4,0:0)
  REAL :: snowncv(0:4,0:0), sr(0:4,0:0), graupel(0:4,0:0), graupelncv(0:4,0:0)
  REAL :: refl(0:4,1:1,0:0), re_cloud(0:4,1:1,0:0), re_ice(0:4,1:1,0:0), re_snow(0:4,1:1,0:0)
  REAL :: props(52), reference(0:15,52), vapor_sat, es
  INTEGER :: mask

  es=fpvs(280.0,1,287.04,461.5,1846.4,4190.0,1846.4,2.5e6,2.834e6,610.78,273.15)
  vapor_sat=0.8*0.622*es/(90000.0-es)
  xam_g=pi*500.0/6.0
  CALL kdm6init(1.28,1000.0,100.0,4190.0,1846.4,1.0e8,0,.FALSE.)

  DO mask=0,15
    CALL run_mask(mask)
    CALL read_properties(props)
    CALL check_properties(mask,props)
    reference(mask,:)=props
    WRITE(*,*) 'PR73_REFERENCE_MASK',mask,props
  END DO
  IF (reference(0,3)==reference(2,3)) ERROR STOP 22
  IF (reference(0,8)==reference(1,8)) ERROR STOP 23
  IF (reference(0,11)==reference(4,11)) ERROR STOP 24
  IF (reference(0,10)==reference(8,10)) ERROR STOP 25

  ! Each target is run after an all-active call in the same process. Every
  ! public output/history array is poisoned before the target invocation.
  DO mask=0,15
    CALL run_mask(15)
    CALL read_properties(props)
    CALL run_mask(mask)
    CALL read_properties(props)
    IF (ANY(props/=reference(mask,:))) ERROR STOP 11
    CALL check_properties(mask,props)
    WRITE(*,*) 'PR73_REENTRY_MASK',mask,props
  END DO
  WRITE(*,'(A)') 'PR73_ACTUAL_KDM6_PROPERTY_MATRIX PASS'

CONTAINS

  SUBROUTINE run_mask(state_mask)
    INTEGER, INTENT(IN) :: state_mask
    INTEGER :: i
    REAL :: temp_k

    temp_k=280.0
    th=temp_k; q=vapor_sat; qc=0.0; qr=0.0; qi=0.0; qs=0.0; qg=0.0
    nn=5.0e8; nc=0.0; ni=0.0; nr=0.0; bg=0.0
    IF (BTEST(state_mask,1)) THEN
      qc(1:3,1,0)=cloud_q
      nc(1:3,1,0)=nc0
    END IF
    IF (BTEST(state_mask,2)) THEN
      qi(1:3,1,0)=ice_q
      ni(1:3,1,0)=ni0
    END IF
    IF (BTEST(state_mask,0)) THEN
      qr(1:3,1,0)=rain_q
      nr(1:3,1,0)=nr0
    END IF
    IF (BTEST(state_mask,3)) THEN
      qg(1:3,1,0)=graupel_q
      bg(1:3,1,0)=graupel_b
    END IF
    diag_rhog=-777.0; den=999.0; den(1:3,1,0)=1.0; pii=1.0
    p=90000.0; delz=100.0; xland=1.0
    rain=-777.0; rainncv=-777.0; snow=-777.0; snowncv=-777.0; sr=-777.0
    graupel=-777.0; graupelncv=-777.0; refl=-777.0; re_cloud=-777.0; re_ice=-777.0; re_snow=-777.0
    BLOCK
      LOGICAL :: capture_exists
      INQUIRE(FILE='pr73_property_capture.dat',EXIST=capture_exists)
      IF (capture_exists) THEN
        OPEN(UNIT=98,FILE='pr73_property_capture.dat',STATUS='OLD')
        CLOSE(98,STATUS='DELETE')
      END IF
    END BLOCK
    CALL kdm6(TH=th,Q=q,QC=qc,QR=qr,QI=qi,QS=qs,QG=qg,NN=nn,NC=nc,NI=ni,NR=nr,BG=bg, &
         DIAG_RHOG=diag_rhog,DEN=den,PII=pii,P=p,DELZ=delz,DELT=1.0,G=9.81,CPD=1004.5, &
         CPV=1846.4,CCN0=1.0e8,RD=287.04,RV=461.5,T0C=273.15,EP1=0.608,EP2=0.622, &
         QMIN=1.0e-12,XLS=2.834e6,XLV0=2.5e6,XLF0=3.34e5,DEN0=1.28,DENR=1000.0, &
         SCALE_H=0.0,QNN_LAND_MULT=1.0,QNN_SEA_MULT=1.0,NCMIN_LAND=10.0,NCMIN_SEA=10.0, &
         CLIQ=4190.0,CICE=1846.4,PSAT=610.78,XLAND=xland,RAIN=rain,RAINNCV=rainncv, &
         SNOW=snow,SNOWNCV=snowncv,SR=sr,REFL_10CM=refl,DIAGFLAG=.FALSE.,DO_RADAR_REF=0, &
         GRAUPEL=graupel,GRAUPELNCV=graupelncv,ITIMESTEP=2,HAS_REQC=1,HAS_REQI=1,HAS_REQS=1, &
         RE_CLOUD=re_cloud,RE_ICE=re_ice,RE_SNOW=re_snow,IDS=1,IDE=3,JDS=0,JDE=0,KDS=1,KDE=1, &
         IMS=0,IME=4,JMS=0,JME=0,KMS=1,KME=1,ITS=1,ITE=3,JTS=0,JTE=0,KTS=1,KTE=1)
  END SUBROUTINE run_mask

  SUBROUTINE read_properties(values)
    REAL, INTENT(OUT) :: values(52)
    OPEN(UNIT=98,FILE='pr73_property_capture.dat',STATUS='OLD',ACTION='READ')
    READ(98,*) values
    CLOSE(98)
    IF (.NOT.ALL(ieee_is_finite(values))) ERROR STOP 12
  END SUBROUTINE read_properties

  SUBROUTINE check_properties(state_mask,values)
    INTEGER, INTENT(IN) :: state_mask
    REAL, INTENT(IN) :: values(52)
    IF (NINT(values(43))/=MERGE(2,0,BTEST(state_mask,3))) ERROR STOP 13
    IF (BTEST(state_mask,1)) THEN
      IF (values(3)<=0.0) ERROR STOP 14
    ELSE IF (values(3)<=0.0) THEN
      ERROR STOP 15
    END IF
    IF (BTEST(state_mask,0)) THEN
      IF (values(8)<=0.0) ERROR STOP 16
    ELSE IF (values(36)/=0.0) THEN
      ERROR STOP 17
    END IF
    IF (BTEST(state_mask,2)) THEN
      IF (ABS(values(35)-4.0*values(37))>1.0e-5*MAX(1.0,ABS(values(35)))) ERROR STOP 18
    ELSE IF (values(35)/=0.0 .OR. values(37)/=0.0) THEN
      ERROR STOP 19
    END IF
    IF (BTEST(state_mask,3)) THEN
      IF (ABS(values(38)-400.0)>1.0e-3) ERROR STOP 20
    ELSE IF (values(38)/=0.0 .OR. values(34)/=0.0) THEN
      ERROR STOP 21
    END IF
  END SUBROUTINE check_properties

END PROGRAM test_pr73_property_matrix
