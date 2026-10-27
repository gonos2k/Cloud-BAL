#!/usr/bin/env python3
"""Reproduce the bounded T39/RK1 producer and RK2 callback source bits with pinned ifx."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, struct, subprocess, tempfile
from fractions import Fraction
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EVIDENCE = REPO / 'docs/evidence/t39_closed_replay_20261027'
MANIFEST = EVIDENCE / 'manifest.json'
BUILD_RECEIPT = REPO / 'docs/evidence/pr107_t39_capture_20261026/build_receipt.json'
BUILD_RECEIPT_SHA = 'b66d9f87b58f371f8fce79e2b7c9727cfd13096cd2db9c51efa435efff0e5767'
PROFILE = REPO / 'tests/intel_toolchain.sh'
PROFILE_SHA = '5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
PREPROCESSED = Path('/var/tmp/pr107_t39_native_capture_20261026/preprocessed/module_em.f90')
PREPROCESSED_SHA = 'f671a8720ca46cc4c99b244140b0a03c6154ab0ba3d9f422810e2efe5b678338'
PRODUCER_SHA = '609fce974d5687000eabb82621bc8447315adaa7118ea1f19106e52855d08bc4'
CONSUMER_SHA = 'f2d52c400fedb20140593041902706a2c0e688b3536aea3464a44fe0415ce52a'
TRANSFORM_PROOF_SHA = '4c274500ee76892f41669287a885060f7cce63207f0482bf7fb821c5c70bc063'
TRANSFORMED_MODULE_SHA = 'c978b37a5f290770f899336a52195dbbc78ead87482e40d89f14f90db86263f6'


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def bound_input(name: str, expected: str) -> Path:
    path=EVIDENCE/name
    rows=[r for r in json.loads(MANIFEST.read_text())['files'] if r['name']==name]
    if len(rows)!=1 or rows[0]['sha256']!=expected:
        raise ValueError(f'{name} is not uniquely bound by closure manifest')
    if sha(path)!=expected: raise ValueError(f'{name} hash mismatch')
    return path


def verify_sources() -> dict:
    if sha(BUILD_RECEIPT)!=BUILD_RECEIPT_SHA: raise ValueError('C2 build receipt hash mismatch')
    if sha(PROFILE)!=PROFILE_SHA: raise ValueError('Intel profile hash mismatch')
    if sha(PREPROCESSED)!=PREPROCESSED_SHA: raise ValueError('C2 preprocessed module hash mismatch')
    build=json.loads(BUILD_RECEIPT.read_text()); proof=build['source_transform_proof']
    if build.get('status')!='PASS_OVERLAY_BUILD' or build.get('model_run') is not False:
        raise ValueError('unexpected C2 diagnostic overlay build receipt state')
    compiled=[row for row in build.get('compiled_overrides',[]) if row.get('member')=='module_em.o']
    if len(compiled)!=1 or compiled[0].get('generated_source_sha256')!=PREPROCESSED_SHA \
       or compiled[0].get('generated_source_path')!=str(PREPROCESSED) \
       or compiled[0].get('source_sha256')!=TRANSFORMED_MODULE_SHA:
        raise ValueError('C2 module_em compile input is not bound to the pinned preprocessed/source hashes')
    if proof.get('math_source_unchanged') is not True or proof.get('sha256')!=TRANSFORM_PROOF_SHA \
       or proof.get('source_sha256')!=TRANSFORMED_MODULE_SHA:
        raise ValueError('C2 source transform proof binding mismatch')
    proof_path=Path(proof['path'])
    if not proof_path.is_file() or sha(proof_path)!=TRANSFORM_PROOF_SHA:
        raise ValueError('C2 source transform proof file missing or hash mismatch')
    if proof.get('producer_target')!={'cell_ijk':[2,219,13],'rkstep':1,'timestep':39}:
        raise ValueError('unexpected producer selection in C2 transform proof')
    if proof.get('group_target')!={'rkstep':2,'timestep':39}:
        raise ValueError('unexpected group selection in C2 transform proof')
    source_path=Path(proof['source_path'])
    if not source_path.is_file() or sha(source_path)!=TRANSFORMED_MODULE_SHA:
        raise ValueError('transformed C2 source missing or hash mismatch')
    profile_check=subprocess.run(['bash','-lc',f'source \"{PROFILE}\" && printf \"FC=%s\\nVER=%s\\n\" \"$CLOUD_BAL_FC\" \"$($CLOUD_BAL_FC --version | head -1)\" && printf \"O0=%s\\n\" \"${{CLOUD_BAL_FREE_FLAGS[*]}}\" && printf \"O2=%s\\n\" \"${{CLOUD_BAL_REPRO_FLAGS[*]}}\"'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True).stdout.splitlines()
    profile_values={line.split('=',1)[0]:line.split('=',1)[1] for line in profile_check if '=' in line}
    if set(profile_values)!={'FC','VER','O0','O2'}: raise ValueError('could not obtain pinned Intel compiler identity/flags')
    compiler=Path(profile_values['FC']).resolve(); compiler_version=profile_values['VER']
    import shlex
    o0_flags=shlex.split(profile_values['O0']); o2_flags=shlex.split(profile_values['O2'])
    compiler_sha=sha(compiler)
    if compiler_version!='ifx (IFX) 2026.0.0 20260331' or compiler_sha!='909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef':
        raise ValueError('pinned Intel compiler identity mismatch')
    hydro_path=bound_input('HYDRO_T39_receipt.json','a71f157b19695cae4cb228cd92b91f05a837fdcd913b1eff3d0d25809697a697')
    hydro=json.loads(hydro_path.read_text())
    if hydro.get('arm')!='HYDRO' or hydro.get('status')!='INCOMPLETE' or hydro.get('returncode')!=1 or hydro.get('final_completed_step')!=38:
        raise ValueError('closed HYDRO receipt is not the expected T39 failure closure')
    return {'build_receipt':str(BUILD_RECEIPT),'build_receipt_sha256':BUILD_RECEIPT_SHA,
            'closed_hydro_receipt':str(hydro_path),'closed_hydro_receipt_sha256':sha(hydro_path),
            'compiler_path':str(compiler),'compiler_sha256':compiler_sha,'compiler_version':compiler_version,
            'profile_flags':{'O0':o0_flags,'O2':o2_flags},
            'preprocessed_source':str(PREPROCESSED),'preprocessed_source_sha256':PREPROCESSED_SHA,
            'transformed_source':str(source_path),'transformed_source_sha256':TRANSFORMED_MODULE_SHA,
            'transform_proof_sha256':TRANSFORM_PROOF_SHA,'math_source_unchanged':True,
            'intel_profile':str(PROFILE),'intel_profile_sha256':PROFILE_SHA}


def r32(bits): return struct.unpack('>f',int(bits,16).to_bytes(4,'big'))[0]
def r64(bits): return struct.unpack('>d',int(bits,16).to_bytes(8,'big'))[0]
def frac32(bits): return Fraction.from_float(r32(bits))
def f32(bits): return f"transfer(int(z'{bits}',int32),0.0_real32)"


def make_driver(q,n,consumer,probe:bool) -> str:
    def field(name,row):
        return '\n'.join(f'  {name}({dx+1},1,{dy+2})={f32(row["stencil"][dy][dx])}'
                         for dy in (-1,0,1) for dx in range(3))
    def env(row):
        return '\n'.join([f'  x({dx+1},1,{dy+2})={f32(row["stencil"][dy][3+dx])}\n'
                           f'  mut({dx+1},{dy+2})={f32(row["stencil"][dy][6+dx])}'
                           for dy in (-1,0,1) for dx in range(3)])
    m=q['metrics32_bits']; assert m==n['metrics32_bits']
    geom='\n'.join([f'  {name}({i},{j})={f32(m[idx])}' for idx,name,i,j in [
      (0,'ux',2,2),(1,'ux',3,2),(2,'uy',2,2),(3,'uy',3,2),
      (4,'vx',2,2),(5,'vx',2,3),(6,'vy',2,2),(7,'vy',2,3),
      (8,'tx',2,2),(9,'ty',2,2)]])
    scale='\n'.join([f'  {name}(1)={f32(q["scale32_bits"][idx])}' for idx,name in [(0,'c1'),(1,'c2')]]+
                    [f'  {name}={f32(q["scale32_bits"][idx])}' for idx,name in [(2,'rdx'),(3,'rdy')]])
    zero='\n'.join(f'  q2({i},1,{j})=0.0_real32; n2({i},1,{j})=0.0_real32' for i in range(1,4) for j in range(1,4))
    if probe:
        qcalls='oq,xq'; ncalls='on,xn'; qcalls2='oq2,xq2'; ncalls2='on2,xn2'
        outs=""" write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK1_Q',xq(2,1,2),transfer(oq(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK1_B',xn(2,1,2),transfer(on(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK2_Q',xq2(2,1,2),transfer(oq2(2,1,2),0_int64)
 write(*,'(A,1X,ES45.35E4,1X,Z16.16)') 'RK2_B',xn2(2,1,2),transfer(on2(2,1,2),0_int64)
 write(*,'(A,1X,L1,1X,ES45.35E4)') 'RK1_RATIO_EXACT_900',xq(2,1,2)==900.0_real128*xn(2,1,2),xq(2,1,2)/xn(2,1,2)-900.0_real128"""
    else:
        qcalls='oq'; ncalls='on'; qcalls2='oq2'; ncalls2='on2'
        outs=""" write(*,'(A,1X,Z16.16)') 'RK1_Q',transfer(oq(2,1,2),0_int64)
 write(*,'(A,1X,Z16.16)') 'RK1_B',transfer(on(2,1,2),0_int64)
 write(*,'(A,1X,Z16.16)') 'RK2_Q',transfer(oq2(2,1,2),0_int64)
 write(*,'(A,1X,Z16.16)') 'RK2_B',transfer(on2(2,1,2),0_int64)"""
    extra=' real(real128) :: xq(1:3,1:1,1:3),xn(1:3,1:1,1:3),xq2(1:3,1:1,1:3),xn2(1:3,1:1,1:3)\n' if probe else ''
    return f'''program replay
 use iso_fortran_env, only: int32,int64,real32,real64,real128
 use pr87_horizontal_diffusion64, only: horizontal_diffusion64
 implicit none
 real(real32) :: q1(1:3,1:1,1:3),n1(1:3,1:1,1:3),q2(1:3,1:1,1:3),n2(1:3,1:1,1:3)
 real(real32) :: x(1:3,1:1,1:3),mut(1:3,1:3),c1(1:1),c2(1:1)
 real(real32) :: ux(1:3,1:3),uy(1:3,1:3),vx(1:3,1:3),vy(1:3,1:3),tx(1:3,1:3),ty(1:3,1:3),rdx,rdy
 real(real64) :: oq(1:3,1:1,1:3),on(1:3,1:1,1:3),oq2(1:3,1:1,1:3),on2(1:3,1:1,1:3)
{extra} q1=0.0_real32; n1=0.0_real32; q2=0.0_real32; n2=0.0_real32; x=0.0_real32; mut=0.0_real32
 ux=0.0_real32; uy=0.0_real32; vx=0.0_real32; vy=0.0_real32; tx=0.0_real32; ty=0.0_real32
 {field('q1',q)}
 {field('n1',n)}
 {env(q)}
 {geom}
 {scale}
 {zero}
 call horizontal_diffusion64(q1,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,{qcalls})
 call horizontal_diffusion64(n1,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,{ncalls})
 call horizontal_diffusion64(q2,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,{qcalls2})
 call horizontal_diffusion64(n2,mut,c1,c2,ux,uy,vx,vy,tx,ty,x,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,{ncalls2})
{outs}
end program replay
'''


def exact_module(text: str) -> str:
    start=text.index('MODULE pr87_horizontal_diffusion64\n')
    end=text.index('END MODULE pr87_horizontal_diffusion64',start)+len('END MODULE pr87_horizontal_diffusion64')
    return text[start:end]


def probe_module(module: str) -> tuple[str,list[str]]:
    s=module
    changes=[
      ('routine signature: append exact128 output argument',
       'ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)',
       'ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment,exact128)'),
      ('declaration: expose existing REAL128 increment',
       '    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)\n',
       '    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)\n    REAL(real128),INTENT(OUT) :: exact128(ims:ime,kms:kme,jms:jme)\n'),
      ('initialization of probe output', '    increment=0.0_real64\n',
       '    increment=0.0_real64\n    exact128=0.0_real128\n'),
      ('probe write before original REAL128-to-REAL64 cast',
       '          increment(i,k,j)=REAL(increment128,real64)',
       '          exact128(i,k,j)=increment128\n          increment(i,k,j)=REAL(increment128,real64)'),
    ]
    for label,old,new in changes:
        if s.count(old)!=1: raise ValueError(f'probe modification not unique: {label}')
        s=s.replace(old,new,1)
    return s,[x[0] for x in changes]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-dir',type=Path,required=True,help='must not exist; all outputs are exclusive')
    args=ap.parse_args(); out=args.run_dir.resolve()
    # Fail before creating or modifying any user-selected output if prior evidence exists.
    if out.is_relative_to(REPO.resolve()):
        raise ValueError('native compilation output must be outside the source checkout')
    if out.exists(): raise FileExistsError(out)
    bindings=verify_sources()
    out.mkdir(parents=True,exist_ok=False)
    pp=bound_input('pr92_diffusion_producer.raw.gz',PRODUCER_SHA)
    cp=bound_input('pr92_graupel_source_capture.raw.gz',CONSUMER_SHA)
    sys.path.insert(0,str(REPO/'tools'))
    import pr92_source_replay
    producer_raw=gzip.decompress(pp.read_bytes()); consumer_raw=gzip.decompress(cp.read_bytes())
    prow=out/'capture_inputs'; prow.mkdir()
    ptxt=prow/'producer.raw'; ctxt=prow/'consumer.raw'; ptxt.write_bytes(producer_raw); ctxt.write_bytes(consumer_raw)
    producers=pr92_source_replay.parse_producer_capture(ptxt)
    parsed=pr92_source_replay.parse_consumer_capture(ctxt)
    q=producers.get((39,1,7,7,2,219,13)); b=producers.get((39,1,8,5,2,219,13))
    ids=[r for r in parsed['identity_failures'] if (r['step'],r['rk'],r['i'],r['j'],r['k'])==(39,2,2,219,13)]
    if q is None or b is None or len(ids)!=1: raise ValueError('captured callback producer/consumer selection is not unique')
    consumer=ids[0]
    if q['identity']!=b['identity'] or q['identity']!=[39,1,2,233,2,281,1,39]: raise ValueError('producer identity bounds mismatch')
    closed=json.loads(bound_input('HYDRO_T39_receipt.json','a71f157b19695cae4cb228cd92b91f05a837fdcd913b1eff3d0d25809697a697').read_text())
    for name,pin in [('pr92_diffusion_producer.raw.gz',PRODUCER_SHA),('pr92_graupel_source_capture.raw.gz',CONSUMER_SHA)]:
        rows=[r for r in closed.get('compressed_outputs',[]) if Path(r.get('compressed_path','')).name==name]
        if len(rows)!=1 or rows[0].get('compressed_sha256')!=pin: raise ValueError(f'{name} is not bound by closed HYDRO receipt')
    if q['diffusion64_bits']!=consumer['r64_bits'][0] or b['diffusion64_bits']!=consumer['r64_bits'][1]: raise ValueError('RK1 producer rates do not match RK2 source rates')
    if consumer['r64_bits'][2:4]!=['0000000000000000']*2: raise ValueError('captured RK2 recomputed rates are not zero')
    # Expected one west-neighbor pair: Q=900 binary32 quanta, B=1, all else zero.
    eta=Fraction(1,1<<149)
    qvals=[q['stencil'][dy][dx] for dy in (-1,0,1) for dx in range(3)]
    bvals=[b['stencil'][dy][dx] for dy in (-1,0,1) for dx in range(3)]
    if qvals!=['00000000']*3+['00000384','00000000','00000000']+['00000000']*3:
        raise ValueError(f'unexpected Q stencil {qvals}')
    if bvals!=['00000000']*3+['00000001','00000000','00000000']+['00000000']*3:
        raise ValueError(f'unexpected B stencil {bvals}')
    if any(consumer['stencil'][dy][i] != '00000000' for dy in (-1,0,1) for i in range(6)):
        raise ValueError('RK2 callback Q/N stencil is not all-zero')
    for dy in (-1,0,1):
        if q['stencil'][dy][3:]!=b['stencil'][dy][3:] or q['stencil'][dy][3:]!=consumer['stencil'][dy][6:12]:
            raise ValueError('Q/N RK1 and RK2 xkmhd/mut REAL32 stencil bits differ')
    if q['metrics32_bits']!=b['metrics32_bits'] or q['metrics32_bits']!=consumer['metrics32_bits']:
        raise ValueError('producer and consumer geometry metric bits differ')
    consumer_scale=[struct.pack('>f',r64(v)).hex().upper() for v in consumer['r64_bits'][7:11]]
    if q['scale32_bits']!=b['scale32_bits'] or q['scale32_bits']!=consumer_scale:
        raise ValueError('producer and consumer scale bits differ')
    module=exact_module(PREPROCESSED.read_text()); probe,changes=probe_module(module)
    restored=probe
    for label,old,new in reversed([
      ('routine signature: append exact128 output argument','ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)','ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment,exact128)'),
      ('declaration: expose existing REAL128 increment','    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)\n','    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)\n    REAL(real128),INTENT(OUT) :: exact128(ims:ime,kms:kme,jms:jme)\n'),
      ('initialization of probe output','    increment=0.0_real64\n','    increment=0.0_real64\n    exact128=0.0_real128\n'),
      ('probe write before original REAL128-to-REAL64 cast','          increment(i,k,j)=REAL(increment128,real64)','          exact128(i,k,j)=increment128\n          increment(i,k,j)=REAL(increment128,real64)')]):
        restored=restored.replace(new,old,1)
    if restored!=module: raise ValueError('instrumented probe changed production helper arithmetic outside the declared probe points')
    for name,body in [('horizontal_diffusion64.f90',module+'\n'),('horizontal_diffusion64_probe.f90',probe+'\n')]:
        (out/name).write_text(body)
    native_driver=make_driver(q,b,consumer,False); probe_driver=make_driver(q,b,consumer,True)
    (out/'driver_native.f90').write_text(native_driver)
    (out/'driver_probe.f90').write_text(probe_driver)
    results=[]
    for opt,flags in [('O0','CLOUD_BAL_FREE_FLAGS'),('O2','CLOUD_BAL_REPRO_FLAGS')]:
        work=out/opt; work.mkdir()
        for kind,mod,driver in [('native','horizontal_diffusion64.f90','driver_native.f90'),('probe','horizontal_diffusion64_probe.f90','driver_probe.f90')]:
            exe=work/f'{kind}.exe'; log=work/f'{kind}.log'
            shell=(f'source "{PROFILE}" && "$CLOUD_BAL_FC" "${{{flags}[@]}}" -free '
                   f'-module "{work}" "{out/mod}" "{out/driver}" -o "{exe}" && "{exe}"')
            run=subprocess.run(['bash','-lc',shell],cwd=work,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            log.write_text(run.stdout)
            if run.returncode: raise RuntimeError(f'{opt} {kind} failed; see {log}:\n{run.stdout}')
            rows={line.split()[0]:line.split()[1:] for line in run.stdout.splitlines() if line.startswith(('RK1_','RK2_'))}
            if kind=='native':
                expected={'RK1_Q':[q['diffusion64_bits']], 'RK1_B':[b['diffusion64_bits']],
                          'RK2_Q':['0000000000000000'],'RK2_B':['0000000000000000']}
            else:
                expected={'RK1_Q':[None,q['diffusion64_bits']], 'RK1_B':[None,b['diffusion64_bits']],
                          'RK2_Q':[None,'0000000000000000'],'RK2_B':[None,'0000000000000000'],
                          'RK1_RATIO_EXACT_900':['T',None]}
            for key,ex in expected.items():
                if key not in rows: raise ValueError(f'{opt}/{kind}: missing {key}')
                if ex[0] is not None and rows[key][0].upper()!=ex[0]: raise ValueError(f'{opt}/{kind}: {key} REAL128 result mismatch')
                if ex[-1] is not None and rows[key][-1].upper()!=ex[-1]: raise ValueError(f'{opt}/{kind}: {key} REAL64 bits mismatch')
            if kind=='probe' and float(rows['RK1_RATIO_EXACT_900'][1])!=0.0:
                raise ValueError(f'{opt} REAL128 quotient-minus-900 is nonzero: {rows["RK1_RATIO_EXACT_900"]}')
            results.append({'optimization':opt,'build':kind,'status':'PASS','flags_variable':flags,
                            'compiler_flags':bindings['profile_flags'][opt],
                            'executable_sha256':sha(exe),'log':str(log),'log_sha256':sha(log),'stdout':run.stdout.strip()})
    q64=r64(q['diffusion64_bits']); b64=r64(b['diffusion64_bits'])
    delta=Fraction.from_float(q64)-900*Fraction.from_float(b64)
    if delta<=0: raise ValueError('captured REAL64 pair is not above exact 900:1 cone')
    exact={'q64_bits':q['diffusion64_bits'],'b64_bits':b['diffusion64_bits'],
           'q64_exact_fraction':f'{Fraction.from_float(q64).numerator}/{Fraction.from_float(q64).denominator}',
           'b64_exact_fraction':f'{Fraction.from_float(b64).numerator}/{Fraction.from_float(b64).denominator}',
           'q_minus_900_times_b_exact_fraction':f'{delta.numerator}/{delta.denominator}',
           'q_minus_900_times_b_decimal_approx':format(float(delta),'.17g'),
           'q_minus_900_times_b_positive':True,
           'exact_cone_test':'q64 <= 900*b64 is FALSE by exact Fraction comparison; this, not a rounded quotient display, establishes the REAL64 cone crossing',
           'binary64_quotient_display_only':format(q64/b64,'.17g'),
           'q_ulp':math.ulp(q64),'delta_as_fraction_of_q_ulp':float(delta/Fraction.from_float(math.ulp(q64))),
           'stencil_origin':{'west_q_bits':'00000384','west_b_bits':'00000001','q_quanta':900,'b_quanta':1,
                             'quantum_exact_fraction':str(eta),'center_and_other_neighbors_zero':True}}
    receipt={'schema':'pr107_t39_callback_c2_horizontal_diffusion_replay_v2',
      'status':'PASS_O0_O2_NATIVE_AND_PROBE','scope':'bounded exact callback-cell producer helper replay; not a full C2 host transaction or forecast causal proof',
      'inputs':{'producer_capture':str(pp),'producer_sha256':sha(pp),'consumer_capture':str(cp),'consumer_sha256':sha(cp),
        'producer_identity_bounds':q['identity'],'producer_q_record_key':[39,1,7,7,2,219,13],
        'producer_b_record_key':[39,1,8,5,2,219,13],'callback_consumer_key':[39,2,2,219,13]},
      'bindings':bindings,'native_helper':{'source':'C2 pinned preprocessed module_em.f90 module pr87_horizontal_diffusion64, routine horizontal_diffusion64; source arithmetic unmodified',
        'extracted_module_sha256':sha(out/'horizontal_diffusion64.f90'),'driver_sha256':sha(out/'driver_native.f90')},
      'instrumented_probe':{'source':'same extracted helper with only listed observability changes; output REAL128 increment128 alongside original REAL64 result',
        'module_sha256':sha(out/'horizontal_diffusion64_probe.f90'),'driver_sha256':sha(out/'driver_probe.f90'),
        'alterations':changes},'capture_values':{'rk1_q_source_bits64':q['diffusion64_bits'],'rk1_b_source_bits64':b['diffusion64_bits'],
        'rk2_recomputed_q_bits64':consumer['r64_bits'][2],'rk2_recomputed_b_bits64':consumer['r64_bits'][3],
        'rk2_q_source_bits64':consumer['r64_bits'][0],'rk2_b_source_bits64':consumer['r64_bits'][1]},
      'exact_rounding_analysis':exact,'compiler_runs':results,
      'limitations':['The REAL128 output is from an instrumented copy, not the production helper interface.','Rational cone comparison proves the rounded REAL64 pair lies above q=900*b; it does not by itself establish full grouped-transaction causality.','No tolerance or source policy was changed.'],
      'fresh_output_dir':str(out),'replay_helper':str(Path(__file__).resolve()),
      'replay_helper_sha256':sha(Path(__file__))}
    # Exclusive final write; no existing receipt is ever replaced.
    rp=out/'receipt.json'
    with rp.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(rp)

if __name__=='__main__': main()
