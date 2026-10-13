#!/usr/bin/env python3
"""Optional report figure: requires matplotlib in addition to runtime packages."""
from pathlib import Path
import argparse
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    full = json.loads((HERE / 'full_case_profile.json').read_text())
    quick = json.loads(args.profile.read_text())
    ranks = list(quick['rank_timers'].values())
    if len(ranks) != 16:
        parser.error('This figure compares the same 16-rank 4x4 layout')
    names = ['- fxynl_rwg', 'tstep_grid_hgt', '- exch_edges_vel',
             '- recheck_wod', 'dump_gmt_nl_hgt', 'displacement_apply_kj_filter']
    labels = ['Nonlinear momentum', 'Height step (inclusive)', 'Velocity halo exchange',
              'Wet/dry recheck', 'Grid output', 'Kajiura source filter']
    total = np.mean([r['All']['elapsed_s'] for r in ranks])
    qshare = [100 * np.mean([r[n]['elapsed_s'] for r in ranks]) / total for n in names]
    fshare = [full['regions'][n]['percent_of_all_mean'] for n in names]
    # Raw timer arrays preserve MPI ranks in increasing rank order.
    region = full['regions']['- fxynl_rwg']
    full_values = np.asarray(region['seconds_by_rank'])
    quick_values = np.asarray([r['- fxynl_rwg']['elapsed_s'] for r in ranks])
    if full_values.shape != quick_values.shape:
        raise ValueError('Historical rank arrays do not match')
    full_normalized = full_values / full_values.mean()
    quick_normalized = quick_values / quick_values.mean()
    fig, (left, right) = plt.subplots(1, 2, figsize=(12.8, 5.0), layout='constrained')
    y = np.arange(len(names))
    left.barh(y - .19, fshare, height=.36, color='#31688e', label='Full 10861 s')
    left.barh(y + .19, qshare, height=.36, color='#d78422', label='Quick 1800 s')
    for index, (a, b) in enumerate(zip(fshare, qshare)):
        left.text(a + .45, index - .19, f'{a:.1f}%', va='center', fontsize=8)
        left.text(b + .45, index + .19, f'{b:.1f}%', va='center', fontsize=8)
    left.set_yticks(y, labels)
    left.invert_yaxis()
    left.set_xlim(0, max(fshare + qshare) * 1.2)
    left.set_xlabel('Mean across MPI ranks / total elapsed (%)')
    left.set_title('Same active kernels and similar time distribution')
    left.legend(frameon=False, loc='lower right')
    right.plot(np.arange(16), full_normalized, '-o', color='#31688e', label='Full')
    right.plot(np.arange(16), quick_normalized, '-s', color='#d78422', label='Quick')
    right.axhline(1, color='0.6', lw=1, ls='--')
    right.set_xticks(np.arange(0, 16, 2))
    right.set_xlabel('MPI rank in the same 4 x 4 decomposition')
    right.set_ylabel('Momentum kernel time / mean across ranks')
    correlation = float(np.corrcoef(full_normalized, quick_normalized)[0, 1])
    right.set_title(f'Uneven per-rank workload preserved (r = {correlation:.3f})')
    right.legend(frameon=False)
    fig.suptitle('Hirota Bay: full-size real-data HPC regression, 16 MPI x 1 thread')
    fig.supxlabel('Timer regions can overlap; percentages must not be added. Source work occupies a larger fraction of the short case.', fontsize=9)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    fig.savefig(args.output.with_suffix('.pdf'))
    print(json.dumps(dict(momentum_rank_correlation=correlation,
                         quick_percent_of_all=dict(zip(names, qshare)),
                         full_percent_of_all=dict(zip(names, fshare))), indent=2))


if __name__ == '__main__':
    main()
