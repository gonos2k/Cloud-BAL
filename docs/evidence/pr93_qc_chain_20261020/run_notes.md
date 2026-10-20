Metgrid reproduction: fresh work directory `/var/tmp/pr93_metgrid_same13_replay_20261020`; copied PR83 `_b` WPS inputs, geogrid, executable, and namelist; copied pinned `METGRID.TBL`; changed only the scratch namelist table path to `./`; sourced `tests/intel_toolchain.sh`; ran `./metgrid.exe`. Output SHA-256 exactly matched PR83 actual met_em.

Horizontal replay: fresh working directory `/var/tmp/pr93_horizontal_qc_replay_20261020`; extracted the exact PR83 LAPS QC records using the preserved v5 Fortran extractor; freshly compiled preserved WPS `module_map_utils.F`, `llxy_module.F`, and `interp_module.F` with pinned ifx O2 flags; ran the preserved `grid_rows_288.f90` operator against PR83 met_em QC. Result: 288/288 bitwise matches. Repeated the operator with QC extracted from the PR83 KLBG input as a source contrast: 22/288 matches.

Vertical composition: `tools/pr92_qc_vertical_support.py` read the reproduced exact PR83 met_em and actual PR83 wrfinput plus the regenerated WPS link rows. Its summary is in `qc_vertical_composition.json`. The previously completed source-form Intel O0/O2 probe is bound to those same input hashes and has 624/624 initialized-QCLOUD bit matches.

The source inputs were copied into fresh scratch before metgrid; archived paths remain read-only. No real.exe or native model rerun was made.
