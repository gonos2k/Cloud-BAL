# PR94: frozen C4 physical validation

## Baseline and scope

The baseline is merged PR93 (`3d055bf24e92bfd6bba5d558cb8b77a32f8fa668`). Its closed OFF and COUPLED runs each completed 600 seconds and 30 KDM6 calls. The C4 executable SHA-256 is `20aaa6058797e7d1ec7a874ae92ed44f9ac19876ef2f14477b5eedb6a1ae44be`. Those inputs, run artifacts, physics sources, acceptance predicates, and failed generic audits remain intact.

This change analyzes that existing window, prepares a current-generation HYDRO control, and extends the stability experiment. It changes no native physics equation, guard, precision, moment prior, balance weight, or wind cap. HYDRO input authorization extends the existing PR84v2 initializer metadata; its physical policy body must restore exactly to the pinned parent policy.

| Question | Current evidence | Scientific acceptance |
|---|---|---|
| Does C4 run for ten minutes? | Existing two closed runs, 30 calls each | `PASS_SCOPED` execution only |
| Does absolute water balance close? | Each arm's inventory, precipitation and column residual; missing terms identified | `OPEN` |
| Is the final QC difference a smaller copy of the initial pattern? | Actual arrays reproduce negative cosine; fixed buffers and translation diagnostics added | No |
| Is observation skill improved? | No authoritative matched observation/operator pair available | `NOT_EVALUATED` |
| Is the early pressure/wind response reduced? | Same-coordinate maps and time series; HYDRO comparison required | `OPEN` |
| Do PSD number changes represent nucleation? | Logged reconstruction coverage audited separately | No such attribution |
| Does the candidate run for 30/60 minutes? | One 3600-second request per arm, including the 1800-second checkpoint | Pending closed receipts |

## Existing ten-minute results

[Absolute water accounting](PR94_WATER_BUDGET_20261021.md) uses the actual hybrid dry carrier at every saved time and actual map area. OFF and COUPLED available signed column residuals are respectively **+1.4628756114e11 kg** and **+1.4628676981e11 kg**. These are atmospheric inventory change plus ground precipitation, with lateral/relaxation exchange, integrated surface exchange and complete numerical terms missing. They are neither closed conservation errors nor diagnosed water production. Column L1/maxima and three-dimensional inventory-change diagnostics are kept distinct.

The captured third-call input thickness differs from the corresponding history thickness. History precipitation spans three calls. Consequently a call-specific closed budget cannot be recovered by inserting endpoint geometry or assigning a minute's precipitation to one call.

[Cloud and early-response analysis](PR94_CLOUD_RESPONSE_20261021.md) reads the actual paired arrays on the source-derived **613 values in 16 columns**, fixed horizontal buffers and the full active domain. QC at 600 seconds has cosine **−0.367995**, initial-pattern projection **−0.096917**, and orthogonal residual RMS **3.063e−5 kg/kg dry**. Species differences, maps, a bounded translation scan and fixed-coordinate pressure/Phi/W series describe redistribution without assigning its cause. Negative alignment and smaller RMS establish neither lost observation skill nor reduced initialization shock.

The original observation mask remains fixed. Buffers expand horizontal columns through all native levels. Translation lags are selected on the same data and are descriptive; a best lag on the search boundary is explicitly reported. Maps of the level with largest absolute difference are vertical envelopes, not an isobaric surface. Actual staggered winds are reported separately from mass-point averages; neither is called a continuity closure.

## Controls and stability extension

The HYDRO control must use the existing pipeline's thermodynamic/density configuration and immutable PR81 inputs/supports, with continuity and force priors disabled and U/V/omega unchanged. A historical PR78 HYDRO chain was reproduced while checking the delivery path, but its thermodynamic generation differs; it is retained as a qualified diagnostic and is not the matched forecast control. The current-generation chain and final input receipt passed independent review. A 600-second HYDRO control has been launched with the original C4 executable; its completion and response remain pending. This treatment disables continuity and force priors together and cannot isolate their individual effects.

[The compact diagnostics profile](PR94_LONGRUN_DIAGNOSTICS_20261021.md) retains all completed `POST_KDM6` records, full first-600-second records, and selected later full stages. Density validation remains outside the output gate. Pinned Intel O0/O2 manufactured tests verify retained bytes and existing fatal behavior. The new partial-host executable is **a diagnostic overlay**, SHA-256 `3eea34b73a1ac3a7c0dfb121968e82fa764e65eeeee0df75c79e8bba27641bac`; it is not the original C4 executable. Its nine physics source bodies, parent archive, profile and cycle support match C4, as recorded in [the source/build audit](evidence/pr94_longrun_diagnostics_20261021/source_build_audit.json).

One OFF and one COUPLED 3600-second request are running and include the 1800-second checkpoint. Their combined conservative space requirement was 1874.72 GiB against 4991.63 GiB free on the selected filesystem. Launch/preflight status is recorded in [the launch plan](evidence/pr94_longrun_diagnostics_20261021/longrun_launch_plan.json). Closed native prefixes/history still require comparison against C4; manufactured-driver equality does not establish full-model equivalence.

## Validation and remaining work

Team review found and addressed two runner gaps: cross-filesystem copies now pass staged-byte verification before WRF launch, and HYDRO finalization checks arm, launch/preflight input binding, candidate hash and unchanged source-chain artifacts. The OFF ancillary template is not modified. Missing timesteps, snapshots, duplicate records, fatal messages and changed inputs still prevent completion.

The [cold-process audit](PR94_PROCESS_LIMITS_20261021.md) preserves the current activity ratios and explains why full-proposal reason codes do not identify the constraint selecting the final fraction. The [native closure source audit](PR94_NATIVE_CLOSURE_GAPS_20261021.md) identifies the missing actual RK face transports, boundary increments and surface/PBL contributions.

The physical approval remains **OPEN**. Missing water/energy and face-flux terms, actual observation residuals, the matched HYDRO response and closed longrun evidence must be evaluated before claiming improved mass–wind balance, reduced initial shock or forecast skill. Generic exact/precomputed failures remain separate from source-defined completed endpoints. Graph updates provide navigation and provenance, not runtime or scientific validation.
