# Frozen ice operators at five B1 levels

The figure and CSV select the single target level of each declared case, not all 39 profile levels. Circles and squares report the measured post-entry and post-PSD1 ice number concentrations from the O0 frozen-state probe; the dashed line is the nominal entry cap. Color identifies the raw file number, nominal maximum-mass seed, or fixed 50 µm seed. The lower panel is the reciprocal of the measured first-slope inverse lambda, not the first PSD block's lambda. Values are also available unscaled in `target_levels.csv`; `provenance.json` records input and artifact hashes.

The experiment composes source-extracted operators with QI held fixed, uses a file-state density proxy, and sets QMIN to 1e-15. It is not a full microphysics routine, a forecast, or evidence that a particular seed is optimal. Boundary selection uses the declared nominal policy; native source constants and real32 arithmetic govern the probe.

Regenerate from the Cloud-BAL root:

```sh
python tools/plot_ice_stage_contract.py docs/evidence/ice_stage_contract_20261111/cases/profiles.json docs/evidence/ice_stage_contract_20261111/native/metadata.json docs/evidence/ice_stage_contract_20261111/native/output_O0.txt docs/evidence/ice_stage_contract_20261111/figures
```

`full_column_trace.png` instead shows the O0 full-column experiment at the maximum-IWC target level for all three seeds. Its companion `full_column_target_stages.csv` retains every normalized target-stage record, including WRAPPER and active/intermediate stages omitted from the axis. Wrapper input number is annotated because the 50 µm seed is much larger than the plotted range. Distinct horizontal offsets make coincident seed markers visible. The instrumented and unmodified column terminal outputs agree byte-for-byte; the inputs remain file-derived proxies and do not establish WRF first-use. Intervening intervals include multiple processes and cannot by themselves identify the cause of a change.

```sh
python tools/plot_ice_stage_trace.py docs/evidence/ice_stage_contract_20261111/analysis/target_stages.csv docs/evidence/ice_stage_contract_20261111/cases/profiles.json docs/evidence/ice_stage_contract_20261111/figures
```
