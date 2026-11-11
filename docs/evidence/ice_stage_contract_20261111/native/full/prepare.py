#!/usr/bin/env python3
"""Add write-only probes to the SHA-pinned whole CONTROL routine."""
from pathlib import Path
import hashlib,sys
s=Path(sys.argv[1]).read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
def after(needle, text):
 global s
 assert s.count(needle)==1,(needle,s.count(needle))
 s=s.replace(needle,needle+'\n'+text,1)
def before(needle,text):
 global s
 assert s.count(needle)==1,(needle,s.count(needle))
 s=s.replace(needle,text+'\n'+needle,1)
def record(stage,loop,qi,ni,den,lam='-1.0'):
 return f"write(89,'(a,1x,3(i0,1x),5(es24.16e3,1x))') '{stage}', {loop}, i, k, {qi}, {ni}, {den}, {lam}, t(i,k)"
after('         nci(i,k,2) = ni(i,k,j)*den(i,k,j)',record('WRAPPER', '0','qci(i,k,2)','nci(i,k,2)','den(i,k,j)'))
after('       nci(i,k,2) = min(max(nci(i,k,2),0.0),1.0e6)',record('ENTRY','0','qci(i,k,2)','nci(i,k,2)','den(i,k)'))
needle='   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &\n                   rslopeb,rslope2,rslope3,rslopemu,rsloped,work1,workn,its, &\n                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)'
assert needle in s
s=s.replace(needle,needle+"\ndo k=kts,kte\n do i=its,ite\n"+record('SLOPE','loop','qci_tmp(i,k)','nci_tmp(i,k)','den_tmp(i,k)','rslope(i,k,4)')+'\n enddo\nenddo',1)
markers=[('          if(qci(i,k,2) .ge. 1.e-14 ) then','          if(supcol.gt.2.'),('          if(qci(i,k,2).ge. 1.e-14 ) then','          avedia(i,k,1) ='),('          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then','            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)')]
for n,(a,b) in enumerate(markers,1):
 start=s.index(a); end=s.index(b,start)
 part=s[start:end]
 pre=record(f'PSD{n}_PRE','loop','qci(i,k,2)','nci(i,k,2)','den(i,k)')
 post=record(f'PSD{n}_POST','loop','qci(i,k,2)','nci(i,k,2)','den(i,k)')
 # Separate active-stage record ensures lambda is read only when assigned.
 active=record(f'PSD{n}_ACTIVE','loop','qci(i,k,2)','nci(i,k,2)','den(i,k)','lamdi_tmp(i,k)')
 idx=part.rfind('          endif'); assert idx>=0
 part=part[:idx]+active+'\n'+part[idx:]
 s=s[:start]+pre+'\n'+part+post+'\n'+s[end:]
after('         ni(i,k,j) = nci(i,k,2)/den(i,k,j)',record('FINAL','0','qci(i,k,2)','nci(i,k,2)','den(i,k,j)'))
Path('instrumented.f90').write_text(s)
print('instrumented_sha256',hashlib.sha256(s.encode()).hexdigest())
