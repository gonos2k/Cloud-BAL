# CP02 RN1 representativeness and provenance audit

This note covers the retained CP02 RN1 reference files for valid times 2026-08-16 13:00 through 18:00 UTC. It audits artifact identity and what the producer contract can establish about upstream provenance and coverage. It does not replay raw-data scoring or rerun the model.

## Artifact identity

The six canonical files are present at `/NHNHOME/DATA/yhlee_data/ODAM/20260816/`. Their byte lengths, SHA-256 values, and UTC/LST headers match the canonical inventory retained with the earlier six-hour work. Each file contains 37,697 values, corresponding to the complete 149 by 253 output crop, all finite, and has no negative values. Exact per-hour details and the host paths are recorded in [the read-only audit receipt](evidence/precip_transitions_20261027/rn1_contract/host_file_audit.json).

These checks establish the identity and serialized dimensions of the files now available. They do not identify the executable or all runtime inputs used when the files were produced.

## Per-hour upstream rain input remains unresolved

The wrapper source in `ANAL/NE57/SHEL/klps_lc05_dfsd_odam.csh` takes the analysis time from `anal.tim`. It selects `anal_rain_${ANLTIM}00.gdat` when present, or links the previous-hour `anal_rain_${P01TIM}00.gdat` to the current-time filename otherwise. Therefore, the RN1 output filename and its UTC/LST header alone cannot prove the timestamp of its rain-analysis input.

The wrapper constructs the same-hour and previous-hour `anal_rain` candidates under `${KL05DAOU}/DFSD/`, reads `${KL05LOGO}/anal.tim`, and writes per-hour logs beneath `${KL05LOGO}/${ANLTIM}/`. The current `kl05_src` environment utility was not found in the checked utility paths, so those variables cannot be fully resolved from this checkout. The concrete day directory `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816` exists and contains eight `klps_lc05_anal` files, but has no RN1 outputs and none of the six same-hour or six previous-hour rain candidates. Checked `/ANAL/NE57/DAIO/LOGO` and `/ANAL/NE57/LOGO` roots are absent. Header/member-name listings (no extraction) of `/NHNHOME/DATA/yhlee_data/ANAL.KL05.tar`, `ANAL.20260831.tar`, `ODAM/dfsd.tar`, and `ODAM/dfsd_new.tar` found retained RN1 copies in the latter, but no matching rain-input/control/log members. The `ANAL.KL05.tar` listing did not retain the tar process status separately, so its empty filtered output is not proof of a complete archive search. The 122 GB `ANAL_MODL.tar` and other runtime/archive trees were not searched. Exact paths, sizes, checked patterns, and outcomes are recorded in the receipt and replay output. Therefore execution-time same-hour-versus-previous-hour fallback status remains unresolved for **each** of 13–18 UTC; absence in these checked locations does not prove which input was used. No inference is made from RN1 values or timestamps.

## What RN1 represents, and what coverage cannot be claimed

The pinned producer source writes RN1 on a 149 by 253 crop. Its RAIN input is a 1-km analysis; each RN1 output point uses the maximum over a 5 by 5 neighborhood of those 1-km cells, followed by cloud/mask suppression and AWS and priority-station overrides. The 5 by 5 operation is over 1-km input cells. It must not be interpreted as a 5 by 5 neighborhood of 5-km cells.

RN1 is a processed analysis that includes radar, LNG radar, and AWS contributions; it is not raw gauge truth independent of those inputs. The text product has no explicit missing-value or sensor-coverage bitmap. Complete finite serialization (37,697/37,697) establishes that the output grid is populated numerically, not that radar or gauge observations covered every location. Likewise, the fixed 3,688-point South Korea land mask is a geographic scoring eligibility mask, not an observation-coverage or quality mask. Zeros cannot be assumed to mean observed dry conditions.

The locally available producer source at `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/dfsd/ODAM/klps_lc05_dfsd_odam.f` hashes to `f0088086ee3db6fe7ef7aa8faa2e9d4bc9fedd282f9c3b67fdd56bf9f5ecce16`, matching the earlier source pin. The producer pins, time interpretation, output layout, and limitations are detailed in `docs/evidence/precip_hourly_20261027/rn1_recovery/source_findings.md`. This verifies the current source file against the pin, not the historical executable, per-hour rain-input timestamps, or accumulation-start boundary. Preserve the product's valid-time labeling without making stronger interval claims until an upstream unit/time contract is available.

## Consequence for CP02 claims

The six canonical RN1 files are suitable as identified archived reference artifacts for the retained comparison. Any statement about their per-hour upstream freshness, sensor coverage, or independent observational skill exceeds available evidence. The prior limitation that the 3,688-point mask is geographic and that RN1 is a processed radar/AWS analysis remains in force. This audit adds no raw-RN1 replay and no new model result.
