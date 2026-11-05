#!/usr/bin/env python3
"""Gate the bounded target phi7 machine-numerator observation."""
import json,os,struct,subprocess,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import phi_case as phi_case
base=phi_case.base
TARGET='p20183';OWNER=5
PCS=['0x2156fe7','0x2156fea','0x2156ff6','0x2156ff9','0x2156fff','0x2157002','0x2157005','0x2157067','0x215706a','0x215706f','0x2157072','0x2157077']
OPCODES=['0f5cd3','488b83a0020000','0f58da','430f1054bd00','0f5cda','0f5ed8','0f295b30','0f5ec8','430f1004be','0f5cc8','430f110cbc','4983c704']


def require_freeze():
    path=HERE/'numerator_freeze.json';expected=os.environ.get('CP05_NUMERATOR_FREEZE_SHA')
    if not expected or not path.is_file() or base.sha(path)!=expected:raise ValueError('reviewed numerator freeze and root GO required')
    f=json.loads(path.read_text());p0=phi_case.writer.PHASE0;pd=base.BUNDLE/'native/phi_discovery/p20183'
    required=[HERE/'numerator_case.py',HERE/'numerator_probe.py',HERE/'numerator_plan.json',HERE/'test_numerator_gate.py',
              HERE/'phi_probe.py',HERE/'phi_case.py',HERE/'phi_schema.json',HERE/'phi_freeze.json',HERE/'writer_rank_wrapper.sh',
              HERE/'writer_case.py',HERE/'parity_case.py',HERE/'parity_freeze.json',base.BUNDLE/'native/phi_source_lineage.json',
              base.ROOT/'tests/intel_toolchain.sh',base.CORNERS,base.PRIOR_MANIFEST,base.PRIOR_GLOBAL,
              p0/'B1_parity_receipt.json',p0/'DM065_parity_receipt.json',p0/'external_capture_inventory.json',
              pd/'paired_closure.json',pd/'B1/phi_receipt.json',pd/'DM065/phi_receipt.json',
              Path('/usr/bin/gdb'),Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun'),
              base.B1/'wrf.exe',base.B1/'wrfinput_d01',base.DM/'wrfinput_d01']
    if set(f['sha256'])!={str(p.resolve()) for p in required}:raise ValueError('numerator freeze inventory differs')
    if any(base.sha(p)!=digest for p,digest in f['sha256'].items()):raise ValueError('numerator frozen input changed')


def lane_word(vector,lane):
    raw=bytes.fromhex(vector)
    if len(raw)!=16 or not 0<=lane<4:raise ValueError('bad vector/lane')
    return raw[4*lane:4*lane+4].hex()


def float_word(raw):return np.frombuffer(bytes.fromhex(raw),dtype='<f4')[0]


def word_float(value):return np.asarray(np.float32(value),dtype='<f4').tobytes().hex()


def validate_numerator(arm,dest):
    path=dest/'phi_capture/numerator_rank5.jsonl';events=[json.loads(x) for x in path.read_text().splitlines()]
    if [x['sequence'] for x in events]!=list(range(1,len(events)+1)) or any(x['arm']!=arm or x['target']!=TARGET or (x['i'],x['j'],x['k'])!=(144,142,4) for x in events):raise ValueError('numerator event identity differs')
    phi=[x for x in events if x['event']=='phi7_entry'];pre=[x for x in events if x['event']=='vector_prepoint'];reads=[x for x in events if x['event']=='read_watch_after'];stops=[x for x in events if x['event']=='instruction_stop'];fin=[x for x in events if x['event']=='phi7_return']
    if len(phi)!=1 or len(pre)!=1 or len(reads)!=1 or len(fin)!=1 or not fin[0]['captured'] or [x['pc'] for x in stops]!=PCS or [x['opcode'] for x in stops]!=OPCODES:
        raise ValueError('incomplete or unexpected instruction sequence')
    if not (phi[0]['sequence']<reads[0]['sequence']<pre[0]['sequence']<stops[0]['sequence'] and stops[-1]['sequence']<fin[0]['sequence']):raise ValueError('numerator event ordering differs')
    if (phi[0]['caller_pc']!='0x13eb579' or phi[0]['kdm_completed']!=1 or
        phi[0]['hypsometric_opt']!=2 or phi[0]['use_theta_m']!=1 or
        (phi[0]['non_hydrostatic'] & 1)!=1 or
        struct.unpack('<i',bytes.fromhex(phi[0]['non_hydrostatic_raw_word']))[0]!=phi[0]['non_hydrostatic'] or
        reads[0]['reported_pc'] not in ('0x2156fdb','0x2156fe7','0x2156ff6','0x2156fff')):
        raise ValueError('phi7 caller, branch or watched vector-read PC differs')
    d=phi[0]['bounds'];ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
    def offset(level):return 4*((142-d['jms'])*nk*ni+(level-d['kms'])*ni+(144-d['ims']))
    ph=int(phi[0]['ph_base'],16);phb=int(phi[0]['phb_base'],16);al=int(phi[0]['al_base'],16)
    expected_addresses={'ph':hex(ph+offset(4)),'ph_next':hex(ph+offset(5)),
                        'phb':hex(phb+offset(4)),'phb_next':hex(phb+offset(5))}
    if (phi[0]['neighbor_watch_address']!=hex(ph+offset(3)) or reads[0]['watched_address']!=phi[0]['neighbor_watch_address'] or
        phi[0]['al_address']!=hex(al+offset(4)) or pre[0]['al_target_address']!=phi[0]['al_address'] or
        pre[0]['operand_addresses']!=expected_addresses or pre[0]['pc']!='0x2156f80' or not 0<=pre[0]['skipped_vectors']<=500):
        raise ValueError('independent target/neighbor address derivation differs')
    lane=pre[0]['lane'];mapping=pre[0]['operand_slot_mapping'];words=pre[0]['operand_words']
    expected=json.loads((HERE/'numerator_plan.json').read_text())['input_binding'][arm]
    if phi[0]['operand_words']!=expected or words!=expected:
        raise ValueError('phi7 input differs from frozen observed words')
    if set(mapping.values())!={0,1,2,3} or any(x['lane']!=lane for x in stops):raise ValueError('operand mapping or lane differs')
    total_bytes=ni*nk*(d['jme']-d['jms']+1)*4
    if not (ph+total_bytes<=phb or phb+total_bytes<=ph):raise ValueError('PH and PHB storage overlap')
    load_successors=('0x2156fdb','0x2156fe7','0x2156ff6','0x2156fff')
    if reads[0]['reported_pc'] not in (load_successors[mapping['ph']],load_successors[mapping['ph_next']]):
        raise ValueError('PH read-watch PC does not match a PH operand load')
    slots={n:words[name] for name,n in mapping.items()}
    if (lane_word(stops[0]['xmm2'],lane)!=slots[0] or lane_word(stops[0]['xmm3'],lane)!=slots[1] or
        lane_word(stops[2]['xmm3'],lane)!=slots[2] or lane_word(stops[4]['xmm2'],lane)!=slots[3]):raise ValueError('machine input registers differ from observed PH/PHB words')
    with np.errstate(all='raise'):
        sub1=word_float(np.float32(float_word(slots[0])-float_word(slots[1])))
        add=word_float(np.float32(float_word(slots[2])+float_word(sub1)))
        numerator=word_float(np.float32(float_word(add)-float_word(slots[3])))
    if lane_word(stops[1]['xmm2'],lane)!=sub1 or lane_word(stops[3]['xmm3'],lane)!=add or lane_word(stops[5]['xmm3'],lane)!=numerator:
        raise ValueError('actual SIMD arithmetic differs from float32 replay')
    first_div=word_float(np.float32(float_word(numerator)/float_word(lane_word(stops[5]['xmm0'],lane))))
    if lane_word(stops[6]['xmm3'],lane)!=first_div or lane_word(stops[7]['xmm1'],lane)!=first_div:
        raise ValueError('first division or saved numerator differs')
    log_word=lane_word(stops[7]['xmm0'],lane)
    second_div=word_float(np.float32(float_word(first_div)/float_word(log_word)))
    if lane_word(stops[8]['xmm1'],lane)!=second_div or lane_word(stops[9]['xmm1'],lane)!=second_div:
        raise ValueError('second division differs')
    if lane_word(stops[9]['xmm0'],lane)!=pre[0]['alb_word']:
        raise ValueError('actual ALB operand differs from target')
    final_al=word_float(np.float32(float_word(second_div)-float_word(pre[0]['alb_word'])))
    if (lane_word(stops[10]['xmm1'],lane)!=final_al or stops[10]['al_target_address']!=pre[0]['al_target_address'] or
        stops[11]['al_target_address']!=pre[0]['al_target_address'] or stops[11]['stored_al_word']!=final_al):
        raise ValueError('AL arithmetic/vector lane/store binding differs')
    phi_events=[json.loads(x) for x in (dest/'phi_capture/phi_rank5.jsonl').read_text().splitlines()]
    phientries=[x for x in phi_events if x['event']=='function_entry' and x.get('function')=='phi']
    phireturns=[x for x in phi_events if x['event']=='function_return' and x.get('function')=='phi']
    if (len(phientries)<7 or any(phientries[6]['fields'][key]!=value for key,value in expected.items()) or
        any(phientries[6][key]!=phi[0][key] for key in ('caller_pc','kdm_completed','hypsometric_opt','use_theta_m','non_hydrostatic','non_hydrostatic_raw_word'))):
        raise ValueError('phi7 identity/input differs from paired phi capture')
    if len(phireturns)<7 or phireturns[6]['fields']['al']!=stops[11]['stored_al_word']:
        raise ValueError('stored AL does not match phi7 returned AL')
    return {'event_file_sha256':base.sha(path),'phi7_caller_pc':phi[0]['caller_pc'],'lane':lane,
            'operand_slot_mapping':mapping,'input_words':words,'after_sub_word':sub1,'after_add_word':add,
            'numerator_word':numerator,'first_division_word':first_div,'observed_log_word':log_word,'second_division_word':second_div,
            'alb_word':pre[0]['alb_word'],'stored_al_word':stops[11]['stored_al_word'],
            'actual_instruction_order':'slot0 - slot1; slot2 + result; result - slot3; then division/log and AL vector store',
            'limitations':'Observed one target lane in one phi call per arm; no alternate grouping or source edit was executed.'}


def run(arm):
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm;inputs=json.loads((dest/'case_receipt.json').read_text())['inputs']
    if any(base.sha(dest/n)!=h for n,h in inputs.items()):raise ValueError('prepared inputs changed')
    output=dest/'phi_capture';output.mkdir(exist_ok=False)
    cpus=range(48,56) if arm=='B1' else range(56,64)
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,cpus)),CP05_OUTPUT=str(output),CP05_OWNER='5',CP05_TARGET=TARGET,CP05_ARM=arm,CP05_SCRIPT=str(HERE/'numerator_probe.py'))
    cmd=['taskset','-c',','.join(map(str,cpus)),'/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8','/bin/bash',str(HERE/'writer_rank_wrapper.sh')]
    profile=base.require_runtime_profile(dest/'wrf.exe');start=time.time()
    with (dest/'numerator_launcher.log').open('xb') as log:
        proc=subprocess.Popen(cmd,cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);seen={}
        try:
            while True:
                base.observe_descendants(proc.pid,seen)
                try:code=proc.wait(timeout=2);break
                except subprocess.TimeoutExpired:
                    if time.time()-start>1800:raise TimeoutError('bounded MPI timeout')
        except BaseException:
            base.terminate_group(proc,seen)
            (dest/'numerator_descendants.json').write_text(json.dumps({'process_group':proc.pid,'sampled_pids':seen},indent=2)+'\n');raise
    (dest/'numerator_descendants.json').write_text(json.dumps({'sampling':'approximately every 2 seconds; short-lived descendants may be missed','process_group':proc.pid,'pids':seen},indent=2)+'\n')
    after={n:base.sha(dest/n) for n in inputs}
    if code or after!=inputs:base.terminate_group(proc,seen);raise ValueError('MPI failed or inputs changed')
    logs=sorted(dest.glob('rsl.out.*'))
    if len(logs)!=8 or any('SUCCESS COMPLETE WRF' not in p.read_text(errors='replace') for p in logs):raise ValueError('rank success markers missing')
    history=dest/'wrfout_d01_2026-08-16_12:00:00';ref=(base.B1 if arm=='B1' else base.DM)/history.name
    phase0=json.loads((phi_case.writer.PHASE0/(arm+'_parity_receipt.json')).read_text())
    if base.sha(history)!=phase0['h00_sha256'] or base.sha(ref)!=phase0['h00_sha256']:raise ValueError('h00 differs')
    phi_validation=phi_case.validate_capture(arm,TARGET,dest);numerator_validation=validate_numerator(arm,dest)
    require_freeze()
    if base.require_runtime_profile(dest/'wrf.exe')!=profile:raise ValueError('profile changed')
    source=base.B1 if arm=='B1' else base.DM;original=json.loads((dest/'case_receipt.json').read_text())['source_hashes']
    if any(base.sha(source/n)!=v for n,v in original.items()):raise ValueError('source inputs changed')
    result={'status':'PASS_NUMERATOR_OBSERVATION','arm':arm,'target':TARGET,'argv':cmd,
            'runtime_profile_sha256':profile,'elapsed_seconds':time.time()-start,'inputs_after':after,'h00_sha256':base.sha(history),
            'sampled_descendants_sha256':base.sha(dest/'numerator_descendants.json'),'phi_validation':phi_validation,**numerator_validation}
    (dest/'numerator_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(arm,'PASS',flush=True)


if __name__=='__main__':
    require_freeze();action,arm=sys.argv[1:]
    if arm not in ('B1','DM065'):raise ValueError('invalid arm')
    dest=base.RUNTIME/'gdb_parity'/base.ATTEMPT/arm;prior_case=dest.exists();prior_capture=(dest/'phi_capture').exists()
    try:
        if action=='prepare':base.prepare(arm)
        elif action=='run':run(arm)
        else:raise ValueError('invalid action')
    except BaseException as exc:
        if dest.is_dir() and ((action=='prepare' and not prior_case) or (action=='run' and not prior_capture)):
            f=dest/'numerator_failed_attempt.json'
            if not f.exists():f.write_text(json.dumps({'status':'FAILED_OR_INTERRUPTED','action':action,'error_type':type(exc).__name__,'error':str(exc)},indent=2)+'\n')
        raise
