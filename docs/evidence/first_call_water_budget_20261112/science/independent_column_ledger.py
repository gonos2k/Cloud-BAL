#!/usr/bin/env python3
"""Independent first-call wrapper column ledger; surface components are subsets."""
import collections, gzip, json, math, struct, sys

species = ('qv', 'qc', 'qi', 'qr', 'qs', 'qg')
records = collections.defaultdict(dict)
opener = gzip.open if sys.argv[1].endswith('.gz') else open
with opener(sys.argv[1], 'rt') as stream:
    for line in stream:
        record = json.loads(line)
        cell, event = tuple(record['cell']), record['event']
        if event in records[cell]:
            raise ValueError(f'duplicate {cell} {event}')
        fields = record['fields']
        for name in (*species, 'den', 'delz', 'denr', 'rainncv', 'snowncv', 'graupelncv'):
            raw = struct.unpack('<f', bytes.fromhex(fields[name]['hex_le']))[0]
            if not math.isfinite(raw) or raw != fields[name]['value']:
                raise ValueError(f'invalid {cell} {event} {name}')
        records[cell][event] = fields

columns = collections.defaultdict(list)
for (i, j, k), phases in records.items():
    if set(phases) != {'entry', 'return'}:
        raise ValueError(f'incomplete cell {(i,j,k)}')
    a, b = phases['entry'], phases['return']
    val = lambda row, name: row[name]['value']
    if any(a[n]['hex_le'] != b[n]['hex_le'] for n in ('den', 'delz', 'denr')):
        raise ValueError(f'changed geometry {(i,j,k)}')
    weight = val(a, 'den') * val(a, 'delz')
    if weight <= 0: raise ValueError(f'bad geometry {(i,j,k)}')
    change = {q: weight*(val(b,q)-val(a,q)) for q in species}
    surface = tuple(val(b,n) for n in ('rainncv','snowncv','graupelncv'))
    columns[(i,j)].append((k, change, surface, val(a,'denr')))
rows=[]
for (i,j), levels in sorted(columns.items()):
    levels.sort()
    if [x[0] for x in levels] != list(range(1,40)):
        raise ValueError(f'incomplete column {(i,j)}')
    if len({x[2:] for x in levels}) != 1:
        raise ValueError(f'inconsistent surface {(i,j)}')
    rain, snow, graupel = levels[0][2]
    changes = {q: math.fsum(row[1][q] for row in levels) for q in species}
    ground = rain*levels[0][3]/1000
    rows.append({'i':i, 'j':j, 'change_kg_m2':changes, 'rain_total_kg_m2':ground,
                 'snow_subset_mm':snow, 'graupel_subset_mm':graupel,
                 'closure_residual_kg_m2': math.fsum(changes.values())+ground})
print(json.dumps({'column_count':len(rows), 'rows':rows}, indent=2))
