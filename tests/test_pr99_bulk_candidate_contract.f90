program test_pr99_bulk_candidate_contract
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_bulk_candidate_absence_is_valid,joint_qnb_update
  implicit none
  real(real32) :: qb,bb,oldc,newc,dt,rho
  real(real64) :: sq,sb,aq,ab,theta,qref,bref
  real(real32) :: qbase(1,4),bbase(1,4),qstage(1,4),bstage(1,4)
  real(real32) :: qsource(1,4),bsource(1,4),qtransport(1,4),btransport(1,4)
  real(real32) :: carriers_old(1),carriers_new(1),density(1)
  real(real64) :: qsource64(1,4),bsource64(1,4),qtransport64(1,4),btransport64(1,4)
  real(real64) :: minmass(4),maxmass(4),theta_out,rejected_q(4),rejected_b(4)
  real(real64) :: delta_q(4),delta_b(4),bulk_delta(2)
  integer :: adjustments(4),bulk_count
  logical :: strict_mass(4),feasible
  integer :: failures
  logical :: valid

  failures=0
  qb=transfer(int(z'00000000',int32),0.0_real32)
  bb=transfer(int(z'00000000',int32),0.0_real32)
  dt=transfer(int(z'40D55555',int32),0.0_real32)
  oldc=transfer(int(z'47A09016',int32),0.0_real32)
  newc=transfer(int(z'47A08D94',int32),0.0_real32)
  rho=transfer(int(z'3F53B32D',int32),0.0_real32)
  sq=transfer(int(z'3753214B46A3BC21',int64),0.0_real64)
  sb=transfer(int(z'36B5C40847451A51',int64),0.0_real64)
  aq=transfer(int(z'8000000000000000',int64),0.0_real64)
  ab=transfer(int(z'8000000000000000',int64),0.0_real64)
  theta=1.0_real64
  qref=transfer(int(z'36796B3BA65C1BE8',int64),0.0_real64)
  bref=transfer(int(z'35DCEBC8FCFEFC7A',int64),0.0_real64)

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,qref,bref)
  call check(valid,'captured fatal candidate passes the full extensive certificate')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,nearest(sq,1.0_real64), &
      sb,aq,ab,theta,100.0_real64,900.0_real64,qref,bref)
  call check(.not.valid,'source operand change cannot reuse captured reference candidate')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,1.0_real64,ab, &
      theta,100.0_real64,900.0_real64,qref,bref)
  call check(.not.valid,'nonzero air transport cannot reuse captured reference candidate')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,1.0_real64,ab,0.5_real64, &
      100.0_real64,900.0_real64,qref,bref)
  call check(.not.valid,'trial scale must reproduce exact full candidate')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,nearest(qref,1.0_real64),bref)
  call check(.not.valid,'reference candidate bits must match ordered R64 recomputation')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,qref,nearest(bref,1.0_real64))
  call check(.not.valid,'volume reference bits must match ordered R64 recomputation')

  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,899.0_real64,qref,bref)
  call check(.not.valid,'strict maximum-density cone rejects an out-of-cone candidate')

  qb=0.0_real32; bb=0.0_real32; oldc=1.0_real32; newc=1.0_real32
  dt=1.0_real32; rho=1.0_real32; aq=0.0_real64; ab=0.0_real64; theta=1.0_real64
  sb=0.25_real64*scale(1.0_real64,-149)
  sq=899.0_real64*sb
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,sq,sb)
  call check(valid,'strict cone accepts a subquantum endpoint below its upper bound')
  sq=901.0_real64*sb
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,sq,sb)
  call check(.not.valid,'strict cone rejects a subquantum endpoint above its upper bound')
  sq=900.0_real64*sb
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,sq,sb)
  call check(.not.valid,'uncertain exact cone boundary fails closed')

  sb=0.75_real64*scale(1.0_real64,-149)
  sq=100.0_real64*sb
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      100.0_real64,900.0_real64,sq,sb)
  call check(.not.valid,'half-quantum number-loss budget is enforced')

  qb=transfer(int(z'00000001',int32),0.0_real32); bb=0.0_real32
  oldc=1.0_real32; newc=1.0_real32; dt=huge(0.0_real32); rho=1.0_real32; theta=1.0_real64
  sq=0.1_real64*huge(0.0_real64); aq=-sq
  sb=(0.25_real64*scale(1.0_real64,-149))/real(dt,real64); ab=0.0_real64
  bref=real(dt,real64)*sb
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      1.0_real64,8.0_real64,scale(1.0_real64,-149),bref)
  call check(.not.valid,'large cancellation is rejected by the conservative R64 headroom guard')

  qb=0.0_real32; bb=0.0_real32; dt=1.0_real32; sq=2.0_real64*real(huge(0.0_real32),real64)
  sb=sq/huge(0.0_real64); aq=0.0_real64; ab=0.0_real64
  valid=joint_bulk_candidate_absence_is_valid(qb,bb,oldc,newc,dt,rho,sq,sb,aq,ab,theta, &
      1.0_real64,huge(0.0_real64),sq,sb)
  call check(.not.valid,'the pre-existing REAL32 reference-range gate remains active')

  dt=transfer(int(z'40D55555',int32),0.0_real32)
  oldc=transfer(int(z'47A09016',int32),0.0_real32)
  newc=transfer(int(z'47A08D94',int32),0.0_real32)
  rho=transfer(int(z'3F53B32D',int32),0.0_real32)
  sq=transfer(int(z'3753214B46A3BC21',int64),0.0_real64)
  sb=transfer(int(z'36B5C40847451A51',int64),0.0_real64)
  aq=transfer(int(z'8000000000000000',int64),0.0_real64)
  ab=transfer(int(z'8000000000000000',int64),0.0_real64)
  qbase=0.0_real32; bbase=0.0_real32
  qsource=0.0_real32; bsource=0.0_real32
  qtransport=0.0_real32; btransport=0.0_real32
  qsource64=0.0_real64; bsource64=0.0_real64
  qtransport64=0.0_real64; btransport64=0.0_real64
  qsource64(1,4)=sq; bsource64(1,4)=sb
  qtransport64(1,4)=aq; btransport64(1,4)=ab
  carriers_old(1)=oldc; carriers_new(1)=newc; density(1)=rho
  minmass=[1.0_real64,1.0_real64,1.0_real64,100.0_real64]
  maxmass=[1.0_real64,1.0_real64,1.0_real64,900.0_real64]
  strict_mass=[.false.,.false.,.false.,.true.]
  qstage=123.0_real32; bstage=456.0_real32
  call joint_qnb_update(qbase,bbase,qstage,bstage,qsource,bsource,qtransport,btransport, &
      carriers_old,carriers_new,density,dt,minmass,maxmass,theta_out,rejected_q,rejected_b, &
      feasible,storage_delta_q=delta_q,storage_delta_n=delta_b, &
      storage_adjustments=adjustments,joint_constrained_storage=.true., &
      q_source_rate64=qsource64,n_source_rate64=bsource64, &
      q_transport_rate64=qtransport64,n_transport_rate64=btransport64, &
      joint_quantum_absence=.true.,strict_mass_pairs=strict_mass, &
      bulk_volume_quantum_storage=.true.,bulk_volume_absences=bulk_count,bulk_volume_delta=bulk_delta)
  call check(feasible.and.theta_out==1.0_real64,'full grouped transaction accepts certified endpoint')
  call check(all(qstage==0.0_real32).and.all(bstage==0.0_real32), &
      'group commit stores the paired zero endpoint')
  call check(bulk_count==1.and.adjustments(4)==1,'group commit counts exactly one bulk adjustment')
  call check(bulk_delta(1)<0.0_real64.and.bulk_delta(2)<0.0_real64, &
      'bulk ledger preserves signed extensive losses')

  if (failures/=0) stop 1
  print *, 'PR99_BULK_CANDIDATE_CERTIFICATE_PASS'
contains
  subroutine check(ok,label)
    logical,intent(in) :: ok
    character(*),intent(in) :: label
    if (.not.ok) then
      print *, 'FAIL: ',label
      failures=failures+1
    end if
  end subroutine check
end program test_pr99_bulk_candidate_contract
