# Grouped forecast figures

This offline bundle contains one computational/meteo schematic, six threshold-specific CSI panels, and six hourly RN1 maps. Each map plots only the 3,688 paired RN1 coordinates; no spatial interpolation is applied. The left panel of each CSI figure shows the five case scores; the right panel shows C-A, D-B and joint contrast D-A. Maps use shared boundary bins for rainfall and a symmetric logarithmic color scale for differences. Source validation: `sealed_analysis_recount; rawhistorynotreopened`; raw histories are not reopened during plotting.

Coastline overlay: [Natural Earth 1:50m coastline](https://github.com/nvkelso/natural-earth-vector), commit `ca96624a56bd078437bca8184e78163e5039ad19`; public-domain terms at [Natural Earth terms](https://www.naturalearthdata.com/about/terms-of-use/).

- [Full lead × threshold score tables](full_score_tables.md)
- [Offline figure gallery](index.html)
- `figures.zip` contains this README, score tables, gallery, manifest, source coastline, font, and all PNGs.
- `render_receipt.json` is beside the ZIP and pins its hash.
