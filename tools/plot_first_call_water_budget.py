#!/usr/bin/env python3
"""Plot captured whole-column storage and separately observed source stages."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def draw(wrapper,stages,output):
    rows=wrapper['rows']
    figure,axes=plt.subplots(2,1,figsize=(10.5,8))
    x=[row['i'] for row in rows]
    axes[0].plot(x,[r['raw_column_residual_kg_m2']*1e6 for r in rows],label='Storage + total surface export',color='#0072B2')
    axes[0].plot(x,[r['entry_clip_kg_m2']*1e6 for r in rows],label='Source entry clipping',color='#D55E00',linestyle='--')
    axes[0].plot(x,[r['residual_without_entry_clip_kg_m2']*1e6 for r in rows],label='Residual after subtracting clipping',color='#009E73')
    axes[0].set_ylabel('Water ledger ($10^{-6}$ kg m$^{-2}$)')
    axes[0].set_xlabel('Global Fortran i at j=72')
    axes[0].set_title('Matched CONTROL first call: 116 complete columns',loc='left',weight='bold')
    axes[0].legend(frameon=False,fontsize=8.5)
    target=next(row for row in rows if row['i']==192)
    species=('qv','qc','qi','qr','qs','qg');xp=np.arange(len(species))
    axes[1].bar(xp-.18,[target['before_kg_m2'][q] for q in species],.36,label='First wrapper entry',color='#0072B2')
    axes[1].bar(xp+.18,[target['after_kg_m2'][q] for q in species],.36,label='First wrapper return',color='#E69F00')
    axes[1].set_xticks(xp,['Vapor','Cloud','Ice','Rain','Snow','Graupel'])
    axes[1].set_ylabel('Column mass (kg m$^{-2}$)')
    axes[1].set_title('Column (192,72): species and vertical transport are coupled',loc='left')
    axes[1].legend(frameon=False)
    for axis in axes:
        axis.grid(axis='y',alpha=.25);axis.set_axisbelow(True);axis.spines[['top','right']].set_visible(False)
    figure.text(.09,.018,'Captured density and layer depth; RAINNCV is total export, snow/graupel are subsets.\n'
                'Subtracting entry clipping is a diagnostic ledger; it is not full-domain water/energy closure or forecast validation.',fontsize=8.5)
    figure.tight_layout(rect=(0,.07,1,1));figure.savefig(output/'column_water.png',dpi=180,metadata={'Software':'Matplotlib'});plt.close(figure)
    figure,axes=plt.subplots(2,1,figsize=(11,8),sharex=True)
    for axis,column in zip(axes,(192,201)):
        ledger=[r for r in stages['telescopes'] if r['i']==column]
        exports={r['species']:r['bottom_out_kg_m2']-r['top_in_kg_m2'] for r in stages['rows'] if r['i']==column}
        values=[]
        for row in ledger:
            total=row['total_change_kg_m2']
            if row['stage']=='rsg_sedimentation':total+=sum(exports[q] for q in ('qr','qs','qg'))
            if row['stage']=='ice_sedimentation':total+=exports['qi']
            values.append(total*1e6)
        axis.bar(np.arange(len(values)),values,color=['#D55E00' if r['stage'] in ('entry_clipping','threshold_cleanup') else '#0072B2' for r in ledger])
        axis.axhline(0,color='black',linewidth=.6)
        axis.set_ylabel('Stage ledger\n($10^{-6}$ kg m$^{-2}$)')
        axis.set_title(f'Column ({column},72)',loc='left')
        axis.grid(axis='y',alpha=.25);axis.set_axisbelow(True);axis.spines[['top','right']].set_visible(False)
    axes[-1].set_xticks(np.arange(len(ledger)),[r['stage'].replace('_','\n') for r in ledger],fontsize=7.5)
    figure.text(.09,.015,'Six-species stored changes; sediment stages include their measured bottom export (top inflow zero).\n'
                'Broad source intervals remain composite; bars are not causal contributions or a global budget.',fontsize=8.5)
    figure.tight_layout(rect=(0,.08,1,1));figure.savefig(output/'stage_ledger.png',dpi=180,metadata={'Software':'Matplotlib'});plt.close(figure)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wrapper',type=Path);parser.add_argument('stages',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    draw(json.loads(args.wrapper.read_text()),json.loads(args.stages.read_text()),args.output)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result={'source_sha256':{str(p):sha(p) for p in (args.wrapper,args.stages,Path(__file__))},
            'png_sha256':{p.name:sha(p) for p in args.output.glob('*.png')},
            'scope':'One CONTROL first call; 116 full wrapper columns and two phase-observed replay columns, not independent weather events.'}
    (args.output/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
