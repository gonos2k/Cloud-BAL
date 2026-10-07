# Portable Python contract CI

The maintained entry point is `tests/run_python_contract_tests.sh`. The
current checkout has no tracked `.github/workflows` file, so this document
does not establish an active hosted CI check or a hosted-runner result.
`PYTHON_BIN` selects the local interpreter; the script's test list is the
authoritative registration. It also runs the shell failure-injection test for
the preflight log capture.

The registered tests use fixtures and temporary directories. Examples include
transaction rollback, native geometry algebra, trace parsing, and PR65
numerical replay. The native geometry tests are synthetic algebra and parser
checks, not native model executions.

The local setup example below installs selected NumPy/netCDF4 binary wheels.
The tests create their
own temporary inputs and do not read site operational trees, credentials,
deployment targets, or self-hosted-runner state.

The setup example pins dependency versions, but not wheel hashes. It is a
portable regression check, not a release receipt, reproducibility
attestation, or supply-chain verification.

This is a bounded contract test runner, not a full scientific or operational
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

Run the registered tests locally from the repository root with an executable scratch
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
