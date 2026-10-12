# Team08/12 — WPS / native handoff audit

Read-only audit of Cloud-BAL PR77 snapshot `9701ef23f04576d875508a0882d0e0af67282587` plus the PR77 working tree. The trace found no static pressure-level or unit conversion defect in the LAPSPREP-to-WPS-array mapping. It found two deployment-configuration authority gaps and three native evidence/semantics limits.

## Findings

1. **P1, conditional direct-QV gap.** LAPSPREP emits dry-air QV; the candidate mapper intentionally retains background RH. If metgrid does not select QV, `real` does not set `use_sh_qv`, or the SH path wins, candidate vapor may be ignored and recomputed from stale RH/temperature. Evidence: `src/lapsprep/module_lapsprep_wps.f90:111-114,323-335`, `src/common/cloud_bal_wps_adapter.f90:813-815`, and `tools/check_native_hybrid_geometry.py:234-238`. The deployed flags, namelist, and executable path are not authenticated. Next check: bind the active metgrid and real configuration to a staged pair and read back vapor.

2. **P1, conditional PSFC/terrain gap.** Candidate PSFC (Pa) and SOILHGT (m) are conditional output; preserving source pressure requires the expected metgrid flags and `sfcp_to_sfcp`. Otherwise `real` may replace or terrain-adjust PSFC. Evidence: `src/lapsprep/module_lapsprep_wps.f90:117-119,358-366,409-419`; checker conditions at `tools/check_native_hybrid_geometry.py:234-238`. Next check: compare PSFC, SOILHGT, terrain mask, and hybrid pressure in `wrfinput` under deployed configuration.

3. **P1 acceptance blocker only if called an accepted WRF handoff.** The PR77 receipt documents two copied partialhost experiments, but explicitly marks `native_candidate_accepted=false` and `science_assessed=false`. The KDM6-entry run rejects an ice number-only state; the startup arm traps on floating invalid before KDM6. The manufactured estimator endpoint is not bound through a WRF input file/readback to first-call state. Evidence: `docs/PR77_INTEGRATION_PROGRESS_20261012.md:55-64,112-125`, `docs/evidence/pr77_native_state_20261012.json:26-42,79-88`, and the retained runtime artifacts listed in the JSON finding. This is accurately documented as open, not a newly found code defect.

4. **P2, producer provenance gap.** The native-W consumer accepts a unit/layout checked payload and maps it with the chain rule, but no in-tree native increment writer was found. The consumer does not establish that P/Z derivatives, winds, omega, and eta levels are co-located and derived consistently. A valid-shape but semantically misaligned payload can produce wrong W. Evidence: `src/common/cloud_bal_native_w_consumer.f90:246-268,344-375,541-553` and `src/common/cloud_bal_native_velocity.f90:1-7,121-129`. Next check: bind the actual producer and independently check derivative and destagger semantics on an actual payload.

5. **P3, W semantics risk.** Legacy conversion uses a fixed 8 km scale height; state code uses moist-gas density/gravity; native W uses the pressure-coordinate chain rule. Treating these outputs as equivalent can misstate vertical motion. Evidence: `src/lib/vertical_motion_conversions.f:29-52`, `src/common/cloud_bal_state.f90:809-839`, and `src/common/cloud_bal_native_velocity.f90:121-129`. Trace contracts and compare representative states before claiming equivalence.

## Coverage and limits

Covered LAPSPREP/WPS adapter, moisture carriers, native velocity/W consumer, native geometry/auxiliary contract, selected PR77 receipts, and referenced KLAPS50/WRF handoff provenance. No tests, compilation, edits, or large pipeline reruns were performed. No production metgrid/real configuration or deployed executable was authenticated. External WRF source/link closure remains partial.

Maintained Graphify snapshots were queried separately: KLAPS50 (`d79b97e`, 2026-10-08, 34,375 nodes / 74,275 edges) and Cloud-BAL (`f837bad`, 2026-10-08, 8,542 / 15,847). Neither includes PR77 receipt nodes. Queries were navigation only; exact findings came from source and retained artifacts. No graph update was run in this read-only audit. Graph delta: none; the two dated corpora remain separate. Graph freshness does not establish runtime or scientific validation.
