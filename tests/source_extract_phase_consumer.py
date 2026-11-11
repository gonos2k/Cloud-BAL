#!/usr/bin/env python3
"""Extract the pinned native slope routine verbatim for an isolated test."""
import hashlib
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_bytes()
if hashlib.sha256(source).hexdigest() != 'f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595':
    raise SystemExit('native source hash mismatch')
text = source.decode()
start = text.index('      subroutine slope_rain(')
end = text.index('  END subroutine slope_rain', start) + len('  END subroutine slope_rain')
# Native parameter values and initialization for quantities used by slope_rain;
# velocity coefficients are irrelevant to the slope branch under examination.
preamble = '''module native_slope_test
  implicit none
  real, parameter :: qcrmin=1.e-9, nrmin=1.e-2, dmr=3., bvtr=0.8, mur=1.
  real, parameter :: lamdarmax=3.5e4, pi=3.14159265358979323846
  real, parameter :: pidnr=(pi*1000./6.)*24.
  real, parameter :: rslopermax=1./lamdarmax
  real, parameter :: rsloperbmax=rslopermax**bvtr
  double precision, parameter :: rslopermmax=dble(rslopermax)**mur
  real, parameter :: rsloper2max=rslopermax*rslopermax
  real, parameter :: rsloper3max=rsloper2max*rslopermax
  real, parameter :: pvtr=1., pvtrn=1.
contains
'''
pathlib.Path(sys.argv[2]).write_text(preamble + text[start:end] + '\nend module native_slope_test\n')
