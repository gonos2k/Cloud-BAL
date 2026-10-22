# PR99 native projection and 20-second runner review

Review date: 2026-10-22  
Scope: read-only source review of the native U/V projection proposal, PR86 runner binding, and PR99 response reader. This review is limited to provenance and the single diagnostic launch gate; it is not physical or operational approval.

## Bound artifacts

| Artifact | SHA-256 |
|---|---|
| `tools/pr99_native_projection.py` | `c14bdcf018c4e246472a2989867efa582aaede090cdb8583afafb289f40e0cbf` |
| `tools/pr86_time_response.py` | `6267101c3bab90a9b73124a46cee48b0fbced04b3910657240e444789f732788` |
| `tools/pr99_projection_response.py` | `89c12d6bad49380607379a631c43dfda5ca252afc77651a10611be573251423e` |
| `tests/test_pr99_native_projection.py` | `ce5b4dde1cc022464c876ea008ae73f30b175192a9301fa33185b5f6901f922b` |
| `tests/test_pr86_time_response.py` | `f49fbda43675fd499559ad50be088fbae68fc0e582e7671dcfd82acd26e9eb51` |
| proposal receipt `/var/tmp/pr99_native_projection_v4_20261022/wrfinput_d01.proposal.json` (preflight-bound) | `a6fdd4907228b6bcd95d2eba3e61539adcedf69c0154c23a9e1a2edeb6c6b5d0` |
| proposal candidate `/var/tmp/pr99_native_projection_v4_20261022/wrfinput_d01` | `10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3` |
| preflight `/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr99_native_uv20_preflight_20261022/preflight/preflight.json` | `2a74e97c75585e5b91d62a9dc2db06a07fa4457228f51be1d2e07601214771e2` |
| frozen COUPLED boundary | `885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7` |
| PR85 COUPLED source receipt | `8dc7aa4c8b1cdffc72ab29da5a8db255ee96a271bb452fb5bd73a1e62f32d675` |
| PR87 overlay executable | `e919518165d52e26004858fa40293b7df806a9ba2a17af6ab320858f713768f1` |
| PR87 build receipt | `34a3b92a1d0288e172d34423a1f254ce371213b757f254c13c1c4f6727b7beb7` |

The preflight sets arm `COUPLED`, duration 20 seconds, expected timesteps 1, and disk guard `PASS`. It binds the candidate, parent, boundary, generator, composition, C1 source receipt, and executable. The parent hash is the frozen COUPLED `wrfinput_d01`; the boundary hash matches the frozen COUPLED boundary.

## Review result

**GO for one source-bound 20-second diagnostic launch.** The runner rejects native proposals outside the COUPLED arm or 20-second scope. It verifies every declared proposal artifact, confirms the proposal parent and boundary against the frozen COUPLED template, stages the proposed candidate, and checks candidate/build/source identity and staged hashes before accepting a completed run. Completion requires the expected one-step timestamp and native capture schedule, zero return code, and no fatal lines, processing errors, changed inputs, or duplicate snapshots.

The response reader first requires a clean, closed one-step receipt. It rechecks source receipt and proposal binding, candidate build and boundary against the frozen C1 capture, staged candidate hash, and all 57 native snapshot byte counts and hashes before reading proposal snapshots. Its output labels the result as a proposal treatment, marks physical approval `FAIL_OPEN`, and states that observation skill is unevaluated.

Projection controls are scoped to the declared free interior faces and preserve closed-boundary divergence increments; the proposal receipt remains explicitly pending native consumer and tendency validation. The launch review establishes source binding and reversible input staging only. It does not approve momentum, forecast skill, or deployment.

## Validation

Command: `python -m pytest -q tests/test_pr86_time_response.py tests/test_pr99_native_projection.py`  
Result: **36 passed**.  
Command: `python -m py_compile tools/pr86_time_response.py tools/pr99_projection_response.py`  
Result: **passed**.

The preflight is a launch-gate artifact, not a run receipt. The native 20-second run result was not reviewed in this note; only its source-bound launch readiness is assessed.
