# PR110 external-input absence qualification

## Result

The full portable contract runner passed from a clean archive of the committed PR110 source under the native kernel syscall gate:

- Exit status: 0.
- Runner summary: Tier 'portable' passed: 210 tests passed, 0 skipped.
- The wrapper reports 0 skipped tests; nested pytest output includes one skipped case (test_verify_shadow_wps_pair_lambert.py: 3 passed, 1 skipped).
- Updated PR71 + PR83 transaction + sealed executable focused checks: 10 passed.
- Baseline old PR71 + PR83 transaction focused checks: 2 failed / 2 passed because the frozen research source and native provenance inputs were absent.
- Direct probe: 10 reported paths returned ENOENT for stat, lstat, and open; exists and access were false; ifx was not found on PATH. Raw x86_64 stat and lstat syscalls also independently returned ENOENT.
- The final full run had no SUPERVISOR_PATH_READ_FAILED messages.

## Source and runtime

- PR source commit: bb2358de77d0496d13004b0fba0d6d96036d2934.
- Clean archived source: /var/tmp/pr110_isolated/source-final, synthetic Git HEAD de2b13b39995766949c946f324142c1427cf85ae.
- Git archive SHA256: 982dbfc6e9c462cd074bbe8c063d478037854f98712b03d37a9b41ca6edc3647.
- Python 3.12.3; pytest 8.1.1; NumPy 1.26.4; netCDF4 1.7.4; SciPy 1.15.3; matplotlib 3.10.1.
- Dependency environment: /var/tmp/pr109_isolated/environment.
- TMPDIR: /var/tmp/pr110_isolated/scratch, outside the checkout.

Final full-run command:

    cd /var/tmp/pr110_isolated/source-final
    env TMPDIR=/var/tmp/pr110_isolated/scratch \
      PATH=/var/tmp/pr109_isolated/environment/bin:/usr/bin:/bin \
      PYTHON_BIN=/var/tmp/pr109_isolated/environment/bin/python3 \
      TEST_TIER=portable \
      /var/tmp/pr110_isolated/absent_supervisor_final -- \
      /usr/bin/bash tests/run_python_contract_tests.sh

Supervisor build: GCC 13.3.0-6ubuntu2~24.04, command:

    gcc -O2 -Wall -Wextra       -o /var/tmp/pr110_isolated/absent_supervisor_final       /var/tmp/pr110_isolated/absent_supervisor.c

## Supervisor evidence

- Final C source: /var/tmp/pr110_isolated/absent_supervisor.c, SHA256 984b9e32183add27fca858adb42a0a170b3db6c319a2bba05271fffa81f1e7fd.
- Final binary: /var/tmp/pr110_isolated/absent_supervisor_final, SHA256 6c3467938f18d577b304bafc66ff7da021a5f899eb567f177d4b092c97bf3b55.
- Full portable log: /var/tmp/pr110_isolated/full-portable-seccomp-final.log, SHA256 4521c18a214ed900851765c6a43e8a95a5a5e9d6b67114fe8ed90397a57dfd68.
- Baseline syscall-gate focused log: /var/tmp/pr110_isolated/baseline-seccomp-focused.log, SHA256 17f37adf91e722b1453817075ae94168827d6ad5f9f67935ad78190099fc282d.
- Final updated syscall-gate focused log: /var/tmp/pr110_isolated/focused-seccomp-final.log, SHA256 ed3a5a27ca8f03a2bda786968e4581ce4b95e1980f33136756dfb18bd21d7c17.
- ENOENT probe script: /var/tmp/pr110_isolated/probe_absence.py; its log /var/tmp/pr110_isolated/absence-probe-final.log, SHA256 7fc778d662b0b9bc5e748893f7f38a80bbba4511774f258fd34ff966b7626d4d.
- Raw stat/lstat probe: /var/tmp/pr110_isolated/scratch/raw_stat_probe.py; log /var/tmp/pr110_isolated/raw-stat-probe-final.log, SHA256 0816a986c8329d7be1c59d2cf7a91092053d9235323c132d495d7eeff2d8e8e6.

The source lists the denied prefixes: /NHNHOME and enumerated /var/tmp research/build roots referenced by Cloud-BAL tests. The supervisor sends user notifications for open, openat, openat2, newfstatat, raw stat/lstat, statx, access, faccessat, faccessat2, readlink, readlinkat, chdir, execve, and execveat. It returns ENOENT for those prefixes and continues unrelated calls. Failure to read a notified path from the child returns EIO and emits SUPERVISOR_PATH_READ_FAILED; it never silently continues such a request.

## Separate rootfs checks and limits

The earlier explicit-rootfs PRoot guest view did not expose the configured host paths. Baseline focused output is /var/tmp/pr110_isolated/baseline-focused.log (2 failed / 2 passed); updated focused output is /var/tmp/pr110_isolated/rootfs-updated-focused.log (4 passed). PRoot could not run the sealed MFD_CLOEXEC executable tests, so the full suite used the native-kernel syscall gate instead. PRoot package/source artifacts are retained separately under /var/tmp/pr110_isolated for reproducibility; the clean test snapshot and gate receipts are the small files listed above.

The syscall gate is a nonadversarial absence qualification, not a security sandbox or physical-host mount isolation claim. It filters the listed path operations and configured prefixes only. It does not block alternate path aliases, directory enumeration, already-open file descriptors, or a hostile process designed to bypass the test setup. It establishes behavior for the test suite and configured access paths; it does not establish general filesystem isolation.
