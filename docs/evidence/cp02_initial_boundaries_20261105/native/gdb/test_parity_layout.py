#!/usr/bin/env python3
"""Synthetic, no-model check of GDB snapshot packing and float32 TK."""
import importlib.util
import os
import struct
import sys
import tempfile
import types
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[5]
SCRIPT=Path(__file__).with_name('parity_probe.py')
CORNERS=ROOT/'docs/evidence/cp02_thermo_cloud_path_20261105/cohorts/results/unique_global_corners.csv'
EXE='/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED/wrf.exe'


class DummyBreakpoint:
    def __init__(self,*args,**kwargs):pass

    @property
    def pending(self):
        return False


def main():
    memory={}
    fake=types.ModuleType('gdb')
    fake.Breakpoint=DummyBreakpoint;fake.FinishBreakpoint=DummyBreakpoint
    fake.current_progspace=lambda:types.SimpleNamespace(filename=EXE)
    commands=[]
    fake.execute=lambda command,*args,**kwargs:commands.append(command)
    fake.selected_inferior=lambda:types.SimpleNamespace(read_memory=lambda ptr,n:memory[ptr][:n])
    sys.modules['gdb']=fake
    with tempfile.TemporaryDirectory(dir=ROOT.parent/'runtime') as tmp:
        os.environ.update(CP05_CORNERS=str(CORNERS),CP05_OUTPUT=tmp,PMI_RANK='5')
        spec=importlib.util.spec_from_file_location('probe',SCRIPT);probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
        assert 'set startup-with-shell off' in commands
        probe.CELLS={(143,141),(144,141)}
        d={'ids':1,'ide':200,'jds':1,'jde':200,'kds':1,'kde':4,
           'ims':142,'ime':145,'jms':140,'jme':142,'kms':1,'kme':2,
           'its':143,'ite':144,'jts':141,'jte':141,'kts':1,'kte':2}
        pointers=[0]*77; arrays=[]
        for index,arg in enumerate(list(range(1,13))+[14,16,15]):
            a=(np.arange(24,dtype='f4').reshape(3,2,4)+np.float32(index+1))
            a[:,:,0]=np.nan
            pointers[arg-1]=1000+arg*1000;memory[pointers[arg-1]]=a.tobytes();arrays.append(a)
        ctx={'pointers':pointers,'step':1,'dims':d}
        probe.write_snapshot(ctx,'entry',1)
        global_bytes=(Path(tmp)/'global_entry_rank5.bin').read_bytes()
        selected_bytes=(Path(tmp)/'selected_entry_rank5.bin').read_bytes()
        assert global_bytes[:8]==selected_bytes[:8]==b'CBSP0001'
        assert struct.unpack('>15i',global_bytes[8:68])== (1,5,1,1,143,144,141,141,1,2,1,1,1,14,4)
        assert struct.unpack('>15i',selected_bytes[8:68])==(6,5,1,1,143,144,141,141,1,2,1,1,1,16,4)
        for n,(k,i) in enumerate((k,i) for k in (1,2) for i in (143,144)):
            values=[float(a[1,k-1,i-142]) for a in arrays]
            expected=values[:13]+[float(np.float32(np.float32(values[0])*np.float32(values[14])))]
            assert struct.unpack_from('>14f',global_bytes,68+56*n)==tuple(expected)
            row=struct.unpack_from('>3i16f',selected_bytes,68+76*n)
            assert row[:3]==(i,141,k) and row[3:]==tuple(expected+[values[13],values[14]])
    print('synthetic global/selected raw layout and core-only TK PASS')


if __name__=='__main__':main()
