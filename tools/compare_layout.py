#!/usr/bin/env python3
"""Paired full-output regression. Platform launch/transport policy is external.

B1/C1/C2/B2 share one allocation. C1 uses legacy output defaults, C2 an
explicit equivalent namelist. No frozen scientific thresholds are changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT/'benchmarks/hirota_quick/run.py'


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path, required=True)
    ap.add_argument('--baseline-sha256', required=True)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--work-dir', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--mpiexec', required=True)
    ap.add_argument('--ranks', type=int, required=True)
    ap.add_argument('--threads', type=int, required=True)
    ap.add_argument('--procx', type=int, required=True)
    ap.add_argument('--procy', type=int, required=True)
    ap.add_argument('--run-budget', type=int, default=2100)
    args = ap.parse_args()
    baseline, candidate, work, dest = (p.resolve() for p in
        (args.baseline, args.candidate, args.work_dir, args.output))
    if args.ranks != args.procx*args.procy:
        ap.error('ranks must equal procx*procy')
    if sha(baseline) != args.baseline_sha256:
        raise RuntimeError('Baseline binary hash differs; do not silently change the control')
    if (work/'coupling_output.nml').exists():
        raise RuntimeError('Control prepared input must not already contain an output override')
    if shutil.disk_usage(dest.parent if dest.parent.exists() else ROOT).free < 64*1024**3:
        raise RuntimeError('Need >=64 GiB free; full output must not be truncated')
    subprocess.run([sys.executable, str(ROOT/'tools/check_layout.py')], check=True)
    dest.mkdir(parents=True, exist_ok=False)
    explicit = dest/'explicit-inputs'
    explicit.mkdir()
    for source in work.iterdir():
        (explicit/source.name).symlink_to(source.resolve(), target_is_directory=source.is_dir())
    config = ROOT/'cases/hirota_quick/coupling_output.nml'
    shutil.copyfile(config, explicit/config.name)
    started = time.monotonic()
    record = dict(host=os.uname().nodename, job=os.environ.get('CCS_JOB_ID'),
        plan=['B1', 'C1', 'C2', 'B2'], ranks=args.ranks, threads=args.threads,
        procx=args.procx, procy=args.procy, baseline=str(baseline), candidate=str(candidate),
        baseline_sha256=sha(baseline), candidate_sha256=sha(candidate),
        prepared_inputs=str(work), explicit_config_sha256=sha(config),
        mpi_launcher=args.mpiexec, environment={key: os.environ.get(key) for key in
            ('UCX_TLS', 'OMPI_MCA_pml', 'OMPI_MCA_btl', 'OMPI_MCA_coll')},
        frozen_inputs_full_output=True, original_tolerances=True,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for folder in
            ('src', 'tools', 'platform/lineshine', 'cases/hirota_quick')
            for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)},
        performance_rule='Candidate mean MPI and workflow times <= 1.05 * paired control means; '
                         'two samples per binary, indicative single-node regression check only',
        runs=[])
    save(dest/'paired.json', record)
    env = os.environ.copy()
    env['JAGURS_RUN_LIMIT_S'] = '180'
    preflight = [sys.executable, str(RUNNER), 'analytic', '--exe', str(candidate),
                 '--output', str(dest/'preflight'), '--threads', '1', '--mpiexec', args.mpiexec]
    with (dest/'preflight.log').open('w') as log:
        result = subprocess.run(preflight, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        record.update(finished=True, stopped_reason='Candidate analytic preflight failed')
        save(dest/'paired.json', record)
        return 2
    for tag in record['plan']:
        remaining = args.run_budget-(time.monotonic()-started)
        if remaining < 360:
            record['stopped_reason'] = 'Insufficient remaining budget for a full run'
            break
        exe = baseline if tag.startswith('B') else candidate
        inputs = explicit if tag == 'C2' else work
        output = dest/tag
        env['JAGURS_RUN_LIMIT_S'] = str(int(min(600, remaining-120)))
        command = [sys.executable, str(RUNNER), 'run', '--exe', str(exe),
            '--work-dir', str(inputs), '--output', str(output),
            '--ranks', str(args.ranks), '--procx', str(args.procx), '--procy', str(args.procy),
            '--threads', str(args.threads), '--mpiexec', args.mpiexec]
        print('START '+tag, flush=True)
        t = time.monotonic()
        with (dest/(tag+'.log')).open('w') as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        row = dict(tag=tag, returncode=result.returncode, total_wall_s=time.monotonic()-t,
                   coupling_config='explicit legacy-equivalent' if tag == 'C2' else 'absent / legacy defaults')
        if (output/'report.json').exists():
            report = json.loads((output/'report.json').read_text())
            row.update({key:report[key] for key in ('numerical_correctness_passed',
                'historical_regression_passed', 'profile_complete', 'within_5_minutes',
                'recurring_wall_s', 'error') if key in report})
            row['mpi_wall_s'] = report.get('mpi_run', {}).get('wall_s')
        record['runs'].append(row)
        save(dest/'paired.json', record)
        print('END '+json.dumps(row), flush=True)
        if result.returncode not in (0, 3) or not row.get('numerical_correctness_passed') or not row.get('profile_complete'):
            record['stopped_reason'] = 'Runtime/numerical/profile failure; preserve all evidence'
            break
    complete = len(record['runs']) == 4 and 'stopped_reason' not in record
    record.update(all_four_completed=complete, elapsed_before_extra_audit_s=time.monotonic()-started)
    if complete:
        for field in ('mpi_wall_s', 'recurring_wall_s'):
            b = [r[field] for r in record['runs'] if r['tag'].startswith('B')]
            c = [r[field] for r in record['runs'] if r['tag'].startswith('C')]
            ratio = statistics.mean(c)/statistics.mean(b)
            record[field+'_comparison'] = dict(baseline=b, candidate=c,
                baseline_mean=statistics.mean(b), candidate_mean=statistics.mean(c),
                candidate_over_baseline=ratio, change_percent=100*(ratio-1),
                within_five_percent=ratio <= 1.05)
        # Additional stronger check, excluded from every timed sample.
        hashes = {}
        for tag in record['plan']:
            selected = sorted(p for p in (dest/tag).iterdir() if p.is_file() and not p.is_symlink()
                and (p.suffix == '.grd' or (p.name.startswith('tgs') and p.name[3:].isdigit())))
            hashes[tag] = {p.name:sha(p) for p in selected}
            save(dest/(tag+'-output-sha256.json'), hashes[tag])
        ref = hashes['B1']
        cross = dict(reference='B1', criterion='SHA256 equality of every generated GRD and native gauge file',
                     audit_excluded_from_performance=True, comparisons={})
        for tag in ('C1', 'C2', 'B2'):
            missing = sorted(set(ref)-set(hashes[tag]))
            extra = sorted(set(hashes[tag])-set(ref))
            different = sorted(name for name in set(ref)&set(hashes[tag]) if ref[name] != hashes[tag][name])
            cross['comparisons'][tag] = dict(files=len(hashes[tag]), missing=missing, extra=extra,
                different=different, byte_identical=not (missing or extra or different))
        cross['passed'] = bool(ref) and all(r['byte_identical'] for r in cross['comparisons'].values())
        save(dest/'output-equivalence.json', cross)
        record['output_equivalence_passed'] = cross['passed']
        record['performance_nonregression_passed'] = all(record[field+'_comparison']['within_five_percent']
            for field in ('mpi_wall_s', 'recurring_wall_s'))
    record.update(finished=True, elapsed_including_extra_audit_s=time.monotonic()-started,
        note='Original exit 3 is the 300s performance gate, not a scientific failure. No sample selection.')
    record['passed'] = complete and record.get('output_equivalence_passed', False) and record.get('performance_nonregression_passed', False)
    save(dest/'paired.json', record)
    print('COMPARISON_FINISHED '+str(dest), flush=True)
    return 0 if record['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
