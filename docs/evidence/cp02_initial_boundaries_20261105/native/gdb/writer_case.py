#!/usr/bin/env python3
"""Bounded original-executable writer discovery with target wrapper parity."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import parity_case as base

TARGETS={'nr20330':(5,141,142,2),'nr20330max':(5,141,143,11),
         'p20183':(5,144,142,4),'p17051':(3,140,120,38)}
PHASE0=base.BUNDLE/'native/phase0'


def require_freeze():
    path=HERE/'writer_freeze.json'; expected=os.environ.get('CP05_WRITER_FREEZE_SHA')
    if not expected or not path.is_file() or base.sha(path)!=expected:
        raise ValueError('reviewed writer freeze and root GO identity required')
    frozen=json.loads(path.read_text())
    required=[HERE/'writer_case.py',HERE/'writer_probe.py',HERE/'writer_schema.json',HERE/'test_writer_gate.py',
              HERE/'writer_rank_wrapper.sh',HERE/'parity_case.py',HERE/'parity_freeze.json',
              base.ROOT/'tests/intel_toolchain.sh',base.CORNERS,base.PRIOR_MANIFEST,base.PRIOR_GLOBAL,
              PHASE0/'B1_parity_receipt.json',PHASE0/'DM065_parity_receipt.json',PHASE0/'external_capture_inventory.json',
              Path('/usr/bin/gdb'),Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun'),
              base.B1/'wrf.exe',base.B1/'wrfinput_d01',base.DM/'wrfinput_d01']
    if set(frozen['sha256'])!={str(p.resolve()) for p in required}:raise ValueError('writer freeze inventory differs')
    if any(base.sha(p)!=digest for p,digest in frozen['sha256'].items()):raise ValueError('writer frozen input changed')


def selected_target(path,ijk):
    result={}
    with path.open('rb') as stream:
        for _ in range(4):
            header=stream.read(68)
            if len(header)!=68 or header[:8]!=b'CBSP0001':raise ValueError('bad selected header')
            stage,rank,call,step,*rest=struct.unpack('>15i',header[8:])
            nfields,nrecords=rest[-2:]
            if nfields!=16:raise ValueError('wrong selected fields')
            found=[]
            for _ in range(nrecords):
                row=stream.read(76)
                if len(row)!=76:raise ValueError('truncated selected record')
                values=struct.unpack('>3i16I',row)
                if values[:3]==ijk:found.append(values[3:])
            if len(found)!=1 or step in result:raise ValueError('missing or duplicate selected target')
            result[step]=found[0]
    return result


def event_words(fields):
    names=('th','qv','qc','qr','qi','qs','qg','nn','nc','ni','nr','bg','den')
    raw=lambda name:struct.unpack('<I',bytes.fromhex(fields[name]))[0]
    th=struct.unpack('<f',bytes.fromhex(fields['th']))[0]
    pii=struct.unpack('<f',bytes.fromhex(fields['pii']))[0]
    tk=struct.unpack('<I',struct.pack('<f',th*pii))[0]
    return tuple(raw(name) for name in names)+(tk,raw('p'),raw('pii'))


def validate_pressure_guard(event):
    raw=struct.unpack('<i',bytes.fromhex(event['non_hydrostatic_raw_word']))[0]
    if raw!=event['non_hydrostatic'] or (raw & 1)!=event['non_hydrostatic_branch_bit'] or (raw & 1)!=1 or event['k_plus_one']>event['kme']:
        raise ValueError('pressure branch or k+1 guard differs')


def validate_capture(arm,target,dest):
    rank,i,j,k=TARGETS[target];output=dest/'writer_capture';path=output/f'writer_rank{rank}.jsonl'
    events=[json.loads(line) for line in path.read_text().splitlines()]
    if [e['sequence'] for e in events]!=list(range(1,len(events)+1)) or any(e['rank']!=rank or e['target']!=target or (e['i'],e['j'],e['k'])!=(i,j,k) for e in events):
        raise ValueError('event identity or sequence differs')
    inventory=json.loads((PHASE0/'external_capture_inventory.json').read_text())
    prior={x['path']:x['sha256'] for x in inventory['arms'][arm]}
    kdm=[]
    kdm_nr_pointers={}
    for stage in ('entry','return'):
        reference=base.RUNTIME/'gdb_parity/phase0_03'/arm/'gdb_capture'/f'selected_{stage}_rank{rank}.bin'
        if base.sha(reference)!=prior[str(reference.resolve())]:raise ValueError('phase0 target reference changed')
        expected=selected_target(reference,(i,j,k))
        rows=[e for e in events if e['event']==f'function_{stage}' and e.get('function')=='kdm']
        if len(rows)!=4 or {e['timestep'] for e in rows}!={1,2,3,4}:raise ValueError('missing target KDM boundaries')
        for row in rows:
            if event_words(row['fields'])!=expected[row['timestep']]:raise ValueError('target wrapper parity differs')
            if target.startswith('nr'):
                if row['nr_matches_rk'] is not True:raise ValueError('QNR pointer binding failed')
                if stage=='entry':kdm_nr_pointers[row['timestep']]=row['nr_base_pointer']
                elif kdm_nr_pointers.get(row['timestep'])!=row['nr_base_pointer']:
                    raise ValueError('KDM NR entry/return base pointer differs')
            if target.startswith('p') and row['prep_binding_matches'] is not True:raise ValueError('pressure pointer binding failed')
        kdm.extend(rows)
    active=None; watches=[]; pending_guard=None
    for event in events:
        if event['event']=='pressure_guard':
            if active is not None or pending_guard is not None:raise ValueError('unpaired pressure guard')
            validate_pressure_guard(event);pending_guard=event
        elif event['event']=='function_entry':
            if active is not None:raise ValueError('overlapping observed producer calls')
            if event['function']=='pressure':
                if pending_guard is None:raise ValueError('missing pressure guard')
                for key in ('candidate_timestep','acoustic_iteration','non_hydrostatic','non_hydrostatic_raw_word','non_hydrostatic_branch_bit'):
                    if event.get(key)!=pending_guard[key]:raise ValueError('pressure guard metadata differs')
                if pending_guard['k_plus_one']!=event['k']+1 or pending_guard['kme']!=event['bounds']['kme']:
                    raise ValueError('pressure guard bounds differ')
                pending_guard=None
            elif pending_guard is not None:
                raise ValueError('pressure guard not followed by pressure entry')
            active=event;watches=[]
        elif event['event']=='watch_after':
            if active is None:raise ValueError('watch event outside producer call')
            owner={'rk':'rk_update_scalar','pressure':'calc_p_rho'}.get(active['function'])
            if event['owner']!=owner or event['target_pointer']!=active['target_pointer']:
                raise ValueError('watch event owner or target differs')
            if event['candidate_timestep']!=active['candidate_timestep']:
                raise ValueError('watch event timestep differs')
            for key in ('rk_step','acoustic_iteration'):
                if key in active and event.get(key)!=active[key]:raise ValueError('watch event stage differs')
            watches.append(event)
        elif event['event']=='function_return':
            if active is None or event['function']!=active['function']:
                raise ValueError('unpaired or out-of-order producer return')
            for key in ('candidate_timestep','timestep','rk_step','acoustic_iteration','target_pointer','bounds'):
                if key in active and event.get(key)!=active[key]:raise ValueError('producer return metadata differs')
            if active['function'] in ('rk','pressure'):
                if event['watch_events']!=len(watches):raise ValueError('watch event count differs')
                field='scalar_current' if active['function']=='rk' else 'p'
                if active['function']=='rk' and active['fields']['scalar_current']!=event['fields'][field] and not watches:
                    raise ValueError('changed RK candidate update lacks a watch event')
                if watches and watches[-1]['post_word']!=event['fields'][field]:
                    raise ValueError('last watched word differs from producer return')
            active=None;watches=[]
        else:
            raise ValueError('unknown trace event')
    if active is not None or pending_guard is not None:raise ValueError('unclosed producer call or pressure guard')
    counts={}
    for e in events:
        key=e['event']+':'+e.get('function',e.get('owner',''))
        counts[key]=counts.get(key,0)+1
    op='rk' if target.startswith('nr') else 'pressure'
    entries=[e for e in events if e['event']=='function_entry' and e.get('function')==op]
    returns=[e for e in events if e['event']=='function_return' and e.get('function')==op]
    if len(entries)!=len(returns):raise ValueError('unpaired producer calls')
    if target.startswith('p') and sum(e['event']=='pressure_guard' for e in events)!=len(entries):
        raise ValueError('missing pressure guard event')
    for step in range(1,5):
        group=[e for e in entries if e['candidate_timestep']==step]
        if target.startswith('nr'):
            group=[e for e in group if e['qnr_base_pointer']==kdm_nr_pointers[step]]
            if any(not (e['scs']==e['sce']==e['runtime_p_qnr']==e['qnr_species_index']) for e in group):raise ValueError('QNR registry identity differs')
            if [e['rk_step'] for e in group]!=[1,2,3]:raise ValueError('incomplete QNR RK stages')
        else:
            # Pinned defaults: RK order 3, time_step_sound=0, nonadaptive,
            # dt=20 s, dx=dy=5000 m -> four sound steps; RK uses 1,2,4.
            if [e['acoustic_iteration'] for e in group] != [0,1,0,1,2,0,1,2,3,4]:
                raise ValueError('incomplete pressure RK/acoustic sequence')
            prep=[e for e in events if e['event']=='function_entry' and e.get('function')=='prep' and e['candidate_timestep']==step]
            pretr=[e for e in events if e['event']=='function_return' and e.get('function')=='prep' and e['candidate_timestep']==step]
            if len(prep)!=1 or len(pretr)!=1:raise ValueError('incomplete pressure prep')
    unmatched = ([e for e in entries if e['qnr_base_pointer'] != kdm_nr_pointers[e['candidate_timestep']]]
                 if target.startswith('nr') else [])
    return {'event_file_sha256':base.sha(path),'event_count':len(events),'event_counts':counts,
            'unclassified_same_index_candidate_count':len(unmatched),
            'unclassified_note':'Same numeric species index with different storage base remains unclassified; no species identity inferred.',
            'target_entry_return_matches':8,'watch_events':sum(e['event']=='watch_after' for e in events),
            'limitations':'Watchpoint reports after changed stores; zero events does not prove no writes. Store-PC and vector-lane arithmetic need separately authorized preinstruction replay.'}


def run(arm,target):
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm
    inputs=json.loads((dest/'case_receipt.json').read_text())['inputs']
    if any(base.sha(dest/n)!=h for n,h in inputs.items()):raise ValueError('prepared inputs changed')
    output=dest/'writer_capture';output.mkdir(exist_ok=False)
    owner=TARGETS[target][0];cpus=range(48,56) if arm=='B1' else range(56,64)
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,cpus)),CP05_OUTPUT=str(output),CP05_OWNER=str(owner),CP05_TARGET=target,CP05_SCRIPT=str(HERE/'writer_probe.py'))
    cmd=['taskset','-c',','.join(map(str,cpus)),'/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8','/bin/bash',str(HERE/'writer_rank_wrapper.sh')]
    profile=base.require_runtime_profile(dest/'wrf.exe');start=time.time()
    with (dest/'writer_launcher.log').open('xb') as log:
        process=subprocess.Popen(cmd,cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);seen={}
        try:
            while True:
                base.observe_descendants(process.pid,seen)
                try:exit_code=process.wait(timeout=2);break
                except subprocess.TimeoutExpired:
                    if time.time()-start>1800:raise TimeoutError('bounded MPI timeout')
        except BaseException:
            base.terminate_group(process,seen)
            (dest/'writer_descendants.json').write_text(json.dumps({'sampled_process_group':process.pid,'sampled_pids':seen},indent=2)+'\n')
            raise
    (dest/'writer_descendants.json').write_text(json.dumps({'sampling':'approximately every 2 seconds; short-lived descendants may be missed','process_group':process.pid,'pids':seen},indent=2)+'\n')
    after={n:base.sha(dest/n) for n in inputs}
    if exit_code or after!=inputs:
        base.terminate_group(process,seen);raise ValueError('MPI failed or inputs changed')
    if 'SUCCESS COMPLETE WRF' not in ''.join(p.read_text(errors='replace') for p in dest.glob('rsl.out.*')):
        raise ValueError('WRF success marker missing')
    history=dest/'wrfout_d01_2026-08-16_12:00:00';reference=(base.B1 if arm=='B1' else base.DM)/history.name
    phase0=json.loads((PHASE0/(arm+'_parity_receipt.json')).read_text())
    if phase0['status']!='PASS' or not history.exists() or base.sha(history)!=phase0['h00_sha256'] or base.sha(reference)!=phase0['h00_sha256']:
        raise ValueError('h00 history differs from frozen phase0')
    validation=validate_capture(arm,target,dest)
    require_freeze()
    if base.require_runtime_profile(dest/'wrf.exe')!=profile:raise ValueError('profile changed')
    source=base.B1 if arm=='B1' else base.DM
    original=json.loads((dest/'case_receipt.json').read_text())['source_hashes']
    if any(base.sha(source/n)!=h for n,h in original.items()):raise ValueError('source inputs changed')
    result={'status':'PASS_DISCOVERY_CAPTURE','arm':arm,'target':target,'argv':cmd,'runtime_profile_sha256':profile,
            'elapsed_seconds':time.time()-start,'inputs_after':after,'h00_sha256':base.sha(history),
            'sampled_descendants_sha256':base.sha(dest/'writer_descendants.json'),
            'sampled_escaped_groups':{str(pid):group for pid,(group,start) in seen.items() if group!=process.pid},**validation}
    (dest/'writer_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(arm,target,'PASS',flush=True)


if __name__=='__main__':
    require_freeze()
    action,arm,target=sys.argv[1:]
    if arm not in ('B1','DM065') or target not in TARGETS:raise ValueError('invalid arm or target')
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm;prior_case=dest.exists();prior_capture=(dest/'writer_capture').exists()
    try:
        if action=='prepare':base.prepare(arm)
        elif action=='run':run(arm,target)
        else:raise ValueError('invalid action')
    except BaseException as exc:
        if dest.is_dir() and ((action=='prepare' and not prior_case) or (action=='run' and not prior_capture)):
            failure=dest/'writer_failed_attempt.json'
            if not failure.exists():failure.write_text(json.dumps({'status':'FAILED_OR_INTERRUPTED','action':action,'target':target,'error_type':type(exc).__name__,'error':str(exc)},indent=2)+'\n')
        raise
