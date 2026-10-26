#!/usr/bin/env python3
"""Platform-neutral CPU recipe; dependency locations remain caller settings.

The original benchmark builder and verifier are not edited. This wrapper adds
an explicit choice of the common CPU output-collection implementation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-gather', choices=['legacy', 'collective'], default='legacy')
    ap.add_argument('--skip-max-velocity', action='store_true',
                    help='Omit only the diagnostic maximum-velocity product; default keeps it')
    ap.add_argument('--build-dir', type=Path, required=True)
    ap.add_argument('--opt', default='-O3 -fopenmp -ffp-contract=off')
    args, remaining = ap.parse_known_args()
    if any(x.startswith(('--opt', '--build-dir')) for x in remaining):
        ap.error('Duplicate optimization/build-directory argument')
    if 'USE_GPU' in args.opt:
        ap.error('This recipe validates CPU only; use a separately qualified GPU backend')
    build = args.build_dir.resolve()
    if build.exists() and '--dry-run' not in remaining:
        ap.error('Build directory exists; choose a new path to preserve prior evidence')
    subprocess.run([sys.executable, str(ROOT/'tools/check_layout.py')], check=True)
    opt = args.opt
    if args.output_gather == 'collective':
        opt += ' -DJAGURS_COLLECTIVE_ONEFILE'
    if args.skip_max_velocity:
        opt += ' -DSKIP_MAX_VEL'
    command = [sys.executable, str(ROOT/'benchmarks/build_gnu.py'),
               '--build-dir', str(build), '--opt='+opt] + remaining
    result = subprocess.run(command, cwd=ROOT)
    if not result.returncode and '--dry-run' not in remaining:
        (build/'portability-build.json').write_text(json.dumps(dict(
            scientific_base='fddf60996db9044d1bedb18d8d281dd8804e2bf8',
            git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            git_status=subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True),
            backend='cpu_fortran', output_gather=args.output_gather,
            skip_max_velocity=args.skip_max_velocity,
            command=command, gpu_validated=False,
            note='Opt-in CPU engineering changes; frozen inputs/references/verifier unchanged. '
                 'Source and executable hashes are recorded in build.json.'), indent=2)+'\n')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
