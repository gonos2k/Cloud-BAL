# Legacy derived-cloud production safety audit

## Contract

`tools/audit_legacy_deriv_safety.py` is one fail-closed decision pipeline for
the legacy `klps_anal_derv.exe`. It evaluates six stages:

1. source authority: evaporation, radar bogus-w, and empirical cloud bogus-w;
2. exact source and executable-name selection;
3. `deriv.nl` defense-in-depth settings;
4. direct legacy calls in the deployed binary;
5. `FC` and `CPP` selection of Intel `ifx`;
6. production provenance.

Source authority is proved at the three use sites, not by control-flow
inference: both dormant radar calls require literal constant-false guards, and
the exact 27th `get_cloud_deriv` argument must be literal `.false.`. Flag and
mode assignments remain defense in depth. The first five stages are
deterministic local checks. The sixth is deliberately
`BLOCKED`: a source/binary clean-build trace and the scheduler's resolved
`${KL05EXET}` argv/environment trace do not yet exist. A namelist-only OFF state,
matching timestamps, or embedded filenames never prove production binding.
Therefore this revision cannot issue a production `GO`.

## Current audit

Run:

```bash
tests/run_legacy_deriv_safety_audit.sh
```

The wrapper only reads `ANAL`, `MODL`, and `klaps-v5.0_`. Audit output and the
review patch are created in a temporary directory. The tool rejects output
paths inside any protected original tree and never replaces an existing file.

The current operational path is expected to be `BLOCKED` because:

- `rfill_evap` and `get_radar_deriv` remain directly callable;
- empirical cloud bogus-w is hardcoded active;
- both `FC` and `CPP` select `ifort`, not `ifx`;
- no trusted build/runtime execution trace binds the audited binary.

The current `MODE_EVAP=0` and `L_BOGUS_RADAR_W=.false.` namelist values pass
only as defense in depth.

## Review-only patch

The same tool can render one deterministic minimal patch without applying it:

```bash
python3 tools/audit_legacy_deriv_safety.py \
  --source ../klaps-v5.0_/src/deriv/laps_deriv_sub.f \
  --emit-patch /tmp/legacy-deriv-safety.patch
```

The patch hard-locks evaporation, radar bogus-w, and empirical cloud bogus-w,
passes literal `.false.` at the cloud bogus-w call argument, and places literal
constant-false guards around both dormant radar calls.
It is only a SHADOW safety prerequisite; it does not authorize publication.

## CLI

Audit inputs are `--source`, `--makefile`, `--make-config`, `--job-script`,
`--namelist`, and `--binary`. `--output` writes the JSON decision and
`--emit-patch` writes the review-only patch. Missing optional audit evidence is
reported as `BLOCKED`; exit status is 0 only for `GO` and 2 for `BLOCKED`.
