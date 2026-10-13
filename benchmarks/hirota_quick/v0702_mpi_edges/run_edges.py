#!/usr/bin/env python3
"""Short, full-geometry CPU MPI nesting regression, including both opposite edges.

Run from a prepared checkout with its MPI environment loaded. This is a separate
decomposition test, not a replacement for the 1800 s frozen-reference regression.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import resource
import sys

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('hirota_benchmark', HERE.parent / 'run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def field(path):
    with Dataset(path) as ds:
        return np.asarray(ds['z'][:]), {
            key: np.asarray(ds[key][:]) for key in ('x_range', 'y_range', 'spacing', 'dimension')
        }


def compare_layout(output, reference):
    result = {'passed': True, 'fields': [], 'gauges': {}}
    for grid in ('SD01', 'SD02', 'SD03'):
        for step in (90, 180):
            for variable, atol in bench.FIELD_ATOL.items():
                name = f'{grid}.{variable}.{step:08d}.grd'
                actual, metadata = field(output / name)
                expected, ref_metadata = field(reference / name)
                row = bench.compare(actual, expected, atol)
                row['file'] = name
                row['coordinate_metadata_equal'] = all(
                    np.array_equal(metadata[k], ref_metadata[k]) for k in metadata)
                row['passed'] &= row['coordinate_metadata_equal']
                row['reference_abs_max'] = float(np.max(np.abs(expected)))
                result['fields'].append(row)
                result['passed'] &= row['passed']

    expected_files = sorted(p.name for p in reference.glob('tgs[0-9]*'))
    actual_files = sorted(p.name for p in output.glob('tgs[0-9]*'))
    if not expected_files or actual_files != expected_files:
        raise ValueError('Missing or inconsistent gauge outputs')
    max_error = np.zeros(3)
    max_scaled = np.zeros(3)
    max_reference = np.zeros(3)
    failed = []
    samples = 0
    for name in expected_files:
        actual = bench.read_history(output / name, expected_dt=.1)
        expected = bench.read_history(reference / name, expected_dt=.1)
        if actual.shape != expected.shape or not np.array_equal(actual[:, 0], expected[:, 0]):
            raise ValueError(f'Gauge time mismatch: {name}')
        if abs(actual[-1, 0] - 18.1) > 1e-8:
            raise ValueError(f'Incomplete gauge history: {name}')
        samples += len(actual)
        errors = np.abs(actual[:, 1:] - expected[:, 1:])
        limits = np.array([2e-5, 1e-4, 1e-4]) + bench.RTOL * np.abs(expected[:, 1:])
        max_error = np.maximum(max_error, errors.max(axis=0))
        max_scaled = np.maximum(max_scaled, (errors / limits).max(axis=0))
        max_reference = np.maximum(max_reference, np.abs(expected[:, 1:]).max(axis=0))
        if np.any(errors > limits):
            failed.append(name)
    result['gauges'] = dict(
        passed=not failed, station_count=len(expected_files), samples_per_station=181,
        total_native_time_samples=samples, columns=['eta', 'qx', 'qy_south'],
        max_abs_error=max_error.tolist(), max_error_over_tolerance=max_scaled.tolist(),
        reference_abs_max=max_reference.tolist(), failed_station_count=len(failed),
        failed_stations=failed[:20])
    result['passed'] &= result['gauges']['passed']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/hirota_inputs')
    parser.add_argument('--exe', type=Path, default=ROOT / 'build/gnu/jagurs')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/mpi_edges')
    parser.add_argument('--mpiexec', default='mpiexec')
    parser.add_argument('--mpi-args', default='')
    parser.add_argument('--cores', default=None)
    parser.add_argument('--threads', type=int, default=1)
    args = parser.parse_args()
    args.exe = args.exe.resolve()
    args.work = args.work.resolve()
    # Dense coastal station clusters can put more than 1024 open gauge files on
    # one rank when testing skinny decompositions. Retain every station and raise
    # only this launcher's inherited soft descriptor limit, within its hard limit.
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    required_limit = 8192
    if soft_limit < required_limit:
        if hard_limit != resource.RLIM_INFINITY and hard_limit < required_limit:
            raise ValueError('This full-station check needs RLIMIT_NOFILE >= 8192')
        resource.setrlimit(resource.RLIMIT_NOFILE, (required_limit, hard_limit))
    bench.validate_work(args.work, bench.manifest())
    output = bench.new_directory(args.output)
    record = dict(
        scope='CPU non-dispersive full-geometry 18 s MPI decomposition check',
        reference='V0702 patched 2x2, same executable and frozen real input',
        note='This tests decomposition invariance; historical and analytic correctness are separate checks.',
        executable_sha256=bench.sha(args.exe),
        open_file_soft_limit=resource.getrlimit(resource.RLIMIT_NOFILE)[0],
        dataset_manifest_sha256=bench.sha(HERE.parent / 'dataset_manifest.json'),
        duration_s=18, output_times_s=[9, 18], gauge_interval_s=.1,
        atol=bench.FIELD_ATOL, rtol=bench.RTOL, runs={}, comparisons={}, passed=True)
    for procx, procy in ((2, 2), (1, 4), (4, 1)):
        name = f'{procx}x{procy}'
        run_dir = bench.new_directory(output / name)
        bench.stage(args.work, run_dir, procx, procy)
        par = (run_dir / 'tsun.par').read_text()
        for key, value in [('tend', 18), ('itmap', 90), ('itmap_start', 90),
                           ('itmap_end', 180), ('plotgrd', -1)]:
            par = bench.replace_parameter(par, key, value)
        (run_dir / 'tsun.par').write_text(par)
        result = bench.mpi_run(run_dir, args.exe, args, ranks=4)
        record['runs'][name] = result
        print(f'{name}: exit={result["returncode"]}, wall={result["wall_s"]:.3f} s', flush=True)
        if result['returncode']:
            raise RuntimeError(f'MPI run failed: {run_dir}')
        comparison = compare_layout(run_dir, output / '2x2')
        record['comparisons'][name] = comparison
        record['passed'] &= comparison['passed']
        bench.save(output / 'report.json', record)
        print(f'{name}: comparison passed={comparison["passed"]}', flush=True)
    bench.save(output / 'report.json', record)
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
