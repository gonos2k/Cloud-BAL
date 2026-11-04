# B1 rain-number lineage and candidate execution addendum

Recorded 2026-11-04T03:08:42Z. This addendum updates campaign status only. `lineage.md` and `lineage.json` preserve the read-only source investigation as it stood when created; their statements that no candidate input or forecast existed describe that earlier snapshot.

## Producer and zero origin

The current `ORIGINAL_B1_100` input remains `9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5`. The exact metgrid→real replay is recorded in `runtime_real/runlogs/replay_receipt.json` and `runtime_real/boundary_comparison.json`. It regenerated the expected metgrid product and reproduced the B1 `wrfinput_d01` byte-for-byte. The output contains 202,569 positive-QRAIN cells while every QNRAIN value is zero. Metgrid's actual product carries QR mass but no QNR/QNRAIN variable.

This resolves the artifact path and reproduces the zero output, but does not identify the executed real initialization routine that wrote or preserved those zeros. The retained historical `real.exe` still has no hash-indexed source/object/build receipt tying it to the nearby Thompson-only `make_RainNumber` source. `mp_physics=37` is confirmed by the effective real namelist and Registry mapping to KDM6; the nearby Thompson initializer remains a conditional source explanation only. Do not attribute the zeros to that routine as an executed-code fact.

The fresh real-stage boundary `b32cfabe2d634eb553de4b80df4e1a01b7a939feb97f8f36a176366700ac3ce3` is a one-record 12→15Z real artifact. The current six-hour forecast boundary is the distinct `74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45` with records at 12Z and 15Z covering 12→18Z. Both contain QRAIN and QNRAIN boundary arrays with observed all-zero values; no missing-variable inference was used.

## B1-specific rain-number prior and actual first-call gate

The frozen research policy is `B1_RAIN_PSD_PRIOR_POLICY_20261104.json` (SHA-256 `25387970de9685e3024af7983d47650ab6b6068188f765df58243d6ebefa7601`). It applies only to B1. It declares a rain-only geometric-center PSD prior (`mu=1`, `lambda=sqrt(961×35000)=5799.5689495 m-1`) for exact-zero initial QNRAIN where initial QRAIN exceeds the captured KDM6 `qcrmin` and the baseline first-call mask marks the cell as called. It adds no arbitrary number floor and does not relax the source bounds. The PR61/PR83 policies are not applied to this input.

The candidate input is `ad030e8bbfca319c4594dcfa5b0656b9bc387d9fcbe23372fd6ed8808aaf0f21`. Initialization receipt: `candidate/initialization.json` (SHA-256 `546eeb48f4913e67bedc277e85a5f290364a940e74c4d5db749438b8c49e8a7a`). The source-gated first-call preflight is `candidate/candidate_preflight.json` (SHA-256 `4d51c8bf0214dff43a0e1862ab25eebd1bf552f51556a5ae44d57f1657e6949b`). Its independent archive replay is `candidate/preflight_capture/preflight_replay.json`; the 56 deterministic compressed first-step streams and their raw/compressed hashes are inventoried in `candidate/preflight_capture/capture_manifest.json`.

The 20-second instrumented probe used eight ranks and a distinct probe executable (`6706f6162d37c057b2699afd03ae7c0b4dbf94fe97b925c0369916ba6c708661`). Across 2,533,440 actual called cells, raw ENTRY→PRE_UPDATE QRAIN and internal number matched the retained KDM6 nonnegative clips exactly: `QR_PRE=max(QR_ENTRY,0)` and `NR_PRE=max(float32(QNRAIN_ENTRY×DEN_ENTRY),0)`, with zero numeric and zero signed-zero mismatches. Raw ENTRY included 1,698 negative QR and 1,774 negative NR values; the captured source clips them before the PRE_UPDATE state. On the actual clamped PRE_UPDATE state, 246,132 cells passed source PSD guards (`QR>=qcrmin`, internal `NR>=nrmin`), maximum internal NR was 30,594.4629, and no called cell exceeded `nrmax`. The float32 lambda equation reconstruction had median 5,799.5684 m-1; 437 active cells were below the source lambda minimum and enter its existing lower-bound clamp. Lambda is reconstructed from captured operands, not directly captured from the local lambda variable.

The five-stage same-mask OLD/FIX quick-probe comparison is `candidate/first_call_comparison.json` and `.csv`. Entry and PRE_UPDATE QV, temperature, and QR were bitwise unchanged; NR changed at 353,452 ENTRY and 351,678 PRE_UPDATE cells. After processing, QV, temperature, QR, and NR differ from the zero-number baseline at 241,712, 199,042, 361,137, and 361,420 cells, respectively. This is a descriptive first-timestep state response, not a water-budget closure or rain-causality result.

## Candidate six-hour execution

The frozen single-case, 26-constraint evaluation plan is `candidate/evaluation_plan.json` (SHA-256 `073a2805e1ff4e184fbfb67aa1d8f61899d8decbd8c4bc0c7e701a1aa6a7d964`); its source freeze is `candidate/source_freeze.json` (SHA-256 `8a15f4c48b6f5193c79f148e5a03f4b3ccba2b040112f8536c523887f24b208e`). The candidate forecast used the noninstrumented fixed FIX executable `68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f`, the exact 12–18Z namelist `eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df`, and common boundary `74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45`. The instrumented 20-second probe executable was not used for this forecast.

Runtime receipt: `candidate/runtime_gate.json` (SHA-256 `e8e2b870a5be5f410767673929f1e6b309036b7fcc07e6c5e778810dd32f64bf`). The six-hour run exited 0; all eight rank logs reached the 18Z success marker; all seven expected hourly histories from 12Z through 18Z exist and their embedded `Times` values match their filenames. All 89 staged input hashes, including QRAIN/QNRAIN input, namelist, boundary, executable, and TBLs, match the prelaunch inventory after the run. The launcher was pinned with `taskset` and Intel MPI settings to CPUs 56–63; per-rank `/proc` affinity was not sampled, and the receipt records this limitation.

The runtime receipt establishes run completion and outputs only. Root's independent score recount against the frozen 26 CSI constraints determines admission; this addendum makes no score or candidate-selection claim.

## Remaining physical binding limit

The B1 historical `real.exe` source-to-binary binding remains unresolved. The matched-source KDM6 constants/formula support the declared PSD prior, and the candidate's observed first-call clamps and number cap pass, but the prior remains a research assumption rather than an observed particle-size calibration. Forecast output existence does not establish the candidate's frozen CSI constraints or full mass/energy closure.
