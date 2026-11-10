# Fresh real replay and rejected fixed-prior completion

This bundle documents a single B1 demonstration, not a weather improvement or a forecast. The source-pinned physical interpretation and detailed outcome are in [real_probe_rejection.md](../real_probe_rejection.md). Native first-use observation is **UNRUN** because the common completion rejected the candidate before publication.

`plan.json` and `plan_v2.json` preserve the 91 input identities and fixed physical policy. Their original paths refer to the external scratch environment; the corresponding `namelist_v1.input` and `namelist_v2.input` are copied here and each reproduces the hash in its plan. Version 1 put `use_theta_m` in the wrong namelist section and `real_bad_namelist.log` records the fatal parse. Version 2 fixes that syntax only, matching the historical effective setting. The first version-2 execution used the shell's 8192 KiB stack and failed in `vert_interp` (`real_stack_failure.log`); a fresh retry with unlimited stack succeeded (`real_success.log`). The successful file exactly matches the historical SHA-256 `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`.

`completion.stdout` records a wrapper metadata guard failure before real launch. `completion_v2.stdout` records a producer replay followed by a binary-stream protocol mismatch while the driver interface was being changed; it is not a physics result. `manifest_v2.json` binds the rebuilt matching driver, and `completion_v3.stdout` records the authoritative common-kernel failure at (1,228,13,NI). Output and success receipt were absent. No fixed prior was changed following rejection and no 20-second WRF run was started.

The driver was compiled in a fresh directory with `tests/intel_toolchain.sh` pinned IFX 2026.0.0 reproducibility profile (`-O2 -fp-model strict -fimf-arch-consistency=true -no-ftz -fpe0` plus profile diagnostics). SHA-256: profile `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`, ifx `909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef`, compiled driver `ac51c581b57172b7ef913bb5dca24aa18c3ad94ed0f4681d865929c924eca11a`, real.exe `58118b30f35f1e817cd500fc0047ee3e0b334975a3231faf3a46b3a5728c5c10`. The local executable, compiled driver, full NetCDF file, and 16 MB candidate array bundle remain outside this repository under `scratch/physical_moment_handoff_20261110/native_probe_20261110/`; the manifest binds their hashes. A historical receipt and candidate source are present but do not establish source-to-executable provenance for real.exe.

`recount_ice_cap.py` independently reads only QICE, QNICE, AL and ALB from the hash-verified producer file. `ice_cap_recount.json` gives the reproducible C-order mask algorithm, shape, mask SHA-256, count, and failed cell values. Run with:

```sh
python recount_ice_cap.py /path/to/wrfinput_d01 /new/path/recount.json
```

The 106,128 count is a file-state calculation of prior-implied cap exceedances before background precedence. It is not the count of physically observed particles, a native model diagnostic, or evidence of first-use density. The original input has zero QNICE everywhere; file proxy density is not guaranteed equal to the subsequent native first-use density.
