#!/bin/bash
#DSUB --mpi hmpi
#DSUB -q q_hpcapp
#DSUB -n jagurs_layout
#DSUB -nn 1
#DSUB -N 1
#DSUB -rpn 1
#DSUB -R "cpu=608;mem=64G"
#DSUB -x job
#DSUB -T 2400
#DSUB -oo jagurs-layout.%A.out
#DSUB -eo jagurs-layout.%A.err
set -eo pipefail
source "$PWD/platform/lineshine/env.sh"
source "$PWD/platform/lineshine/single_node_transport.sh"
set -u
cd "$JAGURS_ROOT"
previous=/eapp_test_01/yanlifeng/jagurs-hirota-20261013
evidence="build/layout-evidence/${CCS_JOB_ID:?}"
mkdir -p "$evidence"
{ date -Is; hostname; cat "$CCS_ALLOC_FILE"; lscpu; numactl -H;
  mpirun --version; mpif90 --version;
  sha256sum "$previous/build/opt01-collective/jagurs" build/cpu-collective/jagurs;
} > "$evidence/environment.txt"
"$JAGURS_PYTHON" tools/check_layout.py > "$evidence/protected-files.json"
cp platform/lineshine/{validate_layout.sh,env.sh,single_node_transport.sh,launch.py,rank.py} "$evidence/"
exec "$JAGURS_PYTHON" tools/compare_layout.py \
  --baseline "$previous/build/opt01-collective/jagurs" \
  --baseline-sha256 dc19b58f536915fb2ed98fa1f35b4ee58e687d81facb78b90246a62ebc8bf04c \
  --candidate "$JAGURS_ROOT/build/cpu-collective/jagurs" \
  --work-dir "$previous/build/hirota_inputs" \
  --mpiexec "$JAGURS_PYTHON $JAGURS_ROOT/platform/lineshine/launch.py" \
  --output "$JAGURS_ROOT/runs/layout-${CCS_JOB_ID}" \
  --ranks 128 --threads 1 --procx 16 --procy 8 --run-budget 2100
