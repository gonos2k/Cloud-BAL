# Validation scope

- Final focused batch: 93 tests passed. `focused_validation.txt` and
  `validation_sources.json` identify the tested source files.
- The source-derived ice test compiles in fresh scratch directories with
  the pinned Intel 2026 O0 and O2 profiles. Its literal receipt is
  `../pr96_hydro_20261021/ice_ng_o0_o2.txt`, SHA256
  `f4be518c04dbcd017ef17c656e3fcf468cacc2d02ba7356ffe7d7a31adadf47c`.
- That raw receipt retains two trailing spaces emitted by its
  `compile_command` printer. It is excluded from the whitespace check to
  preserve its bytes. `git diff --cached --check` passes for every other
  staged file. The zero-context diagnostic patch reproduces the same
  compiled source as before its display-format change.
- The separate nine-object native overlay build passes with the pinned
  optimized strict profile. It is a partial-host build, with three native
  600-second validation requests launched and closed results pending.

No canonical full pipeline, clean WRF rebuild, whole-tile water closure,
energy closure, native mass–wind closure, or independent observation skill
is established by these focused checks.
