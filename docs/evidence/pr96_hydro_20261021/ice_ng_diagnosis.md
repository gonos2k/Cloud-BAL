# PR96 HYDRO T26 ice nongraupel base diagnosis

## Frozen runtime evidence

The closed HYDRO receipt identifies the executed C4 image as
`20aaa6058797e7d1ec7a874ae92ed44f9ac19876ef2f14477b5eedb6a1ae44be` and
records the fatal `KDM6 invalid base before nongraupel admission` after 25
completed calls (500 model seconds). The hash-bound stdout is
`runs_on_lustre/HYDRO_600s_c4_current/run/rsl.out.0000.gz` under the PR94
run root. Its fail record names timestep 26, latitude 67, i=207, k=19,
loop=1, and prints `n=2` as the literal source diagnostic field; this report
does not infer a substep meaning for that field.

The same record reports search status 1, `rain_full_evap_pending=F`, and
`rain_ng_base_valid=F`. The twelve exact float32 words are the source-ordered
`rain_q_fixed(5)`, `rain_n_fixed(3)`, background, temperature, vapor, and dry
carrier density:

```text
2481A27B 3588833E 369D5018 3B761470 39F6208F 393A9AD4
438BCC94 460D2D82 358F6BA1 4384E934 3B93E58F 3F13A9EB
```

For the ice pair, `q=1.0170986115554115e-6`, `n=279.5982666015625`, and
`rho=0.5768114924430847`. C4 source constants give `lambda_min=9080`,
`lambda_max=1820000`, `dmi=3`, and float32 `pidni=1570.79638671875`. Using the
same operation order as the consumer's strict predicate, the lower ice
number bound is `279.5983589944634`; the captured number is lower by
`9.239290091045405e-5` (`3.30449e-7` relative). That is state validity
failure reason 7, the active ice PSD pair bound. The vapor and temperature
are positive; the printed rain, cloud, and background/graupel pairs do not
explain this failure.

The host T26 PRE_KDM6 trace records ice `q=9.49175159803417e-7` (REAL32
`357ECAD2`), published `NI=476.6050109863281` (`43EE4D71`), and REAL32
dry-air-volume number concentration `rho*NI=274.9112548828125 m^-3`
(`438974A4`). The public number-to-volume conversion is
`REAL32(NI * DEN)`. Its strict lower number bound is `260.92633896480805`,
so this host boundary passes. The fatal KDM6 base copy instead records
`q=1.0170986115554115e-6` (`3588833E`) and captured KDM6 ice number
concentration `n=279.5982666015625 m^-3` (`438BCC94`), with strict lower
bound `279.5983589944634`; the captured number is low by
`9.239290091045405e-5`. Thus the invalid pair is produced inside KDM6 after
the host PRE_KDM6 boundary.

The trace preserves T25 POST_KDM6 and T26 PRE_RK, RK1/2/3, and PRE_KDM6
boundaries. The archived trace was verified through EOF and its bounded
selection is recorded in `stage_trace.json`. All six recorded boundaries
pass the strict ice predicate. Source inspection then narrows the missed
completion: the internal stage 2 ice PSD completion block (source around
4232–4276) accepts the pair under the freezing producer's 8 ULP mean-mass
cone, while the subsequent NG base validator applies the stricter number
bound. There are no assignments to `qci(i,k,2)` or `nci(i,k,2)` and no calls
between that completion block and the NG base copy around 5244, so the
stage 2 completion output is the failing NG input. This proves a missed
producer contract at stage 2; the captures do not identify the exact earlier
within-KDM6 operation that first moved the state across the strict boundary.
The source-derived replay feeds the archived failure pair through each
completion block to verify the local repair, without presenting that replay
as an original intermediate-state capture.

## Minimal source correction

`tools/pr96_ice_ng_contract.py` pins the C4 source SHA and adds one shared
strict active-ice number predicate. It uses the consumer's exact bound
operation order, returns the number endpoints for producer direction
selection, and is called by the strict nongraupel consumer and all three
active-ice completion blocks. A strict lower or upper number miss directs the
existing `pr85_kdm6_psd_bound_number` helper to the corresponding endpoint.
The existing 8 ULP freezing cone remains in place, and the native inactive
ice allowance remains unchanged.

The source-derived Intel regression resets the captured failing REAL32 number
before each of the three completion blocks, then checks the directed endpoint
against the shared strict predicate and existing producer cone. For each of
three q/rho scales, it also feeds the adjacent REAL32 values just outside
both strict bounds independently through all three producer blocks and checks
that each repair restores strict validity and stays inside the producer cone.
The helper's availability and validity outputs are separate arguments. The
inactive cutoff case is checked for no new reconstruction. Pinned IFX2026 O0
and O2 commands, working directories, profile hash, source/test/fixture hashes,
and results are recorded in `ice_ng_o0_o2.txt`.

## Limits

No HYDRO model rerun is included here. The source-level harness establishes
the local repair and validator contract; it does not establish forecast
runtime closure, full three-arm closure, or physical approval. The available
stdout gives exact failure bits and current producer/consumer code, but no
checkpoint for each earlier producer boundary. The Cloud-BAL graph snapshot
also does not extract the legacy KDM6 Fortran module; source is authoritative
for this diagnosis.
