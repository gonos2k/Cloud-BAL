#!/usr/bin/env python3
"""Synthetic observed-vector arithmetic and target-store corruption checks."""
import ast,json,os,struct,tempfile
from pathlib import Path
import numpy as np
os.environ['CP05_ATTEMPT']='synthetic_numerator_gate'
import numerator_case as case


def main():
    probe=case.HERE/'numerator_probe.py'
    tree=ast.parse(probe.read_text())
    function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='vector_operand_bases')
    observed=[]
    namespace={'qword':lambda address: observed.append(address) or address+1000}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(probe),'exec'),namespace)
    assert namespace['vector_operand_bases'](0x1000,0x7777)==[0x1280+1000,0x1200+1000,0x12a0+1000,0x7777]
    assert observed==[0x1280,0x1200,0x12a0]
    plan=json.loads((case.HERE/'numerator_plan.json').read_text());words=plan['input_binding']['B1'];lane=2
    mapping={'ph_next':0,'ph':1,'phb_next':2,'phb':3}
    f=lambda word:np.frombuffer(bytes.fromhex(word),dtype='<f4')[0]
    w=lambda value:np.asarray(np.float32(value),dtype='<f4').tobytes().hex()
    sub=w(np.float32(f(words['ph_next'])-f(words['ph'])))
    add=w(np.float32(f(words['phb_next'])+f(sub)))
    num=w(np.float32(f(add)-f(words['phb'])))
    one=w(1.);zero=w(0.)
    def vec(word):return ('00000000'*lane)+word+('00000000'*(3-lane))
    regs=[(zero,words['ph_next'],words['ph'],zero),
          (zero,sub,words['ph'],zero),
          (zero,sub,words['phb_next'],zero),
          (zero,sub,add,zero),
          (zero,words['phb'],add,zero),
          (num,words['phb'],num,zero),
          (num,words['phb'],one,zero),
          (one,words['phb'],one,one),
          (one,words['phb'],one,one),
          (one,words['phb'],one,one),
          (one,words['phb'],one,zero),
          (one,words['phb'],one,zero)]
    events=[]
    def emit(event,**kwargs):events.append({'event':event,'sequence':len(events)+1,'arm':'B1','target':'p20183','i':144,'j':142,'k':4,**kwargs})
    bounds={'ims':143,'ime':145,'jms':141,'jme':143,'kms':1,'kme':40}
    ni=3;nk=40
    offset=lambda level:4*((142-bounds['jms'])*nk*ni+(level-bounds['kms'])*ni+(144-bounds['ims']))
    addresses={'ph':hex(0x1000+offset(4)),'ph_next':hex(0x1000+offset(5)),
               'phb':hex(0x2000+offset(4)),'phb_next':hex(0x2000+offset(5))}
    target=hex(0x3000+offset(4));neighbor=hex(0x1000+offset(3))
    emit('phi7_entry',operand_words=words,caller_pc='0x13eb579',bounds=bounds,
         ph_base='0x1000',phb_base='0x2000',al_base='0x3000',al_address=target,neighbor_watch_address=neighbor,
         kdm_completed=1,hypsometric_opt=2,use_theta_m=1,non_hydrostatic=-1,non_hydrostatic_raw_word='ffffffff')
    emit('read_watch_after',watched_address=neighbor,reported_pc='0x2156fdb')
    emit('vector_prepoint',pc='0x2156f80',skipped_vectors=3,lane=lane,operand_slot_mapping=mapping,operand_addresses=addresses,operand_words=words,alb_word=one,al_target_address=target)
    for index,(pc,opcode) in enumerate(zip(case.PCS,case.OPCODES)):
        x0,x2,x3,x1=regs[index];extra={}
        if index>=10:extra.update(al_target_address=target)
        if index==11:extra.update(stored_al_word=zero)
        emit('instruction_stop',pc=pc,opcode=opcode,lane=lane,xmm0=vec(x0),xmm1=vec(x1),xmm2=vec(x2),xmm3=vec(x3),**extra)
    emit('phi7_return',captured=True)
    with tempfile.TemporaryDirectory(dir=case.base.RUNTIME) as temporary:
        dest=Path(temporary);cap=dest/'phi_capture';cap.mkdir();path=cap/'numerator_rank5.jsonl';phi=cap/'phi_rank5.jsonl'
        phi.write_text(''.join(json.dumps({'event':'function_entry','function':'phi','fields':words,'caller_pc':'0x13eb579','kdm_completed':1,'hypsometric_opt':2,'use_theta_m':1,'non_hydrostatic':-1,'non_hydrostatic_raw_word':'ffffffff'})+'\n'+json.dumps({'event':'function_return','function':'phi','fields':{'al':zero}})+'\n' for _ in range(7)))
        def write():path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        write();r=case.validate_numerator('B1',dest);assert r['numerator_word']==num
        events[6]['xmm3']=vec(zero);write()
        try:case.validate_numerator('B1',dest)
        except ValueError:pass
        else:raise AssertionError('corrupted SIMD operand accepted')
        events[6]['xmm3']=vec(words['phb_next']);events[-2]['stored_al_word']=one;write()
        try:case.validate_numerator('B1',dest)
        except ValueError:pass
        else:raise AssertionError('corrupted AL store accepted')
        events[-2]['stored_al_word']=zero;events[1]['watched_address']='0x1';write()
        try:case.validate_numerator('B1',dest)
        except ValueError as exc:assert 'address derivation' in str(exc)
        else:raise AssertionError('wrong neighbor watch accepted')
        events[1]['watched_address']=neighbor;events[1]['reported_pc']='0x2156fff';write()
        try:case.validate_numerator('B1',dest)
        except ValueError as exc:assert 'PH operand load' in str(exc)
        else:raise AssertionError('PHB-load PC accepted as PH watch')
    print('numerator machine-order, lane and AL corruption gates PASS')


if __name__=='__main__':main()
