#!/usr/bin/env python3
"""Bind the three actual preparation runs to their builds, inputs and outputs."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import netCDF4


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify(manifest, directory):
    subprocess.run(["sha256sum", "-c", str(manifest)], cwd=directory,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("build", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    repository = Path(__file__).resolve().parents[4]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    if commit != "a63a8029fc134e1bab77f0a96757e3b369b8e93d":
        raise ValueError("Cloud-BAL checkout differs from the build commit")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "src", "tests/intel_toolchain.sh",
                    "tools/build_upstream_producer.sh"], cwd=repository, check=True)
    for name in ("inputs", "runtime", "executable"):
        verify(args.build / f"{name}.sha256", args.build)
    source_before = args.root / "initial_source_before.sha256"
    source_after = args.root / "initial_source_after.sha256"
    if source_before.read_bytes() != source_after.read_bytes():
        raise ValueError("prepared source input inventory changed")
    source = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/") / \
             "cp02_maintained_derived_O0_qej27s72/matched_control_chain12_O0.ym17bs9h/prepared"
    verify(source_before, source)
    result = {"cloud_bal_commit": commit,
              "compiler_profile": "tests/intel_toolchain.sh; lapsprep O2",
              "initial_inventory_roots": ["static/", "lapsprd/"],
              "unsealed_copied_paths": ["payload.nc", "cdl/", "time/", "log/", "any other files outside static/ and lapsprd/"],
              "initial_inventory_limit": "other copied files were not inventoried before launch; no assumption is made about whether LAPSPREP read them",
              "build_executable_sha256": digest(args.build / "klps_anal_prep.exe"),
              "build_manifests": {name: digest(args.build / f"{name}.sha256")
                                  for name in ("inputs", "runtime", "executable")},
              "source_inventory_sha256": digest(source_before), "modes": {}}
    for mode in ("OFF", "HYDRO", "LIQUID_RADAR_RH1"):
        initial = args.root / f"init_{mode}"
        native = args.root / f"native_{mode}"
        before, after = initial / "inputs_before.sha256", initial / "inputs_after.sha256"
        if before.read_bytes() != after.read_bytes():
            raise ValueError(f"{mode} initial input inventory changed")
        verify(before, initial / "input")
        for stage in ("metgrid", "real"):
            verify(native / f"{stage}_inputs.sha256", native / stage)
        if "Successful completion of metgrid" not in (native / "metgrid.log").read_text():
            raise ValueError(f"{mode} metgrid success marker missing")
        if "SUCCESS COMPLETE REAL_EM INIT" not in (native / "real/rsl.out.0000").read_text():
            raise ValueError(f"{mode} real success marker missing")
        record = {"wps_sha256": digest(initial / "output.wps"),
                  "namelist_sha256": digest(initial / "input/static/lapsprep.nl"),
                  "input_inventory_sha256": digest(before),
                  "metgrid_input_manifest_sha256": digest(native / "metgrid_inputs.sha256"),
                  "real_input_manifest_sha256": digest(native / "real_inputs.sha256"),
                  "met_em_sha256": digest(native / "metgrid/met_em.d01.2026-08-16_12:00:00.nc"),
                  "wrfinput_sha256": digest(native / "real/wrfinput_d01")}
        if mode != "OFF":
            path = initial / "output.wps.shadow.nc"
            with netCDF4.Dataset(path) as ds:
                record["shadow"] = {"sha256": digest(path),
                    "result_authority": str(ds.result_authority),
                    "pipeline_status": int(ds.pipeline_status),
                    "acceptance_failures": int(ds.acceptance_failures),
                    "physical_continuity_assessed": int(ds.physical_continuity_assessed)}
        result["modes"][mode] = record
    verify(source_before, source)
    for name in ("inputs", "runtime", "executable"):
        verify(args.build / f"{name}.sha256", args.build)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
