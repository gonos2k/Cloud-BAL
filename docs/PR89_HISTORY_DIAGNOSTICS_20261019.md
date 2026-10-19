# PR89 paired OFF/COUPLED history diagnostics

This report compares the receipt-bound OFF and COUPLED v50 WRF history files at elapsed 0 and 60 s. The generated summary is [paired_history.json](evidence/pr89_process_contract_20261019/history/paired_history.json); the analyzer is [pr89_paired_history.py](../tools/pr89_paired_history.py).

## Inputs and grid check

Both run receipts are `COMPLETE`, return code 0, and bind the input `wrfout_d01_2026-08-16_13:00:00` by SHA-256. Their expected timestamps agree from 13:00:20 through 13:01:00, with a receipt-derived history origin of 13:00:00. The paired history file hashes are:

| Arm | SHA-256 |
| --- | --- |
| OFF | `cebc524bc907d1c0e32c11dfa4b302893f25bf4e5574c412548c7eb4a03b6129` |
| COUPLED | `64e7ee9c67d826193caae46b1dddd1e7f8410690fea74deb15febefb9ec9eb67` |

The mass grids match exactly: 282 × 234 cells, `DX=DY=5000 m`. All 22 available static map, coordinate, hybrid coefficient, and vertical-coordinate fields match exactly. Field dimensions and units also match across arms, including total pressure (`P+PB`), geopotential (`PH+PHB`), and face-staggered `U`, `V`, and `W`.

## Scope and method

For each field, the analyzer computes cellwise `deltaX(t) = COUPLED(t) - OFF(t)` at both endpoints and `delta_evolution = deltaX(T60) - deltaX(T0)`. It reports signed sum, L1 sum, maximum absolute cell value, maximum absolute vertical-column value, and column L1 for three fixed scopes: the whole native grid; the interior after excluding one horizontal boundary ring; and the initial native analysis water support. The last scope is the horizontal union of columns where any native water mixing ratio differs exactly between arms at T0, then held fixed at T60. It contains 27 of 65,988 horizontal columns (0.041%) in the zero-based inclusive box `j=14..19, i=132..137`. Its packed mask SHA-256 is recorded in the JSON. This is a descriptive, outcome-selected native support and is not an independent observation validation mask. The authoritative 162-cell pressure-analysis support has not been mapped to this native grid by a source-bound operator; it is not replaced by these 27 columns.

Every scope reports its selected cell count. If a fixed support is empty, it is marked `EMPTY_SCOPE`, sums are zero, and maxima are JSON `null`; the analyzer does not manufacture a zero maximum or fail the paired run.

For each water species, number moment, and `QIB`, the analyzer decomposes the T60 cross-arm endpoint difference and each arm's T0-to-T60 extensive change cellwise as:

```text
m_C*r_C - m_O*r_O = mean(m)*[r_C-r_O] + mean(r)*[m_C-m_O]
```

Here `m` is native hybrid dry layer mass from the PR87 pinned-constants method, and `r` is the corresponding mixing ratio, number concentration, or rime-volume variable. It also decomposes the difference between the two arms' temporal extensive changes by subtracting the OFF temporal terms from the COUPLED temporal terms. The JSON reports each term's signed/L1/max/column summaries and the maximum absolute floating-point identity residual. This is an algebraic endpoint decomposition, not a timestep or domain budget closure.

The `U` and `V` diagnostics include native face arrays and adjacent-face finite differences divided by `DX` and `DY`. These are computational-grid derivatives without map-factor correction; no physical divergence, full momentum equation, or continuity closure is evaluated. Reflectivity and cloud-fraction fields are not treated as observations, and no observation fit is computed.

## Selected endpoint results

These are COUPLED-minus-OFF mixing-ratio deltas at T60 on the fixed whole native grid; the full signed/L1/max/column summaries and interior scope are in the JSON.

| Field | Signed sum | L1 sum | Max absolute cell |
| --- | ---: | ---: | ---: |
| `QVAPOR` (kg kg-1) | 0.02015 | 0.03253 | 6.074e-4 |
| `QCLOUD` (kg kg-1) | 4.727e-4 | 0.02002 | 1.825e-3 |
| `QICE` (kg kg-1) | 0.004791 | 0.05277 | 2.105e-3 |
| `QRAIN` (kg kg-1) | -0.01888 | 0.02148 | 3.447e-4 |
| `QSNOW` (kg kg-1) | -0.01372 | 0.06203 | 2.140e-3 |
| `QGRAUP` (kg kg-1) | 0.002278 | 0.004440 | 1.318e-3 |

The carrier decomposition is sensitive to changes in both tracer value and dry carrier. At T60, `QCLOUD` has an extensive difference signed sum of `-1.493e6 kg`, L1 `2.195e8 kg`, and maximum absolute cell `2.247e7 kg` over the whole grid. Within the initial native analysis water support, its signed difference is `3.026e7 kg` and L1 is `1.516e8 kg`. In that fixed support, OFF's T0-to-T60 extensive change is `-1.836e9 kg`, COUPLED's is `-1.541e9 kg`, and their evolution difference is `2.949e8 kg`. The maximum T60 identity residual there is `3.04e-9 kg` from floating-point arithmetic. These summaries describe the T0-selected support and should not be read as an independent observation result, cloud-process source, or flux.

## Validation and limits

The analyzer checks receipt file hashes and run windows, exact timestamp agreement, cross-arm mass-grid geometry, available static geometry fields, and compared variable descriptors before reporting statistics. Manufactured tests verify the carrier decomposition independently and exercise geometry and receipt-hash rejection.

The outputs describe native history differences only. They do not establish observation agreement, reflectivity fit, process attribution, flux closure, shock behavior, or full-model conservation. The history extraction contains only T0/T60 snapshots, so no intervening timestep tendency is evaluated.

The [source-gap audit](evidence/pr89_process_contract_20261019/review/pr89_mass_wind_source_gap_20261019.md) records why actual endpoint face arrays do not yet establish a source-bound dry-mass flux closure: the exact helper implementations are not bound to the executable, and intermediate RK/substep and boundary tendencies are absent. No unbound sibling source formula is substituted.
