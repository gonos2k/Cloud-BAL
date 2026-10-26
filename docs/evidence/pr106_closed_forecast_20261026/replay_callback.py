#!/usr/bin/env python3
"""Read-only PR104 T39/RK2 graupel rejection and source-store replay."""
import argparse, gzip, json, struct, hashlib
from pathlib import Path
from fractions import Fraction

RUNS = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr104_validtime_forecast_20261026')
ARMS = ('HYDRO', 'AMPLITUDE', 'STRUCTURED')
P = argparse.ArgumentParser()
P.add_argument('--output-dir', required=True, type=Path)
OUT = P.parse_args().output_dir
OUT.mkdir(parents=True, exist_ok=False)
TARGET = (39, 2, 2, 219, 13)
BITS = ('3676D01F0BF49AE5', '35D9F4C29CF672CB')

def f64(h): return struct.unpack('>d', bytes.fromhex(h))[0]
def f32(h): return struct.unpack('>f', bytes.fromhex(h))[0]
def exact32(h): return Fraction.from_float(f32(h))
def exact64(h): return Fraction.from_float(f64(h))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

SOURCE_PATHS = {
  'C2_core_source':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/src/common/cloud_bal_joint_transport.f90',
  'graupel_cone_source':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/tools/pr87_graupel_cone_mixture.py',
  'PR92_capture_source':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/tools/pr92_source_replay.py',
  'C2_candidate_build_receipt':'/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json',
  'C2_candidate_module_em':'/var/tmp/pr99_bulk_candidate_native_c2_20261022/source/overrides/module_em.F',
  'executed_candidate_executable':'/var/tmp/pr99_bulk_candidate_native_c2_20261022/wrf_pr87_overlay.exe'
}
PRE_SOURCE_HASHES = {k:sha(Path(v)) for k,v in SOURCE_PATHS.items()}

report = {
  'schema': 'pr106_t39_graupel_callback_replay_v1',
  'method': 'Python-only IEEE bit decoding and source-predicate inspection; no model run or compiler invocation.',
  'compiler_invoked': False,
  'source_pointers': {
    'store_ratio_predicate': {'path':'Cloud-BAL/src/common/cloud_bal_joint_transport.f90','lines':'592-609'},
    'c2_interval_helper': {'path':'Cloud-BAL/src/common/cloud_bal_joint_transport.f90','lines':'379-474'},
    'graupel_reason6': {'path':'Cloud-BAL/tools/pr87_graupel_cone_mixture.py','lines':'217-224'},
    'source_mismatch_capture_guard': {'path':'Cloud-BAL/tools/pr92_source_replay.py','lines':'21-26'},
    'hashes': PRE_SOURCE_HASHES
  },
  'source_predicate': {
    'source': '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/src/common/cloud_bal_joint_transport.f90',
    'sha256': sha(Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL/src/common/cloud_bal_joint_transport.f90')),
    'predicate': 'strict_mass_ratio_valid64 requires q64/n64 <= maximum_ratio; joint_moment_store sets failure_stage=2 before this check and returns invalid if it fails.',
    'independent_check': 'The exact captured REAL64 quotient is greater than the captured upper bound 900.0; dry density is positive. Both candidate moments round to REAL32 zero.'
  },
  'arms': [],
  'group_cause_assessment': {
    'callback_scope': 'Exact per-cell store rejection and PR92 producer/geometry capture are available for the returned T39/RK2 cell. They establish that cell-level rejection predicate.',
    'full_group_scope': 'Not established. PR92_STORE_FAIL_FULL records enumerate several failing cells, and the PR99_GROUP_FAILURE fixture is only at timestep 32, not the T39 fatal. The callback is not a grouped-transaction causal certificate.',
    'available_replay_assets': 'The T39/RK2 PR92_FAIL block captures producer identity, source and recomputed diffusion bits, state stencil, grid metrics, weights, donor terms, face coefficients, and cache delta at the callback cell. This supports per-cell producer/source predicate replay. Full-domain candidate arrays / complete group trial state for every pair are not present in this bounded capture.'
  }
}
for arm in ARMS:
    run = RUNS/arm/'run'
    lines = gzip.open(run/'pr92_graupel_source_capture.raw.gz','rt',encoding='ascii').read().splitlines()
    fail_i = next(i for i,l in enumerate(lines) if l.startswith('PR92_FAIL 39 2 2 219 13 '))
    block=[]
    for l in lines[fail_i:]:
        if l.startswith('PR92_FAIL ') and block: break
        if l.startswith('PR92_STORE_FAIL_') and block: break
        block.append(l)
    r64=next(l.split()[1:] for l in block if l.startswith('PR92_R64 '))
    store_i=next(i for i,l in enumerate(lines) if l.startswith('PR92_STORE_FAIL_FULL 39 2 2 219 13 '))
    sf=lines[store_i].split(); r32=lines[store_i+1].split()
    vals=[f64(sf[8]),f64(sf[9])]
    q,n=vals
    upper=f64(sf[16])
    quotient=q/n
    full_rows=[]
    for l in lines:
        x=l.split()
        if len(x)==21 and x[0]=='PR92_STORE_FAIL_FULL' and x[1:3]==['39','2']:
            full_rows.append({'i':int(x[3]),'j':int(x[4]),'k':int(x[5]),'stage':int(x[7]),'q_bits':x[8],'n_bits':x[9]})
    # Per-cell identity fields captured by the source diagnostic.
    source_q,source_n,diff_q,diff_n=map(f64,r64[:4])
    # Reconstruct the ordered runtime REAL64 formula from all paired FULL/R32 inputs.
    dt,old,new,rho,qbase,nbase=map(f32,r32[1:])
    source_pair_q,source_pair_n=f64(sf[10]),f64(sf[11])
    transport_q,transport_n=f64(sf[12]),f64(sf[13])
    replay_q=(old*qbase+dt*(source_pair_q+transport_q))/new
    replay_n=(old*nbase+dt*(source_pair_n+transport_n))/new
    replay_bits=[struct.pack('>d',replay_q).hex().upper(),struct.pack('>d',replay_n).hex().upper()]
    exact_q=(exact32(r32[2])*exact32(r32[5])+exact32(r32[1])*(exact64(sf[10])+exact64(sf[12])))/exact32(r32[3])
    exact_n=(exact32(r32[2])*exact32(r32[6])+exact32(r32[1])*(exact64(sf[11])+exact64(sf[13])))/exact32(r32[3])
    max_ratio=exact64(sf[16])
    group_path=run/'pr99_group_failure.raw.gz'
    group_text=gzip.open(group_path,'rt',encoding='ascii').read()
    group_timesteps=sorted({int(x.split()[1]) for x in group_text.splitlines() if x.strip().startswith('PR99_GROUP_FAILURE_')})
    report['arms'].append({
      'arm':arm,
      'timestep_rk_cell':list(TARGET),
      'callback_candidate_bits64':sf[8:10],
      'candidate_q_real64':q,'candidate_n_real64':n,'candidate_q_over_n_real64':quotient,
      'strict_mass_bounds_real64':[f64(sf[15]),upper],
      'upper_bound_excess':quotient-upper,
      'dry_density_real32':f32(r32[4]),'dry_density_bits32':r32[4],
      'candidate_real32_bits_after_rounding':[format(struct.unpack('>I',struct.pack('>f',q))[0],'08X'),format(struct.unpack('>I',struct.pack('>f',n))[0],'08X')],
      'store_failure_stage':int(sf[7]),'full_candidate_record_matches_callback_bits':sf[8:10]==list(BITS),
      'formula_inputs':{'dt_bits32':r32[1],'old_carrier_bits32':r32[2],'new_carrier_bits32':r32[3],
        'dry_density_bits32':r32[4],'base_q_bits32':r32[5],'base_n_bits32':r32[6],
        'source_q_bits64':sf[10],'source_n_bits64':sf[11],
        'transport_q_bits64':sf[12],'transport_n_bits64':sf[13]},
      'ordered_r64_formula_replay_bits64':replay_bits,
      'ordered_r64_formula_matches_runtime_bits':replay_bits==sf[8:10],
      'exact_rational_endpoint':{'Q_star':str(exact_q),'N_star':str(exact_n),'Q_star_decimal':float(exact_q),'N_star_decimal':float(exact_n),
        'Q_minus_900N':str(exact_q-max_ratio*exact_n),
        'Q_over_N_minus_900':str(exact_q/exact_n-max_ratio),
        'outside_strict_100_900_cone':exact_q>max_ratio*exact_n},
      'exact_source_rate':{'Q_s_over_N_s_minus_900':str(exact64(sf[10])/exact64(sf[11])-max_ratio),
        'Q_s_minus_900N_s':str(exact64(sf[10])-max_ratio*exact64(sf[11])),
        'outside_strict_100_900_cone':exact64(sf[10])>max_ratio*exact64(sf[11])},
      'graupel_diffusion_source_identity':{'source_bits64':r64[:2], 'recomputed_diffusion_bits64':r64[2:4],
        'bits_match':r64[:2]==r64[2:4],
        'source_capture_hook': 'The existing pr92_source_replay.py capture hook is inserted at the q/n source identity guard and emits PR92_FAIL only when source and recomputed diffusion bits differ.'},
      'c2_interval_certificate_expected':False,
      'c2_classification':'source-logic exact classification: rejected by the maximum-ratio interval check; not run through a compiler. Since exact Q*>900*N* and the C2 outward interval encloses Q* and 900*N*, its Q upper bound exceeds the cone upper bound.',
      'c2_rejection_reason':'The exact typed-input endpoint is outside maximum ratio 900, so the C2 cone interval check correctly rejects it; this is not a conservative rejection of an exact-valid endpoint.',
      'producer_source_bits64':r64[:2], 'recomputed_diffusion_bits64':r64[2:4],
      'source_q_minus_recomputed_q':source_q-diff_q,'source_n_minus_recomputed_n':source_n-diff_n,
      'producer_capture_record_count':len(block),'producer_identity_record':next(l for l in block if l.startswith('PR92_PRODUCER_IDENTITY')),
      'geometry_and_faces_captured':all(any(x.startswith(tag) for x in block) for tag in ('PR92_STENCIL ','PR92_METRICS ','PR92_WEIGHTS ','PR92_DONOR_TERMS ','PR92_FACE_COEFFICIENTS ')),
      'full_candidate_store_failure_records_t39_rk2':len(full_rows),
      'first_full_candidate_store_failure_records_t39_rk2':full_rows[:4],
      'matching_pr99_group_diagnostic_timesteps':group_timesteps
    })
with (OUT/'actual_callback_excerpts.txt').open('x') as f:
    f.write('Read-only excerpts from receipt-bound T39/RK2 diagnostic captures.\n')
    for arm in ARMS:
        lines=gzip.open(RUNS/arm/'run/pr92_graupel_source_capture.raw.gz','rt',encoding='ascii').read().splitlines()
        i=next(i for i,l in enumerate(lines) if l.startswith('PR92_FAIL 39 2 2 219 13 '))
        f.write('\n== '+arm+' callback producer block ==\n')
        f.write('\n'.join(lines[i:i+14])+'\n')
        j=next(i for i,l in enumerate(lines) if l.startswith('PR92_STORE_FAIL_FULL 39 2 2 219 13 '))
        f.write('\n'.join(lines[j:j+2])+'\n')
        g=gzip.open(RUNS/arm/'run/pr99_group_failure.raw.gz','rt',encoding='ascii').read().splitlines()
        f.write('PR99 group failure timestep headers: '+'; '.join(x.strip() for x in g if x.strip().startswith('PR99_GROUP_FAILURE_'))+'\n')
POST_SOURCE_HASHES = {k:sha(Path(v)) for k,v in SOURCE_PATHS.items()}
report['source_hashes_pre'] = PRE_SOURCE_HASHES
report['source_hashes_post'] = POST_SOURCE_HASHES
report['source_artifacts_unchanged_during_analysis'] = PRE_SOURCE_HASHES == POST_SOURCE_HASHES
# Rewrite is forbidden: add source snapshots before creating the result file.
with (OUT/'source_integrity.json').open('x') as source_integrity_file:
    json.dump({'pre':PRE_SOURCE_HASHES,'post':POST_SOURCE_HASHES,'unchanged':PRE_SOURCE_HASHES==POST_SOURCE_HASHES},source_integrity_file,indent=2,allow_nan=False)

with (OUT/'actual_callback_replay.json').open('x') as result_file:
    json.dump(report,result_file,indent=2,allow_nan=False)
    result_file.write('\n')
