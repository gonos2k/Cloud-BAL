#!/usr/bin/env python3
"""Exercise writer gate with prior observed target words and corruptions, no model run."""
import json
import os
import struct
import tempfile
from pathlib import Path

os.environ['CP05_ATTEMPT']='synthetic_writer_gate'
import writer_case as case


def main():
    arm='B1';target='nr20330';rank,i,j,k=case.TARGETS[target]
    prior=case.base.RUNTIME/'gdb_parity/phase0_03'/arm/'gdb_capture'
    snapshots={stage:case.selected_target(prior/f'selected_{stage}_rank{rank}.bin',(i,j,k)) for stage in ('entry','return')}
    names=('th','qv','qc','qr','qi','qs','qg','nn','nc','ni','nr','bg','den','p','pii')
    indexes=list(range(13))+[14,15]
    def fields(words):return {name:struct.pack('<I',words[index]).hex() for name,index in zip(names,indexes)}
    events=[]
    def emit(event,**kwargs):events.append({'event':event,'sequence':len(events)+1,'rank':rank,'target':target,'i':i,'j':j,'k':k,**kwargs})
    for step in range(1,5):
        for rk in (1,2,3):
            metadata={'function':'rk','candidate_timestep':step,'rk_step':rk,'scs':7,'sce':7,'runtime_p_qnr':7,'qnr_species_index':7,'qnr_base_pointer':'0x1000','target_pointer':'0x1234','bounds':{}}
            emit('function_entry',fields={'scalar_current':'00000000'},**metadata)
            emit('function_return',fields={'scalar_current':'00000000'},watch_events=0,**metadata)
        emit('function_entry',function='kdm',timestep=step,nr_base_pointer='0x1000',nr_matches_rk=True,fields=fields(snapshots['entry'][step]))
        emit('function_return',function='kdm',timestep=step,nr_base_pointer='0x1000',nr_matches_rk=True,fields=fields(snapshots['return'][step]))
    with tempfile.TemporaryDirectory(dir=case.base.RUNTIME) as temporary:
        dest=Path(temporary);out=dest/'writer_capture';out.mkdir();path=out/f'writer_rank{rank}.jsonl'
        def write():path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        write();receipt=case.validate_capture(arm,target,dest);assert receipt['target_entry_return_matches']==8
        events[1]['fields']['scalar_current']='0000803f';write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'lacks a watch event' in str(exc)
        else:raise AssertionError('changed unobserved QNR must fail')
        events[1]['fields']['scalar_current']='00000000';events[-1]['fields']['nr']='0000803f';write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'wrapper parity differs' in str(exc)
        else:raise AssertionError('changed target wrapper must fail')
        events[-1]['fields']['nr']=fields(snapshots['return'][4])['nr']
        # A second category can share the same numeric species index.
        unrelated=dict(events[0]);unrelated['qnr_base_pointer']='0x2000';unrelated['target_pointer']='0x2234'
        unrelated_return=dict(events[1]);unrelated_return['qnr_base_pointer']='0x2000';unrelated_return['target_pointer']='0x2234'
        events[0:0]=[unrelated,unrelated_return]
        def renumber():
            for number,event in enumerate(events,1):event['sequence']=number
        renumber();write();assert case.validate_capture(arm,target,dest)['unclassified_same_index_candidate_count']==1
        for e in events:
            if e.get('function')=='kdm' and e.get('timestep')==1:e['nr_base_pointer']='0x7777'
        write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'incomplete QNR RK stages' in str(exc)
        else:raise AssertionError('wrong bound pointer must fail')
        for e in events:
            if e.get('function')=='kdm' and e.get('timestep')==1:e['nr_base_pointer']='0x1000'
        saved=events[2:4];del events[2:4];renumber();write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'incomplete QNR RK stages' in str(exc)
        else:raise AssertionError('missing matched stage must fail')
        events[2:2]=saved;events[2:2]=[dict(saved[0]),dict(saved[1])];renumber();write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'incomplete QNR RK stages' in str(exc)
        else:raise AssertionError('duplicate matched stage must fail')
    print('writer gate baseline, changed-store and target-word rejection PASS')


if __name__=='__main__':main()
