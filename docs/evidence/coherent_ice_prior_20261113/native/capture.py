"""Read-only GDB capture of KDM wrapper return on each MPI rank."""
import gdb
import hashlib
import json
import os
import struct
from pathlib import Path

EXPECTED_EXE = '3a286f6691fa94c2dccf55b14e4cbf609b8c9540c2caf83556969932ca9854ea'
FIELDS = (('QI', 5), ('QS', 6), ('NI', 10), ('DEN', 14), ('TH', 1),
          ('PII', 15), ('P', 16), ('QV', 2), ('DELZ', 17))
BOUNDS = ('ids', 'ide', 'jds', 'jde', 'kds', 'kde', 'ims', 'ime',
          'jms', 'jme', 'kms', 'kme', 'its', 'ite', 'jts', 'jte', 'kts', 'kte')
rank = int(os.environ['PMI_RANK'])
target = int(os.environ['TARGET_STEP'])
with open(gdb.current_progspace().filename, 'rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != EXPECTED_EXE:
        raise RuntimeError('incorrect executable')


def memory(address, size):
    return bytes(gdb.selected_inferior().read_memory(address, size))


def integer(address):
    return struct.unpack('<i', memory(address, 4))[0]


def arguments(count):
    frame = gdb.selected_frame()
    registers = [int(frame.read_register(name)) for name in ('rdi', 'rsi', 'rdx', 'rcx', 'r8', 'r9')]
    stack = int(frame.read_register('rsp'))
    return registers + list(struct.unpack('<' + str(count - 6) + 'Q', memory(stack + 8, 8 * (count - 6))))


def interval(bounds, axis):
    return (max(bounds[axis + 'ts'], bounds[axis + 'ds']),
            min(bounds[axis + 'te'], bounds[axis + 'de'] - 1))


class ReturnCapture(gdb.FinishBreakpoint):
    def __init__(self, args, bounds, owned):
        super().__init__(gdb.newest_frame(), internal=True)
        self.args = args
        self.bounds = bounds
        self.owned = owned

    def stop(self):
        d = self.bounds
        (i0, i1), (j0, j1), (k0, k1) = self.owned
        nx = d['ime'] - d['ims'] + 1
        nz = d['kme'] - d['kms'] + 1
        count = (i1 - i0 + 1) * (j1 - j0 + 1) * (k1 - k0 + 1)
        output = Path('..') / ('kdm_return_rank%d.bin' % rank)
        info = []
        with output.open('xb') as stream:
            for name, number in FIELDS:
                start = stream.tell()
                digest = hashlib.sha256()
                for j in range(j0, j1 + 1):
                    for k in range(k0, k1 + 1):
                        offset = 4 * ((j - d['jms']) * nz * nx + (k - d['kms']) * nx + i0 - d['ims'])
                        row = memory(self.args[number - 1] + offset, 4 * (i1 - i0 + 1))
                        stream.write(row)
                        digest.update(row)
                if stream.tell() - start != 4 * count:
                    raise RuntimeError('field length mismatch')
                info.append({'name': name, 'argument_1based': number,
                             'base': hex(self.args[number - 1]), 'offset_bytes': start,
                             'bytes': 4 * count, 'sha256': digest.hexdigest()})
        with output.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        metadata = {'rank': rank, 'target_step': target, 'event': 'kdm_wrapper_return',
                    'full_bounds_fortran_1based': d,
                    'processed_domain_intersection_fortran_1based': {'i': [i0, i1], 'j': [j0, j1], 'k': [k0, k1]},
                    'field_order': 'field-major; each field ordered j,k,i with i contiguous',
                    'dtype': 'little-endian IEEE-754 float32', 'cell_count': count,
                    'fields': info, 'binary_file': output.name, 'binary_sha256': digest}
        (Path('..') / ('kdm_return_rank%d.json' % rank)).write_text(json.dumps(metadata, indent=2) + '\n')
        return False


class Entry(gdb.Breakpoint):
    def stop(self):
        args = arguments(77)
        if integer(args[52]) != target:
            return False
        d = dict(zip(BOUNDS, [integer(args[i - 1]) for i in range(60, 78)]))
        owned = tuple(interval(d, axis) for axis in ('i', 'j', 'k'))
        for axis, (lo, hi) in zip(('i', 'j', 'k'), owned):
            if lo > hi or lo < d[axis + 'ms'] or hi > d[axis + 'me']:
                raise RuntimeError('invalid domain/owned/memory intersection')
        self.enabled = False
        keepers.append(ReturnCapture(args, d, owned))
        return False


gdb.execute('set pagination off')
gdb.execute('set confirm off')
gdb.execute('set debuginfod enabled off')
gdb.execute('set disable-randomization off')
gdb.execute('set startup-with-shell off')
gdb.execute('set language c')
keepers = [Entry('*0x2283ac0', internal=True)]
