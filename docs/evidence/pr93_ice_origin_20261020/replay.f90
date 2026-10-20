program replay_guard
 use iso_fortran_env, only: real32,real64,int32
 use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
 implicit none
 real(real32) :: qc,nc,qi,ni,rho,qca,nca,qia,nia,pidnc,pidni,pi
 real(real32) :: lamdacmin,lamdacmax,lamdaimin,lamdaimax,dmc,dmi,lambda
 real(real32) :: native_number,directed_number,lo_tol,hi_tol
 real(real64) :: cmin,cmax,imin,imax,mean_mass,request_q,request_n,approved_q,approved_n,fraction
 real(real64) :: exact_min,exact_max
 logical :: legacy_available,valid,base_valid,accepted,source_cone_fail,old_branch
 integer(int32) :: bits
 integer :: stage
 character(len=6) :: stage_name
 external :: pr85_kdm6_psd_bound_number,pr85_kdm6_freezing_packet
 pi=4.0_real32*atan(1.0_real32)
 pidnc=transfer(int(z'4402EFA4',int32),0.0_real32)
 pidni=transfer(int(z'44C4597C',int32),0.0_real32)
 lamdacmin=12000.0_real32; lamdacmax=500000.0_real32
 lamdaimin=9080.0_real32; lamdaimax=1820000.0_real32
 dmc=3.0_real32; dmi=3.0_real32
 qc=transfer(int(z'376296F1',int32),0.0_real32)
 nc=transfer(int(z'4C22685A',int32),0.0_real32)
 qi=transfer(int(z'3623A538',int32),0.0_real32)
 ni=transfer(int(z'441BBBE7',int32),0.0_real32)
 rho=transfer(int(z'3F0938B8',int32),0.0_real32)
 request_q=2.1296498102647661e-13_real64
 request_n=5.0349597749963093e-01_real64
 cmin=real(pidnc,real64)/(real(lamdacmax,real64)**real(dmc,real64))
 cmax=real(pidnc,real64)/(real(lamdacmin,real64)**real(dmc,real64))
 imin=real(pidni,real64)/(real(lamdaimax,real64)**real(dmi,real64))
 imax=real(pidni,real64)/(real(lamdaimin,real64)**real(dmi,real64))
 lo_tol=8.0_real32*spacing(real(imin,real32))
 hi_tol=8.0_real32*spacing(real(imax,real32))
 do stage=1,3
   select case(stage)
   case(1); stage_name='stage1'
   case(2); stage_name='stage2'
   case(3); stage_name='stage3'
   end select
   lambda=exp(log((pidni*ni)/(rho*qi))*(1.0_real32/dmi))
   mean_mass=real(rho,real64)*real(qi,real64)/real(ni,real64)
   old_branch=lambda<=lamdaimin
   source_cone_fail=mean_mass<imin-real(lo_tol,real64) .or. &
                    mean_mass>imax+real(hi_tol,real64)
   bits=transfer(lambda,bits)
   print '(a,1x,i1,1x,z8.8,1x,l1,1x,l1,1x,1p,2e24.16)', &
        'PSD_GUARD',stage,bits,old_branch,source_cone_fail,mean_mass,imax
   if (source_cone_fail) then
     call pr85_kdm6_psd_bound_number(qi,rho,lamdaimin,lamdaimin,lamdaimax,pidni,dmi,1, &
          'ice',trim(stage_name),230,247,20,ni,legacy_available,.false.,0,native_number,directed_number, &
          exact_min,exact_max,valid)
     if (.not.valid) error stop 'existing PSD bound helper rejected captured state'
     ni=directed_number
     mean_mass=real(rho,real64)*real(qi,real64)/real(ni,real64)
     print '(a,1x,i1,1x,l1,1x,z8.8,1x,es24.16,1x,es24.16)', &
          'BOUND_HELPER',stage,valid,transfer(ni,bits),real(ni,real64),mean_mass
   endif
 enddo
 call pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,real(nearest(1.0e-14_real32,-1.0_real32),real64), &
      request_q,request_n,cmin,cmax,imin,imax,qca,nca,qia,nia,approved_q,approved_n,fraction,base_valid,accepted)
 print '(a,2(1x,l1),1x,1p,3e24.16)','PACKET_RESULT',base_valid,accepted,fraction,approved_q,approved_n
end program
