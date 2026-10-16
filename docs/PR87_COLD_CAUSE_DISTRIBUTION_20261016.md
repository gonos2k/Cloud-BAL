# PR87 cold process admission distribution (2026-10-16)

## Scope and method

This note examines the saved PR85 v17 first-call `PR85_KDM6_COLD` records from
the OFF and COUPLED arms. The analysis reads the source-recorded process
proposal, approval, and withheld vectors for NG, AUT, and G; each ledger is
checked against its run receipt while read. Cell weights and coordinate checks
reuse the PR86 first-call measure. No model rerun or physics change was made.

The proposal/approval measure is the PR86 half-L1 Q plus QV vector-activity
proxy in kg. It does not measure independent primitive reaction gross rates.
The per-record approval fraction is applied vector activity divided by
proposed vector activity. Distribution percentages below are weighted by
proposed vector activity, not by record count.

The saved fields separate two stages. First, each group's alpha is produced by
its feasibility search. Second, the shared composite gamma scales all group
alphas when the combined endpoint needs backtracking. The analysis recovers the
pre-composite alpha as saved alpha divided by gamma and partitions proposal
withholding into `(1 - alpha)`, then `alpha * (1 - gamma)`. No row with gamma
zero occurred in these arms, so this split covers all positive proposals.

## Findings

The frozen v17 OFF/COUPLED ledgers are the baseline for the distribution
below. Later candidate runs do not replace these measurements. The separate
AUT/G reason probe is narrower: it covered suppressed nonzero proposals in
the first KDM6 call of an `INCOMPLETE` candidate run. V27bcompact is an
observer-only 20-second OFF comparison with unchanged physics; its matching
first-call captures and post-step state do not extend the cold-reason probe or
complete the requested two-step cycle.

The OFF and COUPLED distributions are nearly identical. Proposal-weighted
approval fractions and suppression attribution are:

| Group | Approved / proposed | Process feasibility withheld | Shared composite withheld | Zero feasible step records / proposal records |
|---|---:|---:|---:|---:|
| NG | 75.67% | 23.10% | 1.23% | 0 / 596,215 |
| AUT | 4.81% | 94.92% | 0.27% | 45,873 OFF; 45,880 COUPLED / about 49,415 |
| G | 14.91% | 84.44% | 0.65% | 122,165 OFF; 122,171 COUPLED / about 123,807 |

The paired-arm values differ by less than 0.01 percentage point. The
per-record approval distribution shows where the withheld activity lies:

| Group | Proposal activity approved at most 1% | Proposal activity approved above 99% |
|---|---:|---:|
| NG | 5.03% | 62.26% |
| AUT | 92.84% | 4.10% |
| G | 74.36% | 12.29% |

The low AUT and G approvals mainly arise at their individual feasibility
searches. Shared composite backtracking contributes a much smaller part of the
withheld activity. NG has a broad distribution, with most proposal activity
approved at 99% or more.

## What the records establish

The status values are `0=FEASIBLE_SEARCH`, `1=NO_FEASIBLE_STEP`, and
`2=SEARCH_FAILURE`. The source also assigns G status 2 when its required volume
rate is unsupported, so that G category would conflate two cases. No G status 2
proposal occurred in either arm. AUT and G have many status 1 proposals, which
are recorded as zero approval; the remaining status 0 proposals can still have
partial alpha. NG proposal records are status 0.

These fields establish whether suppression occurred at per-process admission
or at combined-endpoint backtracking. They do not record which specific
constraint set the feasibility boundary. The validator checks nonnegative
moments, mass-number bounds, PSD consistency, graupel mass-volume bounds,
temperature, and vapor, but its cold ledger saves only the search status and
alpha. It cannot tell from these packets whether AUT or G was limited by a
particular species floor, paired number bound, PSD edge, temperature, or vapor
condition. The composite retry and gamma likewise do not identify the endpoint
moment that triggered a backtrack.

The saved v17 cold ledger cannot label an individual feasibility constraint.
A separate diagnostic overlay did run its AUT/G source probe on the candidate's
first KDM6 call. It evaluates the full proposal with the same validator and
records the first failed endpoint check, plus an independent vapor check, only
for suppressed nonzero proposals. The rows carry vector-activity and frozen-
cell weighting fields. Candidate first-call pre/post dumps matched the frozen
arm captures byte-for-byte, but the 40-second candidate run remained
`INCOMPLETE`; these reason counts support first-call diagnosis only. They do
not certify which constraint selected the admitted alpha. The offline
summarizer also requires the candidate receipt to bind the reason ledger.

The first-call-only probe results are summarized below. The denominator is
**emitted proposal activity**: only AUT/G rows with a nonzero Q/QV vector and
pre-composite `alpha < 1` are logged. Each category's share divides its
half-L1 Q+QV proposal activity by that group's emitted proposal activity.
`Rejected / category proposal` is the weighted `(1 - alpha)` share before
composite gamma; it excludes alpha=1 rows and later shared backtracking.

| Group | First failed endpoint check | Emitted proposal activity share (OFF / COUPLED) | NO_FEASIBLE_STEP share of group emitted activity (OFF / COUPLED) | Rejected / category proposal (OFF / COUPLED) |
|---|---|---:|---:|---:|
| AUT | RAIN | 100.00% / 100.00% | 96.29% / 96.29% | 99.20% / 99.19% |
| G | BULKDENSITY | 84.45% / 84.44% | 72.33% / 72.32% | 97.59% / 97.59% |
| G | RAIN | 10.29% / 10.29% | 6.59% / 6.59% | 91.75% / 91.75% |
| G | ORPHAN | 2.16% / 2.16% | 1.09% / 1.09% | 73.54% / 73.54% |
| G | DONORNEGATIVE | 1.78% / 1.78% | 0.54% / 0.54% | 61.88% / 61.87% |
| G | ICE | 1.27% / 1.27% | 1.26% / 1.26% | 100.00% / 100.00% |
| G | PSDCLOUD | 0.05% / 0.05% | 0.00% / 0.00% | 90.23% / 90.23% |

AUT first-failure rows all classify as RAIN. For G, the most common first
failed full-proposal check is bulk density, but this does not prove that bulk
density is the bound controlling admitted alpha. Status and vapor reason are
kept separate in the evidence JSON; no vapor failures occurred. These runs
ended `INCOMPLETE` with return code 1 after one completed timestep. The
first-call pre/post dumps match their frozen arm byte-for-byte, so these
records support first-call diagnosis only and do not validate the requested
40-second window.

## Baseline versus candidate scope and next cold target

The saved v17 per-arm proposal counts are 596,215 NG, about 49,415 AUT, and
about 123,807 G. Their proposal-weighted approval fractions are 75.67%, 4.81%,
and 14.91%, respectively. The v17 ledger measures half-L1 Q/QV vector
activity weighted by frozen cell geometry. It is a diagnostic activity proxy,
not primitive gross reaction throughput, net condensate production, a
precipitation budget, or latent heat. The partition into process-alpha
withholding and shared-gamma withholding uses that same proxy.

The separate first-call candidate probe reports the first failed check for a
full AUT/G proposal, among emitted nonzero rows with alpha below one. It found
RAIN for all emitted AUT proposal activity. For G, 84.44–84.45% was first
classified BULKDENSITY; the remainder was mainly RAIN, then ORPHAN,
DONORNEGATIVE, and ICE. No vapor failures were recorded. The denominator is
emitted proposal activity, not all baseline proposal activity or record
count; alpha-one rows and later composite-gamma withholding are excluded.
`(1-alpha)*proposal` is the pre-composite rejected amount in this proxy. These
classifications identify the first failed full-proposal endpoint check, not
the unique constraint that set admitted alpha. The probe did not classify NG
endpoint reasons; its baseline approval and withholding split is available,
but no NG reason distribution is claimed.

The reason-probe candidate ended `INCOMPLETE` after one timestep. Its frozen
first-call pre/post captures match the v17 reference byte-for-byte. The later
V27bcompact OFF run is a separate observer-only check: it completed one
20-second step and its first-call captures and post-step state match V26c, but
it neither changes the cold-reason sample nor completes the two-step cycle.
Current paired-cycle status and the later physical-candidate failures are
tracked in [the completion report](PR87_TWO_STEP_COMPLETION_20261016.md).

For the next cold-physics investigation, prioritize **G bulk-density/volume
compatibility at the proposal and completed-store boundary**. It is the
largest emitted G first-failure category in this evidence, and the source
checks distinguish graupel bulk density from the rain/cloud number-volume
constraints. Test whether the proposal and the completed G representation use
the same declared mass-volume definition and bounds. Do not infer from this
ranking alone that bulk density uniquely controls alpha. AUT rain compatibility
is the next separate target. The historical 417 kg freezing case is not the
priority indicated by these proposal-weighted results.

An additional warm-path diagnostic is separate from the saved cold G/AUT
distribution. The V13 runtime diagnostic confirmed `NO_FEASIBLE_STEP` with
alpha zero at timestep 1, `lat=2, i=46, k=3, loop=1`; the stored base was valid.
The source had skipped the existing zero-alpha trial body and then marked this
case fatal. V14 changes that retry-0 status-1 path to evaluate the existing
trial, including pending rain-to-CCN transfer, and enables the existing sparse
warm budget row only for status 1. At the diagnosed warm rain-birth proposal,
cloud Q decreased and rain Q increased by `8.338e-8 kg/kgdry`, while
proposed rain N increased by about `325 #/m3`; the experimental strict warm
rain PSD constraint admitted no positive step. This records a withheld proposal,
not an accepted physical source. It does not change the cold-ledger counts or
the cold AUT/G cause classification above.

V14 subsequently rejected a paired warm intermediate with
`QR=3.3340966e-10 < qcrmin=1e-9` at `(lat,i,k,loop)=(22,199,17,2)` solely
because the new warm PSD opt-in imposed a completed-state constraint there.
V15 removes that speculative opt-in and restores the original source-defined
warm pair-only domain. The independently justified zero-trial control fix and
sparse status-one trace remain. Strict completed air, rain-sedimentation, and
public-store gates are retained; accepting a warm transient does not certify
an invalid completed state. The cold baseline distributions above are unchanged.

## Evidence

- `docs/evidence/pr87_cold_reasons_20261016.json`: per-arm proposal fractions,
  approval bins, search-status distributions, composite gamma distributions,
  and the two-stage weighted withholding split.
- `docs/evidence/pr87_admission_reasons_20261016.json`: first-call-only AUT/G
  endpoint-reason and status distributions, weighted proposal / approved /
  rejected activity, plus candidate receipts and compressed/raw hashes.
- `docs/evidence/pr87_two_step_v13_20261016/`: compact V13 source/build and
  exact-fragment validation archive plus the first-row rain coefficient
  inference from the closed V12 diagnostic. Closed V13 receipts and a filtered
  causal component payload are separate additions; no full model arrays, raw
  ledgers, or executable are included.
- `docs/evidence/pr87_two_step_v14_20261016/`: compact V14 source/build and
  focused validation evidence. The reused exact-fragment O0/O2 receipt binds
  unchanged native fragment/kernel/support only; it is not a V14 runtime
  result. The later V14 runtime receipts closed INCOMPLETE before the first
  step; their failure is separate from the source/build archive.
- V14 archive manifest SHA256:
  `562d5fc75f950ef97654e72915a55f510acb884ffc03ad97a221441561dc384e`.
- V12 first-row inference: `pidnr=12566.37109375` from
  `exactNmax=(rhoDry*lambdaMax^3/pidnr)*Q`; the exact row and compressed plus
  decoded ledger hashes are in `v12_rain_pidnr_inference.json`.
- V13 archive manifest SHA256:
  `793498261660872ebeb8397ea0f2f0967b527abc8aa910a971a6f796d7f2d310`.
- Evidence JSON SHA256: `0dd4454fbf0c94586b4d8f7fd8ef0d75ab07319cdb89b941b634998a4719a932`.
- Admission-reason evidence JSON SHA256: `b9c70105e18e27780bf41069ea5d9893eaf3c9cf21048312592fb41c608daab4`.
- The V27bcompact OFF observer comparison is
  `docs/evidence/pr87_two_step_v27bcompact_20261016/runtime/observer_comparison.json`
  (SHA256 `8ac52931d57034581e13a28f3da7ce67f621f0a82d370f70b9fc4b49a5fff49a`);
  it records `PASS_OBSERVER_ONLY_FIRST20`, not a cold-reason rerun or a
  two-step completion. Its closed OFF receipt is SHA256
  `e8ce17013b928a8e0116bdd32976e08b43e28b12562f9c2578bb21a617c16a77`.
- Source: `/var/tmp/pr85_native_joint_candidate_20261015v17/source/phys/module_mp_kdm6.F`.
- The 2026-10-16 Cloud-BAL graph snapshot is structural extraction only and
  does not establish runtime or scientific validity. The KLAPS50 graph remains
  a separately dated snapshot.
