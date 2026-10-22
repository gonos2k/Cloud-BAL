from pathlib import Path
base=Path('/var/tmp/pr100_snow_build_20261022/source/module_mp_kdm6_snow.f90')
out=Path('/var/tmp/pr100_snow_build_20261022/source/module_mp_kdm6_snow_fulltile.f90')
s=base.read_text()
needle='   real(kind=8) :: pr89_cold_q(5),pr89_cold_qv,pr89_cold_alpha,pr89_cold_scale\n'
insert='''   real(kind=8) :: pr89_cold_q(5),pr89_cold_qv,pr89_cold_alpha,pr89_cold_scale
   real(8) :: pr100_qs_stored(ite-its+1),pr100_qs_stored_c(ite-its+1)
   real(8) :: pr100_qs_approved(ite-its+1),pr100_qs_approved_c(ite-its+1)
   real(8) :: pr100_qs_diff(ite-its+1),pr100_qs_diff_c(ite-its+1)
   real(8) :: pr100_qs_stored_l1(ite-its+1),pr100_qs_stored_l1_c(ite-its+1)
   real(8) :: pr100_qs_approved_l1(ite-its+1),pr100_qs_approved_l1_c(ite-its+1)
   real(8) :: pr100_qs_diff_l1(ite-its+1),pr100_qs_diff_l1_c(ite-its+1)
   real(8) :: pr100_qs_stored_max(ite-its+1),pr100_qs_approved_max(ite-its+1)
   real(8) :: pr100_qs_diff_max(ite-its+1),pr100_qs_bottom(ite-its+1)
   real(8) :: pr100_qs_bottom_c(ite-its+1),pr100_qs_bottom_r32(ite-its+1)
   real(8) :: pr100_qs_bottom_r32_c(ite-its+1)
   integer :: pr100_qs_count(ite-its+1),pr100_qs_top_clamps(ite-its+1)
   integer(kind=8) :: pr100_qs_steps(ite-its+1)
   integer :: pr100_qs_bottom_loops(ite-its+1)
   real :: pr100_qs_decrement,pr100_qs_bottom_r32_value
'''
assert s.count(needle)==1
s=s.replace(needle,insert)
needle='   idim = ite-its+1\n   kdim = kte-kts+1\n'
init='''   idim = ite-its+1
   kdim = kte-kts+1
   pr100_qs_stored=0.d0; pr100_qs_stored_c=0.d0
   pr100_qs_approved=0.d0; pr100_qs_approved_c=0.d0
   pr100_qs_diff=0.d0; pr100_qs_diff_c=0.d0
   pr100_qs_stored_l1=0.d0; pr100_qs_stored_l1_c=0.d0
   pr100_qs_approved_l1=0.d0; pr100_qs_approved_l1_c=0.d0
   pr100_qs_diff_l1=0.d0; pr100_qs_diff_l1_c=0.d0
   pr100_qs_stored_max=0.d0; pr100_qs_approved_max=0.d0
   pr100_qs_diff_max=0.d0; pr100_qs_bottom=0.d0
   pr100_qs_bottom_c=0.d0; pr100_qs_bottom_r32=0.d0; pr100_qs_bottom_r32_c=0.d0
   pr100_qs_count=0; pr100_qs_top_clamps=0
   pr100_qs_steps=0; pr100_qs_bottom_loops=0
'''
assert s.count(needle)==1
s=s.replace(needle,init)
# Top update: save the exact R32 decrement; preserve original physical assignment.
needle='''           pr100_qs_before=qrs(i,k,2)
           qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)
'''
rep='''           pr100_qs_before=qrs(i,k,2)
           pr100_qs_decrement=falk(i,k,2)*dtcld/dend(i,k)
           qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)
'''
assert s.count(needle)==1
s=s.replace(needle,rep)
# Add compact top event after selected-cell raw record.
needle='''                falk(i,k,2)*dtcld/dend(i,k))
          call pr99_total_checkpoint(i,k,lat,loop,2935'''
rep='''                falk(i,k,2)*dtcld/dend(i,k))
           call pr100_snow_compact_event(i-its+1,pr100_qs_before,qrs(i,k,2), &
                -dble(min(pr100_qs_before,pr100_qs_decrement)),den(i,k),delz(i,k),1,n,pr100_qs_decrement, &
                pr100_qs_stored,pr100_qs_stored_c,pr100_qs_approved,pr100_qs_approved_c, &
                pr100_qs_diff,pr100_qs_diff_c,pr100_qs_stored_l1,pr100_qs_stored_l1_c, &
                pr100_qs_approved_l1,pr100_qs_approved_l1_c,pr100_qs_diff_l1,pr100_qs_diff_l1_c, &
                pr100_qs_stored_max,pr100_qs_approved_max,pr100_qs_diff_max, &
                pr100_qs_count,pr100_qs_top_clamps,pr100_qs_steps)
          call pr99_total_checkpoint(i,k,lat,loop,2935'''
assert s.count(needle)==1
s=s.replace(needle,rep)
# Internal event uses R64 difference of independently represented dqs operands.
needle='''                  dqs(i,k),dqs(i,k+1),-dqs(i,k)+dqs(i,k+1))
          call pr99_total_checkpoint(i,k,lat,loop,2951'''
rep='''                  dqs(i,k),dqs(i,k+1),-dqs(i,k)+dqs(i,k+1))
             call pr100_snow_compact_event(i-its+1,pr100_qs_before,qrs(i,k,2), &
                  dble(dqs(i,k+1))-dble(dqs(i,k)),den(i,k),delz(i,k),2,n,0.0, &
                  pr100_qs_stored,pr100_qs_stored_c,pr100_qs_approved,pr100_qs_approved_c, &
                  pr100_qs_diff,pr100_qs_diff_c,pr100_qs_stored_l1,pr100_qs_stored_l1_c, &
                  pr100_qs_approved_l1,pr100_qs_approved_l1_c,pr100_qs_diff_l1,pr100_qs_diff_l1_c, &
                  pr100_qs_stored_max,pr100_qs_approved_max,pr100_qs_diff_max, &
                  pr100_qs_count,pr100_qs_top_clamps,pr100_qs_steps)
          call pr99_total_checkpoint(i,k,lat,loop,2951'''
assert s.count(needle)==1
s=s.replace(needle,rep)
# Accumulate actual source-bottom contribution at every existing per-loop output block.
needle='''        falls um = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)'''
# exact source spelling has no space
needle='''        fallsum = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)
        fallsum_qsi = fall(i,kts,2)+fall(i,kts,4)
'''
rep='''        fallsum = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)
        fallsum_qsi = fall(i,kts,2)+fall(i,kts,4)
        pr100_qs_bottom_r32_value=fall(i,kts,2)*delz(i,kts)/denr*dtcld*1000.
        call pr100_snow_kahan(dble(fall(i,kts,2))*dble(delz(i,kts))/dble(denr)*dble(dtcld)*1000.d0, &
             pr100_qs_bottom(i-its+1),pr100_qs_bottom_c(i-its+1))
        call pr100_snow_kahan(dble(pr100_qs_bottom_r32_value),pr100_qs_bottom_r32(i-its+1), &
             pr100_qs_bottom_r32_c(i-its+1))
        pr100_qs_bottom_loops(i-its+1)=pr100_qs_bottom_loops(i-its+1)+1
'''
assert s.count(needle)==1
s=s.replace(needle,rep)
# Emit one fixed-schema row per cell at end of each per-latitude call.
needle='''   call liquid_end(lat,its,ite)
   end subroutine kdm62d
'''
rep='''   call pr100_snow_write_columns(lat,its,ite,pr100_qs_count,pr100_qs_top_clamps, &
        pr100_qs_steps,pr100_qs_bottom_loops,pr100_qs_stored,pr100_qs_approved, &
        pr100_qs_diff,pr100_qs_stored_l1,pr100_qs_approved_l1,pr100_qs_diff_l1, &
        pr100_qs_stored_max,pr100_qs_approved_max,pr100_qs_diff_max, &
        pr100_qs_bottom,pr100_qs_bottom_r32)
   call liquid_end(lat,its,ite)
   end subroutine kdm62d
'''
assert s.count(needle)==1
s=s.replace(needle,rep)
# External helper. Only accumulates diagnostics; no model state is read/written here.
s += '''\nsubroutine pr100_snow_compact_event(ix,qbefore,qafter,approved,den,dz,kind,substep,top_decrement, &
     stored,stored_c,packet,packet_c,diff,diff_c,stored_l1,stored_l1_c,packet_l1,packet_l1_c, &
     diff_l1,diff_l1_c,stored_max,packet_max,diff_max,count,top_clamp,steps)
  implicit none
  integer,intent(in)::ix,kind,substep
  real,intent(in)::qbefore,qafter,den,dz,top_decrement
  real(8),intent(in)::approved
  real(8),intent(inout)::stored(*),stored_c(*),packet(*),packet_c(*),diff(*),diff_c(*)
  real(8),intent(inout)::stored_l1(*),stored_l1_c(*),packet_l1(*),packet_l1_c(*)
  real(8),intent(inout)::diff_l1(*),diff_l1_c(*),stored_max(*),packet_max(*),diff_max(*)
  integer,intent(inout)::count(*),top_clamp(*)
  integer(kind=8),intent(inout)::steps(*)
  real(8)::w,s,p,d
  real::candidate
  w=dble(den)*dble(dz)
  s=w*(dble(qafter)-dble(qbefore))
  p=w*approved
  d=s-p
  call pr100_snow_kahan(s,stored(ix),stored_c(ix))
  call pr100_snow_kahan(p,packet(ix),packet_c(ix))
  call pr100_snow_kahan(d,diff(ix),diff_c(ix))
  call pr100_snow_kahan(abs(s),stored_l1(ix),stored_l1_c(ix))
  call pr100_snow_kahan(abs(p),packet_l1(ix),packet_l1_c(ix))
  call pr100_snow_kahan(abs(d),diff_l1(ix),diff_l1_c(ix))
  stored_max(ix)=max(stored_max(ix),abs(s))
  packet_max(ix)=max(packet_max(ix),abs(p))
  diff_max(ix)=max(diff_max(ix),abs(d))
  count(ix)=count(ix)+1
  if (substep<1.or.substep>bit_size(steps(ix))) error stop 'PR100 snow invalid substep'
  steps(ix)=ibset(steps(ix),substep-1)
  if (kind==1) then
    candidate=qbefore-top_decrement
    if (candidate<0..and.qafter==0.) top_clamp(ix)=top_clamp(ix)+1
  endif
end subroutine pr100_snow_compact_event

subroutine pr100_snow_kahan(x,total,correction)
  implicit none
  real(8),intent(in)::x
  real(8),intent(inout)::total,correction
  real(8)::y,t
  y=x-correction
  t=total+y
  correction=(t-total)-y
  total=t
end subroutine pr100_snow_kahan

subroutine pr100_snow_write_columns(lat,its,ite,count,top_clamp,steps,bottom_loops, &
     stored,packet,diff,stored_l1,packet_l1,diff_l1,stored_max,packet_max,diff_max,bottom,bottom_r32)
  implicit none
  integer,intent(in)::lat,its,ite,count(ite-its+1),top_clamp(ite-its+1),bottom_loops(ite-its+1)
  integer(kind=8),intent(in)::steps(ite-its+1)
  real(8),intent(in)::stored(ite-its+1),packet(ite-its+1),diff(ite-its+1)
  real(8),intent(in)::stored_l1(ite-its+1),packet_l1(ite-its+1),diff_l1(ite-its+1)
  real(8),intent(in)::stored_max(ite-its+1),packet_max(ite-its+1),diff_max(ite-its+1)
  real(8),intent(in)::bottom(ite-its+1),bottom_r32(ite-its+1)
  integer::i,u,ios
  open(newunit=u,file='pr100_snow_columns.raw',form='formatted',status='unknown', &
       position='append',action='write',iostat=ios)
  if(ios/=0) error stop 'PR100 snow compact open failed'
  do i=its,ite
    write(u,'(a,6i10,1p,11e24.16)',iostat=ios) 'PR100_SNOW_COLUMN',i,lat, &
         count(i-its+1),top_clamp(i-its+1),steps(i-its+1),bottom_loops(i-its+1), &
         stored(i-its+1),packet(i-its+1),diff(i-its+1),stored_l1(i-its+1), &
         packet_l1(i-its+1),diff_l1(i-its+1),stored_max(i-its+1), &
         packet_max(i-its+1),diff_max(i-its+1),bottom(i-its+1),bottom_r32(i-its+1)
    if(ios/=0) error stop 'PR100 snow compact write failed'
  enddo
  close(u,iostat=ios)
  if(ios/=0) error stop 'PR100 snow compact close failed'
end subroutine pr100_snow_write_columns
'''
out.write_text(s)
print(out)
