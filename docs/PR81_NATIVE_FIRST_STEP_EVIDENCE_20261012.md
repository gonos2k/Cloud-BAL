# PR81 native first-step investigation — 2026-10-12

## Reproduction and source finding

The 12 UTC native case is the PR80 baseline case. It is distinct from the 13 UTC
CP06 candidate and this evidence does not establish behavior for that candidate.
The actual 12 UTC namelist leaves `use_input_w` at its false default. No W
preservation, namelist, FPE-mask, floor, or scheme/version setting was changed.

The PR80 executable (`d85baa306069780818cb9c39c295a6b19787bd96db3e8381401ef68fabf8a5af`)
and archive (`89b4072b37e21b985cf4a10406f16164d20aeb0a76af7be675a4d337c510fe0c`)
were replayed through the isolated case-copy helper. The baseline negative
control reproduces the packed `calc_ww_cp` divide at `divps %xmm9,%xmm7`; active
lanes are finite, while upper zero/zero padding lanes raise the invalid flag.
The source case remains unchanged across the safe replay (109 input files,
including the original executable).

A separate debug-symbol-only KSAS object was used solely for source mapping. Its
scalar divide maps to `module_cu_ksas.f90:1977`,
`dtconv(i) = tfac * tem / wc(i)`. Raw operands were `-631.03125 / 0`. GDB
reported `i=1`, `cnvflg(1)=.FALSE.`, and `wc(1)=0`. In the source, `wc` starts at
zero and only accumulates for active convective columns; earlier filtering
clears `cnvflg` when there is no qualifying layer or the diagnosed velocity is
below its threshold. The later physical consumers of `dtconv` are protected by
`cnvflg`. The unguarded calculation also read cloud-bound indices for inactive
columns.

## Focused candidate

[`controlled.cu_ksas_inactive_timescale.patch`](../patches/controlled.cu_ksas_inactive_timescale.patch)
guards that calculation by `cnvflg`, sets the inactive-column `dtconv` sentinel
to zero, and calls WRF fatal handling for active nonpositive `wc`. Active
columns retain the existing equation and both existing clamps. The patch applies
with zero fuzz to the pinned `.F` and generated `.f90` copies. It does not add a
denominator floor. The extracted patched source loop also passes a focused
pinned-Intel O0/O2 test: an inactive column with zero `wc` and invalid cloud
indices returns the zero sentinel, active columns exercise both existing
clamps, and active zero `wc` reaches WRF fatal handling.

Under the pinned Intel profile, the selective builder replaces only objects
whose runtime traps were observed: the original seven diagnosed modules, then
`module_diffusion_em` and `module_small_step_em` after each next padding-lane
trap. It emits compile and link argv, including their NUL-delimited forms,
working directories, source/generated-source/archive snapshots, output paths,
object hashes, and the KSAS patch hash. Module files are directed to the fresh
scratch compile directory; the source tree is not used as a module-output
directory. Build output hashes can differ across scratch roots because ifx
embeds the absolute module-output path in at least one object; the per-build
audit records the exact realized paths and hashes.

The nine-object candidate reached the first RK step without the reproduced
KSAS, diffusion, or small-step SIMD traps. The run then stopped at the existing
KDM6 check `KDM6 invalid NC number basis input`. This is an `error stop`, not a
SIGFPE, and no first-microphysics completion is claimed. The KDM6 number-basis
policy was outside this native compiler-contract fix and was not changed. The
safe replay again preserved all 109 source-case files; the copied baseline
executable hash was the expected PR80 `d85baa…` value.

Runtime traces and build products are retained under `/var/tmp/pr81_native_*`;
the compact observations above are recorded here instead of copying full GDB
register/local dumps into the source tree. Register evidence includes all XMM
lanes at each trap; the KSAS inactive-column values were captured from the
separate source-mapped debug candidate, not attributed to the stripped
nine-object candidate.

## Evidence correction

An early runner version hardlinked the PR80 source executable and then copied a
candidate over that shared inode. The PR80 run executable briefly changed from
SHA `d85baa…` to candidate SHA `601c6c…`. The source executable was unlinked and
restored from the independent retained PR80 executable; its restored inode has
link count one and the exact PR80 SHA. The prior run directories that shared the
mutated inode are excluded as executable-identity evidence. The runner now
copies inputs and executables to separate inodes, rejects an existing run
directory, and snapshots all source-case file hashes before and after every
replay. The current PR80 negative control and candidate replays use that safe
path. No PR80 receipt was edited.

## KDM6 NC predicate and retained audit

The first-step candidate stops at `KDM6 invalid NC number basis input`, but the
actual call operands and cell indices were not captured. In the pinned PR80
compiled-source snapshot, `specific_number_to_volume` at lines 318–332 returns
invalid for any of these conditions: nonfinite NC or dry density, NC < 0, dry
density <= 0, product overflow, nonfinite converted number, or positive NC
underflowing to zero after multiplication. The preceding call at lines 958–959
succeeded at the same loop cell, so `DEN` and `Q` were finite, `DEN > 0`, `Q >= 0`,
and the computed dry density was finite and positive. Density validity therefore
did not trigger this stop. The remaining possibilities are non-finite/negative
NC or a finite positive NC rejected by the overflow/underflow conversion checks.
The exact NC and converted value were not captured, so the error text cannot
distinguish those cases. The host driver passes `NC=qnc_curr`, `DEN=rho`, and
`Q=qv_curr` at `module_microphysics_driver.F:2535–2550`; `module_initialize_real.F`
interpolates QNC at lines 2024–2039. The candidate's 12:00 initialization
`wrfout` readback has finite QNCLOUD values from zero to 1.5973472e9 kg-1, but
this is not the state at the failing call and does not identify its cell or
operands. The first KDM6 call and first microphysics step remain open.

The machine-readable build/run/test receipts, including hashes of all nine
selected source/object pairs and compact GDB observations, are in
[`pr81_native_first_step_20261012.json`](evidence/pr81_native_first_step_20261012.json).
The focused KSAS test now compiles from its isolated scratch directory in both
Intel O0 and O2 profiles. Its hash-bound patch retains four existing trailing
spaces in context lines; no patch bytes were changed for the metadata update.

The builder rejects an explicitly supplied existing scratch directory before
creating outputs; an existing-directory probe returned the expected status 2.
The case copier operates on regular files in the case directory (flat-file
scope), skips prior outputs/logs and executables, and installs the selected
candidate executable in a distinct inode. The nine-object build is a
selected-only link closure: unselected archive members and retained host link
objects are inherited from the PR80 build. The exact selected source/object
hashes, runtime input hashes, baseline restoration hashes, test artifacts, and
these scope limits are recorded in the machine-readable receipt.
