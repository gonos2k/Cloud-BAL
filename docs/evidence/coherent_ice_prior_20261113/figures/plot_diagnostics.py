#!/usr/bin/env python3
"""Plot coverage and distinct numerical observations without implying acceptance."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('diagnostic', type=Path)
    parser.add_argument('common_receipt', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    diagnostic = json.loads(args.diagnostic.read_text())
    common = json.loads(args.common_receipt.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    values = [common['covered_common_ok'], common['covered_common_failed'], common['uncovered_selected']]
    labels = ['Common OK', 'Common rejected', 'Uncaptured']
    axes[0].barh(labels, values, color=['#327c78', '#c16649', '#90969c'])
    for row, value in enumerate(values):
        axes[0].text(value + 2500, row, f'{value:,}', va='center')
    axes[0].set_xlim(0, 245000)
    axes[0].set_title(f"Frozen selection: {common['frozen_selected']:,} cells")
    axes[0].set_xlabel('Cells; whole application stops for missing capture')
    axes[0].invert_yaxis()
    keys = ['ice_zero_ni_positive', 'solid_total_zero', 'computed_rounded_ni_density_above_cap']
    x = np.arange(len(keys))
    for shift, name, label, color in [(-.18, 'history_same_covered_cells', 'History', '#8596b0'),
                                      (.18, 'coherent_return_covered_cells', 'Same-boundary return', '#327c78')]:
        counts = [diagnostic[name][key] for key in keys]
        axes[1].bar(x + shift, counts, .36, label=label, color=color)
        for position, value in zip(x + shift, counts):
            axes[1].text(position, value + 1500, f'{value:,}', ha='center', fontsize=8)
    axes[1].set_xticks(x, ['QI=0, NI>0', 'QI+QS=0', 'Scaled NI above cap'])
    axes[1].set_ylim(0, 105000)
    axes[1].set_title('Same 288,745 covered selected cells')
    axes[1].set_ylabel('Cells; observations may overlap')
    axes[1].legend(frameon=False)
    fig.suptitle('Numerical information and diagnostics; no new initialized state', fontsize=13)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
