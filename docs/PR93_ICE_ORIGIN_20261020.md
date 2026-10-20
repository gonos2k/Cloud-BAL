# PR93 active ice origin investigation

## Scope and classification

The exact C18 public stage trace records T24 `PRE_KDM6` at `(i,j,k)=(230,247,20)` in both OFF and COUPLED arms as `QI=3616C0A1`, public `NI=448C5DCB`, and dry density `DEN=3F0938B8`. The pinned KDM6 conversion `specific_number_to_volume(NI,DEN,...)` produces internal `NI=44167A96` (`601.9154053`). Using the freezing helper's REAL64 expression, `REAL(DEN,R64)*REAL(QI,R64)/REAL(NI_internal,R64)`, the PRE_KDM6 mean is `2.000467184384699e-9 kg`, within the configured active ice interval. The public number field is per dry mass; the internal KDM6 number is per volume.

The bounded [trace provenance record](evidence/pr93_ice_origin_20261020/trace_provenance.json) binds each arm's C18 receipt SHA256, receipt-listed compressed trace SHA256, and decompressed payload SHA256. It retains only T23 POST_KDM6 and T24 PRE_RK, RK1, RK2, RK3, and PRE_KDM6 for the target cell. OFF and COUPLED records agree bit-for-bit at those stages. The reader is [pr93_ice_origin_trace.py](../tools/pr93_ice_origin_trace.py); it checks both trace hashes against the preserved C18 receipt while streaming the source gzip.

The final T24 `PINU` failure row is an internal KDM6 freezing-helper input, not a public PRE_KDM6 snapshot. Its active ice input is `QI=3623A538`, internal `NI=441BBBE7`, and `DEN=3F0938B8`. The same source helper expression gives mean mass `2.0982771175135736e-9 kg`, above the source maximum `2.0982747187893314e-9 kg` and its existing 8 REAL32 ULP allowance. This establishes that KDM6 presents an invalid active-ice base to the freezing helper; it does not identify the first operation that wrote the state.

## Confirmed boundary-guard behavior

The selected C18 KDM6 source is `/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F` (SHA256 `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`). At its ice PSD checks for stages 1, 2, and 3, the source computes the REAL32 slope using `exp(log((pidni*nci)/(dry_carrier_density*qci))*(1./dmi))` and repairs only when the result is `<= lamdaimin` or `>= lamdaimax`.

The exact REAL32 source expression at the failing PINU bits yields `lambda=9080.0009765625` (`460DE001`), while `lamdaimin=9080`. The lower-bound branch therefore skips. This is a confirmed source-form boundary skip at the captured failing state. It does not prove the earlier KDM6 operation that first made the ice state invalid.

The local replay applies the source-bound check to the captured state, passes an invalid endpoint through the existing `pr85_kdm6_psd_bound_number` helper, and then calls the unchanged `pr85_kdm6_freezing_packet` helper. The directed number becomes `622.93670654296875` (`441BBBF3`), giving a source mean of `2.0982746504506367e-9 kg`, inside the helper's allowed cone. The freezing helper returns `base_valid=T, accepted=F`: the state is valid and the captured tiny packet is normally deferred. O0 and O2 outputs match in [O0.log](evidence/pr93_ice_origin_20261020/O0.log) and [O2.log](evidence/pr93_ice_origin_20261020/O2.log).

The replay runs the same captured state through the three structurally equivalent slope guards; after the stage1 correction the source-bound check passes stages 2 and 3. It is a focused guard replay, not a replay of intervening physical tendencies or the full model call.

## Evidence limits

The saved `pr85_ice_sedimentation_budget` is guarded to the first KDM6 call and contains no T24 pre/post operator state at this coordinate. The preserved C18 traces therefore do not expose the first internal write that moved the state from valid PRE_KDM6 to invalid PINU. Earlier internal sedimentation or microphysics attribution remains pending a targeted stage capture. No tolerance change, public NI coordinate change, or shared KDM6 edit is included here.

The maintained Cloud-BAL Graphify snapshot has no node for the externally selected C18 `module_mp_kdm6.F`; source inspection and exact local replay are authoritative for this result.

## Reproduction

From the Cloud-BAL directory, run:

```bash
python3 tools/pr93_ice_origin.py
```

The tool compiles the checked-in replay and the unchanged PSD-bound and freezing helpers with the pinned `tests/intel_toolchain.sh` profile in fresh `/var/tmp` scratch directories for O0 and O2. It does not compile or run the full model.
