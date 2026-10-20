program source_store_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use captured_data
  use d1_graupel_adapter
  use cloud_bal_joint_transport, only: joint_moment_store
  use cloud_bal_policy_replay, only: policy_store => joint_moment_store
  implicit none
  real(real32) :: field(-1:1,1:1,-1:1),field_n(-1:1,1:1,-1:1),sq,sn,psq,psn,rho32
  real(real64) :: inc,ninc,q,n,qs,ns,qa,na,rho,mn,mx,oldmass,newmass,qbase,nbase,dt64
  real(real128) :: face(4),nface(4)
  integer(int64) :: words(2),candidate_q_bits,candidate_n_bits
  integer :: r,dy,x,adj,stage,padj,pstage
  logical :: valid,nvalid,pvalid,formula_ok,qface_ok,nface_ok,stored_strict
  do r=1,size(producer_id,2)
    call load_producer(r)
    call graupel_diffusion_point(field,0,1,0,inc,face,valid)
    write(*,'(A,1X,I0,1X,L1,2(1X,Z16.16),1X,7(I0,1X))') 'PRODUCER_REPLAY',r,valid, &
      transfer(inc,0_int64),producer_diff(1,r),producer_id(:,r)
  end do
  do r=1,size(identity64,2)
    call load_identity(r)
    call graupel_diffusion_point(field,0,1,0,inc,face,valid)
    call graupel_diffusion_point(field_n,0,1,0,ninc,nface,nvalid)
    qface_ok=valid
    nface_ok=nvalid
    do x=1,4
      words=transfer(face(x),words)
      qface_ok=qface_ok.and.all(words==identity_face(2*x-1:2*x,r))
      words=transfer(nface(x),words)
      nface_ok=nface_ok.and.all(words==identity_face(8+2*x-1:8+2*x,r))
    end do
    write(*,'(A,1X,I0,4(1X,L1),4(1X,Z16.16))') 'IDENTITY_REPLAY',r,valid,nvalid,qface_ok,nface_ok, &
      transfer(inc,0_int64),identity64(3,r),transfer(ninc,0_int64),identity64(4,r)
  end do
  do r=1,size(store64,2)
    q=transfer(store64(1,r),q); n=transfer(store64(2,r),n)
    qs=transfer(store64(3,r),qs); ns=transfer(store64(4,r),ns)
    qa=transfer(store64(5,r),qa); na=transfer(store64(6,r),na)
    rho=transfer(store64(7,r),rho); mn=transfer(store64(8,r),mn); mx=transfer(store64(9,r),mx)
    oldmass=transfer(store64(10,r),oldmass); newmass=transfer(store64(11,r),newmass)
    qbase=transfer(store64(12,r),qbase); nbase=transfer(store64(13,r),nbase)
    dt64=real(transfer(store32(1,r),0.0_real32),real64)
    candidate_q_bits=transfer((oldmass*qbase+dt64*(qs+qa))/newmass,candidate_q_bits)
    candidate_n_bits=transfer((oldmass*nbase+dt64*(ns+na))/newmass,candidate_n_bits)
    formula_ok=candidate_q_bits==store64(1,r).and.candidate_n_bits==store64(2,r)
    rho32=transfer(store32(4,r),rho32)
    call joint_moment_store(q,n,rho32,mn,mx,.true.,sq,sn,adj,valid, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      failure_stage=stage)
    call policy_store(q,n,rho32,mn,mx,.true.,psq,psn,padj,pvalid, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
      allow_bulk_volume_quantum_absence=.true.,failure_stage=pstage)
    stored_strict=.false.
    if (pvalid) stored_strict=strict_graupel_pair(real(psq,real64),real(psn,real64),mn,mx)
    write(*,'(A,1X,I0,1X,L1,1X,I0,1X,I0,1X,L1,1X,I0,1X,L1,1X,I0,1X,L1,2(1X,Z8.8))') &
      'STORE_REPLAY',r,formula_ok,stage,adj,valid,pstage,pvalid,padj,stored_strict, &
      transfer(psq,0_int32),transfer(psn,0_int32)
  end do
contains
  subroutine load_producer(row)
    integer,intent(in) :: row
    integer :: xx,yy
    field=0.0_real32; field_n=0.0_real32; mut_diff=0.0_real32; xkmhd_diff=0.0_real32
    do yy=1,3
      do xx=1,3
        field(xx-2,1,yy-2)=transfer(producer_stencil(xx,yy+3*(row-1)),0.0_real32)
        xkmhd_diff(xx-2,1,yy-2)=transfer(producer_stencil(3+xx,yy+3*(row-1)),0.0_real32)
        mut_diff(xx-2,yy-2)=transfer(producer_stencil(6+xx,yy+3*(row-1)),0.0_real32)
      end do
    end do
    call load_metrics(producer_metrics(:,row))
    c1(1)=transfer(producer_scale(1,row),c1(1)); c2(1)=transfer(producer_scale(2,row),c2(1))
    rdx=transfer(producer_scale(3,row),rdx); rdy=transfer(producer_scale(4,row),rdy)
  end subroutine load_producer

  subroutine load_identity(row)
    integer,intent(in) :: row
    integer :: xx,yy
    field=0.0_real32; mut_diff=0.0_real32; xkmhd_diff=0.0_real32
    do yy=1,3
      do xx=1,3
        field(xx-2,1,yy-2)=transfer(identity_stencil(xx,yy+3*(row-1)),0.0_real32)
        field_n(xx-2,1,yy-2)=transfer(identity_stencil(3+xx,yy+3*(row-1)),0.0_real32)
        xkmhd_diff(xx-2,1,yy-2)=transfer(identity_stencil(6+xx,yy+3*(row-1)),0.0_real32)
        mut_diff(xx-2,yy-2)=transfer(identity_stencil(9+xx,yy+3*(row-1)),0.0_real32)
      end do
    end do
    call load_metrics(identity_metrics(:,row))
    c1(1)=real(transfer(identity64(8,row),0.0_real64),real32)
    c2(1)=real(transfer(identity64(9,row),0.0_real64),real32)
    rdx=real(transfer(identity64(10,row),0.0_real64),real32)
    rdy=real(transfer(identity64(11,row),0.0_real64),real32)
  end subroutine load_identity

  subroutine load_metrics(m)
    integer(int32),intent(in) :: m(10)
    msfux_diff(0,0)=transfer(m(1),0.0_real32); msfux_diff(1,0)=transfer(m(2),0.0_real32)
    msfuy_diff(0,0)=transfer(m(3),0.0_real32); msfuy_diff(1,0)=transfer(m(4),0.0_real32)
    msfvx_inv_diff(0,0)=transfer(m(5),0.0_real32); msfvx_inv_diff(0,1)=transfer(m(6),0.0_real32)
    msfvy_diff(0,0)=transfer(m(7),0.0_real32); msfvy_diff(0,1)=transfer(m(8),0.0_real32)
    msftx(0,0)=transfer(m(9),0.0_real32); msfty(0,0)=transfer(m(10),0.0_real32)
  end subroutine load_metrics
end program source_store_replay
