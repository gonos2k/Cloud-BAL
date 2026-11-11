! Explicit closed internal processes on a fixed dry-air mass basis.
MODULE cloud_bal_phase_moments
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: apply_water_phase_transfer
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: evaporate_cloud_completely, melt_graupel_proportionally
CONTAINS
  PURE SUBROUTINE evaporate_cloud_completely(temperature,species,nn,nc,status)
    REAL(real64), INTENT(INOUT) :: temperature,species(6),nn,nc
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: t_new,s_new(6),delta(6),nn_new
    INTEGER :: transfer_status
    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(nn) .OR. .NOT.ieee_is_finite(nc)) RETURN
    IF (.NOT.ieee_is_finite(species(2))) RETURN
    IF (nn<0.0_real64 .OR. nc<0.0_real64) RETURN
    IF (species(2)==0.0_real64 .AND. nc>0.0_real64) RETURN
    IF (species(2)>0.0_real64 .AND. nc==0.0_real64) RETURN
    IF (nc>HUGE(nn)-nn) RETURN
    nn_new=nn+nc
    t_new=temperature; s_new=species
    delta=0.0_real64; delta(1)=species(2); delta(2)=-species(2)
    CALL apply_water_phase_transfer(t_new,s_new,delta,transfer_status)
    IF (transfer_status/=STATUS_OK) RETURN
    temperature=t_new; species=s_new; nn=nn_new; nc=0.0_real64
    status=STATUS_OK
  END SUBROUTINE evaporate_cloud_completely

  PURE SUBROUTINE melt_graupel_proportionally(temperature,species,bg,melt,status)
    REAL(real64), INTENT(INOUT) :: temperature,species(6),bg
    REAL(real64), INTENT(IN) :: melt
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: t_new,s_new(6),delta(6),bg_new
    INTEGER :: transfer_status
    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(bg) .OR. .NOT.ieee_is_finite(melt) .OR. &
        .NOT.ieee_is_finite(species(6))) RETURN
    IF (bg<0.0_real64 .OR. melt<0.0_real64 .OR. species(6)<0.0_real64) RETURN
    IF (melt>species(6)) RETURN
    IF (species(6)==0.0_real64 .AND. bg>0.0_real64) RETURN
    IF (melt>0.0_real64 .AND. bg==0.0_real64) RETURN
    bg_new=bg
    IF (species(6)>0.0_real64) bg_new=bg*((species(6)-melt)/species(6))
    t_new=temperature; s_new=species
    delta=0.0_real64; delta(4)=melt; delta(6)=-melt
    CALL apply_water_phase_transfer(t_new,s_new,delta,transfer_status)
    IF (transfer_status/=STATUS_OK) RETURN
    temperature=t_new; species=s_new; bg=bg_new
    status=STATUS_OK
  END SUBROUTINE melt_graupel_proportionally
END MODULE cloud_bal_phase_moments
