#!/usr/bin/env python3
"""Plot the pinned analytical ice policy, not a native forecast result."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT/'docs/evidence/physical_moment_handoff_20261110/native/actual_real'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads((PRIOR/'policy.json').read_text())
    recount = json.loads((PRIOR/'ice_cap_recount.json').read_text())
    # The same nominal mass envelope used by the source-bound policy.
    mmax = policy['upper'][1]
    cap = policy['number_cap'][1]
    first = recount['failed_cell_qice_kg_per_kg']*recount['failed_cell_file_dry_density_kg_per_m3']
    peak = recount['ice_mean_mass_kg']*recount['peak_implied_internal_ni_m-3']
    args.output.mkdir(parents=True, exist_ok=True)
    x = np.linspace(0, .004, 401)
    with (args.output/'ice_feasibility_curve.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['ice_mass_concentration_kg_m3','minimum_number_m3','number_cap_m3','interval_empty'])
        writer.writerows((float(q),float(q/mmax),cap,bool(q/mmax>cap)) for q in x)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    fig, ax = plt.subplots(figsize=(8,4.7), constrained_layout=True)
    ax.plot(x*1000, x/mmax/1e6, label=r'Minimum number: $\rho q_i/m_{max}$', color='#2166ac')
    ax.axhline(cap/1e6, color='#b2182b', label='Policy number cap')
    limit = cap*mmax*1000
    ax.axvspan(limit, 4, color='#ef8a62', alpha=.2, label='Empty analytical interval')
    for name,q,yoffset in [('First prior rejection',first,.13),('File maximum',peak,.15)]:
        ax.scatter(q*1000,q/mmax/1e6,color='black',zorder=4)
        ax.annotate(name,(q*1000,q/mmax/1e6),xytext=(q*1000+.05,q/mmax/1e6+yoffset),fontsize=9)
    ax.set(xlabel='File-state ice mass concentration (g m$^{-3}$)',ylabel='Ice number concentration ($10^6$ m$^{-3}$)',xlim=(0,4),ylim=(0,2.1),title='Fixed ice mass can leave no admissible number')
    ax.grid(alpha=.2);ax.legend(loc='upper left',fontsize=9)
    fig.savefig(args.output/'01_ice_feasibility.png',dpi=180,metadata={'Software':'Cloud-BAL pinned analytical policy'})
    plt.close(fig)
    print(json.dumps({'nominal_max_mean_mass_kg':mmax,'cap_m3':cap,'mass_limit_g_m3':limit,'first_mass_g_m3':first*1000,'peak_mass_g_m3':peak*1000,'scope':'Stored REAL32 inputs; nominal analytical policy, not actual first-use density or forecast.'}))


if __name__ == '__main__':
    main()
