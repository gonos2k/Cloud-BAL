# Independent review of the closed PR102 five-arm history readback

## Scope and binding

Reviewed the published final-v2 five-arm report and its execution/publication bindings. No raw history or live model fields were opened. The STRUCTURED C2 receipt is COMPLETE for 32/32 steps and 640 seconds, return code 0, SHA-256 `313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6`. The report is `fivearm_history_readback.json`, SHA-256 `d10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2`. Execution record SHA-256 is `cfb54c75dfd6d6b6e101a98a7f24e7ecd3b3cd1beba1d949c03ec7d5a7ddcd9d`; root post-closure GO SHA-256 is `1893acf1f6853cc41674a3843f8f3e0103ac6db3c5676b2d909a5d50b54ca5ad`.

The report binds the fixed composition hash, 613-cell support, 16 support columns, 39 levels, 196-column buffer, exact 11 timestamps from 0 to 600 seconds, five actual C2 arms, and the unchanged v2 reader. Code pins before/after match. The four fields are pressure (Pa), geopotential (m²/s²), W (m/s), and QCLOUD (kg/kg dry). Each field/time/arm has the declared support and buffer sample counts.

## Findings

At 600 seconds, on the original 613-cell support, RMS(arm − actual OFF) for STRUCTURED N is lower than projected P by 13.34% for pressure, 20.85% for geopotential, 24.16% for W, and 23.61% for QCLOUD. The N RMS remains above HYDRO H for all four fields at this endpoint. At 60 seconds, N RMS is higher than P for geopotential by 9.13% and W by 0.23%; endpoint reductions therefore do not describe a uniform time response.

On the 196-column buffer at 600 seconds, N RMS(arm − OFF) is lower than P by 10.58%, 8.24%, 20.68%, and 11.98% for the same four fields. N is above H for pressure, geopotential, and W, but QC is below H there (1.0534e-5 versus 1.1157e-5 kg/kg dry). The support-only “all above H” statement must not be generalized to the buffer.

Each non-OFF arm's t=0 QCLOUD contrast against actual OFF matches bitwise with the other arms on both masks. This shared contrast is nonzero: RMS is `1.2509394e-4 kg/kg dry` on support and `3.5424699e-5 kg/kg dry` on buffer. At 600 seconds, QC contrast cosine against that arm's own t=0 contrast is negative on both regions: support N `−0.15249`, P `−0.38319`, H `−0.09225`; buffer N `−0.10244`, P `−0.29660`, H `−0.05353`. These are fixed-pattern diagnostics, not Pearson correlation or observation skill; lower QC RMS does not establish preservation of the initial contrast.

The PNG and PDF show all five arms at all 11 history times for the four fields, with solid original-support and dashed fixed-buffer curves. No plot defect was apparent. The figures show RMS response only; QC contrast cosines and projections are reported in the JSON.

## Final full-response consistency review

The frozen full-response report is now published as
[`closed_response/response.json`](../closed_response/response.json), SHA-256
`c336cbf5ede5a19f073f0ce195ee928c1daa4074fe7dafe817e2734fdfb04ebf`. Its
execution is COMPLETE with return code 0 and before/after input pins identical;
the execution record SHA-256 is
`5ebefc02d93a117c4ae9e8318a6a02542df7697aeaf17153d1ab7ab7526bfa45`. The
publication receipt is COMPLETE_DESCRIPTIVE_ONLY, SHA-256
`a90286c734c97c21be5178783fdf61c19f11094e9b3db6da876a7db93cb8bb4a`.

The report's candidate-minus-OFF RMS, max-absolute, and signed-sum values
match the final-v2 five-arm report exactly for all 11 saved times, four
overlapping fields, and both fixed regions: 88 comparison cases, with zero
numeric mismatches on the shared metrics. The full report's saved history
covers 0–600 seconds at 60-second intervals. Its separate POST_KDM6 trace is
at 20, 60, 300, 320, 480, 500, 600, and 640 seconds for Q/QC/QI/QR/QS/QG; it
is not conflated with host history.

The first-source section is scoped to H=HYDRO, P=original projected, and
N=candidate one-step captures (57 files per role). Its physical dry-column
rates and raw assembled RU/RV norms match the already-published first-native
assessment exactly. The report keeps staggered RU/RV/MUDF source diagnostics
separate from physical kg/s column rates and does not claim energy,
acceleration, or continuity closure. No raw model fields were opened for this
cross-check.

This is a **GO for closed-report scope, coverage, provenance, and cross-reader
consistency**. It is not science or forecast approval. Physical approval
remains `FAIL_OPEN`; observation skill remains `NOT_EVALUATED`. HYDRO remains a
control reference, not truth. All history differences and QC pattern metrics
are descriptive; a negative QC contrast cosine is not described as preserved
initial pattern or skill.
