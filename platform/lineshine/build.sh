#!/bin/bash
# Platform/dependency selection only; the CPU build recipe lives in tools/.
set -eo pipefail
source "$(dirname "$0")/env.sh"
set -u
cd "$JAGURS_ROOT"
exec "$JAGURS_PYTHON" tools/build_cpu.py --proj9 --output-gather collective \
    --build-dir "${JAGURS_BUILD_DIR:-$JAGURS_ROOT/build/cpu-collective}" "$@"
