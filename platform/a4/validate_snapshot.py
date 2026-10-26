#!/usr/bin/env python3
"""Regression against retained Oct26 evidence; no historical files are edited.

Private-site acceptance adapter, not a distributable case/input package.
One 180-second physical window with all 182 source frames, 64 MPI ranks.
"""
import argparse
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--historical', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    history, exe, dest = (p.resolve() for p in (args.historical, args.candidate, args.output))
    dest.mkdir(parents=True, exist_ok=False)
    sys.dont_write_bytecode = True  # Even imported helper caches stay read-only.
    sys.path.insert(0, str(history))
    common = importlib.import_module('common')
    runner = importlib.import_module('run_case')
    # Both modules use their ROOT for newly generated state. Inputs and the
    # historical runner remain read-only; no original batch is ever started.
    common.ROOT = runner.ROOT = dest
    for name in ('rank_exec.py', 'affinity_probe'):
        (dest/name).symlink_to(history/name)
    common.save(dest/'build_catalog.json', {'skip': dict(
        executable=str(exe), executable_sha256=common.sha(exe))})
    common.save(dest/'provenance.json', dict(
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        files={str(history/n): common.sha(history/n) for n in ('common.py','run_case.py','rank_exec.py','affinity_probe')},
        candidate_sha256=common.sha(exe), historical_directory=str(history),
        scope='Short source-path/coupling regression; not a new scaling curve or full-event observation validation'))
    r = runner.run(10, 64, 180, 'merged-p064', timeout=600, variant='skip')
    comparison = runner.compare(str(history/'runs/control-instrumented'), 'merged-p064')
    log = (dest/'runs/merged-p064/stdout.000000').read_text()
    matches = re.findall(r'New rupture step: istep=(\d+) dt=\S+ t=\S+ tau=\S+ ig=\d+ irupt=(\d+)',log)
    checks = dict(r['checks'], comparison=comparison['passed'],
        exact_source_clock=[tuple(map(int,m)) for m in matches]==[(1+3*i,i+1) for i in range(182)],
        affinity=json.loads((dest/'runs/merged-p064/affinity.json').read_text())['passed'],
        timer_rank_count=len(r['all_rank_timers'])==64,
        error_guard_count=all(t['error_global_reduce']['calls']==601 for t in r['all_rank_timers'].values()),
        gauge_count=all(t['gauge_output']['calls']==200 for t in r['all_rank_timers'].values()))
    result = dict(passed=all(checks.values()), checks=checks, mpi_wall_s=r['mpi_wall_s'],
                  max_other_cpu_cores=r['max_other_cpu_cores'], comparison=comparison)
    common.save(dest/'acceptance.json', result)
    print(json.dumps(result,indent=2))
    if not result['passed']:
        raise SystemExit(2)

if __name__ == '__main__':
    main()
