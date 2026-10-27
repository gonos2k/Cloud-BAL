# RN1 additional verification: source and provenance findings

## Producer identity

The local source matches the six-hour inventory's source pins:

| Source | SHA-256 |
|---|---|
| `klaps-v5.0_/dfsd/ODAM/klps_lc05_dfsd_odam.f` | `f0088086ee3db6fe7ef7aa8faa2e9d4bc9fedd282f9c3b67fdd56bf9f5ecce16` |
| `klaps-v5.0_/dfsd/RAIN/klps_lc05_dfsd_rain.f` | `02a78c9c1c013b748d68bcfc6bc4e1560a4bba637db7aa52f00123ec78f4765a` |
| `klaps-v5.0_/dfsd/RAIN/read_radar.f` | `59881dee6763e1d08988c2f3138423fb75df74d394f1db9def297edeea79beee` |
| `klaps-v5.0_/dfsd/RAIN/read_lng_radar.f` | `dfb86901666c7b8b7e750500b49f20481c43cbc4f193a8b73f81599c2521d34b` |

This pins the declared producer source, but not the historical executable or its complete runtime inputs.

## Definition and clock

- `klaps-v5.0_/dfsd/ODAM/klps_lc05_dfsd_odam.f:247-269` parses `str_date10` as the analysis time and derives `date_local` by adding nine hours.
- `.../klps_lc05_dfsd_odam.f:888-894` writes `DFS_VSRT_GRD_KLPS_ODAM_RN1.YYYYMMDDHH00`; the text header writes analysis time with `+000hour` and a separately labelled LST time. Data follow as `10F7.1`, with x varying fastest.
- `.../klps_lc05_dfsd_odam.f:47-50` defines the 149x253 output crop from source grid x=76..224, y=7..259 (inclusive, one-based).
- `Cloud-BAL/scratch/cp02_six_hour_20260914/reference/inventory.json:64-74,130-138,194-202,258-266,322-330,386-394` records all six 13-18 UTC stamps, LST headers 22-03, shape, byte count and canonical product SHA-256.

## Input, hourly interpretation, missingness and coverage

- `ANAL/NE57/SHEL/klps_lc05_dfsd_odam.csh:27-41` takes ANLTIM from `anal.tim`, derives LST+9 and the previous-hour timestamp.
- `.../klps_lc05_dfsd_odam.csh:91-114` selects `anal_rain_${ANLTIM}00.gdat` when present, otherwise symlinks `anal_rain_${P01TIM}00.gdat` (previous hour) to the current-time filename. Therefore the RN1 UTC filename/header alone does **not** prove the rain analysis input was fresh at that hour; archived per-run logs or input receipts are needed to resolve fallback for each hour.
- `.../klps_lc05_dfsd_odam.csh:153-156` exports `INFILE_RAIN`, runs ODAM using the current ANLTIM, and moves the RN1 output to `${KL05DAOU}/DFSD/${ANLYMD}`. This is the operational copy path to inspect if accessible. The six-hour inventory instead names the delivery path `/NHNHOME/WORKSPACE/26weather002_A/yhlee_data/ODAM/20260816`; that path was absent at initial inspection. Root reports the recovered originals at `/NHNHOME/DATA/yhlee_data/ODAM/20260816`.
- `.../klps_lc05_dfsd_odam.f:774-812` reads direct-record INFILE_RAIN; each output point uses a 5x5 max from the 1-km rain analysis. `:817-867` suppresses values using cloud coverage / mask and applies a `<0.1 => 0` threshold. `:827-839` overwrites with valid AWS station rain; `:869-885` performs area-to-station and priority-station overrides.
- `klaps-v5.0_/dfsd/ODAM/read_curl_aws.f:53-60,250-255` identifies AWS `rn_hr1`, accepting nonmissing values from 0 to 600. The RAIN pipeline includes radar, LNG radar and AWS composition (see `klaps-v5.0_/dfsd/RAIN/klps_lc05_dfsd_rain.f:727-795`; README history at `.../RAIN/README:16-21`). Thus RN1 is a processed observation analysis with station adjustments, not raw independent gauge truth.
- The RN1 text has no explicit missing/coverage bitmap. Inventory reports 37,697/37,697 finite, zero negative values for each file; this proves complete serialization, not radar/gauge sensor coverage. The retained verification also uses a fixed South Korea land mask of 3,688 points.
- Existing source reference `Cloud-BAL/docs/CP02_ODAM_PRECIPITATION_REFERENCE_20260914.md:19-21,40-44` calls RN1 one-hour accumulated surface precipitation, but advises preserving numerical units until the upstream rain-unit contract is checked and matching model accumulation to the same hour. The code pins the valid/analysis endpoint, not an accumulation-start timestamp; avoid claiming more interval semantics than the upstream contract establishes.

## Alternate archive identity

Six RN1 files at `/NHNHOME/WORKSPACE/26weather002_A/aroma37/exp_yoona171/PRCP_DATA` exist for 202608161300..1800. All have the expected 267686-byte size and matching UTC/LST header stamps, but every SHA differs from the canonical six-hour inventory. Alternate SHA-256 values:

| UTC | Alternate SHA-256 | Canonical inventory SHA-256 |
|---|---|---|
| 13 | `e8784a25af62474975bc8659fb200acc215bd25877ac5700cc5827fb3db92b30` | `5f435e9e7845860636b8ac6d4a982563f1d709f4340dadb7828df2f2cda8e9a1` |
| 14 | `d65f46f20127ec11c3122cbc35b333139d0af86892d47d541973e21786ea0ca4` | `54ba0fe609630eec8366b9f4a21fddd29baabbd1ad89e8a2ac4e769900887497` |
| 15 | `04ebd0953f52ec50a2ea6b86851a4469ddb9c4358642f999204cabf1565af74b` | `00219ebc741da5bbdc79b408a1363e4a920d4f58d41118978234d2cbe089f346` |
| 16 | `194125b7b50fc1be87c4abaf993a0ba0ef7f833ea4af3eeb25cfbe4eaee58feb` | `74f2b96af4e0686b15dc1c8a75e337f964a9e25841540a61b3d3546e22187af6` |
| 17 | `0def605a640d1df22e261dcef7d588e0d07f82a0532fdba04b3c76bff6f2bbfd` | `77145a0b095203e452cc029cf56a97f1ff10a5485b69f76ab1d21219c15fa2d5` |
| 18 | `c43533da2c0525fd28fbac0524ff2aa285535d2a88fd71b5de09df442df21d04` | `f0b6834a27449904efb7f6242e47a6246d75ad1403d6eb24ce82c689f00557bc` |

These are a different artifact version and should not substitute for canonical files. Their matching headers and byte lengths are insufficient provenance. The maintained audit already records the rejection (`wiki/log.md:2606`).
