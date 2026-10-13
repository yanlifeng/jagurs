#!/usr/bin/env python3
"""Prepare and run the frozen Hirota 1800 s MPI regression, plus an analytic wave.

Python dependencies: numpy, netCDF4. Build and unpack once; the recurring run
includes input verification, MPI execution, comparisons, and the analytic test.
No historical archive path is needed after this repository has been downloaded.
"""
from pathlib import Path
import argparse
import hashlib
import json
import lzma
import os
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / 'data'
HISTORY_RE = re.compile(r't=\s*(\S+)\s+hz=\s*(\S+)\s+fx=\s*(\S+)\s+fy=\s*(\S+)')
TIMER_RE = re.compile(r'^\|([^|]+)\|\s*(\d+)\|\s*([0-9.Ee+-]+)\|')
RTOL = 1e-6
FIELD_ATOL = {'eta_raw': 2e-5, 'qx_raw': 1e-4,
              'qy_south_raw': 1e-4, 'depth_raw': 2e-5}
FULL_TIMER_S = {'All': 1114.070, '- fxynl_rwg': 389.461,
                'tstep_grid_vel': 427.604, 'tstep_grid_hgt': 92.026,
                '- hxynl_rwg': 9.601, '- mapgrids_vel': 3.542,
                '- mapgrids_hgt': 2.354, '- exch_edges_vel': 13.787,
                '- exch_edges_hgt': 16.652, '- exch_edges_wod': 4.759,
                '- recheck_wod': 22.436, 'maxgrd_v_check_nl': 39.267,
                'maxgrd_check_nl': 10.528, 'error_check': 20.588,
                'dump_gmt_nl_hgt': 183.619,
                'displacement_apply_kj_filter': 2.158, 'read_rupture': 1.191,
                'maxgrd_write_gmt_init': 1.947}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False,
                                   allow_nan=False) + '\n')


def manifest():
    return json.loads((HERE / 'dataset_manifest.json').read_text())


def check_hash(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f'SHA256 mismatch: {path}: {actual} != {expected}')


def validate_data(record, all_files=False):
    hashes = record['distributed_files_sha256']
    for name, expected in hashes.items():
        if all_files or not name.startswith('forcing'):
            check_hash(DATA / name, expected)


def validate_work(work, record):
    for name, expected in record['fixed_input_sha256'].items():
        check_hash(work / name, expected)
    for name in ('tsun.par', 'gridfile.dat'):
        if (work / name).read_bytes() != (DATA / name).read_bytes():
            raise ValueError(f'Frozen template modified: {work / name}')
    for name, expected in record['source_frames_sha256'].items():
        check_hash(work / name, expected['sha256'])
    for grid in range(1, 4):
        expected = sorted(n for n in record['source_frames_sha256']
                          if n.startswith(f'forcing{grid}/'))
        actual = (work / f'disp{grid}.list').read_text().splitlines()
        if actual != expected:
            raise ValueError(f'Frame ordering changed: disp{grid}.list')


def validate_simulation_input(output, record):
    """Accept decomposition changes only; reject accidental retuning of physics."""
    for name, expected in record['fixed_input_sha256'].items():
        if name not in ('tsun.par', 'gridfile.dat'):
            check_hash(output / name, expected)
    if (output / 'gridfile.dat').read_bytes() != (DATA / 'gridfile.dat').read_bytes():
        raise ValueError('Simulation grid template changed')
    actual = (output / 'tsun.par').read_text()
    expected = (DATA / 'tsun.par').read_text()
    for name in ('procx', 'procy'):
        m = re.findall(rf'(?mi)^\s*{name}\s*=\s*(\d+)\s*$', actual)
        if len(m) != 1 or int(m[0]) < 1:
            raise ValueError(f'Invalid MPI decomposition: {name}')
        expected = replace_parameter(expected, name, int(m[0]))
    if actual != expected:
        raise ValueError('Simulation namelist changed beyond procx/procy')
    for name, expected in record['source_frames_sha256'].items():
        check_hash(output / name, expected['sha256'])
    for grid in range(1, 4):
        expected = sorted(n for n in record['source_frames_sha256']
                          if n.startswith(f'forcing{grid}/'))
        if (output / f'disp{grid}.list').read_text().splitlines() != expected:
            raise ValueError(f'Simulation source ordering changed: disp{grid}.list')


def prepare(work):
    start = time.monotonic()
    record = manifest()
    validate_data(record, all_files=True)
    work = work.resolve()
    if work.exists() and any(work.iterdir()):
        if not (work / 'prepared.json').exists():
            raise ValueError(f'Refusing to overwrite nonempty directory: {work}')
        validate_work(work, record)
        print(f'Existing prepared input verified: {work}', flush=True)
        return
    work.mkdir(parents=True, exist_ok=True)
    for name in set(record['fixed_input_sha256']) | {'tsun.par', 'gridfile.dat'}:
        shutil.copyfile(DATA / name, work / name)
    for grid in range(1, 4):
        pack = DATA / f'forcing{grid}.xor.xz'
        pieces = [pack] if pack.exists() else sorted(DATA.glob(pack.name + '.part*'))
        if not pieces:
            raise ValueError(f'Missing source pack for grid {grid}')
        names = sorted(n for n in record['source_frames_sha256']
                       if n.startswith(f'forcing{grid}/'))
        if len(names) != record['source_frames']:
            raise ValueError(f'Wrong source frame count for grid {grid}')
        (work / f'forcing{grid}').mkdir()
        # Concatenation is a one-time preparation cost; the MPI benchmark reads
        # ordinary upstream GRD files, with no decompression in timed kernels.
        with tempfile.TemporaryFile() as joined:
            for part in pieces:
                with part.open('rb') as f:
                    shutil.copyfileobj(f, joined)
            joined.seek(0)
            with lzma.LZMAFile(joined, 'rb') as f:
                if f.read(len(b'JAGR-XOR-1\n')) != b'JAGR-XOR-1\n':
                    raise ValueError('Invalid exact-source archive header')
                previous = None
                for name in names:
                    length_bytes = f.read(8)
                    if len(length_bytes) != 8:
                        raise ValueError(f'Truncated source frame: {name}')
                    length, = struct.unpack('<Q', length_bytes)
                    if length != record['source_frames_sha256'][name]['bytes']:
                        raise ValueError(f'Invalid source size: {name}')
                    raw = f.read(length)
                    if len(raw) != length:
                        raise ValueError(f'Truncated source bytes: {name}')
                    delta = np.frombuffer(raw, dtype=np.uint8)
                    if previous is None:
                        previous = np.zeros_like(delta)
                    previous = np.bitwise_xor(previous, delta)
                    target = work / name
                    target.write_bytes(previous.tobytes())
                    check_hash(target, record['source_frames_sha256'][name]['sha256'])
                if f.read(1):
                    raise ValueError('Unexpected extra frame bytes')
        (work / f'disp{grid}.list').write_text('\n'.join(names) + '\n')
        print(f'Grid {grid}: {len(names)} source frames unpacked and SHA256 verified', flush=True)
    save(work / 'prepared.json', dict(dataset_manifest_sha256=sha(HERE / 'dataset_manifest.json'),
         wall_s=time.monotonic() - start, note='One-time input preparation, excluded from recurring runtime.'))
    print(f'Prepared {work} in {time.monotonic() - start:.2f} s', flush=True)


def new_directory(path):
    path = path.resolve()
    if path.exists():
        raise ValueError(f'Output directory already exists; use a new path: {path}')
    path.mkdir(parents=True)
    return path


def replace_parameter(text, name, value):
    text, count = re.subn(rf'(?mi)^\s*{re.escape(name)}\s*=.*$', f'{name}={value}', text)
    if count != 1:
        raise ValueError(f'Expected one namelist parameter: {name}')
    return text


def stage(work, output, procx, procy):
    for source in work.iterdir():
        if source.name in ('prepared.json', 'tsun.par'):
            continue
        # Runtime-only symlinks avoid copying 650 MB for every optimization run.
        (output / source.name).symlink_to(source.resolve(), target_is_directory=source.is_dir())
    par = (work / 'tsun.par').read_text()
    par = replace_parameter(par, 'procx', procx)
    par = replace_parameter(par, 'procy', procy)
    (output / 'tsun.par').write_text(par)


def mpi_run(output, exe, args, ranks):
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS=str(args.threads), MKL_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MKL_DYNAMIC='FALSE', MKL_CBWR='COMPATIBLE')
    command = shlex.split(args.mpiexec) + shlex.split(args.mpi_args)
    command += ['-n', str(ranks), str(exe), 'par=tsun.par']
    if args.cores:
        command = ['taskset', '-c', args.cores] + command
    start = time.monotonic()
    with (output / 'launcher.log').open('w') as f:
        result = subprocess.run(command, cwd=output, env=env, stdout=f, stderr=subprocess.STDOUT)
    row = dict(command=command, returncode=result.returncode,
               wall_s=time.monotonic() - start, ranks=ranks,
               threads_per_rank=args.threads, executable_sha256=sha(exe),
               environment={key: env.get(key) for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                   'MKL_CBWR', 'MKL_DYNAMIC', 'OPENBLAS_NUM_THREADS', 'I_MPI_PIN',
                   'I_MPI_PIN_PROCESSOR_LIST', 'I_MPI_FABRICS') if env.get(key) is not None})
    save(output / 'mpi_run.json', row)
    return row


def read_history(path, duration=None, integer_only=False, expected_dt=None):
    rows = []
    last = None
    with path.open() as f:
        for line in f:
            m = HISTORY_RE.search(line)
            if not m:
                continue
            row = [float(x.replace('D', 'E')) for x in m.groups()]
            if not np.isfinite(row).all():
                raise ValueError(f'Nonfinite gauge output: {path}')
            if last is not None and row[0] <= last:
                raise ValueError(f'Nonmonotonic gauge time: {path}')
            if expected_dt is not None:
                interval = row[0] if last is None else row[0] - last
                if abs(interval - expected_dt) > 1e-8:
                    raise ValueError(f'Missing or shifted native gauge sample: {path} at {row[0]} s')
            last = row[0]
            if duration is not None and row[0] > duration + 1e-8:
                break
            if integer_only and abs(row[0] - round(row[0])) >= 1e-8:
                continue
            rows.append(row)
    if not rows:
        raise ValueError(f'No gauge samples found: {path}')
    return np.asarray(rows)


def compare(actual, reference, atol):
    actual, reference = np.asarray(actual), np.asarray(reference)
    if actual.shape != reference.shape:
        return dict(passed=False, actual_shape=list(actual.shape), reference_shape=list(reference.shape))
    finite = bool(np.isfinite(actual).all() and np.isfinite(reference).all())
    if not finite:
        return dict(passed=False, finite=False)
    diff = np.abs(actual - reference)
    tolerance = atol + RTOL * np.abs(reference)
    # Explicit reductions avoid a BLAS thread pool competing with MPI or
    # changing verifier timing according to unrelated host BLAS defaults.
    norm = float(np.sqrt(np.sum(reference * reference, dtype=np.float64)))
    error_norm = float(np.sqrt(np.sum(diff * diff, dtype=np.float64)))
    return dict(passed=bool(np.all(diff <= tolerance)), finite=True,
                samples=int(actual.size), max_abs_error=float(np.max(diff)),
                relative_L2=error_norm / max(norm, 1e-300),
                max_tolerance_ratio=float(np.max(diff / tolerance)),
                failing_samples=int(np.count_nonzero(diff > tolerance)), atol=atol, rtol=RTOL)


def verify(output):
    start = time.monotonic()
    record = manifest()
    validate_data(record)
    validate_simulation_input(output, record)
    gauges = {}
    with np.load(DATA / 'reference_gauges.npz') as refs:
        for sid, reference in zip(refs['station_ids'], refs['histories']):
            actual = read_history(output / f'tgs{int(sid):06d}', duration=1800., integer_only=True, expected_dt=.1)
            time_ok = actual.shape == reference.shape and bool(np.allclose(actual[:, 0], reference[:, 0], rtol=0, atol=1e-8))
            row = {'time_and_shape_passed': time_ok}
            for col, name, atol in ((1, 'eta_m', 2e-5), (2, 'qx_m2_s', 1e-4), (3, 'qy_south_m2_s', 1e-4)):
                row[name] = compare(actual[:, col], reference[:, col], atol)
            row['passed'] = time_ok and all(row[n]['passed'] for n in ('eta_m', 'qx_m2_s', 'qy_south_m2_s'))
            gauges[str(int(sid))] = row
    fields, values, refvalues = {}, {}, {}
    with Dataset(DATA / 'bathy3.grd') as d:
        expected_spacing = np.asarray(d['spacing'][:])
    with np.load(DATA / 'reference_fields.npz') as refs:
        for name, atol in FIELD_ATOL.items():
            with Dataset(output / f'SD03.{name}.00018000.grd') as d:
                raw = d['z'][:]
                if np.ma.count_masked(raw):
                    raise ValueError(f'Unexpected masked raw output: {name}')
                values[name] = np.asarray(raw)
                refvalues[name] = refs[name]
                row = compare(values[name], refs[name], atol)
                row['dimensions_passed'] = bool(np.array_equal(d['dimension'][:], record['grids'][-1]['shape'][::-1]))
                row['spacing_passed'] = bool(np.allclose(d['spacing'][:], expected_spacing, rtol=0, atol=1e-14))
                row['coordinates_passed'] = all(bool(np.allclose(d[f'{axis}_range'][:], refs[name + f'_{axis}_range'], rtol=0, atol=1e-12)) for axis in ('x', 'y'))
                row['passed'] = row['passed'] and row['coordinates_passed'] and row['dimensions_passed'] and row['spacing_passed']
                fields[name] = row
    # The raw water-column depth diagnoses shoreline stability. Cells closer
    # than the allowed eta+bed error to 1e-6 m are reported separately, since a
    # sign flip at that threshold is not a meaningful physical discrepancy.
    water = values['eta_raw'] + values['depth_raw']
    refwater = refvalues['eta_raw'] + refvalues['depth_raw']
    margin = FIELD_ATOL['eta_raw'] + FIELD_ATOL['depth_raw'] + RTOL * (
        np.abs(refvalues['eta_raw']) + np.abs(refvalues['depth_raw']))
    stable = np.abs(refwater - 1e-6) > margin
    mismatch = (water > 1e-6) != (refwater > 1e-6)
    wetdry = dict(threshold_m=1e-6, stable_nodes=int(stable.sum()),
                  near_threshold_nodes=int((~stable).sum()),
                  all_mask_differences=int(mismatch.sum()),
                  stable_mask_differences=int((mismatch & stable).sum()),
                  passed=not bool(np.any(mismatch & stable)))
    passed = all(r['passed'] for r in gauges.values()) and all(r['passed'] for r in fields.values()) and wetdry['passed']
    result = dict(passed=passed, duration_s=1800., gauges=gauges, fields=fields,
                  wetdry=wetdry, wall_s=time.monotonic() - start,
                  scope='Numerical agreement with frozen historical full-run prefix; no new observation-fit claim.')
    save(output / 'verification.json', result)
    return result


def profile(output):
    ranks = {}
    for path in sorted(output.glob('stdout.*')):
        timers = {}
        with path.open(errors='replace') as f:
            for line in f:
                m = TIMER_RE.match(line)
                if m:
                    name, calls, elapsed = m.groups()
                    timers[name.strip()] = dict(calls=int(calls), elapsed_s=float(elapsed))
        if timers:
            ranks[path.name] = timers
    all_times = [r['All']['elapsed_s'] for r in ranks.values() if 'All' in r]
    rank0 = ranks.get('stdout.000000', {})
    total = rank0.get('All', {}).get('elapsed_s', 0.)
    comparison = {name: dict(short_elapsed_s=rank0[name]['elapsed_s'],
                   short_percent_of_all=100 * rank0[name]['elapsed_s'] / total,
                   historical_full_percent_of_all=100 * elapsed / FULL_TIMER_S['All'])
                  for name, elapsed in FULL_TIMER_S.items() if name in rank0 and total}
    result = dict(rank_timers=ranks, rank0_comparison_to_historical_full_run=comparison,
                  note='Timer regions overlap: parent tstep regions include nested kernel regions. Percentages must not be summed. Source initialization is proportionally larger in a short prefix.')
    if all_times:
        result['all_rank_summary'] = dict(ranks_with_timer=len(all_times), max_s=max(all_times),
            mean_s=float(np.mean(all_times)), min_s=min(all_times), max_over_mean=max(all_times) / float(np.mean(all_times)))
        frozen_path = HERE / 'full_case_profile.json'
        if frozen_path.exists():
            frozen = json.loads(frozen_path.read_text())
            comparisons = {}
            total_mean = float(np.mean(all_times))
            for name, original in frozen['regions'].items():
                values = [r[name]['elapsed_s'] for r in ranks.values() if name in r]
                if not values:
                    continue
                short_mean = float(np.mean(values))
                comparisons[name] = dict(observed_ranks=len(values),
                    short_seconds_min=min(values), short_seconds_max=max(values),
                    short_seconds_mean=short_mean,
                    short_percent_of_all_mean=100 * short_mean / total_mean,
                    historical_full_percent_of_all_mean=original['percent_of_all_mean'],
                    historical_full_seconds_mean=original['seconds_mean'],
                    historical_full_seconds_max=original['seconds_max'])
            result['all_rank_comparison_to_historical_full_run'] = comparisons
    save(output / 'profile.json', result)
    return result


def analytic(output, exe, args):
    output = new_directory(output)
    for source in (DATA / 'analytic').iterdir():
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    run = mpi_run(output, exe, args, 4)
    if run['returncode']:
        result = dict(passed=False, mpi_run=run)
    else:
        history = read_history(output / 'tgs000001')
        t, actual = history[:, 0], history[:, 1]
        g, depth, dx, wavelength, dt, amplitude = 9.8, 4000., 500., 40000., .25, .01
        kh = 2 * np.sin((2 * np.pi / wavelength) * dx / 2) / dx
        omega = 2 / dt * np.arcsin(dt * np.sqrt(g * depth * kh * kh) / 2)
        expected = amplitude * np.cos(omega * (t + dt / 2)) / np.cos(omega * dt / 2)
        relative_l2 = float(np.linalg.norm(actual - expected) / np.linalg.norm(expected))
        max_error = float(np.max(np.abs(actual - expected)))
        timing_ok = len(t) >= 960 and abs(t[0] - .25) < 1e-9 and t[-1] >= 240. and bool(np.allclose(np.diff(t), .25, rtol=0, atol=1e-8))
        np.savetxt(output / 'analytic_comparison.csv', np.c_[t, actual, expected], delimiter=',',
            header='time_s,computed_eta_m,discrete_analytic_eta_m', comments='')
        result = dict(passed=relative_l2 < 1e-4 and max_error < 1e-6 and timing_ok,
                      relative_L2=relative_l2, relative_L2_limit=1e-4,
                      max_abs_error_m=max_error, max_abs_error_limit_m=1e-6,
                      timing_passed=timing_ok, final_time_s=float(t[-1]), samples=len(t), mpi_run=run,
                      reference='Independent discrete SWE dispersion, prescribed leapfrog half-step initialization; no fitted phase or amplitude.')
    save(output / 'analytic.json', result)
    return result


def run_all(args):
    if args.ranks != args.procx * args.procy:
        raise ValueError('--ranks must equal --procx times --procy')
    exe = args.exe.resolve()
    if not exe.is_file():
        raise ValueError(f'Executable not found: {exe}')
    work = args.work_dir.resolve()
    output = new_directory(args.output)
    begin = time.monotonic()
    report = dict(passed=False, hostname=platform.node(), machine=platform.machine(),
                  platform=platform.platform(), ranks=args.ranks, procx=args.procx,
                  procy=args.procy, threads_per_rank=args.threads,
                  dataset_manifest_sha256=sha(HERE / 'dataset_manifest.json'),
                  executable_sha256=sha(exe), budget_s=300.)
    try:
        start = time.monotonic()
        validate_data(manifest())
        validate_work(work, manifest())
        report['input_validation_wall_s'] = time.monotonic() - start
        stage(work, output, args.procx, args.procy)
        print(f'Running full-size Hirota prefix: {args.ranks} MPI ranks, 1800 simulated seconds', flush=True)
        report['mpi_run'] = mpi_run(output, exe, args, args.ranks)
        if report['mpi_run']['returncode']:
            raise RuntimeError(f'JAGURS failed; see {output / "launcher.log"}')
        print(f'MPI completed in {report["mpi_run"]["wall_s"]:.2f} s; checking frozen references', flush=True)
        verification = verify(output)
        report['historical_regression_passed'] = verification['passed']
        report['verification_wall_s'] = verification['wall_s']
        timings = profile(output)
        report['timers_available'] = bool(timings['rank_timers'])
        expected_logs = {f'stdout.{rank:06d}' for rank in range(args.ranks)}
        report['profile_complete'] = set(timings['rank_timers']) == expected_logs and all(
            r.get('All', {}).get('elapsed_s', 0.) > 0.
            and '- fxynl_rwg' in r and 'tstep_grid_hgt' in r
            for r in timings['rank_timers'].values())
        analytic_result = analytic(output / 'analytic', exe, args)
        report['analytic'] = analytic_result
        report['numerical_correctness_passed'] = verification['passed'] and analytic_result['passed']
        report['recurring_wall_s'] = time.monotonic() - begin
        report['within_5_minutes'] = report['recurring_wall_s'] < 300.
        report['passed'] = report['numerical_correctness_passed'] and report['within_5_minutes'] and report['profile_complete']
    except Exception as exc:
        report['error'] = str(exc)
        report['recurring_wall_s'] = time.monotonic() - begin
        save(output / 'report.json', report)
        raise
    save(output / 'report.json', report)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['passed'] else (3 if report['numerical_correctness_passed'] and report['profile_complete'] else 2)


def add_mpi_arguments(parser):
    parser.add_argument('--exe', type=Path, default=ROOT / 'build/gnu/jagurs')
    parser.add_argument('--mpiexec', default='mpiexec', help='MPI launcher command, shell-style tokenization')
    parser.add_argument('--mpi-args', default='', help='Launcher options; quote as --mpi-args="..."')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--cores', default='', help='Optional Linux taskset CPU list, e.g. 0-15; respect scheduler allocation')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='One-time exact unpacking and SHA verification')
    p.add_argument('--work-dir', type=Path, default=ROOT / 'build/hirota_inputs')
    p = commands.add_parser('run', help='Run real-case regression + independent analytic check; write report.json')
    p.add_argument('--work-dir', type=Path, default=ROOT / 'build/hirota_inputs')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ranks', type=int, default=16)
    p.add_argument('--procx', type=int, default=4)
    p.add_argument('--procy', type=int, default=4)
    add_mpi_arguments(p)
    for name in ('verify', 'profile'):
        p = commands.add_parser(name)
        p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('analytic', help='Only the independent standing-wave calculation')
    p.add_argument('--output', type=Path, required=True)
    add_mpi_arguments(p)
    args = ap.parse_args()
    if args.command == 'prepare':
        prepare(args.work_dir)
        return 0
    if args.command == 'run':
        return run_all(args)
    if args.command == 'profile':
        print(json.dumps(profile(args.output), indent=2))
        return 0
    if args.command == 'verify':
        result = verify(args.output)
        print(json.dumps({key: val for key, val in result.items() if key not in ('gauges', 'fields')}, indent=2))
        return 0 if result['passed'] else 2
    validate_data(manifest())
    result = analytic(args.output, args.exe.resolve(), args)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
