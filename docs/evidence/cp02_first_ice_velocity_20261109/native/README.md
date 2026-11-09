# First ice sedimentation velocity evidence

The CONTROL source is the previously published conservation candidate, SHA-256 `ad255ae8b505af6b4ceebd177a54948d8bfff7fcd2c9f6d45c90122be0b57786`. The NEW source (SHA-256 `c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2`) applies `patches/kdm6_first_ice_velocity.patch` to CONTROL. After the last warm substep, `slope_kdm6` has refreshed ice mass and number velocities in m/s. The patch divides each by the donor layer depth exactly once before entering the ice loop. The existing division after each ice substep remains. The exchange, REAL64 transfer arithmetic, REAL32 state, coefficients, and zero-process branches are unchanged. These names correspond to CONTROL and ICE_FIXED respectively in forecast builds.

Reproduce with the pinned Intel compiler in a fresh external directory, with TMPDIR there:

```sh
bash docs/evidence/cp02_first_ice_velocity_20261109/native/run_intel.sh /var/tmp/new-fresh-ice-test
python -m pytest -q tests/test_cp02_first_ice_velocity.py
```

The script checks patch replay identity and exact production work-array declarations. It runs the seven previously defined native conservation cases afresh at O0 and O2, using a copied driver with `work1` and `workn` corrected to REAL64; all other model fields retain their production kinds. The literal 3.75 m/s CFL input is calculated in REAL64 before division by REAL32 depth. This does not retroactively alter the previous evidence or its results. The greatest relative conservation residual in this run was 3.214e-8.

The coupled column uses the verbatim production `slope_kdm6` and module declarations extracted from NEW, followed by the exact new boundary normalization and actual shared ice-exchange statements; it recomputes slope after each substep and extracts the existing end normalization. It initializes the relevant ice and default-slope values from the production `kdm6init` equations, with inactive warm species and zeroed unused warm velocity coefficients. This is an isolated column, not a full invocation of `kdm62D` or model initialization. For dz=100 m and dt=20 s the actual slope yields mass velocity approximately 0.5 m/s and number velocity approximately 0.125 m/s: CONTROL's first transfer caps at 100% for each, whereas NEW transfers 10% and 2.5%, respectively. The actual production coefficient ratio makes the number result different from a hypothetical 0.2 m/s example. Both conserve the column plus bottom outflow. One and four substeps are exercised; the test saves the raw output of every slope call and independently checks each normalized speed against raw speed divided by depth, detecting repeated division.

The complete frozen module compiled against the 664 model modules; linking the complete model library into this small executable required additional WRF dependencies, so the final test extracts the actual production routine as described above. Compiler and case outputs are summarized in `intel_receipt.txt`; intermediate attempts and their build logs were kept under `/var/tmp/cp02_first_ice_velocity_20261109_run{1,2,3,4}`. This evidence does not establish full-forecast or scientific validation.
