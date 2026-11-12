#!/usr/bin/env python3
"""Whole-column wrapper water accounting for a captured first KDM6 call."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct

WATER=('qv','qc','qi','qr','qs','qg')
PHYSICS_SHA256='f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
SURFACE=('rain','rainncv','snow','snowncv','graupel','graupelncv')


def value(record,name):
    field=record['fields'][name]
    number=field['value']
    if type(number) not in (int,float) or not math.isfinite(number):
        raise ValueError(f'nonfinite {name}')
    try:
        word=struct.pack('<f',number).hex()
    except (OverflowError,struct.error) as exc:
        raise ValueError(f'invalid REAL32 {name}') from exc
    decoded=struct.unpack('<f',bytes.fromhex(field['hex_le']))[0]
    if word!=field['hex_le'] or decoded!=number:
        raise ValueError(f'REAL32 word mismatch: {name}')
    return number


def read_pairs(path):
    pairs=collections.defaultdict(dict)
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt') as stream:
        for line in stream:
            record=json.loads(line)
            if (record['kind']!='kdm' or record['event'] not in ('entry','return')
                    or type(record['step']) is not int or record['step']!=1):
                raise ValueError('only first wrapper entry/return records are supported')
            cell=tuple(record['cell'])
            if len(cell)!=3 or any(type(x) is not int for x in cell):
                raise ValueError('invalid cell index')
            if record['event'] in pairs[cell]:
                raise ValueError(f'duplicate {cell} {record["event"]}')
            for name in (*WATER,*SURFACE,'den','delz','denr'):
                value(record,name)
            pairs[cell][record['event']]=record
    if not pairs:
        raise ValueError('empty capture')
    return pairs


def column_ledgers(pairs,row_j):
    reference=next(iter(pairs.values())).get('entry')
    if reference is None:
        raise ValueError('missing entry')
    bounds=reference['bounds']
    if any(type(bounds.get(name)) is not int for name in
           ('its','ite','ide','jts','jte','jde','kts','kte')):
        raise ValueError('invalid bounds')
    if not bounds['jts']<=row_j<=min(bounds['jte'],bounds['jde']-1):
        raise ValueError('requested row outside bounds')
    expected={(i,row_j,k) for i in range(bounds['its'],min(bounds['ite'],bounds['ide']-1)+1)
              for k in range(bounds['kts'],bounds['kte']+1)}
    if not expected or set(pairs)!=expected:
        raise ValueError('capture does not cover the complete requested row')
    columns=collections.defaultdict(list)
    for cell,phases in pairs.items():
        if set(phases)!= {'entry','return'}:
            raise ValueError(f'incomplete cell {cell}')
        a,b=phases['entry'],phases['return']
        if (a['bounds']!=bounds or b['bounds']!=bounds
                or a['rank']!=reference['rank'] or b['rank']!=reference['rank']
                or a['options']!=reference['options'] or b['options']!=reference['options']):
            raise ValueError(f'changed bounds or ownership {cell}')
        for name in ('den','delz','denr'):
            if a['fields'][name]['hex_le']!=b['fields'][name]['hex_le']:
                raise ValueError(f'changed geometry {cell}: {name}')
        den,dz=(value(a,name) for name in ('den','delz'))
        if den<=0 or dz<=0 or value(a,'denr')<=0:
            raise ValueError(f'nonpositive geometry {cell}')
        columns[cell[:2]].append((cell[2],a,b,den*dz))
    result=[]
    for (i,j),levels in sorted(columns.items()):
        levels.sort(key=lambda row:row[0])
        bounds=levels[0][1]['bounds']
        if [r[0] for r in levels]!=list(range(bounds['kts'],bounds['kte']+1)):
            raise ValueError(f'incomplete column {(i,j)}')
        if any(row[1]['bounds']!=bounds for row in levels):
            raise ValueError(f'inconsistent column bounds {(i,j)}')
        reference=levels[0][2]
        for _,a,b,_ in levels:
            if any(b['fields'][name]['hex_le']!=reference['fields'][name]['hex_le'] for name in SURFACE):
                raise ValueError(f'inconsistent surface values {(i,j)}')
            if any(a['fields'][name]['hex_le']!=levels[0][1]['fields'][name]['hex_le'] for name in SURFACE):
                raise ValueError(f'inconsistent entry surface {(i,j)}')
            if value(a,'denr')!=value(levels[0][1],'denr'):
                raise ValueError(f'inconsistent water density {(i,j)}')
        before={q:math.fsum(w*value(a,q) for _,a,_,w in levels) for q in WATER}
        after={q:math.fsum(w*value(b,q) for _,_,b,w in levels) for q in WATER}
        changes={q:math.fsum(w*(value(b,q)-value(a,q)) for _,a,b,w in levels) for q in WATER}
        # RAINNCV is call-total precipitation, reset internally. Snow/graupel
        # diagnostics are subsets and must not be added to the total.
        rain=value(reference,'rainncv')
        if rain<0:raise ValueError('negative surface precipitation')
        export=rain*value(levels[0][1],'denr')/1000
        clipped=math.fsum(w*max(-value(a,q),0) for _,a,_,w in levels for q in WATER if q!='qv')
        result.append({'i':i,'j':j,'levels':len(levels),'before_kg_m2':before,'after_kg_m2':after,
                       'change_kg_m2':changes,'surface_total_kg_m2':export,
                       'snow_subset_mm':value(reference,'snowncv'),
                       'graupel_subset_mm':value(reference,'graupelncv'),
                       'entry_clip_kg_m2':clipped,
                       'residual_without_entry_clip_kg_m2':math.fsum(changes.values())+export-clipped,
                       'raw_column_residual_kg_m2':math.fsum(changes.values())+export})
    return result


def validate_identity(capture,native_receipt,source):
    digest=hashlib.sha256(capture.read_bytes()).hexdigest()
    receipt=json.loads(native_receipt.read_text())
    if (receipt['status']!='PASS' or receipt['capture_sha256']!=digest
            or receipt['source_sha256']!=PHYSICS_SHA256
            or hashlib.sha256(source.read_bytes()).hexdigest()!=PHYSICS_SHA256):
        raise ValueError('capture and target physics identity mismatch')
    return digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--row-j',type=int,required=True)
    parser.add_argument('--native-receipt',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    digest=validate_identity(args.capture,args.native_receipt,args.source)
    ledgers=column_ledgers(read_pairs(args.capture),args.row_j)
    args.output.mkdir(parents=True,exist_ok=False)
    summary={'capture_sha256':digest,'physics_source_sha256':PHYSICS_SHA256,
             'native_receipt_sha256':hashlib.sha256(args.native_receipt.read_bytes()).hexdigest(),
             'column_count':len(ledgers),'rows':ledgers,
             'scope':'Native wrapper storage plus total surface export. Raw residual is not attributed to a process; no whole-domain water or energy claim.'}
    (args.output/'column_ledger.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (args.output/'column_ledger.csv').open('w',newline='') as stream:
        fields=['i','j','levels',*[q+'_change_kg_m2' for q in WATER],
                'surface_total_kg_m2','snow_subset_mm','graupel_subset_mm','entry_clip_kg_m2',
                'residual_without_entry_clip_kg_m2','raw_column_residual_kg_m2']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in ledgers:
            flat={k:row[k] for k in fields if k in row}
            flat.update({q+'_change_kg_m2':row['change_kg_m2'][q] for q in WATER});writer.writerow(flat)
    print(json.dumps({'column_count':len(ledgers),'maximum_abs_raw_residual_kg_m2':max(abs(r['raw_column_residual_kg_m2']) for r in ledgers)}))


if __name__=='__main__':
    main()
