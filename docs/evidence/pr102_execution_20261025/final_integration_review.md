# PR102 final integration review (pre-640)

Read-only source review recorded 2026-10-25. The 640-second `STRUCTURED` run
was still active when this review was requested; no live run output was read.
This note does not approve that run or make any physical or forecast claim.

## Source pins

| Artifact | SHA-256 |
|---|---|
| `tools/pr86_time_response.py` | `35adaa773773c046311d731ea1426821befb225a444092405098b4ee4e8baa43` |
| `tools/pr102_execution_preflight.py` | `e80f5fc69e4b8cc7ee4dbe0281265faa7f1a97c9856c1be52e02a42ab9900277` |
| `tools/pr102_capture20_preflight.py` | `8f8f55e8733ab7c1fc03ff867cdb1f28570360b5b9a6cbd2b9dee6d82967a049` |
| `tools/pr102_response.py` | `9e30de564c85b5cfdbb8c9141d3f86f68d2958582892c62ad7578c77affe866e` |
| `docs/evidence/pr102_execution_20261025/first_native/first_native_response.json` | `9fc8117c5dd46d625ec77d318d5ba8f50d58abb900d457417929bf1708fa6a98` |

The first-native JSON records equal before/after source pins for its analysis
dependencies, including the runner, execution preflight, candidate builder,
response analyzer, native readers, support helper, and gravity receipt.

## Review result

No material integration blocker was found in the reviewed source. The runner
keeps `PROJECTED` bound to the PR99 native-projection proposal and 640-second
schedule. PR102 uses distinct `STRUCTURED`, `STRUCTURED_CAPTURE`, and
`STRUCTURED_BASELINE20` arms. The 640-second structured arm requires the
candidate-bound PR102 execution preflight; the one-step capture arm requires
the archived consumer receipt; and the baseline arm requires the exact base
C2 executable. The PR102 template checks bind HYDRO, COUPLED, original P,
boundary, proposal parent, candidate input, namelist, and C2 executable to the
declared closed controls.

The staging path copies the frozen runtime into a fresh run directory, then
overlays only the selected candidate input and executable and writes the
duration-adjusted namelist there. Staged inputs are checked before launch;
closed-run receipts compare staged and original runtime inputs after execution.
This protects the frozen runtime inputs. A failure during preparation/staging
can leave a partial output directory, but does not write to the source runtime.

The execution preflight pins the closed controls and their receipts, binds
proposal H/C/P and boundary identities to those controls, checks the candidate
is U/V-only against original P, and requires H/P/N source captures with one
shared diagnostic build and passing noninterference receipts. The 20-second
preflight is explicitly `launch_authorized: false`, refuses an existing
future-run root or output receipt, and records the exact arm, input, boundary,
namelist, environment, consumer, and build dependencies.

The frozen first-native response uses H = HYDRO, P = original projected, and
N = candidate; paired differences are candidate minus reference. It labels raw
RU/RV as native staggered source-coordinate operator diagnostics and keeps
those values separate from MUDF and dry-column mass rates. Its dry-column rate
is reported in kg/s per native support column, calculated from each captured
MU update, captured timestep, shared area/C1H/DNW, and pinned gravity. The
reported N L2 rate is 6.69% above P and 8.94% below nonzero H. This is not
presented as an improvement, continuity closure, acceleration, or forecast
approval. The response remains `DESCRIPTIVE_ONLY`, observation skill
`NOT_EVALUATED`, and physical approval `FAIL_OPEN`.

The PR102 response reader requires a closed 32-step structured receipt and
validates receipt-bound history, trace, and first-step source artifacts. Its
first-native evidence is explicitly one completed 20-second timestep, with
RK placement inferred from pinned source call order because the raw snapshots
do not encode an RK ordinal.

## Scope limit

This review covers source integration and the already closed one-step
H/P/N evidence only. It does not assess the in-progress 640-second outputs,
response acceptance, observation skill, or physical approval. Graphify
navigation was not useful for these newly added files because the maintained
snapshot did not contain their current relationships; source and receipt
hashes above are authoritative for this review.
