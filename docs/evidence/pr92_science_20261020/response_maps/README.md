# C14 same-location response, 2026-10-20

These are diagnostics of the preserved C14 OFF/COUPLED 240-second runs, not a new model execution. Both history files are hash-bound to their successful twelve-step receipts and the pinned C14 executable. The tool checks matching native geometry and actual elapsed times 0/60/120/180/240 s. See `fixed_location_response.json` for exact identities and hashes.

`tools/pr92_response_maps.py` retains the native mass levels for P+PB and native interfaces for PH+PHB and W. Each map shows the **signed COUPLED-minus-OFF value at the largest absolute difference in that column**. The selected vertical level can change by column and time. Bottom panels use one fixed geographic view around the 27-column T0 water-difference support; they do not define an observation footprint.

The JSON also follows the union of each time’s whole-grid maximum locations at **fixed (i,j,k)** across every saved time. This avoids treating different maxima as one point’s oscillation. A fixed model level is neither a fixed altitude nor a material parcel.

For example, pressure at native (i,j,k)=(136,17,11) is −28.1875, −360.6328125, −84.6171875, −14.0078125, and −2.53125 Pa. Pressure at (136,18,1) is −32.3046875, +83.609375, −21.5859375, −25.25, and −74.9609375 Pa. Thus the 60-second interior pressure peak decays at its own location, while a different location controls the 240-second maximum. Neither statement establishes reduced initial shock.

W maxima at 60 and 120 seconds occur at the highest stored interface; their absolute differences are 1.7285291 and 2.2188903 m/s. Excluding the lowest/highest interfaces gives maxima 1.5579816 and 2.0035478 m/s. At (136,17,14), an interior fixed location, W differences are 0, +0.276452, +1.072122, +1.405045, +1.463653 m/s. The interface partition is descriptive and does not establish a boundary-condition error: native geometric W and the model’s transformed-coordinate boundary velocity are different quantities.

The 27 columns are outcome-selected descriptive support, not the original pressure-analysis/observation support. These paired state differences provide no pressure-force, dry-mass continuity, energy or water closure, independent observation skill, or pure model-change attribution. Scientific approval remains OPEN.
