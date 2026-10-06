# PR59 current 12 UTC native handoff and KDM6 first call

Date: 2026-10-06. Scope: the published PR59 2026-08-16 12 UTC candidate, one
native `real.exe` handoff, and one 20-second WRF diagnostic run capturing the
first public KDM6 call. This is execution evidence only; it is not native
startup authorization, forecast validation, or science acceptance.

## Candidate to real

The selected producer is transaction `lapsprep-262281200-9017919-o0`, source
commit `90179191edc33b5ae5606a37f4cd67eac507eed0`, valid time
2026-08-16 12:00 UTC. Its committed generation is
`/var/tmp/cloud_bal_pr59_current_lapsprep_20261002/generations/lapsprep-262281200-9017919-o0`.
The manifest binds `candidate.wps` SHA-256
`fbe2238d13a4308ea7ef53a1d13196e2791801974c696ce8951127d14f043afc` and
`candidate.wps.shadow.nc` SHA-256
`222989c98a62804696f9264267c85725ab443bcab99f6a20f3a736dbcfac34ff`; its
retained validation says `verify_shadow_wps_pair` PASS. The producer mode is
`LIQUID_RADAR_RH1_PHI`, balance disabled. Its compiler process closure remains
`NOT_ASSESSED`.

Metgrid copied that exact WPS byte stream to `LAPS:2026-08-16_12:00`. The
source and copied-file SHA-256 values match. It used the retained metgrid
executable SHA-256
`3107306ad0f8702e818eb84d8d4f9c96561b3632ffbaf2b157b5e284e1a18afe`,
`METGRID.TBL`, `geo_em.d01.nc`, and same-time KLBG/RCHA/SOIM/SOIT plus SST and
TAVGSFC inputs from `scratch/cp02_actual12_liquid_wps.HisIOM/metgrid_LIQUID_RADAR_RH1/`.
The output `met_em.d01.2026-08-16_12:00:00.nc` has SHA-256
`c296c7657f7c259bb26fc523407c61f87b083a6680399b989639518f6dc4fb93`; the
metgrid log reports successful completion.

Pinned Intel `real.exe` completed with an unlimited stack. The successful
run used current-candidate 12 UTC metgrid data and a retained 15 UTC metgrid
boundary input from the prior run tree. It wrote `wrfinput_d01` SHA-256
`397daf0387d522243167f5e48831f7415bea07f00c22e5674ef89f73db1a2c0c` and
`wrfbdy_d01` SHA-256
`64ab86c004af0f81b221c89c5bfb6ff57aef7410c7f5542ce93c00c7f732009d`.
`real.exe` with the default shell stack limit had also faulted on retained
control met_em files; increasing the stack resolved that runtime failure. It
was not a candidate-specific input failure. The mixed-time boundary provenance
is retained here explicitly.

## Native first-call capture

The baseline run directory is
`/var/tmp/kdm6_first_call_pr60_20261006/native_first_call_20s`. It starts at
2026-08-16 12:00:00 and ends 20 seconds later, uses `MP_PHYSICS=37`, one MPI
rank, 20-second timestep, and completed at 12:00:20. No longer forecast was
run. The WRF input/boundary hashes are the two values above. The executable
SHA-256 is
`ab8cc24579adb6112684029636e3bdd2ab06e6fa600721b7ee6c322b21a7ba62`.

For this isolated diagnostic build, the selected private KDM6 source was
`scratch/ccn_native_start.j2U4Rf/phys/module_mp_kdm6.F` (SHA-256
`9f34e893e814872138f8d8402095be0cc76fbf0700c6095f69d7f530c05bcdae`). The
replayable instrumentation patch is
[native_kdm6_first_call_trace.patch](native_kdm6_first_call_trace.patch); its
applied source has SHA-256
`9986e3ecfc116bb1a723d68dc423418541971f421d5a6dfafa47e59273bf6a80`, object
`a19086f7ce3d650004ca5599f3a6ceae50acdb3f63a8a4ee3cfa55fc51036902`, and
`start_em.o` is
`76bb6306e334c261045a0f28e8c4a24b2a5afcbc9025d4a45e2b21bce67dd7c9`.
The reused KIM-meso main objects and host libraries are listed in
`/var/tmp/kdm6_first_call_pr60_20261006/private_trace_build/host-link-inputs.sha256`.
Only the private KDM6 source/object was instrumented and rebuilt; this is not
a clean, closed host rebuild and makes no operational-equivalence claim. It
used the pinned Intel profile (`ifx 2026.0`, Intel MPI 2021.18),
`CLOUD_BAL_REPRO_FLAGS` plus fixed/free preprocessing with `-DRWORDSIZE=4`
and `-convert big_endian`. The stream parser deliberately decodes the
observed big-endian int32/real32 stream rather than host-native byte order.

The trace writes immediately on entry to public `kdm6` before the wrapper
converts public number-per-kg fields to internal number-per-m3 at lines 332–338
of the isolated source, and immediately after the return conversions at lines
373–378. The host driver call is at
`KIM-meso/.../phys/module_microphysics_driver.F:2535`, passing
`TH=th`, `PII=pi_phy`, `DEN=rho`, `P=p`, and `DELZ=dz8w`. The trace captures `TH`,
`PII`, `DEN`, `P`, `DELZ`, vapor `Q`, mass fields `QC/QR/QI/QS/QG`, moments
`NN/NC/NI/NR`, graupel volume `BG`, `DIAGRHOG`, and `XLAND`, plus timestep,
bounds, and CCN parameters. The selected public KDM6 wrapper computes physical
temperature at entry as `t(i,k)=th(i,k,j)*pii(i,k,j)` (isolated source line
325); the host driver binds `TH=th` and `PII=pi_phy` at lines 2535–2549.
Accordingly, `T_K` and its pre/post change are calculated from elementwise
products of the captured `TH` and `PII` arrays. They do not treat `TH` itself
as physical temperature or use a separate modified-temperature convention.

The trace contract records `TH` in K, `PII` dimensionless, `DEN` in kg dry
air m⁻³, `P` in Pa, `DELZ` in m, water vapor `Q` and hydrometeor masses
`QC/QI/QR/QS/QG` in kg kg⁻¹ dry air, number moments `NN/NC/NI/NR` in
number kg⁻¹ dry air, and `BG`/QIB in m³ kg⁻¹ dry air. `DIAGRHOG` is a
diagnostic density in kg m⁻³; `XLAND` is the categorical land/sea mask. These
are the selected private profile's public dry-air bases; the wrapper multiplies
number-per-kg values by `DEN` only for the internal KDM6 call.

The `SAVE` flag and fixed filenames make this diagnostic serial and one-tile
only. One MPI rank and one active tile were used. The capture summarizes the
active compute tile only, shape X×Y×Z = 232×280×39 (2,533,440 cells); halo
and outer-boundary cells are excluded. The raw data include the complete
allocated arrays, but this parser intentionally reports the active tile.

The raw captures are:

| Stage | timestep | bytes | SHA-256 |
|---|---:|---:|---|
| pre-call | 1 | 195,542,592 | `aa01a611b81cf041961748a945e91b4d52aa6704c9fea4398ec7cbe9138139b2` |
| post-call | 1 | 195,542,592 | `ffdfabb7fadb3d986400003ecc0283af1511c4f6931c842130c3309852fd7c1c` |

All traced values were finite on the active tile before and after this call:
2,533,440 of 2,533,440 cells for every 3D field and 64,960 of 64,960 for
XLAND. Pre-call ranges were T (`TH*PII`) 200.10356–302.50415 K, DEN
0.0839428–1.16266 kg m⁻³, P 5266.79–101726.96 Pa, and QV 1.51704e-7–
0.0225213 kg kg⁻¹. Negative near-zero hydrometeor mass values were present
at entry (QC 32,457; QI 6,584; QR 1,835; QS 1,923; QG 113 cells); this trace
does not pre-clamp or conceal them.

Before the first call, `NN`/QNCCN was the only nonzero number field. The
selected private profile documents its `start_em` initialization: configured
`ccn_conc=1.0e8 m⁻³`, `scale_h=750 m`, land multiplier 50, sea multiplier
0.5, converted to public `number kg⁻¹ dry air` with `al+alb`. The pre-call
trace had 98 negative and 88 zero NN cells among the active cells (minimum
−11.04799; maximum 5.0290033e9), so this capture is not a blanket validation
of that profile's cellwise output.

`NC`/QNCLOUD, `NI`/QNICE, `NR`/QNRAIN, and `BG`/QIB were all zero at call
entry (all 2,533,440 cells). Every positive-mass pair therefore had a missing
moment at entry: QC/NC 1,510,952; QI/NI 835,790; QR/NR 361,253; QG/BG 7,377.
This matches the private profile's `NO_IMPLICIT_INITIALIZER` contract for
those four fields. The public PR59 candidate and `real.exe` handoff do not
provide authenticated native moments or denominator/units evidence for them.
These zeros are observed bytes, not authorized initial conditions.

After the KDM6 call, all fields included in the KDM6 raw trace remained finite,
but the call changed
the moment/diagnostic arrays: NC at 49,765 cells, NI at 187,744, NR at 37,577,
BG at 65,764, and DIAGRHOG at 68,749. Derived temperature changed at
1,181,404 cells (maximum absolute change 3.94824 K), vapor Q at 1,163,080
cells (maximum absolute change 0.00130204 kg kg⁻¹), QC at 1,543,443 cells,
QI at 852,155, QR at 365,542, QS at 263,703, and QG at 69,347. These are
per-field changes; no sum of mixing ratios is presented as physical mass.
Positive-mass/zero-moment gaps remained for QC/NC at 238,835 cells and QR/NR
at 33,617. QI/NI and QG/BG gaps became zero in this post-call state. This
records model numerics, not an initializer or physical prior.

In selected `ProgB_param` source (lines 3367–3384), `qrs(i,k,3)>qcrmin` or
`brs(i,k)>brs_min` enters the graupel branch. If `brs==0`, the numerical
fallback assigns `rhox=rho_max=900 kg m⁻³` (except a negative signed zero);
after bounds, the branch computes `brs=qrs/rhox`. Call-entry `BG` was zero,
while post-call `BG` changed at 65,764 cells and `DIAGRHOG` reached 900. This
is observed numerical recovery behavior, not a source-authorized physical QIB
initializer. It is distinct from the historical `rho_mid=400 kg m⁻³`
parameter. Do not interpret reconstructed BG as a PR59-provided initial
condition.

## Reflectivity and the negative CCN values

The baseline namelist used `history_interval=60` minutes, so its only
`wrfout` was the start-time record. That record's `REFL_10CM` was finite zero
at all 2,573,532 native cells. A separate replay used the same WRF executable,
`wrfinput`, `wrfbdy`, physics settings, and first-call raw trace hashes,
changing only history cadence to `history_interval=0` minutes and
`history_interval_s=20` seconds. Its output file SHA-256 is recorded in
[`evidence/pr60_current12_kdm6_first_call.json`](evidence/pr60_current12_kdm6_first_call.json).
The two cadence-repeat raw trace hashes exactly match the baseline pair, and
the repeat `wrf.exe`, `wrfinput_d01`, and `wrfbdy_d01` hashes also match. The
two-record `wrfout` has SHA-256
`ae069a7a36ea637e50029cf31c604fce3e14ceb1a9f8e057d53ed9123a58a74d`.
At 12:00:20, `REFL_10CM` had 2,539,915 finite cells and 33,617 nonfinite cells
out of 2,573,532; 105,076 values were positive, 40,092 were zero, and
2,394,747 were negative (the −35 dBZ floor is represented as negative). The
range was −35 to 69.2933 dBZ. All 33,617 nonfinite cells mapped exactly to
post-KDM6 active-tile cells with `QR>0` and `NR=0`; no nonfinite reflectivity
occurred outside that mask. In `refl10cm_kdm6` (lines 3915–3920 and 4041),
rain mass above threshold forms `lamr` from `nr` and then uses its
inverse. This source/state alignment ties the missing rain moment directly to
the nonfinite reflectivity diagnostic. It is a failed gate, not a successful
post-call validation.

The start-time `wrfout` QNCCN profile reconstructs against the private startup
rule with maximum relative error `5.73821e-06`; its QNCCN is positive
(`0.000310588` to `5.02923264e9` number kg⁻¹ dry air). At KDM6 entry later in
the timestep, `NN` had 98 negative and 88 zero active-tile cells.
`module_microphysics_driver.F` passes live `qnn_curr` to KDM6 (around line
2535); the trace is written before public-to-internal wrapper conversion and
before KDM6's later internal clamp. There is no intermediate capture between
start-time output and that call, so the negative-cell origin is unresolved.
No clipping or new CCN prior is inferred from this trace.

## Replay and tests

With NumPy installed, replay the saved bytes and validate timestep 1:

```bash
python3 tools/native_kdm6_trace.py \
  /var/tmp/kdm6_first_call_pr60_20261006/native_first_call_20s/kdm6_first_call_pre.raw \
  /var/tmp/kdm6_first_call_pr60_20261006/native_first_call_20s/kdm6_first_call_post.raw \
  --expected-timestep 1 \
  --output /var/tmp/kdm6_first_call_pr60_20261006/native_first_call_20s/kdm6_first_call_summary_replay.json
python3 tests/test_native_kdm6_trace.py
```

The parser rejects wrong byte order/magic, malformed or truncated fields,
invalid bounds/parameters, malformed names, and stage/timestep mismatch; it
retains nonfinite counts while emitting JSON-safe finite extrema. Ten tests
cover these cases and paired moment gap/change calculations. The parser is
registered in `tests/run_python_contract_tests.sh`.

The native execution stopped after 20 seconds. Resolving an authorized
initialization for all four missing moments, the negative/zero QNCCN cells,
and full host source/build closure are blockers before any longer forecast.
