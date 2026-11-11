#!/usr/bin/env python3
"""Check retained native words and plot selected historical B1 handoff states."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(native):
    rows = [json.loads(line) for path in sorted((native/'capturedsmallrecords').glob('rank*.jsonl'))
            for line in path.read_text().splitlines()]
    file_values = json.loads((native/'file_values.json').read_text())
    records = []
    for original in file_values['values']:
        cell = original['cell']
        selected = [row for row in rows if row['cell'] == cell]
        assert len({row['rank'] for row in selected}) == 1
        entry = [row for row in selected if row['kind'] == 'kdm' and row['event'] == 'entry']
        returned = [row for row in selected if row['kind'] == 'kdm' and row['event'] == 'return']
        assert len(entry) == len(returned) == 1
        entry, returned = entry[0], returned[0]
        for row in selected:
            for value in row['fields'].values():
                assert struct.pack('<f', value['value']).hex() == value['hex_le']
        record = dict(zip(('i', 'j', 'k'), cell))
        record['owner_rank'] = entry['rank']
        for native_name, file_name in (('qi','QICE'), ('qs','QSNOW'), ('ni','QNICE')):
            final_rk = [row for row in selected if row['kind'] == 'update' and row['event'] == 'return'
                        and row['rk_step'] == 3 and row['current_base'] == entry['bases'][native_name]]
            assert len(final_rk) == 1
            assert final_rk[0]['fields']['current']['hex_le'] == entry['fields'][native_name]['hex_le']
            record['file_'+native_name] = original['fields'][file_name]['value']
            record['rk3_'+native_name] = final_rk[0]['fields']['current']['value']
            record['entry_'+native_name] = entry['fields'][native_name]['value']
            record['return_'+native_name] = returned['fields'][native_name]['value']
        den_file = np.float32(1)/np.float32(np.float32(original['fields']['AL']['value'])
                                             +np.float32(original['fields']['ALB']['value']))
        record['file_density_proxy'] = float(den_file)
        record['entry_den'] = entry['fields']['den']['value']
        record['entry_tk_offline'] = float(np.float32(np.float32(entry['fields']['th']['value'])
                                                   *np.float32(entry['fields']['pii']['value'])))
        record['file_to_entry_qi_difference'] = record['entry_qi']-record['file_qi']
        record['file_to_entry_qs_difference'] = record['entry_qs']-record['file_qs']
        record['entry_ni_volume'] = float(np.float32(record['entry_ni'])*np.float32(record['entry_den']))
        records.append(record)
    assert len(records) == 5
    return records


def draw(rows, output):
    figure, axes = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True)
    x = np.arange(len(rows))
    for column, title, axis in zip(('qi','qs','ni'),
                                  ('Ice mass (g kg$^{-1}$)', 'Snow mass (g kg$^{-1}$)',
                                   'Public ice number (kg$^{-1}$)'), axes):
        scale = 1000 if column != 'ni' else 1
        for offset, stage, label, color in ((-.13,'file','File input','#0072B2'),
                                            (0,'entry','First KDM6 entry','#E69F00'),
                                            (.13,'return','First KDM6 return','#009E73')):
            axis.scatter(x+offset, [r[stage+'_'+column]*scale for r in rows], label=label, color=color, s=45)
        axis.set_ylabel(title)
        axis.grid(axis='y', alpha=.3)
        axis.spines[['top','right']].set_visible(False)
        if column == 'ni':
            axis.ticklabel_format(axis='y', style='sci', scilimits=(0,0))
    axes[0].legend(loc='upper left', ncol=3, frameon=False)
    axes[0].set_title('Historical B1: file to first KDM6 boundary', loc='left', weight='bold')
    axes[-1].set_xticks(x, [f"({r['i']},{r['j']},{r['k']})" for r in rows])
    axes[-1].set_xlabel('Selected Fortran (i,j,k) cell')
    figure.text(.09,.015,'RK stage-3 return equals first KDM6 entry for QI/QS/NI at all five cells.\n'
                'Entry-to-return includes all KDM6 processes and vertical fluxes; it is not an ice-to-snow-only transfer.\n'
                'Unchanged historical input; no accepted new initialization or forecast-performance result.',fontsize=8.5)
    figure.tight_layout(rect=(0,.08,1,1))
    figure.savefig(output,dpi=180,metadata={'Software':'Matplotlib'})
    plt.close(figure)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    rows=summarize(args.native)
    table=args.output/'native_handoff.csv'
    with table.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0])
        writer.writeheader();writer.writerows(rows)
    image=args.output/'native_handoff.png'
    draw(rows,image)
    sources=[args.native/'file_values.json',*sorted((args.native/'capturedsmallrecords').glob('rank*.jsonl')),
             Path(__file__)]
    receipt={'status':'PASS','cells':5,'rk3_to_entry_exact_words':15,'sources_sha256':{str(p):sha(p) for p in sources},
             'csv_sha256':sha(table),'png_sha256':sha(image),
             'scope':'Selected unchanged historical B1 states only; no sole-process attribution, domain budget or new-policy validation.'}
    (args.output/'provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    main()
