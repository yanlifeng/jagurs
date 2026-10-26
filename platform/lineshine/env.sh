#!/bin/bash
# Source this file. The solver uses the coherent GNU/HMPI stack, not default flang.
_jagurs_restore_u=0
case $- in *u*) _jagurs_restore_u=1; set +u ;; esac
source /work_ssd/software/HPCKit/25.1.0.SPC001/compiler/gcc/env/setvars.sh
source /work_ssd/software/HPCKit/25.1.0.SPC001/hmpi/gcc/env/setvars.sh --mode=release
export NETCDF_PREFIX=/work_ssd/software/soft/lib/netcdf/4.9.3-hpckit25.1.0.SPC001-gcc12.3.1-hmpi25.1.0.SPC001-hdf51.14.3-pnetcdf1.14.0
export PROJ_PREFIX=/work_ssd/software/soft/lib/proj/9.4.1-hpckit25.1.0.SPC001-gcc12.3.1
export FFTW_PREFIX=/work_ssd/software/soft/lib/fftw/3.3.10-hpckit25.1.0.SPC001-bisheng4.2.0.2.B002-hmpi25.1.0.SPC001
export LD_LIBRARY_PATH="$NETCDF_PREFIX/lib:$PROJ_PREFIX/lib64:$FFTW_PREFIX/lib:/work_ssd/software/soft/lib/szip/2.1.1-hpckit25.1.0.SPC001-gcc12.3.1/lib:${LD_LIBRARY_PATH:-}"
export PATH="$NETCDF_PREFIX/bin:$PATH"
export FC=mpif90 CC=gcc
export JAGURS_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
export JAGURS_PYTHON="${JAGURS_PYTHON:-$JAGURS_ROOT/build/pyenv/bin/python}"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE OMP_PROC_BIND=close OMP_PLACES=cores
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
if ((_jagurs_restore_u)); then set -u; fi
unset _jagurs_restore_u
