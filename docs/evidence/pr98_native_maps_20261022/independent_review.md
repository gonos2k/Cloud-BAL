# PR98 native maps review — 2026-10-22

Scope: read-only review of `tools/pr98_native_maps.py`, `docs/evidence/pr98_native_maps_20261022/manifest.json`, and both PNG figures. No regeneration or code edits.

## Result

No substantive data or provenance findings. Manifest pins native level 16; active mass grid i=2..233, j=2..281; 613 original QC points and 16 projected columns; zoom bounds i=128.5..142.5, j=10.5..24.5 and explicitly says the fixed five-cell Chebyshev buffer was selected independently of response values. It binds all three closed C1 histories and receipts, plus composition, plotting source, and four artifact hashes. Recomputed PNG/SVG and script hashes match the manifest.

The reader calls the existing `load_history`, which destaggers U and V by averaging adjacent native faces onto mass points and destaggers W vertically; panel arrays share `(39, 280, 232)`. The six panel extrema match corresponding native-effect source values: initial U max 6.3578898908, V max 6.1800928116, wind magnitude 6.5525397042 m/s; pressure −30.90234375..25.42578125 Pa; geopotential −85.6435546875..90.4573974609 m²/s²; W −0.4812700786..0.3633011486 m/s. Both figures show the fixed QC outline, initial wind peak marker, and explicitly disclaim force, continuity, and observation-skill interpretation. Full-domain and buffered views are legible and consistent.

## Minor clarity suggestion

The figure subtitle says “Mass-point saved states,” and the plotting code’s `load_history` dependency performs the face-to-mass averaging, but the U/V panel titles do not themselves say “mass-point averaged.” Consider changing them to “Initial mass-point U increment” and “Initial mass-point V increment” (or adding one short note to the subtitle). This is documentation clarity only; no analysis defect.

Files reviewed: `tools/pr98_native_maps.py` SHA-256 `10dab1d0bd2075726546172a1496180a6c2d3075557537d68e466d36e4e44dc6`; manifest SHA-256 `86c20d44387090bef7326fc476e86e0fb40ff682843aa081b2c11062f684eb52`.
