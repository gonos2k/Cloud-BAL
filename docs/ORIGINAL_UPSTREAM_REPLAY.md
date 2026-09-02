# Original KLAPS upstream replay harness

Status: `BLOCKED_SAFE_PREFLIGHT`

The replay harness prepares the missing direct-QBAL generation without writing
to live `ANAL`, `MODL`, `klaps-v5.0_`, balance, LAPSPREP, WPS, or final product
trees.  It does not accept `bigfile`, `LAPS:*`, `KLBG:*`, `met_em`,
`lapsprep/wps`, or `balance/*` as an upstream source.

## Command

```bash
python3 tools/original_upstream_replay.py \
  --root scratch/original_upstream_replay/<new-generation>
```

The repository default replay specification has a source-code-pinned SHA-256.
Every custom `--spec` requires a separately supplied `--spec-sha256`; a
missing or mismatched pin produces only a BLOCKED receipt.

Every declared source is copied into the new scratch root.  Copies are regular,
single-link, read-only files with a verified SHA-256; symlinks and hard links to
the protected source are not used. Every source-tree path component is checked
without following symlinks, and nested source-tree symlinks or multiply linked
files block the generation. Source-tree paths containing a forbidden
final/bigfile component are rejected. The downstream direct-QBAL receipt also
rejects a pre-QBAL root with a symlink anywhere in its ancestor path. This
preflight has no execution option.

The command always emits `PRE_QBAL_MANIFEST.json` after a safe output root has
been established.  A blocked run exits with status 3.  It records:

- the exact four case identities and FUA/FSF/LW3/VRZ/VRT hashes;
- replay harness, replay specification and case-manifest hashes;
- original Intel executable and configuration hashes;
- a deterministic source-tree receipt hash;
- per-case VRT completion before temperature analysis;
- the VRT gate as `PASS` or `BLOCKED`, and every executable stage as `NOT_RUN`
  with its explicit blocker;
- expected LT1/LQ3/LW3/LCO/LSX paths and producer identities; and
- `generation_status=BLOCKED`, never a false COMPLETE generation.

While blocked, `input_closure_sha256` is null; the hash of the currently
declared subset is recorded separately as `declared_input_receipt_sha256` and
is never presented as a complete closure.

`PRE_QBAL_MANIFEST.json` is promoted to the
`original_klaps_pre_qbal_generation_v1` COMPLETE form only after all products
have been independently generated and validated.  The COMPLETE product map is
fixed as follows.

| Product | Producer stage | Producer executable |
|---|---|---|
| LT1 | temperature_analysis | klps_anal_temp.exe |
| LQ3 | humidity_analysis | klps_anal_humd.exe |
| LW3 | wind_analysis | klps_anal_wind_openmp.exe |
| LCO | derived_cloud_analysis | klps_anal_derv.exe |
| LSX | surface_analysis | klps_anal_lsfc.exe |

## Current deterministic blockers

The prepared four cases pass their source hashes and VRT completion gate.  The
original executables also pass the pinned SHA-256 and Intel-family checks.
Execution is nevertheless refused because:

1. wind, surface, cloud, humidity, previous-time, lightning and satellite
   input closures have not been enumerated file by file;
2. Intel runtime and external library files have not been pinned as a complete
   read closure;
3. the host denies the strict bubblewrap namespace probe, so read/write access
   cannot be constrained to the declared scratch tree; and
4. the legacy programs can return process status zero after internal failure,
   while stage-specific output validators are not complete.

There is intentionally no unrestricted fallback.  The next implementation
step is to enumerate those closures and add field/time/grid-aware validators;
only then can a reviewed sandbox backend be enabled.

The deterministic source-tree hash currently records what was inspected; it
is not yet pinned by an independent release authority. That external pin is a
promotion prerequisite, not a reason to weaken the current BLOCKED preflight.

## Test

```bash
tests/run_original_upstream_replay_tests.sh
```

The fixture uses inert, structurally valid ELF files carrying an Intel runtime
marker and verifies that none is started, only declared files are copied, every
copy is independent and read-only, the protected inputs are unchanged, and a
BLOCKED manifest is still produced.  The real dry-run additionally verifies all
four prepared VRT files before reporting the current blockers.
