# PR93 active-ice source review

## Scope and inputs

Read-only source review of PR93 generated overlays against selected C18 source `/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F` (SHA256 `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`). C1 was the initial module-boundary attempt; C2 moved the shared predicate to an external function; C3 added pre-arithmetic finite/positive input guards; C4 added opt-in sedimentation capture. The reviewed C4 hash is recorded below. This is not a native build or runtime validation.

## Findings

- C3 moves the single copied predicate body outside the closed module and declares it external at the producer and packet call sites; this addresses C1’s module-boundary placement failure without duplicating predicate logic. The generator applies the same focused change to all three active-ice reconstruction blocks. Stage1 and stage2 retain `QI >= 1.e-14`; stage3 retains `QI >= qmin .and. NI >= ncmin`. It does not widen the source activation gates.
- The shared `pr93_kdm6_pair_in_cone` predicate is a direct move of the freezing packet's former `in_cone`: exact `(Q,N)=(0,0)` remains valid; one-sided/nonpositive pairs remain invalid; positive pairs use the same REAL64 `rho*Q/N` expression and the same endpoint-specific 8 REAL32-ULP allowance. The packet helper now calls this shared predicate for its base and candidate checks. No tolerance or coordinate conversion changed.
- For active ice above the source upper mean-mass endpoint, the inserted condition selects `lambda=lamdaimin` and the existing side-1 PSD number-bound helper; below the lower mean-mass endpoint, it selects `lambda=lamdaimax` and side 2. The direction follows `mean_mass = pidni/lambda**dmi`. Values already inside the existing predicate are left alone. A nonpositive number paired with active positive ice errors before it can be silently repaired.
- Stage1 and stage2 retain their existing `n0i` recomputations after number repair. Stage3 retains its prior cache behavior. All three blocks re-evaluate the shared cone (plus the existing positive paired source-inactive exception) before leaving the producer block, which is before the next following source section consumes the local state.
- The existing boundary helper remains the only number writer. Direct interior-slope repairs set its existing trace argument so they receive the existing PSD boundary ledger row; physical freezing activation and packet ledgers are not repurposed. No new side ledger or duplicate number arithmetic was introduced.
- Error handling remains fail-fast: helper invalidity errors before assignment; after an accepted helper result, the producer assigns the directed number and recomputes the stage1/2 cache, then errors if the output postcondition fails. A postcondition failure is fatal (`ERROR STOP`), so there is no in-process rollback path. This matches the surrounding native fatal-invariant pattern; there is no recoverable continuation with partially repaired state.

## First-write interval: deduction, not capture

The preserved PRE_KDM6 row is a valid active pair; the final PINU row is invalid. In the selected C18 source, before the first `PR85_SED_ICE` call (around source line 3006), the setup computes slopes and rates and clamps entry NI, but contains no direct assignment to `qci(i,k,2)`. Source order therefore supports this bounded deduction: if the captured T24 positive-QI, `T=257` cell reaches this cold ice path, its first possible direct QI mutation inside KDM6 is the first ice sedimentation helper call. This is a source-control-flow deduction only. The saved T24 artifact does not capture pre/post state at that helper, and the entry NI clamp could affect the pair before QI changes. Thus the evidence does not establish that this helper actually made the pair invalid or prove the first pair-invalidating write. A stage capture would be required for that claim.

The exact PRE_KDM6 and PINU bit evidence and guard replay are summarized in `docs/PR93_ICE_ORIGIN_20261020.md`; that note explicitly records the first-write capture gap. The preserved sedimentation causality examples in PR87 concern different coordinates/runs and cannot be transferred as direct T24 evidence.

## Graphify evidence and limits

The read-only `graphify query` ran against the isolated PR93 worktree’s stale tracked snapshot (1,499 nodes) and returned unrelated LAPSPREP/state nodes; that query is not evidence about maintained graph contents. Separate root inspection reports the maintained Cloud-BAL graph at 13,304 nodes (SHA256 prefix `600bb37…`) and KLAPS50 graph at 39,132 nodes. Root inspection found the externally selected C18 `module_mp_kdm6.F` absent from the maintained Cloud-BAL graph. During delegated work, a broad catch-up update incidentally changed seven tracked graphify paths in the isolated new worktree; root restored those tracked paths. The restoration record says ignored derivative caches were retained. No published graph delta is claimed; graph freshness does not establish runtime or scientific validation.

## Review disposition

No issue found in predicate identity, 8-ULP preservation, repair direction, original activation guards, stage1/2 cache refresh, or reuse of the existing PSD ledger helper. C3 resolves the orphan-check ordering concern. C2-to-C3 diff contains only the same finite/positive input guard moved ahead of lambda construction in each of the three producer blocks, with the redundant later NI check removed. Keep the T24 first-write statement explicitly labeled as a source-order deduction; the direct first pair-invalidating operation remains unobserved.


## C3 resolution

The focused C2-to-C3 source diff adds the pre-arithmetic finite/positive input guard at all three active-ice reconstruction sites and removes the later orphan-only check. No other generated-source differences were present. The reviewed C3 artifact is `/var/tmp/pr93_sources_c3_20261020/module_mp_kdm6.F`, SHA256 `73db5c6aed0b43798ff76d4f5d971ed1d13c4769ab96557fc1f94f31f1bed833`.


## C4 diagnostic capture review

The focused C3-to-C4 generated-source diff adds one local integer declaration and before/after writes around the existing ice paired-sedimentation call. The three physical PSD producer blocks and the freezing predicate/helper are byte-identical to C3. The selector checks timestep, call latitude, and column index; it records every matching outer loop/substep and all `kts:kte` levels, including loop/substep identifiers in each row. The BEFORE row is immediately before the call; AFTER is immediately after a successful call and its existing validity check. Each row stores REAL32 QI, NI-volume, and dry-density bit patterns as hexadecimal, plus DELZ, mass/number rates, and timestep. Write failures are fatal diagnostics. The selector encloses only I/O, so it does not alter state, acceptance, or call scheduling. With no `--trace-column`, `generate()` does not insert the capture, preserving default-off behavior.

One capture limitation: if the sedimentation helper returns `valid=.false.`, the existing fatal check occurs before the AFTER row, so the rejected call has a BEFORE record but no AFTER record. For successful calls, the requested pairwise trace is complete. The new evidence should be used to claim a first write only after matching the captured run's source prefix/input hashes to C18, or explicitly describe it as evidence from a new candidate capture.

Reviewed artifact: `/var/tmp/pr93_sources_c4_20261020/module_mp_kdm6.F`, SHA256 `b358064642d81c86ee1f914c52620ade2c7589ccf302dcffd26d25809fd5adaa`. No published graph delta or runtime/scientific validation is claimed by this source review.

## Prelaunch fixture and runner review

The fixture's primary ice case now follows the actual host-facing REAL32 path: producer `Nvol`, public export through `volume_number_to_specific` to REAL32 `Nspec`, next-entry conversion through `specific_number_to_volume` back to REAL32 `Nvol`, then the unchanged freezing consumer. This matches the KDM6 source locations around lines 1740–1745 (ice export) and 1586–1590 (ice import). The assertion checks that this round-tripped ice pair is base-valid while the fixed tiny packet is deferred, with no producer or consumer tolerance change. The producer cases also compile the exact three transformed C3 blocks and existing PSD-bound helper.

The REAL64 `Nspec64 = DBLE(Nvol)/DBLE(rho)` common-store check remains as a separate component test. It is not the actual ice export path and is not labeled as the complete host transaction. The packet review reports the pinned Intel O0/O2 fixture passing; I reviewed the source and fixture statically and did not rerun it. Python test source SHA256: `b107a9a39b47ba73134b51e41ce11f23c83e0fc24473079eccc46bcd1c194d84`; generated Fortran fixture SHA256: `1cd73963df81a25c4ec22fd802eaaf4b62df450393161e0cca71b712f4238cfa`; generated source SHA256: `73db5c6aed0b43798ff76d4f5d971ed1d13c4769ab96557fc1f94f31f1bed833`.

The source note does not claim a directly captured first pair-invalidating writer. It distinguishes the source-order deduction that the first possible direct QI mutation is the first ice sedimentation call from the unobserved first pair-invalidating write. Any new paired-run capture should be attributed to C18 only if its exact source prefix and inputs match; otherwise describe it as evidence from that new candidate run.

Scoped source approval: C4 adds only the reviewed opt-in capture around the existing successful ice-sedimentation call; the C3 producer and packet predicate logic is unchanged. The fixture now separately represents the actual ice R32 export/re-entry path and the common-store R64 component path. No published graph delta, native run, or scientific validation is claimed.

## Bound-run diagnostic environment review

The runner change derives `PR91_RUN_ID` deterministically from the arm and resolved output path, records it in preflight and launch provenance, and passes it into the model subprocess environment. The ID uses a restricted whitespace-free form accepted by the existing native trace writer; `subprocess.run` inherits the current environment and overlays this explicit diagnostic value. The existing shell setup does not clear it. This closes the earlier launch gap where PR91 instrumentation stopped after one step because the variable was absent. The runner also adds the 480s/500s observations needed around steps 24/25 and recognizes PR85/PR93 packet rejections as fatal. Static review found no blocker in these focused changes; the independent packet fixture suite is reported by root as 18 tests passing. I did not run tests or inspect the active bound-run payloads.

Audit defaults now point only to `/var/tmp/pr93_{OFF,COUPLED}_600s_c4_bound_20261020`. The initial execution directories closed INCOMPLETE due to missing `PR91_RUN_ID`, which is a launch-environment failure rather than a physical integration result; they remain preserved separately and are not the final paired-run audit targets.
