#!/usr/bin/env python3
"""Build the unchanged official GNU configuration plus the committed fixes.

The source tree stays free of objects. GNU Fortran with OpenMPI and FFTW is
the portable route. --local selects the libraries already installed on the
development x86 machine; it is not a Kunpeng-specific build recipe.
"""
from pathlib import Path
import argparse, os, subprocess, shutil, json, time, hashlib, shlex

ROOT = Path(__file__).resolve().parents[1]
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--local', action='store_true')
    ap.add_argument('--build-dir', type=Path, default=ROOT/'build/gnu')
    ap.add_argument('--fc', default=os.environ.get('FC','mpif90'))
    ap.add_argument('--cc', default=os.environ.get('CC','gcc'))
    ap.add_argument('--netcdf', default=os.environ.get('NETCDF_PREFIX','/usr'))
    ap.add_argument('--proj', default=os.environ.get('PROJ_PREFIX','/usr'))
    ap.add_argument('--fftw', default=os.environ.get('FFTW_PREFIX','/usr'))
    ap.add_argument('--proj9', action='store_true',
                    help='Use upstream PROJ9 support (required with PROJ 9 headers).')
    ap.add_argument('--opt', default='-O3 -fopenmp -ffp-contract=off')
    ap.add_argument('--dry-run', action='store_true',
                    help='Check compiler/headers and print the build command without writing files.')
    a=ap.parse_args(); build=a.build_dir.resolve()
    if build == ROOT or build == (ROOT/'src').resolve() or build in ROOT.parents:
        ap.error('--build-dir must be a separate build directory, not the source tree or its ancestors')
    if a.local:
        deps=ROOT.parent/'tsunami-jagurs-20260915/deps'
        mkl=Path('/opt/intel/oneapi/mkl/2023.2.0')
        fc='mpif90 -fc=gfortran'; netcdf=proj=str(deps)
        fftw_include=str(mkl/'include/fftw')
        libs=f'-L{deps}/lib -lnetcdff -L/usr/lib64 -lnetcdf -lproj -L{mkl}/lib/intel64 -lmkl_rt -lpthread -lm -ldl -Wl,-rpath,{mkl}/lib/intel64'
    else:
        fc=a.fc;netcdf=a.netcdf;proj=a.proj
        fftw_include=str(Path(a.fftw)/'include')
        libs=f'-L{netcdf}/lib -L{netcdf}/lib64 -lnetcdff -lnetcdf -L{proj}/lib -L{proj}/lib64 -lproj -L{a.fftw}/lib -L{a.fftw}/lib64 -lfftw3 -lm'
    # Query the selected MPI wrapper, which need not use PATH's gfortran.
    try:
        fc_command=shlex.split(fc)
        compiler=subprocess.check_output(fc_command+['--version'],text=True,
                                         stderr=subprocess.STDOUT).strip()
        if 'GNU Fortran' not in compiler:
            ap.error('--fc must select an MPI wrapper backed by GNU Fortran')
        version=subprocess.check_output(fc_command+['-dumpversion'],text=True).strip()
        major=int(version.split('.')[0])
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        ap.error(f'Cannot query the selected Fortran compiler {fc!r}: {exc}')
    base='-cpp -ffree-line-length-none'
    # GNU 8 has no -fallow-invalid-boz; retain the historical compatibility flag.
    base+=' -fno-range-check' if major<10 else ' -fallow-invalid-boz'
    headers=[Path(netcdf)/'include/netcdf.inc', Path(fftw_include)/'fftw3.f',
             Path(proj)/('include/proj.h' if a.proj9 else 'include/proj_api.h')]
    missing=[str(p) for p in headers if not p.is_file()]
    if missing:
        ap.error('Missing development headers: '+', '.join(missing)+
                 '. Set --netcdf/--fftw/--proj prefixes; add --proj9 for PROJ 9.')
    cmd=['make','-j1','-f','Makefile.gfortran',f'FC={fc}',f'CC={a.cc}',f'BASE={base}',
         f'NETCDF={netcdf}',f'PROJ_DIR={proj}',f'FFTW3_INCLUDE_DIR={fftw_include}',
         f'OPT={a.opt} -I{fftw_include}',f'LIBS={libs}',
         'PREC=REAL_DBLE','MPI=ON','USE_ALLTOALLV=ON','ONEFILE=ON',
         'TIMER=DETAIL','CONV_CHECK=ON']
    if a.proj9:cmd.append('PROJ9=ON')
    if a.dry_run:
        print(json.dumps(dict(command=cmd, compiler=compiler.splitlines()[0],
                              build_dir=str(build)),indent=2))
        return
    build.mkdir(parents=True, exist_ok=True)
    for p in (ROOT/'src').iterdir():
        if p.is_symlink():
            target=build/p.name
            if target.is_symlink() or target.exists():target.unlink()
            target.symlink_to(os.readlink(p))
        elif p.is_file():shutil.copyfile(p,build/p.name)
    # Fortran module prerequisites are not explicit in the upstream Makefile.
    subprocess.run(['make','-j1','-f','Makefile.gfortran','clean'],cwd=build,check=True,
                   stdout=subprocess.DEVNULL)
    start=time.monotonic()
    with (build/'build.log').open('w') as log:
        result=subprocess.run(cmd,cwd=build,stdout=log,stderr=subprocess.STDOUT)
    record=dict(command=cmd,returncode=result.returncode,wall_s=time.monotonic()-start,
                compiler=compiler.splitlines()[0],
                source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT/'src').iterdir() if p.is_file() and p.suffix in ('.f90','.f','.h','.c')},
                platform_specific_recipe=a.local)
    if result.returncode==0:
        record['executable_sha256']=hashlib.sha256((build/'jagurs').read_bytes()).hexdigest()
    (build/'build.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='source_sha256'},indent=2))
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':main()
