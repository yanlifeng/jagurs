#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text())
rank=int(os.environ['OMPI_COMM_WORLD_RANK']);expected=data['groups'][rank]
actual=sorted(os.sched_getaffinity(0))
if actual!=expected: raise SystemExit(f'REFUSE rank {rank}: actual={actual}, expected={expected}')
node=data['rank_memory_nodes'][rank]
print('NUMA_BIND '+json.dumps(dict(rank=rank,pid=os.getpid(),cores=actual,memory_node=node)),flush=True)
os.execvpe('numactl',['numactl','--membind='+str(node)]+sys.argv[2:],os.environ)
