#!/usr/bin/env python3
"""Launch only within a scheduler-proven full-node allocation, excluding system cores."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def cpulist(text):
    result = set()
    for part in text.split(','):
        bounds = part.split('-')
        a, b = int(bounds[0]), int(bounds[-1])
        result.update(range(a, b + 1))
    return result


def allocation():
    if not os.environ.get('CCS_JOB_ID'):
        raise RuntimeError('Submit via dsub; no login-node execution')
    host = socket.gethostname().split('.')[0]
    rows = Path(os.environ['CCS_ALLOC_FILE']).read_text().splitlines()
    rows = [line.split() for line in rows if line.strip()]
    if len(rows) != 1 or rows[0][0].split('.')[0] != host or int(rows[0][1]) != 608:
        raise RuntimeError(f'Requires a complete single-node 608-CPU allocation: {rows}')
    # A full-node job without -a has no per-rank affinity file. In that case,
    # CCS_ALLOC_FILE granting all 608 CPUs and sysfs topology are the authority.
    affinity_name = os.environ.get('CCS_COSCHED_MPI_AFFINITY_FILE')
    allowed = set()
    if affinity_name:
        for line in Path(affinity_name).read_text().splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[1].split('.')[0] != host:
                raise RuntimeError(f'Unexpected scheduler affinity row: {line}')
            allowed.update(cpulist(fields[2]))
    else:
        allowed = cpulist(Path('/sys/devices/system/cpu/online').read_text().strip())
    if allowed != set(range(608)):
        raise RuntimeError(f'Full-node affinity not confirmed ({len(allowed)} CPUs)')
    return host, allowed


def main():
    if len(sys.argv) < 4 or sys.argv[1] != '-n':
        raise SystemExit('Expected -n RANKS executable [arguments]')
    ranks = int(sys.argv[2])
    threads = int(os.environ.get('OMP_NUM_THREADS', '1'))
    host, allowed = allocation()
    per_domain = 37 // threads
    if threads < 1 or ranks < 1 or ranks > 16 * per_domain:
        raise RuntimeError('Requested rank/thread layout cannot fit without crossing NUMA domains')
    groups = []
    # Balanced count across 16 CPU NUMA domains; adjacent ranks within a domain.
    for domain in range(16):
        count = ranks // 16 + (domain < ranks % 16)
        for local_rank in range(count):
            first = 38 * domain + local_rank * threads
            group = list(range(first, first + threads))
            if any(cpu not in allowed or cpu % 38 == 37 for cpu in group):
                raise RuntimeError('Attempt to use an unallocated/system CPU')
            groups.append(group)
    flattened = [cpu for group in groups for cpu in group]
    if len(groups) != ranks or len(set(flattened)) != ranks * threads:
        raise RuntimeError('Overlapping/invalid rank masks')
    cwd = Path.cwd()
    rankfile = cwd / 'lineshine.rankfile'
    mapping = cwd / 'lineshine.mapping.json'
    for target in (rankfile, mapping):
        if target.exists():
            raise RuntimeError(f'Refuse to overwrite mapping: {target}')
    rankfile.write_text(''.join(f'rank {rank}={host} slot={group[0]}-{group[-1]}\n'
                                for rank, group in enumerate(groups)))
    mapping.write_text(json.dumps(dict(job=os.environ['CCS_JOB_ID'], host=host,
        ranks=ranks, threads=threads, allocated_cpus=sorted(allowed), groups=groups,
        layout='balanced NUMA, contiguous rank groups; system CPUs excluded'), indent=2)+'\n')
    env = os.environ.copy()
    # Replace only HMPI's automatic mapping with an explicit subset of that same allocation.
    env.pop('CCS_COSCHED_MPI_AFFINITY_FILE', None)
    env['OMP_DYNAMIC'] = 'FALSE'
    env['OMP_PROC_BIND'] = 'close'
    env['OMP_PLACES'] = 'cores'
    env['OMP_WAIT_POLICY'] = 'ACTIVE'
    wrapper = Path(__file__).with_name('rank.py')
    command = ['mpirun', '--mca', 'plm', 'isolated', '--mca', 'rmaps_rank_file_physical', 'true',
               '--rankfile', str(rankfile), '--report-bindings', '-n', str(ranks),
               sys.executable, str(wrapper), str(mapping)] + sys.argv[3:]
    timeout = int(env.get('JAGURS_RUN_LIMIT_S', '1000'))
    result = subprocess.run(['timeout', '--signal=TERM', '--kill-after=15', str(timeout)]+command, env=env)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
