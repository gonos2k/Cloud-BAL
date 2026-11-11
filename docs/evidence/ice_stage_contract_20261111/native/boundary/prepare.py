#!/usr/bin/env python3
"""Extract and exercise the source gates and ice lambda limiters."""
import hashlib,sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
def section(a,b):
 i=s.index(a); return s[i:s.index(b,i)]
def unique(a):
 matches=[v for v in s.splitlines() if v.strip()==a]; assert len(matches)==1,(a,len(matches)); return matches[0]+'\n'
constants=''.join(unique(x).replace(', private','') for x in ['real, parameter, private :: deni    = 500.0','real, parameter, private :: bvti    = 1.0','real, parameter, private :: lamdaimax = 1.82e6','real, parameter, private :: lamdaimin = 9.08e3','real, parameter, private :: dmi = 3.0','real, parameter, private :: mui = 0.'])
gamma=section('        REAL FUNCTION GAMMLN(x)','   real function fpvs(')
init=''.join(unique(x) for x in ['pi = 4.*atan(1.)','cmi = pi*deni/6.','mui1 = 1. + mui','g1pmi = rgmma(mui1)','dimui1 = 1.+dmi + mui','g1pdimi = rgmma(dimui1)','pidni = cmi*g1pdimi/g1pmi','rslopeimax = 1./lamdaimax','rslopeibmax = rslopeimax ** bvti','rslopeidmax = (rslopeimax) ** dmi','rslopei2max = (rslopeimax) * rslopeimax','rslopei3max = (rslopei2max) * rslopeimax'])+'rslopeimmax = 1.\n'
slope=section('          if(qci(i,k) .le. qmin) then','          vt(i,k,1) = DBLE(pvtr)')
slope=slope.replace('qci(i,k)','qci_tmp(i,k)').replace('nci(i,k)','nci_tmp(i,k)')
blocks=[]
for a,b in [('          if(qci(i,k,2) .ge. 1.e-14 ) then','          if(supcol.gt.2.'),('          if(qci(i,k,2).ge. 1.e-14 ) then','          avedia(i,k,1) ='),('          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then','            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)')]:
 block=section(a,b); block=block.replace(a,a+'\nactive=.true.',1); blocks.append(block)
limiter=section('            if(lamdi_tmp(i,k) .le. lamdaimin) then','          if(supcol.gt.2.')
limiter=limiter[:limiter.rfind('          endif')]
limiter=limiter.replace('              lamdi_tmp(i,k) = lamdaimin','              branch=1\n              lamdi_tmp(i,k) = lamdaimin',1).replace('              lamdi_tmp(i,k) = lamdaimax','              branch=2\n              lamdi_tmp(i,k) = lamdaimax',1)
header='''program boundary
implicit none
'''+constants+'''real :: den(1,1),qci(1,1,2),nci(1,1,3),qci_tmp(1,1),nci_tmp(1,1),qmin,ncmin
real :: rslope(1,1,4),rslopeb(1,1,4),rsloped(1,1,4),rslope2(1,1,4),rslope3(1,1,4)
double precision :: rslopemu(1,1,4),n0i(1,1)
real :: rslopeimax,rslopeibmax,rslopeidmax,rslopei2max,rslopei3max,rslopeimmax
real :: pi,cmi,mui1,g1pmi,dimui1,g1pdimi,pidni,lamdi_tmp(1,1),x,y,z,lamdai
real :: threshold,qi_in,ni_in,lambda_in
integer :: which,side,branch,failures
integer,parameter :: i=1,k=1
logical :: active
lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))
'''
main='''failures=0
den=1.; qmin=1.e-15; ncmin=10.
! First slope: QI <= qmin defaults; immediately above with zero NI takes zero fallback.
do side=-1,1
 qi_in=qmin
 if(side==-1) qi_in=nearest(qmin,-1.)
 if(side==1) qi_in=nearest(qmin,1.)
 qci_tmp=qi_in; nci_tmp=0.
 call ice_slope
 if(side<=0) then
  call check(rslope(1,1,4)==1./lamdaimax,'slope default',side)
 else
  call check(rslope(1,1,4)==1./lamdaimin,'slope zero NI fallback',side)
 endif
enddo
! Both main PSD gates activate at QI == 1e-14 even with zero NI.
threshold=1.e-14
do which=1,2
 do side=-1,1
  qi_in=threshold
  if(side==-1) qi_in=nearest(threshold,-1.)
  if(side==1) qi_in=nearest(threshold,1.)
  qci=0.;nci=0.;qci(1,1,2)=qi_in;active=.false.
  call psd(which)
  call check(active .eqv. (side>=0),'PSD1/2 threshold',side)
  call check((nci(1,1,2)>0.) .eqv. (side>=0),'PSD1/2 zero NI reconstruction',side)
 enddo
enddo
! Third gate requires QI >= qmin and NI >= ncmin, including equality.
do side=-1,1
 qi_in=qmin
 if(side==-1) qi_in=nearest(qmin,-1.)
 if(side==1) qi_in=nearest(qmin,1.)
 qci=0.;nci=0.;qci(1,1,2)=qi_in;nci(1,1,2)=ncmin;active=.false.
 call psd(3)
 call check(active .eqv. (side>=0),'PSD3 QI threshold',side)
 ni_in=ncmin
 if(side==-1) ni_in=nearest(ncmin,-1.)
 if(side==1) ni_in=nearest(ncmin,1.)
 qci=0.;nci=0.;qci(1,1,2)=qmin;nci(1,1,2)=ni_in;active=.false.
 call psd(3)
 call check(active .eqv. (side>=0),'PSD3 NI threshold',side)
enddo
! Direct supplied lambda tests the extracted limiter, not exp(log()) rounding.
do which=1,2
 do side=-1,1
  if(which==1) threshold=lamdaimin
  if(which==2) threshold=lamdaimax
  lamdi_tmp=threshold
  if(side==-1) lamdi_tmp=nearest(threshold,-1.)
  if(side==1) lamdi_tmp=nearest(threshold,1.)
  lambda_in=lamdi_tmp(1,1)
  qci=0.;nci=0.;qci(1,1,2)=1.e-5;nci(1,1,2)=10.;branch=0
  call limit
  if(which==1) call check((branch==1) .eqv. (side<=0),'lower lambda limiter',side)
  if(which==2) call check((branch==2) .eqv. (side>=0),'upper lambda limiter',side)
  if(branch/=0) then
   call check(lamdi_tmp(1,1)==threshold,'lambda clamped',side)
  else
   call check(lamdi_tmp(1,1)==lambda_in,'lambda unchanged',side)
  endif
 enddo
enddo
if(failures/=0) error stop 1
print '(a)', 'BOUNDARY PASS'
contains
subroutine check(condition,label,side)
logical,intent(in)::condition
character(*),intent(in)::label
integer,intent(in)::side
write(*,'(a,1x,i0,1x,l1)') label,side,condition
if(.not.condition) failures=failures+1
end subroutine
subroutine ice_slope
'''+slope+'''end subroutine
subroutine psd(which_psd)
integer,intent(in)::which_psd
select case(which_psd)
case(1)
'''+blocks[0]+'''case(2)
'''+blocks[1]+'''case(3)
'''+blocks[2]+'''end select
end subroutine
subroutine limit
'''+limiter+'''end subroutine
'''+gamma+'''end program boundary
'''
out=header+init+main
Path('boundary.f90').write_text(out)
print('source_sha256',hashlib.sha256(s.encode()).hexdigest())
print('generated_sha256',hashlib.sha256(out.encode()).hexdigest())
