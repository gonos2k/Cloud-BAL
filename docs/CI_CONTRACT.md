# Portable Python contract CI

The maintained entry point is `tests/run_python_contract_tests.sh`. It discovers
every `tests/test_*.py` file and checks tier registration with
`tests/check_test_tiers.py`; newly added tests join the portable tier by
default and must collect under pytest. The small
`tests/python_script_test_allowlist.json` lists the legacy self-running checks
that use script entry points instead of pytest collection. A newly discovered
module with no collected test cases fails visibly until it uses pytest or is
explicitly added to that small script allowlist. The
`tests/test_tier_exceptions.json` file assigns tests that
need Linux facilities, native toolchain/evidence, or real operational data to
their own tiers. The checker prints every selected test and every skipped test
with the tier and a short reason. `PYTHON_BIN` selects the interpreter and
`TEST_TIER` selects `portable`, `linux`, `native`, or `realdata` (default:
`portable`). The portable run also executes the shell preflight failure and
transaction-recovery tests.
Some native checks also need command arguments or environment paths; those
requirements are recorded with their tier assignment. The generic tier runner
does not invent missing evidence paths.

The registry assigns each Python test module to its strongest required
inputs. Local PR83 RK builder checks, PR87 ProgB v36 fixture checks, PR91
source-store trace parsing, PR92 source parsing/report joins and
representability/shell-input checks, PR94 synthetic policy identity, PR98
boundary contracts, PR99 fixture validation, PR101 synthetic replay and
source-rejection checks, and PR103 plan/GO checks remain portable. Their
companion tests that read external source trees, frozen runners, compiler
profiles, native receipts, archived executables, or operational run receipts
are registered as `native` or `realdata` with the dependency recorded per
module. The PR87 cloud/PBL consumer builds and PR92 generated Fortran replays
use the pinned Intel profile in `native`. The PR94 HYDRO candidate, PR97 C4
capture set, and PR101 closed C2 controls are `realdata`. A same-host pass
cannot establish availability of those external dependencies.

PR109 qualification additionally runs the complete portable entry point under
Linux Landlock with external research-file reads and Intel compiler execution
denied. A new checkout on a host with those resources is not, by itself, a
portability proof. See `PR109_MEMORY_AND_PORTABILITY_20261027.md` for the
qualification scope and exact evidence.

The current checkout has no tracked `.github/workflows` file, so this document
does not establish an active hosted CI check or a hosted-runner result.

The portable tests use checked-in fixtures and temporary directories. Examples
include transaction rollback, geometry algebra, trace parsing, and numerical
replay. Geometry and parser contracts are not native model executions.

PR83 has two separate checks. The portable policy-contract fixture checks the
declared policy identity, valid time, density equation, evidence inventory, and
the frozen policy-file digest without opening external source artifacts. The
`realdata` source integration test invokes the production validator, which
continues to require exact hashes for the external source, executable,
archive, and receipts. Portable tests that mock these source bindings do not
replace that integration check. Missing fixture or evidence files fail the
selected integration test rather than counting as a pass.

The local setup example below installs selected NumPy/netCDF4 binary wheels.
The tests create their
own temporary inputs and do not read site operational trees, credentials,
deployment targets, or self-hosted-runner state.

The setup example pins dependency versions, but not wheel hashes. It is a
portable regression check, not a release receipt, reproducibility
attestation, or supply-chain verification.

The portable tier is a bounded contract check, not full scientific or
operational validation. It does not test:

- Fortran compilation, linking, runtime behavior, or any `tests/*.f90`/`tests/*.f`
  test invoked by `tests/run_unit_tests.sh`.
- Intel `ifx` toolchain integration or native build provenance; these are
  classified under `native`.
- The host-sandbox and `/usr/bin/bwrap` assumptions in
  `tests/test_original_upstream_replay.py`.
- Real operational inputs, production deployment, credentials, or scientific
  correctness claims beyond the checked Python contracts.

The optional C/`nm`/`objdump` branch in `test_legacy_deriv_safety.py` runs
when those tools exist and reports a skip otherwise; its availability is not
guaranteed by the Python environment.

Run the portable tier locally from the repository root with an executable
scratch filesystem. Keep the virtual environment in the checkout scratch area
and use a separate writable temporary directory outside the checkout; the
production replay guard rejects temporary paths inside the repository.

```bash
mkdir -p scratch
venv_dir=$(mktemp -d "$PWD/scratch/python-contract.XXXXXX")
tmp_dir=$(mktemp -d /var/tmp/python-contract-tmp.XXXXXX)
trap 'rm -rf "$venv_dir" "$tmp_dir"' EXIT
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --only-binary=:all: \
  'numpy==1.26.4' 'netCDF4==1.7.4' 'cftime==1.6.5' \
  'pytest==8.1.1' 'scipy==1.15.3' 'matplotlib==3.10.1'
TMPDIR="$tmp_dir" PYTHON_BIN="$venv_dir/bin/python" tests/run_python_contract_tests.sh
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
