#!/usr/bin/env python3
"""Small host-side schedule tests, not a replacement for the MPI regression."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(['python3', str(ROOT/'tools/check_layout.py')], check=True)
    fc = shutil.which('gfortran')
    if fc is None:
        raise RuntimeError('gfortran is needed for the native schedule checks')
    cases = {
        'default': (None, 'legacy', True),
        'explicit': ((ROOT/'cases/hirota_quick/coupling_output.nml').read_text(), 'legacy', True),
        'off': ('&coupling_output extra_output_count=0 /', 'off', True),
        'custom': ('&coupling_output extra_output_count=1, extra_output_steps=9 /', 'custom', True),
        'negative_count': ('&coupling_output extra_output_count=-1 /', 'legacy', False),
        'too_many': ('&coupling_output extra_output_count=17 /', 'legacy', False),
        'duplicate': ('&coupling_output extra_output_steps=9,9 /', 'legacy', False),
        'zero_step': ('&coupling_output extra_output_count=1, extra_output_steps=0 /', 'legacy', False),
        'unknown_key': ('&coupling_output bad_key=1 /', 'legacy', False),
    }
    results = {}
    with tempfile.TemporaryDirectory(prefix='jagurs-layout-test-') as temp:
        work = Path(temp)
        # The disabled optimization must preprocess back to the old CPU path.
        original = subprocess.check_output(['git', 'show',
            'fddf60996db9044d1bedb18d8d281dd8804e2bf8:src/mod_onefile.f90'], cwd=ROOT)
        old_file = work/'original_onefile.f90'
        old_file.write_bytes(original)
        cpp = [fc, '-cpp', '-E', '-P', '-DMPI', '-DONEFILE', '-DREAL_DBLE',
               '-I'+str(ROOT/'src')]
        old_text = subprocess.check_output(cpp+[str(old_file)], text=True)
        new_text = subprocess.check_output(cpp+[str(ROOT/'src/mod_onefile.f90')], text=True)
        nonblank = lambda value: [line for line in value.splitlines() if line.strip()]
        assert nonblank(old_text) == nonblank(new_text), 'Disabled collective changed the original CPU path'
        guard = subprocess.run(cpp+['-DUSE_GPU', '-DJAGURS_COLLECTIVE_ONEFILE',
            str(ROOT/'src/mod_onefile.f90')], capture_output=True, text=True)
        assert guard.returncode != 0 and 'CPU-only' in guard.stderr, 'Missing GPU misuse guard'
        results['collective_disabled_source'] = 'identical_after_preprocessing'
        results['collective_gpu_guard'] = 'rejected_as_expected'
        exe = work/'test_schedule'
        subprocess.run([fc, '-cpp', '-O2', '-ffree-line-length-none', '-I'+str(ROOT/'src'),
                        '-J'+str(work), str(ROOT/'src/mod_coupling_output.f90'),
                        str(ROOT/'tests/test_coupling_schedule.f90'), '-o', str(exe)], cwd=work, check=True)
        for name, (contents, mode, ok) in cases.items():
            config = work/(name+'.nml')
            if contents is not None:
                config.write_text(contents+'\n')
            result = subprocess.run([str(exe), str(config), mode], cwd=work, capture_output=True, text=True)
            assert (result.returncode == 0) == ok, (name, result.stdout, result.stderr)
            results[name] = 'PASS' if ok else 'rejected_as_expected'
    print(json.dumps(dict(passed=True, tests=results, scope='serial schedule/static checks only'), indent=2))


if __name__ == '__main__':
    main()
