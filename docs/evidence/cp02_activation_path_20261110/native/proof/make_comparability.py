#!/usr/bin/env python3
"""Bind exact history, shared-column parity and raw-to-packed capture receipts."""
import hashlib,json
from pathlib import Path

NATIVE=Path(__file__).resolve().parents[1]
BUNDLE=NATIVE.parent
ROOT=NATIVE.parents[3]
RUNTIME=ROOT.parent/'runtime/forecasts'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def passed(path):
    value=json.loads(path.read_text())
    if value['status']!='PASS':raise ValueError(f'nonpassing evidence: {path}')
    return value

def main():
    schema=NATIVE/'schema/schema.json';source=NATIVE/'source/source_receipt.json';selector=BUNDLE/'cohorts/native_columns.csv';mapping=BUNDLE/'cohorts/mapping_receipt.json';points=BUNDLE/'cohorts/selected_points.csv';supplement=NATIVE/'schema/contract_supplement.json'
    if json.loads(mapping.read_text())['selector_sha256']!=sha(selector):raise ValueError('mapping selector differs')
    if json.loads(mapping.read_text())['selected_points_sha256']!=sha(points):raise ValueError('mapping points differ')
    if json.loads(source.read_text())['selector_sha256']!=sha(selector):raise ValueError('source selector differs')
    if json.loads(supplement.read_text())['schema_sha256']!=sha(schema):raise ValueError('schema supplement differs')
    arms={}
    for arm in ('CONTROL','MP10'):
        case=RUNTIME/arm;compact=NATIVE/'compact'/arm;packed=NATIVE/'packed'/arm
        history=case/'history_comparison.json';shared=case/'shared_comparison.json';capture=compact/'capture_receipt.json';recount=compact/'raw_recount_receipt.json';surface=compact/'surface_audit.json';packing=packed/'packing_receipt.json'
        h=passed(history);passed(shared); c=json.loads(capture.read_text()); r=passed(recount); a=passed(surface); p=passed(packing)
        if c['status']!='COMPLETE' or c['schema_sha256']!=sha(schema) or c['source_receipt_sha256']!=sha(source):raise ValueError('capture does not bind schema/source')
        if r['capture_receipt_sha256']!=sha(capture) or a['capture_receipt_sha256']!=sha(capture) or p['capture_receipt_sha256']!=sha(capture):raise ValueError('receipt capture binding differs')
        if a['raw_recount_sha256']!=sha(recount) or p['raw_recount_sha256']!=sha(recount):raise ValueError('receipt recount binding differs')
        history_rows=[]
        for name,item in sorted(h['comparisons'].items()):
            if not item['exact'] or item['actual_sha256']!=item['reference_sha256']:raise ValueError('history byte identity failed')
            history_rows.append({'name':name,**item})
        if len(history_rows)!=4:raise ValueError('four history files required')
        arms[arm]={'capture_receipt_sha256':sha(capture),'raw_recount_sha256':sha(recount),'packing_receipt_sha256':sha(packing),'surface_audit_sha256':sha(surface),'shared_comparison_sha256':sha(shared),'history_comparison_sha256':sha(history),'history4byte_equal':history_rows}
    result={'status':'PASS','schema':'cp02_activation_weak_comparability_v1','schema_sha256':sha(schema),'source_receipt_sha256':sha(source),'selector_sha256':sha(selector),'mapping_receipt_sha256':sha(mapping),'selected_points_sha256':sha(points),'supplement_sha256':sha(supplement),'arms':arms,'limitation':'Three points; diagnostic reproduction only; does not establish causal attribution or domain-wide scientific validation.'}
    (NATIVE/'proof/comparability.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
