# PR99 bulk candidate contract evidence

This bounded bundle supports the local candidate-certificate note. It contains
the source validation receipt and commands, short test outputs, the three-arm
C1 fallback summary, and one selected T32 reason-6 excerpt per original arm.
It excludes compiled host sources, executables, private model arrays, full
model stdout, and full PR92 captures.

## Frozen source and test pins

[`provenance/README.md`](provenance/README.md) describes the selected evidence.
`provenance/source_validation.json` is the author-frozen v2 validation summary.
It binds the shared core, source generator, focused test
and fixture hashes, pinned C1 host source, generated host-source hash, Intel
profile, compiler, fresh scratch paths, expanded test commands, executable
hashes, and PASS/limitations. The generated host source itself is intentionally
not copied into this public bundle.

The source generator produced host SHA-256
`98a44389d693ec28533d492c129204fc0bdba22e6ed3ae71acc9e65df7b9cb1a` from
pinned C1 host SHA-256
`f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af`, using
shared core SHA-256
`6c844fe8a68ded3c653d800065d428c390b08845a584dc65ab070995adc7dd53`,
archival pre-certificate core SHA-256
`faa4ce0e31bf5b394c9a5ec2045a917464dca7cd4d902b6aa62be80a19aa5ac0`, and
generator SHA-256
`64f9b4fea53ae44ba15d0a4b331520c4b5931436e001ea4b8124fc8b348bfaf0`.
The archival fixture is an identity/preimage check for the embedded module; it
is not used as a runtime core.

The final author-validation JSON SHA-256 is
`4abb18635ae5f19b04ac87f31b3b6100e9d4df850a43bd556a156b8b72eafeb1`. The
independent oracle pins that validation in
`independent_oracle/pinned_inputs.json` (SHA-256
`53b8e584c840989dcc8cac77e0bec7078e13d30af173e22c92a204b9601fa515`). Its
final source manifest SHA-256 is
`71a9818bb95a2c18fd91c494a9e06151d19a00717568864cc44008f5ab087d56`. The
independent review is included at
`independent_oracle/independent_review.txt` (SHA-256
`e8ddf731dc2989f6310d057a7225fe77ffbde00c376117736abd17e9e3010343`). The
full shared-core regression validation JSON SHA-256 is
`0ee2677132c34b0175d7a261492a4a950d527feb7340f598005ec0f793b44f23`.

## Runtime context

`provenance/three_arm_fallback_summary.json` is pinned by SHA-256
`451c161986f3fc3502641cee87f6717fdfa4c5042854d875ae72d6c58e26ae89` and
binds the three original C1 arms plus the separate diagnostic OFF capture.
Each old C1 arm is **INCOMPLETE**, ending at step 31/32 (620/640 seconds,
return code 1). The short excerpts select the same T32/RK1 local reason-6
fallback at `(i,j,k)=(2,241,14)`, pair 4. They are not full captures and do not
establish a producer-wide or physical cause.

The unchanged earlier grouped-failure package distinguishes this local
reason-6 event from its first ordinary stage-2 store rejection:
[`PR99_GROUPED_FAILURE_DIAGNOSTIC_20261022.md`](../../PR99_GROUPED_FAILURE_DIAGNOSTIC_20261022.md).
The bulk-candidate proposal changes storage admissibility and must be tested
as a separate candidate, PR99-C2. The independent typed-input oracle and
source/control-space review are complete with no false accepts and no review
blocker; they do not validate the full model. Native three-arm tests have not
started, and no forecast or launch is represented here.

## Files

- `provenance/source_validation.json`: hashes, commands, results, compiler/profile, and limits.
- `provenance/commands.txt`: compact compiler/profile/scratch summary; expanded commands are in the JSON.
- `provenance/new_candidate_O0.stdout`, `provenance/new_candidate_O2.stdout`: local certificate test markers.
- `provenance/pr92_O0.stdout`, `provenance/pr92_O2.stdout`, and stderr files: existing policy regression outputs.
- `provenance/python_tests.stderr`: Python fixture test summaries.
- `provenance/three_arm_fallback_summary.json`: bounded selected runtime bindings and status.
- `provenance/C1_OFF_T32_reason6.txt`, `provenance/C1_HYDRO_T32_reason6.txt`, `provenance/C1_COUPLED_T32_reason6.txt`: selected per-arm excerpts.
- `independent_oracle/`: exact Fraction reference, 40 typed cases, Fortran black-box harness, per-profile results/logs/hash inputs, and frozen independent review. Compiled executables are excluded.
- `core_regression/`: pinned-core FREE/O0 and REPRO/O2 command/stdout/validation records. Executables are excluded.

Native three-arm tests have not started; this package does not authorize a
run. `SHA256SUMS` covers every file in this directory except itself.
