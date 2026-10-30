# Runtime and preprocessing provenance

The current Cloud-BAL LAPSPREP was built at commit
`a63a8029fc134e1bab77f0a96757e3b369b8e93d` with the repository's pinned Intel
profile, `tools/build_upstream_producer.sh lapsprep O2`, and external KLAPS
dependencies identified in `inputs.sha256`. The full compile and link commands
are in `build.txt`; the executable, dynamic runtime, and link manifests are
retained here. The model host itself is the separately archived historical
WRF executable, not a clean current C2 build.

The current modes use a private copy of the same 12 UTC prepared LAPS data and
the historical vapor-enabled namelist: `hotstart=.false.`, `balance=.false.`,
`output_format='wps '`, `snow_thresh=1.1`, `lwc2vapor_thresh=0`,
`make_sfc_uv=.false.`, `wind_coordinate='GRID_RELATIVE'`, and
`wps_output_vapor=.true.`. Experiments are `OFF`, `HYDRO`, and
`LIQUID_RADAR_RH1`. The OFF WPS writer omits hydrometeor records while both
candidate writers include them. Differences therefore include this explicit
writer/initialization contract. An additional current OFF run with the legacy
vapor-disabled configuration produced the historical legacy OFF WPS exactly;
the vapor-enabled current OFF also exactly reproduced the historical paired
vapor-enabled OFF WPS. Both are preparation checks, not proof that the actual
six-hour original control has identical input.

The original arm uses the actual archived six-hour OFF `wrfinput_d01` hash
`5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc`,
not the separate paired `real_OFF` input. The current vapor-enabled OFF input
matches that separate paired input, hash `50766cfc41433873f3b3118ff51de56bf94b5e817a307a994b52f905ae177072`.
The numerical state comparison is in `../initial_original_vs_current_off.json`.
The original input used a full 235-record OFF WPS product and a different
`real.exe` (`5e94804f...`); the fresh paired current OFF uses the vapor-enabled
OFF product and `real.exe` (`58118b30...`). Original-to-current differences
therefore cannot be attributed to the Cloud-BAL source version alone.
All arms use the same archived six-hour boundary, namelist, WRF host, eight MPI
ranks and one OpenMP thread. The 18 UTC boundary input uses background RH/TT
conversion because LAPS 18 UTC is unavailable.

The shell scripts record the actual host-specific preparation and candidate
launch commands; their absolute research-host paths are intentional and they
are not portable CI scripts. Input files and large model products remain in
external scratch and are identified by hash. The current build source and
dynamic runtime manifests are checked before running. All three initialization
inventories cover `static/` and `lapsprd/` (not every copied file), and those
inventories and all three metgrid/real input postchecks match. For the
original and current OFF forecasts, the four central inputs were hashed before
launch; inventories of the remaining copied runtime files were captured while
those runs were already in progress. The first OFF wrapper then failed after
WRF wrote its success marker, and its WRF command exit was not recorded; see
`failed_OFF_receipt.json`. It is retained as a failed wrapper, not scored as a
completed run. Its fresh OFF retry and both queued candidate launches hash all
copied files before launch and verify them after termination. This distinction
prevents an in-flight inventory from being represented as a pre-launch check.
The other regular files in the prepared root, including `payload.nc`, `cdl/`,
`time/`, and `log/`, were hashed only after preparation. At the recorded
post-hoc time, the source and all three copied inventories have the same 31
file hashes. These measurements cannot establish their earlier identity or
whether a given excluded file was read by LAPSPREP.
`current_forecast_wrf_off_actual.sh` reconstructs the script used for OFF by
removing the two later-added full-inventory lines from the queued candidate
script; its exact earlier script bytes were not separately hashed at launch.

The `*_lapsprep.txt`, `*_metgrid.txt`, `*_real.txt`, `*_postcheck.txt`, and
`build*.txt` files preserve the corresponding original `.log` bytes; the
extension was changed for repository tracking. The archived LAPSPREP logs
contain NUL bytes produced by the program and are preserved byte-for-byte.
`wrf_runtime_inflight.sha256` identifies the WRF dynamic libraries observed
during the first two runs, rather than asserting a pre-launch runtime seal.
