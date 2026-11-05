#!/usr/bin/env python3
"""Synthetic observed-vector arithmetic and target-store corruption checks."""
import json,os,struct,tempfile
from pathlib import Path
import numpy as np
os.environ['CP05_ATTEMPT']='synthetic_numerator_gate'
import numerator_case as case


def main():
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
    emit('phi7_entry',operand_words=words,caller_pc='0x13eb579')
    emit('read_watch_after')
    emit('vector_prepoint',lane=lane,operand_slot_mapping=mapping,operand_words=words,alb_word=one,al_target_address='0x2008')
    for index,(pc,opcode) in enumerate(zip(case.PCS,case.OPCODES)):
        x0,x2,x3,x1=regs[index];extra={}
        if index>=10:extra.update(al_target_address='0x2008')
        if index==11:extra.update(stored_al_word=zero)
        emit('instruction_stop',pc=pc,opcode=opcode,lane=lane,xmm0=vec(x0),xmm1=vec(x1),xmm2=vec(x2),xmm3=vec(x3),**extra)
    emit('phi7_return',captured=True)
    with tempfile.TemporaryDirectory(dir=case.base.RUNTIME) as temporary:
        dest=Path(temporary);cap=dest/'phi_capture';cap.mkdir();path=cap/'numerator_rank5.jsonl';phi=cap/'phi_rank5.jsonl'
        phi.write_text(''.join(json.dumps({'event':'function_entry','function':'phi','fields':words})+'\n'+json.dumps({'event':'function_return','function':'phi','fields':{'al':zero}})+'\n' for _ in range(7)))
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
    print('numerator machine-order, lane and AL corruption gates PASS')


if __name__=='__main__':main()
