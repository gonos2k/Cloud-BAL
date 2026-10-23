subroutine pr100_norm_observe(before,after,ncol,ix,invalid,changed,maxchange)
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  real,intent(in)::before(6),after(6)
  integer,intent(in)::ncol,ix
  integer,intent(inout)::invalid(ncol),changed(ncol)
  real(8),intent(inout)::maxchange(ncol)
  integer::n
  do n=1,6
    if (.not.ieee_is_finite(before(n)).or.before(n)<0.) invalid(ix)=invalid(ix)+1
    if (before(n)/=after(n)) then
      changed(ix)=changed(ix)+1
      if (ieee_is_finite(before(n)).and.ieee_is_finite(after(n))) &
        maxchange(ix)=max(maxchange(ix),abs(dble(after(n))-dble(before(n))))
    endif
  enddo
end subroutine pr100_norm_observe

subroutine pr100_norm_write_columns(lat,its,ite,invalid,changed,maxchange)
  implicit none
  integer,intent(in)::lat,its,ite,invalid(ite-its+1),changed(ite-its+1)
  real(8),intent(in)::maxchange(ite-its+1)
  integer::i,u,ios
  open(newunit=u,file='pr100_norm_check.raw',form='formatted',status='unknown', &
       position='append',action='write',iostat=ios)
  if(ios.ne.0) error stop 'PR100 normalization check open failed'
  do i=its,ite
    write(u,'(a,4i10,1p,e24.16)',iostat=ios) 'PR100_NORM_COLUMN',i,lat,invalid(i-its+1), &
         changed(i-its+1),maxchange(i-its+1)
    if(ios.ne.0) error stop 'PR100 normalization check write failed'
  enddo
  close(u,iostat=ios)
  if(ios.ne.0) error stop 'PR100 normalization check close failed'
end subroutine pr100_norm_write_columns

subroutine pr100_unowned_event(site,i,j,k,loop,before,after,den,dz,ncol,ix,donor,receiver, &
     signed,signed_c,l1,l1_c,max_event,event_count)
  implicit none
  integer,intent(in)::site,i,j,k,loop,ncol,ix,donor,receiver
  real,intent(in)::before(6),after(6),den,dz
  real(8),intent(inout)::signed(ncol,3),signed_c(ncol,3),l1(ncol,3),l1_c(ncol,3),max_event(ncol,3)
  integer,intent(inout)::event_count(ncol,3)
  integer::u,ios
  real(8)::pre_total,post_total,delta,weight,approved
  real(8)::qbefore(6),qafter(6)
  qbefore=dble(before); qafter=dble(after)
  pre_total=sum(qbefore); post_total=sum(qafter)
  delta=post_total-pre_total
  weight=dble(den)*dble(dz)
  approved=qbefore(donor)
  call pr100_unowned_kahan(weight*delta,signed(ix,site),signed_c(ix,site))
  call pr100_unowned_kahan(abs(weight*delta),l1(ix,site),l1_c(ix,site))
  max_event(ix,site)=max(max_event(ix,site),abs(weight*delta))
  event_count(ix,site)=event_count(ix,site)+1
  if ((i.eq.203.and.j.eq.81).or.(i.eq.205.and.j.eq.230).or. &
      (i.eq.146.and.j.eq.215)) then
    open(newunit=u,file='pr100_unowned_selected.raw',form='formatted',status='unknown', &
         position='append',action='write',iostat=ios)
    if(ios.ne.0) error stop 'PR100 unowned selected open failed'
    write(u,'(a,6i10,1p,18e24.16)',iostat=ios) 'PR100_UNOWNED',site,i,j,k,loop,event_count(ix,site), &
         den,dz,approved,pre_total,post_total,delta,before,after
    if(ios.ne.0) error stop 'PR100 unowned selected write failed'
    close(u,iostat=ios)
    if(ios.ne.0) error stop 'PR100 unowned selected close failed'
  endif
end subroutine pr100_unowned_event

subroutine pr100_unowned_kahan(x,total,correction)
  implicit none
  real(8),intent(in)::x
  real(8),intent(inout)::total,correction
  real(8)::y,t
  y=x-correction
  t=total+y
  correction=(t-total)-y
  total=t
end subroutine pr100_unowned_kahan

subroutine pr100_unowned_write_columns(lat,its,ite,event_count,signed,l1,max_event)
  implicit none
  integer,intent(in)::lat,its,ite,event_count(ite-its+1,3)
  real(8),intent(in)::signed(ite-its+1,3),l1(ite-its+1,3),max_event(ite-its+1,3)
  integer::i,site,u,ios
  open(newunit=u,file='pr100_unowned_columns.raw',form='formatted',status='unknown', &
       position='append',action='write',iostat=ios)
  if(ios.ne.0) error stop 'PR100 unowned summary open failed'
  do i=its,ite
    do site=1,3
      write(u,'(a,4i10,1p,3e24.16)',iostat=ios) 'PR100_UNOWNED_COLUMN',i,lat,site, &
           event_count(i-its+1,site),signed(i-its+1,site),l1(i-its+1,site),max_event(i-its+1,site)
      if(ios.ne.0) error stop 'PR100 unowned summary write failed'
    enddo
  enddo
  close(u,iostat=ios)
  if(ios.ne.0) error stop 'PR100 unowned summary close failed'
end subroutine pr100_unowned_write_columns
program pr100_unowned_harness
  implicit none
  real :: before(6),after(6),den,dz
  real(8) :: signed(4,3),signed_c(4,3),l1(4,3),l1_c(4,3),max_event(4,3)
  integer :: event_count(4,3),invalid(4),changed(4)
  real(8) :: maxchange(4),expected(3)
  integer :: site
  signed=0.d0; signed_c=0.d0; l1=0.d0; l1_c=0.d0; max_event=0.d0; event_count=0; expected=0.d0
  invalid=0; changed=0; maxchange=0.d0
  den=2.; dz=3.
  do site=1,3
    before=[0.1,0.2,0.3,0.,0.,0.]
    after=before
    select case(site)
    case(1)
      after(2)=before(2)+before(3); after(3)=0.
      expected(site)=dble(den)*dble(dz)*(sum(dble(after))-sum(dble(before)))
      call pr100_unowned_event(site,10,15,7,1,before,after,den,dz,4,2,2,3, &
           signed,signed_c,l1,l1_c,max_event,event_count)
    case(2)
      after(3)=before(3)+before(2); after(2)=0.
      expected(site)=dble(den)*dble(dz)*(sum(dble(after))-sum(dble(before)))
      call pr100_unowned_event(site,10,15,7,1,before,after,den,dz,4,2,3,2, &
           signed,signed_c,l1,l1_c,max_event,event_count)
    case(3)
      after(2)=before(2)+before(4); after(4)=0.
      expected(site)=dble(den)*dble(dz)*(sum(dble(after))-sum(dble(before)))
      call pr100_unowned_event(site,10,15,7,1,before,after,den,dz,4,2,2,4, &
           signed,signed_c,l1,l1_c,max_event,event_count)
    end select
  enddo
  if(any(event_count(2,:)/=1)) error stop 'unowned event index/counter failure'
  if(any(abs(signed(2,:)-expected)>1.d-15)) error stop 'unowned R32 endpoint delta mismatch'
  before=[0.1,0.2,0.3,0.,0.,0.]; after=before
  call pr100_norm_observe(before,after,4,2,invalid,changed,maxchange)
  if(invalid(2)/=0.or.changed(2)/=0) error stop 'normalization clean fixture failed'
  before(5)=-1.; after(5)=0.
  call pr100_norm_observe(before,after,4,2,invalid,changed,maxchange)
  if(invalid(2)/=1.or.changed(2)/=1.or.maxchange(2)/=1.d0) error stop 'normalization change fixture failed'
  print *, 'PR100_UNOWNED_HELPER_PASS sites=3 clean+negative-clamp fixtures'
end program pr100_unowned_harness
