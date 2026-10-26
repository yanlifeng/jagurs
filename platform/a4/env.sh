#!/bin/bash
# Site policy only. Source before building/running; do not put this in src/.
source /opt/intel/oneapi/mpi/2021.12/env/vars.sh
export JAGURS_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
export JAGURS_PYTHON=${JAGURS_PYTHON:-/home/user_home/ylf/disaster-chain-secom-20260928/py/bin/python}
export LD_LIBRARY_PATH="/home/user_home/ylf/tsunami-jagurs-20260915/deps/lib:/opt/intel/oneapi/mkl/2023.2.0/lib/intel64:${LD_LIBRARY_PATH:-}"
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export OMP_DYNAMIC=FALSE MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export I_MPI_FABRICS=shm:ofi
