"""Check captured source bytes, address chain and REAL32 arithmetic independently."""
import gzip
import hashlib
import json
import math
import struct
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent.parent

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def f(raw): return struct.unpack('<f', bytes.fromhex(raw))[0]
def raw(value): return struct.pack('<f', value).hex()
def rnd(value): return f(raw(value))

def main():
    rows = []
    inputs = {}
    for arm in ('OFF', 'HYDRO', 'LIQUID'):
        for rank, target in (('1', 'P05_00'), ('3', 'P01_00')):
            path, = (EVIDENCE / 'captures' / arm).glob('raw_*_rank' + rank + '_pid*.json.gz')
            inputs[str(path.relative_to(EVIDENCE))] = sha(path)
            record = json.loads(gzip.decompress(path.read_bytes()))
            events = record['source_events']
            lookup = {e['role']: e for e in events if e['role'] != 'watch_access'}
            arm_event = lookup['arm']; call, = (i for i in record['inner'] if i['watch_target'] == target)
            point, = (x for x in call['points'] if x['label'] == target)
            qrs = int(point['entry']['qrs']['address_hex'], 16)
            frame = bytes.fromhex(arm_event['frame_rbx_raw_hex'])
            qbase = struct.unpack_from('<Q', frame, 0x1f0)[0]
            base = struct.unpack_from('<Q', frame, 0x728)[0]
            assert qbase == int(call['argument_pointers_hex'][3], 16)
            offset = qrs-qbase
            bounds = call['candidate_bounds']
            assert offset % 4 == 0 and 0 <= offset//4 < (bounds['ite']-bounds['its']+1)*(bounds['kte']-bounds['kts']+1)
            address = base + offset
            assert address == int(arm_event['address_hex'], 16)
            ordered = [e['event_ordinal'] for e in events]
            assert ordered == sorted(ordered) and len(set(ordered)) == len(ordered)
            assert all(e['inner_call_id'] == call['event_id'] and call['event_ordinal'] < e['event_ordinal'] < call['return']['event_ordinal'] for e in events)
            before = lookup['writer_before_2a8']; after = lookup['writer_after_2a8']
            start = lookup['before_upstream_2cf']; op = start['operands']; regs = start['scalar_registers']
            a = f(op['array_0x120']['raw_hex']); b = f(op['array_0xb0']['raw_hex'])
            floor = f(regs['xmm9']['raw_hex']); scale = f(op['frame_0x140']['raw_hex'])
            assert all(map(math.isfinite, (a,b,floor,scale))) and scale == 20.0
            result = rnd(rnd(max(a, floor) - b) / scale)
            assert raw(result) == lookup['before_frame_store_2f6']['scalar_registers']['xmm0']['raw_hex']
            assert raw(result) == lookup['after_frame_store_2fb']['operands']['frame_0x18']['raw_hex']
            mn = lookup['before_min_29d']
            assert mn['operands']['frame_0x18']['raw_hex'] == lookup['after_frame_store_2fb']['operands']['frame_0x18']['raw_hex']
            x0 = f(mn['scalar_registers']['xmm0']['raw_hex']); x1 = f(mn['scalar_registers']['xmm1']['raw_hex'])
            assert mn['scalar_registers']['xmm1']['raw_hex'] == raw(rnd(result / f(mn['operands']['constant_34bbaf4']['raw_hex'])))
            assert before['scalar_registers']['xmm0']['raw_hex'] == (mn['scalar_registers']['xmm0']['raw_hex'] if x0 < x1 else mn['scalar_registers']['xmm1']['raw_hex'])
            assert after['source']['raw_hex'] == before['scalar_registers']['xmm0']['raw_hex']
            accesses = [e for e in events if e['role'] == 'watch_access']
            assert [e['pc_after_write_hex'] for e in accesses[:2]] == ['0x25ef2ae','0x25f4498']
            assert all(int(e['address_hex'],16) == address for e in accesses)
            assert accesses[0]['after']['raw_hex'] == accesses[1]['before']['raw_hex'] == accesses[1]['after']['raw_hex'] == after['source']['raw_hex']
            load, = (e for e in record['producer_events'] if e['role'] == 'before_load')
            loaded, = (e for e in record['producer_events'] if e['role'] == 'after_load')
            assert int(load['source']['address_hex'],16) == address and load['source']['raw_hex'] == after['source']['raw_hex']
            assert loaded['scalar_registers']['xmm6']['raw_hex'] == after['source']['raw_hex']
            assert after['event_ordinal'] < accesses[0]['event_ordinal'] < load['event_ordinal'] < loaded['event_ordinal'] < accesses[1]['event_ordinal']
            join, = (e for e in record['producer_events'] if e['role'] == 'branch_join')
            multiply = [e for e in record['producer_events'] if e['role'] == 'after_multiply']
            if multiply:
                assert len(accesses) == 3 and accesses[2]['pc_after_write_hex'] == '0x25f44c8'
                assert multiply[0]['event_ordinal'] < accesses[2]['event_ordinal'] < join['event_ordinal']
                assert accesses[2]['after']['raw_hex'] == multiply[0]['scalar_registers']['xmm6']['raw_hex'] == join['source']['raw_hex']
            else:
                assert len(accesses) == 2 and join['source']['raw_hex'] == after['source']['raw_hex']
            rows.append({'arm':arm, 'rank':rank, 'target':target, 'source_raw_hex':after['source']['raw_hex'], 'source_write_pc':'0x25ef2a8', 'source_load_pc':'0x25f4492', 'access_count':len(accesses)})
    assert len(rows) == 6
    out = {'status':'PASS', 'scope':'Six selected first-call cells; access watch begins after initialization; source-byte and arithmetic checks, not scientific validation', 'script_sha256':sha(Path(__file__)), 'raw_capture_sha256':inputs, 'rows':rows}
    (EVIDENCE / 'review/independent_source.json').write_text(json.dumps(out, indent=2, sort_keys=True)+'\n')
    print('PASS six independent source chains')

if __name__ == '__main__': main()
