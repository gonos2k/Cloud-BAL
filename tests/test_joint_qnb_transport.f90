program test_joint_qnb_transport
  use iso_fortran_env, only: real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan, ieee_positive_inf
  use cloud_bal_joint_transport, only: joint_qnb_update
  implicit none
  real(real32) :: qb(2,4), nb(2,4), qs(2,4), ns(2,4)
  real(real32) :: qsrc(2,4), nsrc(2,4), qt(2,4), nt(2,4)
  real(real32) :: mold(2), mnew(2), rho(2), dt
  real(real64) :: minmass(4), maxmass(4), theta, rq(4), rn(4)
  logical :: feasible
  integer :: p

  dt = 1.0_real32
  mold = [1.0_real32, 2.0_real32]
  mnew = [2.0_real32, 1.0_real32]
  rho = 1.0e-4_real32
  minmass = [1.0e-7_real64, 1.0e-7_real64, 1.0e-7_real64, 1.0e-7_real64]
  maxmass = [1.0e-5_real64, 1.0e-5_real64, 1.0e-5_real64, 1.0e-5_real64]
  qb = 1.0e-6_real32
  do p = 1,4
    nb(:,p) = qb(:,p)/1.0e-6_real32
  end do
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32

  ! A constant tracer remains constant when old and new dry-air carriers
  ! differ, provided the paired transport matches the carrier increment.
  do p = 1,4
    qt(:,p) = (mnew-mold)*qb(1,p)/dt
    nt(:,p) = (mnew-mold)*nb(1,p)/dt
  end do
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (.not. feasible .or. theta /= 1.0_real64) error stop 'constant-tracer update rejected'
  if (any(qs /= qb) .or. any(ns /= nb)) error stop 'constant tracer changed with carrier'

  ! One member's unrepresentable number-only arrival constrains the same
  ! accepted transport fraction for all four mass/number pairs.
  qs = qb
  ns = nb
  qt = 1.0e-7_real32
  nt = 1.0e-7_real32
  nt(1,2) = 1.0e4_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (.not. feasible .or. theta >= 1.0_real64 .or. theta <= 0.0_real64) &
    error stop 'joint limiter did not find a positive feasible fraction'
  if (any(qs < 0.0_real32) .or. any(ns < 0.0_real32)) error stop 'negative committed state'
  do p = 1,4
    if (any(real(ns(:,p),real64) < real(qs(:,p),real64)/maxmass(p) &
             -8.0_real64*real(epsilon(0.0_real32),real64)* &
              max(abs(real(ns(:,p),real64)),abs(real(qs(:,p),real64)/maxmass(p))))) &
      error stop 'lower particle-mass bound violated'
    if (any(real(ns(:,p),real64) > real(qs(:,p),real64)/minmass(p) &
             +8.0_real64*real(epsilon(0.0_real32),real64)* &
              max(abs(real(ns(:,p),real64)),abs(real(qs(:,p),real64)/minmass(p))))) &
      error stop 'upper particle-mass bound violated'
  end do
  if (any(rq <= 0.0_real64) .or. any(rn <= 0.0_real64)) &
    error stop 'rejected shared transport budget not recorded'

  ! Antisymmetric face transfers conserve extensive Q and N in a closed
  ! two-cell domain when the common candidate is fully accepted.
  mold = 1.0_real32
  mnew = mold
  rho = 1.0e-4_real32
  qs = qb
  ns = nb
  qt = 0.0_real32
  nt = 0.0_real32
  do p = 1,4
    qt(:,p) = [-2.0e-8_real32,2.0e-8_real32]
    nt(:,p) = [-2.0e-2_real32,2.0e-2_real32]
  end do
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (.not. feasible .or. theta /= 1.0_real64) error stop 'closed face rejected'
  do p = 1,4
    if (abs(sum(qs(:,p))-sum(qb(:,p))) > 2.0e-12_real32) &
      error stop 'closed Q face budget not conserved'
    if (abs(sum(ns(:,p))-sum(nb(:,p))) > 2.0e-5_real32) &
      error stop 'closed N face budget not conserved'
  end do

  ! Invalid source-only states are rejected before the arrays are modified.
  qs = qb
  ns = nb
  nsrc(1,1) = -1.0_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'invalid source-only candidate accepted'
  if (any(qs /= qb) .or. any(ns /= nb)) error stop 'failure partially committed'

  ! A finite REAL32 number mixing ratio may still convert to zero public
  ! number density at the actual local dry density.
  nsrc = 0.0_real32
  ns = nb
  rho = tiny(0.0_real32)
  do p = 1,4
    nb(:,p) = 1.0e-10_real32
    qb(:,p) = nb(:,p)*1.0e-6_real32
  end do
  qt = 0.0_real32
  nt = 0.0_real32
  qsrc = 0.0_real32
  ns = nb
  qs = qb
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'public number density underflow accepted'

  ! Round-to-nearest retains a positive product above half the minimum
  ! subnormal, including values below the minimum subnormal itself.
  rho = nearest(0.0_real32,1.0_real32)
  nb = 0.75_real32
  qb = 7.5e-7_real32
  ns = nb
  qs = qb
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (.not.feasible) error stop 'positive rounded subnormal product rejected'

  rho = 1.0_real32
  nb = qb/1.0e-6_real32
  ns = nb
  qs = qb
  qt = 0.0_real32
  nt = 0.0_real32
  qsrc(1,1) = ieee_value(0.0_real32,ieee_quiet_nan)
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'nonfinite source accepted'
  qsrc = 0.0_real32
  qsrc(1,1) = ieee_value(0.0_real32,ieee_positive_inf)
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'infinite source accepted'

  ! A broad ice PSD range must not let the upper N bound set the
  ! tolerance for the lower N bound, or admit mass without particles.
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 1.0e-6_real32
  nsrc = 0.0_real32
  minmass = 1.0e-14_real64
  maxmass = 1.0e-6_real64
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'mass-only source admitted with wide PSD interval'
  nsrc = 0.5_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'lower N bound weakened by unrelated upper bound'
  if (any(qs /= qb) .or. any(ns /= nb)) error stop 'PSD rejection partially committed'

  ! KDM6 QG/QIB uses QIB rime volume (m3/kg-dry): QG/QIB is bulk
  ! density (kg/m3), and QIB*rho_dry is rime volume fraction (m3/m3).
  qb = 0.0_real32
  nb = 0.0_real32
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  minmass = 1.0e-14_real64
  maxmass = 1.0e-6_real64
  minmass(4) = 100.0_real64
  maxmass(4) = 900.0_real64
  qb(1,4) = 7.0e-5_real32
  nb(1,4) = 1.0e-7_real32
  qs = qb
  ns = nb
  rho = 1.0_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (.not. feasible .or. qs(1,4)/ns(1,4) /= 700.0_real32) &
    error stop 'valid QG/QIB bulk density rejected'

  qb(1,4) = 9.01e-5_real32
  qs = qb
  ns = nb
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'QG/QIB bulk density above 900 accepted'
  if (any(qs /= qb) .or. any(ns /= nb)) error stop 'QG/QIB rejection partially committed'

  qb(1,4) = 175.0_real32
  nb(1,4) = 0.25_real32
  qs = qb
  ns = nb
  rho = nearest(0.0_real32,1.0_real32)
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible)
  if (feasible) error stop 'unrepresentable QIB volume fraction accepted'
  if (any(qs /= qb) .or. any(ns /= nb)) error stop 'QIB underflow rejection partially committed'
end program test_joint_qnb_transport
