# PR99 native projection 20-second post-run review

Review date: 2026-10-22  
Review type: independent read-only receipt, input, capture, and comparison audit.  
Result: **PASS for provenance and reported one-step response reproduction. Physical approval remains `FAIL_OPEN`; observation skill remains `NOT_EVALUATED`.**

## Exact artifact pins

| Artifact | SHA-256 |
|---|---|
| Response analyzer `tools/pr99_projection_response.py` | `6c2f7bcdfea5e221a9dd3ee24e90336429ef171433b42a19eab92b528c146f60` |
| Runner `tools/pr86_time_response.py` | `6267101c3bab90a9b73124a46cee48b0fbced04b3910657240e444789f732788` |
| Closed run receipt | `f734125bb30555c30cf6815ab8b61a58d5cb173605c13f4f6ff7ce9d326a90a1` |
| Launch preflight | `fb5ae032186bea24a5c8dffe852650fe6573ade2b6784a09f9b0858add1254f9` |
| Response output | `62fde5687c176b0ae1af2c2debbc6003c6a8f778786ae6b640e40d32fbd94a4d` |
| Proposal receipt | `a6fdd4907228b6bcd95d2eba3e61539adcedf69c0154c23a9e1a2edeb6c6b5d0` |
| Proposal candidate input | `10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3` |
| Proposal generator | `c14bdcf018c4e246472a2989867efa582aaede090cdb8583afafb289f40e0cbf` |
| COUPLED boundary | `885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7` |
| Executed native overlay | `e919518165d52e26004858fa40293b7df806a9ba2a17af6ab320858f713768f1` |
| Original C1 native-effect source report | `84b6f4e20891cf8d66e705e7d4aa15eafa2bedff016db25b75fdbc2722350f43` |
| Original C1 dry-column-rate report | `478309562e2a0684f477b65d95762d4307d48484f6f8ddaab0a507b7df409ff7` |

The copied receipt, preflight, and response are byte-identical to the corresponding closed files at the run root and external v4 response path. The receipt records `COUPLED`, `COMPLETE`, return code 0, one expected 20-second model timestamp, completed step 1, and unchanged input/build with no changed inputs, processing errors, fatal lines, or duplicate post-step snapshots. Its launch-runner source hash equals the current pinned runner hash above. The source receipt, proposal candidate, and boundary hashes recompute to their receipt/preflight pins.

The response analyzer was rerun read-only on the closed run root. Its result is canonically identical to the preserved `response.json`, including the receipt hash, proposal binding, frozen capture binding, all 208-variable input audit, 57 captured snapshots, and reported metrics. Its checks verify the proposal binding against the frozen COUPLED parent and boundary, recheck candidate build and source receipt identity, and hash every proposal snapshot. Static native geometry snapshots match the frozen COUPLED capture.

The initial-input comparison finds 208 stored variables, with only U and V values different. Their dimensions, dtypes, units, staggering, attributes, and global metadata match; 206 other variables are bitwise identical. U differs at 7,097 elements and V at 7,096 elements. The comparison references the candidate and its original COUPLED parent; all 57 native output snapshots are bound to the same captured executable/build and boundary as the original OFF/HYDRO/COUPLED captures.

Frozen-capture comparison identity ignores only relocated checkout path fields while retaining receipt, manifest, inventory, executable, and source hashes. Both original C1 comparison reports bind the same frozen native capture identity as the archived capture manifests.

## Reported comparisons

All three columns below use the same 16-column support footprint and captured native diagnostics. The dry-column mass rate is differentiated from the captured MU update over its recorded acoustic-call interval (about 6.667 seconds), using fixed C1H, DNW, native map area, and pinned gravity. Its units are kg/s. It is not a global mass-loss result or a separate face-flux closure.

| Metric | HYDRO | Original C1 COUPLED | PR99 native proposal |
|---|---:|---:|---:|
| Observed dry-column mass-rate L2 (kg/s) | 17,899,337.37 | 383,305,796.43 | 15,276,840.85 |
| Assembled RU L2 (native source-coordinate units) | 24,361.97 | 41,212.46 | 37,999.03 |
| Assembled RV L2 (native source-coordinate units) | 23,908.72 | 34,050.81 | 33,199.72 |

The proposal reduces the dry-column rate L2 by 96.0% against original C1 COUPLED, but remains 14.6% below HYDRO. RU and RV decrease by 7.8% and 2.5% against original C1 COUPLED; their proposal values remain 1.56 and 1.39 times HYDRO. RU/RV norms are equal-cell source-coordinate diagnostics, not acceleration, energy, or complete momentum closure.

The generator provenance binds the extra U/V equal-face norm to the original C1 candidate and proposal: 105.6076434 m/s to 101.1432095 m/s, retaining 95.77%. This is not an energy-weighted norm.

## Limits and findings

No artifact-binding or arithmetic-reproduction blocker was found. This is one 20-second diagnostic integration and one captured initial acoustic response on the fixed support. It does not establish long-run stability, complete momentum balance, pressure correction quality, cloud-signal preservation, observation skill, or global dry-mass closure. The candidate remains an explicitly labeled research proposal, not the default baseline; physical approval remains **`FAIL_OPEN`**.
