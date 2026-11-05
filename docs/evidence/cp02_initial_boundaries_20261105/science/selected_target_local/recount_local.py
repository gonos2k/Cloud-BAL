#!/usr/bin/env python3
"""Report selected target cell/level states and exact TK product algebra."""
import csv,hashlib,json,os
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parents[2]
BASE='803c398b178db89271976b941a74db7e3a9010ffe16091c94749f5d1feb5ab1c'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    path=P/'baseline/results/early_selected.npz'
    if sha(path)!=BASE:raise ValueError('baseline differs')
    rows=[]
    with np.load(path,allow_pickle=False) as z:
        cells=z['native_cells_i_j_1based'];fields=list(z['fields'])
        for point,i,j,k in [('NFA12',144,142,4),('NFA05',140,120,38)]:
            where=np.flatnonzero((cells[:,0]==i)&(cells[:,1]==j))
            if where.size!=1:raise ValueError('target coordinate not unique')
            ci=int(where[0])
            for step in range(1,5):
                a=z['B1_entry'][step-1,k-1,ci];b=z['DM065_entry'][step-1,k-1,ci];row={'point_id':point,'i_1based':i,'j_1based':j,'k_1based':k,'step':step}
                for name in ('QV','QC','NR','TH','TK','P','PII'):
                    n=fields.index(name);row[f'B1_{name}']=float(a[n]);row[f'DM065_{name}']=float(b[n]);row[f'delta_{name}']=float(np.float64(b[n])-np.float64(a[n]));row[f'{name}_bit_equal']=bool(a[n].view('u4')==b[n].view('u4'))
                # Reference path: PII_DM*(TH_DM-TH_B1) + TH_B1*(PII_DM-PII_B1).
                th_term=float(b[15])*(float(b[0])-float(a[0]));pii_term=float(a[0])*(float(b[15])-float(a[15]));actual=float(b[13])-float(a[13]);row['theta_term_K']=th_term;row['PII_term_K']=pii_term;row['f32_product_rounding_residual_K']=actual-(th_term+pii_term);rows.append(row)
    out=P/'science/selected_target_local/entry_cells.csv';receipt=P/'science/selected_target_local/receipt.json'
    if os.path.lexists(out) or os.path.lexists(receipt):raise FileExistsError('preserve result')
    with out.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    record={'status':'PASS','baseline_sha256':BASE,'source_sha256':sha(Path(__file__)),'csv_sha256':sha(out),'rows':len(rows),'limits':'Two explicitly selected native cells, not whole columns. TK is f32(TH*PII). Terms are algebraic and do not identify heating or cause.'}
    with receipt.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print('PASS',sha(receipt))

if __name__=='__main__':main()
