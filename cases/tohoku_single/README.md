# Tohoku single-grid CPU engineering profile

This directory describes engineering settings, not a replacement earthquake,
bathymetry, observation data set or a complete standalone input package.

The a4 2026-10-26 selected run used the existing 10 arcsec 5041×3961 input,
dt=0.3 s, 182 dynamic frames and 0.9 s station sampling. In the existing
tsun.par namelist, set these optional controls (do not replace physical values):

```fortran
source_field_output=0
legacy_velocity_diagnostics=0
kj_workspace_cache=1
source_local_read=1
error_check_interval=1
```

For a new case, copy `coupling_output.nml` from this directory into its run
directory: it explicitly disables historical Hirota-only extra handoff frames.
The legacy_velocity_diagnostics=0 control also suppresses extra configured
handoff frames, but never suppresses regular raw output scheduled by itmap.

Build with `tools/build_cpu.py --skip-max-velocity ...` only when the maximum
velocity hazard map is not required. This removes no SWE velocity/flux update
and does not suppress zmax. The default build retains this product.

Source local reads require CPU + MPI + ONEFILE, non-pixel spherical CF lon/lat
files with node_offset=0, aligned to each computational grid including halos.
The qualified path rejects scaling/fill attributes and misalignment; arbitrary
source formats are not supported. Keep source_local_read=0 for unqualified
inputs. Independent reads are not collective parallel NetCDF and may stress a
large shared filesystem; this is not a guaranteed multi-node I/O improvement.

The cache reuses CPU FFT plans and workspace, never physical source fields,
depth, latitude or filter coefficients. It is disabled for USE_GPU. Defaults
are cache=0, local_read=0, source_field_output=1, guard_interval=1, preserving
historical behavior. Sampling, duration and decomposition belong to the case/
launcher, not to platform-specific scientific equations.
