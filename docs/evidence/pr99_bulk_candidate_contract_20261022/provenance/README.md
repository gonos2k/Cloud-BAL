# Provenance and selected source-validation outputs

`source_validation.json` is the author-frozen v2 validation summary. It records
the core, generator, focused source/test/fixture hashes, compiler and pinned
Intel profile, fresh scratch paths, expanded commands, executable hashes,
results, and the limits of the local tests. Its source generator output is
`module_em_certified_v2.F` SHA-256
`98a44389d693ec28533d492c129204fc0bdba22e6ed3ae71acc9e65df7b9cb1a`;
the 302 KB generated file is not copied here.

The two `new_candidate_*.stdout` files each contain the local certificate PASS
marker at O0 and O2 for v2. `python_tests.stderr` records the focused Python fixture
test summaries. The `pr92_*.stdout` and `pr92_*.stderr` files preserve the
existing storage-policy regression outputs at O0/O2; O0 emitted compiler
diagnostics, so its stderr is retained without interpretation as a test
failure (the validation summary records PASS).

`three_arm_fallback_summary.json` binds the incomplete historical OFF, HYDRO,
and COUPLED C1 receipts/captures and separately identified diagnostic OFF
capture. The three `C1_*_T32_reason6.txt` files are selected excerpts only.
Full model stdout, PR92 captures, arrays, and compiled products remain outside
this bundle and are identified only by path/hash where recorded.

The root README contains the interpretation and remaining native-run gates.
Independent Fraction-oracle inputs, per-profile outputs, and its review are
under `../independent_oracle/`; the full shared-core O0/O2 regression summary
and outputs are under `../core_regression/`. `SHA256SUMS` covers the package
files except itself.
