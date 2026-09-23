# Same-case cloud moisture attribution

Base: PR #43, `5f51fbbcec8d7908ce4e91f9d59394927348a917`.
Status: `PASS_SCOPED / CLOUD_SWITCH_CAUSAL_REPLAY` for the late humidity
cloud-moistening block in the retained 13 UTC case.

The PR43 local force maximum includes a sharp final-minus-generation-stage
moisture structure at `(i,j)=(55,162)`. The stage field is the retained FUA
specific humidity used before the humidity producer; the final field is
retained LQ3. Their difference spans several producer steps. Cloud coverage
alone did not identify which step caused it.

## Controlled producer replay

We rebuilt the current humidity target at pinned Intel O0 and O2 with
`tools/build_upstream_producer.sh` in fresh scratch. At each optimization,
two fresh copies of the matching PR43 actual13 runroot received the same
retained LC3 product, SHA-256
`03335747f5236a8f5cdc4003106e5cea210e8b389f2e5e1275d540f6d70dfec9`.
Both LQ3 output paths were empty before execution. Each run had 74 paired
input files: 73 non-switch inputs matched byte-for-byte, and the sole change
was `CLOUD_SWITCH=1` versus `0` in the copied
`moisture_switch.nl`. LQ3/LH3/LH4 are generated outputs, and previous replay
logs are not producer inputs; they are excluded from the input comparison.
Each run used its own runroot, short `LAPS_DATA_ROOT`
symlink and temporary directory. The verified launcher checked pinned build
and runtime files before execution.

The ON runs both produced an LQ3 file **byte-identical** to the retained 13 UTC LQ3
(SHA-256 `30f88ef53fa19a7db892be0c2ccda5fa2fb77a127eaefbc9ad23192443854df2`).
Both OFF runs produced the same distinct LQ3 (SHA-256
`19295cfe180d4eeadfa599e9712fbe968d8411618c36e68e2c585d6038f19bb2`).
The source consults `CLOUD_SWITCH` after
the variational step, before `cloud_sat`; supersaturation QC follows. Thus
ON–OFF measures the **net effect of that late cloud block including its QC
consequence**, with earlier humidity processing held fixed. It does not by
itself isolate the raw `cloud_sat` call from subsequent clipping.

At the target node, pressure is matched through the file's actual `level`
coordinate. The selected values are in g/kg of specific humidity:

| Pressure | Stage FUA | Cloud OFF | Cloud ON = retained LQ3 | ON−OFF |
|---:|---:|---:|---:|---:|
| 1000 hPa | 17.369572 | 18.127620 | 18.127620 | 0 |
| 950 hPa | 17.011032 | 17.569326 | 17.569326 | 0 |
| 900 hPa | 13.808614 | 14.888365 | 14.888365 | 0 |
| 850 hPa | 10.138989 | 10.138989 | 12.502538 | +2.363549 |
| 650 hPa | 3.766327 | 3.766327 | 7.066789 | +3.300462 |
| 600 hPa | 2.416432 | 2.416432 | 6.712755 | +4.296323 |
| 550 hPa | 2.211258 | 2.211258 | 5.059912 | +2.848654 |
| 500 hPa | 2.784371 | 2.784371 | 3.699053 | +0.914682 |

The omitted 800, 750 and 700 hPa rows also have positive ON–OFF changes,
recorded individually in `comparison.json`. At 850–500 hPa, OFF equals stage
at this node, so the entire final-minus-stage change there is attributable to
the net late cloud block in this controlled replay. At 1000–900 hPa, the
nonzero stage-to-final changes remain in the earlier humidity analysis path;
the late cloud block changes none of those three rows. Across the domain,
16,807 valid node-level values change between ON and OFF, with no negative
ON–OFF values. That count does not
mean all changes are validated observations or an authorized moisture update.

Using retained FUA HT and the LC3 height coordinate in the legacy mapping,
the target pressure-grid cloud fraction is 1 at 950–450 hPa. At 1000 hPa it
is about 0.443, below `cloud_sat`'s 0.6 threshold. Cloud coverage can permit
moistening, while the actual `qadjust` and final clipping determine its size.
The replayed output difference is stronger evidence for the final effect than
cloud fraction alone.

The validator `tests/diagnose_qbal_cloud_switch.py` checks copied inputs,
LC3 and retained LQ3 hashes, valid time, pressure order, support, navigation,
producer success logs and the current build receipt. It keeps stage, OFF, ON,
cloud effect and other-analysis change separate at the selected node.
`tests/test_qbal_cloud_switch.py` rejects a second input change. Build/run
commands and large raw artifacts are kept under the PR44 scratch evidence
directory. The compact [O0](evidence/pr44_cloud_O0.json) and
[O2](evidence/pr44_cloud_O2.json) receipts preserve the hashes and each target
pressure row for review. The retained producer inputs and original LQ3 were
not changed.

This attribution closes the cause of the target node's **net late cloud
moistening** in the tested case. It does not judge whether the cloud mapping or
amount is meteorologically correct. It supplies no humidity-error covariance,
surface datum, wind boundary flux, complete column budget, or permission to
reduce humidity merely to shrink the relative pressure-force diagnostic.
