# PR91 — host storage and repeated consumption (2026-10-20)

## Latest candidate: C14

| Identity / gate | Status |
|---|---|
| Preserved reference | PR90/C7, `3a896be3d381909f0cc61d1c0896b329b98d5aea`: OFF and COUPLED 180s / nine KDM6 calls |
| Latest candidate | C14: source-prepared diffusion, FogDES contract, and explicit inactive-ice storage option |
| Executable SHA-256 | `5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be` |
| Paired 240s requests | C14 RUNNING; no completion claimed |
| Same-candidate 600s | NOT_RUN_PENDING_240S |
| Configuration | Pinned Intel selected-object partial-host; one domain, rank, thread and tile |
| Scientific approval | OPEN / FAIL_OPEN |

C13 is not an accepted replacement for C7. Its T9/RK2 full candidate fails for an inactive ice storage case and five near-boundary graupel cases in OFF (four graupel cases in COUPLED); the existing graupel fallback first rejects the ice pair. Exact source/store replay is in progress. No density or storage tolerance is widened.

The successful C7 reference is preserved. Failed C9/C10/C12 repairs and the OFF-only C11d diagnostic are separate identities; none replaces C7. C12 completed two steps (40s) but failed at T3/RK3. Its known failure was not sent through another 600s request. See the [closed C12 audit](evidence/pr91_source_store_contract_20261020/c12/runtime/closed_runtime_audit.json) and [investigation history](evidence/pr91_host_store_20261020/investigation_history.md).

## What the original six failures mean

The D3 diagnostic reproduces C7 OFF's first 73 state records through T9 POST_KDM6 byte-for-byte (7,537,409,380 bytes), then reaches its T10 failure. The six selected coordinates yield 17 actual failed-store records across baseline/source-first attempts and RK stages. Pinned Intel O0/O2 replay reproduces all exact candidates, stages, adjustments and sentinels: 15 graupel stage-2 strict mass failures and two cloud stage-3 continuous volume failures. This is targeted diagnostic coverage, not a domain-wide failure count.

The graupel-only certification/fallback already exists. Its control flow permits source-first cloud handling; no new graupel correction or density tolerance is introduced. The cloud physical-source endpoint itself is representable under the existing temporary mean-mass contract. Adding a horizontal-diffusion term evaluated on the old field can invalidate the prepared donor before air transport. C8's attempted final-volume check at the temporary endpoint was premature and remains absent from C14.

The failed-store trace records the optional `failure_stage` at the real host call, exact operands/options, and rollback sentinels. A sentinel -1 is never evidence that -1 was committed to the model. The trace's six-coordinate selection is diagnostic only; the physical repair has no coordinate-specific condition.

## Producer contributions remain distinct

The source-first path completes its physical-source REAL32 interior field, then evaluates the existing horizontal-diffusion operator on that field using the saved RK1 producer geometry. The inherited outer donor ring remains explicit old-time boundary data. No source is invented on unused halos, and closed-boundary conservation is not claimed.

At the actual RK1 producer C12 retains REAL32 tendencies before and after diffusion. Before the original coupled tendencies are overwritten, it computes

```text
nonD64 = (REAL64(final32) - REAL64(afterD32))
       + (REAL64(beforeD32) - REAL64(original_coupled32))
source_first_rate64 = nonD64 + D(prepared)
```

The parenthesized differences matter. The discarded C10 expression subtracted a large old diffusion term and erased a positive incoming Q while retaining N. The C11d native-stencil replay identifies that exact arithmetic failure; C12 removes the cancellation rather than adding precision or a floor.

The normal candidate path is unchanged. Producer identity, timestep, RK, bounds, all four channel-ready flags and active-footprint finite checks guard the caches. The extra before/after and non-diffusion fields cost 64 bytes per memory-grid point, beyond the earlier four-channel REAL64 old-diffusion cache. The embedded kernel retains its existing REAL128 internals and REAL32/REAL64 API.

`dt * [D(prepared)-D(old)]` is a proposed operator-evaluation difference in pressure-coordinate units. A matching feasible joint commit proves the candidate path was used; that ledger is not an isolated stored-inventory increment, global kg budget, phase transfer, or rounding-only term. Final all-pair commit/rollback, strict stores and air-transport ratio-one requirement remain in force.

## FogDES approves the same state the host consumes

C12's T3/RK3 source candidate serializes as Q `3E4048B6F24832C2`, N `413B9F5F69B64B8F`. The lower mass bound is `3CF2DD58BFD7689A`; Q/N is `3CF2DD58BFD76899`. The binary64 product `m_min*N` rounds to Q, so the old FogDES cross-product comparison passes. The host's strict quotient comparison rejects it at stage 2. This temporary source call has **no volume-number bounds**; the earlier volume-enabled standalone probe is not its actual call.

C13 calls the existing `joint_moment_store` inside FogDES `candidate(theta)` after stored tendency, sidecar reconstruction and source endpoint arithmetic. It uses the host's strict mean-mass, normal-Q adjustment and joint-quantum options, without prematurely imposing the final KDM6 volume contract. Candidate-at-zero, bisection and the final selected scale are still checked. The same accepted column factor scales Q/N fluxes and ground sinks. No tolerance, number floor, density-limit change or isolated component repair is added.

In the matched COUPLED T3 column summary, theta changes from `0.0029400507919490337` to `0.0029400505591183901` and remains positive. Incoming summary fields match while outgoing fields change. The [bounded live-prefix comparison](evidence/pr91_science_sources_20261020/c13_source_correction_row/README.md) is direct producer-ledger evidence, not proof of identical primitive inputs or whole-run completion.

The correction sidecar originates in PBL and is updated by FogDES; its variable name does not identify PBL as the failure's producer. Trial density uses the source's per-level dry-density expression. Equality to future host AL/ALB density is not assumed; the host still rechecks its actual state.

## Bounded inactive-ice representation

C13's T9/RK2 ice candidate has exact Q/N words `3688C8D426312D82` / `39E15693A166AD9C`. Q rounds to zero, while N exceeds the existing paired-zero cap. The existing graupel fallback rejects this ice pair before it can complete the full transaction; this is distinct from a new graupel physics defect.

C14 adds an explicit, default-off inactive-Q storage option. It permits a positive Q smaller than the binary32 minimum quantum to be represented by that quantum, retaining rounded N, only under the declared inactive cutoff and positive finite stored number-volume conversion. It does not expand the paired-zero N cap or active PSD bounds. The default inactive-Q underflow rejection remains. Adjustment 4 has a distinct count and signed Q/N residual in the final grouped storage ledger; fallback counters and arrays commit only together after feasibility.

This is a numerical representation policy, not nucleation or phase change. Source-first endpoint storage uses the same opt-in, but its changes belong to the existing aggregate `SOURCE_REPRESENTATION` pressure-coordinate difference; that aggregate also contains other producer changes and is not an isolated quantum correction or a kg inventory budget.

An exact REAL64 binary32-quantum constant now makes the intended thresholds explicit. A controlled pinned Intel O0/O2 probe shows that the former `REAL(NEAREST(...),REAL64)` expression and the explicit constant agree. An earlier uncontrolled cast-to-zero observation was not reproduced; no compiler defect or threshold correction is claimed. The explicit inactive-Q option remains a deliberate representation-policy change.

## Validation and evidence

- [Final Intel validation receipt](evidence/pr91_host_store_20261020/final_validation.json): 63 unique focused cases across 22 files, including the C14 inactive-ice storage fixture. Its full maintained-core O0/O2 executions are inside the C14 test and are not additional pytest cases. The earlier 57-case C13 receipt is preserved at [final_c13_validation/root_receipt.json](evidence/pr91_host_store_20261020/final_c13_validation/root_receipt.json); the complete C14 source, test, profile, build and log pins are in [final_c14/source_pins.json](evidence/pr91_host_store_20261020/final_c14/source_pins.json).
- [C12 source/formula bundle](evidence/pr91_source_store_contract_20261020/c12/README.md): frozen host/solve, exact captured native REAL128 stencil, non-diffusion decomposition, writer and intermediate/final contract tests.
- [C13 FogDES bundle](evidence/pr91_source_store_contract_20261020/c13/README.md): captured marginal-candidate rejection and a separate source-present positive-flux/common-theta/conservation/store regression.

The captured-packet test does not establish positive theta for that exact native primitive proposal. C13 closed INCOMPLETE at T9/RK2; C14 runtime closure remains a separate gate. Builds replace selected objects in the preserved host; they are not a clean rebuild of all WRF and libraries. No whole canonical pipeline pass is claimed for these final files.

## Physical diagnostics remain separate

[Preserved C5/C7 history response](PR91_HISTORY_RESPONSE_20261020.md) provides same-location pressure, Phi and native-face W maps/trajectories through 180s. At common 0/60/120s the C5–C7 interaction of the COUPLED–OFF differences is zero at stored precision for those three fields. This is neither observation skill nor new-candidate history.

[Science source audit](PR91_SCIENCE_SOURCE_GAPS_20261020.md) records C7's large area-weighted AUT/G activity deferral and the recovered original 162-cell pressure mask. Target-specific WPS horizontal and real vertical influence rows remain uncomputed. The fixed 27-column difference support is descriptive, not independent observation support.

Water/energy closure, native face-flux continuity and momentum, particle-number reconstruction accounting, large-process-deferral justification, observation-signal preservation and reduced initialization shock remain OPEN. Current-candidate quantities must use its own carrier, time, geometry and boundary terms. Graph freshness is separate from runtime and scientific validation.
