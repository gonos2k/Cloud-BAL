# CP06-A thermodynamic density-prior experiment, revision 3

This frozen revision is prepared before the next retained candidate run. It
retains the exact v2 thermodynamic prior, masks, input products, wind/omega
caps, and support windows. Revision 2 reached its thermodynamic column, Phi,
and continuity trial but the frozen force-prior stage rejected the analytically
optimal stored wind state: its shared-flux continuity RMS was
`2.3482573795782823e-10`, just above the unchanged limit
`2.339591491450392e-10`. The v2 run and receipt remain immutable evidence.

## Stored-state force-prior backtracking

Keep the existing continuous analytic force-prior step as the first trial. If
the stored float32 candidate fails an existing continuity, strict objective,
absolute-force, or hard increment constraint, retry at half the step length,
with each candidate rebuilt from the immutable input state. Permit at most 20
halvings. Recompute the stored state, shared dry-flux residual, force objective,
absolute force residual, and hard wind/omega increment caps for each trial.
Accept only a stored candidate that passes every existing gate and has the
existing strict force-objective decrease. Never accept the zero step as a
fallback; reject atomically if no trial passes. Metadata, authority, and
nonfinite failures remain immediate failures. The retry count is recorded in
the force-prior diagnostics as the number of halvings used by the returned
candidate (or the 20 attempted halvings on exhaustion).

This is numerical feasibility control for float32 storage. It does not change
the objective, tolerances, caps, controls, masks, science authority, or prior
strength. The `0.5` density-prior background weight, 5 K and 0.005 kg/kg
thermodynamic bounds, 10 m/s wind cap, 5 Pa/s omega cap, and all original
continuity thresholds remain frozen.

## Retained case and validation

Use the same hash-bound 2026-08-16 13 UTC CP06-A input and 235×283×22 grid:
162 material cells, 69 liquid-thermodynamic cells, 180 Phi cells, 500 wind
controls, 980 continuity cells, and 900 force cells. The same-trial
thermodynamic receipts include pre-prior T/qv/condensates and dry-air mass.
Require a successful joint pipeline candidate, exact condensate preservation,
the fixed observation signal and supports, shared-flux continuity receipt,
unchanged strength bounds, writer producer replay, and atomic rollback for a
separate over-cap trial. The writer must reject nonfinite prior-ledger and
condensate-witness receipts without creating output files.

Keep all v1 and v2 frozen specs and rejected-run receipts unchanged. No cloud
attenuation, support/cap/threshold changes, zero-step acceptance, Phi-only
smoothing, or science-authority claim is allowed. This remains a diagnostic
research trial and does not constitute native model promotion.
