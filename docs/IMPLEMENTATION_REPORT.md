# Cloud-BAL implementation report

Status date: 2026-09-02
Reference commit: the clean HEAD hash recorded in each hash-verified
`RUN_SUMMARY.json` and transaction manifest under the trusted single-user model

## Decision

The repository contains a tested **focused SHADOW candidate**, not an
operationally integrated Cloud-BAL release. `OFF` and `SHADOW` are the only
safe modes.  This research build does not compile an ACTIVE mode.  A future
promotion adapter must be reviewed separately after the canonical pipeline
replaces the linked legacy call graph, the complete KLAPS executables build,
and real-data end-to-end tests pass.

| Scope | Status |
|---|---|
| Canonical modules and engineering tests | conditional GO |
| Four prepared real hourly input sets | source inventory GO; direct QBAL closure BLOCKED |
| Legacy executable integration | NO-GO |
| Real KLAPS parallel experiment | NO-GO |
| Operational publication | NO-GO |
| Radar downdraft ACTIVE | NO-GO |

## Preserved comparison baseline

The pre-change comparison material is isolated at:

```text
scratch/baseline_legacy_0d4c9a8_20260816
```

It contains 21 independent, read-only ANAL/MODL/configuration/executable
payloads. `tests/run_isolation_gate.sh` verifies the exact archive inventory,
each declared live file against its immutable baseline digest, and full
live-tree metadata/ctime before and
after a command. Candidate output must start in a new or empty directory below
`scratch/candidate` and may contain no links or special files. This is an
integrity receipt, not an OS read-only sandbox; the current host does not allow
the available `bwrap` user namespace.

## Implemented focused candidate

Four new modules define one candidate contract:

```text
cloud_bal_state
  -> cloud_bal_column_physics
  -> cloud_bal_balance_operator
  -> cloud_bal_pipeline
```

`cloud_bal_grid_geometry` supplies the one cumulative-distance implementation
used by canonical and legacy localization, including bounded search-radius
conversion for extreme finite configuration values. The real-data boundary is
`cloud_bal_real_netcdf`; the legacy boundary is the diagnostic-only
`cloud_bal_legacy_shadow_adapter`. Neither adapter exposes ACTIVE authority.

- `cloud_bal_state` owns values, cell validity, quality/source flags, time,
  units, dimensions, dry-air mixing-ratio hydrometeors, grid measures, boundary
  fluxes, and optional post-QC radar LOS observations.
- `cloud_bal_column_physics` owns cloud-layer detection, cloud-support
  diagnosis, S-band reflectivity conversion, relative fall-flux
  reconstruction, and the explicit deposited/suspended/boundary/blocked/
  microphysical interface ledger. Missing omega never enters trajectory
  arithmetic. This is not a source-removing, global mass-transport claim.
- `cloud_bal_balance_operator` owns the discrete support, divergence, adjoint,
  face coefficients, matrix-free solve, update, and final residual. Connected
  support components receive compatibility and gauge treatment. Solver and
  state update use the same coefficients. One `omega_authorized` mask controls
  target, coefficient, correction, and publication; target-free omega cells
  and their metadata are bitwise unchanged. Exact and near-alternating
  pressure-face targets are rejected before the solve. The requested
  `omega_target` remains bitwise immutable; trust-region attenuation is
  recorded in the stage result instead of rewriting that target.
- `cloud_bal_pipeline` is the only candidate authority boundary.  This focused
  build accepts only `OFF` and `SHADOW`; every other integer is rejected.
  `OFF` is an exact no-op and `SHADOW` cannot modify the operational state.

Cloud type alone no longer fabricates a vertical-velocity amplitude or sine
profile.  It identifies local layer/regime support only.  A future nonzero
cloud-air-motion target requires a separately valid grid-mean dynamic driver
and uncertainty; neither is present in this focused snapshot.

The focused radar cooling/evaporation path remains disabled. Its legacy cloud
call also receives literal `.false.` after `w_3d` is initialized to zero, so
the focused source cannot publish empirical cloud bogus-W. The linked
production source is audited separately and remains a promotion blocker until
its source, binary, and ifx provenance all prove the same guard. Loading-only
downdraft is calculated for SHADOW diagnostics, but phase/fall-speed-uncertain targets do
not receive `SOURCE_DYNAMIC_TARGET` and cannot seed the wind solver. The
finite-difference divergent/vortical summaries are diagnostics, not a
Helmholtz decomposition or rotational acceptance gate.

Missing precipitation phase no longer changes category abruptly at one
temperature threshold. One bounded C1 rain/snow partition is shared by
hydrometeor allocation and terminal-velocity diagnosis; the fallback never
creates graupel from temperature alone. Explicit analyzed phases remain
unchanged.

The legacy LAPSPREP water-only saturation transfer is also default-disabled;
requesting a positive `LWC2VAPOR_THRESH` now fails until the canonical coupled
water/latent-heat adapter is linked.

Targeted legacy safety fixes are also present:

- the legacy `get_laps_3d_analysis_data` ABI is preserved; qbal alone calls
  `get_laps_3d_analysis_data_ex` for the independent cloud-omega status;
- the legacy background caller checks that 3-D status immediately, before any
  later 2-D read can overwrite it;
- integer lightning data use a logical validity mask instead of a real missing
  sentinel;
- the first and subsequent balanced-output writes propagate failures;
- WPS output validates projection/wind coordinates and OPEN/WRITE/CLOSE status;
- the legacy radar vertical-motion switch is forced off;
- WPS wind coordinates are declared explicitly, not hard-coded;
- the baseline comparator rejects duplicate/truncated recognized fields.

`tools/cloud_bal_transaction.py` stages declared products, verifies hashes,
writes a manifest and completion marker, renames the generation, and only then
uses a cooperative-process atomic switch for the `current` pointer. Its commit identity is a validated
40-hex declaration; repository-HEAD equality remains a coordinator/clean-CI
gate. It is a publication primitive; the legacy multi-writer call paths have
not yet been migrated to it.

## Verification completed

Run the focused checks with:

```bash
tests/run_unit_tests.sh
tests/run_transaction_gate.sh
tests/run_isolation_gate.sh scratch/candidate/local/noop
tests/run_real_input_inventory.sh
```

The current suite covers canonical state rejection, target metadata and
missing/range handling,
column conservation cases, compact disconnected support, balance rollback,
nonzero-background total-residual projection, OFF identity, SHADOW
no-authority, WPS and balanced-writer failure injection, transaction context
and product tamper containment, masked-integer NetCDF/comparator parse failures,
independent comparison roots (no self/symlink/hardlink alias), a clean-source
three-repeat synthetic reproduction probe, and explicit PARTIAL status when
the preserved legacy executable cannot be rerun,
the retained legacy unit tests, and a fixed-form syntax compile of `qbalpe.f`.
The complete focused Fortran suite now uses only the pinned Intel ifx 2026
profile with strict floating-point exceptions.  That gate exposed and then
verified the explicit missing-omega trajectory fallback; no GNU compiler
fallback remains in the focused test scripts.

`tests/run_real_input_inventory.sh` validates the hashes, dimensions, fields,
units, pressure levels, UTC valid/reference times, and radar/TID summaries for
the prepared 2026-08-16 12/13/14/15 UTC FUA, FSF, pre-QBAL LW3, VRZ and VRT
sets.  All four prepared sets pass.  The same check deliberately reports the
direct QBAL closure as `BLOCKED` because original-chain LT1, LQ3, LCO and LSX
have not yet been regenerated.  It also hard-rejects final bigfile, `LAPS:*`,
`KLBG:*`, `met_em`, LAPSPREP and post-QBAL balance paths as inputs.  The exact
source-derived contract is `docs/QBAL_REAL_INPUT_CONTRACT.md`.

`tools/original_upstream_replay.py` materializes the declared upstream inputs
as independent read-only scratch copies and emits a pre-QBAL receipt. For all
four hours it verifies VRT completion before temperature use, but deliberately
never executes a production binary. LT1/LQ3/LCO/LSX therefore remain
`NOT_PRODUCED`, and the direct-QBAL checker correctly remains BLOCKED instead
of accepting copied downstream products as evidence. A symlink or multiply
linked file anywhere in the declared source tree is also a blocker. Its
computed tree hash is a receipt, not yet an external promotion pin.

The same four hours can be run through the radar-only canonical SHADOW adapter
using Intel ifx.  The authoritative result is not copied into this report: it
is the hash-verified generation produced by the clean-HEAD runner under the
documented trusted single-user model.
Per-case numerical reports independently reconstruct localization, `D*S` continuity
increments, operator identity, interface flux closure and the Fortran
acceptance bitset.  Rejected candidates remain diagnostic evidence; they do
not change operational arrays or become scientific successes.

`tests/run_real_shadow_cases.sh` now writes all four cases into one hash-verified
generation through staging, per-case independent validation, a hashed
manifest, completion marker and cooperative-process atomic `current` switch.
It requires a clean exact-head worktree and reports artifact validity separately from the
candidate decision.  `tests/run_real_shadow_figures.sh` uses one deterministic
level/cross-section rule for every case and produces eight diagnostic
background/proposal/difference figures. These are explicitly not operational
original-versus-candidate comparisons. Each figure states whether dynamic
balance was evaluated or the result is hydrometeor-only with wind modification
unauthorized.

The focused real reader now rejects every required variable whose numeric
type, rank, or dimension order differs from the NE57 contract; a full-size
permuted-axis LW3 negative test is part of the pinned Intel suite. Surface
coverage must be complete, observed no-echo remains distinct from missing
radar data, and an unchanged pre-existing target is not mislabeled as a new
column change.

The standalone numerical validator deliberately labels its artifact authority
`UNBOUND`.  Only the hash-verified generation verifier may combine that numerical
result with product hashes, source commit, input manifest and build receipt and
call the generation valid evidence.

`tests/run_radar_velocity_audit.sh` reads all ten prepared radar velocity grids
for every hour and maps native levels to diagnostic levels by pressure value.
Usable radial velocities exist, but usable Nyquist values are zero in all 40
files, the files lack an internal S-band wavelength identity, and the LW3
grid-relative/earth-relative wind contract is unresolved.  The audit therefore
publishes coverage counts but no projected-wind RMS.  Radial velocity remains
diagnostic-only; it supplies neither update nor held-out acceptance authority
until wind coordinates, dealiased/Nyquist/uncertainty, beam,
wavelength, and hydrometeor-fall-speed provenance are one contract. Exact
audit numbers belong only to the committed generation, not this report.

`tests/run_reproduction_comparison.sh` is not in the passing verification
list.  It records available diagnostic receipts but exits nonzero until an
actual isolated legacy rerun and real candidate comparison both complete; the old
`--allow-partial` success escape has been removed. An incomplete run also
cannot write `DIAGNOSTIC_COMPLETE`.

`tools/prepare_operational_comparison.py` defines the later plotting-input
contract. “Original” means archived products made by the operational KLAPS
chain, never the canonical background array. It requires distinct
`REAL_OPERATIONAL_ORIGINAL`, `SHADOW_CANDIDATE`, and
`OPERATIONAL_UNCHANGED` roles plus matching hashes, time, grid, projection,
levels, units, staggering, wind coordinates, and valid masks. It emits no
comparison arrays while any pair is incomplete. The present inventory is
therefore `NOT_READY`; no background/candidate diagnostic plot is represented
as an operational before/after comparison. Candidate evidence must use the
exact `radar-only-shadow-ifx-2026-v3` configuration and a met_em product must
contain exactly one `Times` record. Empty or diagnostic/background/synthetic
embedded authorities, duplicate product/time pairs, duplicate WPS record
identities, and artifact reuse across pairs are rejected.

The focused suite is pinned to Intel ifx 2026. The read-only integration audit
also confirms that this does not imply a full production Intel build: the
three selected KLAPS binaries retain legacy ifort signatures, contain no
canonical adapter symbols, and lack a closed NetCDF/HDF5 runtime on this host.
Full production ifx linkage remains BLOCKED.

Passing these tests does **not** prove a complete KLAPS build, NetCDF/WPS
round-trip fidelity, real-observation coverage/freshness, cold-start forecast
impact, or compiler/platform reproducibility.

## Integration blockers

The old modules and call sites remain reachable:

```text
cloud_bal_field_contracts
cloud_bal_moisture
cloud_bal_cloud_profiles
cloud_bal_localization
cloud_bal_radar_downdraft
cloud_bal_wind_modes
```

Production `qbalpe`, derived-cloud, and LAPSPREP paths still use parts of that
legacy/candidate-v1 graph. The canonical four-module pipeline is therefore not
yet the linked single source of truth. Replacing only one solver or one update
would mix operators; the full read -> candidate -> gate -> publish transaction
must be switched atomically.

In particular, production derived-cloud still calls the legacy cloud-profile
path with `l_flag_bogus_w=.true.`, and production qbal still builds a 30--60 km
COM-centered support.  Therefore this branch has **not** yet fixed the reported
broad wind deformation in the operational executable.  The real-data v3
SHADOW adapter instead authorizes no dynamic target and changes no wind.

Other release blockers are:

1. no complete KLAPS link or linked-symbol reachability audit;
2. no full canonical NetCDF/WPS field-contract adapter and round-trip test;
3. no full-QBAL real-data zero-skip comparison or cold-start experiment;
4. no full hydrometeor/water/enthalpy transaction in the operational path;
5. no multi-product migration to generation-based atomic publication;
6. no protected branch, required CI, signed validation manifest, or promotion
   evidence for the exact commit.

The original input audit adds these concrete blockers:

7. the original background selector can choose among equal-valid-time cycles
   by file-list order and checks only the last field status;
8. the original cloud/derived chain can blend model reflectivity into `LPS`,
   assign Cb/updraft outside radar coverage, reuse stale COM, and return a
   normal process exit after required-input failure;
9. upstream VRT ordering is checked by the non-executing replay harness; the
   focused reader distinguishes observed `-10 dBZ` no-echo provenance from
   missing coverage, but the files still carry no S-band/site provenance;
10. the full original Intel build still lacks a pinned ABI-compatible
    NetCDF/HDF5/runtime bundle and clean out-of-source link proof.
11. the collocated A-grid normal operator retains horizontal parity gauges;
    checkerboard control or native face velocity degrees of freedom are needed
    before any balance ACTIVE mode;
12. cumulative physical distance is implemented and regression-tested for
    nonuniform localization, but the focused real adapter still accepts only
    its verified NE57 grid until another real-grid case is archived.

The second eight-agent cross-review keeps several promotion gates open: radar
flux lineage still needs a persisted per-source ledger plus permutation test,
and terrain-aware top/bottom boundary fixtures are required. The standalone
publication primitive rejects
deterministic symlink and hardlink escapes, but concurrent parent replacement
requires a directory-fd coordinator before production use.

`docs/RELEASE_CHECKLIST.md` is the authoritative short checklist;
`docs/PIPELINE_SIMPLIFICATION_PLAN.md` retains the detailed derivation and
review history. Documentation must keep “source implementation”,
“linked integration”, and “scientific/operational validation” as separate
claims.
