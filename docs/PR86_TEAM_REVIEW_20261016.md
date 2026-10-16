# PR86 independent team review (2026-10-16)

## Review result

Implementation review: **PASS, no remaining source or test blockers**.
Scientific validation remains **OPEN**. The focused Python suite passed 21
checks; no Fortran build or new model run was performed for this review.

## Runtime receipts

Both 600-second attempts returned 1 after one completed 20-second step. They
entered timestep 2 and stopped at the FogDES paired Stokes settling guard,
`FogDES paired Stokes settling requires both cloud moments`. Each strict
receipt is `INCOMPLETE`, records only the `13:00:20` model timestamp and
`POST_KDM6` step 1, and has maximum seen timestep 2. The legacy
`final_state_timestep` field is absent, so it cannot conflict with the completed
step count. Staged and source inputs are unchanged, source receipts are
unchanged, processing errors are empty, and compressed output identities are
retained. OFF's launch runner hash was unavailable because that attempt
started before source hardening; both strict receipts bind the successor
collector source hash. COUPLED launch provenance includes its launch runner
hash.

Only the initial `13:00:00` history frame exists in either arm. All ten later
minute timestamps through `13:10:00` are recorded as missing. The first-call
PRE and POST dump hashes in both arms match the corresponding PR85v17 baseline
hashes. This establishes first-call identity only and does not override the
later runtime failure.

## Scientific and implementation checks

- Cold/warm source rows map native `(i,j,k)` to active `(j,k,i)` slots and
  check logged `rhoDry` against the same-cell DEN. Q/QV activity uses
  `rhoDry*DELZ*map_area`; number activity uses `DELZ*map_area`; column
  sedimentation values use map area only. NPZ map sums agree with JSON totals
  to about `5.6e-13` relative error.
- Process mass and count values are half-L1/L1 vector activity proxies, not
  primitive gross reaction transfers. Stored-minus-approved residuals are
  kept separate and are not added to proposal activity.
- Cold heat remains a `K kg` diagnostic. Warm heat remains a `cpm`-weighted
  `J` proxy. Neither is a full energy budget. Rain-freezing proposed heat is
  unavailable without source-matched `xlf/cpm` terms.
- Signed water changes use `C` as storage creation positive and storage loss
  negative, with `R = R0 - sum(C)`. Rain-freezing uses `DELZ*map area` because
  its logged residual already includes `rhoDry`. Remaining partial residuals
  are OFF `-16,962.075555828906 kg` and COUPLED `-16,751.474967941016 kg`.
- The first-call response reconstructs physical temperature as `TH*PII` from
  receipt-bound dumps. The history-mode field `T` is correctly labeled
  perturbation potential temperature. Uncaptured winds and geopotential are
  omitted; no retention ratio or observation-skill claim is made.
- The duplicate-time gate rejects duplicate timestamps and POST_KDM6 records.
  The strict runs explicitly remain incomplete because of the recorded fatal,
  missing history outputs, and missing completed steps.

## Validation

```text
python3 -m pytest -q tests/test_pr86_water_budget.py tests/test_pr86_process_budget.py tests/test_pr86_water_terms.py tests/test_pr86_time_response.py tests/test_pr86_compare_response.py
21 passed (0.57s)
```

Reviewed source, test, evidence, and documentation hashes; per-arm final
receipt identities; and runtime results are recorded in
`docs/evidence/pr86_team_review_20261016.json`.
