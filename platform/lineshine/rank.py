#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
rank = int(os.environ['OMPI_COMM_WORLD_RANK'])
expected = set(data['groups'][rank])
actual = os.sched_getaffinity(0)
if actual != expected:
    raise SystemExit(f'REFUSE rank {rank}: actual={sorted(actual)}, expected={sorted(expected)}')
os.environ['JAGURS_EXPECTED_CPUS'] = ','.join(map(str, sorted(expected)))
print(f'BIND rank={rank} cpus={sorted(actual)} threads={data["threads"]}', flush=True)
os.execvpe(sys.argv[2], sys.argv[2:], os.environ)
