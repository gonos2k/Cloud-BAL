PROGRAM test_phase_moments
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: apply_water_phase_transfer
  USE cloud_bal_phase_moments, ONLY: evaporate_cloud_completely,melt_graupel_proportionally
  IMPLICIT NONE
  REAL(real64) :: s(6),expected(6),delta(6),t,te,nn,nc,bg,old(6),to,oldbg
  INTEGER :: status

  s=[0.01_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
  expected=s; t=280.0_real64; te=t; nn=20.0_real64; nc=80.0_real64
  delta=0.0_real64; delta(1)=s(2); delta(2)=-s(2)
  CALL apply_water_phase_transfer(te,expected,delta,status)
  IF (status/=STATUS_OK) ERROR STOP 'evaporation oracle transfer'
  CALL evaporate_cloud_completely(t,s,nn,nc,status)
  IF (status/=STATUS_OK .OR. ANY(s/=expected) .OR. t/=te) ERROR STOP 'evaporation transfer'
  IF (nc/=0.0_real64 .OR. nn/=100.0_real64) ERROR STOP 'evaporation moments'

  s=[0.01_real64,0.0_real64,0.0_real64,0.001_real64,0.0_real64,0.002_real64]
  expected=s; t=280.0_real64; te=t; bg=0.00001_real64
  delta=0.0_real64; delta(4)=0.0005_real64; delta(6)=-delta(4)
  CALL apply_water_phase_transfer(te,expected,delta,status)
  IF (status/=STATUS_OK) ERROR STOP 'melt oracle transfer'
  CALL melt_graupel_proportionally(t,s,bg,delta(4),status)
  IF (status/=STATUS_OK .OR. ANY(s/=expected) .OR. t/=te) ERROR STOP 'melt transfer'
  IF (ABS(bg-0.0000075_real64)>1.e-20_real64) ERROR STOP 'melt volume'
  old=s; to=t; oldbg=bg
  CALL melt_graupel_proportionally(t,s,bg,1.0_real64,status)
  IF (status/=STATUS_FAILED .OR. ANY(s/=old) .OR. t/=to .OR. bg/=oldbg) ERROR STOP 'melt rollback'
  nn=20.0_real64; nc=80.0_real64; old=s; t=100.0_real64; to=t
  CALL evaporate_cloud_completely(t,s,nn,nc,status)
  IF (status/=STATUS_FAILED .OR. ANY(s/=old) .OR. t/=to .OR. &
      nn/=20.0_real64 .OR. nc/=80.0_real64) ERROR STOP 'evaporation rollback'
  s=0.0_real64; t=280.0_real64; nn=20.0_real64; nc=80.0_real64
  old=s; to=t
  CALL evaporate_cloud_completely(t,s,nn,nc,status)
  IF (status/=STATUS_FAILED .OR. ANY(s/=old) .OR. t/=to .OR. &
      nn/=20.0_real64 .OR. nc/=80.0_real64) ERROR STOP 'orphan cloud number rollback'
  bg=0.00001_real64
  CALL melt_graupel_proportionally(t,s,bg,0.0_real64,status)
  IF (status/=STATUS_FAILED .OR. ANY(s/=old) .OR. t/=to .OR. &
      bg/=0.00001_real64) ERROR STOP 'orphan graupel volume rollback'
  s=0.0_real64; s(2)=ieee_value(0.0_real64,ieee_quiet_nan)
  old=s; t=280.0_real64; to=t; nn=20.0_real64; nc=80.0_real64
  CALL evaporate_cloud_completely(t,s,nn,nc,status)
  IF (status/=STATUS_FAILED .OR. ANY(TRANSFER(s,[0_int64,0_int64,0_int64,0_int64,0_int64,0_int64])/= &
      TRANSFER(old,[0_int64,0_int64,0_int64,0_int64,0_int64,0_int64])) .OR. &
      t/=to .OR. nn/=20.0_real64 .OR. nc/=80.0_real64) ERROR STOP 'NaN cloud mass rollback'
  CALL precondition_boundaries()
  PRINT *, 'phase moment completion: PASS'
CONTAINS
  SUBROUTINE precondition_boundaries()
    REAL(real64) :: q(6),temp,n,ncloud,volume,nan
    nan=ieee_value(0.0_real64,ieee_quiet_nan)

    q=[0.01_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
    temp=280.0_real64; n=20.0_real64; ncloud=0.0_real64
    CALL reject_evaporation(temp,q,n,ncloud)
    ncloud=-1.0_real64
    CALL reject_evaporation(temp,q,n,ncloud)
    ncloud=nan
    CALL reject_evaporation(temp,q,n,ncloud)
    ncloud=TINY(1.0_real64)
    CALL evaporate_cloud_completely(temp,q,n,ncloud,status)
    IF (status/=STATUS_OK .OR. q(2)/=0.0_real64 .OR. ncloud/=0.0_real64) ERROR STOP 'tiny NC accepted'
    q=0.0_real64; temp=280.0_real64; n=0.0_real64; ncloud=0.0_real64
    CALL evaporate_cloud_completely(temp,q,n,ncloud,status)
    IF (status/=STATUS_OK .OR. ANY(q/=0.0_real64) .OR. temp/=280.0_real64 .OR. &
        n/=0.0_real64 .OR. ncloud/=0.0_real64) ERROR STOP 'empty evaporation no-op'

    q=[0.01_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64,0.002_real64]
    temp=280.0_real64; volume=0.0_real64
    CALL reject_melt(temp,q,volume,0.0005_real64)
    CALL reject_melt(temp,q,volume,0.002_real64)
    volume=-1.0_real64
    CALL reject_melt(temp,q,volume,0.0005_real64)
    volume=nan
    CALL reject_melt(temp,q,volume,0.0005_real64)
    volume=0.00001_real64
    CALL reject_melt(temp,q,volume,nan)
    CALL reject_melt(temp,q,volume,-0.0005_real64)
    volume=0.0_real64
    old=q; to=temp
    CALL melt_graupel_proportionally(temp,q,volume,0.0_real64,status)
    IF (status/=STATUS_OK .OR. ANY(q/=old) .OR. temp/=to .OR. volume/=0.0_real64) &
      ERROR STOP 'zero melt with missing BG no-op'
    volume=TINY(1.0_real64)
    CALL melt_graupel_proportionally(temp,q,volume,0.0005_real64,status)
    IF (status/=STATUS_OK .OR. q(6)>=0.002_real64) ERROR STOP 'tiny BG accepted'
    q=0.0_real64; temp=280.0_real64; volume=0.0_real64
    CALL melt_graupel_proportionally(temp,q,volume,0.0_real64,status)
    IF (status/=STATUS_OK .OR. ANY(q/=0.0_real64) .OR. temp/=280.0_real64 .OR. &
        volume/=0.0_real64) ERROR STOP 'empty melt no-op'
  END SUBROUTINE precondition_boundaries

  SUBROUTINE reject_evaporation(temp,q,n,ncloud)
    REAL(real64), INTENT(INOUT) :: temp,q(6),n,ncloud
    REAL(real64) :: saved(9)
    saved=[temp,q,n,ncloud]
    CALL evaporate_cloud_completely(temp,q,n,ncloud,status)
    IF (status/=STATUS_FAILED .OR. ANY(TRANSFER([temp,q,n,ncloud],[0_int64],9)/= &
        TRANSFER(saved,[0_int64],9))) ERROR STOP 'evaporation precondition rollback'
  END SUBROUTINE reject_evaporation

  SUBROUTINE reject_melt(temp,q,volume,amount)
    REAL(real64), INTENT(INOUT) :: temp,q(6),volume
    REAL(real64), INTENT(IN) :: amount
    REAL(real64) :: saved(8)
    saved=[temp,q,volume]
    CALL melt_graupel_proportionally(temp,q,volume,amount,status)
    IF (status/=STATUS_FAILED .OR. ANY(TRANSFER([temp,q,volume],[0_int64],8)/= &
        TRANSFER(saved,[0_int64],8))) ERROR STOP 'melt precondition rollback'
  END SUBROUTINE reject_melt
END PROGRAM test_phase_moments
