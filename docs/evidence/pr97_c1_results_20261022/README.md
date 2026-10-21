# PR97 C1 matched history response

This evidence compares the already closed PR96 C1 OFF, HYDRO, and COUPLED 600 s runs. It reads their saved WRF histories and receipts; it does not launch model runs. The response analyzer is `tools/pr94_hydro_response.py`; the full numerical output is [hydro_response.json](hydro_response.json).

## Boundaries and identity

- All three receipts report `COMPLETE`, return code 0, and step 30/30. The executable SHA-256 is `a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d`.
- The runs share namelist SHA-256 `afc366ae884021ae5eb91510f61a137cab30880ba9a81702094e763e5fb52f35` and boundary SHA-256 `885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7`. Their initial conditions remain arm-specific: OFF `23a948dfbea1cd9f1d69d9aad30531218a4c93ac6a82159e73e5505e39440200`; HYDRO `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c`; COUPLED `d10c2b987856586c9b8105a69eaeda03951f85f29be3ec4e7118d4f79b478c2d`.
- HYDRO's receipt-bound source input chain was revalidated by the analyzer. All histories have matching grid coordinates and hybrid coefficients and matching saved timestamps at 0, 60, …, 600 s. The fixed support masks contain 613 source cells, 2,496 cells in the 2-cell Chebyshev buffer, 7,644 in the 5-cell buffer, and 2,533,440 in the active history domain.
- Masks derive from `docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json` (SHA-256 `331eb9837c41a7aa663864c348f8fe18c44f8e55feed736900f5029685b1aa64`).

## Reading the result

`hydro_response.json` records direct HYDRO−OFF, COUPLED−HYDRO, and COUPLED−OFF vector metrics at each saved history time for vapor, cloud, rain, ice, snow, graupel, pressure, geopotential, and mass-point winds. The pointwise identity `COUPLED−OFF = (HYDRO−OFF) + (COUPLED−HYDRO)` holds to zero reported residual for all fields and times. This is an algebraic check, not causal attribution; RMS differences are not additive.

On the fixed 613-cell support, the table gives spatial RMS of each actual field difference at selected saved times. `H−O` is HYDRO−OFF; `C−H` is COUPLED−HYDRO. See the JSON for full-active-domain and buffer results.

| Time (s) | Pressure (Pa) H−O / C−O / C−H | Geopotential (m² s⁻²) H−O / C−O / C−H | W (m s⁻¹) H−O / C−O / C−H | QCLOUD (kg/kg dry) H−O / C−O / C−H |
|---:|---:|---:|---:|---:|
| 0 | 8.527 / 8.527 / 0 | 38.276 / 38.276 / 0 | 0 / 0 / 0 | 1.251×10⁻⁴ / 1.251×10⁻⁴ / 0 |
| 60 | 68.260 / 78.194 / 34.533 | 42.788 / 72.734 / 66.119 | 0.2450 / 0.3471 / 0.2576 | 4.245×10⁻⁵ / 5.054×10⁻⁵ / 2.163×10⁻⁵ |
| 120 | 21.439 / 31.350 / 20.287 | 35.746 / 59.358 / 45.636 | 0.2540 / 0.3402 / 0.2265 | 2.912×10⁻⁵ / 4.584×10⁻⁵ / 3.532×10⁻⁵ |
| 600 | 4.241 / 5.902 / 3.847 | 4.439 / 11.059 / 10.618 | 0.1120 / 0.2260 / 0.2034 | 2.286×10⁻⁵ / 3.295×10⁻⁵ / 2.532×10⁻⁵ |

All entries are direct spatial RMS values from the paired saved arrays; C−O was computed directly and not inferred from the component RMS values. For pressure, W, and QCLOUD, C−O remains larger than H−O at 60, 120, and 600 s (equal at 0 s). For geopotential it is also larger at those three later times. C−H is supplementary and varies by field and time; it does not show a consistent reduction. This describes paired-run differences, not adjustment quality or observational skill.

The JSON also records actual staggered U/V/W face arrays at 0, 60, 120, and 600 s using `pr94_cloud_response.read_face_winds` and the same outer-ring crop as PR94. These comparisons use each full declared active face crop, separately from the 613-cell mass-point mask and mass-point wind statistics. Shapes, sample counts, direct pair delta RMS, and maximum absolute deltas are included. No face flux, continuity, or mass-wind closure is inferred.

The separate PR96 C1 audit queue remains `REVIEW_REQUIRED` / `FAIL_OPEN`. For each arm, the generic Q/N/B audit is `FAIL` (OFF 161 failures; HYDRO 159; COUPLED 159), while the exact source endpoint audit is `PASS` and the active-ice 8-ULP policy is `PASS`. These are distinct policies; none is promoted by this response report. The queued audit receipts and their digests are listed in `scratch/pr96_local_closure_20261021/closed_audits/pr96_c1_20261021/overview.json` (SHA-256 `201ab705b5f96a59f1e7c8f26e17cb42147eadfd9cbaff621cded60c92097a51`).

This report grants no scientific approval. Differences describe outcomes from separate initial states under a shared boundary; they do not isolate mechanisms or establish observation skill, continuity closure, or forecast value. The C1 audit JSON does not measure negative COND or partial evaporation. Those claims belong to the separate original C4 two-column trace and must retain that trace's scope.

The bounded receipt, audit, build, preflight, input, namelist, boundary, profile, history, and timestamp identities are recorded in [closed_results.json](closed_results.json); the file references the audit overview by SHA-256 rather than duplicating its source payload. Each receipt, audit, and generated history hash was checked against the overview and the response analyzer's verified history identity.

## Reproduction

From `Cloud-BAL`:

```sh
python3 tools/pr94_hydro_response.py \
  --off-run /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/OFF_600s_c1 \
  --hydro-run /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/HYDRO_600s_c1 \
  --coupled-run /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/COUPLED_600s_c1 \
  --expected-executable-sha256 a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d \
  --output docs/evidence/pr97_c1_results_20261022
```

Result JSON SHA-256: `e53345d8539cbcde99017db0e9a46a09291c2caa61befde4278d1c5e5efe73eb`.
Closed results JSON SHA-256: `bb69a2ec7ce83902c589ce6b3fa0464c3ade0e3e94d13c7a9ba45b5c32b6ba7f`.
