"""Capture one target lane through the newly linked calc_p_rho_phi numerator."""
import hashlib
import importlib.util
import json
import os
import struct
from pathlib import Path

import gdb

TARGET = (144, 142, 4)
RANK = int(os.environ['PMI_RANK'])
OWNER = 5
EXPECTED_EXE = os.environ['GROUPED_EXE_SHA256']
SYMBOL_BASE = int(os.environ['GROUPED_SYMBOL_BASE'], 16)
PC = {name: int(value, 16) for name, value in json.loads(os.environ['GROUPED_PC_JSON']).items()}
OPCODES = {name: bytes.fromhex(value) for name, value in json.loads(os.environ['GROUPED_OPCODE_JSON']).items()}
INDEX_REGISTER = os.environ['GROUPED_INDEX_REGISTER']
OPERAND_BASES = os.environ['GROUPED_OPERAND_BASES'].split(',')
OPERATION_ORDER = json.loads(os.environ['GROUPED_OPERATION_ORDER'])
OUT = Path(os.environ['GROUPED_OUTPUT'])
VARIANT = os.environ['GROUPED_VARIANT']
ARM = os.environ['GROUPED_ARM']
event_module_path = Path(os.environ['GROUPED_EVENT_MODULE'])
event_spec = importlib.util.spec_from_file_location('grouped_operation_events', event_module_path)
event_module = importlib.util.module_from_spec(event_spec)
event_spec.loader.exec_module(event_module)

with Path(gdb.current_progspace().filename).open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != EXPECTED_EXE:
        raise RuntimeError('unexpected executable hash')

if RANK != OWNER:
    raise RuntimeError('GDB started on wrong rank')

events_path = OUT / f'operation_rank{RANK}.jsonl'
events = events_path.open('x', buffering=1)
sequence = 0
call_ordinal = 0
args = None
bounds = None
target_addresses = None
capture = None
captured = False
steps = []


def emit(event, **fields):
    global sequence
    sequence += 1
    record = {'sequence': sequence, 'event': event, 'arm': ARM,
              'variant': VARIANT, 'rank': RANK,
              'target': TARGET, 'phi_call_ordinal': call_ordinal,
              **fields}
    events.write(event_module.encode_event(record) + '\n')


def read(address, size):
    if not address:
        raise RuntimeError('null memory address')
    return bytes(gdb.selected_inferior().read_memory(address, size))


def word(address):
    return read(address, 4).hex()


def qword(address):
    return struct.unpack('<Q', read(address, 8))[0]


def integer(address):
    return struct.unpack('<i', read(address, 4))[0]


def pointers(count):
    frame = gdb.selected_frame()
    names = ('rdi', 'rsi', 'rdx', 'rcx', 'r8', 'r9')
    values = [int(frame.read_register(name)) for name in names[:count]]
    if count > 6:
        stack = int(frame.read_register('rsp'))
        values.extend(struct.unpack('<' + str(count - 6) + 'Q', read(stack + 8, 8 * (count - 6))))
    return values


def shape(a, start):
    names = ('ids', 'ide', 'jds', 'jde', 'kds', 'kde', 'ims', 'ime', 'jms', 'jme',
             'kms', 'kme', 'its', 'ite', 'jts', 'jte', 'kts', 'kte')
    result = dict(zip(names, (integer(a[i]) for i in range(start, start + 18))))
    if not (result['ims'] <= result['its'] <= result['ite'] <= result['ime'] and
            result['jms'] <= result['jts'] <= result['jte'] <= result['jme'] and
            result['kms'] <= result['kts'] <= result['kte'] <= result['kme']):
        raise RuntimeError('invalid array bounds')
    return result


def owns(d):
    i, j, k = TARGET
    return (d['its'] <= i <= min(d['ite'], d['ide'] - 1) and
            d['jts'] <= j <= min(d['jte'], d['jde'] - 1) and
            d['kts'] <= k <= min(d['kte'], d['kde'] - 1))


def offset(d, k):
    i, j, _ = TARGET
    ni = d['ime'] - d['ims'] + 1
    nk = d['kme'] - d['kms'] + 1
    return 4 * ((j - d['jms']) * nk * ni + (k - d['kms']) * ni + (i - d['ims']))


def reg(name):
    return int(gdb.selected_frame().read_register(name))


def rawreg(name):
    return bytes(gdb.selected_frame().read_register(name).bytes).hex()


def vector_starts():
    rbx, index = reg('rbx'), reg(INDEX_REGISTER)
    bases = [reg(token) if token.startswith('r') else qword(rbx + int(token, 16))
             for token in OPERAND_BASES]
    return [base + 4 * index for base in bases]


class TargetPhi(gdb.Breakpoint):
    def __init__(self):
        super().__init__(f'*0x{SYMBOL_BASE:x}', internal=True)

    def stop(self):
        global args, bounds, target_addresses, call_ordinal
        args, bounds, target_addresses = None, None, None
        a = pointers(46)
        d = shape(a, 28)
        if not owns(d):
            return False
        call_ordinal += 1
        hypso, use_theta, nh = integer(a[2]), integer(a[27]), integer(a[26])
        if (hypso != 2 or use_theta != 1 or nh & 1 != 1 or TARGET[2] + 1 > d['kme']):
            return False
        args, bounds = a, d
        target_addresses = {
            'ph': a[13] + offset(d, TARGET[2]),
            'ph_next': a[13] + offset(d, TARGET[2] + 1),
            'phb': a[14] + offset(d, TARGET[2]),
            'phb_next': a[14] + offset(d, TARGET[2] + 1),
            'al': a[3] + offset(d, TARGET[2]),
            'alb': a[4] + offset(d, TARGET[2]),
        }
        inputs = {name: word(address) for name, address in target_addresses.items()}
        emit('target_phi_entry', function_entry_pc=hex(reg('pc')), hypsometric_opt=hypso,
             use_theta_m=use_theta, non_hydrostatic=nh, bounds=d,
             addresses={name: hex(value) for name, value in target_addresses.items()},
             input_words=inputs)
        return False


class VectorEntry(gdb.Breakpoint):
    def __init__(self):
        super().__init__(f'*0x{PC["vector_entry"]:x}', internal=True)
        self.skipped = 0

    def stop(self):
        global capture, captured
        if captured or args is None or target_addresses is None:
            return False
        starts = vector_starts()
        operand_addresses = {target_addresses[name] for name in ('ph', 'ph_next', 'phb', 'phb_next')}
        lane_candidates = []
        for slot, start in enumerate(starts):
            for lane in range(4):
                address = start + 4 * lane
                if address in operand_addresses:
                    lane_candidates.append((slot, lane, address))
        if len(lane_candidates) < 4:
            self.skipped += 1
            if self.skipped > 25000:
                raise RuntimeError('bounded vector scan did not reach target cell')
            return False
        by_name = {name: starts.index(next(start for start in starts if address in range(start, start + 16, 4)))
                   for name, address in target_addresses.items() if name in ('ph', 'ph_next', 'phb', 'phb_next')}
        lanes = {name: (target_addresses[name] - starts[by_name[name]]) // 4
                 for name in ('ph', 'ph_next', 'phb', 'phb_next')}
        if len(set(by_name.values())) != 4 or len(set(lanes.values())) != 1:
            raise RuntimeError('four input lanes do not align')
        lane = lanes['ph']
        if any(starts[by_name[name]] + 4 * lane != target_addresses[name]
               for name in ('ph', 'ph_next', 'phb', 'phb_next')):
            raise RuntimeError('target operand effective addresses differ')
        regs = {name: rawreg(name) for name in ('xmm0', 'xmm1', 'xmm2', 'xmm3', 'xmm4')}
        capture = {'lane': lane, 'vector_starts': [hex(x) for x in starts],
                   'operand_slot_mapping': by_name, 'input_words': {name: word(target_addresses[name])
                                                                      for name in ('ph', 'ph_next', 'phb', 'phb_next')},
                   'alb_word': word(target_addresses['alb']),
                   'al_address': hex(target_addresses['al']),
                   'vector_registers_at_entry': regs,
                   'entry_pc': hex(reg('pc')), 'index_element_offset': reg(INDEX_REGISTER),
                   'r12_store_base': hex(reg('r12')), 'r15_store_base': hex(reg('r15')),
                   'skipped_vector_entries': self.skipped}
        emit('target_vector_entry', **capture)
        self.enabled = False
        for step in steps:
            step.enabled = True
        return False


class OperationStep(gdb.Breakpoint):
    def __init__(self, name):
        super().__init__(f'*0x{PC[name]:x}', internal=True)
        self.name = name
        self.enabled = False

    def stop(self):
        global captured
        if capture is None or reg('pc') != PC[self.name]:
            raise RuntimeError('unexpected operation breakpoint')
        event = {'instruction': self.name, 'pc': hex(reg('pc')),
                 'instruction_bytes': read(reg('pc'), len(OPCODES[self.name])).hex(),
                 'lane': capture['lane'], 'xmm0': rawreg('xmm0'), 'xmm1': rawreg('xmm1'),
                 'xmm2': rawreg('xmm2'), 'xmm3': rawreg('xmm3'), 'xmm4': rawreg('xmm4'),
                 'index_value': reg(INDEX_REGISTER), 'r12': hex(reg('r12')), 'r15': hex(reg('r15'))}
        if read(reg('pc'), len(OPCODES[self.name])) != OPCODES[self.name]:
            raise RuntimeError('instruction bytes differ from frozen disassembly')
        if self.name == 'store_before':
            vector = reg('r12') + 4 * reg(INDEX_REGISTER)
            address = vector + 4 * capture['lane']
            if address != int(capture['al_address'], 16):
                raise RuntimeError('AL store vector does not address target cell')
            event['al_store_target_address'] = hex(address)
            event['al_candidate_vector'] = rawreg('xmm1')
            event['al_candidate_word'] = event_module.vector_lane_word(event['al_candidate_vector'], capture['lane'])
        elif self.name == 'store_after':
            address = reg('r12') + 4 * reg(INDEX_REGISTER) + 4 * capture['lane']
            if address != int(capture['al_address'], 16):
                raise RuntimeError('post-store AL address differs')
            event['al_store_target_address'] = hex(address)
            event['stored_al_word'] = word(address)
            captured = True
        emit('instruction', **event)
        self.enabled = False
        return False


gdb.execute('set pagination off')
gdb.execute('set confirm off')
gdb.execute('set debuginfod enabled off')
gdb.execute('set disable-randomization off')
gdb.execute('set startup-with-shell off')
gdb.execute('set language c')
TargetPhi()
VectorEntry()
steps = [OperationStep(name) for name in OPERATION_ORDER]

