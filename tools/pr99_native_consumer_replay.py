#!/usr/bin/env python3
"""Call the archived C1 native calc_ww_cp on a bounded WRF input snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import netCDF4
import numpy as np
import pr87_native_history


ROOT = Path(__file__).resolve().parents[1]
C1_RECEIPT = Path("/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json")
KIM_ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2")
DRIVER = ROOT / "tools/pr99_native_consumer_driver.f90"
ARRAY_ORDER = ("U", "V", "MU", "MUB", "C1H", "C2H", "DNW", "MSFTX", "MSFTY",
               "MSFUX", "MSFUY", "MSFVX", "MSFVX_INV", "MSFVY")
C1_MASS_DIMS = (234, 282, 39)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def field(dataset: netCDF4.Dataset, name: str, time_index: int) -> np.ndarray:
    return np.asarray(pr87_native_history._finite(dataset, name, time_index), dtype=np.float32)


def native_arrays(dataset: netCDF4.Dataset, time_index: int) -> tuple[dict[str, np.ndarray], int, int, int, int]:
    mass_nx = len(dataset.dimensions["west_east"])
    mass_ny = len(dataset.dimensions["south_north"])
    levels = len(dataset.dimensions["bottom_top"])
    if (mass_nx, mass_ny, levels) != C1_MASS_DIMS:
        raise ValueError(
            f"C1 calc_ww_cp requires mass dimensions {C1_MASS_DIMS}; "
            f"input has {(mass_nx, mass_ny, levels)}")
    nx, ny, nk, nkf = mass_nx + 1, mass_ny + 1, levels, levels + 1

    arrays: dict[str, np.ndarray] = {}

    def put3(name: str, source: str, pad_x: bool = False, pad_y: bool = False) -> None:
        values = field(dataset, source, time_index).transpose(2, 0, 1)
        padded = np.zeros((nx, nkf, ny), dtype=np.float32)
        padded[:values.shape[0], :values.shape[1], :values.shape[2]] = values
        if pad_x:
            padded[-1, :, :values.shape[2]] = padded[-2, :, :values.shape[2]]
        if pad_y:
            padded[:, :, -1] = padded[:, :, -2]
        arrays[name] = padded

    def put2(name: str, source: str, pad_x: bool = True, pad_y: bool = True) -> None:
        values = field(dataset, source, time_index).T
        padded = np.empty((nx, ny), dtype=np.float32)
        padded[:values.shape[0], :values.shape[1]] = values
        if pad_x:
            padded[-1, :values.shape[1]] = padded[-2, :values.shape[1]]
        if pad_y:
            padded[:, -1] = padded[:, -2]
        arrays[name] = padded

    put3("U", "U", pad_y=True)
    put3("V", "V", pad_x=True)
    put2("MU", "MU")
    put2("MUB", "MUB")
    for name in ("C1H", "C2H", "DNW"):
        arrays[name] = np.zeros(nkf, dtype=np.float32)
        arrays[name][:nk] = field(dataset, name, time_index)
    put2("MSFTX", "MAPFAC_MX")
    put2("MSFTY", "MAPFAC_MY")
    put2("MSFUX", "MAPFAC_UX", pad_x=False)
    put2("MSFUY", "MAPFAC_UY", pad_x=False)
    put2("MSFVX", "MAPFAC_VX", pad_y=False)
    put2("MSFVY", "MAPFAC_VY", pad_y=False)
    for name in ("MSFTX", "MSFTY", "MSFUX", "MSFUY", "MSFVX", "MSFVY"):
        if np.any(arrays[name] <= 0.0):
            raise ValueError(f"{name} must be positive before reciprocal/map-coordinate use")
    arrays["MSFVX_INV"] = 1.0 / arrays["MSFVX"]
    arrays["RDX"] = np.asarray(pr87_native_history._finite(dataset, "RDX", time_index), dtype=np.float32)
    arrays["RDY"] = np.asarray(pr87_native_history._finite(dataset, "RDY", time_index), dtype=np.float32)
    if np.any(arrays["RDX"] <= 0.0) or np.any(arrays["RDY"] <= 0.0):
        raise ValueError("RDX and RDY must be positive")
    return arrays, nx, ny, nk, nkf


def write_input(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with path.open("wb") as stream:
        for name in ARRAY_ORDER:
            values = arrays[name]
            stream.write(np.asarray(values, dtype="<f4").tobytes(order="F"))
        for name in ("RDX", "RDY"):
            stream.write(np.asarray(arrays[name], dtype="<f4").tobytes())


def link_command(receipt: dict, driver_object: Path, executable: Path) -> list[str]:
    original = receipt["link_argv"]
    compiler = original[0]
    archive = Path(receipt["parent_archive_copy"])
    support_objects = []
    library_args = []
    for item in original:
        if item in {compiler, "-o", original[2]}:
            continue
        if item.endswith(".o"):
            if Path(item).name not in {"wrf.o", "module_wrf_top.o"}:
                support_objects.append(item)
            continue
        if item.endswith(".a"):
            if item != str(archive):
                library_args.append(item)
            continue
        if item.startswith(("-Wl,", "-L", "-l", "-qopenmp")):
            library_args.append(item)
    args = [compiler, "-free",
            "-I", str(KIM_ROOT / "dyn_em"), "-I", str(KIM_ROOT / "frame"),
            str(driver_object), *support_objects, "-o", str(executable),
            str(archive), *library_args]
    return args


def reproducibility_flags(profile: Path) -> list[str]:
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; printf "%s\\n" "${CLOUD_BAL_REPRO_FLAGS[@]}"',
         "pr99-native-consumer-flags", str(profile)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"could not read pinned profile flags: {result.stdout}")
    return result.stdout.splitlines()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="native WRF input or history file")
    parser.add_argument("--time-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True,
                        help="private raw field output path, preferably under /var/tmp")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    receipt = json.loads(C1_RECEIPT.read_text())
    with netCDF4.Dataset(args.input) as dataset:
        arrays, nx, ny, nk, nkf = native_arrays(dataset, args.time_index)
        rdx = float(arrays["RDX"])
        rdy = float(arrays["RDY"])
    scratch = Path(tempfile.mkdtemp(prefix="pr99-native-consumer-", dir="/var/tmp"))
    write_input(scratch / "native_consumer_input.bin", arrays)
    shutil.copy2(DRIVER, scratch / DRIVER.name)
    profile = Path(receipt["compiler_profile_path"])
    profile_flags = reproducibility_flags(profile)
    compile_argv = [receipt["compiler_path"], *profile_flags, "-free", "-I",
                    str(KIM_ROOT / "dyn_em"), "-I", str(KIM_ROOT / "frame"), "-c",
                    str(scratch / DRIVER.name), "-module", str(scratch), "-o",
                    str(scratch / "driver.o")]
    build = subprocess.run(
        ["bash", "-c",
         'source "$1"; "$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" -free -I "$2/dyn_em" '
         '-I "$2/frame" -c "$3" -module "$4" -o "$5"',
         "pr99-native-consumer-compile", str(profile), str(KIM_ROOT),
         str(scratch / DRIVER.name), str(scratch), str(scratch / "driver.o")],
        cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (scratch / "compile.log").write_text(build.stdout)
    if build.returncode:
        raise RuntimeError(f"pinned Intel driver compile failed: {build.stdout}")
    exe = scratch / "native_consumer.exe"
    argv = link_command(receipt, scratch / "driver.o", exe)
    linked = subprocess.run(
        ["bash", "-c",
         'source "$1"; shift; requested_fc="$1"; shift; '
         '"$requested_fc" "${CLOUD_BAL_REPRO_FLAGS[@]}" "$@"',
         "pr99-native-consumer-link", str(profile), argv[0], *argv[1:]],
        cwd=scratch, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False)
    (scratch / "link.log").write_text("\n".join(argv) + "\n" + linked.stdout)
    if linked.returncode:
        raise RuntimeError(f"native consumer link failed: {linked.stdout}")
    effective_link_argv = [argv[0], *profile_flags, *argv[1:]]
    (scratch / "link.log").write_text("\n".join(effective_link_argv) + "\n" + linked.stdout)
    mpi_env = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh")
    runtime_libs = ":".join(("/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib",
                              "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib",
                              "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib"))
    run = subprocess.run(
        ["bash", "-c", 'source "$1"; source "$2"; export LD_LIBRARY_PATH="$3:${LD_LIBRARY_PATH:-}"; exec "$4"',
         "pr99-native-consumer-run", str(profile), str(mpi_env), runtime_libs, str(exe)],
        cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (scratch / "run.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(f"native consumer execution failed: {run.stdout}")
    result = np.fromfile(scratch / "native_consumer_ww.bin", dtype="<f4").reshape(
        (nx, nkf, ny), order="F")
    tile = result[1:nx - 2, :, 1:ny - 2].astype(np.float64)
    mass_levels = tile[:, :nk, :]
    boundary_faces = tile[:, [0, nk], :]
    report = {
        "schema": "pr99_native_calc_ww_cp_replay_v1",
        "native_consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
        "object_source": "module_big_step_utilities_em.o member pulled from C1 parent archive",
        "c1_archive": str(receipt["parent_archive_copy"]),
        "c1_archive_sha256": sha256(Path(receipt["parent_archive_copy"])),
        "archive_member_sha256": subprocess.check_output(
            ["bash", "-c", 'ar p "$1" module_big_step_utilities_em.o | sha256sum',
             "pr99-hash-member", str(receipt["parent_archive_copy"])], text=True).split()[0],
        "interface_module": str(KIM_ROOT / "dyn_em/module_big_step_utilities_em.mod"),
        "interface_module_sha256": sha256(KIM_ROOT / "dyn_em/module_big_step_utilities_em.mod"),
        "compiler_profile": str(profile),
        "compiler_profile_sha256": receipt["compiler_profile_sha256"],
        "input": str(args.input),
        "input_sha256": sha256(args.input),
        "time_index": args.time_index,
        "rdx_m_inv": rdx,
        "rdy_m_inv": rdy,
        "mass_grid_shape": [nx_mass, ny_mass, nk],
        "staggered_driver_shape": [nx, ny, nkf],
        "active_tile_one_based": {"i": [2, nx_mass - 1], "j": [2, ny_mass - 1],
                                   "k": [1, nkf]},
        "active_value_count": int(tile.size),
        "finite_value_count": int(np.isfinite(tile).sum()),
        "native_ww_min_pa_s": float(tile.min()),
        "native_ww_max_pa_s": float(tile.max()),
        "native_ww_rms_pa_s": float(np.sqrt(np.mean(tile * tile))),
        "native_ww_max_abs_pa_s": float(np.max(np.abs(tile))),
        "native_ww_mass_levels_1_to_39_rms_pa_s": float(np.sqrt(np.mean(mass_levels * mass_levels))),
        "native_ww_lower_top_face_max_abs_pa_s": float(np.max(np.abs(boundary_faces))),
        "native_ww_sha256": sha256(scratch / "native_consumer_ww.bin"),
        "native_ww_raw_path": str(args.raw_output),
        "driver_sha256": sha256(DRIVER),
        "executable_sha256": sha256(exe),
        "compiler_flags": "CLOUD_BAL_REPRO_FLAGS from pinned Intel profile plus -free and KIM module include paths for compile; same profile flags for final link",
        "profile_repro_flags": profile_flags,
        "compile_argv": compile_argv,
        "link_argv": effective_link_argv,
        "run_log": run.stdout,
        "physical_scope": "computed mass-coordinate ww (Pa/s) from native U/V, MU/MUB and C1 geometry; not W and not a saved native ww comparison",
        "boundary_scope": "one mass-grid row/column excluded so every MU/MUB face donor and staggered U/V input is inside the history-file arrays; all 39 mass levels plus the top w-face are emitted for the selected interior; top interface input padding is unused by calc_ww_cp",
        "capture_limitation": "initial condition replay only; no exact T32 U/V/MU/C geometry snapshot was present in the frozen C1 capture",
        "scratch": str(scratch),
    }
    (args.output / "replay.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    shutil.copy2(scratch / "native_consumer_ww.bin", args.raw_output)
    shutil.copy2(scratch / "compile.log", args.output / "compile.log")
    shutil.copy2(scratch / "link.log", args.output / "link.log")
    shutil.copy2(scratch / "run.log", args.output / "run.log")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
