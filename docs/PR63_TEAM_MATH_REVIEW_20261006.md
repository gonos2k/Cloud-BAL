# PR63 team math review — state transitions and component contract

Review scope: fixed-pressure phase-ledger mathematics, canonical dry-mass
refresh placement, nonzero contract replay, and interpretation of native
carrier evidence. This review does not approve a coupled physical initial
state.

## Fixed-pressure phase accounting

For a pressure cell with represented total mass `mp` and dry-air mixing ratios
`r_s`, the canonical dry-air measure is

```text
md = mp / (1 + sum_s r_s)
```

An internal phase transfer `xi_s` is locally mass- and energy-closed when
`xi_d = 0`, `sum_s xi_s = 0`, and its represented mixture-enthalpy increment is
zero. In exact arithmetic this preserves total water, `md`, and mixture
enthalpy; the saturation solver changes temperature to realize that enthalpy
constraint. The phase ledger therefore remains distinct from external source
and boundary increments.

The phase calculation and its water/enthalpy budget must use the pre-transfer
`md`, as the pressure cell's carrier is fixed during that calculation. After
the candidate species have been stored as float32, recomputing `md` from fixed
`mp` and the stored mixing ratios is appropriate endpoint canonicalization.
The resulting difference from pre-transfer `md` is a representation delta,
not an external dry-air source; it can include both float32 storage rounding
and any accepted incoming mismatch between `md` and `mp/(1+sum(r_s))`. The
contract-only endpoint helper leaves its incoming candidate `md` unchanged outside
the cells marked changed, avoiding extra helper updates to inactive cells that
may be valid within the canonical-state tolerance but not bitwise identical to
the recomputed formula.

The nonzero fixture declares its condensation extent independently of the
candidate, sets source and boundary increments to zero, and records opposing
vapor/cloud-water extensive increments. Its physical tolerance must remain a
predeclared bound for float32 storage and derived-`md` rounding; it must not be
expanded to make a failed physical balance pass. The writer/reader round trip
must replay this same contract and candidate snapshot.

The implemented fixture uses a 4x4x3 research state because the evaluator and
writer operate on that state shape. This is a scoped pipeline/writer/readback
exercise, not a production NE57 candidate. The schema-7 command-line validator
is intentionally production-bound to the canonical 235x283x22 domain and
metadata; its rejection of this synthetic fixture on those fields is an
expected admission gate. Do not weaken that gate or report the fixture as a
schema-7 production admission. The fixture supports only the narrower claim
that a nonzero fixed-pressure phase candidate can be generated, serialized,
and replayed by the physical-contract reader.

An earlier trial placed this refresh inside the standalone phase kernel. That
changed legacy pressure-transition replay semantics and broke its extensive
stage telescope, so the shared-kernel placement was rejected. The current
implementation instead canonicalizes only value-changed thermodynamic cells
for a fixed-geometry contract-backed pipeline candidate, after the state
blocks and before the contract endpoint gate; it preserves stored `md`
elsewhere. The standalone phase operator and legacy geometry-transition path
retain their fixed-carrier behavior.

This narrow placement still creates an endpoint representation delta relative
to the pre-transfer phase carrier. It must fit a tolerance declared before
candidate execution; it must never be relabeled as source, boundary flux, or
internal phase extent. A more complete receipt could report it separately as
`eta_d = md_post-md_pre`,
`eta_s = (md_post*r_post_s-md_pre*r_pre_s)-xi_s`, and
`eta_H = (md_post*h_post-md_pre*h_pre)` for zero-enthalpy phase transfer.
Any bound must include float32 storage ULPs and the accepted incoming mismatch
between `md_pre` and `mp/(1+sum(r_pre))`, propagated through the dry-mass and
enthalpy formulas. The pinned Real SHADOW I/O and focused pipeline tests passed
for this scoped fixture; this does not validate the older full transition
ledger by the synthetic fixture.

## Interpretation and limits

- A component-contract PASS is local endpoint compatibility with declared
  source, boundary, and phase increments. The caller identity is only a label;
  it does not authenticate the physical authority or provenance of source or
  boundary terms.
- Zero dry-mass, net-water, and mixture-enthalpy phase stoichiometry does not
  establish donor availability, process-rate admissibility, chronology, or
  full microphysics moment feasibility.
- The contract does not assess native total energy, dry-mass tendency,
  sedimentation, or mass-wind balance. It is not a joint optimizer or a
  stationarity test.
- For a fixed pressure-cell mass `mp`, the accepted endpoint must also satisfy
  `md * (1 + sum(r_s)) = mp`. Thus dry-air mass is derived from the stored
  water mixing ratios; it is not an independent knob after pressure geometry
  is fixed. Internal phase exchange changes species and temperature while
  preserving dry carrier, total water, and represented enthalpy. External
  water increments, by contrast, change the derived dry carrier unless the
  total pressure-cell mass/geometry or a physical boundary budget also changes.
- A genuinely feasible coupled trial therefore needs an independently
  authorized external source and boundary-flux ledger, explicit donor limits
  and phase-process extents, fixed/adjustable variable declarations, and a
  physical tolerance set before candidate generation. The current `identity`
  string is only a label and cannot authorize its source terms. The evaluator
  can reject a declared inconsistent trial, but it does not construct another
  feasible one or infer missing fluxes. Without time-resolved boundary fluxes
  and an independently supported omega/dynamics target, a moisture-driven
  dry-mass change cannot be promoted to a mass-wind-balanced candidate.
- Corrected v2 call-boundary geometry capture has verified timestep 1, RK4,
  `HYBRID_OPT=2`, and bitwise-identical pre/post geometry. Source inspection
  confirms `calc_p_rho_phi` uses `MU=grid%mu_2` upstream of microphysics;
  KDM6 itself receives `DEN` and `DELZ`, not `MU`. The solve-em tile bounds
  `(1:234,1:282,1:39)` contain the KDM active bounds `(2:233,2:281,1:39)`.
  Reconstructed hybrid layer pressure increments are positive, and their sum
  agrees with `MU_2+MUB` to at most `1.0944e-4 Pa`; interface consistency
  differs by at most `0.00250 Pa`. However, the same-call
  `DEN*DELZ*DX*DY/(MSFTX*MSFTY)` diagnostic differs by `+0.05856%` from the
  MU-coefficient column mass. This is not closure: retain it as a diagnostic,
  do not fit a scale factor. A closed budget still needs the exact area/metric
  and layer-mass mapping plus boundary fluxes; a `t+20` geometry-weighted mass
  remains only a cross-stage proxy.
- The first purported instrumented `solve_em` run did not contain the
  instrumented object: the linked archive retained its original member and
  the executable lacked the probe symbol. That run cannot establish a causal
  stage. A later corrected v2 receipt verifies the canonical archive member,
  linked executable trace symbol, and isolated launch. In that corrected trace,
  `QG=0,BG>0` row/minor-loop aggregate counts are 11 before the terminal
  cutoff and 2,465 after it, a net increase of 2,454 across the recorded terminal cuts.
  The trace supports attributing that net increase to the terminal `QG`
  cutoff; it does not support attributing all 2,465 to it. The first
  observations of the 11 pre-existing cases are at loop 1 in rows
  14,15,22,115,122,197,200,214,247; their earlier origin remains open. A
  external research-source patch pairs the existing `QG<=qcrmin` terminal
  extinction with `BG=0`. The first paired v2b attempt was stopped by an
  authorized SIGTERM before reaching that terminal branch. Its input receipt
  (`a59bcd0b804ca29a25e380c6d13b8e35b0ed659f057fc6085b85c2a6a86bc2a1`) had
  unchanged inputs, but the run was incomplete and cannot establish either a
  pass or a paired-branch failure. It emitted an anomalously large
  52,242,972-byte KDM stage trace (768,278 fixed-size records, repeatedly
  tagged at latitude 2 / minor loop 1); this is repeated instrumentation
  output, not a count of ghost cells. A later matched control/paired run
  completed with separate isolation receipts. Both returned code zero, passed
  declared input/output integrity checks, and had byte-identical KDM6 pre-call
  state and geometry. The successful matched pair is specifically
  `build_paired_matched/{control,paired}`, not the earlier failed build
  directories. Each archive has 372 entries and 371 unique member names
  (`track_driver.o` is duplicated); the only differing unique member is
  `module_mp_kdm6.o`. The archived `solve_em.o` is identical in both archives
  (SHA256 `8670703c8229399709caaf5fb47e8c9dc865ad5def98cc7d4baaed6054bfd772`).
  The control and paired archived KDM6 member hashes are respectively
  `de145f8c7393085beb03e841fccbf78fe0243ffc28d2148c139747e6cbe03ab3` and
  `659a50b84906ba23c1e9265b0549cb774594ab33055fb9eb9b41d7506ceae00c`.
  The loose staged control object hash
  (`6c58c715dce54c2c83b0707ca0d83fc6b74055e8dadc5c4f3ef21c76f7f07ed6`)
  does not match its archive member; the paired loose object matches its
  archive member. Therefore the linked archive member and executable chain,
  not the loose control object, identify the control variant. The successful
  run executable hashes are `2a412690a6c6b4acdacfbf66507fae53406b4a1170403133b801e88a868a4e4e`
  (control) and `ee6d85d22597a1973dd551c9f33b3c5c7bb2f399a02300d6ad9da03a57c18155`
  (paired), matching the executables copied into the isolated run roots. The
  isolation receipt hashes are
  `bd8ea9ee3cdf475ae371ce9e2bd1cc637ea734c48601dde13a9cfb844a9458ae`
  (control) and
  `0073caf9a11c4b2c66d528c769ee21ebba632d3a3bdcc92c0803e58a8a98a609`
  (paired). The source hashes bind the external KDM6 files, but the loose
  control-object discrepancy remains a build-artifact chain limitation. On the
  returned KDM6 state,
  `QG=0,BG>0` fell from 2,465 to zero; QG itself and every other captured KDM6
  field were bitwise unchanged, with BG changed at exactly those 2,465 cells.
  For this mask the source-reconstructed same-call descriptor used
  `dp_k=-[C1H_k*(MU_2+MUB)+C2H_k]*DNW_k`,
  `md_k=dp_k*DX*DY/(MSFTX*MSFTY*g)`, followed by axis alignment to the raw
  `(y,k,x)` BG field. The mapped sum of `BG_control-BG_paired` is
  `44.97818557873735 m^3`; the unweighted ratio difference sums to
  `3.64208905151702e-9 m^3 kg-dry-air^-1`. This is a local bulk-volume
  descriptor, not a mass or energy closure: the independent geometry audit
  found the `DEN*DELZ` diagnostic differs by `+0.05856%` from MU-coefficient
  column mass, and boundary/source flux closure is absent. The selected QC/NC
  return gap remains one cell, and the 11 pre-cutoff ghost-cell origins remain
  open. This is process-state evidence, not full PSD or scientific acceptance.

## Review status

Scoped mathematics is consistent with the fixed-pressure component contract.
The pinned Real SHADOW I/O suite now passes with the nonzero 4x4x3
contract-backed pipeline candidate, writer, independent physical-contract
readback, mutation checks, and legacy transition replay. The separate schema-7
CLI remains production-bound to canonical 235x283x22 dimensions and metadata;
its rejection of the synthetic fixture is expected, and production admission
is not granted. This is a scoped writer/readback exercise, not a real NE57
nonzero candidate or scientific/runtime acceptance.

The corrected v2 executable provenance and call-boundary geometry are
verified. The matched archive and run-executable hashes, receipt hashes, and
control loose-object caveat are recorded above. This review finds no remaining
implementation blocker for the *scoped paired terminal cleanup effect*:
same pre-call state/geometry, one unique archive-member difference, and exactly
the intended BG changes in the captured KDM6 return. That scoped conclusion
does not authorize production use. The one QC-positive/NC-zero return gap and
transient RK-stage negatives remain; the donor flux/operator for the selected
QC/NC gap and the origins of 11 pre-cutoff QG/BG ghosts remain open. The
same-call carrier descriptor is not a closed mass budget. Native mass closure,
full physical initialization, and initial-shock reduction remain FAIL/OPEN.
