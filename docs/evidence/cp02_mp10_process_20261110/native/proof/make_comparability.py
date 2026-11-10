#!/usr/bin/env python3
"""Bind byte-identical forecasts and complete raw-to-packed native lineage."""
import hashlib,json
from pathlib import Path

NATIVE=Path(__file__).resolve().parents[1];BUNDLE=NATIVE.parent;ROOT=NATIVE.parents[3];RUNTIME=ROOT.parent/'runtime/forecasts'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(p.read_text())
def main():
    source=NATIVE/'source/source_receipt.json';schema=NATIVE/'schema/schema.json';selector=BUNDLE/'cohorts/native_columns.csv';review=BUNDLE/'review/compact_v2_go.json'
    sr=load(source);rv=load(review)
    if rv['status']!='GO_FOR_COMPACTION' or sr['selector_sha256']!=sha(selector):raise ValueError('source/review/selector mismatch')
    for name,expected in rv['sha256'].items():
        if sha(ROOT/name)!=expected:raise ValueError('review binding changed: '+name)
    result={'schema':'cp02_mp10_process_comparability_v1','status':'PASS','source_receipt_sha256':sha(source),'schema_sha256':sha(schema),'selector_sha256':sha(selector),'postrun_review_sha256':sha(review),'reviewed_script_sha256':rv['sha256'],'arms':{}}
    pins_path=NATIVE/'runs/reference_pins.json';pins=load(pins_path)
    for arm in ('CONTROL','MP10'):
        case=RUNTIME/arm;compact=NATIVE/'compact'/arm;packed=NATIVE/'packed'/arm
        cap=compact/'capture_receipt.json';recount=compact/'raw_recount_receipt.json';pack=packed/'packing_receipt.json';reloc=compact/'relocation_receipt.json';hist=case/'history_comparison.json';run=case/'run_receipt.json'
        c,r,p,l,h,u=map(load,(cap,recount,pack,reloc,hist,run))
        surface=compact/'surface_audit.json'; surface_audit=load(surface)
        if surface_audit['status']!='PASS' or surface_audit['capture_receipt_sha256']!=sha(cap) or surface_audit['raw_recount_sha256']!=sha(recount):raise ValueError('surface arithmetic audit not bound')
        if any(x['status'] not in ('PASS','COMPLETE') for x in (c,r,p,l,h,u)):raise ValueError('nonpassing receipt')
        if c['arm']!=arm or r['arm']!=arm or p['arm']!=arm or h['arm']!=arm:raise ValueError('arm mismatch')
        if c['source_receipt_sha256']!=sha(source) or r['capture_receipt_sha256']!=sha(cap) or p['capture_receipt_sha256']!=sha(cap) or p['raw_recount_sha256']!=sha(recount):raise ValueError('capture/recount/packing chain mismatch')
        if l['packing_receipt_sha256']!=sha(pack) or l['capture_receipt_sha256']!=sha(cap) or l['raw_recount_sha256']!=sha(recount):raise ValueError('relocation chain mismatch')
        src=NATIVE/'source'/f'{arm}.f90'
        if sha(src)!=sr['arms'][arm]['source_sha256']:raise ValueError('instrumented source changed')
        cin={x['name']:x for x in c['outputs']};pout={x['name']:x for x in p['outputs']}
        if not cin or len(cin)!=len(c['outputs']) or set(cin)!=set(pout):raise ValueError('empty, duplicate or mismatched packed inventory')
        for name,item in pout.items():
            if item['source_sha256']!=cin[name]['sha256'] or sha(packed/name)!=item['sha256'] or (packed/name).stat().st_size!=item['size_bytes']:raise ValueError('packed artifact mismatch: '+name)
        if h['run_receipt_sha256']!=sha(run) or h['reference_pins_sha256']!=sha(pins_path):raise ValueError('history receipt lineage mismatch')
        expected=[f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12,19)]
        if set(h['comparisons'])!=set(expected):raise ValueError('seven histories required')
        histories=[]
        for name in expected:
            row=h['comparisons'][name]
            if not row['exact'] or row['actual_sha256']!=row['reference_sha256'] or row['reference_sha256']!=pins[arm]['history_sha256'][name] or sha(case/name)!=row['actual_sha256']:raise ValueError('history bytes differ')
            histories.append({'name':name,'actual_sha256':row['actual_sha256'],'reference_sha256':row['reference_sha256'],'byte_equal':True})
        result['arms'][arm]={'source_sha256':sha(src),'capture_receipt_sha256':sha(cap),'raw_recount_sha256':sha(recount),'packing_receipt_sha256':sha(pack),'surface_audit_sha256':sha(surface),'relocation_receipt_sha256':sha(reloc),'history_comparison_sha256':sha(hist),'run_receipt_sha256':sha(run),'packed_artifacts':len(pout),'history7byte_equal':histories}
    (NATIVE/'proof/comparability.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
