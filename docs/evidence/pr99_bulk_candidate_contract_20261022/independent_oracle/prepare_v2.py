#!/usr/bin/env python3
"""Prepare exact Fraction cases and a standalone Fortran black-box caller."""
from __future__ import annotations
import json, math, struct
from fractions import Fraction
from pathlib import Path

OUT=Path('/var/tmp/pr99_bulk_oracle_finalv2_20261022')

def b32(x): return struct.unpack('>I',struct.pack('>f',float(x)))[0]
def b64(x): return struct.unpack('>Q',struct.pack('>d',float(x)))[0]
def f32(bits): return struct.unpack('>f',struct.pack('>I',bits))[0]
def f64(bits): return struct.unpack('>d',struct.pack('>Q',bits))[0]
def frac32(bits):
    x=f32(bits)
    return Fraction.from_float(x) if math.isfinite(x) else None
def frac64(bits):
    x=f64(bits)
    return Fraction.from_float(x) if math.isfinite(x) else None

fields32=('base_q','base_b','old_carrier','new_carrier','dt','dry_density')
fields64=('source_q','source_b','transport_q','transport_b','theta','minimum_ratio','maximum_ratio','reference_q','reference_b')
cases=[]
def add(name,*,base_q=0.,base_b=0.,old=1.,new=1.,dt=1.,rho=1.,sq=0.,sb=0.,tq=0.,tb=0.,theta=0.,lo=100.,hi=900.,refq=None,refb=None):
    x={'name':name}
    for key,val in zip(fields32,(base_q,base_b,old,new,dt,rho)): x[key+'_bits']=f'{b32(val):08x}'
    vals=(sq,sb,tq,tb,theta,lo,hi)
    for key,val in zip(fields64,vals): x[key+'_bits']=f'{b64(val):016x}'
    rq,rb=reference(x)
    if refq is not None: rq=refq
    if refb is not None: rb=refb
    x['reference_q_bits']=f'{b64(rq):016x}'; x['reference_b_bits']=f'{b64(rb):016x}'
    cases.append(x)

def opref(x):
    get32=lambda n:f32(int(x[n+'_bits'],16))
    get64=lambda n:f64(int(x[n+'_bits'],16))
    oq=get32('old_carrier'); nq=get32('new_carrier'); dt=get32('dt')
    tq=get64('theta')
    # Explicit Python binary64 operations mirror the ordered R64 expression.
    q=(oq*get32('base_q') + dt*(get64('source_q') + tq*get64('transport_q')))/nq
    b=(oq*get32('base_b') + dt*(get64('source_b') + tq*get64('transport_b')))/nq
    return q,b
reference=opref
eta=Fraction(1,1<<149)
# Actual closed-run fatal cell, copied from pinned PR92_STORE_FAIL_FULL/R64/R32 record.
fatal={
'base_q_bits':'00000000','base_b_bits':'00000000','old_carrier_bits':'47a09016','new_carrier_bits':'47a08d94','dt_bits':'40d55555','dry_density_bits':'3f53b32d',
'source_q_bits':'3753214b46a3bc21','source_b_bits':'36b5c40847451a51','transport_q_bits':'0000000000000000','transport_b_bits':'0000000000000000','theta_bits':'3fea7665a0000000','minimum_ratio_bits':'4059000000000000','maximum_ratio_bits':'408c200000000000','reference_q_bits':'36796b3ba65c1be8','reference_b_bits':'35dcebc8fcfefc7a'}
fatal['name']='actual_fatal_32_1_2_241_14'
cases.append(fatal)
# Interior cone and fraction of positive candidates spanning requested scales.
for ratio in (100.,100.00000000000001,500.,899.9999999999999,900.):
    b=float(eta/4); q=ratio*b
    add(f'interior_ratio_{ratio:g}',sq=q,sb=b)
# Exact typed R64 neighbors around the strict cone edges.
b=float(eta/4)
for edge,base in [('min',100.*b),('max',900.*b)]:
    for direction,label in ((-math.inf,'below'),(0.,'equal'),(math.inf,'above')):
        q=base if direction==0. else math.nextafter(base,direction)
        add(f'{edge}_edge_{label}',sq=q,sb=b)
# Opposing source and transport components at each requested theta, same net candidate.
for theta in (0.,.5,.75,1.):
    b=float(eta/4); q=500.*b
    if theta==0.: sq,sb,tq,tb=q,b,0.,0.
    else: sq,sb,tq,tb=1.75*q,1.75*b,-.75*q/theta,-.75*b/theta
    add(f'cancel_theta_{theta:g}',sq=sq,sb=sb,tq=tq,tb=tb,theta=theta)
# Tiny base contribution amplified by a large, but valid, old carrier.
for old,base in ((2.0**100,2.0**-245),(2.0**-100,2.0**-30)):
    q=500.*float(eta/8); b=float(eta/8)
    # Use source remainder to land in the bulk quantum region.
    add(f'tiny_base_old_{old:.3g}',base_q=base,base_b=base/500.,old=old,sq=q-old*base,sb=b-old*base/500.)
# Half-B and max-density-Q quantum budget boundaries (strict limits).
half_b=float(eta/2)
for value,label in ((math.nextafter(half_b,0.),'below'),(half_b,'equal'),(math.nextafter(half_b,math.inf),'above')):
    add(f'half_B_{label}',sq=500.*value,sb=value)
qbudget=float(Fraction(900,2)*eta)
for value,label in ((math.nextafter(qbudget,0.),'below'),(qbudget,'equal'),(math.nextafter(qbudget,math.inf),'above')):
    add(f'max_Q_budget_{label}',sq=value,sb=value/900.)
# Binding, sign, invalid-domain, and large finite/overflow witnesses.
x=dict(cases[1]); x['name']='reference_q_nextafter_mismatch'; x['reference_q_bits']=f'{b64(math.nextafter(f64(int(x["reference_q_bits"],16)),math.inf)):016x}'; cases.append(x)
for nm,vals in [('zero_old',dict(old=0.)),('negative_new',dict(new=-1.)),('zero_density',dict(rho=0.)),('negative_theta',dict(theta=-.25)),('theta_over_one',dict(theta=1.25)),('negative_dt',dict(dt=-1.))]: add(nm,sq=float(eta/8),sb=float(eta/1000),**vals)
# finite rate inputs whose operational expression overflows, and nonfinite bit-pattern inputs.
add('large_rate_overflow_r64',sq=1.0e308,sb=1.0e308,dt=3.0e38,theta=1.)
nan=dict(cases[1]); nan['name']='nan_source_q'; nan['source_q_bits']='7ff8000000000000'; cases.append(nan)

# Final-v2 guards: REAL32 endpoint range, very large max ratio, overflow
# headroom, tiny positive carrier, and signed cancellation cases.
add('maxratio_large_valid',sq=1.0e-20,sb=1.0e-320,lo=1.0e299,hi=1.0e300)
add('maxratio_large_out_of_r32',sq=1.0e40,sb=1.0e-260,lo=1.0e300,hi=1.0e300)
add('r32_q_upper_edge_valid',sq=float.fromhex('0x1.fffffep+127')*0.0 + 500.0*float(eta/8),sb=float(eta/8))
add('tiny_new_carrier',new=2.0**-120,sq=500.0*float(eta/8)*2.0**-120,sb=float(eta/8)*2.0**-120)
add('near_r64_overflow_same_sign',sq=3.0e307,sb=3.0e307,theta=0.0)
add('large_signed_source_transport_cancel',sq=3.0e307,sb=3.0e307,tq=-3.0e307,tb=-3.0e307,theta=1.0)
add('negative_transport_interior',sq=1.75*500.0*float(eta/8),sb=1.75*float(eta/8),tq=-0.75*500.0*float(eta/8),tb=-0.75*float(eta/8),theta=1.0)

# Exact rational reference and conservative no-false-accept oracle.
def exact_candidate(c):
    get32=lambda n:frac32(int(c[n+'_bits'],16))
    get64=lambda n:frac64(int(c[n+'_bits'],16))
    v=[get32(n) for n in fields32]; w=[get64(n) for n in fields64]
    if any(z is None for z in v+w): return None
    bq,bb,old,new,dt,rho=v; sq,sb,tq,tb,theta,lo,hi,_,_=w
    if old<=0 or new<=0 or dt<=0 or rho<=0 or theta<0 or theta>1 or bq<0 or bb<0: return None
    return ((old*bq + dt*(sq+theta*tq))/new,
            (old*bb + dt*(sb+theta*tb))/new,
            rho,lo,hi)

def exact_oracle(c):
    z=exact_candidate(c)
    if z is None: return False
    q,b,rho,lo,hi=z
    if rho<=0 or lo<=0 or hi<lo or q<=0 or b<=0: return False
    if q<lo*b or q>hi*b: return False
    if b>=eta/2 or q>=hi*eta/2: return False
    huge32=Fraction.from_float(float.fromhex('0x1.fffffep+127'))
    if q>huge32 or b>huge32: return False
    rq=frac64(int(c['reference_q_bits'],16)); rb=frac64(int(c['reference_b_bits'],16))
    if rq is None or rb is None or rq<=0 or rb<=0: return False
    if rq>huge32 or rb>huge32: return False
    if (rq,rb)!=tuple(map(Fraction.from_float,opref(c))): return False
    if rq>=hi*eta/2 or rb>=eta/2: return False
    if (rq,rb)!=tuple(map(Fraction.from_float,opref(c))): return False
    return True

for c in cases:
    c['oracle_valid']=exact_oracle(c)
    c['reference_bits_match_operational_r64']= (
      c['reference_q_bits']==f'{b64(opref(c)[0]):016x}' and c['reference_b_bits']==f'{b64(opref(c)[1]):016x}')
(OUT/'cases.json').write_text(json.dumps({'schema':'fraction_oracle_cases_v1','method':'exact rational evaluation of typed IEEE inputs; acceptance is one-way: helper true must imply exact validity','cases':cases},indent=2)+'\n')
# Harness imports the in-progress core and only calls its public black-box signature.
lines=['program bulk_absence_harness','  use iso_fortran_env, only: int32,int64,real32,real64','  use cloud_bal_joint_transport, only: joint_bulk_candidate_absence_is_valid','  implicit none','  integer :: c','  logical :: accepted']
for ix,c in enumerate(cases,1):
    def r32(name): return f"transfer(int(z'{c[name+'_bits']}',int32),0.0_real32)"
    def r64(name): return f"transfer(int(z'{c[name+'_bits']}',int64),0.0_real64)"
    args=[r32('base_q'),r32('base_b'),r32('old_carrier'),r32('new_carrier'),r32('dt'),r32('dry_density'),r64('source_q'),r64('source_b'),r64('transport_q'),r64('transport_b'),r64('theta'),r64('minimum_ratio'),r64('maximum_ratio'),r64('reference_q'),r64('reference_b')]
    lines.append(f'  c={ix}; accepted=joint_bulk_candidate_absence_is_valid('+', &\n      '.join(args)+')')
    lines.append("  write(*,'(i0,1x,l1)') c,accepted")
lines+=['end program bulk_absence_harness','']
(OUT/'bulk_absence_harness.f90').write_text('\n'.join(lines))
print(f'prepared {len(cases)} cases; oracle-positive={sum(c["oracle_valid"] for c in cases)}')
print('oracle-valid cases:',', '.join(c['name'] for c in cases if c['oracle_valid']))
print('fatal case exact oracle:',next(c['oracle_valid'] for c in cases if c['name'].startswith('actual_fatal')))
