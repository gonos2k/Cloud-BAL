program test_bulk_volume_policy
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use cloud_bal_joint_transport, only: joint_moment_store,joint_qnb_update
  implicit none
  real(real64), parameter :: eta=scale(1.0_real64,-149)
  real(real64) :: q,b,q2,b2,theta,rejected_q(4),rejected_b(4)
  real(real64) :: qrates(2,4),brates(2,4),qdelta(4),bdelta(4)
  real(real64) :: cell_bounds(2,2),bulk_delta(2)
  real(real64) :: pair_bounds(2,2,4),inactive_limits(4)
  real(real64) :: minmass(4),maxmass(4),bounds(2)
  real(real32) :: sq,sb,rho(2),qb(2,4),bb(2,4),qs(2,4),bs(2,4)
  real(real32) :: qt(2,4),bt(2,4),oldcarrier(2),newcarrier(2),dt
  real(real32) :: qstage(2,4),bstage(2,4)
  integer :: adjustment,stage,adjustments(4),bulk_count
  integer :: inactive_adjustments(4)
  logical :: valid,feasible,strict_pairs(4)
  logical :: inactive_pair(4)
  character(len=32) :: test_name

  q=transfer(int(z'370528AC448AD089',int64),0.0_real64)
  b=transfer(int(z'3668384CB70114F1',int64),0.0_real64)
  rho=1.0_real32

  test_name='known_candidate'
  call store(q,b,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5.and.stage==0.and.sq==0.0_real32.and.sb==0.0_real32,test_name)
  call store(q,b,.false.,sq,sb,adjustment,valid,stage)
  call check(.not.valid.and.stage==6,test_name//' default_off')

  q2=transfer(int(z'370FBB34F9B63B31',int64),0.0_real64)
  b2=transfer(int(z'367229317228D12C',int64),0.0_real64)
  call store(q2,b2,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5.and.stage==0.and.sq==0.0_real32.and.sb==0.0_real32, &
      'actual_rk2_candidate')
  call check(real(q2,real32)==transfer(int(z'0000007F',int32),0.0_real32), &
      'actual_rk2_candidate positive rounded Q')
  call store(real(127.0_real64*eta,real64),eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==0.and.sq>0.0_real32.and.sb>0.0_real32, &
      'actual_rk2_candidate feasible positive pair at fixed Q32')

  test_name='b_half_quantum_boundaries'
  call store(85.0_real64*eta,nearest(0.5_real64*eta,-1.0_real64),.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' below')
  call store(85.0_real64*eta,0.5_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' tie')
  call store(85.0_real64*eta,nearest(0.5_real64*eta,1.0_real64),.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' above')
  ! The bulk-loss bound is half of max_ratio times one B quantum. This
  ! near-boundary pair remains inside the strict continuous cone.
  call store(449.0_real64*eta,0.499_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' max-ratio budget interior')
  call store(0.25_real64*eta,0.001_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5.and.sq==0.0_real32.and.sb==0.0_real32, &
      test_name//' both round to zero')
  test_name='q_threshold_boundaries'
  call store(99.0_real64*eta,0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' belowrounded')
  call store(99.5_real64*eta,0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' old minimum threshold now allowed')
  call store(100.0_real64*eta,0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' old exact minimum now allowed')
  call store(450.0_real64*eta,0.5_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' both strict budgets reject tie')

  test_name='cone_and_orphan'
  call store(90.0_real64*eta,0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==5,test_name//' strict_valid')
  call store(10.0_real64*eta,0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' lower_cone')
  call store(90.0_real64*eta,0.0_real64,.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' orphan')
  call store(ieee_value(0.0_real64,ieee_quiet_nan),0.2_real64*eta,.true.,sq,sb,adjustment,valid,stage)
  call check(.not.valid,test_name//' nonfinite')

  test_name='normal_and_existing_absence'
  call store(2.5e-5_real64,1.0e-7_real64,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==0.and.sq>0.0_real32.and.sb>0.0_real32,test_name//' normal')
  call joint_moment_store(0.0_real64,0.0_real64,1.0_real32, &
      100.0_real64,900.0_real64,.true.,sq,sb,adjustment,valid,allow_joint_quantum_absence=.true., &
      strict_mass_ratio=.true.,allow_bulk_volume_quantum_absence=.true.)
  call check(valid.and.adjustment==0.and.sq==0.0_real32.and.sb==0.0_real32, &
      test_name//' existing absent pair unchanged')
  call store(127.0_real64*eta,eta,.true.,sq,sb,adjustment,valid,stage)
  call check(valid.and.adjustment==0.and.sq==real(127.0_real64*eta,real32).and. &
      sb==real(eta,real32),test_name//' positive pair remains unchanged')

  test_name='incompatible_store_options'
  bounds=[100.0_real64,900.0_real64]
  call joint_moment_store(85.0_real64*eta,0.2_real64*eta,1.0_real32,100.0_real64,900.0_real64, &
      .true.,sq,sb,adjustment,valid,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      volume_number_bounds=bounds,allow_bulk_volume_quantum_absence=.true.,failure_stage=stage)
  call check(.not.valid.and.stage==1,test_name//' volume contract')
  call joint_moment_store(85.0_real64*eta,0.2_real64*eta,1.0_real32,100.0_real64,900.0_real64, &
      .true.,sq,sb,adjustment,valid,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      inactive_mass_limit=1.0_real64,allow_bulk_volume_quantum_absence=.true.,failure_stage=stage)
  call check(.not.valid.and.stage==1,test_name//' inactive limit')
  call joint_moment_store(85.0_real64*eta,0.2_real64*eta,1.0_real32,100.0_real64,900.0_real64, &
      .true.,sq,sb,adjustment,valid,allow_joint_quantum_absence=.true., &
      allow_bulk_volume_quantum_absence=.true.,failure_stage=stage)
  call check(.not.valid.and.stage==1,test_name//' missing strict gate')
  call joint_moment_store(85.0_real64*eta,0.2_real64*eta,1.0_real32,100.0_real64,900.0_real64, &
      .true.,sq,sb,adjustment,valid,strict_mass_ratio=.true., &
      allow_bulk_volume_quantum_absence=.true.,failure_stage=stage)
  call check(.not.valid.and.stage==1,test_name//' missing quantum absence opt-in')
  test_name='grouped_commit_and_count'
  call reset_group(2)
  qrates(:,4)=q; brates(:,4)=b
  call update_group(feasible,bulk_count,adjustments,qdelta,bdelta)
  call check(feasible.and.bulk_count==2.and.adjustments(4)==2,test_name)
  call check(all(qstage(:,4)==0.0_real32).and.all(bstage(:,4)==0.0_real32),test_name//' stored')
  call check(qdelta(4)==-2.0_real64*q.and.bdelta(4)==-2.0_real64*b,test_name//' signed budget')
  call check(all(bulk_delta==[-2.0_real64*q,-2.0_real64*b]),test_name//' policy-only budget')

  test_name='policy_ledger_separate_from_rounding'
  call reset_group(2)
  qrates(1,4)=q; brates(1,4)=b
  brates(2,4)=1.0e-7_real64
  qrates(2,4)=nearest(900.0_real64*brates(2,4),-1.0_real64)
  call update_group(feasible,bulk_count,adjustments,qdelta,bdelta)
  call check(feasible.and.bulk_count==1.and.adjustments(4)==2,test_name)
  call check(all(bulk_delta==[-q,-b]),test_name//' isolated policy loss')
  call check(qdelta(4)/=bulk_delta(1),test_name//' total also contains normal Q repair')

  test_name='grouped_atomic_rollback'
  call reset_group(2)
  qrates(1,4)=q; brates(1,4)=b
  qrates(2,4)=10.0_real64*eta; brates(2,4)=0.2_real64*eta
  call update_group(feasible,bulk_count,adjustments,qdelta,bdelta)
  call check(.not.feasible.and.bulk_count==0.and.all(adjustments==0),test_name)
  call check(all(qstage==0.25_real32).and.all(bstage==0.5_real32),test_name//' stages')
  call check(all(qdelta==0.0_real64).and.all(bdelta==0.0_real64).and. &
      all(bulk_delta==0.0_real64),test_name//' ledgers')

  test_name='grouped_reject_without_strict_p4'
  call reset_group(1)
  strict_pairs(4)=.false.
  call update_group(feasible,bulk_count,adjustments,qdelta,bdelta)
  call check(.not.feasible.and.bulk_count==0.and.all(qstage==0.25_real32),test_name)

  test_name='grouped_reject_volume_contract'
  call reset_group(2)
  cell_bounds(1,:)=[100.0_real64,900.0_real64]
  cell_bounds(2,:)=[100.0_real64,900.0_real64]
  call joint_qnb_update(qb,bb,qstage,bstage,qs,bs,qt,bt,oldcarrier,newcarrier,rho,dt, &
      minmass,maxmass,theta,rejected_q,rejected_b,feasible,joint_subnormal_storage=.false., &
      storage_delta_q=qdelta,storage_delta_n=bdelta,storage_adjustments=adjustments, &
      joint_constrained_storage=.true.,q_source_rate64=qrates,n_source_rate64=brates, &
      q_transport_rate64=0.0_real64*qrates,n_transport_rate64=0.0_real64*brates, &
      joint_quantum_absence=.true.,strict_number_pair=4,volume_number_bounds=cell_bounds, &
      strict_mass_pairs=strict_pairs,bulk_volume_quantum_absence=.true., &
      bulk_volume_absences=bulk_count,bulk_volume_delta=bulk_delta)
  call check(.not.feasible.and.bulk_count==0.and.all(qstage==0.25_real32),test_name)

  test_name='grouped_coexists_with_c14_p1_p3_p2_options'
  call reset_group(2)
  qb(:,1)=0.0078125_real32; bb(:,1)=1.0_real32
  qb(:,3)=0.015625_real32; bb(:,3)=2.0_real32
  minmass(2)=2.6055879053e-16_real64; maxmass(2)=2.0983e-9_real64
  qrates(:,2)=0.25_real64*eta; brates(:,2)=1.0e-20_real64
  qrates(:,4)=q; brates(:,4)=b
  pair_bounds=0.0_real64
  pair_bounds(:,1,1)=100.0_real64; pair_bounds(:,2,1)=900.0_real64
  pair_bounds(:,1,3)=100.0_real64; pair_bounds(:,2,3)=900.0_real64
  inactive_limits=[0.0_real64,9.999998977483753e-15_real64,0.0_real64,0.0_real64]
  inactive_pair=[.false.,.true.,.false.,.false.]
  call joint_qnb_update(qb,bb,qstage,bstage,qs,bs,qt,bt,oldcarrier,newcarrier,rho,dt, &
      minmass,maxmass,theta,rejected_q,rejected_b,feasible,joint_subnormal_storage=.false., &
      storage_delta_q=qdelta,storage_delta_n=bdelta,storage_adjustments=adjustments, &
      joint_constrained_storage=.true.,q_source_rate64=qrates,n_source_rate64=brates, &
      q_transport_rate64=0.0_real64*qrates,n_transport_rate64=0.0_real64*brates, &
      joint_quantum_absence=.true.,number_pair_bounds=pair_bounds,strict_mass_pairs=strict_pairs, &
      inactive_mass_limits=inactive_limits,inactive_q_quantum_adjustment_pairs=inactive_pair, &
      inactive_q_quantum_adjustments=inactive_adjustments, &
      bulk_volume_quantum_absence=.true.,bulk_volume_absences=bulk_count,bulk_volume_delta=bulk_delta)
  call check(feasible.and.bulk_count==2.and.adjustments(4)==2,test_name)
  call check(all(qstage(:,1)==0.0078125_real32).and. &
      all(bstage(:,1)==1.0_real32).and. &
      all(qstage(:,3)==0.015625_real32).and. &
      all(bstage(:,3)==2.0_real32),test_name//' bounded pairs preserved')
  call check(all(adjustments([1,3])==0).and.all(qdelta([1,3])==0.0_real64).and. &
      all(bdelta([1,3])==0.0_real64),test_name//' bounded pair ledgers')
  call check(all(qstage(:,2)==real(eta,real32)).and.all(bstage(:,2)==real(1.0e-20_real64,real32)).and. &
      all(inactive_adjustments==[0,2,0,0]).and.all(adjustments([1,2,3])==[0,2,0]), &
      test_name//' p2 inactive-Q adjustment preserved')
  call check(all(qstage(:,4)==0.0_real32).and.all(bstage(:,4)==0.0_real32).and. &
      bulk_count==adjustments(4),test_name//' p4 bulk count')
  call check(qdelta(2)==2.0_real64*(real(eta,real32)-0.25_real64*eta).and. &
      bdelta(2)==2.0_real64*(real(real(1.0e-20_real64,real32),real64)-1.0e-20_real64),test_name//' p2 signed ledger')
  call check(qdelta(4)==-2.0_real64*q.and.bdelta(4)==-2.0_real64*b, &
      test_name//' p4 signed ledger')
  call check(all(bulk_delta==[qdelta(4),bdelta(4)]),test_name//' independent bulk ledger')

  test_name='grouped_coexists_with_other_strict_number_pair'
  call reset_group(2)
  qrates(:,4)=q; brates(:,4)=b
  inactive_limits=[0.0_real64,9.999998977483753e-15_real64,0.0_real64,0.0_real64]
  inactive_pair=[.false.,.true.,.false.,.false.]
  call joint_qnb_update(qb,bb,qstage,bstage,qs,bs,qt,bt,oldcarrier,newcarrier,rho,dt, &
      minmass,maxmass,theta,rejected_q,rejected_b,feasible,joint_subnormal_storage=.false., &
      storage_delta_q=qdelta,storage_delta_n=bdelta,storage_adjustments=adjustments, &
      joint_constrained_storage=.true.,q_source_rate64=qrates,n_source_rate64=brates, &
      q_transport_rate64=0.0_real64*qrates,n_transport_rate64=0.0_real64*brates, &
      joint_quantum_absence=.true.,strict_number_pair=1,volume_number_bounds=cell_bounds, &
      strict_mass_pairs=strict_pairs,inactive_mass_limits=inactive_limits, &
      inactive_q_quantum_adjustment_pairs=inactive_pair, &
      inactive_q_quantum_adjustments=inactive_adjustments, &
      bulk_volume_quantum_absence=.true.,bulk_volume_absences=bulk_count,bulk_volume_delta=bulk_delta)
  call check(feasible.and.bulk_count==2.and.adjustments(4)==2,test_name)

  print '(a)', 'PR92 bulk-volume quantum policy PASS'

contains

  subroutine check(ok,label)
    logical,intent(in) :: ok
    character(len=*),intent(in) :: label
    if (.not.ok) then
      print '(a,1x,a)', 'FAIL',trim(label)
      error stop 1
    end if
  end subroutine check

  subroutine store(qin,bin,enabled,qout,bout,adj,ok,failstage)
    real(real64),intent(in) :: qin,bin
    logical,intent(in) :: enabled
    real(real32),intent(out) :: qout,bout
    integer,intent(out) :: adj,failstage
    logical,intent(out) :: ok
    call joint_moment_store(qin,bin,1.0_real32,100.0_real64,900.0_real64,.true., &
        qout,bout,adj,ok,allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
        strict_mass_ratio=.true.,failure_stage=failstage, &
        allow_bulk_volume_quantum_absence=enabled)
  end subroutine store

  subroutine reset_group(ncells)
    integer,intent(in) :: ncells
    qb=0.0_real32; bb=0.0_real32; qs=0.0_real32; bs=0.0_real32
    qt=0.0_real32; bt=0.0_real32; qstage=0.25_real32; bstage=0.5_real32
    oldcarrier=1.0_real32; newcarrier=1.0_real32; rho=1.0_real32; dt=1.0_real32
    minmass=[0.001_real64,1.0_real64,0.001_real64,100.0_real64]
    maxmass=[0.01_real64,900.0_real64,0.01_real64,900.0_real64]
    qrates=0.0_real64; brates=0.0_real64
    strict_pairs=[.false.,.false.,.false.,.true.]
    if (ncells<1) error stop 'invalid test group size'
  end subroutine reset_group

  subroutine update_group(ok,count,adj,dq,dn)
    logical,intent(out) :: ok
    integer,intent(out) :: count,adj(4)
    real(real64),intent(out) :: dq(4),dn(4)
    call joint_qnb_update(qb,bb,qstage,bstage,qs,bs,qt,bt,oldcarrier,newcarrier,rho,dt, &
        minmass,maxmass,theta,rejected_q,rejected_b,ok,joint_subnormal_storage=.false., &
        storage_delta_q=dq,storage_delta_n=dn,storage_adjustments=adj, &
        joint_constrained_storage=.true.,q_source_rate64=qrates,n_source_rate64=brates, &
        q_transport_rate64=0.0_real64*qrates,n_transport_rate64=0.0_real64*brates, &
        joint_quantum_absence=.true.,strict_mass_pairs=strict_pairs, &
        bulk_volume_quantum_absence=.true.,bulk_volume_absences=count,bulk_volume_delta=bulk_delta)
  end subroutine update_group

end program test_bulk_volume_policy
