#!/usr/bin/env python3
"""Re-run the archived Hirota parent without modifying historical evidence.

The full archive is required: the portable quick fixture does not include the
10 m sECOM geometry. Run each stage separately; existing runs are immutable.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import gzip

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = Path('/home/user_home/ylf/disaster-chain-real-20261002')
PARENT_NAME = 'root_tohoku_north_geoprecise_coherent_10m_parent'
OLD_PARENT = ARCHIVE / 'tsunami' / PARENT_NAME
NEW_PARENT = REPO / 'runs/full_chain_parent'
EXE = REPO / 'build/gnu/jagurs'
NEW_PACKET = REPO / 'runs/full_chain_packet_10m'
NEW_CHILD = REPO / 'runs/full_chain_child_10m'
NEW_SHORT = REPO / 'runs/full_chain_child_10m_prefix100'
OLD_CHILD = ARCHIVE / 'inundation/agent_hirota10_yamazaki2018_geoprecise_coherent_riemann_v3_viscex_v1b'
CHILD_BUILD = ARCHIVE / 'inundation/agent_build_hirota_978x1094_viscex_v1b'
OLD_SHORT = ARCHIVE / 'inundation/agent_hirota10_viscex_v1b_prefix100_omp32'
PHYSICAL = ['run_data.txt', 'model_grid.nc', 'run_data_bc_elev.nc',
            'bfric2d.inp', 'initial_eta.bin', 'initial_velocity.bin',
            'boundary_riemann.bin', 'terrain.npz', 'observations_locked.json']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n')


def archived_modules():
    sys.path.insert(0, str(ARCHIVE / 'scripts'))


def configure_archive(path):
    global ARCHIVE, OLD_PARENT, OLD_CHILD, CHILD_BUILD, OLD_SHORT
    ARCHIVE = Path(path).resolve()
    OLD_PARENT = ARCHIVE/'tsunami'/PARENT_NAME
    OLD_CHILD = ARCHIVE/'inundation/agent_hirota10_yamazaki2018_geoprecise_coherent_riemann_v3_viscex_v1b'
    CHILD_BUILD = ARCHIVE/'inundation/agent_build_hirota_978x1094_viscex_v1b'
    OLD_SHORT = ARCHIVE/'inundation/agent_hirota10_viscex_v1b_prefix100_omp32'


def prepare():
    NEW_PARENT.mkdir(parents=True, exist_ok=False)
    names = ['tsun.par', 'gridfile.dat', 'stations.txt', 'station_mapping.json',
             'coastal_receiver_mapping.json', 'highrate_sampling_request.json']
    names += [f'{stem}{k}.{ext}' for k in range(1, 4)
              for stem, ext in [('bathy', 'grd'), ('post_bathy', 'grd'),
                                ('bed_final', 'grd'), ('bed_components', 'npz'),
                                ('disp', 'list')]]
    for name in names:
        shutil.copy2(OLD_PARENT / name, NEW_PARENT / name)
    inputs = {n: sha(NEW_PARENT / n) for n in names}
    assert all(sha(OLD_PARENT / n) == h for n, h in inputs.items())
    forcing = []
    for k in range(1, 4):
        frames = (NEW_PARENT / f'disp{k}.list').read_text().splitlines()
        assert len(frames) == 182
        forcing.extend(dict(grid=k, file=f, sha256=sha(f)) for f in frames)
    meta = json.loads((OLD_PARENT / 'case.json').read_text())
    meta.update(name=NEW_PARENT.name, parent_case=str(OLD_PARENT),
                executable=str(EXE), mpi_cores='16-31', mpi_ranks=16,
                station_unique_nodes=int((NEW_PARENT / 'stations.txt').read_text().splitlines()[0]),
                version_migration='Official V0702 with retained chain fixes',
                reproduction_scope='Complete 10861 s parent; same frozen physical inputs and output schedule')
    save(NEW_PARENT / 'case.json', meta)
    contract = json.loads((OLD_PARENT / 'input_contract.json').read_text())
    contract.update(frozen_before_outputs_utc=datetime.now(timezone.utc).isoformat(),
                    physical_input_sha256=inputs, executable_sha256=sha(EXE),
                    build_manifest=str(EXE.parent / 'build.json'),
                    source_frames=forcing, original_parent=str(OLD_PARENT),
                    reproducibility_certified=False)
    save(NEW_PARENT / 'input_contract.json', contract)
    save(HERE / 'full_parent_input_identity.json', dict(
        original=str(OLD_PARENT), candidate=str(NEW_PARENT),
        original_version='V0701 with chain fixes', candidate_version='V0702 with chain fixes',
        all_input_files_byte_identical=True, physical_input_sha256=inputs,
        source_frame_count=len(forcing), actual_station_count=meta['station_unique_nodes'],
        original_case_metadata_stale_station_count=4302,
        executable_sha256=sha(EXE), physical_duration_s=10861,
        source_clock_dt_s=[.9, .3, .1], mpi_decomposition=[4, 4]))
    print('PREPARED', NEW_PARENT, flush=True)


def run_parent():
    assert not (NEW_PARENT / 'run.log').exists(), 'Existing execution is immutable'
    contract = json.loads((NEW_PARENT / 'input_contract.json').read_text())
    assert sha(EXE) == contract['executable_sha256']
    for n, h in contract['physical_input_sha256'].items():
        assert sha(NEW_PARENT / n) == h
    env = dict(os.environ, OMP_NUM_THREADS='1', OMP_DYNAMIC='FALSE',
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', MKL_DYNAMIC='FALSE',
               MKL_CBWR='COMPATIBLE', I_MPI_PIN='1',
               I_MPI_PIN_PROCESSOR_LIST=','.join(map(str, range(16, 32))))
    env['LD_LIBRARY_PATH'] = str(ARCHIVE.parent / 'tsunami-jagurs-20260915/deps/lib') + ':' + env.get('LD_LIBRARY_PATH', '')
    cmd = ['mpirun', '-np', '16', str(EXE), 'par=tsun.par']
    save(NEW_PARENT / 'execution_contract.json', dict(
        start_utc=datetime.now(timezone.utc).isoformat(), command=cmd,
        executable_sha256=sha(EXE),
        environment={k: env[k] for k in ['OMP_NUM_THREADS', 'OMP_DYNAMIC',
            'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'MKL_DYNAMIC',
            'MKL_CBWR', 'I_MPI_PIN', 'I_MPI_PIN_PROCESSOR_LIST']},
        dynamic_libraries=subprocess.check_output(['ldd', str(EXE)], text=True),
        mpi_version=subprocess.check_output(['mpirun', '-version'], text=True)))
    start = time.perf_counter()
    with (NEW_PARENT / 'run.log').open('x') as log:
        result = subprocess.run(cmd, cwd=NEW_PARENT, env=env, stdout=log,
            stderr=subprocess.STDOUT,
            preexec_fn=lambda: os.sched_setaffinity(0, set(range(16, 32))))
    report = dict(returncode=result.returncode, wall_s=time.perf_counter()-start,
                  command=cmd, executable_sha256=sha(EXE))
    save(NEW_PARENT / 'run.json', report)
    save(HERE / 'full_parent_execution.json', report)
    assert result.returncode == 0, report
    archived_modules()
    import root_hirota_coherent_parent as original_driver
    original_driver.CASE = NEW_PARENT
    original_driver.post_depth()
    print('COMPLETE_PARENT_AND_POST_DEPTH', report, flush=True)


def require_parent():
    assert json.loads((NEW_PARENT / 'run.json').read_text())['returncode'] == 0
    assert json.loads((NEW_PARENT / 'actual_coordinate_axis_gate.json').read_text())['pass_gate']


def compare_npz(old, new):
    import numpy as np
    with np.load(old) as a, np.load(new) as b:
        assert set(a.files) == set(b.files)
        rows = {}
        for key in a.files:
            x, y = a[key], b[key]
            equal = x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes()
            row = dict(dtype=str(x.dtype), shape=list(x.shape), equal=equal)
            if x.dtype.kind in 'fiu' and x.shape == y.shape:
                row['max_abs_difference'] = float(np.max(np.abs(x.astype(float)-y.astype(float)))) if x.size else 0.
            rows[key] = row
    return dict(all_arrays_bit_identical=all(r['equal'] for r in rows.values()), arrays=rows)


def field_pair(name):
    from netCDF4 import Dataset
    import numpy as np
    a, b = OLD_PARENT/name, NEW_PARENT/name
    ha, hb = sha(a), sha(b)
    result = dict(file=name, original_sha256=ha, candidate_sha256=hb,
                  bytes=a.stat().st_size, byte_identical=ha == hb)
    with Dataset(a) as ds:
        finite = all(np.isfinite(np.asarray(v[:])).all()
                     for v in ds.variables.values() if np.dtype(v.dtype).kind in 'fiu')
    assert finite, ('Nonfinite archived physical field', name)
    result['finite'] = True
    if ha != hb:
        rows = {}
        with Dataset(a) as x, Dataset(b) as y:
            if set(x.variables) != set(y.variables):
                result.update(physical_arrays_equal=False, error='Variable set changed')
                return result
            for key in x.variables:
                u, v = np.asarray(x[key][:]), np.asarray(y[key][:])
                if v.dtype.kind in 'fiu':
                    assert np.isfinite(v).all(), ('Nonfinite candidate physical field', name, key)
                eq = u.dtype == v.dtype and u.shape == v.shape and u.tobytes() == v.tobytes()
                rows[key] = dict(equal=eq)
                if u.dtype.kind in 'fiu' and u.shape == v.shape:
                    rows[key]['maximum_absolute_difference'] = float(abs(u.astype(float)-v.astype(float)).max())
        result.update(physical_arrays_equal=all(r['equal'] for r in rows.values()), variables=rows)
    else:
        result['physical_arrays_equal'] = True
    return result


def compare_fields():
    """Every SD03 raw field, three-grid source-filter frames and saved maxima."""
    require_parent()
    contract = json.loads((NEW_PARENT/'input_contract.json').read_text())
    assert sha(EXE) == contract['executable_sha256']
    assert all(sha(NEW_PARENT/n) == h for n,h in contract['physical_input_sha256'].items())
    assert all(sha(row['file']) == row['sha256'] for row in contract['source_frames'])
    def selected(p):
        return bool(
        (re.fullmatch(r'SD03\.(eta_raw|depth_raw|qx_raw|qy_south_raw)\.\d{8}\.grd', p.name)
         or re.fullmatch(r'SD0[123]\.(zmax|vmax)\.grd', p.name)
         or re.fullmatch(r'SD0[123]\.initl_disp\d+\.grd', p.name)))
    names = sorted(p.name for p in OLD_PARENT.iterdir() if selected(p))
    new_names = sorted(p.name for p in NEW_PARENT.iterdir() if selected(p))
    assert names == new_names, 'New and archived field file sets differ'
    assert len([n for n in names if '.eta_raw.' in n]) == 10504
    expected_steps = [3599, 3601] + list(range(3600, 108611, 10))
    for field in ['eta_raw', 'depth_raw', 'qx_raw', 'qy_south_raw']:
        assert sorted(n for n in names if f'.{field}.' in n) == sorted(
            f'SD03.{field}.{step:08d}.grd' for step in expected_steps)
    for grid in range(1,4):
        assert sum(n.startswith(f'SD{grid:02d}.initl_disp') for n in names) == 182
    assert all((NEW_PARENT/n).exists() for n in names)
    counts, mismatches = {}, []
    byte_same = arrays_same = total_bytes = 0
    start = time.perf_counter()
    # netCDF C libraries are not thread safe; process workers isolate handles.
    detail = HERE / 'full_field_comparison.jsonl.gz'
    with gzip.open(detail, 'wt') as log, ProcessPoolExecutor(max_workers=4) as pool:
        for i, row in enumerate(pool.map(field_pair, names, chunksize=20), 1):
            log.write(json.dumps(row)+'\n')
            group = row['file'].split('.')[1]
            if group.startswith('initl_disp'): group = 'initl_disp'
            counts[group] = counts.get(group, 0)+1
            byte_same += row['byte_identical']
            arrays_same += row['physical_arrays_equal']
            total_bytes += row['bytes']
            if not row['physical_arrays_equal'] and len(mismatches) < 30:
                mismatches.append(row)
            if i % 4000 == 0: print('FIELD_COMPARE', i, len(names), flush=True)
    clock = lambda p: re.findall(r'Computing rupture effects: time_step=(\d+).*?ig=(\d+) irupt=(\d+)', (p/'stdout.000000').read_text())
    old_clock, new_clock = clock(OLD_PARENT), clock(NEW_PARENT)
    expected_clock = [(str(step),str(grid),str((step-1)//9+1))
                      for step in range(1,1639) for grid in range(1,4)]
    assert old_clock == expected_clock and new_clock == expected_clock, 'Missing/changed rupture step/frame sequence'
    depth = compare_npz(OLD_PARENT/'coastal_post_depth_exact.npz', NEW_PARENT/'coastal_post_depth_exact.npz')
    report = dict(original=str(OLD_PARENT), candidate=str(NEW_PARENT),
        file_count=len(names), counts=counts, byte_identical_files=byte_same,
        new_and_archived_file_sets_equal=True, all_field_numeric_variables_finite=True,
        candidate_inputs_and_source_frames_unchanged_after_run=True,
        raw_snapshot_time_coverage_exact=True,
        physical_arrays_identical_files=arrays_same, total_original_bytes=total_bytes,
        all_physical_fields_bit_identical=arrays_same == len(names),
        source_clock_records=len(old_clock), source_clock_exact=old_clock == new_clock,
        exact_post_depth=depth, differing_fields=mismatches,
        full_detail=detail.name, full_detail_sha256=sha(detail), wall_s=time.perf_counter()-start)
    save(HERE/'full_parent_fields_comparison.json', report)
    print('FIELD_COMPARISON_COMPLETE', json.dumps({k:v for k,v in report.items() if k not in ['exact_post_depth','differing_fields']}), flush=True)


def gauge_pair(name):
    import numpy as np
    a, b = OLD_PARENT/name, NEW_PARENT/name
    ha, hb = sha(a), sha(b)
    result = dict(file=name, original_sha256=ha, candidate_sha256=hb,
                  byte_identical=ha == hb)
    def read(path):
        s = path.read_text().split('\n', 1)[1]
        for token in ['step=', 't=', 'hz=', 'fx=', 'fy=']:
            s = s.replace(token, ' ')
        x = np.fromstring(s.replace('D', 'E'), sep=' ').reshape(-1, 5)
        assert np.isfinite(x).all()
        return x
    x = read(a)
    y = x if ha == hb else read(b)
    expected_steps = np.arange(1,108612)
    for label, data in [('reference', x), ('candidate', y)]:
        assert len(data) == len(expected_steps), (name, label, 'Incomplete samples')
        assert np.array_equal(data[:,0], expected_steps), (name, label, 'Step sequence changed')
        assert np.max(abs(data[:,1]-expected_steps*.1)) < 1e-8, (name, label, 'Time axis changed')
    result['shape_equal'] = x.shape == y.shape
    if x.shape != y.shape:
        result.update(numerically_equal=False, time_exact=False)
        return result
    delta = y[:, 2:]-x[:, 2:]
    result.update(numerically_equal=np.array_equal(x, y),
                  time_exact=np.array_equal(x[:, :2], y[:, :2]),
                  samples=len(x), first_s=float(y[0,1]), last_s=float(y[-1,1]),
                  finite=True, complete_time_coverage=True,
                  max_absolute_difference=np.max(abs(delta), axis=0).tolist(),
                  squared_difference=np.sum(delta*delta, axis=0).tolist(),
                  squared_reference=np.sum(x[:,2:]**2, axis=0).tolist(),
                  changed_samples=np.count_nonzero(delta, axis=0).tolist())
    return result


def compare_gauges():
    import numpy as np
    require_parent()
    names = sorted(p.name for p in OLD_PARENT.glob('tgs[0-9][0-9][0-9][0-9][0-9][0-9]'))
    assert names == sorted(p.name for p in NEW_PARENT.glob('tgs[0-9][0-9][0-9][0-9][0-9][0-9]')), 'Gauge file sets changed'
    assert len(names) == int((OLD_PARENT/'stations.txt').read_text().splitlines()[0]) == 2482
    start = time.perf_counter()
    byte_same = numeric_same = time_same = 0
    maximum = np.zeros(3)
    changed = np.zeros(3, dtype=np.int64)
    examples = []
    detail = HERE/'full_gauge_comparison.jsonl.gz'
    with gzip.open(detail, 'wt') as log, ProcessPoolExecutor(max_workers=4) as pool:
        for i, row in enumerate(pool.map(gauge_pair, names, chunksize=4), 1):
            log.write(json.dumps(row)+'\n')
            byte_same += row['byte_identical']; numeric_same += row['numerically_equal']; time_same += row['time_exact']
            if 'max_absolute_difference' in row:
                maximum = np.maximum(maximum, row['max_absolute_difference'])
            changed += row.get('changed_samples', [0,0,0])
            if not row['numerically_equal'] and len(examples)<5: examples.append(row)
            if i % 200 == 0: print('GAUGE_COMPARE', i, len(names), 'max_eta_qx_qy', maximum.tolist(), flush=True)
    report = dict(original=str(OLD_PARENT), candidate=str(NEW_PARENT),
        station_count=len(names), byte_identical_files=byte_same, numerically_identical_files=numeric_same,
        new_and_archived_file_sets_equal=True, all_values_finite=True,
        samples_per_station=108611, first_s=.1, last_s=10861.1,
        complete_native_step_time_coverage=True,
        exact_time_and_step_files=time_same, all_time_and_steps_exact=time_same == len(names),
        all_native_records_numerically_identical=numeric_same == len(names),
        maximum_absolute_eta_qx_qy_difference=maximum.tolist(), changed_eta_qx_qy_samples=changed.tolist(),
        additional_roundoff_gate_absolute_eta_qx_qy=[1e-9, 1e-8, 1e-8],
        additional_roundoff_gate_passed=bool(np.all(maximum <= np.array([1e-9,1e-8,1e-8]))),
        note='No tolerance declares downstream equivalence. Reconstructed float32 sECOM input equality is checked separately.',
        examples=examples, full_detail=detail.name, full_detail_sha256=sha(detail), wall_s=time.perf_counter()-start)
    save(HERE/'full_parent_gauge_comparison.json', report)
    print('GAUGE_COMPARISON_COMPLETE', json.dumps({k:v for k,v in report.items() if k != 'examples'}), flush=True)


def rebuild_child():
    require_parent()
    archived_modules()
    import inundation_hirota_geoprecise as geo
    geo.PARENT = NEW_PARENT
    geo.configure(10)
    body = geo.body
    body.OUT, body.CASE, body.BUILD = NEW_PACKET, NEW_CHILD, CHILD_BUILD
    NEW_PACKET.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    geo.coordinate_gate()
    print('RECONSTRUCT_INITIAL', flush=True); body.state()
    print('EXTRACT_FULL_BOUNDARY_HISTORY', flush=True); body.extract()
    print('GATE_FULL_BOUNDARY', flush=True); body.gate()
    print('ASSEMBLE_NATIVE_VELOCITY', flush=True); body.assemble(10801)
    print('WRITE_SECOM_INPUTS', flush=True); body.prepare_case()
    for suffix in ['', '_rest30', '_prefix2100']:
        path = NEW_CHILD.with_name(NEW_CHILD.name+suffix)/'case.json'
        meta = json.loads(path.read_text())
        meta.update(coordinate_interface_version=4,
                    coordinate_contract=str(NEW_PACKET/'coordinate_contract.json'),
                    coordinate_contract_sha256=sha(NEW_PACKET/'coordinate_contract.json'),
                    parent_grid_coordinates='Double precision source/input/raw coordinate contract',
                    viscosity_integration_version='v1b',
                    requested_build=str(CHILD_BUILD))
        save(path, meta)
    save(HERE/'child_reconstruction.json', dict(
        original_child=str(OLD_CHILD), candidate_child=str(NEW_CHILD),
        candidate_parent=str(NEW_PARENT), candidate_packet=str(NEW_PACKET),
        converter_scripts={p.name:sha(p) for p in (ARCHIVE/'scripts').glob('inundation_hirota*.py')},
        unchanged_child_executable=str(CHILD_BUILD/'s--pom.x'),
        unchanged_child_executable_sha256=sha(CHILD_BUILD/'s--pom.x'),
        input_window_global_s=[360,10801], child_simulation_window_s=[360,10800],
        wall_s=time.perf_counter()-start))
    print('RECONSTRUCT_COMPLETE', flush=True)


def compare_child():
    rows = {}
    old_execution = json.loads((OLD_CHILD/'execution.json').read_text())
    assert old_execution['status'] == 'completed' and old_execution['exit_code'] == 0
    assert abs(old_execution['final_local_time_s']-10440) < .001
    numerical = json.loads((OLD_CHILD/'numerical_validation.json').read_text())
    assert numerical['completed'] and numerical['numerical_checks_pass']
    history = json.loads((OLD_CHILD/'historical_acceptance.json').read_text())
    assert history['primary_I_project_target_pass']
    old_nc = sorted(p.name for p in OLD_CHILD.glob('*.nc'))
    new_nc = sorted(p.name for p in NEW_CHILD.glob('*.nc'))
    assert old_nc == new_nc, 'NetCDF input file sets changed'
    names = sorted(set(PHYSICAL + old_nc))
    for name in names:
        a, b = OLD_CHILD/name, NEW_CHILD/name
        ha, hb = sha(a), sha(b)
        if name in PHYSICAL:
            assert ha == old_execution['physical_inputs_sha256'][name], ('Archived physical input modified', name)
        row = dict(original_sha256=ha, candidate_sha256=hb, byte_identical=ha==hb,
                   bytes=a.stat().st_size,
                   historical_execution_hash_available=name in PHYSICAL)
        if ha != hb and name.endswith('.npz'):
            row['array_comparison'] = compare_npz(a,b)
            row['physical_arrays_equal'] = row['array_comparison']['all_arrays_bit_identical']
        elif ha != hb and name.endswith('.nc'):
            from netCDF4 import Dataset
            import numpy as np
            with Dataset(a) as x, Dataset(b) as y:
                equal = set(x.variables) == set(y.variables)
                arrays = {}
                for key in x.variables:
                    u, v = np.asarray(x[key][:]), np.asarray(y[key][:])
                    eq = u.dtype==v.dtype and u.shape==v.shape and u.tobytes()==v.tobytes()
                    arrays[key] = dict(equal=eq, dtype=str(u.dtype), shape=list(u.shape))
                    equal &= eq
            row.update(physical_arrays_equal=False, diagnostic_variable_arrays_equal=bool(equal), variables=arrays,
                       policy='Strict NetCDF byte identity required; variable values alone do not establish units, dimensions or attribute identity.')
        else:
            row['physical_arrays_equal'] = ha==hb
        rows[name]=row
    report = dict(original_child=str(OLD_CHILD), candidate_child=str(NEW_CHILD),
        all_nine_files_byte_identical=all(rows[n]['byte_identical'] for n in PHYSICAL),
        all_nine_physical_inputs_bit_identical=all(rows[n]['physical_arrays_equal'] for n in PHYSICAL),
        auxiliary_netcdf_files=[n for n in names if n not in PHYSICAL],
        all_netcdf_input_file_sets_equal=True,
        all_fifteen_input_files_byte_identical=all(r['byte_identical'] for r in rows.values()),
        all_fifteen_physical_inputs_bit_identical=all(r['physical_arrays_equal'] for r in rows.values()),
        files=rows, historical_inputs_still_match_execution_record=True,
        historical_full_execution_complete=True,
        historical_full_numerical_checks_pass=True,
        historical_project_I_target_pass=True,
        historical_evidence_sha256={n:sha(OLD_CHILD/n) for n in
            ['execution.json','numerical_validation.json','historical_acceptance.json']},
        executable_sha256=sha(CHILD_BUILD/'s--pom.x'),
        child_executable_matches_historical=sha(CHILD_BUILD/'s--pom.x')==old_execution['executable_sha256'],
        excluded_metadata='case.json contains new paths/provenance; it is not a solver physics input.')
    save(HERE/'child_physical_input_comparison.json', report)
    print('CHILD_INPUTS', json.dumps({k:v for k,v in report.items() if k != 'files'}), flush=True)


def run_short_child():
    report = json.loads((HERE/'child_physical_input_comparison.json').read_text())
    assert report['all_fifteen_physical_inputs_bit_identical'], 'Changed downstream input requires full 10440 s child validation'
    assert report['child_executable_matches_historical']
    archived_modules()
    from inundation_hirota_pipeline import clone
    from inundation_hirota_execute import run
    clone(NEW_CHILD, NEW_SHORT, 'prefix', 100)
    previous = json.loads((OLD_SHORT/'execution.json').read_text())
    assert previous['status'] == 'completed' and previous['pipeline_only']
    assert abs(previous['final_local_time_s']-100) < .001
    assert previous['executable_sha256'] == report['executable_sha256']
    assert previous['threads'] == 32 and previous['cpu'] == '64-95'
    full_previous = json.loads((OLD_CHILD/'execution.json').read_text())
    assert full_previous['threads'] == 32 and full_previous['cpu'] == '64-95'
    names = sorted(set(PHYSICAL+[p.name for p in OLD_SHORT.glob('*.nc')]))
    previous_identity = {}
    for name in names:
        old_hash, new_hash = sha(OLD_SHORT/name), sha(NEW_SHORT/name)
        if name in PHYSICAL:
            assert old_hash == previous['physical_inputs_sha256'][name], ('Archived short input modified', name)
        assert old_hash == new_hash, ('New and old short physical inputs differ', name)
        if name != 'run_data.txt':
            assert old_hash == sha(OLD_CHILD/name), ('Short baseline not from historical full input', name)
        previous_identity[name] = dict(original_short_sha256=old_hash,
                                      candidate_short_sha256=new_hash,
                                      matches_historical_full_except_duration=True)
    child_library_path = str(ARCHIVE.parent/'tsunami-jagurs-20260915/deps/lib')+':'+os.environ.get('LD_LIBRARY_PATH','')
    ldd = subprocess.check_output(['ldd', str(CHILD_BUILD/'s--pom.x')], text=True,
                                 env=dict(os.environ, LD_LIBRARY_PATH=child_library_path))
    assert 'not found' not in ldd, ldd
    libs = sorted(set(re.findall(r'(?:=>\s+|^\s*)(/\S+)', ldd, flags=re.M)))
    runtime = dict(cpu='64-95', threads=32,
        configured_environment=dict(OMP_NUM_THREADS='32', OMP_STACKSIZE='256M',
            OMP_PROC_BIND='true', OMP_PLACES='cores', OPENBLAS_NUM_THREADS='1',
            LD_LIBRARY_PATH=child_library_path),
        same_cpu_threads_as_old_short_and_full=True,
        unchanged_execution_driver_sha256=sha(ARCHIVE/'scripts/inundation_hirota_execute.py'),
        ldd=ldd, current_dynamic_library_sha256={p:sha(p) for p in libs},
        historical_dynamic_library_hashes_available=False,
        environment_evidence='Same archived execution wrapper explicitly sets these OpenMP variables, same CPU/threads and executable; historical dynamic-library hashes were not recorded. Seven exact output comparisons provide the new runtime regression evidence.')
    save(HERE/'child_100s_runtime_contract.json', runtime)
    run(NEW_SHORT, CHILD_BUILD/'s--pom.x', '64-95', 32, pipeline_only=True)
    assert all(sha(p)==h for p,h in runtime['current_dynamic_library_sha256'].items())
    names = ['chain_max.bin', 'chain_snapshots.bin', 'chain_metrics.csv',
             'mass_audit.csv', 'depth_audit.csv', 'closure_audit.csv', 'riemann_flux_audit.csv']
    rows = {n:dict(original_sha256=sha(OLD_SHORT/n), candidate_sha256=sha(NEW_SHORT/n)) for n in names}
    for row in rows.values(): row['byte_identical'] = row['original_sha256']==row['candidate_sha256']
    result = dict(actual_new_child_duration_s=100, original=str(OLD_SHORT), candidate=str(NEW_SHORT),
        all_seven_outputs_byte_identical=all(r['byte_identical'] for r in rows.values()), files=rows,
        execution=json.loads((NEW_SHORT/'execution.json').read_text()),
        validation=json.loads((NEW_SHORT/'pipeline_validation.json').read_text()),
        short_input_identity=previous_identity,
        original_short_execution_status=previous['status'],
        runtime_contract='child_100s_runtime_contract.json',
        runtime_contract_sha256=sha(HERE/'child_100s_runtime_contract.json'),
        dynamic_libraries_unchanged_during_new_run=True,
        complete_child_10440_s_recomputed=False,
        complete_child_equivalence_basis='All nine core reconstructed physical inputs and all six auxiliary NetCDF inputs exactly equal the completed historical archive; same unchanged executable. A fresh 100 s integration additionally checks the coupling and runtime environment. Historical execution froze core nine hashes; auxiliary NetCDF files are compared to their retained current archive.')
    save(HERE/'child_100s_execution_and_comparison.json', result)
    assert result['all_seven_outputs_byte_identical'], result
    print('SHORT_CHILD_COMPLETE_AND_IDENTICAL', flush=True)


def summarize():
    names = ['full_parent_input_identity.json', 'full_parent_execution.json',
             'full_parent_fields_comparison.json', 'full_parent_gauge_comparison.json',
             'child_reconstruction.json', 'child_physical_input_comparison.json',
             'child_100s_runtime_contract.json', 'child_100s_execution_and_comparison.json']
    reports = {n:json.loads((HERE/n).read_text()) for n in names}
    retained_records = [('tsun.par','full_parent_tsun.par'),
        ('gridfile.dat','full_parent_gridfile.dat'),
        ('input_contract.json','full_parent_input_contract.json'),
        ('execution_contract.json','full_parent_execution_contract.json'),
        ('actual_coordinate_axis_gate.json','full_parent_coordinate_gate.json'),
        ('exact_depth_reconstruction_audit.json','full_parent_depth_audit.json')]
    for old, new in retained_records:
        shutil.copyfile(NEW_PARENT/old, HERE/new)
    execution = reports['full_parent_execution.json']
    fields = reports['full_parent_fields_comparison.json']
    gauges = reports['full_parent_gauge_comparison.json']
    child = reports['child_physical_input_comparison.json']
    short = reports['child_100s_execution_and_comparison.json']
    gates = dict(
        original_parent_inputs_exact=reports['full_parent_input_identity.json']['all_input_files_byte_identical'],
        complete_parent_execution=execution['returncode']==0,
        full_raw_source_maxima_fields_exact=fields['all_physical_fields_bit_identical'],
        physical_inputs_unchanged_during_parent=fields['candidate_inputs_and_source_frames_unchanged_after_run'],
        exact_source_clock=fields['source_clock_exact'],
        reconstructed_double_bed_exact=fields['exact_post_depth']['all_arrays_bit_identical'],
        native_gauges_complete_and_finite=gauges['all_values_finite'] and gauges['complete_native_step_time_coverage'] and gauges['all_time_and_steps_exact'],
        native_gauge_roundoff_bound=gauges['additional_roundoff_gate_passed'],
        all_fifteen_reconstructed_child_inputs_exact=child['all_fifteen_physical_inputs_bit_identical'],
        unchanged_child_executable=child['child_executable_matches_historical'],
        fresh_child_100s_completed=short['execution']['status']=='completed' and short['validation']['pass'],
        all_seven_fresh_child_outputs_exact=short['all_seven_outputs_byte_identical'],
        libraries_unchanged_during_new_child=short['dynamic_libraries_unchanged_during_new_run'],
        historical_full_child_completed=child['historical_full_execution_complete'] and child['historical_full_numerical_checks_pass'],
        historical_project_I_target_pass=child['historical_project_I_target_pass'])
    history = json.loads((OLD_CHILD/'historical_acceptance.json').read_text())
    result = dict(passed=all(gates.values()), gates=gates,
        candidate_executable_sha256=execution['executable_sha256'],
        recomputed=['Full JAGURS 10861 s trajectory', 'Complete 10 m initial state and 360..10801 s boundary conversion', 'sECOM v1b 100 s runtime/coupling regression'],
        complete_10440_s_child_integration_rerun=False,
        complete_child_equivalence_basis='Identical newly reconstructed 15 physical input files/arrays and unchanged solver executable, anchored to the completed historical full run; the seven new 100 s outputs must additionally match exactly. Historical dynamic-library hashes were unavailable, so current library hashes and unchanged-during-run checks are retained without claiming historical library byte identity.',
        historical_metrics_not_rescored=True,
        inherited_historical_I_metrics=history['metrics'],
        limitations=['Prescribed published Yamazaki/Okada forcing, not a CGFDM validation',
                     'Source inversion used tsunami/runup constraints; not blind source validation',
                     'Historical dry-front convergence/fixed-bed/59 R marker limitations retained',
                     'Only the 10 m child is qualified here; historical 20 m result did not pass all I-target gates'],
        evidence_sha256={n:sha(HERE/n) for n in names+[r[1] for r in retained_records]},
        driver_sha256=sha(Path(__file__)),
        wall_times_s=dict(full_parent=execution['wall_s'],
            field_comparison=fields['wall_s'], gauge_comparison=gauges['wall_s'],
            child_reconstruction=reports['child_reconstruction.json']['wall_s'],
            fresh_child_100s=short['execution']['wall_time_s']))
    save(HERE/'SUMMARY.json', result)
    print(json.dumps(result, indent=2), flush=True)
    assert result['passed'], gates


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {'prepare': prepare, 'run-parent': run_parent,
               'compare-fields': compare_fields, 'compare-gauges': compare_gauges,
               'rebuild-child': rebuild_child, 'compare-child': compare_child,
               'run-short-child': run_short_child, 'summarize': summarize}
    parser.add_argument('action', choices=actions)
    parser.add_argument('--archive', type=Path, default=ARCHIVE,
                        help='Root of the complete historical disaster-chain archive')
    args = parser.parse_args()
    configure_archive(args.archive)
    actions[args.action]()
