# CP06-A Same-13-UTC Handoff: OPEN

The retained Cloud-BAL producer input is `2026-08-16T13:00:00Z` (epoch
`1786885200`), but the available producer NetCDF remains diagnostic-only. It
does not establish a WPS/metgrid/real/WRF handoff or authorize promotion. The
separate native initialization readback is for `2026-08-16_12:00:00`; its own
receipt states that it is not the same analysis candidate and that first
physics and the microphysics moment contract were not assessed
([PR80 WRF readback](evidence/pr80_wrf_initialization_readback_20261012.json),
`valid_time`, `same_analysis_candidate_assessed`,
`first_physics_call_assessed`, and `microphysics_moment_contract_assessed`).

The same-13-UTC pipeline stages **ungrib, metgrid, real, and `wrf_init` have
not been run** with this candidate. No active, hash-identified WPS/metgrid/
real configuration or executable is bound to it. A source-bound `wrf_init`
record must identify the exact WRF source revision and source hashes, binary
hash, namelist/configuration, input-file hash, valid time, and the initialization
arrays actually read. A source trace alone is not runtime-consumption evidence.

The existing pressure-to-WPS mapper carries candidate temperature, height,
U/V, vapor, and hydrometeors while retaining four required ancillary fields
from a time/grid-matched WPS background: **RH, SLP, skin temperature, and snow
cover** (`src/common/cloud_bal_wps_adapter.f90`,
`pressure_wps_fields` and `map_pressure_candidate_to_wps`). Those four values
are retained from an authentic background for the same valid time and grid
under the current adapter contract. A different RH reconstruction would need
an explicit thermodynamic/observation contract; it is not provided by this
handoff. Missing ancillary inputs must not be invented. The LAPSPREP
writer also supports an optional `SOILHGT` record paired with `PSFC`, with
`real` required to select the documented surface-pressure path
(`src/lapsprep/module_lapsprep_wps.f90`, `output_ungrib_format`). This is an
additional writer/configuration condition, not a substitute for the four
ancillary fields.

Do not map pressure-coordinate omega into W: the adapter deliberately has no
omega member and makes no vertical-velocity-authority claim. The handoff stays
`OPEN`, the candidate stays diagnostic-only, and no same-13-UTC native
initialization or science acceptance is implied. The producer checkpoint also
lists WPS/metgrid/real and native Q/N/B initialization as remaining work
([CP06-A producer checkpoint](CP06_A_JOINT_PRODUCER_20261012.md#remaining-checkpoint-work)).
