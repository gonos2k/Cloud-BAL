# PR62 review follow-up: state transitions

Base: `8a26a2cf414e89a31ddcefe8a68e51b5b3e82391` (PR62 merge).
This batch separates implementation, traced causes, component feasibility,
and native physical acceptance. Full physical approval remains FAIL/OPEN.

## Implementation and evidence

- [x] Trace the first observed creation of the incoming QC/NC gap and negative QC at
  actual initialization, transport, and pre-physics boundaries. Record stage
  membership, state, and available contemporaneous carrier information.
- [x] Locate zero-mass/positive graupel volume in the native process sequence;
  distinguish it from small positive-pair density boundary deviations.
- [x] Run a nonzero candidate through the actual pipeline, retained component
  contract, writer, and independent readback. Set the contract before the run;
  never use computed endpoint differences as source authority.
- [x] Separate immutable inputs and mutable outputs before launch. Reject
  hardlink/symlink output aliases and preserve control hashes through the run.
- [x] Complete independent agent-team review and affected pinned Intel/Python
  validation; record failed attempts and source/build/artifact identities.
- [x] Freeze implementation; update separately dated KLAPS50/Cloud-BAL graphs
  and derived wiki reports/audit, with extraction limits.
- [x] Push reviewed changes and create [PR #63](https://github.com/gonos2k/Cloud-BAL/pull/63) against main.

## Physical exit gates

- [ ] Incoming Q/N/volume state is admissible at the actual physics evaluation
  boundaries; do not project every intermediate RK stage into equilibrium.
- [ ] Process donor limits and final species transfers preserve the applicable
  joint moment domain. Air transport and differential sedimentation use their
  respective equations.
- [ ] Same-call mapped species budgets use the contemporaneous dry carrier,
  hybrid geometry, map factors, and boundary terms. A t+20 carrier proxy does
  not close the first-call budget.
- [ ] Feasible joint trials use independently declared analysis/boundary terms
  and internal phase-transfer freedom; feasibility, stationarity, and state
  change are separate tests.
- [ ] Complete host/parallel closure and fixed-setting BASE/HYDRO/COUPLED
  10/30/60-minute responses, preserving independent cloud/rain/updraft signals.

Historical PR62 captures, restored-control incident records, priors, and
thresholds remain immutable. Research native modifications are confined to
external source copies. No scoped PASS supplies scientific or operational
approval.

## Scope of the checked implementation items

The incoming target `(172,76,1)` is zero in the input and PRE_RK trace. An
additional cut first observes positive QC with zero NC immediately after the
RK1 QC update; the following NC update leaves NC zero. At RK1/RK2 stage ends
both are negative, while RK3 has positive QC with zero NC. This identifies
observed update boundaries, not the exact first flux/source operator. Do not
enforce a physical PSD on each intermediate sequential scalar update.

Full solve-tile and KDM active bounds differ by a horizontal buffer ring.
Post-physics 236 full-tile gaps comprise one KDM-active gap and 235 buffer
gaps. Mask and raw-state classifications agree on the exact common window.
The active return has one QC/NC gap for each of QC>0, QC>runtime epsilon,
and QC>1e-9, and no negative QC; buffer values are not silently discarded or
counted as directly consumed KDM state.

The terminal graupel cutoff trace has 11 ghost-volume cases before and 2,465
after, a net increase of 2,454. The first origin of the 11 remains open. A
paired mass/volume cleanup preserves the existing extinction threshold; its
matched research run removes all 2,465 returned ghost-volume states. The
one QC/NC return gap remains, and the earlier 11-cell origin is still open.
Only BG differs in the captured return fields; the existing water cutoff
and its discarded water budget are unchanged. Build-chain limitations and
failed attempts are retained in the native report.

The nonzero candidate is an actual pipeline/writer fixture on a synthetic
4x4x3 fixed-pressure grid. Its phase increment and storage allowance are
declared before execution; its independent physical-contract readback passes.
It is not a real NE57 joint candidate. The production schema-7 validator's
dimension/metadata rejection remains expected and unchanged.

Pinned Intel O0/O2 focused pipeline/phase tests and the Real SHADOW I/O suite
passed. Root independently reran nine affected Python test files, including the
11-case geometry, 10-case transition-mask, and 3-case paired-volume tests. These are
selected tests, not an assertion of the entire unit suite.

Same-call MU2/hybrid coefficients/map factors and KDM DEN/DELZ were captured.
The MU-based mapped dry mass and DEN*DELZ diagnostic differ by +0.05856%; no
scale fitting was applied. Boundary/process fluxes and water/energy closure
remain open even though contemporaneous geometry is now available.

[KG update and separate corpus snapshots](PR63_KG_UPDATE_20261006.md) record the frozen implementation and extraction limits.


## PR64 erratum — selected RK values and capture provenance (2026-10-07)

The earlier target description above confuses the aggregate minimum QC with
the selected moments. Successful matched PR63 stage captures show positive
QC and negative NC at RK1/RK2, then positive QC with NC=0 at completed RK3.
The following NC updates in the incomplete fine-cut run also produce negative
NC at RK1/RK2; they do not leave NC zero. Fine cuts from that incomplete run
must not be attributed to the successful matched runs.

The independent aggregate negative-QC counts remain valid, including 23,494
KDM6-entry cells. See the [full erratum and frozen capture hashes](
PR63_NATIVE_STATE_TRANSITION_20261006.md#pr64-erratum--selected-rk-values-and-capture-provenance-2026-10-07).
Original files and receipts are preserved. Physical approval remains FAIL/OPEN.
