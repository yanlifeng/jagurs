# Single-node NUMA scaling launcher

`launch_numa.py` is a platform-only launcher; it does not change the solver or
the existing balanced `launch.py`. Use it only inside a scheduler-confirmed
complete 608-CPU single-node allocation (`-x job`).

Set `JAGURS_NUMA_DOMAINS=1|2|4|8|16` and `OMP_NUM_THREADS=1`, then invoke
`python launch_numa.py -n RANKS EXECUTABLE ...`. Ranks are distributed equally
over CPU NUMA domains `0..N-1`. The launcher checks sysfs CPU numbering and
excludes the last/system CPU of each 38-CPU domain; at most 37 application
cores are available per domain. Memory-only NUMA nodes are not CPU domains.

`rank_numa.py` verifies actual CPU affinity and uses `numactl --membind` for
strict local memory placement. Thus the single-domain measurement cannot
quietly borrow remote-domain memory bandwidth; allocation failure is an
invalid test, not a reason to silently change memory policy. Save the mapping,
topology, distance and memory-size records with each result.

For the 2011 Tohoku 10-arcsec case, the planned primary curve uses 32 MPI per
domain: 32/64/128/256/512 ranks. The additional 592-rank point uses 37 per
domain and must be labelled separately. This is speedup relative to one
**NUMA domain**, not one CPU core. Prefix domains cross socket boundaries at
the largest point; this hardware effect must not be attributed solely to the
algorithm. The independent experiment folder contains fixed inputs, paired
short source-path checks, repeated timings and full-event numerical checks.

Local mapping unit tests: `python tests/test_numa_mapping.py`. On-node CPU and
memory-policy probes are required before using timings; unit tests alone do
not certify runtime binding or numerical correctness.
