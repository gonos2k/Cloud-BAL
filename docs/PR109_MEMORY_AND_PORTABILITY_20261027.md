# PR109: dynamic input memory contract and isolated portable regression

Base: PR108 merge `cb60815357d83fafe43dcdbb6afa6eb88192c04a`.

LAPSPREP's dynamic input preflight now accepts only `NF_FLOAT` payloads and
level coordinates. Those fields are subsequently read by legacy `NCVGT` into
default REAL buffers; accepting `NF_DOUBLE` there did not provide conversion.
The producer format remains unchanged. Double precision input support is not
claimed. Static-file `NCVGT`/`NCVGT1` reads are outside this change.

The final REAL32 native W candidate is checked against the open variable's
fill/missing and range attributes before writing. Rejection preserves the
original W and other sampled fields. Git status failure now propagates through
the clean-source helper, including command substitution and the two real
runners' final checks.

## Portable boundary

PR108's fresh checkout ran on the research host. That success did not establish
independence from external research files or the installed Intel toolchain.
This revision retains pure fixture checks and separates source-bound/native
execution and external receipt checks into explicitly registered integration
modules. Production provenance checks and historical pins are unchanged.

The qualification run uses a copied source tree and Python environment under
one private scratch root. Landlock denies external research file reads and
Intel compiler reads/execution, and those denials are probed before the suite.
`HOME`, `TMPDIR`, Python user-site settings and PATH are explicitly set.
Directory metadata remains visible; this is a dependency-confinement test,
not a claim of an empty filesystem or an adversarial security boundary.
System libraries and tools remain accessible. Network isolation is not claimed.

The initial namespace-based isolation attempt was unavailable on this host
(`bwrap` user-ID mapping denied). It was not counted as a passing test. Early
Landlock setup runs exposed directory-traversal access and the archive's absent
Git identity; those environment setup failures are separate from discovered
external test dependencies. The final complete run, source hashes and scopes
are recorded in the validation evidence.

## Validation

- Confined full portable command: exit 0; 208 Python files and 2 shell files
  passed, with no all-skipped files. The 201 pytest modules reported 1,340 cases
  passed and one optional pyproj reference skipped; seven legacy scripts passed.
- Registry: 309 modules = 208 portable + 4 Linux + 83 native + 14 realdata.
  This is classification, not a pass for all four tiers.
- Pinned Intel fresh-scratch LAPSPREP harness passed at O0/O2. Each optimization
  executes the same 33 rejection cases, including `f8t3`, `f8u3`, `f8level`,
  requiring nonzero exit and no output. Valid producer fixtures remain covered.
- Native W passed O0/O2, including range overflow and output collision with
  `_FillValue`/`missing_value`; original W and sampled other fields remain unchanged.
- Actual corrupt-index shell checks propagate failure for direct and command
  substitution calls. Existing publication recovery regressions still pass.
- Changed/split Python files preserve all 86 test declarations. The new sibling
  files collected 29 cases: 28 integration cases and one portable fixture case.
  Collection did not execute their native/evidence paths;
  focused pure tests and the complete confined run validate the portable side.
- Independent team reviews covered LAPSPREP, W, shell gates and test separation.

Exact source hashes, commands, dependency versions and log hashes are in
[evidence/validation.json](evidence/pr109_memory_portability_20261027/validation.json).
The confinement launcher and six double-input rejection summaries are retained
beside it. No full native/Linux/realdata suite pass is asserted.

## Scientific scope

No C2 physics, wind input, solver tolerance or source-cache policy changes.
The prior H/A/N one-hour forecast remains INCOMPLETE at 760 seconds; 14 UTC
observation skill remains NOT_EVALUATED. This change does not resolve T39 or
establish full-host conservation. Existing research jobs are not restarted.
Graph updates describe source relationships, not runtime/scientific validation.
