# PR73 actual KDM6 property-stage matrix

The actual frozen PR72 KDM6 source was built and run in the pinned Intel O0 and O2 profiles. The test calls the real `kdm6init` and `kdm6` entry point. A source-hash-pinned test transform poisons the actual cloud slope, `ProgB_param`, `slope_kdm6`, and velocity-rate outputs, captures their resulting properties, then returns before substep counting or physical rate application. The production source has no behavior change because the capture, poison, and return are all inside `TEST_PR73_PROPERTY_MATRIX` preprocessing guards.

The matrix varies exact-zero versus active paired state for rain Q/N, cloud Q/N, ice Q/N, and graupel Q/B. It covers all 16 combinations. Each mask first produces a reference property record. The test then calls the all-active mask, poisons the public output/history arrays, transitions to the target mask in the same executable, and requires exact equality with that target's reference record. The actual properties checked include inline cloud slope moments, rain and ice slopes and number velocities, and `ProgB_param`/graupel status, density, slope, and velocity outputs. The active graupel fixture is QG/BG = 400 kg m-3.

The test also checks that absent rain has zero number velocity, absent ice has zero mass and number velocity, active ice preserves the actual source relation V_m = 4 V_N, absent graupel has zero graupel velocity, and absent graupel properties do not retain poisoned values. These checks establish property-stage independence for the tested inputs. They do not establish that a complete KDM6 process call succeeds or conserves water and energy.

The source completes the first `n0r/n0c/n0i` reconstruction only after its initial rate application and microphysical work. This test returns before that work so that absence remains paired at the property stage; it does not claim n0 reconstruction coverage. The capture reads the first active i/k cell from a small wrapper domain, with one j call. Graupel density coverage here is limited to 400 kg m-3.

The separate full-module probe returned for masks 0–4, then stopped at mask 5 with `ProgB unsupported PSD state rejected`; masks 6–15 and O2 were not run. Its preserved [receipt and per-mask logs](evidence/pr73_species_fullmodule_probe_20261008/receipt.json) bind that failure. This property-stage test does not replace or reinterpret that failure.

Run from a clean checkout with:

```bash
tests/run_pr73_property_matrix.sh
```

The runner creates fresh `/var/tmp` O0/O2 build directories, verifies the frozen source SHA-256 `1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819`, and refuses to overwrite its durable evidence directory. [The final receipt](evidence/pr73_property_matrix_20261008/receipt.json) binds the source transform, compiler profile, test and runner hashes, objects, executables, logs, and all 32 reference/re-entry records. The exact source transform is [captured here](evidence/pr73_property_matrix_20261008/source_transform.patch).
