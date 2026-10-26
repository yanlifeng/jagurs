"""Static import guards and an executable check of the actual guard condition.

These tests do not replace MPI/source-I/O or full-event numerical regression.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    params = (ROOT/'src/mod_params.f90').read_text()
    main = (ROOT/'src/JAGURS.f90').read_text()
    cache = (ROOT/'src/mod_displacement.f90').read_text()
    reader = (ROOT/'src/mod_newsubs.f90').read_text()
    for key, default in [('source_field_output', 1), ('legacy_velocity_diagnostics', 1),
                         ('kj_workspace_cache', 0), ('source_local_read', 0), ('error_check_interval', 1)]:
        assert re.search(r'\b'+key+r'\s*=\s*'+str(default)+r'\b', params), key
    assert 'if(error_check_interval < 1)' in main
    assert 'legacy_velocity_diagnostics /= 0 .and. coupling_extra_output_due(istep, velgrd)' in main
    assert "'.eta_raw.'" not in main  # Raw writer remains in the coupling interface.
    assert 'keep_workspace = .false. ! GPU' in cache
    assert 'if(source_local_read == 1)' in reader and 'nf90_enotatt' in reader
    condition = re.search(r'if\((mod\(istep,error_check_interval\).*?)\) then', main).group(1)
    assert shutil.which('gfortran'), 'gfortran required'
    # Compile the exact production predicate, rather than a second Python model.
    source = '''program check
      implicit none
      integer :: istep, istart, nstep, error_check_interval, count, k
      integer :: intervals(3) = [1,10,50], expected(3) = [2001,202,42]
      istart=1; nstep=2001
      do k=1,3
        error_check_interval=intervals(k); count=0
        do istep=istart,nstep
          if (PREDICATE) count=count+1
        end do
        if(count /= expected(k)) stop 1
      end do
      istart=27; nstep=65; error_check_interval=50; count=0
      do istep=istart,nstep
        if (PREDICATE) count=count+1
      end do
      if(count /= 3) stop 2
    end program
    '''.replace('PREDICATE', condition)
    with tempfile.TemporaryDirectory(prefix='jagurs-cpu-guards-') as d:
        d = Path(d); (d/'guard.f90').write_text(source)
        subprocess.run(['gfortran','-ffree-line-length-none',str(d/'guard.f90'),'-o',str(d/'check')],check=True)
        subprocess.run([str(d/'check')],check=True)
    print(json.dumps(dict(passed=True, scope='defaults, coupling ownership, CPU guards, actual cadence predicate')))

if __name__ == '__main__':
    main()
