# PR89 final closed-window evidence review (2026-10-19)

Read-only review of the process-consumer report, cold summary, current manifest, C5 120/600-second arm receipts, 120/600 cold-summary JSON, and source-bound T7 rain-store audit. No model, source, or graph action was performed. Result: no evidence-binding or scope blocker found.

## Runtime and receipt bindings

- Process report SHA-256: `b4bf071f997741c5d8e02e92636475d34509dab8a8664d5861fb68f8a44947e3`.
- Cold summary report SHA-256: `5b911bac24ab09cf320cd51d59cb56e61af940d211c97f6b1b3e586509d722f5`.
- Manifest SHA-256: `56268041a860970f9aa9ec4d7cf4a04d982513f251df58d9151e8e77a2b8b6c6`.
- OFF/COUPLED C5 120-second receipt SHAs: `199ae0f4eeed0ea0472150ae2d056351f8939c2835096b1e05bc1f9ec122ac33` / `5989d07a9c9a4999c2d44ccc11160f597abfa46d29c92e60630651249cdecab3`.
- OFF/COUPLED C5 600-second receipt SHAs: `80b6fa75e515751cb83992301b8b32a0cb858d9c58dafb57faf682296ae90e34` / `ff3b32962d4136b0938b2b35ec3bb18632b579065b70bd383a66945f64ba579d`.
- C5 120-second / 600-second cold-summary SHAs: `af5a57bfdf3538bd072d7a191a11483a06d9da5193e31ab5891133fb68969cfb` / `837f6997313110a2b86a7a38034654255631da2c6666ac7ab536f68ba9a559dc`.
- T7 audit SHA-256: `f97dcfc283c7e443656e95d1a29036b340876661d846c6a7ed5d68605c88654f`.

The manifest’s receipt paths and hashes match the present receipt bytes. Both 120-second receipts say `COMPLETE`, return code 0, and six final completed steps. The 600-second receipts say `INCOMPLETE`, return code 128, and six completed steps, with a seventh timestep observed. Both 600-second receipts bind run identity `PR87 selected-object native candidate`, the same C5 executable SHA-256 `beb2da6745606566074e15a043d173a8be01d277f00c4cc90ad3915f5de5a2d6`, unchanged candidate build, and zero changed staged/original inputs. The manifest reports those same states and keeps `physical_approval` at `FAIL_OPEN`.

The C5 120 cold summary has 1,680 calls per arm (280 at each completed step 1–6). The 600 attempt summary has 1,901 parsed calls per arm: 1,680 from completed steps and 221/280 at partial step 7, leaving 59 call rows absent per arm. Both docs distinguish the completed prefix from the partial timestep and do not claim a completed 600-second run.

## Units and claim limits

The cold JSON and report consistently label the weighted metric `kg m-2 SUM_COLUMNS`, derived using actual same-call `DEN*DELZ` weights. The collector has no horizontal area, so the tables are not grid-area/global kilograms. They describe same-call proposed/applied/deferred group-vector water activity; zero raw cell rows remain explicit, and the measure is not individual reaction throughput or a closed water/energy budget.

The T7 audit binds an OFF-run source/build path and states that the diagnostic prints rounded values rather than exact operand bits. Its ledger omits the rejected cell because rows are written after valid storage, so it does not establish which exact predicate failed or a confirmed PSD cause. Both arm receipts carry the same generic fatal label, but the docs correctly keep cause attribution open. Observation fit, mass-wind/face-flux closure, energy closure, and initial-shock reduction remain unverified/open.

One wording nuance for later cleanup: the process report says the 600-second runs use the “same C5 executable and inputs.” The receipts confirm the same executable and identical arm-specific initial-state, boundary, and source-receipt hashes across 120/600 requests, while the candidate namelist hash changes from `dee430a6…` at 120 seconds to `afc366ae…` at 600 seconds for the intended runtime/end-time/history-interval edits. Clarifying “same scientific inputs with the duration-specific namelist” would make that binding precise. This does not alter the result or invalidate the receipt chain.
