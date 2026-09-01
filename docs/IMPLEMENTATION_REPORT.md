# Cloud-BAL implementation report

Status date: 2026-09-01
Reference commit: `cb0a5713f1acd737fa9a058f9d32adedf71bd9d1`

## Decision

The repository contains a tested **focused SHADOW candidate**, not an
operationally integrated Cloud-BAL release. `OFF` and `SHADOW` are the only
safe modes.  This research build does not compile an ACTIVE mode.  A future
promotion adapter must be reviewed separately after the canonical pipeline
replaces the linked legacy call graph, the complete KLAPS executables build,
and real-data end-to-end tests pass.

| Scope | Status |
|---|---|
| Canonical modules and synthetic tests | conditional GO |
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
payloads. `tests/run_isolation_gate.sh` verifies the archive checksums and the
live ANAL/MODL hashes before and after an isolated command. Candidate outputs
must be below `scratch/candidate`; the gate rejects protected output paths.

## Implemented focused candidate

Four new modules define one candidate contract:

```text
cloud_bal_state
  -> cloud_bal_column_physics
  -> cloud_bal_balance_operator
  -> cloud_bal_pipeline
```

- `cloud_bal_state` owns values, cell validity, quality/source flags, time,
  units, dimensions, dry-air mixing-ratio hydrometeors, grid measures, boundary
  fluxes, and optional post-QC radar LOS observations.
- `cloud_bal_column_physics` owns cloud-layer detection, cloud-support
  diagnosis, S-band reflectivity conversion, relative
  fall-flux transport, and the explicit deposited/suspended/boundary/blocked/
  microphysical ledger. Missing omega never enters trajectory arithmetic.
- `cloud_bal_balance_operator` owns the discrete support, divergence, adjoint,
  face coefficients, matrix-free solve, update, and final residual. Connected
  support components receive compatibility and gauge treatment. Solver and
  state update use the same coefficients.
- `cloud_bal_pipeline` is the only candidate authority boundary.  This focused
  build accepts only `OFF` and `SHADOW`; every other integer is rejected.
  `OFF` is an exact no-op and `SHADOW` cannot modify the operational state.

Cloud type alone no longer fabricates a vertical-velocity amplitude or sine
profile.  It identifies local layer/regime support only.  A future nonzero
cloud-air-motion target requires a separately valid grid-mean dynamic driver
and uncertainty; neither is present in this focused snapshot.

The radar cooling/evaporation path remains disabled. Loading-only downdraft is
calculated for SHADOW diagnostics but has no publication authority. The
finite-difference divergent/vortical summaries are diagnostics, not a
Helmholtz decomposition or rotational acceptance gate.

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
writes a manifest and completion marker, renames the generation atomically,
and only then changes the `current` pointer. Its commit identity is a validated
40-hex declaration; repository-HEAD equality remains a coordinator/clean-CI
gate. It is a publication primitive; the legacy multi-writer call paths have
not yet been migrated to it.

## Verification completed

Run the focused checks with:

```bash
tests/run_unit_tests.sh
tests/run_transaction_gate.sh
tests/run_isolation_gate.sh scratch/candidate/local/noop
```

The current suite covers canonical state rejection, target metadata and
missing/range handling,
column conservation cases, compact disconnected support, balance rollback,
nonzero-background total-residual projection, OFF identity, SHADOW
no-authority, WPS and balanced-writer failure injection, transaction context
and product tamper containment, masked-integer NetCDF/comparator parse failures,
the retained legacy unit
tests, and a fixed-form syntax compile of `qbalpe.f`.

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

Other release blockers are:

1. no complete KLAPS link or linked-symbol reachability audit;
2. no canonical NetCDF/WPS field-contract adapter and round-trip test;
3. no real-data zero-skip smoke/cold-start experiment;
4. no full hydrometeor/water/enthalpy transaction in the operational path;
5. no multi-product migration to generation-based atomic publication;
6. no protected branch, required CI, signed validation manifest, or promotion
   evidence for the exact commit.

The second eight-agent cross-review also keeps two numerical promotion gates
open: the physical full-state residual must represent lateral/support-edge
background flux independently of the zero increment boundary, and radar flux
lineage still needs a persisted per-source ledger plus permutation test.
Accepted attenuation/attempt diagnostics and nonzero top/bottom boundary
fixtures are also still required. The standalone publication primitive rejects
deterministic symlink and hardlink escapes, but concurrent parent replacement
requires a directory-fd coordinator before production use.

`docs/PIPELINE_SIMPLIFICATION_PLAN.md` is the authoritative checklist for
closing these blockers. Documentation must keep “source implementation”,
“linked integration”, and “scientific/operational validation” as separate
claims.
