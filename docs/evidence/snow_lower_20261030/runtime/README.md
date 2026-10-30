# Lower-factor QSNOW sensitivity runtime

Eight six-hour forecasts cover CONTROL and IMPROVED at initial QSNOW factors 0.6, 0.7, 0.8, and 0.9. The already completed 0.5 CONTROL and IMPROVED cases are reused only after source, executable, boundary, namelist, QSNOW scaling, case receipt, and seven-history hash checks; see [reuse provenance](reused_factor050_provenance.json).

CONTROL uses the original WRF executable and original initial input. IMPROVED uses the fixed executable and background-preserved B1 input. The shared boundary and six-hour namelist are pinned in [common plan](common_plan.json). Each new candidate modifies only initial QSNOW using float64(source) times float64(factor), then casts to float32. The prelaunch audit confirms all other 207 variable values and all native metadata remain unchanged.

The run completed 8 cases from 2026-10-30T07:47:06.009798+00:00 to 2026-10-30T08:10:02.262191+00:00 UTC using eight disjoint 8-CPU slots, eight Intel MPI ranks per case, one OpenMP thread per rank, and the pinned Intel MPI 2021.18 runtime. All case receipts report SUCCESS; the finalized receipt verifies all 56 hourly histories, their SHA-256 values and embedded times, finite/unmasked RAINC/RAINNC/RAINSH, source and staged-input preservation, and rank affinity. See [batch receipt](batch_receipt.json), [final receipt](final_receipt.json), and [history validation](history_validation.json).

The launcher was run as `bash runtime/env.sh` so its script-relative path resolves to this runtime directory. An initial sourced invocation exited before launching WRF because `$0` resolved to `/bin/bash`; it created no forecast output. The corrected launch completed successfully.

These are same-event diagnostic QSNOW perturbations. They do not establish conservative initialization, independent forecast skill, or operational suitability.
