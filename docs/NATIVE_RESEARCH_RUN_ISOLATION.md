# Isolated native research runs

Use `tools/run_isolated_native.py` for a research run whose declared outputs
must not overwrite retained comparison evidence. Create a fresh real directory
for each run, place its runtime inputs there, and name every output, raw
capture, launch record, and log the command may write.

```bash
python3 tools/run_isolated_native.py \
  --run-root /var/tmp/native-run-unique \
  --input /var/tmp/native-run-unique/wrfinput_d01 \
  --input /var/tmp/native-run-unique/wrfbdy_d01 \
  --input /var/tmp/native-run-unique/namelist.input \
  --output wrfout_d01_2026-08-16_12:00:20 \
  --output kdm6_pre.raw \
  --output kdm6_post.raw \
  --output rsl.out.0000 \
  --receipt run-isolation.json \
  -- /absolute/path/to/wrf.exe
```

The helper checks the run-root path and output-parent components for symlinks,
rejects existing or duplicate output paths before launch, and checks declared
outputs again afterward for regular-file type and a single link. Its JSON
receipt records input hashes before and after, output hashes and inode/link
metadata, and post-run integrity failures. A command that creates a hardlinked
output is recorded as failed even though the process has already run.

Inputs must be detached, single-link regular files. Copy inputs into the fresh
run tree before launch; the helper rejects symlinks and hardlinks. It does not
chmod inputs, because that would not be a reliable write-protection boundary.
Input hashes are checked before and after execution. This detects persistent
changes but does not prevent a process from writing and restoring bytes.

The helper is not an OS sandbox. It checks only the paths declared with
`--input`, `--output`, and `--receipt`; it cannot prevent or certify writes to
undeclared paths, nor does it close concurrent pathname replacement races.
Declare all expected model outputs, raw captures, launch records, and logs, and
use a fresh run directory whose other contents are understood. Preserve each
receipt with the run evidence. This guard provides no scientific validation.

## PR63 native trace use (2026-10-06)

The native trace launcher used `run_isolated()` from this helper for a fresh
copy at `/var/tmp/pr63_native_transition_20261006/run_transition_v2`. Its
receipt is `run-isolation.json` (SHA-256
`3570a95c63702d548f18de3417369d210b749a0ba46ee704dd1a4794e524e7e6`). The
recorded process returned 0; all 102 declared input hashes were unchanged and
all 15 declared outputs were present, regular files with `nlink=1`. A
read-only audit found no input/output inode aliases and no output inode shared
with the retained `run_rank2`, `run_ifxruntime`, or failed stage2 run.

The selected executable in the run root hashes to
`d0b260a721f1df37c045ae08e7c5fe1d7b0c1e0d8f11cba9490e34f60f309c30`, matching
the linked executable. The detached `wrfinput_d01` and `wrfbdy_d01` hashes
match the expected PR62 candidate inputs. The call-entry and return raw files
and initial `wrfout` are byte-identical to the retained `run_rank2` and
`run_ifxruntime` artifacts. Runtime compiler/MPI environment scripts and
resolved libraries are declared and hash-checked inputs; `ldd` and the
launched environment are captured as outputs. The environment capture records
inherited variables but does not independently freeze or validate every
environment variable.

Build provenance for this run was checked separately: the instrumented
`solve_em.o` SHA-256 is
`8670703c8229399709caaf5fb47e8c9dc865ad5def98cc7d4baaed6054bfd772` in the
object file, the replacement archive member, and the build manifest. The
linked executable contains the transition probe symbol and the run-root copy
matches its linked executable hash.

Keep the earlier attempts distinct. The retained `run_ifxruntime` and
`run_rank2` executables do not contain the transition-state probe symbol; they
are reference captures, not transition-stage instrumented runs. The failed
`run_transition_cutoff_stage2` executable does contain that probe and was linked
from the corrected `solve_em.o` archive member (SHA-256
`5a35089427a6bfae8fb88a161e6a3697f70994cae9aad6180989d19796c2c20d`) for its
build. It failed a bounds check because the instrumentation indexed tile 2 in
a one-tile run. Its receipt remains preserved (SHA-256
`870e83b429b590f6c47fb5920f8516eec239ffeb2428eaf5a91570e246adf55e`); the
failure is an instrumentation/runtime bounds error, not evidence about
physical behavior. The successful `run_transition_v2` is a later, separately
built executable with corrected tile indexing and independently verified
archive-member provenance.

These are engineering isolation and artifact-identity checks for a one-rank,
one-tile, 20-second research execution. They do not validate undeclared writes,
multi-rank behavior, the full host build, physical conservation, initial-shock
reduction, or forecast skill. The later paired graupel-volume replay, if used,
requires its own fresh run root and receipt.

## Paired graupel attempt (initial failure retained; later pair completed)

The guarded attempt at `/var/tmp/pr63_native_transition_20261006/run_paired_v2b`
has receipt SHA-256
`a59bcd0b804ca29a25e380c6d13b8e35b0ed659f057fc6085b85c2a6a86bc2a1`. It
returned code 1 with input integrity `PASS` and output isolation `FAIL`: 98
declared input hashes were unchanged, all 13 produced declared outputs were
regular single-link files, and none shared an inode with files in the v2
control run. Required `kdm6_first_call_post.raw` and
`pr63_graupel_extinction.raw` were absent. The log records SIGTERM in KDM6;
the parent authorized interruption after an excessive repeated diagnostic
stream. This attempt therefore provides no evidence about paired QG/BG
extinction.

This attempt used `bash ./launch.sh`, but `launch.sh` was not declared as an
input. Its separately observed SHA-256 was
`2e6f5fd68eea0803eb3c7a3d6050cbac5921ab753c6c0adeb682608b35096cce` and its
link count was one; those observations do not retroactively bind its bytes in
the run receipt. Preserve this failed attempt; it provides no evidence about
paired QG/BG extinction.

An additional read-only, standalone parser audit is recorded outside the run
directory at `/var/tmp/pr63_native_transition_20261006/independent_geometry_audit.json`
(SHA-256 `bc657c52968ad58280ccd4851df77d12d682acdd714964f5dbbc3df4c0b84ead`).
It parses both `PR63GEO2` geometry snapshots, checks their fixed positional
array shapes and inclusive bounds against the KDM6 pre-call header, and
recomputes layer and column pressure consistency from current `MU2+MUB`. The
maximum layer/interface difference was 0.00250 Pa and column closure
difference 0.000109 Pa. `DEN*DELZ*area` differed by 0.05856% from the
hybrid-coefficient dry-mass diagnostic; it remains a diagnostic, not a closed
budget. Units are inferred from source equations because the raw geometry
header contains no unit strings. This audit is also limited to timestep 1 of
the one-rank, one-tile capture and grants no physical approval.

The reusable read-only CLI is `tools/native_kdm6_call_geometry.py`. It accepts
the geometry capture, KDM6 pre/post captures, and guarded run receipt as
arguments; it checks the receipt-bound executable and outputs, fixed
`PR63GEO2` record order, finite arrays, stage/timestep/bounds, tile coverage,
and source equations above. Replaying it against the same v2 run gives the
same geometry pressure residuals and both carrier totals as the independent
script. At the audited version, the CLI source SHA-256 is
`d0c0810a892f9344fe541a298822d8700b6ab23ef7df3d29e62284747d995615`; the
portable parser tests cover eleven valid and malformed-header/array cases,
including rejection when any pre/post scalar geometry metadata differs. The
0.01 Pa defaults are fixed numerical research-audit bounds for these recorded
geometry identities, not physical tolerances, a floating-point error proof,
or a scientific closure criterion. Derived map area and both mass measures
must be finite and positive before the CLI emits a report. Its
checked-in v2 replay is `docs/evidence/pr63_call_geometry_v2_20261006.json`
(SHA-256 `a83b5067b548595b8e805401bf7916cadbafeda21d358693628cfdaa65aa6499`).
Example:

```bash
python3 tools/native_kdm6_call_geometry.py \
  /var/tmp/pr63_native_transition_20261006/run_transition_v2/pr63_geometry.raw \
  /var/tmp/pr63_native_transition_20261006/run_transition_v2/kdm6_first_call_pre.raw \
  /var/tmp/pr63_native_transition_20261006/run_transition_v2/kdm6_first_call_post.raw \
  /var/tmp/pr63_native_transition_20261006/run_transition_v2/run-isolation.json \
  --expected-executable-sha256 d0b260a721f1df37c045ae08e7c5fe1d7b0c1e0d8f11cba9490e34f60f309c30
```


## Independent paired-run audit (2026-10-06)

Fresh guarded control and paired runs were independently audited from their
receipts and raw captures. The control receipt is
`/var/tmp/pr63_native_transition_20261006/run_pair_control/run-isolation.json`
(SHA-256 `bd8ea9ee3cdf475ae371ce9e2bd1cc637ea734c48601dde13a9cfb844a9458ae`);
the paired receipt is
`/var/tmp/pr63_native_transition_20261006/run_pair_paired/run-isolation.json`
(SHA-256 `0073caf9a11c4b2c66d528c769ee21ebba632d3a3bdcc92c0803e58a8a98a609`).
Each returned 0 and records input integrity/output isolation `PASS`, 104 inputs,
and 15 outputs. All input before/after hashes match; every declared output is
present, matches its receipt hash, and has `nlink=1`. No run-local input/output
inode aliases were found. The 103 non-executable input hashes match across the
pair. Shared immutable external runtime libraries and scripts are the same
host input inodes, not run-local outputs. The executables match both their run
receipt and build link products: control
`2a412690a6c6b4acdacfbf66507fae53406b4a1170403133b801e88a868a4e4e`, paired
`ee6d85d22597a1973dd551c9f33b3c5c7bb2f399a02300d6ad9da03a57c18155`.

The KDM6 call-entry raw capture is byte-identical between runs
(`d2331e90…`); the return captures differ (control `c1601094…`, paired
`ff39f3f7…`). I independently aggregated 280 latitude records (2–281) for
both before/after terminal-cutoff stages. Before cutoff both runs have 11
QG=0/BG>0 cells whose unweighted BG sum is `1.1734889742467643e-16`.
Across all cells with QG<=qcrmin, the unweighted BG sum is
`3.642089051517024e-9`. After cutoff, control has 2,465 ghost cells with
that latter BG sum, while paired has zero ghost cells and zero BG. These
sums of specific-volume values are not integrated volumes. The full post-call KDM6 arrays reproduce those counts. Both runs
retain one active cell with QC > 1e-15 and NC = 0; overall moment acceptance
therefore remains FAIL. The graupel paired change resolves the measured
terminal QG/BG ghost state in this one-rank, one-tile, 20-second research run;
it does not establish a closed budget, full physical initialization, or lower
initial shock/forecast error.

The reproducible independent audit is
`docs/evidence/pr63_pair_run_audit_20261006.json` (SHA-256
`dad423f13a81c185c8db417bd2f97ea4768dab75c2b0ab18c9c6dd4d5a886c02`). Geometry
replays bound to each receipt are
`docs/evidence/pr63_pair_control_geometry_20261006.json` (SHA-256
`59c55bd42b05006603ff6d1a27b05a1c98eee60325f5671035b269d459a2f34b`) and
`docs/evidence/pr63_pair_paired_geometry_20261006.json` (SHA-256
`8daa12dd69fb9f63ea83454564585c5e5958d08a9c319ddc039e4b45b9187ba1`). The
same-call geometry check reproduces the source-defined hybrid pressure and
mass identities. `DEN*DELZ*area` differs by +0.05856% from the hybrid dry-mass
measure and remains a diagnostic only, not a budget closure.

### Separate build-tree artifact incident

`/var/tmp/pr63_native_transition_20261006/artifact_incident_v2_kdm_object.json`
records an out-of-run build-tree mutation. The extracted helper object at
`build_cutoff_v2/link/module_mp_kdm6.o` had prior observed SHA-256
`522a1c07148f6fe027ab4071d817c02a20b4ac3417b1f2e86bf491609da34ec6`, then was
overwritten/restored from the independent `build_cutoff/link/module_mp_kdm6.o`
copy with SHA-256 `7717a8531a40b42fa46b9c7fe2be57a844e4692ab820dcf1728a0b3170c971f2`.
The triggering command was not recoverable. The current v2 archive member and
`run_transition_v2/wrf.exe` remain `7717…` and `d0b260a7…`; this incident is
outside the declared-output runtime guard, which does not protect build-tree
objects or undeclared writes. Keep the incident visible. The helper-object
history is not a fully reproducible source-to-executable chain.

For the later matched pair, source files record SHA-256
`2c3c77b262c928803140207e9bfcd79627101faa50de0d48bafefd1138a4675c` (control)
and `099b4a744c4f11f30ba2b50c23b551d9edd196d58d9813885398d3861e3fa040`
(paired). The archived KDM6 members are `de145f8c7393085beb03e841fccbf78fe0243ffc28d2148c139747e6cbe03ab3`
and `659a50b84906ba23c1e9265b0549cb774594ab33055fb9eb9b41d7506ceae00c`;
run executables have the receipt-bound hashes above. The separately staged
control object is `6c58c715dce54c2c83b0707ca0d83fc6b74055e8dadc5c4f3ef21c76f7f07ed6`,
which differs from its archive member; the paired staged object matches its
archive member at `659a50…`. Compile logs contain warnings but not an archive
command transcript. The source, archive-member, and executable byte identities
are recorded, but the complete control object-to-archive command chain is not
independently established here.
