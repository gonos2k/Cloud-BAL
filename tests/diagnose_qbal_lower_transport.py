#!/usr/bin/env python3
"""Conditional 10 m lower strips and a retrospective Simpson transport budget."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from netCDF4 import Dataset
from diagnose_qbal_boundary import read_snapshot
from diagnose_qbal_sloping_faces import field, nav, sha, triangular_mesh, validate_product_time


def samples(nc, name, units):
    """Preserve missing values; below-ground height values are not observations."""
    var = nc[name]
    allowed = (units,) if isinstance(units,str) else units
    if var.units.replace(" ", "") not in [unit.replace(" ", "") for unit in allowed]:
        raise ValueError(f"{name}: units mismatch")
    value = np.asarray(var[:], dtype=float).squeeze()
    valid = np.isfinite(value)
    for attribute in ("_FillValue", "missing_value"):
        if attribute in var.ncattrs():
            valid &= value != var.getncattr(attribute)
    if "valid_range" in var.ncattrs():
        lo, hi = var.valid_range
        valid &= (value >= lo) & (value <= hi)
    return np.where(valid, value, np.nan)


def finite_percentiles(values):
    """Report unsupported diagnostics as null, never as a zero defect."""
    valid = np.asarray(values)[np.isfinite(values)]
    return np.percentile(valid,[0,1,50,99,100]).tolist() if valid.size else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "static", "frame-evidence", "output-dir"):
        parser.add_argument("--"+name, type=Path, required=True)
    for name in ("lsx", "lt1", "lw3"):
        parser.add_argument("--"+name, type=Path, nargs=3, required=True)
    parser.add_argument("--epoch", type=int, required=True)
    parser.add_argument("--interval-seconds", type=int, required=True)
    parser.add_argument("--radius-m", type=float, required=True)
    parser.add_argument("--retrospective", action="store_true", required=True)
    parser.add_argument("--height-model", choices=["log-pressure-static-avg", "constant-surface-thermodynamics"], required=True)
    parser.add_argument("--lq3", type=Path, nargs=3)
    parser.add_argument("--cap-audit", action="store_true")
    parser.add_argument("--lower-model", choices=["linear-normalized-pressure"], required=True)
    parser.add_argument("--top-source", choices=["lw3-derived"], required=True)
    args = parser.parse_args()
    if args.interval_seconds <= 0 or not np.isfinite(args.radius_m) or not 0 < args.radius_m <= 1e8:
        raise ValueError("invalid time interval or radius")
    thermodynamic = args.height_model == "constant-surface-thermodynamics"
    if thermodynamic != (args.lq3 is not None):
        parser.error("--lq3 is required only with constant-surface-thermodynamics")
    if args.cap_audit and not thermodynamic:
        parser.error("--cap-audit requires constant-surface-thermodynamics")
    products = ("lsx", "lt1", "lw3") + (("lq3",) if thermodynamic else ())
    paths = {name: getattr(args, name).resolve() for name in ("snapshot", "static", "frame_evidence")}
    for name in products:
        for j, path in enumerate(getattr(args, name)):
            paths[f"{name}_{j}"] = path.resolve()
    pins = {name: sha(path) for name, path in paths.items()}
    evidence = paths["frame_evidence"].read_text().lower().replace(" ", "")
    if any(f"parameter({flag}=.true.)" not in evidence
           for flag in ("l_grid_north", "l_grid_north_anal", "l_grid_north_out")):
        raise ValueError("grid-north source contract required")
    with Dataset(paths["static"]) as nc:
        nc.set_auto_maskandscale(False)
        lat, lon, terrain = (field(nc, key) for key in ("lat", "lon", "avg"))
        navigation = nav(nc)
        if nc["avg"].units != "meters MSL":
            raise ValueError("terrain height units mismatch")
    times = [args.epoch-args.interval_seconds, args.epoch, args.epoch+args.interval_seconds]
    ps, height, u, v, us, vs, omega, temperature = ([] for _ in range(8))
    mixing, profile_temperature, specific = [], [], []
    pressure = None
    for j, epoch in enumerate(times):
        for product in products:
            with Dataset(paths[f"{product}_{j}"]) as nc:
                nc.set_auto_maskandscale(False)
                validate_product_time(nc, epoch, product)
                if nav(nc) != navigation:
                    raise ValueError(f"{product}: navigation mismatch")
                if product == "lsx":
                    for key, units, output in (("ps", "pascals", ps), ("u", "meters / second", us),
                                               ("v", "meters / second", vs), ("t", "degrees kelvin", temperature)):
                        value = samples(nc, key, units)
                        if value.shape != terrain.shape or not np.isfinite(value).all():
                            raise ValueError(f"invalid LSX {key}")
                        if thermodynamic and key=="t" and (np.any(value<150) or np.any(value>350)):
                            raise ValueError("LSX temperature outside canonical EOS range")
                        if thermodynamic and key=="ps" and (np.any(value<100) or np.any(value>120000)):
                            raise ValueError("LSX pressure outside canonical EOS range")
                        output.append(value)
                    if thermodynamic:
                        # Producer MR is g vapor/kg dry air; the file misspells kilogram.
                        value = samples(nc,"mr",("grams/kikogram","grams/kilogram"))/1000
                        if (value.shape != terrain.shape or not np.isfinite(value).all()
                                or np.any(value<0) or np.any(value>float(np.float32(.2)))):
                            raise ValueError("invalid LSX mixing ratio")
                        mixing.append(value)
                else:
                    if nc["level"].units != "hectopascals":
                        raise ValueError("pressure units mismatch")
                    levels = np.asarray(nc["level"][:], dtype=float)[::-1]*100
                    if not np.isfinite(levels).all() or np.any(levels <= 0) or np.any(np.diff(levels) >= 0):
                        raise ValueError("invalid pressure levels")
                    if pressure is None:
                        pressure = levels
                    if not np.array_equal(pressure, levels):
                        raise ValueError("pressure grids differ")
                    if product == "lt1":
                        keys = [("ht","meters",height)]
                        if thermodynamic:
                            keys.append(("t3","degrees Kelvin",profile_temperature))
                    elif product == "lw3":
                        keys = [("u3","meters / second",u),("v3","meters / second",v)]
                    else:
                        keys = [("sh","kg/kg",specific)]
                    for key, units, output in keys:
                        value = samples(nc, key, units)[::-1]
                        if value.shape != (len(pressure), *terrain.shape):
                            raise ValueError(f"{key}: shape mismatch")
                        if product == "lw3" and not np.isfinite(value).all():
                            raise ValueError("invalid wind profile")
                        output.append(value)
                    if product == "lw3":
                        value = samples(nc, "om", "pascals / second")
                        if value.shape != (len(pressure), *terrain.shape) or not np.isfinite(value[0]).all():
                            raise ValueError("conditional top requires finite LW3 samples")
                        omega.append(value[0])
    snapshot = read_snapshot(paths["snapshot"])
    if not np.array_equal(ps[1].T, snapshot.ps) or not np.array_equal(pressure, snapshot.p):
        raise ValueError("central pressure geometry differs from pinned case")
    ny, nx = terrain.shape
    if lat.shape != terrain.shape or lon.shape != terrain.shape:
        raise ValueError("static shapes differ")
    _, triangles, edges, incidence = triangular_mesh(nx, ny)
    phi1, phi2 = [np.deg2rad(navigation[key][0]) for key in ("Latin1", "Latin2")]
    if not 0 < phi1 < phi2 < np.pi/2:
        raise ValueError("unsupported secant projection")
    cone = np.log(np.cos(phi1)/np.cos(phi2))/np.log(np.tan(np.pi/4+phi2/2)/np.tan(np.pi/4+phi1/2))
    orientation = np.deg2rad(navigation["LoV"][0])
    parameters = [np.deg2rad(38.), orientation, args.radius_m, cone, orientation]
    nn, nz, nt, ne = nx*ny, len(pressure), len(triangles), len(edges)
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=False)
    with (out/"prepared.bin").open("wb") as stream:
        stream.write(np.array([nn, nz, nt, ne], dtype="<i4").tobytes())
        stream.write(np.array(times, dtype="<i8").tobytes())
        for value in (parameters, np.deg2rad(lat), np.deg2rad(lon), terrain, pressure, ps,
                      np.asarray(height).reshape(3,nz,nn).transpose(0,2,1),
                      np.asarray(u).reshape(3,nz,nn).transpose(0,2,1),
                      np.asarray(v).reshape(3,nz,nn).transpose(0,2,1), us, vs, omega):
            stream.write(np.asarray(value, dtype="<f8").tobytes())
        for value in (triangles+1, edges+1, incidence):
            stream.write(np.asarray(value, dtype="<i4").tobytes())
        if thermodynamic:
            specific_array = np.asarray(specific)
            if np.any((specific_array[np.isfinite(specific_array)] < 0) | (specific_array[np.isfinite(specific_array)] >= 1)):
                raise ValueError("specific humidity must be in [0,1)")
            profile_mixing = specific_array/(1-specific_array)
            for value in (temperature,mixing,
                          np.asarray(profile_temperature).reshape(3,nz,nn).transpose(0,2,1),
                          profile_mixing.reshape(3,nz,nn).transpose(0,2,1)):
                stream.write(np.asarray(value,dtype="<f8").tobytes())
    repo = Path(__file__).resolve().parents[1]
    sources = ["../src/common/cloud_bal_state.f90", "qbal_surface_thermo.f90", "qbal_physical_boundary.f90", "qbal_pressure_flux.f90", "qbal_sloping_geometry.f90",
               "qbal_column_budget.f90", "qbal_lower_transport.f90", "qbal_domain_flux.f90", "diagnose_qbal_lower_transport.f90"]
    source_pins = {s:sha(repo/"tests"/s) for s in sources}
    script = out/"run.sh"
    script.write_text('''#!/usr/bin/env bash
set -euo pipefail
repo=$1
out=$2
mode=$3
audit=$4
. "$repo/tests/intel_toolchain.sh"
for level in O0 O2; do
 mkdir "$out/$level"
 if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 (
 cd "$out/$level"
 "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian "${@:5}" -o diagnose
 ./diagnose "$out/prepared.bin" result.bin "$mode" "$audit"
 )
done
''')
    with (out/"intel.log").open("w") as log:
        subprocess.run(["bash",str(script),str(repo),str(out),"surface-thermo" if thermodynamic else "","cap-audit" if args.cap_audit else ""]+[str(repo/"tests"/s) for s in sources],
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    if any(sha(repo/"tests"/s) != source_pins[s] for s in sources):
        raise ValueError("source changed during compilation/replay")
    counts = [2*nn,3*nn,3*ne,3*ne,3*ne,nt,nt,nt,nt,3*nt,nt,nt]
    names = ["xy","p10","covered","lower","missing","area","surface","volume_rate","bound","top","known","residual"]
    results = []
    for level in ("O0", "O2"):
        with (out/level/"result.bin").open("rb") as stream:
            raw = np.fromfile(stream,dtype="<f8",count=sum(counts))
            mapped = np.fromfile(stream,dtype="<i4",count=3*nn).reshape(3,nn)
            domain = np.fromfile(stream,dtype="<f8",count=2)
            unknown_counts = np.fromfile(stream,dtype="<i4",count=2)
            thermo = np.fromfile(stream,dtype="<f8",count=15*nn).reshape(3,nn,5) if thermodynamic else None
            defects = np.fromfile(stream,dtype="<f8",count=3*nn*(nz-1)).reshape(3,nn,nz-1) if thermodynamic else None
            cap_data = np.fromfile(stream,dtype="<f8",count=15*ne).reshape(3,ne,5) if args.cap_audit else None
            if stream.read(1) or len(domain)!=2 or len(unknown_counts)!=2:
                raise ValueError("invalid domain output extent")
        if raw.size != sum(counts) or not np.isin(mapped,[0,1]).all():
            raise ValueError("invalid driver extent/state")
        arrays = dict(zip(names,np.split(raw,np.cumsum(counts)[:-1])))
        arrays["mapped"] = mapped
        arrays["domain"] = domain
        arrays["unknown_counts"] = unknown_counts
        if thermodynamic:
            arrays["thermo"] = thermo
            arrays["layer_defect"] = defects
        if args.cap_audit:
            arrays["cap_audit"] = cap_data
        for key, width in (("p10",nn),("covered",ne),("lower",ne),("missing",ne),("top",nt)):
            arrays[key] = arrays[key].reshape(3,width)
        arrays["xy"] = arrays["xy"].reshape(nn,2)
        if not np.isnan(arrays["residual"]).all():
            raise ValueError("sub-10m transport must remain unknown")
        if np.any(np.abs(arrays["surface"]-arrays["volume_rate"])>arrays["bound"]):
            raise ValueError("surface volume identity failed")
        results.append(arrays)
    ref, other = results
    for name in names:
        if not np.array_equal(np.isfinite(ref[name]),np.isfinite(other[name])):
            raise ValueError(f"{name}: optimization support differs")
    # Arithmetic comparison uses the pre-cancellation physical operands.
    speed = max(np.max(np.abs(u)),np.max(np.abs(v)),np.max(np.abs(us)),np.max(np.abs(vs)))
    edge_size = np.abs(ref["xy"][edges[:,1]]-ref["xy"][edges[:,0]]).sum(axis=1)
    flux_scale = edge_size*max(np.max(ps),1)*max(speed,1)*4
    tolerance = 1024*np.finfo(float).eps*(nz+1)*flux_scale
    for name in ("covered","lower"):
        delta = np.abs(ref[name]-other[name]); valid = np.isfinite(delta)
        if np.any(np.where(valid,delta,0)>tolerance):
            raise ValueError(f"{name}: optimization arithmetic check failed")
    if not np.array_equal(ref["mapped"],other["mapped"]) or not np.array_equal(ref["unknown_counts"],other["unknown_counts"]):
        raise ValueError("optimization status differs")
    for name in ("xy","p10","missing","area","surface","volume_rate","bound","top"):
        scale = max(float(np.nanmax(np.abs(ref[name]))),1.)
        if not np.allclose(ref[name],other[name],rtol=0,atol=2048*np.finfo(float).eps*scale,equal_nan=True):
            raise ValueError(f"{name}: optimization arithmetic check failed")
    cell_flux_bound = tolerance[np.abs(incidence)-1].sum(axis=1)
    if np.any(np.abs(ref["known"]-other["known"])>cell_flux_bound):
        raise ValueError("known subtotal optimization difference")
    if thermodynamic:
        for name in ("thermo","layer_defect"):
            if not np.array_equal(np.isfinite(ref[name]),np.isfinite(other[name])):
                raise ValueError(f"{name}: optimization support differs")
            if not np.allclose(ref[name],other[name],rtol=1e-12,atol=1e-8,equal_nan=True):
                raise ValueError(f"{name}: optimization arithmetic difference")
    if args.cap_audit:
        if not np.array_equal(ref["cap_audit"][:,:,0],other["cap_audit"][:,:,0]):
            raise ValueError("cap index differs across optimization")
        if not np.isfinite(ref["cap_audit"]).all() or not np.isfinite(other["cap_audit"]).all():
            raise ValueError("incomplete cap audit")
        if np.any(np.abs(ref["cap_audit"][:,:,2]-other["cap_audit"][:,:,2])>3*tolerance):
            raise ValueError("cap-limit arithmetic differs across optimization")
        for column in (1,3,4):
            scale=max(float(np.max(np.abs(ref["cap_audit"][:,:,column]))),1.)
            if not np.allclose(ref["cap_audit"][:,:,column],other["cap_audit"][:,:,column],
                               rtol=0,atol=2048*np.finfo(float).eps*scale):
                raise ValueError("cap diagnostic operands differ across optimization")
    np.savez(out/"arrays.npz",**ref,triangles=triangles,edges=edges,incidence=incidence)
    signs = np.bincount(np.abs(incidence).ravel()-1,weights=np.sign(incidence).ravel(),minlength=ne)
    outer = signs != 0
    weights = np.array([1,4,1])/6
    edge_known = ref["covered"]+np.where(np.isfinite(ref["lower"]),ref["lower"],0)
    average = weights@edge_known
    ground_sum = math.fsum(ref["surface"])
    top_sum = math.fsum(weights@ref["top"])
    side_sum = math.fsum(signs[outer]*average[outer])
    domain_known = math.fsum([ground_sum,side_sum,-top_sum])
    cell_sum = math.fsum(ref["known"])
    closure_scale = math.fsum(np.abs(ref["surface"]))+math.fsum(weights@np.abs(ref["top"]))
    closure_scale += math.fsum(weights@np.abs(edge_known))*2
    arithmetic_bound = 1024*np.finfo(float).eps*closure_scale
    if not np.isnan(ref["domain"][1]) or not np.array_equal(ref["unknown_counts"],[outer.sum(),ne-outer.sum()]):
        raise ValueError("invalid unknown domain bookkeeping")
    if abs(domain_known-ref["domain"][0])>arithmetic_bound:
        raise ValueError("Fortran domain sum differs from independent sum")
    if abs(domain_known-cell_sum)>arithmetic_bound:
        raise ValueError("shared face domain/column sum mismatch")
    # Independent hypsometric diagnostic, not a calibrated physical tolerance.
    # This exposes the pressure/height anchor sensitivity rather than silently
    # approving every monotone interpolation as a physical near-surface layer.
    implied_temperature = []
    for j in range(3):
        valid = ref["mapped"][j].astype(bool)
        surface_pressure = np.asarray(ps[j]).ravel()[valid]
        sample_pressure = ref["p10"][j,valid]
        log_ratio = np.log1p((surface_pressure-sample_pressure)/sample_pressure)
        if np.any(log_ratio <= 0):
            raise ValueError("mapped positive-height pressure is not below PS")
        implied_temperature.append((9.80665*10/(287.05*log_ratio)))
    report = dict(status="CONDITIONAL_10M_STRIP / RETROSPECTIVE_SIMPSON / INCOMPLETE_COLUMN_FLUX",
                  height_mapping_physical_status="NOT_SUPPORTED_FOR_PHYSICAL_PROFILE: common-datum and near-surface thermodynamic consistency unverified",
                  implied_10m_temperature_percentiles_K=[np.percentile(x,[0,1,50,99,100]).tolist() for x in implied_temperature],
                  lsx_2m_temperature_range_K=[[float(np.min(x)),float(np.max(x))] for x in temperature],
                  times=times,triangle_count=nt,edge_count=ne,outer_edge_count=int(outer.sum()),
                  mapped_nodes=ref["mapped"].sum(axis=1).tolist(),
                  mapped_edges=np.isfinite(ref["lower"]).sum(axis=1).tolist(),
                  mapped_outer_edges=np.isfinite(ref["lower"][:,outer]).sum(axis=1).tolist(),
                  mapped_remaining_pressure_span_max_pa=[float(ref["missing"][j,np.isfinite(ref["lower"][j])].max()) for j in range(3)],
                  remaining_pressure_span_max_pa=ref["missing"].max(axis=1).tolist(),
                  lower_flux_max_m2_pa_per_s=np.nanmax(np.abs(ref["lower"]),axis=1).tolist(),
                  surface_sum=ground_sum,simpson_top_sum=top_sum,simpson_outer_known_sum=side_sum,
                  domain_known_subtotal=float(ref["domain"][0]),required_unknown_outer_sum=-domain_known,
                  domain_column_arithmetic_error=domain_known-cell_sum,arithmetic_bound=arithmetic_bound,
                  physical_domain_residual=None,physical_column_residual=None,production_authority=False,
                  time_contract="Endpoint volume secant plus Simpson 12/13/14 transport; quadrature error uncalibrated, not instantaneous",
                  model_contract="static AVG and LT1 HT treated as common height datum; log-pressure interpolation; normalized-pressure lower strip; no sub-10m model",
                  top_role="LW3 omega derived from analyzed wind, not independent observation",
                  input_paths={k:str(v) for k,v in paths.items()},input_sha256=pins,
                  source_sha256={s:sha(repo/"tests"/s) for s in sources+[Path(__file__).name,"diagnose_qbal_sloping_faces.py"]})
    if thermodynamic:
        report["status"] = "THERMODYNAMIC_10M_PRIOR / RETROSPECTIVE_SIMPSON / INCOMPLETE_COLUMN_FLUX"
        report["height_mapping_physical_status"] = "CONDITIONAL_THIN_LAYER_PRIOR: constant LSX temperature and mixing ratio, not calibrated profile authority"
        report["model_contract"] = "constant LSX T2 and dry mixing ratio over 0-10m; canonical gas EOS; original LT1 input height unchanged; its interpolated pressure retained only in thermo[...,3] for comparison"
        report["prior_virtual_temperature_percentiles_K"] = [np.percentile(x[:,0],[0,1,50,99,100]).tolist() for x in ref["thermo"]]
        report["dp_dheight_range_Pa_per_m"] = [[float(np.min(x[:,1])),float(np.max(x[:,1]))] for x in ref["thermo"]]
        report["dp_dTv_range_Pa_per_K"] = [[float(np.min(x[:,2])),float(np.max(x[:,2]))] for x in ref["thermo"]]
        report["legacy_minus_prior_pressure_percentiles_Pa"] = [finite_percentiles(ref["thermo"][j,:,3]-ref["p10"][j]) for j in range(3)]
        report["ground_defect_percentiles_m2_per_s2"] = [finite_percentiles(x[:,4]) for x in ref["thermo"]]
        report["internal_defect_percentiles_m2_per_s2"] = [finite_percentiles(x) for x in ref["layer_defect"]]
        report["ground_defect_valid_count"] = np.isfinite(ref["thermo"][:,:,4]).sum(axis=1).tolist()
        report["internal_defect_valid_count"] = np.isfinite(ref["layer_defect"]).sum(axis=(1,2)).tolist()
        report["legacy_comparison_valid_count"] = np.isfinite(ref["thermo"][:,:,3]).sum(axis=1).tolist()
        report["ground_height_status"] = "DATUM_UNVERIFIED"
        report["defect_contract"] = "g*HT minus trapezoid in log-pressure of Rd*Tv; common terrain/HT datum conditional; not a calibrated error or forced adjustment"
    report["profile_status"]="CAP_DEPENDENT_LEGACY_EXPERIMENT / NOT_AUTHORIZED_FOR_PHYSICAL_PROFILE"
    if args.cap_audit:
        audit=ref["cap_audit"]
        edge_length=np.linalg.norm(ref["xy"][edges[:,1]]-ref["xy"][edges[:,0]],axis=1)
        report["cap_index_changes_between_samples"]=(audit[1:,:,0]!=audit[:-1,:,0]).sum(axis=1).tolist()
        report["cap_limit_shift_percentiles_Pa"]=[finite_percentiles(x[:,1]) for x in audit]
        report["cap_limit_jump_per_length_percentiles_m_Pa_per_s"]=[finite_percentiles(x[:,2]/edge_length) for x in audit]
        report["cap_wind_disagreement_max_coordinate_m_per_s"]=[[float(np.nanmax(x[:,3])),float(np.nanmax(x[:,4]))] for x in audit]
        report["cap_audit_contract"]="Frozen winds; translate both p10 endpoints to current cap crossing; jump is alternative reconstruction difference, not observed time change or boundary forcing. Both cap levels are above current ground. No variance-based profile fit is applied to actual data."
    if any(sha(path)!=pins[name] for name,path in paths.items()):
        raise ValueError("input changed during replay")
    report["artifact_sha256"] = {p.name:sha(p) for p in (out/"prepared.bin",out/"arrays.npz")}
    (out/"report.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("input_paths","input_sha256","source_sha256","artifact_sha256")},indent=2))


if __name__ == "__main__":
    main()
