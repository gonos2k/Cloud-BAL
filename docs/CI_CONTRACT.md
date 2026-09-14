# Portable Python contract CI

The `Portable Python contract` workflow runs on pull requests and on pushes to
`main`. It uses the hosted `ubuntu-24.04` runner, Python `3.11.11`, and no
repository secrets. Checkout and setup actions are pinned to immutable commits;
the commit comments record the verified upstream tags.

The workflow runs `tests/run_python_contract_tests.sh`, which executes these
existing fixture and temporary-directory tests:

- `tests/test_compare_baseline.py`
- `tests/test_intel_integration_audit.py`
- `tests/test_native_hybrid_geometry.py` (synthetic dry-pressure algebra only; not a native model run)
- `tests/test_operational_comparison_prep.py`
- `tests/test_operational_shadow_compare.py`
- `tests/test_output_transaction.py`
- `tests/test_qbal_real_input_manifest.py`
- `tests/test_real_manufactured_balance_generation.py`
- `tests/test_shadow_validator.py`

The NumPy/netCDF4 tests use pinned binary wheels only. The tests create their
own temporary inputs and do not read site operational trees, credentials,
deployment targets, or self-hosted-runner state.

The dependency versions are pinned, but wheel hashes are not locked in this
lane. It is a portable regression check, not a release receipt, reproducibility
attestation, or supply-chain verification.

This is a bounded Python contract lane, not a full scientific or operational
validation. It does not test:

- Fortran compilation, linking, runtime behavior, or any `tests/*.f90`/`tests/*.f`
  test invoked by `tests/run_unit_tests.sh`.
- Intel `ifx` toolchain integration or native build provenance. The integration
  audit test above is fixture-only logic; it does not execute `ifx`.
- The optional native C/`nm`/`objdump` branch in
  `tests/test_legacy_deriv_safety.py`.
- The host-sandbox and `/usr/bin/bwrap` assumptions in
  `tests/test_original_upstream_replay.py`.
- Real operational inputs, production deployment, credentials, or scientific
  correctness claims beyond the checked Python contracts.

Run the same lane locally from the repository root with an executable scratch
filesystem. This workspace mounts `/tmp` with `noexec`, so do not install binary
extension wheels there:

```bash
mkdir -p scratch
venv_dir=$(mktemp -d "$PWD/scratch/python-contract.XXXXXX")
trap 'rm -rf "$venv_dir"' EXIT
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --only-binary=:all: \
  'numpy==1.26.4' 'netCDF4==1.7.4' 'cftime==1.6.5'
PYTHON_BIN="$venv_dir/bin/python" tests/run_python_contract_tests.sh
```

## Staged required-check plan

This table is a development plan, not a claim that remote checks or branch
rules have been installed. Each check must bind its actual tested source,
inputs, configuration and outputs; a green result from a different identity
does not satisfy the gate.

| Checkpoint | Check to establish | Evidence and authority boundary |
|---|---|---|
| CP00 | Portable Python contract | Fixture-only PR check; local execution is not a hosted-runner receipt. |
| CP02 | Pinned ifx reader/unit, upstream and OFF native round-trip | Separate compiler/dependency and native-input receipts; expected BLOCKED dry-runs do not prove producer execution. |
| CP03 | Compatible balance/reference | Actual geometry, target response and independent reference; manufactured results retain test-only authority. |
| CP04–CP05 | Thermodynamic and observation contracts | Species/water/enthalpy and frame/error/authority positive and negative tests; no science promotion. |
| CP06–CP07 | Full native SHADOW and regression | Same-input full-state handoff, independent verifier, complete expected-case manifest and publisher failures. |
| CP08 | Independent event/science gate | Held-out 0–6 h forecasts and high-frequency wave safety under predeclared thresholds; separate from routine PR CI. |
| CP09 | Operational readiness and independent acceptance | SLO/rollback receipts and all mandatory gates; no automatic ACTIVE authorization. |

QA/CI owns check implementation. An independent reviewer evaluates the evidence;
the repository administrator must approve and apply required-check/ruleset
settings. Those actual people and permissions remain unassigned. Do not run
untrusted PR code on a credentialed or operational self-hosted runner. A future
ifx runner needs an explicitly approved isolated execution boundary before it
can be connected to PR automation.
