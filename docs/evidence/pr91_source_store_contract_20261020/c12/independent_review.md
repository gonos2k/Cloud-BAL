# C12 source and runtime review

## Source pins and prior failure evidence

The C12 generated source pair is `generated/module_em.F` (SHA-256 `fcdc8f34b523aa83adcf7f60a049e27aba5f1975c264bb7118bb7efe62120a5f`) and `generated/solve_em.F` (`d0ff9110811811c01ad13709bf5b538f7b92a49739211b0519aac55a81bc04a6`). It was generated from D3 `module_em.F` (`dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d`) and archived C7 `solve_em.F` (`412183300ea8dd6af028ac1a5254f937477b054630db4eb1f5910a6bf974c3c5`).

The original C7 OFF and COUPLED 600-second requests both ended at T10/RK3 before KDM6. Each had the same six `FULL` rejection coordinates: cloud pair 1 `(130,182,2)` and graupel pair 4 `(194,80,22)`, `(132,201,19)`, `(168,225,20)`, `(196,211,16)`, `(231,240,20)`. C7's logger lacked exact candidate bits and `failure_stage`; the precise failed predicate therefore remains open for those C7 records. The archived classification is `docs/evidence/pr90_rain_roundtrip_20261019/c7/600/failure_classification.md`; C7 compiled module SHA-256 is `090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819`.

D3's targeted OFF diagnostic provides exact replay for those six coordinates across T10 RK1/RK2/RK3 and baseline/source-first attempts: 17 records total, all reproduced under pinned Intel O0/O2. Fifteen pair-4 failures are continuous strict mass-ratio stage 2; two pair-1 failures are continuous volume stage 3. D3 stopped at 180 seconds after nine completed steps, so it is diagnostic evidence, not a corrected-run success. The source endpoint passes the existing store under both volume-bound settings. Adding the recorded later non-air source creates a virtual donor that fails the strict mass lower bound before air transport; its continuous volume upper margin is also negative. That distinguishes the endpoint contract from the later donor state and shows that endpoint option alignment alone was not a repair.

## Existing graupel recovery scope

The existing T10/RK3 control flow probes a failed graupel pair with the graupel-only certifier. It clears pair 4 from the failed-pair mask only when that existing certification succeeds. Source-first cloud fallback is then allowed only if no graupel pairs remain failed. D3's T10/RK3 source-first execution and lack of a `PROBE_GRAUPEL_REJECT` record are consistent with the G-only probe clearing pair 4. This is control-flow evidence for the already existing recovery; it is not evidence for a new graupel correction. The earlier C7 transport record likewise reports `SOURCE_FIRST_PAIR_FALLBACK T F F F`.

## C12 runtime evidence to retain

C12 changes source-stage evaluation, so do not claim byte identity against the C7 prefix. For each paired C12 run, retain its preflight and closed receipt with run ID, command, executable/build/source/input hashes, start/end time, return code, completed timestep/seconds, and first fatal location. Keep the compressed exact failure capture with raw and compressed hashes, byte counts, and row counts; retain the source-diffusion and transport-budget ledgers if modest, otherwise preserve their path/hash/size and a filtered T10/RK3 excerpt including pair 1/pair 4 status, fallback flags, and signed per-pair diffusion ledger. Keep the fatal stdout tail and a compact run summary. Avoid copying full domain stage traces; record their path, size, and hash instead.

If a later 600-second run extends the same C12 executable used for a completed 240-second run, a bounded prefix comparison between those C12 runs can be reported through the shared 240-second boundary. That is distinct from comparison to C7 or D3. Source validation and a short C12 runtime do not establish 600-second completion or boundary-flux closure.
