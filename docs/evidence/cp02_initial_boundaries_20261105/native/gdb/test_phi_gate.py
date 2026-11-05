#!/usr/bin/env python3
"""Synthetic nested phi/vspow/watch bridge and corruption checks; no model run."""
import json,os,struct,tempfile
from pathlib import Path
os.environ['CP05_ATTEMPT']='synthetic_phi_gate'
import phi_case as case


def main():
    arm='B1';target='p20183';rank,i,j,k=case.TARGETS[target]
    prior=case.base.RUNTIME/'gdb_parity/phase0_03'/arm/'gdb_capture'
    snapshots={stage:case.writer.selected_target(prior/f'selected_{stage}_rank{rank}.bin',(i,j,k)) for stage in ('entry','return')}
    names=('th','qv','qc','qr','qi','qs','qg','nn','nc','ni','nr','bg','den','p','pii');indexes=list(range(13))+[14,15]
    def fields(words):return {name:struct.pack('<I',words[index]).hex() for name,index in zip(names,indexes)}
    d={'ims':143,'ime':145,'jms':141,'jme':143,'kms':1,'kme':40,'its':143,'ite':145,'ide':200}
    offset=4*((j-d['jms'])*40*3+(k-1)*3+(i-d['ims']));pbase=0x1000;paddr=hex(pbase+offset)
    events=[]
    def emit(event,step,**kw):events.append({'event':event,'sequence':len(events)+1,'rank':rank,'target':target,'i':i,'j':j,'k':k,'kdm_entered':step,'kdm_completed':step,**kw})
    for step in range(4):
        emit('function_entry',step,function='calc_last',caller_pc='0x1',bounds=d,fields={})
        emit('gap_start',step,p_base=hex(pbase),target_address=paddr,p_word='00000000')
        emit('function_return',step,function='calc_last',caller_pc='0x1',bounds=d,fields={'p':'00000000'})
        guard={'caller_pc':'0x13eb579','caller_class':'solve_em_RK','non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff','non_hydrostatic_branch_bit':1,'hypsometric_opt':1,'n_moist':6,'runtime_p_qv':2,'param_first_scalar':2,'use_theta_m':1}
        emit('phi_guard',step,k_plus_one=k+1,kme=40,**guard)
        emit('function_entry',step,function='phi',bounds=d,p_base=hex(pbase),moist_base='0x1a60',qv_base='0x2000',fields={'qv':fields(snapshots['entry'][step+1])['qv']},**guard)
        v={'caller_pc':'0x21586bd','row_pointer':hex(pbase+offset-4),'lane_index':1,'row_length':3,'output_address':paddr}
        emit('vspow_entry',step,input_word='0000803f',exponent_word='0000803f',**v)
        emit('vspow_return',step,output_word='0000803f',**v)
        emit('function_return',step,function='phi',caller_pc='0x13eb579',bounds=d,fields={'p':'00000000'})
        emit('gap_end',step,target_address=paddr,initial_word='00000000',final_word='00000000',watch_events=0,last_phi_p_word='00000000',last_phi_matches_prep=True)
        qv=fields(snapshots['entry'][step+1])['qv'];pe={'p_in_base':hex(pbase),'th_out_base':'0x3000','pii_out_base':'0x4000','pf_out_base':'0x5000','qv_base':'0x2000'}
        emit('function_entry',step,function='prep',caller_pc='0x2',bounds=d,fields={'qv':qv},**pe)
        kfields=fields(snapshots['entry'][step+1]);emit('function_return',step,function='prep',caller_pc='0x2',bounds=d,fields={'th':kfields['th'],'pii':kfields['pii'],'pf':kfields['p']},**pe)
        ke={'th_base':'0x3000','pii_base':'0x4000','p_base':'0x5000','qv_base':'0x2000'}
        emit('function_entry',step,function='kdm',timestep=step+1,caller_pc='0x3',bounds=d,fields=kfields,**ke)
        emit('function_return',step,function='kdm',timestep=step+1,caller_pc='0x3',bounds=d,fields=fields(snapshots['return'][step+1]),**ke)
    with tempfile.TemporaryDirectory(dir=case.base.RUNTIME) as tmp:
        dest=Path(tmp);out=dest/'phi_capture';out.mkdir();path=out/f'phi_rank{rank}.jsonl'
        def write():
            for n,e in enumerate(events,1):e['sequence']=n
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        write();r=case.validate_capture(arm,target,dest);assert r['vspow_calls']==4 and len(r['gap_bridges'])==4
        events[3]['non_hydrostatic_branch_bit']=0;write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'invalid phi branch' in str(exc)
        else:raise AssertionError('corrupt branch accepted')
        events[3]['non_hydrostatic_branch_bit']=1;events[5]['output_address']='0x1';write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'vspow target address' in str(exc)
        else:raise AssertionError('wrong vspow target accepted')
        events[5]['output_address']=paddr;events[4]['qv_base']='0x2004';write()
        try:case.validate_capture(arm,target,dest)
        except ValueError as exc:assert 'QV slice address' in str(exc)
        else:raise AssertionError('wrong QV slice accepted')
    print('nested phi/vspow/bridge gate and corruption rejection PASS')


if __name__=='__main__':main()
