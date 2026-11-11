#!/usr/bin/env python3
"""Build streaming oracle from the independently source-extracted boundary unit."""
from pathlib import Path
import hashlib,sys
s=Path(sys.argv[1]).read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='4c6022c4099d73aa4de13a772fb654dac7c81ba5a8f9f8f2bfd36a8b9f1b9e83'
header=s[:s.index('failures=0')]
header=header.replace('program boundary\nimplicit none','program oracle\nuse iso_fortran_env, only: int32\nimplicit none')
header=header.replace('logical :: active','logical :: active\ncharacter(8) :: mode\ninteger :: ios, active_int\ninteger(int32) :: ni_bits, aux_bits\nreal :: aux')
sub=s[s.index('subroutine ice_slope\n'):].replace('end program boundary','end program oracle')
main='''do
 read(*,*,iostat=ios) mode,den(1,1),qi_in,ni_in,qmin,ncmin
 if(ios < 0) exit
 if(ios /= 0) error stop 'invalid input'
 qci=0.; nci=0.; qci(1,1,2)=qi_in; nci(1,1,2)=ni_in
 active=.false.; aux=-1.
 select case(trim(mode))
 case('SLOPE')
  qci_tmp=qi_in; nci_tmp=ni_in
  call ice_slope
  active=qi_in>qmin
  aux=rslope(1,1,4)
 case('PSD1')
  call psd(1)
 case('PSD2')
  call psd(2)
 case('PSD3')
  call psd(3)
 case default
  error stop 'invalid mode'
 end select
 if(trim(mode)/='SLOPE' .and. active) aux=lamdi_tmp(1,1)
 active_int=0
 if(active) active_int=1
 ni_bits=transfer(nci(1,1,2),ni_bits)
 aux_bits=transfer(aux,aux_bits)
 write(*,'(a,1x,z8.8,1x,z8.8,1x,i0)') trim(mode),ni_bits,aux_bits,active_int
end do
contains
'''
out=header+main+sub
Path('oracle.f90').write_text(out)
print('boundary_sha256',hashlib.sha256(s.encode()).hexdigest())
print('oracle_sha256',hashlib.sha256(out.encode()).hexdigest())
