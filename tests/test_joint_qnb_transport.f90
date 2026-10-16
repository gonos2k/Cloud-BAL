program test_joint_qnb_transport
  use iso_fortran_env, only: int32, real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan, ieee_positive_inf
  use cloud_bal_joint_transport, only: joint_moment_is_valid64, joint_moment_store, joint_qnb_update
  implicit none
  real(real32) :: qb(2,4), nb(2,4), qs(2,4), ns(2,4)
  real(real32) :: qsrc(2,4), nsrc(2,4), qt(2,4), nt(2,4)
  real(real64) :: qsrc64(2,4), nsrc64(2,4), qt64(2,4), nt64(2,4)
  real(real32) :: mold(2), mnew(2), rho(2), dt
  real(real64) :: minmass(4), maxmass(4), theta, rq(4), rn(4)
  real(real64) :: deltaq(4), deltan(4), qcontinuous, ncontinuous, minbound, maxbound
  real(real64) :: strict_volume_bounds(2,2)
  real(real64) :: number_pair_bounds(2,2,4)
  real(real64), parameter :: rain_q64(12) = [ &
    6.2414485339543636e-12_real64, 1.4260306900292141e-11_real64, &
    6.5907654454871058e-09_real64, 4.8985812163176893e-08_real64, &
    2.4936895240761569e-09_real64, 4.269868481919295e-07_real64, &
    1.103179712483762e-07_real64, 3.9088477858009047e-08_real64, &
    5.2894503691985542e-09_real64, 9.9616069120036251e-08_real64, &
    1.9661251106469059e-07_real64, 1.4743551115494971e-09_real64 ]
  real(real64), parameter :: rain_n64(12) = [ &
    2.1295097940249721e-02_real64, 4.8654510754935272e-02_real64, &
    2.2486926758007701e+01_real64, 1.6713390494057899e+02_real64, &
    8.5081792617628107e+00_real64, 1.4568295663667800e+03_real64, &
    3.7639211020130801e+02_real64, 1.3336534978370801e+02_real64, &
    1.8046990420928498e+01_real64, 3.3987846420531798e+02_real64, &
    6.7081906615186097e+02_real64, 5.0303285306287604e+00_real64 ]
  real(real32), parameter :: rain_rho32(12) = [ &
    1.1623120307922363_real32, 0.72127240896224976_real32, &
    0.72177207469940186_real32, 0.61723107099533081_real32, &
    0.66951620578765869_real32, 0.72180688381195068_real32, &
    0.82240802049636841_real32, 0.87050908803939819_real32, &
    0.82061088085174561_real32, 0.76969420909881592_real32, &
    0.90190201997756958_real32, 0.95972782373428345_real32 ]
  real(real64), parameter :: rain_minmass = 12566.37109375_real64/35000.0_real64**3
  real(real64), parameter :: rain_maxmass = 12566.37109375_real64/961.0_real64**3
  real(real64) :: rain_number_volume, rain_lower_number, rain_upper_number, rain_bounds_test(2)
  real(real64) :: cloud_q1,cloud_n1,cloud_qrate,cloud_nrate,cloud_qstage,cloud_nstage
  real(real64) :: cloud_rho64,cloud_pidn,cloud_minmass,cloud_maxmass,cloud_volume_bounds(2)
  real(real32) :: cloud_rho32,cloud_virtual_q,cloud_virtual_n
  real(real64) :: overflow_candidate
  real(real32) :: storedq, storedn, minsub
  real(real32) :: bulk_q_bad, bulk_n, bulk_q_stored
  real(real64) :: bulk_q_boundary
  logical :: feasible
  logical :: strict_mass_flags(4)
  logical :: wrong_mass_flags(3)
  integer :: p, adjustment, adjustments(4), short_adjustments(3), trial, case_index

  ! Invalid density must reject before any ordered NaN comparison under traps.
  call joint_moment_store(400.0_real64,1.0_real64, &
       ieee_value(0.0_real32,ieee_quiet_nan),100.0_real64,900.0_real64,.true., &
       storedq,storedn,adjustment,feasible,strict_mass_ratio=.true.)
  if (feasible) error stop 'strict mass accepted NaN density'

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

  ! Opt-in storage may map a subnormal Q that rounds to zero to joint absence.
  minsub = nearest(0.0_real32,1.0_real32)
  call joint_moment_store(1.0e-46_real64,1.0e-40_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (.not.feasible .or. adjustment /= 1 .or. storedq /= 0.0_real32 .or. &
      storedn /= 0.0_real32) error stop 'joint subnormal absence not selected'
  call joint_moment_store(1.0e-46_real64,1.0e-40_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.false., &
                          storedq,storedn,adjustment,feasible)
  if (feasible .or. adjustment /= 0) error stop 'strict storage repaired Q underflow'

  ! A ratio failure from ordinary REAL32 rounding may move Q by one ULP only
  ! when the continuous pair was valid and the adjusted stored pair passes.
  do trial = 1,5
    call joint_moment_store((1.50_real64+0.01_real64*real(trial,real64))*1.0e-45_real64, &
                            1.50e-39_real64,1.0_real32,1.0e-6_real64,1.0e-5_real64, &
                            .true.,storedq,storedn,adjustment,feasible)
    if (.not.feasible .or. adjustment /= 2 .or. &
        storedq /= nearest(minsub,1.0_real32) .or. &
        storedn /= real(1.50e-39_real64,real32)) error stop 'one-ULP Q storage repair failed'
  end do
  qcontinuous = 5.416812466351981e-43_real64
  ncontinuous = 2.584424854810883e-34_real64
  minbound = 1570.79638671875_real64/(1820000.0_real64**3)
  maxbound = 1570.79638671875_real64/(9080.0_real64**3)
  if (qcontinuous/ncontinuous > maxbound) error stop 'upper-bound fixture is not continuously valid'
  call joint_moment_store(qcontinuous,ncontinuous,1.17269_real32,minbound,maxbound, &
                          .true.,storedq,storedn,adjustment,feasible)
  if (.not.feasible .or. adjustment /= 2 .or. &
      storedq /= nearest(real(qcontinuous,real32),-1.0_real32) .or. &
      storedn /= real(ncontinuous,real32)) error stop 'upper-end one-ULP Q repair failed'

  ! The retained v4 RK3 FULL row is continuously valid, but its Q rounds to
  ! the minimum subnormal and one downward Q ULP leaves positive N alone.
  ! Only the general constrained policy may map this sub-quantum pair to zero.
  qcontinuous = 7.352132008755282e-46_real64
  ncontinuous = 4.691007751024326e-37_real64
  minbound = 1570.79638671875_real64/(1820000.0_real64**3)
  maxbound = 1570.79638671875_real64/(9080.0_real64**3)
  if (.not.joint_moment_is_valid64(qcontinuous,ncontinuous,1.192746_real32, &
                                   minbound,maxbound)) &
    error stop 'retained RK3 sub-quantum pair is not continuously valid'
  call joint_moment_store(qcontinuous,ncontinuous,1.192746_real32,minbound,maxbound, &
                          .true.,storedq,storedn,adjustment,feasible, &
                          allow_normal_q_adjustment=.true., &
                          allow_joint_quantum_absence=.true.)
  if (.not.feasible .or. adjustment /= 3 .or. storedq /= 0.0_real32 .or. &
      storedn /= 0.0_real32) error stop 'constrained sub-quantum joint absence failed'
  call joint_moment_store(qcontinuous,ncontinuous,1.192746_real32,minbound,maxbound, &
                          .true.,storedq,storedn,adjustment,feasible, &
                          allow_normal_q_adjustment=.true.)
  if (feasible) error stop 'subnormal-only store accepted quantum absence'

  ! Quantum absence must not clear Q at or above one REAL32 quantum. Here the
  ! nearest Q and adjacent Q values both fail; rounded N density also underflows.
  minsub = nearest(0.0_real32,1.0_real32)
  qcontinuous = 18.0_real64*real(minsub,real64)
  ncontinuous = 5.1_real64*real(minsub,real64)
  if (.not.joint_moment_is_valid64(qcontinuous,ncontinuous,0.1_real32,3.5_real64,3.55_real64)) &
    error stop 'at-quantum rejection fixture is not continuously valid'
  call joint_moment_store(qcontinuous,ncontinuous,0.1_real32,3.5_real64,3.55_real64, &
                          .true.,storedq,storedn,adjustment,feasible, &
                          allow_normal_q_adjustment=.true., &
                          allow_joint_quantum_absence=.true.)
  if (feasible) error stop 'joint quantum absence cleared Q at the REAL32 minimum subnormal'

  ! The grouped candidate records both actual signed extensive losses for the
  ! retained row when the constrained representation chooses joint absence.
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  qsrc64 = 0.0_real64
  nsrc64 = 0.0_real64
  qt64 = 0.0_real64
  nt64 = 0.0_real64
  qsrc64(1,2) = 7.352132008755282e-46_real64
  nsrc64(1,2) = 4.691007751024326e-37_real64
  mold = 1.0_real32
  mnew = 1.0_real32
  rho = 1.192746_real32
  dt = 1.0_real32
  minmass = 1.0e-6_real64
  maxmass = 1.0e-5_real64
  minmass(2) = 1570.79638671875_real64/(1820000.0_real64**3)
  maxmass(2) = 1570.79638671875_real64/(9080.0_real64**3)
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb) .or. &
      any(deltaq /= 0.0_real64) .or. any(deltan /= 0.0_real64) .or. &
      any(adjustments /= 0)) error stop 'constrained storage enabled quantum absence implicitly'
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64, &
                        joint_quantum_absence=.true.)
  if (.not.feasible .or. theta /= 1.0_real64 .or. adjustments(2) /= 1 .or. &
      qs(1,2) /= 0.0_real32 .or. ns(1,2) /= 0.0_real32) then
    error stop 'grouped sub-quantum joint absence failed'
  end if
  if (deltaq(2) /= -7.352132008755282e-46_real64 .or. &
      deltan(2) /= -4.691007751024326e-37_real64) &
    error stop 'sub-quantum signed storage delta ledger is incorrect'
  if (any(adjustments([1,3,4]) /= 0) .or. any(deltaq([1,3,4]) /= 0.0_real64) .or. &
      any(deltan([1,3,4]) /= 0.0_real64)) error stop 'quantum ledger includes untouched pairs'

  ! The extra quantum-absence flag requires constrained storage mode.
  deltaq = -1.0_real64
  deltan = -1.0_real64
  adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_quantum_absence=.true.)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb) .or. &
      any(deltaq /= 0.0_real64) .or. any(deltan /= 0.0_real64) .or. &
      any(adjustments /= 0)) error stop 'quantum absence accepted outside constrained mode'

  ! The general constrained store may adjust one Q ULP even at normal scale,
  ! but only if the continuous pair passes the unrounded physical checks.
  minbound = 1.0_real64+8.0_real64*real(spacing(1.0_real32),real64)+1.0e-8_real64
  qcontinuous = 1.0_real64+2.0e-8_real64
  call joint_moment_store(qcontinuous,1.0_real64,1.0_real32, &
                          minbound,2.0_real64,.true.,storedq,storedn, &
                          adjustment,feasible,allow_normal_q_adjustment=.true.)
  if (.not.feasible .or. adjustment /= 2 .or. storedq /= nearest(1.0_real32,1.0_real32)) &
    error stop 'normal-Q constrained storage was not applied'
  call joint_moment_store(qcontinuous,1.0_real64,1.0_real32, &
                          minbound,2.0_real64,.true.,storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'subnormal-only store adjusted normal Q'
  if (.not.joint_moment_is_valid64(1.0e-46_real64,1.0e-40_real64,1.0_real32, &
                                   1.0e-6_real64,1.0e-5_real64)) &
    error stop 'continuous validator rejected a representable subnormal pair'
  call joint_moment_store(0.0_real64,1.0e-40_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'genuine number-only continuous pair repaired'
  call joint_moment_store(-1.0e-46_real64,1.0e-40_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'negative continuous mass repaired'
  call joint_moment_store(1.0e-46_real64,-1.0e-40_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'negative continuous number repaired'
  call joint_moment_store(1.0e-56_real64,1.0e-50_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'number-density underflow continuous pair repaired'
  call joint_moment_store(1.0e-12_real64,1.0e-20_real64,1.0_real32, &
                          1.0e-6_real64,1.0e-5_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'invalid normal-mass continuous pair repaired'
  call joint_moment_store(1.2e-38_real64,1.2e-46_real64,1.0e38_real32, &
                          1.0e7_real64,1.0e9_real64,.true., &
                          storedq,storedn,adjustment,feasible)
  if (feasible) error stop 'normal-Q rounding failure repaired'

  ! The grouped opt-in path writes signed extensive storage deltas only on a
  ! successful theta=1 commit and does not alter the shared air transport.
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  mold = 1.0_real32
  mnew = 1.0_real32
  rho = 1.0_real32
  dt = 0.1_real32
  minmass = 1.0e-6_real64
  maxmass = 1.0e-5_real64
  qb(1,1) = minsub
  qsrc(1,1) = minsub
  nb(1,1) = 1.50e-39_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible,.true., &
                        deltaq,deltan,adjustments)
  if (.not.feasible .or. theta /= 1.0_real64 .or. adjustments(1) /= 1) then
    write(*,*) 'OPTIN_STATE',feasible,theta,adjustments(1),qs(1,1),ns(1,1),deltaq(1)
    error stop 'opt-in grouped one-ULP storage policy failed'
  end if
  if (qs(1,1) /= nearest(minsub,1.0_real32) .or. ns(1,1) /= nb(1,1)) &
    error stop 'one-ULP storage policy committed unexpected state'
  qcontinuous = real(minsub,real64)+real(dt,real64)*real(minsub,real64)
  if (deltaq(1) /= real(qs(1,1),real64)-qcontinuous .or. deltan(1) /= 0.0_real64) &
    error stop 'signed storage delta ledger is incorrect'
  if (any(adjustments(2:4) /= 0) .or. any(deltaq(2:4) /= 0.0_real64) .or. &
      any(deltan /= 0.0_real64)) error stop 'storage ledger includes untouched pairs'

  ! Joint underflow records the exact signed loss of both pair members.
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  mold = 0.1_real32
  mnew = 1.0_real32
  dt = 0.1_real32
  maxmass = 1.0e-4_real64
  qb(1,1) = minsub
  nb(1,1) = 1.0e-40_real32
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible,.true., &
                        deltaq,deltan,adjustments)
  if (.not.feasible .or. theta /= 1.0_real64 .or. adjustments(1) /= 1 .or. &
      qs(1,1) /= 0.0_real32 .or. ns(1,1) /= 0.0_real32) &
    error stop 'grouped joint-underflow storage policy failed'
  qcontinuous = real(mold(1),real64)*real(minsub,real64)/real(mnew(1),real64)
  if (deltaq(1) /= real(mnew(1),real64)*(0.0_real64-qcontinuous) .or. &
      deltan(1) /= real(mnew(1),real64)*(0.0_real64- &
        real(mold(1),real64)*real(nb(1,1),real64)/real(mnew(1),real64))) &
    error stop 'joint-underflow ledger did not record both signed deltas'

  ! The grouped update consumes REAL64 source-first donor rates. For periodic
  ! two-cell mixing with C=1/4, the source makes both donors equal before
  ! transport; adding old-state donor rates afterward would make cell 2 Q=.875.
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  qsrc64 = 0.0_real64
  nsrc64 = 0.0_real64
  qt64 = 0.0_real64
  nt64 = 0.0_real64
  mold = 1.0_real32
  mnew = 1.0_real32
  rho = 1.0_real32
  dt = 1.0_real32
  minmass = 1.0_real64
  maxmass = 4.0_real64
  qb(:,1) = [1.0_real32,1.5_real32]
  nb(:,1) = 1.0_real32
  qsrc(2,1) = -0.5_real32
  qsrc64(2,1) = -0.5_real64
  qt(:,1) = [0.125_real32,-0.125_real32]
  ! Source-prepared Q/N are both one, so the source-first periodic donor
  ! transport rate is exactly zero in both cells.
  qs(:,1) = qb(:,1)+qsrc(:,1)
  ns(:,1) = nb(:,1)+nsrc(:,1)
  if (.not.joint_moment_is_valid64(real(qs(1,1),real64),real(ns(1,1),real64), &
                                  rho(1),minmass(1),maxmass(1)) .or. &
      .not.joint_moment_is_valid64(real(qs(2,1),real64),real(ns(2,1),real64), &
                                  rho(2),minmass(1),maxmass(1))) &
    error stop 'source-prepared two-cell donors are invalid'
  if (joint_moment_is_valid64(1.5_real64-0.125_real64-0.5_real64,1.0_real64, &
                              rho(2),minmass(1),maxmass(1))) &
    error stop 'additive old-donor two-cell counterexample unexpectedly passed'
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64)
  if (.not.feasible .or. theta /= 1.0_real64 .or. any(qs(:,1) /= 1.0_real32) .or. &
      any(ns(:,1) /= 1.0_real32)) error stop 'source-first two-cell update failed'
  if (sum(real(qs(:,1),real64)) /= &
      sum(real(qb(:,1),real64))+dt*sum(qsrc64(:,1))) &
    error stop 'source-first two-cell transport did not conserve Q'
  if (sum(real(ns(:,1),real64)) /= &
      sum(real(nb(:,1),real64))+dt*sum(nsrc64(:,1))) &
    error stop 'source-first two-cell transport did not conserve N'
  if (qs(2,1) == real(1.5_real64-0.125_real64-0.5_real64,real32)) &
    error stop 'source-first transport reused old-state donor flux'

  ! The opt-in flag requires every ledger, and failed candidates leave fields
  ! unchanged and ledgers empty.
  qs = qb
  ns = nb
  deltaq = -1.0_real64
  deltan = -1.0_real64
  adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible,.true.)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb)) &
    error stop 'opt-in storage accepted missing ledgers'
  deltaq = -1.0_real64
  deltan = -1.0_real64
  short_adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible,.true., &
                        deltaq,deltan,short_adjustments)
  if (feasible .or. any(deltaq /= 0.0_real64) .or. any(deltan /= 0.0_real64) .or. &
      any(short_adjustments /= 0)) error stop 'wrong-sized storage ledger not initialized'
  qsrc(1,1) = -10.0_real32
  deltaq = -1.0_real64
  deltan = -1.0_real64
  adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible,.true., &
                        deltaq,deltan,adjustments)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb) .or. &
      any(deltaq /= 0.0_real64) .or. any(deltan /= 0.0_real64) .or. &
      any(adjustments /= 0)) error stop 'failed opt-in candidate partially committed'

  ! A strict volume-number contract checks the continuous candidate before
  ! rounding, then checks both REAL64 and rounded REAL32 N-volume products.
  qcontinuous = 1.0_real64+2.0e-8_real64
  ncontinuous = 1.0_real64
  strict_volume_bounds(1,:) = [0.5_real64,0.99999999_real64]
  strict_volume_bounds(2,:) = strict_volume_bounds(1,:)
  call joint_moment_store(qcontinuous,ncontinuous,1.0_real32,0.5_real64,2.0_real64, &
                          .true.,storedq,storedn,adjustment,feasible, &
                          allow_normal_q_adjustment=.true., &
                          volume_number_bounds=strict_volume_bounds(1,:))
  if (.not.feasible .or. adjustment /= 2 .or. &
      storedq /= nearest(1.0_real32,1.0_real32) .or. storedn /= 1.0_real32) &
    error stop 'strict volume-number one-ULP storage adjustment failed'
  call joint_moment_store(1.0_real64,ncontinuous,1.0_real32,0.5_real64,2.0_real64, &
                          .true.,storedq,storedn,adjustment,feasible, &
                          allow_normal_q_adjustment=.true., &
                          volume_number_bounds=strict_volume_bounds(1,:))
  if (feasible .or. adjustment /= 0) &
    error stop 'invalid strict continuous volume-number candidate was repaired'

  ! Here R64(rho*N) is inside the strict upper bound but the actual R32
  ! product rounds above it. The adjacent upward Q must satisfy both products.
  strict_volume_bounds(1,:) = [2.0_real64,2.20999999_real64]
  call joint_moment_store(1.0_real64,real(1.7_real32,real64),1.3_real32, &
                          0.5_real64,1.0_real64,.true.,storedq,storedn, &
                          adjustment,feasible,allow_normal_q_adjustment=.true., &
                          volume_number_bounds=strict_volume_bounds(1,:))
  if (.not.feasible .or. adjustment /= 2 .or. &
      storedq /= nearest(1.0_real32,1.0_real32) .or. &
      real(storedn*1.3_real32,real64) > &
        strict_volume_bounds(1,2)*real(storedq,real64)) &
    error stop 'R32 number-volume product did not guide the strict Q adjustment'
  if (real(storedn,real64)*real(1.3_real32,real64) > &
      strict_volume_bounds(1,2)*real(storedq,real64)) &
    error stop 'strict R64 number-volume product failed after Q adjustment'

  ! The RK3 source-first cloud endpoint is a virtual specific-Q/N donor for
  ! air transport. It must satisfy the cloud mass cone, but the density-volume
  ! contract applies to the completed endpoint after grouped transport.
  cloud_q1=real(transfer(int(z'34785000',int32),0.0_real32),real64)
  cloud_n1=55209024.0_real64
  cloud_qrate=-5.733295348764840e-13_real64
  cloud_nrate=real(-136.900970458984375_real32,real64)+0.02928267221449232_real64
  cloud_rho32=transfer(int(z'3f92c8ca',int32),0.0_real32)
  cloud_rho64=real(cloud_rho32,real64)
  cloud_pidn=real(523.59881591796875_real32,real64)
  cloud_minmass=cloud_pidn/500000.0_real64**3
  cloud_maxmass=cloud_pidn/12000.0_real64**3
  cloud_volume_bounds=[cloud_rho64*12000.0_real64**3/cloud_pidn, &
                       cloud_rho64*500000.0_real64**3/cloud_pidn]
  cloud_qstage=cloud_q1+20.0_real64*cloud_qrate
  cloud_nstage=cloud_n1+20.0_real64*cloud_nrate
  if (cloud_qstage/cloud_nstage/=cloud_minmass .or. &
      cloud_qstage<cloud_minmass*cloud_nstage .or. &
      cloud_nstage*cloud_rho64<=cloud_volume_bounds(2)*cloud_qstage) &
    error stop 'source-stage virtual cloud witness no longer matches V30 operands'
  call joint_moment_store(cloud_qstage,cloud_nstage,cloud_rho32,cloud_minmass,cloud_maxmass, &
      .true.,storedq,storedn,adjustment,feasible,allow_normal_q_adjustment=.true., &
      allow_joint_quantum_absence=.true.,strict_mass_ratio=.true.)
  if (.not.feasible .or. real(storedq,real64)<cloud_minmass*real(storedn,real64) .or. &
      real(storedq,real64)>cloud_maxmass*real(storedn,real64)) &
    error stop 'strict cloud mass-only virtual source donor was rejected'
  cloud_virtual_q=storedq
  cloud_virtual_n=storedn
  call joint_moment_store(cloud_qstage,cloud_nstage,cloud_rho32,cloud_minmass,cloud_maxmass, &
      .true.,storedq,storedn,adjustment,feasible,allow_normal_q_adjustment=.true., &
      allow_joint_quantum_absence=.true.,volume_number_bounds=cloud_volume_bounds, &
      strict_mass_ratio=.true.)
  if (feasible .or. adjustment/=0) &
    error stop 'virtual cloud source candidate bypassed the completed volume contract'
  call joint_moment_store(real(cloud_virtual_q,real64),real(cloud_virtual_n,real64), &
      cloud_rho32,cloud_minmass,cloud_maxmass,.true.,storedq,storedn,adjustment,feasible, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
      volume_number_bounds=cloud_volume_bounds,strict_mass_ratio=.true.)
  if (.not.feasible .or. real(storedn,real64)*cloud_rho64 < &
      cloud_volume_bounds(1)*real(storedq,real64) .or. &
      real(storedn,real64)*cloud_rho64 > cloud_volume_bounds(2)*real(storedq,real64) .or. &
      real(storedn*cloud_rho32,real64) < cloud_volume_bounds(1)*real(storedq,real64) .or. &
      real(storedn*cloud_rho32,real64) > cloud_volume_bounds(2)*real(storedq,real64)) &
    error stop 'completed cloud endpoint did not retain the strict volume contract'

  ! Actual V18 full-proposal failures: keep rounded N fixed and direct Q
  ! into the strict intersection of both number-volume products and the
  ! source mean-mass bounds. Q/N are decimal reconstructions from the formatted
  ! R64 FULL packet, not raw bit captures; density is the corresponding R32
  ! value from PRE_RK.
  do case_index=1,12
    rain_bounds_test(1) = &
      real(rain_rho32(case_index),real64)*961.0_real64**3/12566.37109375_real64
    rain_bounds_test(2) = &
      real(rain_rho32(case_index),real64)*35000.0_real64**3/12566.37109375_real64
    call joint_moment_store(rain_q64(case_index),rain_n64(case_index),rain_rho32(case_index), &
        rain_minmass,rain_maxmass,.true.,storedq,storedn,adjustment,feasible, &
        allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
        volume_number_bounds=rain_bounds_test)
    if (.not.feasible .or. adjustment /= 2 .or. storedn /= real(rain_n64(case_index),real32)) &
      error stop 'directed strict-volume Q store failed or changed ordinary N'
    rain_number_volume=real(storedn,real64)*real(rain_rho32(case_index),real64)
    rain_lower_number=rain_bounds_test(1)*real(storedq,real64)
    rain_upper_number=rain_bounds_test(2)*real(storedq,real64)
    if (rain_number_volume<rain_lower_number .or. rain_number_volume>rain_upper_number .or. &
        real(storedn*rain_rho32(case_index),real64)<rain_lower_number .or. &
        real(storedn*rain_rho32(case_index),real64)>rain_upper_number .or. &
        real(storedq,real64)/real(storedn,real64)<rain_minmass .or. &
        real(storedq,real64)/real(storedn,real64)>rain_maxmass) &
      error stop 'directed strict-volume Q escaped one of the exact stored bounds'
  end do

  ! The grouped kernel reports the signed storage difference using exactly
  ! the selected Q and keeps the rounded N representation unchanged.
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  qsrc=0.0_real32; nsrc=0.0_real32; qt=0.0_real32; nt=0.0_real32
  qsrc64=0.0_real64; nsrc64=0.0_real64; qt64=0.0_real64; nt64=0.0_real64
  qsrc64(1,3)=rain_q64(1); nsrc64(1,3)=rain_n64(1)
  mold=1.0_real32; mnew=1.0_real32; rho=rain_rho32(1); dt=1.0_real32
  minmass=0.5_real64; maxmass=2.0_real64
  minmass(3)=rain_minmass; maxmass(3)=rain_maxmass
  rain_bounds_test(1)=real(rho(1),real64)*961.0_real64**3/12566.37109375_real64
  rain_bounds_test(2)=real(rho(1),real64)*35000.0_real64**3/12566.37109375_real64
  strict_volume_bounds(1,:)=rain_bounds_test
  strict_volume_bounds(2,:)=rain_bounds_test
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,strict_number_pair=3,volume_number_bounds=strict_volume_bounds)
  if (.not.feasible .or. qs(1,3)<=real(rain_q64(1),real32) .or. &
      ns(1,3)/=real(rain_n64(1),real32) .or. adjustments(3)/=1 .or. &
      any(adjustments([1,2,4])/=0) .or. &
      deltaq(3)/=real(qs(1,3),real64)-rain_q64(1) .or. &
      deltan(3)/=real(ns(1,3),real64)-rain_n64(1)) &
    error stop 'directed-Q grouped commit or signed storage budget is incorrect'

  ! Guard the R32 volume product before casting when rounding N would overflow,
  ! even though the continuous R64 candidate itself remains representable.
  overflow_candidate=(real(huge(0.0_real32),real64)/real(1.7_real32,real64))* &
                     (1.0_real64-1.0e-9_real64)
  if (.not.joint_moment_is_valid64(overflow_candidate,overflow_candidate,1.7_real32, &
                                   0.9_real64,1.1_real64) .or. &
      overflow_candidate*real(1.7_real32,real64)>real(huge(0.0_real32),real64) .or. &
      real(real(overflow_candidate,real32),real64)*real(1.7_real32,real64) &
        <= real(huge(0.0_real32),real64)) &
    error stop 'rounded-N overflow fixture did not pass the continuous-only gate'
  call joint_moment_store(overflow_candidate,overflow_candidate,1.7_real32,0.9_real64,1.1_real64, &
      .true.,storedq,storedn,adjustment,feasible,allow_normal_q_adjustment=.true., &
      volume_number_bounds=[0.9_real64*real(1.7_real32,real64), &
                            1.1_real64*real(1.7_real32,real64)])
  if (feasible .or. adjustment/=0) error stop 'rounded N volume overflow was cast or accepted'

  ! A continuous-valid candidate can still have no representable Q in the
  ! strict interval; the bounded directed search must reject it atomically.
  call joint_moment_store(1.00000003_real64,1.0_real64,1.0_real32,0.5_real64,2.0_real64, &
      .true.,storedq,storedn,adjustment,feasible,allow_normal_q_adjustment=.true., &
      volume_number_bounds=[0.99999995_real64,0.99999998_real64])
  if (feasible .or. adjustment /= 0) error stop 'strict Q interval without an R32 value was accepted'

  strict_volume_bounds(:,1) = 0.5_real64
  strict_volume_bounds(:,2) = 0.99999999_real64
  qb = 0.0_real32
  nb = 0.0_real32
  qs = qb
  ns = nb
  qsrc = 0.0_real32
  nsrc = 0.0_real32
  qt = 0.0_real32
  nt = 0.0_real32
  qsrc64 = 0.0_real64
  nsrc64 = 0.0_real64
  qt64 = 0.0_real64
  nt64 = 0.0_real64
  qsrc64(1,1) = 2.0_real64
  nsrc64(1,1) = 1.0_real64
  qsrc64(1,2) = qcontinuous
  nsrc64(1,2) = ncontinuous
  mold = 1.0_real32
  mnew = 1.0_real32
  rho = 1.0_real32
  dt = 1.0_real32
  minmass = 0.5_real64
  maxmass = 2.0_real64
  deltaq = -1.0_real64
  deltan = -1.0_real64
  adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64, &
                        strict_number_pair=2,volume_number_bounds=strict_volume_bounds)
  if (.not.feasible .or. theta /= 1.0_real64 .or. &
      qs(1,1) /= 2.0_real32 .or. ns(1,1) /= 1.0_real32 .or. &
      qs(1,2) /= nearest(1.0_real32,1.0_real32) .or. ns(1,2) /= 1.0_real32) &
    error stop 'strict volume-number update failed or altered another pair'
  if (adjustments(2) /= 1 .or. deltaq(2) /= &
      real(nearest(1.0_real32,1.0_real32),real64)-qcontinuous .or. deltan(2) /= 0.0_real64 .or. &
      any(adjustments([1,3,4]) /= 0)) error stop 'strict volume-number storage ledger is incorrect'

  ! A strict continuous rejection is atomic even when the ordinary eight-ULP
  ! mass validator would admit it; missing constrained ledgers also reject.
  qs = qb
  ns = nb
  qsrc64(1,2) = 1.0_real64
  deltaq = -1.0_real64
  deltan = -1.0_real64
  adjustments = -1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        storage_delta_q=deltaq,storage_delta_n=deltan, &
                        storage_adjustments=adjustments,joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64, &
                        strict_number_pair=2,volume_number_bounds=strict_volume_bounds)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb) .or. &
      any(deltaq /= 0.0_real64) .or. any(deltan /= 0.0_real64) .or. &
      any(adjustments /= 0)) error stop 'strict invalid continuous pair partially committed'
  qsrc64(1,2) = qcontinuous
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
                        minmass,maxmass,theta,rq,rn,feasible, &
                        joint_constrained_storage=.true., &
                        q_source_rate64=qsrc64,n_source_rate64=nsrc64, &
                        q_transport_rate64=qt64,n_transport_rate64=nt64, &
                        strict_number_pair=2,volume_number_bounds=strict_volume_bounds)
  if (feasible .or. any(qs /= qb) .or. any(ns /= nb)) &
    error stop 'strict volume-number mode accepted missing ledgers'

  ! The per-pair contract applies independent source PSD coefficients to
  ! cloud (pair 1) and rain (pair 3); zero rows leave other pairs unrestricted.
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  qsrc=0.0_real32; nsrc=0.0_real32; qt=0.0_real32; nt=0.0_real32
  qsrc64=0.0_real64; nsrc64=0.0_real64; qt64=0.0_real64; nt64=0.0_real64
  mold=1.0_real32; mnew=1.0_real32; rho=[1.0_real32,0.8_real32]; dt=1.0_real32
  minmass=[1.0e-7_real64,1.0e-7_real64,1.0e-7_real64,1.0e-7_real64]
  maxmass=[1.0e-5_real64,1.0e-5_real64,1.0e-5_real64,1.0e-5_real64]
  minmass(1)=523.59881591796875_real64/500000.0_real64**3
  maxmass(1)=523.59881591796875_real64/12000.0_real64**3
  minmass(3)=rain_minmass
  maxmass(3)=rain_maxmass
  number_pair_bounds=0.0_real64
  do case_index=1,2
    number_pair_bounds(case_index,1,1)=real(rho(case_index),real64)* &
        12000.0_real64**3/523.59881591796875_real64
    number_pair_bounds(case_index,2,1)=real(rho(case_index),real64)* &
        500000.0_real64**3/523.59881591796875_real64
    number_pair_bounds(case_index,1,3)=real(rho(case_index),real64)* &
        961.0_real64**3/12566.37109375_real64
    number_pair_bounds(case_index,2,3)=real(rho(case_index),real64)* &
        35000.0_real64**3/12566.37109375_real64
  end do
  qsrc64(1,1)=1.0e-10_real64
  nsrc64(1,1)=1.0_real64
  qsrc64(1,3)=rain_q64(1)
  nsrc64(1,3)=rain_n64(1)
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
  if (.not.feasible .or. theta/=1.0_real64 .or. qs(1,1)<=0.0_real32 .or. &
      qs(1,3)<=real(rain_q64(1),real32) .or. ns(1,3)/=real(rain_n64(1),real32) .or. &
      adjustments(3)/=1 .or. any(adjustments([1,2,4])/=0)) &
    error stop 'independent cloud/rain volume contracts did not commit together'
  do case_index=1,2
    do p=1,4
      if (number_pair_bounds(case_index,1,p)==0.0_real64) cycle
      if (real(ns(case_index,p),real64)*real(rho(case_index),real64) < &
              number_pair_bounds(case_index,1,p)*real(qs(case_index,p),real64) .or. &
          real(ns(case_index,p),real64)*real(rho(case_index),real64) > &
              number_pair_bounds(case_index,2,p)*real(qs(case_index,p),real64) .or. &
          real(ns(case_index,p)*rho(case_index),real64) < &
              number_pair_bounds(case_index,1,p)*real(qs(case_index,p),real64) .or. &
          real(ns(case_index,p)*rho(case_index),real64) > &
              number_pair_bounds(case_index,2,p)*real(qs(case_index,p),real64)) &
        error stop 'per-pair contract failed one of its R64/R32 volume products'
    end do
  end do

  ! Cloud subnormal storage remains joint absence under its own C32 bounds;
  ! the simultaneously strict rain pair remains a normal accepted state.
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  qsrc64=0.0_real64; nsrc64=0.0_real64
  qsrc64(1,1)=1.0e-46_real64; nsrc64(1,1)=1.0e-32_real64
  qsrc64(1,3)=rain_q64(1); nsrc64(1,3)=rain_n64(1)
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true.,joint_quantum_absence=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
  if (.not.feasible .or. qs(1,1)/=0.0_real32 .or. ns(1,1)/=0.0_real32 .or. &
      qs(1,3)<=0.0_real32 .or. ns(1,3)/=real(rain_n64(1),real32)) &
    error stop 'per-pair cloud subnormal/rain normal cases failed'

  ! A continuously invalid strict rain pair rejects the whole candidate and
  ! leaves both staged fields and storage ledgers unchanged.
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  qsrc64=0.0_real64; nsrc64=0.0_real64
  qsrc64(1,1)=1.0e-10_real64; nsrc64(1,1)=1.0_real64
  qsrc64(1,3)=1.0e-12_real64; nsrc64(1,3)=1.0e4_real64
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb) .or. any(deltaq/=0.0_real64) .or. &
      any(deltan/=0.0_real64) .or. any(adjustments/=0)) &
    error stop 'invalid continuous per-pair candidate was repaired or partially committed'

  ! V22b actual cloud counterexample: reject the strict cloud candidate while
  ! the independently bounded rain pair is valid in the same grouped call.
  rho=[transfer(int(z'3F20E608',int32),0.0_real32),0.8_real32]
  number_pair_bounds(1,1,1)=real(rho(1),real64)*12000.0_real64**3/523.59881591796875_real64
  number_pair_bounds(1,2,1)=real(rho(1),real64)*500000.0_real64**3/523.59881591796875_real64
  number_pair_bounds(2,1,1)=real(rho(2),real64)*12000.0_real64**3/523.59881591796875_real64
  number_pair_bounds(2,2,1)=real(rho(2),real64)*500000.0_real64**3/523.59881591796875_real64
  do case_index=1,2
    number_pair_bounds(case_index,1,3)=real(rho(case_index),real64)* &
        961.0_real64**3/12566.37109375_real64
    number_pair_bounds(case_index,2,3)=real(rho(case_index),real64)* &
        35000.0_real64**3/12566.37109375_real64
  end do
  qsrc64(1,1)=real(transfer(int(z'14B2DBD6',int32),0.0_real32),real64)
  nsrc64(1,1)=real(transfer(int(z'2C97B2DB',int32),0.0_real32),real64)
  qsrc64(1,3)=rain_q64(1); nsrc64(1,3)=rain_n64(1)
  if (.not.joint_moment_is_valid64(qsrc64(1,1),nsrc64(1,1),rho(1),minmass(1),maxmass(1)) .or. &
      real(nsrc64(1,1),real64)*real(rho(1),real64) <= &
        number_pair_bounds(1,2,1)*qsrc64(1,1) .or. &
      .not.joint_moment_is_valid64(qsrc64(1,3),nsrc64(1,3),rho(1),minmass(3),maxmass(3)) .or. &
      real(nsrc64(1,3),real64)*real(rho(1),real64) > &
        number_pair_bounds(1,2,3)*qsrc64(1,3)) &
    error stop 'V22b cloud strict-volume invalid/rain valid fixture is incorrect'
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb) .or. any(deltaq/=0.0_real64) .or. &
      any(deltan/=0.0_real64) .or. any(adjustments/=0)) &
    error stop 'invalid cloud pair was repaired or partially committed with valid rain'

  ! Every row of an active pair needs finite positive ordered bounds.
  number_pair_bounds(2,1,1)=0.0_real64
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb)) &
    error stop 'partially specified active pair bounds were accepted'

  ! Reject non-finite bounds before comparing them with zero or each other.
  number_pair_bounds(2,1,1)=real(rho(2),real64)*12000.0_real64**3/523.59881591796875_real64
  do case_index=1,2
    if (case_index==1) then
      number_pair_bounds(1,1,1)=ieee_value(0.0_real64,ieee_quiet_nan)
    else
      number_pair_bounds(1,1,1)=ieee_value(0.0_real64,ieee_positive_inf)
    end if
    call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
        minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
        storage_adjustments=adjustments,joint_constrained_storage=.true., &
        q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
        n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds)
    if (feasible .or. any(qs/=qb) .or. any(ns/=nb)) &
      error stop 'non-finite per-pair bounds were accepted'
  end do
  number_pair_bounds(1,1,1)=real(rho(1),real64)*12000.0_real64**3/523.59881591796875_real64

  ! Legacy and multi-pair contracts are mutually exclusive.
  strict_volume_bounds(1,:)=number_pair_bounds(1,:,3)
  strict_volume_bounds(2,:)=number_pair_bounds(2,:,3)
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,strict_number_pair=3,volume_number_bounds=strict_volume_bounds, &
      number_pair_bounds=number_pair_bounds)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb)) &
    error stop 'simultaneous legacy and multi-pair bounds were accepted'

  ! Strict mass storage rejects a rounded graupel bulk-density state just
  ! above 900, then directs a valid exact-boundary candidate to the nearest
  ! representable Q with its stored rime-volume B unchanged.
  bulk_q_bad=transfer(int(z'35462ED6',int32),0.0_real32)
  bulk_n=transfer(int(z'30617CF8',int32),0.0_real32)
  if (.not.joint_moment_is_valid64(real(bulk_q_bad,real64),real(bulk_n,real64), &
                                   1.0_real32,100.0_real64,900.0_real64)) &
    error stop 'graupel near-boundary compatibility fixture is not accepted by legacy validator'
  call joint_moment_store(real(bulk_q_bad,real64),real(bulk_n,real64),1.0_real32, &
      100.0_real64,900.0_real64,.true.,storedq,storedn,adjustment,feasible, &
      allow_normal_q_adjustment=.true.,strict_mass_ratio=.true.)
  if (feasible .or. adjustment/=0) error stop 'strict mass accepted invalid graupel bulk density'
  bulk_q_boundary=900.0_real64*real(bulk_n,real64)
  if (real(real(bulk_q_boundary,real32),real64)/real(bulk_n,real64)<=900.0_real64) &
    error stop 'ordinary R32 graupel Q did not cross the strict upper bound'
  call joint_moment_store(real(bulk_q_boundary,real64),real(bulk_n,real64),1.0_real32, &
      100.0_real64,900.0_real64,.true.,storedq,storedn,adjustment,feasible, &
      allow_normal_q_adjustment=.true.,strict_mass_ratio=.true.)
  if (.not.feasible .or. adjustment/=2 .or. storedn/=bulk_n .or. &
      real(storedq,real64)/real(storedn,real64)>900.0_real64 .or. &
      real(storedq,real64)/real(storedn,real64)<100.0_real64) &
    error stop 'strict mass boundary did not select an exact valid Q with B fixed'
  bulk_q_stored=storedq

  ! Number-volume rain and strict bulk-density graupel contracts coexist in
  ! one full-theta update, with independent signed storage ledgers.
  qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
  qsrc=0.0_real32; nsrc=0.0_real32; qt=0.0_real32; nt=0.0_real32
  qsrc64=0.0_real64; nsrc64=0.0_real64; qt64=0.0_real64; nt64=0.0_real64
  number_pair_bounds=0.0_real64
  do case_index=1,2
    number_pair_bounds(case_index,1,3)=real(rho(case_index),real64)* &
        961.0_real64**3/12566.37109375_real64
    number_pair_bounds(case_index,2,3)=real(rho(case_index),real64)* &
        35000.0_real64**3/12566.37109375_real64
  end do
  strict_mass_flags=.false.; strict_mass_flags(4)=.true.
  qsrc64(1,3)=rain_q64(1); nsrc64(1,3)=rain_n64(1)
  qsrc64(1,4)=bulk_q_boundary; nsrc64(1,4)=real(bulk_n,real64)
  minmass=[1.0e-7_real64,1.0e-7_real64,rain_minmass,100.0_real64]
  maxmass=[1.0e-5_real64,1.0e-5_real64,rain_maxmass,900.0_real64]
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds, &
      strict_mass_pairs=strict_mass_flags)
  if (.not.feasible .or. theta/=1.0_real64 .or. qs(1,3)<=real(rain_q64(1),real32) .or. &
      ns(1,3)/=real(rain_n64(1),real32) .or. real(qs(1,4),real64)/real(ns(1,4),real64)>900.0_real64 .or. &
      qs(1,4)/=bulk_q_stored .or. ns(1,4)/=bulk_n .or. &
      adjustments(3)/=1 .or. adjustments(4)/=1 .or. &
      any(adjustments([1,2])/=0) .or. deltaq(3)/=real(qs(1,3),real64)-rain_q64(1) .or. &
      deltaq(4)/=real(qs(1,4),real64)-bulk_q_boundary .or. &
      deltan(4)/=real(ns(1,4),real64)-real(bulk_n,real64)) &
    error stop 'strict bulk mass and rain volume contracts did not commit with signed budgets'

  ! The exact invalid graupel state rejects the grouped candidate even when
  ! the rain pair is valid, and cannot be repaired after the continuous gate.
  qs=qb; ns=nb
  qsrc64(1,4)=real(bulk_q_bad,real64); nsrc64(1,4)=real(bulk_n,real64)
  deltaq=-1.0_real64; deltan=-1.0_real64; adjustments=-1
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,number_pair_bounds=number_pair_bounds, &
      strict_mass_pairs=strict_mass_flags)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb) .or. any(deltaq/=0.0_real64) .or. &
      any(deltan/=0.0_real64) .or. any(adjustments/=0)) &
    error stop 'invalid strict graupel mass pair was repaired or partially committed'

  wrong_mass_flags=.true.
  qs=qb; ns=nb
  call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,mold,mnew,rho,dt, &
      minmass,maxmass,theta,rq,rn,feasible,storage_delta_q=deltaq,storage_delta_n=deltan, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,strict_mass_pairs=wrong_mass_flags)
  if (feasible .or. any(qs/=qb) .or. any(ns/=nb)) &
    error stop 'wrong-sized strict mass pair mask was accepted'
  write(*,'(a)') 'PASS test_joint_qnb_transport'
end program test_joint_qnb_transport
