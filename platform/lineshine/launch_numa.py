#!/usr/bin/env python3
"""Single-node NUMA sweep launcher; preserves the older balanced launcher.

JAGURS_NUMA_DOMAINS selects a prefix of CPU NUMA domains, not memory-only nodes.
Ranks are packed evenly in those domains; system CPUs are always excluded.
"""
import json, os, shutil, subprocess, sys
from pathlib import Path
from launch import allocation, cpulist

def make_groups(ranks, threads, domains):
    if domains not in (1,2,4,8,16) or threads<1 or ranks<1 or ranks%domains:
        raise ValueError('Require 1/2/4/8/16 domains and equal ranks/domain')
    per=ranks//domains
    if per*threads>37: raise ValueError('At most 37 application CPUs per domain')
    return [list(range(38*d+r*threads,38*d+(r+1)*threads)) for d in range(domains) for r in range(per)]

def main():
    if len(sys.argv)<4 or sys.argv[1]!='-n': raise SystemExit('Expected -n RANKS executable [arguments]')
    ranks=int(sys.argv[2]);threads=int(os.environ.get('OMP_NUM_THREADS','1'))
    domains=int(os.environ.get('JAGURS_NUMA_DOMAINS','1'))
    host,allowed=allocation();groups=make_groups(ranks,threads,domains)
    topology={}
    for p in Path('/sys/devices/system/node').glob('node[0-9]*'):
        nodestr=(p/'cpulist').read_text().strip()
        if not nodestr: continue
        d=int(p.name[4:]);cpus=cpulist(nodestr)
        topology[d]=dict(cpus=sorted(cpus),distance=list(map(int,(p/'distance').read_text().split())),
            meminfo=(p/'meminfo').read_text(),
            socket=int(Path(f'/sys/devices/system/cpu/cpu{min(cpus)}/topology/physical_package_id').read_text()))
    if set(topology)!=set(range(16)): raise RuntimeError('Unexpected CPU NUMA topology')
    for d in range(16):
        if topology[d]['cpus']!=list(range(38*d,38*(d+1))): raise RuntimeError('Unexpected NUMA CPU numbering')
    flat=[c for g in groups for c in g]
    if not set(flat)<=allowed or len(set(flat))!=ranks*threads or any(c%38==37 for c in flat):
        raise RuntimeError('Invalid, overlapping or system-core mask')
    for cpu in flat:
        if cpulist(Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list').read_text().strip())!={cpu}:
            raise RuntimeError('Unexpected SMT topology')
    if not shutil.which('numactl'): raise RuntimeError('numactl required for explicit local memory binding')
    mapping=Path.cwd()/'lineshine.mapping.json';rankfile=Path.cwd()/'lineshine.rankfile'
    if mapping.exists() or rankfile.exists(): raise RuntimeError('Do not overwrite an existing launch')
    data=dict(job=os.environ['CCS_JOB_ID'],host=host,ranks=ranks,threads=threads,groups=groups,
        active_cpu_numa=list(range(domains)),topology=topology,allocated_cpus=sorted(allowed),
        rank_memory_nodes=[g[0]//38 for g in groups],memory_policy='strict membind to rank CPU NUMA domain')
    mapping.write_text(json.dumps(data,indent=2)+'\n')
    rankfile.write_text(''.join(f'rank {r}={host} slot={g[0]}-{g[-1]}\n' for r,g in enumerate(groups)))
    env=os.environ.copy();env.pop('CCS_COSCHED_MPI_AFFINITY_FILE',None)
    env.update(OMP_DYNAMIC='FALSE',OMP_PROC_BIND='close',OMP_PLACES='cores',OMP_WAIT_POLICY='ACTIVE')
    command=['mpirun','--mca','plm','isolated','--mca','rmaps_rank_file_physical','true',
        '--rankfile',str(rankfile),'--report-bindings','-n',str(ranks),sys.executable,
        str(Path(__file__).with_name('rank_numa.py')),str(mapping)]+sys.argv[3:]
    return subprocess.run(['timeout','--signal=TERM','--kill-after=15',env.get('JAGURS_RUN_LIMIT_S','2400')]+command,env=env).returncode

if __name__=='__main__': sys.exit(main())
