"""Strict streaming decoder for versioned CP05 process frames."""
import gzip
import struct
import numpy as np


def exact(stream, n):
    data = stream.read(n)
    if len(data) != n: raise ValueError('truncated native frame')
    return data


def frames(path, counts):
    with gzip.open(path, 'rb') as stream:
        while magic := stream.read(8):
            if magic != b'C4FR0001': raise ValueError('invalid native frame magic')
            header = struct.unpack('>8i', exact(stream,32))
            constants = np.frombuffer(exact(stream,40),dtype='>f4')
            if not np.isfinite(constants).all(): raise ValueError('nonfinite frame constants')
            records=[]
            while True:
                phase = struct.unpack('>i',exact(stream,4))[0]
                if phase == -1: break
                if phase not in counts: raise ValueError(f'unknown phase {phase}')
                i,k,loop,loops,substep,mstep,n = struct.unpack('>7i',exact(stream,28))
                if n != counts[phase]: raise ValueError(f'wrong field count for phase {phase}: {n}')
                dtype = '>f8' if phase in (18,22) else '>f4'
                values = np.frombuffer(exact(stream,n*(8 if phase in (18,22) else 4)),dtype=dtype).copy()
                if not np.isfinite(values).all(): raise ValueError(f'nonfinite payload at phase {phase}')
                records.append((phase,i,k,loop,loops,substep,mstep,values))
            yield header, constants, records
