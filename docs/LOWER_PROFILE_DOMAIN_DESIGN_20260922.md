# Lower-profile domain and prior: bounded next experiment

## Decision and present evidence

Keep PR40's endpoint-once reconstruction as the integration mechanism. Do not
extend its actual domain by adding finite underground LW3 values, using a
nearest-level extrapolation, or selecting a variance by budget closure. The
new thickness attribution does not supply a wind prior or calibrate C/R.
Physical domain expansion remains **DESIGN_ONLY / NOT_AUTHORIZED**.

The retained 13 UTC domain inventory is 425 pressure-eligible faces, 348
also meeting the conditional LT1 height test, and 90 meeting the additional
10 m bracket/internal-face test, out of 198,480 unique faces. There are
197,448 internal faces. Only two pass the strict final test at all three
times; PR40's chosen 13 UTC face is not one of those two. These are support
inventories, not success rates or covariance estimates.

LSX producer labels distinguish U/V at 10 m AGL, T/TD/MR at 2 m AGL, and
PS at 0 m AGL (`klaps-v5.0_/src/sfc/lapsvanl.f`). The existing constant-T/MR
0–10 m thermodynamic pressure prior remains explicit. LSX U/V is an
analyzed-product sample, not an independent observation of the complete
surface layer. The wind-frame/build lineage remains conditional.

Use separate source families for further investigation:

| Family | Existing role | Unresolved connection |
| --- | --- | --- |
| LW3 U/V with direct-route LT1 HT | Conditional analyzed pressure state | LT1 absolute datum and exact producer wind frame |
| FUA U/V with FUA HT | Separate background prior candidate | Source-to-analysis coordinates, height datum, frame, and error correlation |
| LSX 10 m U/V with PS/T/MR | Analyzed lower sample and thin-layer pressure prior | Height representation and shared-analysis errors |

The direct reader `src/common/cloud_bal_real_netcdf.f90` pairs analyzed LW3
winds with LT1 heights; its thermo fallback does not establish arbitrary
cross-product wind/height combinations. On the PR40 selected face, LT1's
1000 hPa heights are +5.70/+2.95 m above AVG, while index-aligned FUA heights
are -4.75/-7.76 m. FUA HT is missing at all 1050/1100 hPa nodes, although
its U/V values are finite. FUA's navigation origin also differs slightly.
This comparison is a source-state discrepancy, not a collocated height-error
measurement or justification for choosing whichever family closes a budget.

## State basis, samples, and prior must be separate

A broader trial must declare a lower-domain state basis covering the sample
pressure before it fits any wind. Its coefficients are unknown state values;
they are not new observations. Valid above-ground LW3 samples and LSX 10 m
samples enter through their own sampling operators. A background family can
supply a prior only after its location, frame and height relation are bound.
Do not assign a missing coefficient the value of an underground LW3 knot.

The next bounded sensitivity experiment can use a fixed pressure basis and
manufactured, explicitly labeled lower-state prior over a declared pressure
range, with the observation sampling locations varied through existing knot
boundaries. This tests whether sample eligibility and geometry changes cause
new jumps without fabricating a real lower wind. An actual-data extension
requires a separately sourced lower-state prior; no such prior or variance
is approved here. A direct 10 m-to-first-level segment is itself a model
choice, and changing that first level must not silently replace a wide band
of the profile as in the legacy cap path.

For any eventual actual trial:

1. Select the source family, fixed state range and sample-support rules before
   computing transport. Bind time, geometry, height datum and wind rotation.
2. Record prior coefficients, measurement operators, declared error model and
   shared LSX/LW3/background information. Chart-component identity variance is
   a sensitivity assumption, not physical isotropy or calibrated covariance.
3. Fit each endpoint once; integrate that same profile across the face. If
   two endpoints use different bases, a common refinement may split the
   already-defined profiles; it must not change either profile or fill gaps.
4. Test nonzero winds, sample/knot transitions, support entry and exit,
   orientation reversal and shared-face conservation. Fixed-knot continuity
   alone does not establish continuity under support-set changes.
5. Preserve the PS-to-p10 missing strip and its unknown flux. Report how much
   is supported before constructing local or domain budgets. No residual
   becomes complete solely because a profile fit succeeded.

## Remaining evidence and scope

No independent collocated lower-wind truth, calibrated error ensemble,
roughness/displacement-height contract or producer-bound wind-frame receipt
was established by this audit. Spatial correlations between analyzed and
background arrays are not their error covariance. The same observations may
already enter multiple products. Neither a small fit innovation nor a small
transport subtotal can choose a physical prior or an error weight.

The retained input comparison is in
`scratch/pr41_validation/profile_prior.md` in the PR41 worktree; PR40 domain
and transport receipts remain the authoritative previous experiment. This
plan leaves the legacy cap-dependent transport unauthorized, 0–10 m flux
unknown, and full column flux, ON, native consumption and forecast validation
open. It changes no production state, solver or boundary permission.
