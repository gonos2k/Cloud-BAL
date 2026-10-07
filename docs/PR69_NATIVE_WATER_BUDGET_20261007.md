# PR69 source-carrier water accounting observer

This research-only observer was built from the PR68 final4 KDM6 source
(`8429adf9182ee979219ffc43a84706d1cab3d81dab2fd35012b463454a13f5da`). It
records six water species on the source `DEND*DELZ` carrier at five ordered
cutoffs and records the four bottom sedimentation rates at cutoffs 2–4. The
generated source delta is
[`observer_v6.patch`](evidence/pr69_native_water_20261007/observer_v6.patch).

## Source-order and initialization audit

The audit was performed on generated source v6, SHA-256
`77c83992949f8a8373a72240d167dca03a2a74309a555e9440ccd4c03e633f73`.

| Capture | Placement and initialized operands |
| --- | --- |
| Entry | Before the first hydrometeor clamp. Reads `Q`, `QCI`, `QRS`, input `DEN`, and `DELZ`; it does not read `DEND`, `FALL`, `DENR`, or `DTCLD`. |
| Post cleanup | After the five `MAX(...,0)` hydrometeor clamps and after the source copies `DEN` to `DEND`. The observer still uses passed `DEN`; it does not rely on the copy. Optional flux operands are omitted. |
| Post mixed precipitation sedimentation | After the rain, snow, and graupel sedimentation loop has accumulated `FALL(1:3)`. `FALL(4)` was explicitly initialized to zero before the loop. `DEND` was initialized from `DEN`; `DELZ`, input `DENR`, and `DTCLD` are defined. |
| Post first ice substep | After the first ice sedimentation substep updates `FALL(4)` and the hydrometeor state. `DEND`, `DELZ`, `DENR`, and `DTCLD` remain defined. |
| KDM6 return | Before return, after the complete call; all captured states and bottom fluxes have been initialized and evolved by source code. |

The bottom-export replay uses the source equation `sum(FALL(1:4) * DELZ(kts) /
DENR * DTCLD * 1000) * mapped_area`. No `WORK2` operand is captured or used in
this equation. `WORK2` is a separate in-column vapor tendency in KDM6 and is
not a bottom-flux diagnostic. The capture helper defaults flux metadata to
zero at entry/cleanup and only dereferences optional `FALL`, `DENR`, and
`DTCLD` when stage is at least 2. It passes no undefined optional actuals on
the first two calls. The parser rejects captures with missing, reordered, or
nonfinite records.

## Result

The successful observer run reports the following mapped source-carrier
ledger, with kg-valued fields retained for compatibility:

| Cutoff | Total source-carrier measure (kg units) | Source-equation bottom increment (kg units) | Storage plus increment diagnostic (kg units) |
| --- | ---: | ---: | ---: |
| Entry | 93,004,858,222,445.00 | 0 | 0 |
| Post cleanup | 93,004,860,348,557.84 | 0 | +2,126,112.845 |
| Post mixed sedimentation | 93,004,361,413,731.80 | 498,931,427.550 | +2,122,714.347 |
| Post first ice substep | 93,004,361,413,836.03 | 498,931,427.550 | +2,122,818.582 |
| KDM6 return | 93,004,361,203,131.56 | 498,931,427.550 | +1,912,114.113 |

The earliest measured source contribution is the cleanup assignment
`qci(i,k,1)=max(qci(i,k,1),0.0)`: it increases mapped QC storage by
2,126,112.845 source-carrier kg units. Subsequent interval residuals are
−3,398.492 source-carrier kg units through
mixed precipitation sedimentation, +104.240 source-carrier kg units through
the first ice substep, and −210,704.495 source-carrier kg units through the
remainder of KDM6. These interval
values use the same source-carrier kg units. The residuals are
measured terms; they are not assigned to clipping, rounding, or an inferred
source.

These are source-measure accounting values, not established physical water
masses or whole-water closure. The reviewed host `moist_physics_prep_em` forms
moist `DEN = rho = 1/ALT*(1+QV)`, while the public specific-water fields are
declared per kg dry air. The product of passed `DEN` with the KDM6 water mixing
ratios is therefore not proven to be the physical dry-air water carrier. The
precipitation increment is replayed from the selected KDM6 source equation;
comparing it with source-carrier storage is a diagnostic only. Physical
water-mass interpretation remains unsupported until the selected call's
density routing is resolved.

The independent endpoint carrier calculation promotes both source float
operands before subtraction. Its source-carrier storage change is
−497,019,313.399370 kg units, giving +1,912,114.151076 kg units after the
source-equation bottom increment. The staged checkpoint ledger gives
+1,912,114.112946 kg units, a 0.038130 kg-unit reduction-order difference. A
prior replay that subtracted float32 operands before promotion yielded
1,912,245.085 kg units and is excluded as a subtraction artifact. No numerical
closure tolerance is inferred from these differences.

The PR67 hybrid dry-mass focused budget independently reports +6,529,669.629
kg on its hybrid carrier; this is a different call-budget measure and is not
combined with the native `DEND*DELZ` ledger. Native energy remains
`UNSUPPORTED`: this observer does not capture a complete source-defined
energy measure, pressure work, or kinetic energy. THPII alone is not an energy
closure quantity.

## Build and replay evidence

The build used the pinned `tests/intel_toolchain.sh` Intel ifx 2026 profile in
fresh `/var/tmp/pr69_water_native_20261007/build6`, then replaced one KDM6
member in the retained partial-closure PR68 archive. Object and archive-member
SHA-256 values match. The linked executable was copied as a one-link file to
the guarded fresh run directory. The run returned 0 with input integrity and
output isolation both `PASS`. Exact source/object/archive/executable/input
and raw-capture hashes are in the copied
[`native_water_budget.json`](evidence/pr69_native_water_20261007/native_water_budget.json),
[`build_provenance.json`](evidence/pr69_native_water_20261007/build_provenance.json),
and [`run_receipt.json`](evidence/pr69_native_water_20261007/run_receipt.json).
The file hashes and external raw-capture identity are summarized in
[`artifact_manifest.json`](evidence/pr69_native_water_20261007/artifact_manifest.json).
The guarded raw captures remain in the receipt-bound `/var/tmp` run directory.

Replay: `python3 tools/pr69_water_budget.py --water <pr69_water.raw> --geometry
<pr63_geometry.raw> --pre <kdm6_first_call_pre.raw> --post
<kdm6_first_call_post.raw> --process <pr67_kdm6_process.raw> --receipt
<run_receipt.json> --source <module_mp_kdm6_pr69_water_v6.f90>
--source-sha256 77c83992949f8a8373a72240d167dca03a2a74309a555e9440ccd4c03e633f73
--selected-source-sha256 8429adf9182ee979219ffc43a84706d1cab3d81dab2fd35012b463454a13f5da
--build-provenance docs/evidence/pr69_native_water_20261007/build_provenance.json
--output <report.json>`.

The source-bound observer was composed onto frozen joint-process source
`fbfa823b7cba54f0fdd5ffb1cfeaf58fc5722e845508f954e6c992a7aa32a594`, then used
in one guarded native attempt. The candidate rejected its first selected KDM6
call at `(i,k)=(125,17)`; `j` was not captured. `pgdep=-7.6110288e-16` with
`rhox=0` made BG partner-rate support false, so the fraction helper and later
PSD/cutoff checks were skipped.
The run had input integrity PASS but ended before the required post-call
capture. The printed small QI value was not evaluated as a cause. No successful
candidate budget replay or closure is claimed. Build/run identities and the
rejection are bound in
[`pr69_coupled_process_native_20261007.json`](evidence/pr69_coupled_process_native_20261007.json)
and [`candidate_composition.json`](evidence/pr69_native_water_20261007/candidate_composition.json).
The earlier `fda620` attempt remains separately excluded because it read
`bracs`, `bgaci`, and `baacw` before their source recomputation.

Two failed observer generations are retained in `/var/tmp`: v4 read
`DEND` before assignment and is invalid; v5 passed undefined optional actual
arguments at entry/cleanup and is superseded. Neither result is used here.
An earlier v3 run had no complete guard receipt. The successful v6 run is
neutral against the PR68 final4 observer for process raw products; one
diagnostic-only uninitialized `DTCLD` field in 25 pre-process PR68 rain rows
differs due to changed stack layout. The geometry, KDM6 pre/post, process,
transition, QC, and donor-face products are byte-identical. That field is
excluded from the source-carrier ledger.

The v6 receipt predates the stricter runner checks added in this work; its
historical output-isolation check only recorded link counts. The current
runner rejects symlinked run-directory parents, staged inputs or executable,
checks every post-run artifact with `lstat`, requires nonempty mandatory
captures/logs/output, and uses fail-fast environment setup. Injected-run tests
exercise missing captures, a symlink output, and executable replacement. The
read-only shell bootstrap check loads pinned Intel and MPI environments,
verifies `ifx`/`mpiifx`, and does not launch WRF; its command and output are in
[`runtime_bootstrap.json`](evidence/pr69_native_water_20261007/runtime_bootstrap.json). The
retained v6 outputs were independently rechecked as regular one-link files;
the details are in
[`legacy_receipt_recheck.json`](evidence/pr69_native_water_20261007/legacy_receipt_recheck.json).
The run was not repeated solely to replace its historical receipt.

The compiler's exact argv was not retained in the v6 build directory. Its
compile log, source/object hashes, pinned profile, archive-member equality,
full linker argv, executable hash, input receipt, and output receipt remain
available. The provenance record marks this compile-argv gap explicitly.

`tests/test_pr69_water_budget.py` verifies Fortran-order decoding and rejects
reordered or truncated checkpoint records. Native energy, upstream/downstream
boundaries, other timesteps, and whole-model water closure remain unsupported.
