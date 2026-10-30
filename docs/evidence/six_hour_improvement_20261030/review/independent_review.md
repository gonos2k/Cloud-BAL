# Independent six-hour improvement review

**Status: GO.** The runtime, independent score replay, report tables, and rendered figures passed review. No unresolved scoring or presentation blocker was found.

## Runtime and comparability

- The `IMPROVED_BG_FIXED` run completed with exit code 0 in 818.76 seconds and wrote the exact seven histories from 12 through 18 UTC. The runtime receipt and the 20-file runtime manifest validate.
- The 89 staged inputs, producer source inputs, and pre-existing evidence were unchanged. The executable, `wrfinput_d01`, boundary file, and duration-only namelist changes match the pinned preflight contract.
- The 13 UTC history is byte-for-byte identical to the prior one-hour B1 history (`8b4ead8741dff7284b1de140038d85ba48a474d6b8b98e1905e10ddbac165702`). The selected precipitation, near-surface, and hydrometeor fields also match exactly.
- Comparisons with historical ORIGINAL and CURRENT_HYDRO are correctly described as combined contrasts: those controls use older WRF and different initialization/preparation. The six-hour run does not isolate the background policy effect from the executable change.

## Independent score replay

I recomputed the scores directly from the six saved NPZ arrays. All six arrays contain 3,688 unique paired points with consistent spatial identifiers. Every CSV row matched the independent calculation:

- 108 categorical rows: contingency counts, CSI, ETS, POD, FAR, and frequency bias;
- 18 continuous rows: means, ME, MAE, and RMSE;
- 72 paired transitions: hit gains/losses and false-alarm gains/losses.

The +1-hour forecast, reference, coordinates, and point identifiers match the PR135 `POLICY_BG` arrays exactly. The report’s CSI, ΔCSI, continuous-error, ETS, POD, FAR, and frequency-bias tables match the sealed CSV rows at the displayed precision. The reported 21 improvements and 15 deteriorations across 36 lead/threshold combinations are correct against both baselines.

## Report and figures

- UTC/KST windows, one-hour accumulation units, threshold convention, and score equations are correct. The report explicitly distinguishes each hourly window from a cumulative 0-to-lead total and keeps claims bounded to one event.
- The visual review found no rendering or labeling issue. Lead windows, map titles, shared one-hour accumulation color scale, and summary axes are clear; the maps state that they show paired points rather than full interpolated coverage.
- Final targeted tests passed: scorer 6/6 and figure renderer 3/3 (combined 9/9). The renderer reproduces all nine assets byte-for-byte, succeeds without archived host source paths, and preserves existing output when input CSV integrity fails.
- Runtime manifest SHA-256: `c8e2d31dd2edf502534155c8ff4a614dd9be680627644c18218565023977f113`.
- Analysis receipt SHA-256: `0db2f02ceece4d2f12cec459f5af26ca589b2f70c53c3d559b596b10828d8826`.
- Figure manifest SHA-256: `790511a79976968952e7fa6c5046959f0aaf63b808d6a3f2b2c912d17a06f679`.
- Report SHA-256: `8ec4da9a7622c513e27342c12826ff33cd21feedc2db6f9d72af9fdf7882085c`.

## Limits retained in the report

The results are one event and one spatial case; the 3,688 points and 36 time/threshold combinations are not independent weather cases. RN1 is a processed analysis without a coverage bitmap, so underlying input freshness and spatial representativeness remain uncertain. The background policy changes eight native initialization fields. These results do not establish a QR/QS-only effect, process-level flux attribution, full water/energy closure, performance on other events, separate C2 stability, or operational suitability.
