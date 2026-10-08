# PR71 ProgB particle output contract

This research patch gives `ProgB_param` a defined output contract and carries that validity through all seven `KDM62D` call sites. It also fixes one observer read in the generated source: stage zero now serializes the current named ice mass-velocity rate (`mass_velocity_rate(:,:,4)`) rather than the legacy `work1(:,:,4)` slot, which is unassigned after the PR68 field split. The named rate is in s^-1. This changes observer-field semantics only; it does not change model calculations. The patch is generated only against the frozen PR70 composed source and does not change the maintained/native source tree.

## Status and output behavior

`progb_status(i,k)` has four values:

| Value | Meaning | Behavior before property consumption |
|---|---|---|
| `PROGB_ABSENT` | `qg == 0` and `bg == 0` exactly | All 18 `INTENT(OUT)` properties are initialized to zero; graupel slopes are inert and zero. |
| `PROGB_TRANSIENT` | Positive paired values with `qg <= qcrmin` and `bg <= brs_min` | Reject the research run with `ERROR STOP` before a consumer reads the outputs. |
| `PROGB_PSD_ACTIVE` | Positive finite paired values with `(qg > qcrmin OR bg > brs_min)`, raw `qg/bg` within inclusive `[100,900]`, and finite derived properties | Consumers may read the properties. |
| `PROGB_UNSUPPORTED` | Orphan, negative, nonfinite, out-of-range, or nonfinite-derived state | Reject the research run with `ERROR STOP` before a consumer reads the outputs. |

`ProgB_param` first assigns zero to every output on every invocation. The zero values are storage initialization only; status controls whether a property is usable. `brs` is preserved for absent, transient, and unsupported inputs. For active inputs the original single-precision ratio expression is retained after a strict binary64 admission check, and the active `brs` rewrite remains `qg/rhox`.

Classification checks the transient gate before the PSD density interval.
A tiny paired state can therefore be `PROGB_TRANSIENT` even if its ratio is
outside the density table. That status does not declare a supported density
or authorize a downstream property consumer.

The strict raw-ratio admission is a conservative research policy change from the prior clamping behavior: ratios outside `[100,900]` now reject rather than being rewritten to an endpoint. No density is inferred, floored, clipped, or substituted. The endpoint comparison uses the actual single-precision input values promoted to binary64; this deliberately adds no tolerance.

All seven `ProgB_param` calls and their paired `slope_kdm6` calls pass status. The slope routine rejects transient and unsupported states before property reads. The two `n0go` property calculations and every graupel rate gate require active status. Density-based process conversions have explicit active/absent branches, and the final graupel extinction cleanup marks the state absent, clears all 18 properties, and zeros `n0go` so a prior active snapshot cannot be consumed afterward. The two reads of `rhox` before a `ProgB_param` call were removed.

## Exact source and generated artifacts

Input composed source SHA-256: `487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583`.

Generated patch SHA-256: `94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45`.

Patched source SHA-256: `5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41`.

The previous base patch and inventory are retained under `/var/tmp/pr71_output_contract_v1_archive/`; the previous validation receipt remains unchanged. The new validation receipt uses a distinct `observer_fix` filename.

The generator records all 18 output names, their declarations, initialization and production expressions, finite checks, call actuals, and source-level consumers in [`pr71_particle_output_contract_20261008.output_inventory.json`](evidence/pr71_particle_output_contract_20261008.output_inventory.json). The inventory records all seven `ProgB_param` and `slope_kdm6` call locations in the transformed source.

## Validation

Run `tests/run_pr71_particle_output_contract.sh`. It recomposes the pinned PR70 source, verifies the frozen source and process-patch hashes, emits and applies the research patch with zero fuzz, runs seven source-contract checks, and compiles/runs a test harness extracted from the transformed `ProgB_param` routine.

Validation used the pinned Intel profile in `tests/intel_toolchain.sh` (`ifx 2026.0.0 20260331`) from a fresh `/var/tmp` directory. The source checks passed and the harness printed `PR71_PROGB_OUTPUT_CONTRACT_PASS`. The current receipt is [`pr71_particle_output_contract_20261008_observer_fix.json`](evidence/pr71_particle_output_contract_20261008_observer_fix.json); it binds the compiler profile, generator, test, runner, extracted harness, executable, argv, and absolute log paths. It points to `/var/tmp/pr71_particle_output_contract.14hArX`. The earlier receipt is retained unchanged as evidence for the pre-fix patch.

The extraction harness covers exact absence, transient values, zero-sided orphans, negative and nonfinite inputs, out-of-range density, and active values at both supported endpoints. It also executes the exact absent graupel-slope assignments from `slope_kdm6` and the exact status-gated `n0go` branch with `rslopemu=0`, confirming the absent case clears both slope outputs and the stale number concentration without dividing. The endpoints use exactly representable single-precision values with small positive magnitudes. Its local `rgmma` stub calls Fortran's intrinsic `gamma`; the harness validates the source-extracted `ProgB_param` and the two isolated status branches, not the full module's gamma helper or whole-module integration. A first compile exposed a missing formula-block `endif`; that attempt is retained under `/var/tmp/pr71_particle_contract_20261008/build9`. A first endpoint test also showed that the decimal pair `9e-6/1e-8` has a promoted single-precision ratio slightly above 900 and is correctly rejected. Earlier compile/run logs are preserved in the adjacent `/var/tmp/pr71_particle_contract_20261008` work directory.

## Limits

This patch defines and guards the particle-property output contract. It does not establish that graupel physical generation is paired with a corresponding source, close the water or energy ledger, or resolve the freezing-domain audit. `ERROR STOP` rejects unsupported research states; it is not rollback. The patch is a generated research candidate and has not been merged into maintained source.

The maintained Graphify corpus was inspected for navigation. It has no extracted ProgB/KDM6 relationship for this source path, so it did not provide source-specific navigation and no Graphify/KG snapshot was changed by this scratch-only batch. Graph freshness would not establish runtime or scientific validation.
