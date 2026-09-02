# Intel-only integration readiness audit

`tools/audit_intel_integration.py` is a deterministic, read-only evidence gate
for the operational derived-cloud → QBAL → LAPSPREP chain. It never builds or
modifies the original tree.

## Contract

The audit selects these production artifacts:

| Stage | Job executable | Link Makefile |
|---|---|---|
| derived cloud | `klps_anal_derv.exe` | `src/deriv/Makefile` |
| balance | `klps_anal_qbal.exe` | `src/balance/Makefile` |
| LAPSPREP | `klps_anal_prep.exe` | `src/lapsprep/Makefile` |

It returns `0` only when every check is GO, `3` when the inspected production
state is BLOCKED, and `2` when the audit itself is misconfigured.  JSON is
written to standard output unless `--output` is supplied.  Results contain
stable machine reason codes under `findings` and `summary.blocker_codes`.

`GO` means that every static and linked-binary evidence check below passed. It does not
mean that a copied-tree build was executed, nor does it authorize ACTIVE mode
or operational publication.

The gate checks:

1. the exact pinned Intel ifx path, version, and SHA-256;
2. one top-level invocation of each executable in order, explicit completion
   and nonzero-status handling, and `KL05EXET` bound to the audited directory;
3. no forbidden compiler or unreviewed include/override in the common, top,
   stage, or copied `src/lib` Makefiles;
4. `FC` and `CPP` bound to the pinned ifx path or `CLOUD_BAL_FC`;
5. declared NetCDF, HDF5, zlib, szip, and curl roots with non-placeholder
   headers and x86-64 ELF/archive libraries;
6. the stage-specific canonical adapter in each Makefile and source tree;
7. executable ELF files with no `ldd -r` missing library or unresolved symbol;
8. the exact global stage entry symbol and the pinned IntelLLVM `.comment` in
   every executable; and
9. an adjacent `<executable>.ifx.json` receipt binding the binary hash to the
   pinned compiler and exact link argv.

The receipt schema is `cloud-bal-ifx-build-receipt-v1`. It binds the binary
hash, compiler path/version/hash, link driver, and `-o` target. It is supporting
provenance evidence, not cryptographic proof of every source and dependency.

Run the production inspection with the pinned environment:

```bash
tests/run_intel_integration_audit.sh --output scratch/audits/intel-integration.json
```

The current tree is expected to return exit `3`; that is a successful audit
which found integration blockers, not a crash.

An explicit output below `ANAL`, `MODL`, or the original `klaps-v5.0_` tree is
rejected. Audit artifacts are accepted only under a real, non-symlink
Cloud-BAL `scratch/` directory.

`ldd -r` is a dynamic-loader resolution check, not a purely static reader. The
runner removes loader-control variables, uses the pinned runtime environment,
and hashes each selected executable before and after inspection. A detected
change is a blocker and is reported in the summary.

Fixture tests are independent of NetCDF/HDF5 installations and do not compile
anything:

```bash
python3 tests/test_intel_integration_audit.py
```

## Smallest safe full-link probe

The JSON field `copied_tree_full_link_plan.shell_commands` contains the smallest
identified full-link probe: the top Makefile, `src/include`, `src/lib`, and the
three selected stage directories. It copies into Cloud-BAL
`scratch/ifx-link.*`, then runs fixed `/usr/bin/make` commands inside
`/usr/bin/bwrap`: `/` is read-only and only that copy is writable. Make control
variables are cleared and every make receives the literal pinned ifx path as
`FC` and `CPP`.

The plan is always reported as `IDENTIFIED_NOT_EXECUTED`; this audit neither
tests host user-namespace support nor runs it. If bubblewrap cannot establish
the read-only mount, the command fails before make starts. It never installs or
copies results into `ANAL`, `MODL`, the original `klaps-v5.0_`, or `EXET`.

This is a link-readiness gate, not scientific validation.  A successful link
does not authorize ACTIVE mode or replace the required real-case original vs
candidate comparison.
