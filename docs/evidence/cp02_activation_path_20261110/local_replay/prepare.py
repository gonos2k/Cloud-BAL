#!/usr/bin/env python3
"""Extract the unmodified activation and NN clamp statements from native MP10."""
from pathlib import Path
import hashlib
import sys

source = Path(sys.argv[1]).read_text()
start = source.index('           if(sw(i,k).gt.0.) then', source.index('sw(i,k) = (rh(i,k,1)-1.)*100.', source.index('sw(i,k) = (rh(i,k,1)-1.)*100.') + 1))
end = source.index('          endif', start) + len('          endif')
activation = source[start:end]
floor = '            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)'
if source.count(floor) != 1:
    raise ValueError('expected one internal NN floor')
for declaration in ('real, parameter, private :: actk    = 0.6', 'real, parameter, private :: actr    = 1.5'):
    if declaration not in source:
        raise ValueError('activation constants changed')
output = '''module extracted_activation
implicit none
contains
subroutine step(sw, q, qci, nci, t, den, xl, cpm, dtcld, pi, denr, floor_after)
real :: sw(1,1), q(1,1), qci(1,1,1), nci(1,1,3), t(1,1), den(1,1), xl(1,1), cpm(1,1)
real :: ncact(1,1), pcact(1,1), dtcld, pi, denr
real, parameter :: actk=0.6, actr=1.5
integer, parameter :: i=1, k=1
logical :: floor_after
''' + activation + '\nif (floor_after) then\n' + floor + '\nend if\nend subroutine\nend module\n'
Path('extracted.f90').write_text(output)
print('source_sha256', hashlib.sha256(source.encode()).hexdigest())
print('extracted_sha256', hashlib.sha256(output.encode()).hexdigest())
