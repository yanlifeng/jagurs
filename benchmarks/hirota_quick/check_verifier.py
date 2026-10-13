#!/usr/bin/env python3
"""Confirm that the real-case verifier rejects four deliberate mistakes.

Use an already passing run. Only selected input/output files are linked into
temporary directories; each corrupted file is replaced by a private copy.
No simulation is launched and the original run is never written to.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil
import tempfile
import time

import numpy as np
from netCDF4 import Dataset


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('hirota_verifier', HERE / 'run.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def private_copy(directory, name):
    """Break the temporary symlink before making any change."""
    target = directory / name
    original = target.resolve(strict=True)
    if not target.is_symlink():
        raise ValueError(f'Expected a temporary symlink: {target}')
    target.unlink()
    shutil.copyfile(original, target)
    if target.is_symlink():
        raise ValueError(f'Private copy is still a symlink: {target}')
    return target


def corrupt_eta(directory, field, wet_index):
    target = private_copy(directory, field)
    with Dataset(target, 'r+') as dataset:
        values = np.asarray(dataset['z'][:]).copy()
        old_value = float(values.flat[wet_index])
        values.flat[wet_index] += 1.0
        dataset['z'][:] = values
    return dict(file=field, flat_index=wet_index, original_eta_m=old_value,
                deliberately_added_m=1.0)


def reverse_qy(directory, field):
    target = private_copy(directory, field)
    with Dataset(target, 'r+') as dataset:
        values = np.asarray(dataset['z'][:])
        dataset['z'][:] = -values
    return dict(file=field, deliberately_multiplied_by=-1)


def omit_native_sample(directory, gauge):
    target = private_copy(directory, gauge)
    lines = target.read_text().splitlines(keepends=True)
    removed = []
    kept = []
    for line in lines:
        match = VERIFIER.HISTORY_RE.search(line)
        if match and abs(float(match.group(1).replace('D', 'E')) - .2) < 1e-9:
            removed.append(line)
        else:
            kept.append(line)
    if len(removed) != 1:
        raise ValueError(f'Negative-control setup expected one t=0.2 s row: {gauge}')
    target.write_text(''.join(kept))
    return dict(file=gauge, deliberately_removed_native_time_s=.2,
                note='This native sample is not part of the 1 Hz frozen reference.')


def change_friction(directory):
    target = private_copy(directory, 'tsun.par')
    original = target.read_text()
    modified = VERIFIER.replace_parameter(original, 'cf', '-.03')
    if original == modified:
        raise ValueError('Negative-control setup did not change ocean friction')
    target.write_text(modified)
    return dict(file='tsun.par', deliberately_changed_parameter='cf',
                changed_value=-.03)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='Existing successful real-case run, read-only')
    parser.add_argument('--report', type=Path, required=True,
                        help='New JSON file outside the original run directory')
    args = parser.parse_args()
    output, report_path = args.output.resolve(), args.report.resolve()
    if report_path == output or output in report_path.parents:
        parser.error('--report must be outside the original run directory')
    if report_path.exists():
        parser.error('--report already exists; choose a new file')
    baseline_report = output / 'report.json'
    baseline = json.loads(baseline_report.read_text())
    if not baseline.get('passed'):
        parser.error('The original report.json must already have passed=true')
    record = VERIFIER.manifest()
    if baseline.get('dataset_manifest_sha256') != VERIFIER.sha(HERE / 'dataset_manifest.json'):
        parser.error('The original run used a different frozen dataset manifest')
    with np.load(VERIFIER.DATA / 'reference_gauges.npz') as refs:
        gauge_names = [f'tgs{int(sid):06d}' for sid in refs['station_ids']]
    with np.load(VERIFIER.DATA / 'reference_fields.npz') as refs:
        eta = refs['eta_raw'].astype(float)
        water = eta + refs['depth_raw'].astype(float)
        if not np.any(water > .1):
            raise ValueError('No unambiguously wet reference node for the negative control')
        wet_index = int(np.argmax(np.where(water > .1, np.abs(eta), -1.)))
    field_names = {name: f'SD03.{name}.00018000.grd'
                   for name in VERIFIER.FIELD_ATOL}
    needed = set(record['fixed_input_sha256']) | set(gauge_names) | set(field_names.values())
    needed.update(('tsun.par', 'gridfile.dat'))
    for grid in range(1, 4):
        needed.update((f'forcing{grid}', f'disp{grid}.list'))

    # Check the original bytes of every file that a control will privately edit.
    originals = [field_names['eta_raw'], field_names['qy_south_raw'], gauge_names[0], 'tsun.par']
    original_hashes = {name: VERIFIER.sha(output / name) for name in originals}
    tests = [
        ('water_level_plus_1m',
         lambda directory: corrupt_eta(directory, field_names['eta_raw'], wet_index),
         'eta_raw', None),
        ('southward_flux_sign_reversal',
         lambda directory: reverse_qy(directory, field_names['qy_south_raw']),
         'qy_south_raw', None),
        ('missing_native_0_2s_sample',
         lambda directory: omit_native_sample(directory, gauge_names[0]),
         None, 'Missing or shifted native gauge sample'),
        ('changed_ocean_friction', change_friction,
         None, 'Simulation namelist changed beyond procx/procy'),
    ]
    started = time.monotonic()
    results = {}
    for name, mutation, failed_field, expected_error in tests:
        test_started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='jagurs-verifier-control-') as temporary:
            directory = Path(temporary)
            for filename in sorted(needed):
                source = output / filename
                (directory / filename).symlink_to(source.resolve(strict=True),
                                                  target_is_directory=source.is_dir())
            result = dict(mutation=mutation(directory))
            try:
                verification = VERIFIER.verify(directory)
            except ValueError as error:
                if expected_error is None or expected_error not in str(error):
                    raise  # An unrelated exception is not a successful control.
                result.update(passed=True, rejection='expected ValueError',
                              reason=str(error))
            else:
                field_result = verification['fields'].get(failed_field) if failed_field else None
                rejected = (expected_error is None and not verification['passed']
                            and field_result is not None and not field_result['passed'])
                result.update(passed=bool(rejected), rejection='field mismatch' if rejected else 'not rejected as expected',
                              verification_passed=verification['passed'])
                if field_result is not None:
                    result['field_comparison'] = field_result
            result['wall_s'] = time.monotonic() - test_started
            results[name] = result
    unchanged = all(VERIFIER.sha(output / name) == digest
                    for name, digest in original_hashes.items())
    report = dict(passed=unchanged and all(result['passed'] for result in results.values()),
                  original_run=str(output), baseline_report_sha256=VERIFIER.sha(baseline_report),
                  verifier_sha256=VERIFIER.sha(HERE / 'run.py'),
                  original_files_unchanged=unchanged, original_file_sha256=original_hashes,
                  negative_controls=results, wall_s=time.monotonic() - started,
                  scope='Checks that the actual frozen-case verifier rejects meaningful numerical, time-axis and physical-input errors. No simulation or original output was modified.')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    VERIFIER.save(report_path, report)
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
