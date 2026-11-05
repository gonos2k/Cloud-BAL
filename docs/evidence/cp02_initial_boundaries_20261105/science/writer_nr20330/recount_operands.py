#!/usr/bin/env python3
"""Make a paired per-arm RK operand table from closed actual writer evidence."""
import csv,hashlib,json,os,struct
from pathlib import Path
P=Path(__file__).resolve().parent
EXPECTED='81136f351c4804be078761cbfc57a715ccd58bf24ffd1537cb4c180a1b3d475b'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    source=P/'analysis.json'
    if sha(source)!=EXPECTED:raise ValueError('paired actual analysis changed')
    data=json.loads(source.read_text());rows=[]
    if data['status']!='PASS_ACTUAL_WRITER_ANALYSIS' or data['target']!='nr20330':raise ValueError('capture scope differs')
    names=('scalar_old','scalar_current','scalar_tendency','advection_tendency','msfty','c1','c2','mu_old','mu_new','mu_base','dt')
    for pair in data['paired_calls']:
        if pair['identity'][0]!='rk':continue
        for arm in ('B1','DM065'):
            item=pair[arm];field=item['entry_fields_raw'];ret=item['return_fields_raw'];ref=item['source_order_reference']
            row={'arm':arm,'candidate_timestep':item['candidate_timestep'],'rk_step':item['rk_step'],
                 'classification':pair['classification'][arm],'watch_events':item['watch_events']}
            for name in names:
                raw=field.get(name);row[name]=struct.unpack('<f',bytes.fromhex(raw))[0] if raw is not None else ''
                row[name+'_f32_le_hex']=raw or ''
            row['return_NR_or_candidate']=struct.unpack('<f',bytes.fromhex(ret['scalar_current']))[0]
            row['return_f32_le_hex']=ret['scalar_current'];row['source_order_f32_candidate']=ref['reference_nr'];row['observed_minus_reference']=ref['return_minus_reference']
            rows.append(row)
    if len(rows)!=48 or sum(r['classification']=='KDM_NR_pointer_bound' for r in rows)!=24:raise ValueError('candidate inventory differs')
    out=P/'paired_rk_operands.csv';receipt=P/'operand_table_receipt.json'
    if os.path.lexists(out) or os.path.lexists(receipt):raise FileExistsError('preserve existing output')
    with out.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    record={'status':'PASS','analysis_sha256':EXPECTED,'script_sha256':sha(Path(__file__)),'csv_sha256':sha(out),'rows':len(rows),
            'semantics':'First four calls, per-arm candidate RK operands. Only same-step KDM NR-pointer-matched rows are QNR-bound; other index-6 namespace remains unclassified. scalar_old is absent at RK1 entry. Source-order float32 candidate and signed residual are not a compiler-instruction proof. Watch PCs are post-store; no event does not prove no write.'}
    with receipt.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print('PASS',sha(receipt))

if __name__=='__main__':main()
