# Reproducing the bounded C14 response summary

`reproduce_summary.py` first requires exact SHA-256, arm label, COMPLETE status, return code, 12-step completion, and executed-executable identity for the two closed C14 receipts. These checks occur before the large stage-trace area join. The driver then calls the existing `tools/pr90_cold_column_summary.py::area_weighted_totals`, `tools/pr87_native_history.py` history/dry-mass readers, and `tools/pr89_paired_history.py::_verify_static_geometry`. It writes `summary.json`, `cold_area_weighted.json`, and a source/input/output pin manifest to a new output directory. It refuses to overwrite an existing destination.

Run from the Cloud-BAL repository root, choosing a fresh scratch output path:

```sh
python3 docs/evidence/pr91_science_sources_20261020/c14_current_response/reproduce_summary.py \
  --repo-root "$PWD" \
  --off-run-root /var/tmp/pr91_OFF_240s_c14_20261020 \
  --coupled-run-root /var/tmp/pr91_COUPLED_240s_c14_20261020 \
  --output-dir /var/tmp/pr91_c14_response_reproduction_fresh
```

The run roots must contain the closed `receipt.json` and its `run/` directory. The existing area join streams each large stage trace to check same-run source, history, build, executable, execution layout, and full completed-column coverage. Expected run receipt SHA-256 values are `f6a2e40d65c76e4e9abd0dfb1fc26f0c5da3abe4327a5d23829e4a66f34b540a` (OFF) and `9bd0a867987896dc9c6551bbc964e8fd1d2d759cb865827af81346b782a40e48` (COUPLED). The output manifest also records runtime paths and all reused source hashes.

The reused source pins at archive time are: `tools/pr90_cold_column_summary.py` `61b964809856661c89e0d9e1b390469de730e256e653e7f18e0849ee88f9b819`, `tools/pr87_native_history.py` `d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71`, and `tools/pr89_paired_history.py` `8619fa864cbea76bf00100f8ce17bdea04d9a328783f7c93bfb91bdf64be4d9f`.

The archived original machine summary is [summary.json](summary.json), SHA-256 `8b5803001908e89a3d9a5432dc495b2604bdb395a017cdc068669856a7d66efc`; the standalone driver SHA-256 is `66936241de88e5bb6d22d94f2ad41aca52db5922047aa7aca97a9ebcd6df225c`. Reproduction is intended in a fresh scratch directory; keep the generated output separate from this archived bundle.

The final guarded-driver reproduction completed from a byte-identical scratch copy with return code 0. The archived [guarded check](guarded_reproduction_check.json) (SHA-256 `869d6c37b8991d549a433fb0f5b2fa25ad820f01c8485188130aabeef5ae5aba`) records semantic identity with the archived summary (the JSON key ordering differs), byte-identical cold-area output (`f64848511dbb18795afe646643a3770ccb49f4056b1c43d6a9c4f8cccd87a078`), and the guarded driver SHA above. The [reproduction manifest](guarded_reproduction_manifest.json) is SHA-256 `0c1a9d2812a97a57eab1abe1dbfeab21dfdc7b5ffe08c7527ce71cf2021e9b84`. This final guarded run supersedes an earlier pre-guard reproduction attempt.

The driver reproduces the measured ledger and history diagnostics only. It does not compute a water budget, precipitation response, observational score, or physical approval.
