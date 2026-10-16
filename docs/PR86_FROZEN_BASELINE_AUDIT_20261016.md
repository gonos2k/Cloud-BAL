# PR86 frozen-baseline physical audit

## What changed

This batch freezes merged PR85 v17 (`743e9f28bdd9f29d039c9b671d7bd24fbfb3ffa9`)
and adds Python accounting and time-response collection. No Fortran equation,
transport policy, microphysics policy, initial Q/N/B or T/q is changed. The
existing partial-host executable is reused byte for byte; no clean WRF build
or new compiler-profile comparison is claimed.

The PR85 first KDM6 call and first 20-second integrations remain
`PASS_SCOPED`. Their successful receipts are preserved. Later failure in an
extended run does not revoke that result or establish longer-run success.

## First-call measurements

The [water report](PR86_FIRST_CALL_WATER_20261016.md) uses the same captured
dry-density/thickness and map-area measure for both storage and numerical
changes. Bottom outflow is counted once. After subtracting recorded cutoff,
ice→snow rounding, cold/warm storage differences, sedimentation column
residuals and rain-freezing storage differences, the partial residual is
**−16,962.076 kg OFF** and **−16,751.475 kg COUPLED**. Same-call host hybrid
mass and complete energy terms were not captured; closure remains OPEN.

The [process audit](PR86_PROCESS_BUDGET_20261016.md) finds substantial deferred
cold-group mass-vector activity: approximately **24.3% NG, 95.2% AUT and
85.1% G**. These are source-vector activity proxies, not independent gross
reaction transfers. Their proposal activity is the denominator. Warm and
sedimentation suppression is much smaller in the recorded first call.

Absent-graupel rain freezing is structurally blocked under the unchanged
1000 kg/m³ birth packet and 100–900 kg/m³ consumer domain. The withheld
absent-receiver proposals total **417.371 kg OFF** and **417.412 kg COUPLED**.
This is important to physical interpretation, while its absolute mass is
smaller than the cold-group activities. No density bound or packet volume
was changed to admit it.

State validity also does not imply small adjustment: OFF cloud-water and
cloud-ice inventories fall about **35.1% and 29.2%** within the first call
on this measure. Other water species change concurrently. This is not a
total-water loss estimate or evidence of forecast skill.

## Extended response

Both candidates use the exact v17 executable and original input/boundary
hashes. Only end time/duration and history cadence are changed. The strict
collector requires every 20-second timestamp and completed post-KDM6 stage,
rejects duplicate records, checks fatal lines and input identities, and
retains unavailable 1/5/10-minute states as missing.

Actual outcomes and exact receipt provenance are in the
[time-response report](PR86_TIME_RESPONSE_20261016.md). The extension must
not be represented as a ten-minute success unless those gates pass.

Both extended attempts completed **13:00:20** and then stopped at the next
timestep's FogDES guard, `paired Stokes settling requires both cloud moments`.
The guard requires finite nonnegative QC/QNC and rejects a zero/positive
pair; the recorded fatal does not identify its cell or prove which upstream
operator created the pair. No physics change was made to bypass it.
The [history comparison](evidence/pr86_matched_history_response_20261016.json)
contains only the initial 13:00:00 frame in both arms. The requested
1/5/10-minute responses and transport-diffusion measurement remain
**INCOMPLETE**, rather than being inferred from first-step success.

The [matched first-call comparison](evidence/pr86_matched_first_call_response_20261016.json)
retains available Q/N/B, pressure and reconstructed physical temperature
norms at PRE/POST_KDM6. These are unweighted Eulerian differences between
candidates at call boundaries, not a time-zero retention ratio or the full
host final state. U/V/W and Phi were not captured in these dumps. Reproduce
with `tools/pr86_compare_response.py --first-call --off-root` and
`--coupled-root` pointing to the original frozen v17 run roots, plus
`--output` for the JSON destination. The history mode remains separate.

## Next bounded work

Keep v17 available as the first-step reference. Attribute the first later
state failure to its completed producer/consumer boundary before making a
separate physics revision. Use the weighted suppression maps to rank local
process changes; do not restart initializer/cap selection or add a new
transport framework merely to improve a completion label.

Observation retention, transport diffusion, full energy/water closure,
native force/continuity balance, and 10/30/60-minute shock reduction remain
separate scientific gates. Model-internal inconsistencies must not be
cancelled by opposite analysis increments.

## Evidence navigation

- [Frozen identities](evidence/pr86_frozen_baseline_20261016.json)
- [Integration status](evidence/pr86_integration_20261016.json)
- [Checklist](PR86_PHYSICAL_VALIDATION_CHECKLIST_20261016.md)
- [Independent team review](PR86_TEAM_REVIEW_20261016.md)
- [Water maps](evidence/pr86_first_call_water_maps_20261016.png)
- [Suppression maps](evidence/pr86_first_call_suppression_maps_20261016.png)

Graphify snapshots and derived wiki updates describe source relationships
and extraction limits; their freshness is not runtime or scientific approval.
