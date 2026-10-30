# One-hour background-precipitation policy forecast

The diagnostic `POLICY_BG` run uses the candidate initialization produced through LAPSPREP, metgrid and real; it is compared with the existing FIX_H run whose input was reproduced exactly by the newly built baseline producer. The policy initialization is not a manually modified WRF input. Both use the same fixed WRF executable, boundary file, one-hour namelist, 8 MPI ranks and 1 OpenMP thread. The candidate staged 89 input files; only wrfinput differs from FIX_H. The prelaunch receipt binds producer, native, scoped-checker, shadow, source-reference and candidate-input hashes; source, staged files and evidence were checked again after the run.

The run exited successfully with the WRF completion marker and exactly the 12 and 13 UTC history outputs. Full artifacts remain under `/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG/`; input and output hashes are in the receipts here. The research policy and its shadow remain diagnostic-only; this runtime success does not itself establish physical balance, forecast improvement or operational suitability. Independent first-hour scoring is separate.

An unrelated evidence-copy error involving two generic `/tmp` paths is documented in `tmp_copy_incident.json`; their prior state is unknown and those paths were not deleted or modified again.
