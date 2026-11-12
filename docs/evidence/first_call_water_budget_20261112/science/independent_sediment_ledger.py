#!/usr/bin/env python3
"""Independently check captured CONTROL sediment boundary transfers and storage."""
import collections, gzip, json, math, struct, sys

capture, trace = sys.argv[1:]
weights = {}
wrapper = {}
with gzip.open(capture, 'rt') as stream:
    for line in stream:
        r = json.loads(line)
        if r['cell'][0] in (192, 201):
            f = r['fields']; cell = tuple(r['cell'])
            wrapper[(r['event'], *cell)] = tuple(f[q]['value'] for q in ('qv','qc','qi','qr','qs','qg'))
            if r['event'] == 'entry': weights[cell] = f['den']['value'] * f['delz']['value']

def read(stream, n):
    value = stream.read(n)
    if len(value) != n: raise ValueError('truncated trace')
    return value

records = {}
with open(trace, 'rb') as stream:
    if read(stream, 8) != b'C4FR0001': raise ValueError('invalid frame')
    rank, call, step, j, its, ite, kts, kte = struct.unpack('>8i', read(stream, 32))
    read(stream, 40)
    if (rank, step, j, kts, kte) != (3, 1, 72, 1, 39): raise ValueError('unexpected frame')
    while True:
        phase = struct.unpack('>i', read(stream, 4))[0]
        if phase == -1: break
        i, k, loop, loops, substep, mstep, count = struct.unpack('>7i', read(stream, 28))
        expected_counts = {1:16, 2:16, 6:18, 8:16, 9:22, 10:22,
                           18:10, 20:10, 21:10, 22:4, 32:18, 33:18, 34:18}
        if phase in expected_counts and count != expected_counts[phase]:
            raise ValueError(f'phase {phase}: unexpected source payload size {count}')
        code = 'd' if phase in (18, 22) else 'f'
        values = struct.unpack('>' + str(count) + code, read(stream, count * (8 if code == 'd' else 4)))
        if not all(math.isfinite(value) for value in values): raise ValueError('nonfinite trace payload')
        key = (phase, i, k, substep)
        if key in records: raise ValueError(f'duplicate {key}')
        records[key] = (loop, loops, mstep, values)
    if stream.read(1): raise ValueError('unexpected trailing data')

rows = []
stages = []
telescopes = []
for i in (192, 201):
    for name, before_phase, after_phase, indices in (
        ('entry_clipping', 1, 2, (1, 4, 5, 6, 7, 8)),
        ('threshold_cleanup', 32, 33, (1, 6, 7, 8, 9, 10))):
        delta = []
        for k in range(kts, kte+1):
            before = records[(before_phase,i,k,0)][3]
            after = records[(after_phase,i,k,0)][3]
            delta.append(math.fsum(after[n]-before[n] for n in indices)*weights[i,j,k])
        stages.append({'i':i, 'j':j, 'stage':name, 'water_change_kg_m2':math.fsum(delta)})
    for name, prephase, postphase, facephase, state, face in (
        ('qr', 9, 10, 18, 5, 0), ('qs', 9, 10, 18, 6, 2),
        ('qg', 9, 10, 18, 7, 4), ('qi', 20, 21, 22, 3, 0)):
        subs = sorted({key[3] for key in records if key[0] == prephase and key[1] == i})
        if subs != list(range(1, len(subs)+1)) or not subs: raise ValueError('incomplete substeps')
        if len(subs) != 1: raise ValueError('telescope requires one captured substep')
        column_change, bottom, rounding = [], [], []
        for sub in subs:
            before, after, outgoing, incoming = [], [], [], []
            for k in range(kts, kte+1):
                a = records[(prephase,i,k,sub)]; b = records[(postphase,i,k,sub)]
                c = records[(facephase,i,k,sub)]
                if any(x[:3] != (1,1,len(subs)) for x in (a,b,c)): raise ValueError('invalid substep metadata')
                before.append(a[3][state]); after.append(b[3][state])
                outgoing.append(c[3][face]); incoming.append(c[3][face+1])
            if incoming[-1] != 0 or any(incoming[k] != outgoing[k+1] for k in range(len(incoming)-1)):
                raise ValueError('top or internal boundary mismatch')
            delta = math.fsum((after[k-1]-before[k-1])*weights[i,j,k] for k in range(kts,kte+1))
            column_change.append(delta); bottom.append(outgoing[0]); rounding.append(delta+outgoing[0])
        rows.append({'i':i,'j':j,'species':name,'substeps':len(subs),
                     'column_change_kg_m2':math.fsum(column_change),
                     'bottom_out_kg_m2':math.fsum(bottom),
                     'top_in_kg_m2':0.0,'transfer_rounding_residual_kg_m2':math.fsum(rounding)})
    # Full six-species snapshots at source phase boundaries. The ice phases
    # carry only QI; the source changes no other water fields in that loop.
    def snapshot(phase, indices, sub=0):
        return [tuple(records[(phase,i,k,sub)][3][n] for n in indices)
                for k in range(kts,kte+1)]
    entry = [wrapper[('entry',i,j,k)] for k in range(kts,kte+1)]
    returned = [wrapper[('return',i,j,k)] for k in range(kts,kte+1)]
    raw = snapshot(1,(1,4,5,6,7,8))
    clipped = snapshot(2,(1,4,5,6,7,8))
    rsg_pre = snapshot(9,(1,3,4,5,6,7),1)
    rsg_post = snapshot(10,(1,3,4,5,6,7),1)
    ice_pre_qi = snapshot(20,(3,),1)
    ice_post_qi = snapshot(21,(3,),1)
    if any(row[2] != ice_pre_qi[n][0] for n,row in enumerate(rsg_post)):
        raise ValueError('unobserved QI change before ice sedimentation')
    ice_post = [row[:2]+(ice_post_qi[n][0],)+row[3:] for n,row in enumerate(rsg_post)]
    pre_update = snapshot(6,(1,4,5,6,7,8))
    post_update = snapshot(8,(1,4,5,6,7,8))
    pre_zero = snapshot(32,(1,6,7,8,9,10))
    post_zero = snapshot(33,(1,6,7,8,9,10))
    end = snapshot(34,(1,6,7,8,9,10))
    sequence = [('wrapper_to_raw',entry,raw),('entry_clipping',raw,clipped),
                ('clipped_to_rsg',clipped,rsg_pre),('rsg_sedimentation',rsg_pre,rsg_post),
                ('ice_sedimentation',rsg_post,ice_post),('post_ice_to_pre_update',ice_post,pre_update),
                ('main_update',pre_update,post_update),('post_update_to_cleanup',post_update,pre_zero),
                ('threshold_cleanup',pre_zero,post_zero),('post_cleanup_psd',post_zero,end),
                ('core_end_to_wrapper_return',end,returned)]
    for label,before,after in sequence:
        changes = {q:math.fsum((after[n][m]-before[n][m])*weights[i,j,n+kts]
                               for n in range(kte-kts+1))
                   for m,q in enumerate(('qv','qc','qi','qr','qs','qg'))}
        telescopes.append({'i':i,'j':j,'stage':label,'species_change_kg_m2':changes,
                           'total_change_kg_m2':math.fsum(changes.values())})
print(json.dumps({'trace_frame':{'rank':rank,'call':call,'step':step,'j':j,'its':its,'ite':ite},'stages':stages,'rows':rows,'telescopes':telescopes},indent=2))
