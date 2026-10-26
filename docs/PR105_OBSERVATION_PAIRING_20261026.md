# PR105 observation preservation and paired evaluation

The existing C2 HYDRO, AMPLITUDE, and STRUCTURED one-hour requests are preserved.
No forecast is restarted and no model, wind input, physics, precision, prior,
or tolerance is changed. The active PR104 source checkout and its pinned reader
remain immutable; these changes are in a separate worktree based on merged
PR104 (`334969e120afff720f1b5da4eb1d8f0991f1a6c1`).

## Output and score changes

The explicit-valid-time reader serializes strict JSON before opening its output
with exclusive creation. An existing result, including a symlink to one, is not
replaced. Serialization failure creates no output. This fixes the reproduced
output-preservation gap without changing the observation operator.
An I/O failure after creation can leave a partial new file; the failed command
does not produce an accepted dispatch receipt and a rerun requires a fresh path.

N−A, A−H, and N−H use the same station keys, observation values, location,
elevation, reporting minute, and source expected-accuracy metadata. Both stored
residuals must equal prediction minus observation. The complete common sample
is retained; no outlier or station is excluded to improve a score.

For each pair the reader saves prediction differences, both residuals, direct
squared-error differences, `2*reference_error*delta`, `delta**2`, their sum, and
absolute-error differences. The summaries retain signed and absolute totals,
mean MSE/MAE differences, the largest absolute contributor, and cumulative
contributions from the five largest absolute contributions (or all samples if
fewer than five). Sorting contributions is descriptive and never changes the
primary all-station score. Direct and decomposed squared differences use
binary64 arithmetic and can differ at rounding level. Contributions and their
summaries both use the decomposed value; the direct value and its roundoff
difference remain explicit diagnostics.

The raw 13Z BUOY sample is not removed. A common observation error need not
cancel from a paired MSE difference: shifting an observation by epsilon changes
the station's N−A squared-error contrast by `-2*delta*epsilon`.

## Closed-result path

`tools/pr105_paired_scores.py` reuses the same station reducer on the existing
PR104 postclosure result. It requires the successful observation dispatch,
the hash-bound complete H/A/N cohort, the exact dispatched result bytes, the
three closed-arm identities, unchanged source pins, and the requested 14Z
valid time. It does not open forecast fields or launch a model. Input hashes
are checked again after reduction and the new result is exclusively created.

This leaves the already launched, frozen postprocessor unchanged. Its original
raw comparison is retained; paired scores are an additional result. The
original postprocessor is responsible for receipt/180-step/history identity
checks before any model arrays are opened. The paired reducer does not replace
that closure gate.

## Runtime and scientific scope

The timestamped `execution/status_at_start.json` records a direct metadata-only
check: all three supervisors were RUNNING and no `cohort_closed.json` existed.
That is a point-in-time observation, not a claim about their later status.
The requested 14Z predictions, station scores, and candidate ranking remain
pending until actual closed receipts and outputs are available. Previous
640-second success is unchanged and is not promoted to one-hour success.

All 765 eligible T2 station stencils are outside the original 16-column cloud
support and the fixed 196-column buffer. A later T2 score can describe the
surface-temperature response but cannot approve cloud initialization there.
The separate [satellite scope audit](PR105_SATELLITE_SCOPE_20261026.md) examines
actual 14Z LVD content and the missing observation-operator links.

Independent observation skill remains `NOT_EVALUATED`. Full host water/energy
closure, physical balance, and operational acceptance remain OPEN. No norm,
paired score, populated satellite raster, or refreshed graph substitutes for
those separate conditions.

## Validation

The final focused Python batch passed 43 checks with identical source hashes
before and after execution. It covers the existing PR103 reader regression,
explicit-time reader, output preservation, paired score arithmetic, closed
result bindings, and scoped KG guards. The receipt and log are under
`docs/evidence/pr105_observation_pairing_20261026/validation/final_v3/`.
Earlier validation receipts are retained for their source hashes. The final
batch includes the stage-receipt GO binding check and corrected, distinct
approval/graph-selection labels in the derived KG reports.
Manufactured fixtures are not actual 14Z predictions. No Fortran compiler or
new model integration was invoked for this batch.
