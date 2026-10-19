# Independent review: PR89 paired history diagnostics

**Result: no blocking findings.** The paired-history output is internally reproducible from the supplied run receipts and current V50 history files. The analyzer, tests, evidence JSON, and documentation agree on the comparison scope and its limits.

## Evidence checks

- Re-ran `tools/pr89_paired_history.py` against the actual OFF and COUPLED V50 histories and receipts plus the pinned constants receipt. The generated JSON compared equal to `docs/evidence/pr89_process_contract_20261019/history/paired_history.json`.
- Actual receipt hashes match the JSON: OFF `31a69eb3ae41bb25cc0270bccdfa38486b90e6fa3c1079c6fdb500ac65551d70`; COUPLED `4b933ce7583568579b6a00b3c2f9dbdb248927ab23039a43bd0aa5867c82da42`.
- Each receipt is `COMPLETE`, has return code 0, and binds its current history file. Actual history hashes match: OFF `cebc524bc907d1c0e32c11dfa4b302893f25bf4e5574c412548c7eb4a03b6129`; COUPLED `64e7ee9c67d826193caae46b1dddd1e7f8410690fea74deb15febefb9ec9eb67`.
- The constants receipt hash also matches (`7b6cc54597b1d67c35ec112decab192cae3d1d5035ec03f5fb418a081df38670`) and supplies the pinned promoted REAL32 gravity value `9.8100004196167 m s-2`.
- Both histories resolve to receipt-derived T0 `2026-08-16_13:00:00` and T60 `2026-08-16_13:01:00`; the analyzer requires exactly those two timestamps, complete matching windows, and equal cross-arm geometry.
- The 22 available static coordinate, map, and vertical/hybrid fields compare exactly across both arms. Dimensions and `DX=DY=5000 m` match. The JSON stores shapes and exact-match flags rather than separate per-field geometry digests; whole-file hashes are receipt-bound.
- `python -m pytest -q tests/test_pr89_paired_history.py`: **4 passed**.

## Method review

- The OFF/COUPLED comparisons are cellwise at each endpoint, with evolution computed as the T60 cross-arm difference minus the T0 cross-arm difference. The same native grid scopes are held fixed across time.
- The initial support contains 27 of 65,988 columns (zero-based `j=14..19`, `i=132..137`), selected where any native water mixing ratio differs exactly at T0. The code and report correctly call it an outcome-selected descriptive subset, not an independent observation mask. The report also says no authoritative analysis footprint was found.
- Carrier changes are decomposed per cell using the exact symmetric identity `m_C*r_C - m_O*r_O = mean(m)*delta(r) + mean(r)*delta(m)`. The output separately reports endpoint cross-arm differences, temporal terms per arm, and the difference between arms' temporal changes. Identity residuals are retained.
- Empty fixed support is handled explicitly: zero selected cells, `EMPTY_SCOPE`, zero sums, and null maxima/residual maxima. The manufactured test covers this case.
- U and V remain on their native staggered arrays. Their adjacent-face differences divided by DX/DY are computational-grid derivatives; code and report explicitly disclaim map-factor correction, physical divergence, momentum/continuity closure, and observation fit.

## Remaining interpretation limits

The reported vertical-column statistics are unweighted sums over the vertical array dimension, not layer-mass or physical-column integrals. The output labels them as column summaries and does not use them for budget closure. Geometry is proven by exact comparisons, though individual field digests are not serialized. Neither point invalidates the documented descriptive comparison.
