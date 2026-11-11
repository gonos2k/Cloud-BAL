#!/usr/bin/env python3
"""Extract fixed-state ice operators from the pinned CONTROL source."""
from pathlib import Path
import hashlib
import sys
s = Path(sys.argv[1]).read_text()
assert hashlib.sha256(s.encode()).hexdigest() == 'f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
def section(a,b):
    start=s.index(a); return s[start:s.index(b,start)+len(b)]
def line(a):
    matches=[x for x in s.splitlines() if x.strip()==a]
    assert len(matches)==1, (a,len(matches))
    return matches[0]+'\n'
constants=''.join(line(a).replace(', private','') for a in ['real, parameter, private :: deni    = 500.0','real, parameter, private :: bvti    = 1.0','real, parameter, private :: lamdaimax = 1.82e6','real, parameter, private :: lamdaimin = 9.08e3','real, parameter, private :: dmi = 3.0','real, parameter, private :: mui = 0.'])
gamma=section('        REAL FUNCTION GAMMLN(x)','      END FUNCTION rgmma')
slope=section('          if(qci(i,k) .le. qmin) then', '          vt(i,k,1) = DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)')
slope=slope[:slope.rfind('          vt(i,k,1)')]
slope=slope.replace('qci(i,k)', 'qci_tmp(i,k)').replace('nci(i,k)', 'nci_tmp(i,k)')
psd=section('          if(qci(i,k,2) .ge. 1.e-14 ) then','          endif') # nested endif; use next known marker
start=s.index('          if(qci(i,k,2) .ge. 1.e-14 ) then'); end=s.index('          if(supcol.gt.2.',start); psd=s[start:end]
init=''.join(line(x) for x in ['pi = 4.*atan(1.)','cmi = pi*deni/6.','mui1 = 1. + mui','g1pmi = rgmma(mui1)','dimui1 = 1.+dmi + mui','g1pdimi = rgmma(dimui1)','pidni = cmi*g1pdimi/g1pmi','rslopeimax = 1./lamdaimax','rslopeibmax = rslopeimax ** bvti','rslopeidmax = (rslopeimax) ** dmi','rslopei2max = (rslopeimax) * rslopeimax','rslopei3max = (rslopei2max) * rslopeimax'])+'rslopeimmax = 1.\n'
header='''program audit
implicit none
'''+constants+'''real :: qci_tmp(1,1), nci_tmp(1,1)
real :: den(1,1), qci(1,1,2), nci(1,1,3), nkg, qmin, pi, cmi, mui1, g1pmi, dimui1, g1pdimi, pidni
real :: rslope(1,1,4), rslopeb(1,1,4), rsloped(1,1,4), rslope2(1,1,4), rslope3(1,1,4)
double precision :: rslopemu(1,1,4), n0i(1,1)
real :: rslopeimax, rslopeibmax, rslopeidmax, rslopei2max, rslopei3max
real :: x,y,z,lamdai,lamdi_tmp(1,1), capped, first_slope
integer, parameter :: i=1,k=1
integer :: ios
real :: rslopeimmax
lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))
'''
body=init+'''do
 read(*,*,iostat=ios) den(1,1),qci(1,1,2),nkg,qmin
 if(ios /= 0) exit
 nci(1,1,2)=nkg*den(1,1)
'''+line('nci(i,k,2) = min(max(nci(i,k,2),0.0),1.0e6)')+'''capped=nci(1,1,2)
qci_tmp=qci(:,:,2)
nci_tmp=nci(:,:,2)
'''+slope+'''first_slope=rslope(1,1,4)
lamdi_tmp=0.
'''+psd+'''write(*,'(6(es24.15e3,1x))') den(1,1),qci(1,1,2),nkg,capped,first_slope,nci(1,1,2)
end do
contains
'''+gamma+'\nend program audit\n'
out=header+body
Path('extracted.f90').write_text(out)
print('source_sha256',hashlib.sha256(s.encode()).hexdigest())
print('extracted_sha256',hashlib.sha256(out.encode()).hexdigest())
