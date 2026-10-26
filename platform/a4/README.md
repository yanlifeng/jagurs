# a4 CPU recipe

This directory selects GNU Fortran, Intel MPI and the MKL FFTW interface on a4.
It does not own the source reader, FFT workspace cache or shallow-water kernels.

```sh
bash platform/a4/build.sh --skip-max-velocity
```

The common gather defaults to `legacy` on a4. Use `--output-gather collective`
only after a paired regression on the target case. The LineShine recipe opts
into that implementation because it has separate historical validation there.

`JAGURS_NATIVE=1` optionally enables the local CPU ISA. This is NOT the recommended
default: the Oct26 a4 screening did not show a >2% median benefit. Never copy an
x86 executable to ARM. Both builds keep strict floating-point flags (no fast-math).

`--skip-max-velocity` drops the maximum-speed diagnostic product only. It is a
common product choice, not an x86-specific algorithm; omit it when that product
is required. Runtime engineering options are documented in
`cases/tohoku_single/README.md`, separately from compiler/site policy.

For measurements, use only idle resources, physical cores (not SMT siblings),
one MKL thread and verified MPI/OpenMP affinity. The historical experiment's
`rank_exec.py`, `affinity_probe` and load checks are retained with its evidence,
not injected into scientific code. Do not copy its Intel MPI settings to HMPI.
The private host cannot provide multi-node scalability evidence.
