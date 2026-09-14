#!/usr/bin/env python3
"""Static and content checks for the isolated radar remap consumer."""

from __future__ import annotations

import argparse
from pathlib import Path

import netCDF4
import numpy as np


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "src/upstream/radar/remap"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_source_contract() -> None:
    tilt_reader = (SOURCE / "get_tilt_netcdf.f").read_text()
    remap = (SOURCE / "remap.f").read_text()
    netcdfio = (SOURCE / "netcdfio.f").read_text()
    process = (SOURCE / "remap_process.f").read_text()
    scan = (SOURCE / "get_scandata.f").read_text()
    lut = (SOURCE / "lut_gen.f").read_text()
    geometry = (SOURCE / "remap_geometry.cmn").read_text()
    common = (SOURCE / "netcdfio_radar_common.inc").read_text()
    cdl = (SOURCE / "cdl/v00.cdl").read_text()
    runner = (REPO / "tests/run_radar_remap.py").read_text()

    require(",nyquist" in netcdfio and "get_tilt_netcdf_data" in netcdfio,
            "radar_init must pass the common nyquist variable")
    require("get_nyquist = nyquist" in netcdfio,
            "get_nyquist must return the common nyquist variable")
    require("get_nyquist = r_nyquist" not in netcdfio,
            "unbound r_nyquist must not remain in the consumer")
    require(",numGatesV" in netcdfio and ",numGatesZ" in netcdfio,
            "radar_init must pass metadata gate counts into the consumer state")
    require(",numGatesZ" in common and ",numGatesV" in common,
            "metadata gate counts must be shared with data-field readers")
    require("Short counts are valid" in remap and
            "if(i .gt. numGatesZ) data(i) = b_missing_data" in netcdfio and
            "if(i .gt. numGatesV) data(i) = b_missing_data" in netcdfio,
            "short metadata counts must mask padded bins in normalized buffers")
    require("Invalid radar metadata shape/counts" in tilt_reader and
            "Invalid radial metadata at ray" in tilt_reader,
            "invalid counts and radial bounds must return failed status")
    require("real V( V_bin, radial), Z( Z_bin, radial)" in tilt_reader,
            "NetCDF V and Z buffers must be real at the read boundary")
    require("NF_GET_VAR_TEXT(nf_fid,nf_vid,radarName)" in tilt_reader,
            "radarName must be read into radarName")
    require("NF_GET_VAR_TEXT(nf_fid,nf_vid,siteName)" in tilt_reader,
            "siteName must be read into siteName")
    require("integer get_number_of_gates" in remap,
            "integer function declaration must match its implementation")
    require("save v_nyquist_tilt" in process,
            "per-tilt Nyquist values must survive repeated calls")
    require("v_nyquist_tilt = r_missing_data" in process,
            "per-volume Nyquist state must be initialized")
    require("Invalid Nyquist velocity; tilt rejected" in process,
            "invalid Nyquist values must be rejected before folding")
    require("n_rays .gt. max_rays" in scan and "n_gates .gt. MAX_REF_GATES" in scan,
            "scan dimensions must be bounded before caller-array indexing")
    require("validate_radar_schema" in tilt_reader and "Wrong type for radar variable" in tilt_reader,
            "input variables must be checked for type and shape")
    require("n_tilts" in netcdfio and "Missing expected radar tilt" in netcdfio,
            "missing or non-contiguous tilts must fail closed")
    require("nyq:valid_range" not in cdl,
            "NYQ must not advertise an invented physical range")
    require("first_gate_m + (igate_lut - 1)" in lut,
            "LUT range must use metadata first-gate origin")
    require("radar_lut_geometry." in lut and "status='replace'" in lut,
            "LUTs must be regenerated for the current geometry")
    require("if(ntimes_radar .eq. 1)" not in remap and
            remap.count("call lut_gen(") == 1,
            "the caller must regenerate LUTs for every volume")
    require("second_geometry_required" in runner and
            '"accepted": accepted' in runner,
            "receipt must fail closed when a required second-volume mutation is absent")
    require("lut_geometry_ready_cmn" in scan and "lut_first_gate_m_cmn" in geometry,
            "each tilt must match the generated LUT geometry")


def as_text(value: np.ndarray) -> str:
    return b"".join(np.asarray(value).reshape(-1).tolist()).decode("ascii", "ignore").strip()


def check_output(path: Path) -> dict[str, object]:
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_mask(False)
        require(
            {name: len(dim) for name, dim in dataset.dimensions.items()}
            == {"record": 1, "z": 22, "x": 235, "y": 283, "nav": 1, "namelen": 132},
            "unexpected output dimensions",
        )
        for name in ("ref", "vel", "nyq"):
            variable = dataset.variables[name]
            require("scale_factor" not in variable.ncattrs(), f"{name} has unexpected scale")
            require("add_offset" not in variable.ncattrs(), f"{name} has unexpected offset")
            require(variable.dimensions == ("record", "z", "y", "x"), f"{name} indexing changed")

        fill = float(dataset.variables["nyq"]._FillValue)
        values: dict[str, tuple[int, float, float]] = {}
        for name in ("ref", "vel", "nyq"):
            variable = dataset.variables[name]
            data = np.asarray(variable[:])
            valid = np.isfinite(data) & (data != float(variable._FillValue))
            require(np.all(np.isfinite(data[valid])), f"{name} contains non-finite data")
            if name == "nyq":
                require("valid_range" not in variable.ncattrs(),
                        "NYQ must not carry an invented valid_range")
                require(np.all(data[valid] > 0.0), "NYQ contains non-positive observations")
            else:
                lower, upper = map(float, variable.valid_range)
                outside = (data[valid] < lower) | (data[valid] > upper)
                if name == "ref":
                    outside &= ~np.isin(data[valid], (-101.0, -102.0))
                require(not np.any(outside), f"{name} has data outside its declared range")
            values[name] = (int(valid.sum()), float(data[valid].min()), float(data[valid].max()))

        nyq = dataset.variables["nyq"][:]
        nyq_valid = np.isfinite(nyq) & (nyq != fill)
        require(int(nyq_valid.sum()) == values["vel"][0], "NYQ and VEL coverage counts differ")
        require(np.all(nyq[nyq_valid] > 0.0), "NYQ contains non-positive observations")
        require(float(nyq[nyq_valid].max()) > 100.0, "fixture did not exercise the former range bug")
        require(np.allclose(dataset.variables["valtime"][:], dataset.variables["reftime"][:]),
                "valid and reference times differ")
        require(np.all(np.isfinite(dataset.variables["valtime"][:])), "time is not finite")
        comments = as_text(dataset.variables["vel_comment"][0, 0, :])
        require("GSN" in comments and "F" in comments,
                "velocity coverage/Nyquist comment is missing")

        return {
            "dimensions": {name: len(dim) for name, dim in dataset.dimensions.items()},
            "counts": {name: count for name, (count, _, _) in values.items()},
            "ranges": {name: [minimum, maximum] for name, (_, minimum, maximum) in values.items()},
            "nyq_valid_range": None,
            "valtime": float(dataset.variables["valtime"][0]),
            "reftime": float(dataset.variables["reftime"][0]),
            "velocity_comment": comments,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    check_source_contract()
    print("RADAR_REMAP_SOURCE_CONTRACT_PASS")
    if args.output:
        print(check_output(args.output.resolve()))
        print("RADAR_REMAP_NETCDF_CONTENT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
