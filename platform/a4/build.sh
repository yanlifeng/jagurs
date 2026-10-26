#!/bin/bash
set -eo pipefail
source "$(dirname "$0")/env.sh"
set -u
cd "$JAGURS_ROOT"
# --local selects the already frozen a4 dependency recipe in build_gnu.py.
# It expects ../tsunami-jagurs-20260915/deps. No libraries are auto-installed.
opt='-O3 -fopenmp -ffp-contract=off'
if [[ ${JAGURS_NATIVE:-0} == 1 ]]; then
    opt+=' -march=native -mtune=native'
fi
exec "$JAGURS_PYTHON" tools/build_cpu.py --local \
  --build-dir "${JAGURS_BUILD_DIR:-$JAGURS_ROOT/build/cpu-a4}" --opt="$opt" "$@"
