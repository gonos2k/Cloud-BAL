#!/usr/bin/env python3
"""Gate bounded P reconstruction discovery against unchanged original execution."""
import json,os,struct,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import writer_case as writer
base=writer.base
TARGETS={k:writer.TARGETS[k] for k in ('p20183','p17051')}


def require_freeze():
    path=HERE/'phi_freeze.json';expected=os.environ.get('CP05_PHI_FREEZE_SHA')
    if not expected or not path.is_file() or base.sha(path)!=expected:raise ValueError('reviewed phi freeze and root GO required')
    frozen=json.loads(path.read_text())
    required=[HERE/'phi_case.py',HERE/'phi_probe.py',HERE/'phi_schema.json',HERE/'test_phi_gate.py',
              HERE/'writer_rank_wrapper.sh',HERE/'writer_case.py',HERE/'parity_case.py',HERE/'parity_freeze.json',
              base.BUNDLE/'native/phi_source_lineage.json',base.ROOT/'tests/intel_toolchain.sh',base.CORNERS,
              base.PRIOR_MANIFEST,base.PRIOR_GLOBAL,writer.PHASE0/'B1_parity_receipt.json',
              writer.PHASE0/'DM065_parity_receipt.json',writer.PHASE0/'external_capture_inventory.json',
              Path('/usr/bin/gdb'),Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun'),
              base.B1/'wrf.exe',base.B1/'wrfinput_d01',base.DM/'wrfinput_d01']
    if set(frozen['sha256'])!={str(p.resolve()) for p in required}:raise ValueError('phi freeze inventory differs')
    if any(base.sha(p)!=digest for p,digest in frozen['sha256'].items()):raise ValueError('phi frozen artifact changed')


def validate_capture(arm,target,dest):
    rank,i,j,k=TARGETS[target];path=dest/'phi_capture'/f'phi_rank{rank}.jsonl'
    events=[json.loads(line) for line in path.read_text().splitlines()]
    if [e['sequence'] for e in events]!=list(range(1,len(events)+1)) or any(e['rank']!=rank or e['target']!=target or (e['i'],e['j'],e['k'])!=(i,j,k) for e in events):raise ValueError('phi event identity/sequence differs')
    inv=json.loads((writer.PHASE0/'external_capture_inventory.json').read_text())
    prior={x['path']:x['sha256'] for x in inv['arms'][arm]}
    for stage in ('entry','return'):
        reference=base.RUNTIME/'gdb_parity/phase0_03'/arm/'gdb_capture'/f'selected_{stage}_rank{rank}.bin'
        if base.sha(reference)!=prior[str(reference.resolve())]:raise ValueError('phase0 reference changed')
        expected=writer.selected_target(reference,(i,j,k))
        rows=[e for e in events if e['event']==f'function_{stage}' and e.get('function')=='kdm']
        if len(rows)!=4 or {e['timestep'] for e in rows}!={1,2,3,4}:raise ValueError('KDM target coverage differs')
        for row in rows:
            if writer.event_words(row['fields'])!=expected[row['timestep']]:raise ValueError('KDM target parity differs')
    stack=[];guard=None;gap=None;gaps=[];bridges=[];last_phi=None;last_prep=None;vspow_count=0;phi_count=0;pending_v=None
    for e in events:
        kind=e['event'];fn=e.get('function')
        if kind=='phi_guard':
            if guard is not None:raise ValueError('duplicate phi guard')
            raw=struct.unpack('<i',bytes.fromhex(e['non_hydrostatic_raw_word']))[0]
            if (raw!=e['non_hydrostatic'] or (raw&1)!=e['non_hydrostatic_branch_bit'] or not raw&1 or
                e['hypsometric_opt'] not in (1,2) or e['param_first_scalar']!=2 or
                not 1<=e['runtime_p_qv']<=e['n_moist'] or e['n_moist']<2 or e['k_plus_one']>e['kme']):raise ValueError('invalid phi branch')
            guard=e
        elif kind=='function_entry':
            if stack:raise ValueError('overlapping top-level functions')
            if fn=='phi':
                if guard is None:raise ValueError('phi entry missing guard')
                for key in ('caller_pc','caller_class','non_hydrostatic','non_hydrostatic_raw_word','non_hydrostatic_branch_bit','hypsometric_opt','n_moist','runtime_p_qv','param_first_scalar','use_theta_m'):
                    if e[key]!=guard[key]:raise ValueError('phi guard differs from entry')
                if guard['k_plus_one']!=k+1 or guard['kme']!=e['bounds']['kme']:raise ValueError('phi guard bounds differ')
                expected_class={0x13eb579:'solve_em_RK',0x13ffdd4:'solve_em_postphysics'}.get(int(e['caller_pc'],16),'other_unclassified')
                if e['caller_class']!=expected_class:raise ValueError('phi caller class differs')
                d=e['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1;nj=d['jme']-d['jms']+1
                expected_qv=int(e['moist_base'],16)+(e['runtime_p_qv']-1)*ni*nk*nj*4
                if int(e['qv_base'],16)!=expected_qv:raise ValueError('phi QV slice address differs')
                guard=None;phi_count+=1
            elif guard is not None:raise ValueError('phi guard not followed by phi entry')
            stack.append(e)
        elif kind=='vspow_entry':
            if not stack or stack[-1].get('function')!='phi' or pending_v is not None:raise ValueError('orphan vspow entry')
            phi=stack[-1];d=phi['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
            offset=4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(i-d['ims']))
            row_offset=4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+(d['its']-d['ims']))
            row=int(phi['p_base'],16)+row_offset;lane=i-d['its'];length=min(d['ite'],d['ide']-1)-d['its']+1
            if (int(e['row_pointer'],16)!=row or e['lane_index']!=lane or e['row_length']!=length or
                int(e['output_address'],16)!=row+4*lane or int(e['output_address'],16)!=int(phi['p_base'],16)+offset):
                raise ValueError('vspow target address or row/lane differs')
            pending_v=e
        elif kind=='vspow_return':
            if pending_v is None or any(e[x]!=pending_v[x] for x in ('caller_pc','row_pointer','lane_index','row_length','output_address')):
                raise ValueError('unpaired vspow return')
            vspow_count+=1;stack[-1]['_vspow_result']=e['output_word'];pending_v=None
        elif kind=='gap_start':
            if gap is not None or not stack or stack[-1].get('function')!='calc_last':raise ValueError('invalid gap start')
            gap={'start':e,'last':e['p_word'],'watches':0,'phi_return':None}
        elif kind=='gap_watch_after':
            if gap is None or e['target_address']!=gap['start']['target_address'] or e['pre_word']!=gap['last']:
                raise ValueError('gap watch continuity differs')
            gap['last']=e['post_word'];gap['watches']+=1
        elif kind=='gap_end':
            if gap is None or e['target_address']!=gap['start']['target_address'] or e['initial_word']!=gap['start']['p_word'] or e['final_word']!=gap['last'] or e['watch_events']!=gap['watches']:
                raise ValueError('gap closure differs')
            if gap['phi_return'] is None:raise ValueError('no phi producer observed in pressure gap')
            if e['last_phi_p_word']!=gap['phi_return']['fields']['p'] or e['last_phi_matches_prep']!=(e['last_phi_p_word']==e['final_word']):
                raise ValueError('phi-to-prep value bridge differs')
            gaps.append({'kdm_completed':e['kdm_completed'],'last_phi_matches_prep':e['last_phi_matches_prep'],'watch_events':e['watch_events']})
            last_phi=gap['phi_return'];gap=None
        elif kind=='function_return':
            if not stack or stack[-1]['function']!=fn or pending_v is not None:raise ValueError('unpaired function return')
            entry=stack.pop()
            for key in ('caller_pc','bounds'):
                if key in entry and e.get(key)!=entry[key]:raise ValueError('return identity differs')
            if fn=='phi':
                if '_vspow_result' not in entry:raise ValueError('phi lacks target-row vspow')
                e['_entry_qv_base']=entry['qv_base'];e['_entry_qv_word']=entry['fields']['qv']
                if gap is not None:gap['phi_return']=e
            elif fn=='prep':
                last_prep={'entry':entry,'return':e}
                if last_phi is None or last_phi['_entry_qv_base']!=entry['qv_base']:
                    raise ValueError('phi to prep QV pointer differs')
            elif fn=='kdm':
                if last_prep is None:raise ValueError('KDM missing prep')
                pe=last_prep['entry'];pr=last_prep['return']
                if any(pe[x]!=entry[y] for x,y in [('th_out_base','th_base'),('pii_out_base','pii_base'),('pf_out_base','p_base'),('qv_base','qv_base')]):raise ValueError('prep to KDM pointer differs')
                bridges.append({'timestep':entry['timestep'],
                    'phi_to_prep_qv_words_equal':last_phi['_entry_qv_word']==pe['fields']['qv'],
                    'prep_to_kdm_word_equal':{x:pr['fields'][x]==entry['fields'][y] for x,y in [('th','th'),('pii','pii'),('pf','p')]},
                    'prep_to_kdm_qv_words_equal':pe['fields']['qv']==entry['fields']['qv']})
                last_prep=None;last_phi=None
        else:raise ValueError('unknown phi event')
    if stack or guard is not None or gap is not None or pending_v is not None:raise ValueError('incomplete phi event sequence')
    if len(gaps)!=4 or [g['kdm_completed'] for g in gaps]!=[0,1,2,3]:raise ValueError('gap timestep coverage differs')
    return {'event_file_sha256':base.sha(path),'event_count':len(events),'phi_calls':phi_count,'vspow_calls':vspow_count,
            'gap_bridges':gaps,'prep_kdm_bridges':bridges,'target_entry_return_matches':8,
            'limitations':'Caller PCs and observed changed stores only; generic power is not asserted bit-exact and post-watch PCs require preinstruction replay.'}


def run(arm,target):
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm
    inputs=json.loads((dest/'case_receipt.json').read_text())['inputs']
    if any(base.sha(dest/n)!=h for n,h in inputs.items()):raise ValueError('inputs changed')
    output=dest/'phi_capture';output.mkdir(exist_ok=False)
    owner=TARGETS[target][0];cpus=range(48,56) if arm=='B1' else range(56,64)
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,cpus)),CP05_OUTPUT=str(output),CP05_OWNER=str(owner),CP05_TARGET=target,CP05_SCRIPT=str(HERE/'phi_probe.py'))
    cmd=['taskset','-c',','.join(map(str,cpus)),'/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8','/bin/bash',str(HERE/'writer_rank_wrapper.sh')]
    profile=base.require_runtime_profile(dest/'wrf.exe');start=time.time()
    with (dest/'phi_launcher.log').open('xb') as log:
        proc=subprocess.Popen(cmd,cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);seen={}
        try:
            while True:
                base.observe_descendants(proc.pid,seen)
                try:code=proc.wait(timeout=2);break
                except subprocess.TimeoutExpired:
                    if time.time()-start>1800:raise TimeoutError('bounded MPI timeout')
        except BaseException:
            base.terminate_group(proc,seen)
            (dest/'phi_descendants.json').write_text(json.dumps({'process_group':proc.pid,'sampled_pids':seen},indent=2)+'\n')
            raise
    (dest/'phi_descendants.json').write_text(json.dumps({'sampling':'approximately every 2 seconds; short-lived descendants may be missed','process_group':proc.pid,'pids':seen},indent=2)+'\n')
    after={n:base.sha(dest/n) for n in inputs}
    if code or after!=inputs:base.terminate_group(proc,seen);raise ValueError('MPI failed or inputs changed')
    logs=sorted(dest.glob('rsl.out.*'))
    if len(logs)!=8 or any('SUCCESS COMPLETE WRF' not in p.read_text(errors='replace') for p in logs):raise ValueError('rank success markers missing')
    h=dest/'wrfout_d01_2026-08-16_12:00:00';ref=(base.B1 if arm=='B1' else base.DM)/h.name
    phase0=json.loads((writer.PHASE0/(arm+'_parity_receipt.json')).read_text())
    if base.sha(h)!=phase0['h00_sha256'] or base.sha(ref)!=phase0['h00_sha256']:raise ValueError('h00 parity differs')
    checks=validate_capture(arm,target,dest);require_freeze()
    if base.require_runtime_profile(dest/'wrf.exe')!=profile:raise ValueError('runtime profile changed')
    source=base.B1 if arm=='B1' else base.DM;original=json.loads((dest/'case_receipt.json').read_text())['source_hashes']
    if any(base.sha(source/n)!=v for n,v in original.items()):raise ValueError('source inputs changed')
    result={'status':'PASS_PHI_DISCOVERY','arm':arm,'target':target,'argv':cmd,'runtime_profile_sha256':profile,
            'elapsed_seconds':time.time()-start,'inputs_after':after,'h00_sha256':base.sha(h),
            'sampled_descendants_sha256':base.sha(dest/'phi_descendants.json'),**checks}
    (dest/'phi_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(arm,target,'PASS',flush=True)


if __name__=='__main__':
    require_freeze();action,arm,target=sys.argv[1:]
    if arm not in ('B1','DM065') or target not in TARGETS:raise ValueError('invalid case')
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm;prior_case=dest.exists();prior_capture=(dest/'phi_capture').exists()
    try:
        if action=='prepare':base.prepare(arm)
        elif action=='run':run(arm,target)
        else:raise ValueError('invalid action')
    except BaseException as exc:
        if dest.is_dir() and ((action=='prepare' and not prior_case) or (action=='run' and not prior_capture)):
            f=dest/'phi_failed_attempt.json'
            if not f.exists():f.write_text(json.dumps({'status':'FAILED_OR_INTERRUPTED','action':action,'target':target,'error_type':type(exc).__name__,'error':str(exc)},indent=2)+'\n')
        raise
