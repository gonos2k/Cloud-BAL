# PR88 T4 NG-base diagnosis (read-only)

## Provenance and scope

- OFF600 run log: `/var/tmp/pr87_followup_OFF_600s_v50_20261019/run/rsl.out.0000.gz`, SHA-256 `3c53784ea0cd2071421f900f4594d82421f18d81d636cd41b09353e457b773b3`.
- The run closed `INCOMPLETE`, return code 128, after 60 s. This T4 failure is beyond the previously passing 60 s scope.
- V50 `sources.json` selects `/var/tmp/pr87_followup_sources_20261019_v44/module_mp_kdm6.F` for KDM6, SHA-256 `769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f`.

## Observed failure

At timestep 4, KDM6 reports an invalid base before nongraupel admission at `lat=115, i=26, k=18`, outer loop 1. The rain nongraupel search returns status 1 (`NO_FEASIBLE_STEP`); KDM6 validates the unchanged base and finds failure reason 6 in `kdm6_rain_process_state_valid`, the strict rain number upper bound (`n(3) > rain_max*q(3)`, source lines 1192–1194). The printed/hex state is finite and nonnegative, and `QR=7.4702882768562517e-11` is above `qmin≈1e-15` but below source parameter `qcrmin=1e-9`. The graupel density is about 895.46 kg m-3, within [100,900].

## Source transition that explains it

The matching `PR85_RAIN_FREEZE` record is for `(i,j,k)=(26,115,18)`, loop 1. Its `TT` flags say the packet base was valid and the packet was accepted at fraction 1.0. It records this rain pair transition:

| state | Qr (kg/kg) | Nr (m-3) | Nr / strict maximum |
|---|---:|---:|---:|
| before packet | 7.4702938279713749e-11 | 1.6309607028961182e-1 | 0.9999999933651578 |
| after packet | 7.4702882768562517e-11 | 1.6309605538845062e-1 | 1.0000006450932586 |

These `Nr` values are KDM6 internal volume number concentrations: the source converts public number-per-kg inputs to internal `nrs` by multiplying by dry density (lines 468–481), and converts them back on output (lines 1568 ff). Thus the table units are m-3; they are not the public number-per-kg basis. The strict maximum here is `rho*35000**3/pidnr`, using the source-pinned runtime coefficients `pidnr=12566.37109375`, `dmr=3`, `lambda_r_max=35000` (identity guard at source lines 1402–1404). Before the packet the pair is just inside the strict bound; after it is outside by about 6.45e-7 relative. The post-packet Qr/Nr are exactly the values in the later NG-base failure state.

KDM6 calls `pr85_kdm6_rain_freezing_packet` at lines 3739 ff with rain mean-mass bounds `pidnr/lambda_r_max**dmr` and `pidnr/lambda_r_min**dmr`, then stores the accepted returned Qr/Nr at lines 3768–3769. The packet's `rain_cone` check (lines 8730–8743) allows an 8-float32-ULP allowance at each mean-mass bound. At this lower bound, `mmin=2.9309320335276967e-10 kg` and the code allowance is `2.2204460492503131e-16`; the post-packet mean mass is `2.93093014280442e-10`, short by `1.8907232766387847e-16`, so it falls inside that allowance. The transition is therefore consistent with the packet's permissive lower mean-mass tolerance near the maximum-rain-number edge, but the resulting endpoint fails the later strict state predicate. This is a source-supported explanation for the observed invalid base; it does not establish whether that tolerance is scientifically intended.

The logged failed state hex is `36CCE783 328B8E77 2EA445FC 33A266F0 300669B5 4B847172 46897685 3E2702A7 2B19B507 4384C1BD 3B706993 3F23D06F`, ordered `[q(1:5),n(1:3),bg,T,qv,dry_density]`. The extracted-validator replay with the exact source-pinned `pidnr` and correct coefficient order reports:

```
STATE_VALID_REASON F 6
RAIN_N_OVER_MAX 1.00000064509326
```

`replay.F90` and its log are retained beside this note. The replay validates the logged state and predicate; the observer's `PR85_RAIN_FREEZE` row provides the before/after transition evidence.

## Correction to the earlier scratch note

An earlier draft incorrectly attributed the failure to cloud PSD. Its replay call had an extra positional argument, shifting subsequent cloud coefficients. That draft is superseded; the corrected replay uses exact pinned rain parameters and identifies the rain-bound failure above. No source or physics changes were made.

This diagnosis does not prescribe a code change or establish scientific approval.
