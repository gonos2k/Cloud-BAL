#!/usr/bin/env python3
"""Extract the native rain-intercept and raw PREVP statements into a small driver."""
import hashlib
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(source).hexdigest() == 'f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
s = source.decode()
n0 = s[s.index('          n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)', s.index('n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)') + 1):]
first = n0.splitlines()[0]
branch = n0[n0.index('          if(qrs(i,k,1).ge.qcrmin'):n0.index('          if(qci(i,k,1).ge.qmin')]
raw = s[s.index('          if(qrs(i,k,1).gt.0.) then\n            coeres'):]
raw = raw[:raw.index('            if (diagnostic_trace_active')]
program = '''program rain_proof
implicit none
integer :: i,k,case_id
real :: qrs(1,1,1), nrs(1,1,1), den(1,1), rslope(1,1,1), rslopemu(1,1,1)
real :: rslope2(1,1,1), rslopeb(1,1,1), n0r(1,1), lamdr_tmp(1,1), rh(1,1,1)
real :: work1(1,1,1), work2(1,1), prevp(1,1), coeres, pidnr, pi, g1pmr, precr1,precr2
real, parameter :: mur=1., dmr=3., qcrmin=1.e-9, nrmin=1.e-2, lamdarmin=9.61e2, lamdarmax=3.5e4
real, parameter :: fac_evap=1., avtr=841.9, bvtr=0.8
real :: results(2)
i=1; k=1; pi=4.*atan(1.); g1pmr=gamma(1.+mur)
pidnr=(pi*1000./6.)*gamma(1.+dmr+mur)/g1pmr
precr1=2.*pi*.78*gamma(2.+mur)
precr2=2.*pi*.31*sqrt(avtr)*gamma(2.5+.5*bvtr+mur)
den=1.; qrs=1.e-4; rh=.8; work1=1.; work2=1.
rslope=1./20000.; rslopemu=rslope**mur; rslope2=rslope**2; rslopeb=rslope**bvtr
do case_id=1,2
 nrs=0.
 if (case_id==2) nrs=den(1,1)*qrs(1,1,1)*20000.**dmr/pidnr
 prevp=0.
''' + first + '\n' + branch + raw + '''          endif
 results(case_id)=prevp(1,1)
 print '(a,i1,a,es14.6,a,es14.6)', 'case=',case_id,' Nvol=',nrs(1,1,1),' raw_PREVP=',results(case_id)
enddo
if (results(1)/=0. .or. results(2)>=0.) error stop 'unexpected native raw rain response'
print '(a)', 'PASS: positive rain, zero vs positive number'
end program
'''
pathlib.Path('rain_proof.f90').write_text(program)
