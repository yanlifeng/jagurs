#!/bin/bash
#DSUB --mpi hmpi
#DSUB -q q_hpcapp
#DSUB -n jagurs_cpu_sync
#DSUB -nn 1
#DSUB -N 1
#DSUB -rpn 1
#DSUB -R "cpu=608;mem=64G"
#DSUB -x job
#DSUB -T 2400
#DSUB -oo jagurs-sync.%A.out
#DSUB -eo jagurs-sync.%A.err
# A new job/directory: do not replace the historical Oct14 validation script.
set -eo pipefail
export JAGURS_PYTHON=${JAGURS_PYTHON:-/eapp_test_01/yanlifeng/jagurs-portable-20261014/build/pyenv/bin/python}
source "$PWD/platform/lineshine/env.sh"
source "$PWD/platform/lineshine/single_node_transport.sh"
set -u
cd "$JAGURS_ROOT"
previous=/eapp_test_01/yanlifeng/jagurs-portable-20261014
inputs=/eapp_test_01/yanlifeng/jagurs-hirota-20261013/build/hirota_inputs
evidence="build/sync-evidence/${CCS_JOB_ID:?}"
mkdir -p "$evidence"
{ date -Is; hostname; cat "$CCS_ALLOC_FILE"; lscpu; numactl -H;
  mpirun --version; mpif90 --version; git rev-parse HEAD; git status --porcelain;
  sha256sum "$previous/build/cpu-collective/jagurs" build/cpu-collective/jagurs;
} > "$evidence/environment.txt"
exec "$JAGURS_PYTHON" tools/compare_layout.py \
  --baseline "$previous/build/cpu-collective/jagurs" \
  --baseline-sha256 edb3f32798a385966c67490d45a66fb077bad73995489bdbc1fe6cf9611d4929 \
  --candidate "$JAGURS_ROOT/build/cpu-collective/jagurs" \
  --work-dir "$inputs" \
  --mpiexec "$JAGURS_PYTHON $JAGURS_ROOT/platform/lineshine/launch.py" \
  --output "$JAGURS_ROOT/runs/sync-${CCS_JOB_ID}" \
  --ranks 128 --threads 1 --procx 16 --procy 8 --run-budget 2100
