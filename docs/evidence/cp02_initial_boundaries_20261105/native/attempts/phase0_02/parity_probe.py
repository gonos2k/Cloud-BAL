"""GDB Python script: read-only original-executable KDM wrapper parity capture.

Run only under the frozen, reviewed rank wrapper. The process is not modified.
"""
import csv
import hashlib
import json
import os
import struct
from pathlib import Path

import gdb
import numpy as np

CORNERS = Path(os.environ['CP05_CORNERS'])
CORNER_SHA = 'c2ba19be993cd82dfeac0ff1b3a02659d6c137b733903e563da91f4024aa65b9'
OUT = Path(os.environ['CP05_OUTPUT'])
RANK = int(os.environ['PMI_RANK'])
if not 0 <= RANK < 8:
    raise RuntimeError('invalid MPI rank')
SYMBOL = '*0x25df680'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if sha(Path(gdb.current_progspace().filename)) != '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f':
    raise RuntimeError('original executable identity differs')
if sha(CORNERS) != CORNER_SHA:
    raise RuntimeError('cohort identity differs')
with CORNERS.open(newline='') as stream:
    data = list(csv.DictReader(stream))
CELLS = {(int(r['wrf_i_1based']), int(r['wrf_j_1based'])) for r in data}
if len(CELLS) != 123:
    raise RuntimeError('unique cell inventory differs')
if not OUT.is_dir():
    raise RuntimeError('missing isolated output directory')


def argument_pointers():
    frame = gdb.selected_frame()
    registers = [int(frame.read_register(x)) for x in ('rdi','rsi','rdx','rcx','r8','r9')]
    stack = int(frame.read_register('rsp'))
    tail = bytes(gdb.selected_inferior().read_memory(stack + 8, 71 * 8))
    return registers + list(struct.unpack('<71Q', tail))


def integer(pointer):
    return struct.unpack('<i', bytes(gdb.selected_inferior().read_memory(pointer, 4)))[0]


def read_context():
    pointers = argument_pointers()
    step = integer(pointers[52])
    names = ('ids','ide','jds','jde','kds','kde','ims','ime','jms','jme','kms','kme','its','ite','jts','jte','kts','kte')
    dims = dict(zip(names, [integer(pointers[i-1]) for i in range(60,78)]))
    if not 1 <= step <= 4 or not (dims['ims'] <= dims['its'] <= dims['ite'] <= dims['ime'] and
            dims['jms'] <= dims['jts'] <= dims['jte'] <= dims['jme'] and
            dims['kms'] <= dims['kts'] <= dims['kte'] <= dims['kme']):
        raise RuntimeError('invalid timestep or KDM bounds')
    return {'pointers': pointers, 'step': step, 'dims': dims}


def read_fields(context):
    d = context['dims']; ni=d['ime']-d['ims']+1; nk=d['kme']-d['kms']+1; nj=d['jme']-d['jms']+1
    count = ni * nk * nj
    # 12 hydrometeor/state arrays, density, then pressure and Exner.
    args = list(range(1,13)) + [14,16,15]
    values=[]
    inferior=gdb.selected_inferior()
    for arg in args:
        pointer=context['pointers'][arg-1]
        if not pointer:
            raise RuntimeError('null KDM field pointer')
        raw=bytes(inferior.read_memory(pointer, count*4))
        values.append(np.frombuffer(raw,dtype='<f4').reshape((nj,nk,ni)))
    return values


def write_snapshot(context, stage, call):
    d=context['dims']; fields=read_fields(context); step=context['step']
    lo_i=max(d['its'],d['ids']); hi_i=min(d['ite'],d['ide']-1)
    lo_j=max(d['jts'],d['jds']); hi_j=min(d['jte'],d['jde']-1)
    lo_k=d['kts']; hi_k=d['kte']
    if hi_i < lo_i or hi_j < lo_j or hi_k < lo_k:
        raise RuntimeError('empty owner core')
    selected=[(i,j) for j in range(lo_j,hi_j+1) for i in range(lo_i,hi_i+1) if (i,j) in CELLS]
    def value(field,i,k,j):return field[j-d['jms'],k-d['kms'],i-d['ims']]
    for kind in ('selected','global'):
        if kind == 'global' and step != 1:
            continue
        stage_id = (6 if stage == 'entry' else 7) if kind == 'selected' else (1 if stage == 'entry' else 5)
        nfields=16 if kind == 'selected' else 14
        count=(len(selected) if kind == 'selected' else (hi_i-lo_i+1)*(hi_j-lo_j+1))*(hi_k-lo_k+1)
        path=OUT / f'{kind}_{stage}_rank{RANK}.bin'
        with path.open('ab') as stream:
            stream.write(b'CBSP0001')
            stream.write(struct.pack('>15i',stage_id,RANK,call,step,lo_i,hi_i,lo_j,hi_j,lo_k,hi_k,1,1,1,nfields,count))
            if kind == 'global':
                core=[f[lo_j-d['jms']:hi_j-d['jms']+1,lo_k-d['kms']:hi_k-d['kms']+1,lo_i-d['ims']:hi_i-d['ims']+1] for f in fields]
                tk=np.multiply(core[0],core[14],dtype=np.float32)
                z=np.stack(core[:13]+[tk],axis=-1)
                stream.write(z.astype('>f4').tobytes(order='C'))
            else:
                for j in range(lo_j,hi_j+1):
                    for k in range(lo_k,hi_k+1):
                        for i in range(lo_i,hi_i+1):
                            if (i,j) in CELLS:
                                row=[value(f,i,k,j) for f in fields]
                                tk=np.multiply(row[0],row[14],dtype=np.float32)
                                stream.write(struct.pack('>3i16f',i,j,k,*(row[:13]+[tk,row[13],row[14]])))


class AtReturn(gdb.FinishBreakpoint):
    def __init__(self,context,call):
        super().__init__(gdb.newest_frame(),internal=True)
        self.context=context
        self.call=call

    def stop(self):
        write_snapshot(self.context,'return',self.call)
        return False


class AtEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__(SYMBOL,internal=True)
        self.calls=0
        self.return_breakpoints=[]

    def stop(self):
        self.calls+=1
        context=read_context()
        if context['step'] != self.calls:
            raise RuntimeError('unexpected timestep/call ordering')
        write_snapshot(context,'entry',self.calls)
        self.return_breakpoints.append(AtReturn(context,self.calls))
        if self.calls == 4:
            self.enabled=False
        return False


gdb.execute('set pagination off')
gdb.execute('set confirm off')
gdb.execute('set debuginfod enabled off')
gdb.execute('set disable-randomization off')
probe=AtEntry()
