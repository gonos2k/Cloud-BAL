# HYDRO evidence selection

Only **`current_generation_final2/`** binds the selected current-generation HYDRO forecast input. Its final input receipt SHA-256 is `967a481070c37286f6aef8d616679583f1c86afb7dd60ac64f1d411977eba39b`; its initialized input SHA-256 is `46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c`.

Earlier receipts are preserved as attempted input preparation, not as alternative authorizations for the forecast:

- Files directly in this directory include the historical PR78 chain and preliminary current-generation bookkeeping.
- `current_generation/` is superseded. It does not establish the selected final input chain.
- `current_generation_final/` is superseded by final2's boundary and stage/initializer crosslink checks.
- Earlier producer builds whose compiler working directory was the source tree are excluded from the validation claim. Final2 binds fresh O0/O2 builds whose actual working directories were scratch build directories.

A `PASS` inside an earlier immutable receipt describes only that earlier operation; it does not override this selection. `current_generation_final2/artifact_bindings.json` derives artifact paths, hashes and byte counts from the selected files. The full model arrays remain external. Input/readback provenance does not establish forecast completion, observation skill, or physical closure.
