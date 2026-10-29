# CP02 OFF/HYDRO/LIQUID control inputs

This folder records the retained six-hour control inputs as the launch source for a new fresh-scratch replay. The historical directories are `/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/{off,hydro,liquid}/run`.

`copy_manifest.json` is the compact copy plan for a launcher: it lists each included regular file's exact source path, destination name, byte size, and SHA-256, separately for each arm. It excludes `wrfout_*`, `rsl.*`, `launcher.log`, `run.exit`, and `namelist.output`; the included 88 files per arm retain `namelist.input`, `wrfinput_d01`, `wrfbdy_d01`, `physical_history.txt`, and physics tables. The three historical namelists have the same bytes and SHA-256. Keep them as read-only source inputs and make any documented run-time change only in the fresh scratch copy.

`selected_initial_fields.csv` records 624 selected input values per arm for P01, P05, P09, and P13: each point's four mapped native WRF mass-grid corners at all 39 model levels. The sampled fields include the six hydrometeor and vapor mixing ratios, CCN/cloud/ice/rain number-concentration fields, and QIB. `copy_manifest.json` binds `wrfinput_d01`, `wrfbdy_d01`, and the retained 12Z history file per arm, including SHA-256, byte size, NetCDF dimensions, and every variable's dimensions, shape, dtype, and units. It also records the sampled input fields' NetCDF metadata. The history file is provenance and source-state context, not a launch input. These are initial-input values; they do not establish the exact arrays consumed at the first physics call.

`provenance.json` binds the historical `RUNNING.json`, each arm's `PREPARE.json` and `run.sh`, and the original `wrf.exe` path and SHA-256. The executable matches the historical receipt (`de110a7f…c168`) and has no DWARF debug sections. Source filenames and argument labels therefore remain candidates; the receipts do not establish exact compiled-source identity.

`source_verification.json` records a successful before/after check of size, modification time, permissions, and SHA-256 across the input inventories, receipts, executable, boundary and history files, and mapping source. The extraction did not modify those sources. The selected-point mapping is hash-bound in `copy_manifest.json`.

Regenerate with `python3 extract_inputs.py` from the maintained evidence checkout. The script reads only the bound source paths and writes evidence to this folder. No model launch or Fortran build is part of this extraction.
