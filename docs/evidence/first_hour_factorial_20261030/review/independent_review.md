# Independent review: first-hour factorial report

**Review date:** 2026-10-30  
**Status:** Pass after the review fixes and final refresh.  
**Scope:** Factorial scorer and gates, saved score arithmetic, runtime provenance, figures, final Korean manuscript, and its rendered PDF.

## Findings

- The five experiment identities and input pairings are consistent with the stated H0/H1/B0/B1 factorial and external O0 reference. For B0, the staged 89-file set differs from the preserved-background source manifest only at `wrf.exe`; the staged executable is the pinned original executable. The preserved-background `wrfinput_d01` has the expected pinned digest.
- The B0 raw and normalized runtime receipts bind each other by SHA-256. They record successful completion, both exact hourly histories, unchanged staged/source files, and unchanged producer evidence. The final scoring receipt also binds the histories and the independently checked producer evidence.
- Independently recomputed the full categorical contingency table (30 rows) and transition table (48 rows) from the saved NPZ arrays. All saved counts matched. Recomputed continuous score differences and CSI difference-in-differences also matched the report.
- CSI interaction, `(B1−B0)−(H1−H0)`, is −0.002256, +0.001021, −0.002971, −0.007482, +0.014055, and +0.020487 at 0.1, 0.5, 1, 2.5, 5, and 10 mm, respectively. Continuous score interactions are −0.0012908324 mm MAE, −0.0019592131 mm RMSE, and +0.005437281 mm mean error. The report correctly describes these as score-scale differences, not physical or causal shares.
- The figure panels are legible and consistent with the score arrays, case labels, and single-hour paired-sample scope. The design diagram now gives the scorer’s exact total, `Δ(RAINC + RAINNC)`, and states that `RAINSH` is checked zero and excluded. O0 is clearly outside the 2×2 design.
- The manuscript bounds the results to one event and one forecast hour, distinguishes the processed RN1 analysis from gauge truth, notes the unresolved coverage/QC and process-budget limitations, and avoids claims of operational readiness or general skill improvement.
- The continuous-score equations render correctly using `a_i = abs(e_i)`, with MAE, RMSE, and ME defined separately. The final PDF text has no stray `∨`, `¿`, or unrendered TeX commands. All four table captions remain with their tables, and figure captions remain with their figures.
- The renderer’s three tests pass, covering source-path independence, preservation on mutated CSV failure, and deterministic reproduction of all nine figure assets. Its final manifest pins the renderer source.
- Rehashed all **1,185** analysis-receipt source records (910 unique paths): zero mismatches. Rehashed all **496** prior evidence manifest entries (493 preserved in place and three graph artifacts bound to the dated snapshot): zero mismatches.
- References checked: WRF Version 4 technical note [doi:10.5065/1dfh-6p97](https://doi.org/10.5065/1dfh-6p97); the cited KDM6 context is correctly identified as a 2025 conference abstract, not a journal paper or validation of this implementation; JWGFVR 2013 precipitation-verification guidance, hosted by WGNE, supports the stated limitations on supported grid points, stratification, and uncertainty.

## Review fixes confirmed

The review found and confirmed resolution of these issues before the final refresh:

1. The design figure initially included `RAINSH` in the accumulation equation, while the pinned scorer excludes it after a separate zero check. The figure now matches the scorer.
2. Earlier PDFs stranded a table caption from its table. The final PDF keeps all table captions with their tables, including Table 3 and Table 4 on page 5. The methods explanation for `RAINSH` is also in Korean in the final source.
3. A dangling `[4]` citation remained after the bibliography was reduced to three entries. It now points to reference `[3]` (JWGFVR, 2013); the final bibliography has three entries.
4. The first PDF rendering had malformed absolute-value math glyphs. The final equations use `a_i = abs(e_i)`; visual inspection and PDF text extraction confirm the repaired math. The figure axes now label the precipitation threshold as a one-hour accumulation in mm and the error metrics in mm. O0 is described as a separately marked external reference.

## Validation evidence

- `pytest -q tests/test_cp02_first_hour_factorial.py`: **4 passed**.
- `pytest -q tests/test_plot_first_hour_factorial.py`: **3 passed**.
- Independent array recount: **30 categorical rows and 48 transition rows matched**.
- Source-pin recount: all **1,185** analysis receipt records matched their files. Prior-evidence recount: all **496** manifest entries matched their preserved files or dated graph copies.
- Final paper build receipt: all source, score, and figure input hashes match; output PDF and DOCX hashes match the receipt. The final document is six A4 pages with 15 DOCX math objects and three embedded figures.
- Final SHA-256 values:
  - Analysis receipt: `900ee2342a434d418c67d2b86bd5519255fbb555872436ea0e219dd5d23adf56`
  - Figure manifest: `5264c2a19303e7f4e32543ef18e03e22173797a0fc47dc1292976f0ac7ce29bf`
  - Renderer: `40d47aba5cc0473dcc238b2994d025ea4936766f3a35f32d59165d52938fb04c`
  - Paper build receipt: `5cf4c3a6c83681e19e2fd0f349e673ef5de667813b4cfe625f9771524e65df9a`
  - DOCX: `108a7a830b398b60644358f4c1b0d900bf90a7c656f4ba68a184a07054c66839`
  - PDF: `cc60a28f1a1714889b3bc8771049c784978ba1398989c04103610889534f7f4f`

No unresolved scientific, arithmetic, provenance, or presentation blocker was found in the reviewed scope. This review does not expand the runtime or scientific scope beyond the one-case, one-hour experiment.
