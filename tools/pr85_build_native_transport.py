#!/usr/bin/env python3
"""Build a source-bound PR85 native transport and PBL overlay candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from archive_member_hashes import archive_member_hashes

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
PR83_RECEIPT = Path("/var/tmp/pr83_rk_operand_build_20261013_7/pr83_rk_operands_observer_build.json")
PR84_ARCHIVE = Path("/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/link/main/libwrflib_pr84.a")
PR84_EXE = Path("/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/wrf_pr84.exe")
PR84_LINK_MAIN = PR84_ARCHIVE.parent
PR84_BUILD_RECEIPT = ROOT / "docs/evidence/pr84_native_ice_guard_build_20261013.json"
PR84_KDM6_SOURCE = Path("/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/compile/module_mp_kdm6.F")
PR84_KDM6_SOURCE_SHA256 = "f7fb216c82822162c30148829f207deeee5900e46e01ad9082ac58c802a181d9"
PR84_KDM6_MEMBER_SHA256 = "e097b7e70566275d5cd82c211d91e4658091c78ea1b41eb9ffef35bc1159d006"
OBSERVER_SOURCE = ROOT / "tools/pr85_joint_stage_observer.f90"
PR74_SOURCE_RECEIPT = ROOT / "docs/evidence/pr74_shinhong_qni_driver_20261008.json"
PR74_O0_COMPILE = Path("/var/tmp/pr74_shinhong_qni_driver.GvfcGi/O0/compile")
PR74_SHINHONG_SOURCE = PR74_O0_COMPILE / "module_bl_shinhong.F"
PR74_SHINHONG_SOURCE_SHA256 = "5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553"
PR74_PBL_SOURCE = PR74_O0_COMPILE / "module_pbl_driver.F"
PR74_PBL_SOURCE_SHA256 = "342378285d929d06aa88b3c47b27c906bac05e560244162e4f946481ea4bd322"
PR74_SHINHONG_MOD = PR74_O0_COMPILE / "module_bl_shinhong.mod"
PR74_SHINHONG_MOD_SHA256 = "0a93e5ed46e8f51733a96ada5c926ac6b774a4e3bb377646a54443158950d595"
PR74_PBL_OBJECT_SHA256 = "38cb4de8de7f7870f240d50626c527aaf6b8078935aed53b3b8509be157f9c3a"
PR61_FOG_SOURCE = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys/module_bl_fogdes.F")
PR61_FOG_SOURCE_SHA256 = "94d6b4ed3f82c6d7ca9b14107ee07af8ace058dd65f7e07ab5fa0ab8ea1b0ed7"
PR61_DYN_BUILD_LOG = Path("/var/tmp/pr61_ccn_origin_20261006/hostcopy/compile_pass2.log")
PR61_DYN_BUILD_LOG_SHA256 = "e1581e5dc183e007256c9923fa4d48a44cf6e0a56ea7595c9d62807970a1ba80"
WRF_DYN_CPPFLAGS = (
    "-DEM_CORE=1", "-DNMM_CORE=0", "-DNMM_MAX_DIM=2600", "-DDA_CORE=0",
    "-DWRFPLUS=0", "-DIWORDSIZE=4", "-DDWORDSIZE=8", "-DRWORDSIZE=4",
    "-DLWORDSIZE=4", "-DNONSTANDARD_SYSTEM_FUNC", "-DWRF_USE_CLM",
    "-DDM_PARALLEL", "-DNETCDF", "-DLANDREAD_STUB=1", "-DUSE_ALLOCATABLES",
    "-Dwrfmodel", "-DGRIB1", "-DINTIO", "-DKEEP_INT_AROUND", "-DLIMIT_ARGS",
    "-DBUILD_RRTMG_FAST=1", "-DBUILD_RRTMK=1", "-DBUILD_SBM_FAST=1",
    "-DSHOW_ALL_VARS_USED=0", "-DCONFIG_BUF_LEN=65536", "-DMAX_DOMAINS_F=21",
    "-DMAX_HISTORY=25", "-DNMM_NEST=0",
)
KIM_DYN = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/dyn_em")
PART2_SOURCE = KIM_DYN / "module_first_rk_step_part2.F"
PART2_SOURCE_SHA256 = "c2559617bbd4602daf9f1b5703864af11eafadb489c82a91a452beb697db6e1d"
PART1_SOURCE = KIM_DYN / "module_first_rk_step_part1.F"
PART1_SOURCE_SHA256 = "b3d0c70397edd6a20162c55cbd988fe21e4c8aee484fb3b1da72760487e95d63"
BASE_SOURCES = {
    "module_advect_em.o": (KIM_DYN / "module_advect_em.F",
                           "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d"),
    "module_em.o": (KIM_DYN / "module_em.F",
                    "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7"),
    "solve_em.o": (KIM_DYN / "solve_em.F",
                   "6e52d3018a9418d2635a9a5624fe903631e9b5d904151280c384e35a43099f8f"),
    "module_first_rk_step_part1.o": (PART1_SOURCE, PART1_SOURCE_SHA256),
}
BASE_OBJECTS = {
    "module_advect_em.o": "1387f39b29c1c04d18ee48371cd01170fb46ffe5b68c2db8c72c398dc6cddf61",
    "module_em.o": "cccf64664550818bdd15aac32c4cfe71bde795e79ee2c81ec82d54b0daec9f8a",
    "solve_em.o": "31ff7db3659959ad64d76692d171176aa6a6328c6b80982cc636de345d0c3e86",
    "module_first_rk_step_part1.o": "8faae0b7c67b5efa4289b5a4359c238b09edcd667efd91e67be76ec725fc0b65",
}
ORDER = ("module_em.o", "solve_em.o")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], cwd: Path, log: Path) -> None:
    command = "source " + shlex.quote(str(PROFILE)) + "; exec " + " ".join(
        shlex.quote(arg) for arg in argv)
    result = subprocess.run(["bash", "-lc", command], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(f"compile failed ({result.returncode}): {argv[0]}\n{result.stdout}")


def argv_digest(argv: list[str]) -> str:
    return hashlib.sha256(b"\0".join(os.fsencode(arg) for arg in argv) + b"\0").hexdigest()


def version(compiler: Path) -> str:
    return subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0]


def compile_preprocessed(argv: list[str], source: Path, obj: Path, cwd: Path,
                         generated: Path, preprocess_log: Path,
                         compile_log: Path) -> tuple[list[str], list[str]]:
    """Save the exact ifx preprocessing output, then compile those bytes."""
    preprocess_argv = list(argv)
    preprocess_argv.remove("-c")
    preprocess_argv.remove("-fpp")
    preprocess_argv[-3:] = ["-EP", "-fpp", str(source)]
    result = subprocess.run(
        ["bash", "-lc", "source " + shlex.quote(str(PROFILE)) + "; exec " +
         " ".join(shlex.quote(arg) for arg in preprocess_argv)], cwd=cwd,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    preprocess_log.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(f"preprocess failed ({result.returncode}): {source}\n{result.stdout}")
    generated.write_text(result.stdout)

    compile_argv = list(argv)
    compile_argv.remove("-fpp")
    compile_argv[-3:] = [str(generated), "-o", str(obj)]
    run(compile_argv, cwd, compile_log)
    return preprocess_argv, compile_argv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True,
                        help="new scratch directory; an existing path is rejected")
    parser.add_argument("--solve-patch", type=Path, required=True,
                        help="unified solve_em defer/grouped-update patch")
    parser.add_argument("--boundary-patch", type=Path,
                        help="optional post-update grouped-field boundary refresh")
    parser.add_argument("--solve-tile-guard-patch", type=Path,
                        help="optional single-tile fail-closed guard, applied after boundary refresh")
    parser.add_argument("--kernel", type=Path, default=ROOT / "src/common/cloud_bal_joint_transport.f90")
    parser.add_argument("--update-fragment", type=Path, default=ROOT / "tools/pr85_native_joint_update.f90")
    parser.add_argument("--pbl-capture-patch", type=Path,
                        help="optional patch that captures completed selected PBL tendencies")
    parser.add_argument("--source-attribution-patch", type=Path,
                        help="optional RK1 process/diffusion source observer overlay")
    parser.add_argument("--ksas-source-patch", type=Path,
                        help="optional process-specific paired KSAS source prior, applied after attribution")
    parser.add_argument("--fog-patch", type=Path,
                        help="optional FogDES Q/N transport patch and PBL driver call")
    parser.add_argument("--pbl-packet-patch", type=Path,
                        help="optional common-Shinhong paired packet quantization patch")
    parser.add_argument("--kdm6-sedimentation-patch", type=Path,
                        help="optional source-bound KDM6 ice sedimentation replacement patch")
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    patch = args.solve_patch.resolve()
    boundary_patch = args.boundary_patch.resolve() if args.boundary_patch else None
    solve_tile_guard_patch = (args.solve_tile_guard_patch.resolve()
                              if args.solve_tile_guard_patch else None)
    kernel = args.kernel.resolve()
    update_fragment = args.update_fragment.resolve()
    pbl_capture_patch = args.pbl_capture_patch.resolve() if args.pbl_capture_patch else None
    source_attribution_patch = (args.source_attribution_patch.resolve()
                                if args.source_attribution_patch else None)
    ksas_source_patch = args.ksas_source_patch.resolve() if args.ksas_source_patch else None
    fog_patch = args.fog_patch.resolve() if args.fog_patch else None
    pbl_packet_patch = args.pbl_packet_patch.resolve() if args.pbl_packet_patch else None
    kdm6_sedimentation_patch = (args.kdm6_sedimentation_patch.resolve()
                                if args.kdm6_sedimentation_patch else None)
    if scratch.exists():
        raise SystemExit(f"scratch already exists: {scratch}")
    for label, path in (("solve patch", patch), ("grouped-update kernel", kernel),
                        ("native update procedure", update_fragment)):
        if not path.is_file():
            raise SystemExit(f"{label} is missing: {path}")
    if pbl_capture_patch is not None and not pbl_capture_patch.is_file():
        raise SystemExit(f"PBL capture patch is missing: {pbl_capture_patch}")
    if source_attribution_patch is not None and not source_attribution_patch.is_file():
        raise SystemExit(f"source attribution patch is missing: {source_attribution_patch}")
    if ksas_source_patch is not None and not ksas_source_patch.is_file():
        raise SystemExit(f"KSAS source patch is missing: {ksas_source_patch}")
    if ksas_source_patch is not None and source_attribution_patch is None:
        raise SystemExit("KSAS source patch requires the source-attribution patch as its pinned base")
    if fog_patch is not None and not fog_patch.is_file():
        raise SystemExit(f"FogDES patch is missing: {fog_patch}")
    if pbl_packet_patch is not None and not pbl_packet_patch.is_file():
        raise SystemExit(f"PBL packet patch is missing: {pbl_packet_patch}")
    if kdm6_sedimentation_patch is not None and not kdm6_sedimentation_patch.is_file():
        raise SystemExit(f"KDM6 sedimentation patch is missing: {kdm6_sedimentation_patch}")
    if boundary_patch is not None and not boundary_patch.is_file():
        raise SystemExit(f"boundary refresh patch is missing: {boundary_patch}")
    if solve_tile_guard_patch is not None and not solve_tile_guard_patch.is_file():
        raise SystemExit(f"solve tile guard patch is missing: {solve_tile_guard_patch}")
    if (fog_patch is not None or pbl_packet_patch is not None) and \
            (sha256(PR74_SHINHONG_SOURCE) != PR74_SHINHONG_SOURCE_SHA256 or
             sha256(PR74_PBL_SOURCE) != PR74_PBL_SOURCE_SHA256 or
             sha256(PR74_SHINHONG_MOD) != PR74_SHINHONG_MOD_SHA256):
        raise SystemExit("retained PR74 Shinhong/PBL source or module identity mismatch")
    if fog_patch is not None and sha256(PR61_FOG_SOURCE) != PR61_FOG_SOURCE_SHA256:
        raise SystemExit("retained PR61 FogDES source identity mismatch")
    if (source_attribution_patch is not None or ksas_source_patch is not None) and \
            sha256(PART2_SOURCE) != PART2_SOURCE_SHA256:
        raise SystemExit(f"retained KIM part2 source identity mismatch: {PART2_SOURCE}")
    if not PR83_RECEIPT.is_file() or not PR84_ARCHIVE.is_file():
        raise SystemExit("retained PR83 compile recipe or PR84 archive is missing")
    if not PR61_DYN_BUILD_LOG.is_file() or sha256(PR61_DYN_BUILD_LOG) != PR61_DYN_BUILD_LOG_SHA256:
        raise SystemExit("retained PR61 dynamic preprocessing log identity mismatch")
    if not PR84_EXE.is_file() or not PR84_BUILD_RECEIPT.is_file() or not OBSERVER_SOURCE.is_file():
        raise SystemExit("retained PR84 executable/receipt or PR85 observer source is missing")
    if kdm6_sedimentation_patch is not None and (
            not PR84_KDM6_SOURCE.is_file() or
            sha256(PR84_KDM6_SOURCE) != PR84_KDM6_SOURCE_SHA256):
        raise SystemExit("retained PR84 KDM6 source identity mismatch")

    receipt = json.loads(PR83_RECEIPT.read_text())
    base_argv = receipt["compile_argv"]
    if not base_argv or Path(base_argv[0]).name != "ifx":
        raise SystemExit("retained PR83 compile recipe is not an ifx command")
    compiler = Path(base_argv[0])
    parent_receipt = json.loads(PR84_BUILD_RECEIPT.read_text())
    parent_link_argv = parent_receipt["production_link_argv"]
    if sha256(PR84_EXE) != "4912d0f5c6b91d8e57bd0ff91adab2938ed4f74b9e8fa417903202dbf1c9d55a":
        raise SystemExit("retained PR84 executable identity mismatch")
    if sha256(PR84_ARCHIVE) != "7c1ea24fb3baa4d7c4d977920378a6c53f929077b07300754f4d3844a2b3e7da":
        raise SystemExit("retained PR84 archive identity mismatch")
    for member, (source, expected) in BASE_SOURCES.items():
        if not source.is_file() or sha256(source) != expected:
            raise SystemExit(f"retained KIM source mismatch: {source}")
    for member, expected in BASE_OBJECTS.items():
        found = subprocess.run(["ar", "p", str(PR84_ARCHIVE), member],
                               check=True, stdout=subprocess.PIPE).stdout
        if hashlib.sha256(found).hexdigest() != expected:
            raise SystemExit(f"retained PR84 archive member mismatch: {member}")
    if kdm6_sedimentation_patch is not None:
        found = subprocess.run(["ar", "p", str(PR84_ARCHIVE), "module_mp_kdm6.o"],
                               check=True, stdout=subprocess.PIPE).stdout
        if hashlib.sha256(found).hexdigest() != PR84_KDM6_MEMBER_SHA256:
            raise SystemExit("retained PR84 KDM6 archive member identity mismatch")
        if parent_receipt.get("production_source_sha256") != PR84_KDM6_SOURCE_SHA256:
            raise SystemExit("PR84 KDM6 source receipt does not match the retained source")

    scratch.mkdir(parents=True)
    compile_dir = scratch / "compile"
    preprocess_dir = scratch / "preprocessed"
    source_dir = scratch / "source/dyn_em"
    link_dir = scratch / "link/main"
    compile_dir.mkdir()
    preprocess_dir.mkdir()
    source_dir.mkdir(parents=True)
    link_dir.mkdir(parents=True)
    for member in BASE_SOURCES:
        shutil.copy2(BASE_SOURCES[member][0], source_dir / BASE_SOURCES[member][0].name)
    kdm6_source = None
    kdm6_patch_log = None
    if kdm6_sedimentation_patch is not None:
        kdm6_source = source_dir.parent / "phys/module_mp_kdm6.F"
        kdm6_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PR84_KDM6_SOURCE, kdm6_source)
        kdm6_patch_log = scratch / "kdm6_sedimentation_patch.log"
        result = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(kdm6_sedimentation_patch)],
            cwd=source_dir.parent, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        kdm6_patch_log.write_text(result.stdout)
        if result.returncode:
            raise SystemExit("KDM6 sedimentation patch failed to apply:\n" + result.stdout)
    observer_source = scratch / "source/pr85_joint_stage_observer.f90"
    shutil.copy2(OBSERVER_SOURCE, observer_source)
    part2_source = None
    source_attribution_patch_log = None
    ksas_source_patch_log = None
    if source_attribution_patch is not None:
        part2_source = source_dir / PART2_SOURCE.name
        shutil.copy2(PART2_SOURCE, part2_source)
        source_attribution_patch_log = scratch / "source_attribution_patch.log"
        result = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(source_attribution_patch)],
            cwd=scratch / "source", text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        source_attribution_patch_log.write_text(result.stdout)
        if result.returncode:
            raise SystemExit("source attribution patch failed to apply:\n" + result.stdout)
    if ksas_source_patch is not None:
        if part2_source is None:
            raise SystemExit("KSAS source patch has no staged module_first_rk_step_part2.F")
        ksas_source_patch_log = scratch / "ksas_source_patch.log"
        result = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(ksas_source_patch)],
            cwd=scratch / "source", text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        ksas_source_patch_log.write_text(result.stdout)
        if result.returncode:
            raise SystemExit("KSAS source patch failed after attribution overlay:\n" + result.stdout)
    pbl_source = None
    shinhong_source = None
    fog_source = None
    pbl_capture_source = None
    pbl_capture_object = None
    pbl_capture_compile_argv = None
    pbl_capture_log = None
    pbl_capture_generated = None
    pbl_capture_preprocess_argv = None
    pbl_capture_preprocess_log = None
    shinhong_object = None
    shinhong_compile_argv = None
    shinhong_compile_log = None
    shinhong_generated = None
    shinhong_preprocess_argv = None
    shinhong_preprocess_log = None
    fog_object = None
    fog_compile_argv = None
    fog_compile_log = None
    fog_generated = None
    fog_preprocess_argv = None
    fog_preprocess_log = None
    pbl_patch_logs = {}
    if any((pbl_capture_patch, fog_patch, pbl_packet_patch)):
        pr74 = json.loads(PR74_SOURCE_RECEIPT.read_text())
        if pr74["profiles"]["O0"]["module_pbl_driver_object_sha256"] != PR74_PBL_OBJECT_SHA256:
            raise SystemExit("PR74 PBL object binding mismatch")
        phys_dir = source_dir.parent / "phys"
        phys_dir.mkdir(parents=True, exist_ok=True)
        pbl_source = phys_dir / "module_pbl_driver.F"
        shutil.copy2(PR74_PBL_SOURCE, pbl_source)
        shutil.copy2(PR74_SHINHONG_MOD, compile_dir / PR74_SHINHONG_MOD.name)
        if pbl_packet_patch is not None:
            shinhong_source = phys_dir / "module_bl_shinhong.F"
            shutil.copy2(PR74_SHINHONG_SOURCE, shinhong_source)
        if fog_patch is not None:
            fog_source = phys_dir / "module_bl_fogdes.F"
            shutil.copy2(PR61_FOG_SOURCE, fog_source)

        for name, overlay, cwd in (
                ("fog", fog_patch, scratch / "source"),
                ("pbl_packet", pbl_packet_patch, phys_dir),
                ("pbl_capture", pbl_capture_patch, phys_dir)):
            if overlay is None:
                continue
            log_path = scratch / f"{name}_patch.log"
            result = subprocess.run(
                ["patch", "--fuzz=0", "-p1", "-i", str(overlay)], cwd=cwd,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log_path.write_text(result.stdout)
            pbl_patch_logs[name] = log_path
            if result.returncode:
                raise SystemExit(f"{name} patch failed to apply:\n{result.stdout}")

        pr74_compile = pr74["profiles"]["O0"]["compile_argv"]
        if shinhong_source is not None:
            shinhong_object = compile_dir / "module_bl_shinhong.o"
            shinhong_compile_argv = list(pr74_compile[0])
            shinhong_compile_argv[shinhong_compile_argv.index("-I.")] = "-I" + str(compile_dir)
            shinhong_compile_argv[-1:] = [str(shinhong_source), "-o", str(shinhong_object)]
            shinhong_compile_log = scratch / "module_bl_shinhong.compile.log"
            shinhong_generated = preprocess_dir / "module_bl_shinhong.f90"
            shinhong_preprocess_log = scratch / "module_bl_shinhong.preprocess.log"
            shinhong_preprocess_argv, shinhong_compile_argv = compile_preprocessed(
                shinhong_compile_argv, shinhong_source, shinhong_object, compile_dir,
                shinhong_generated, shinhong_preprocess_log, shinhong_compile_log)
        if fog_source is not None:
            fog_object = compile_dir / "module_bl_fogdes.o"
            fog_compile_argv = list(pr74_compile[0])
            fog_compile_argv[fog_compile_argv.index("-I.")] = "-I" + str(compile_dir)
            fog_compile_argv[-1:] = [str(fog_source), "-o", str(fog_object)]
            fog_compile_log = scratch / "module_bl_fogdes.compile.log"
            fog_generated = preprocess_dir / "module_bl_fogdes.f90"
            fog_preprocess_log = scratch / "module_bl_fogdes.preprocess.log"
            fog_preprocess_argv, fog_compile_argv = compile_preprocessed(
                fog_compile_argv, fog_source, fog_object, compile_dir,
                fog_generated, fog_preprocess_log, fog_compile_log)
        if pbl_capture_patch is not None or fog_patch is not None:
            pbl_capture_source = pbl_source
            pbl_capture_object = compile_dir / "module_pbl_driver.o"
            pbl_capture_compile_argv = list(pr74_compile[1])
            pbl_capture_compile_argv[pbl_capture_compile_argv.index("-I.")] = "-I" + str(compile_dir)
            pbl_capture_compile_argv[-1:] = [str(pbl_source), "-o", str(pbl_capture_object)]
            pbl_capture_log = scratch / "module_pbl_driver.compile.log"
            pbl_capture_generated = preprocess_dir / "module_pbl_driver.f90"
            pbl_capture_preprocess_log = scratch / "module_pbl_driver.preprocess.log"
            pbl_capture_preprocess_argv, pbl_capture_compile_argv = compile_preprocessed(
                pbl_capture_compile_argv, pbl_source, pbl_capture_object, compile_dir,
                pbl_capture_generated, pbl_capture_preprocess_log, pbl_capture_log)
    patch_log = scratch / "patch.log"
    patch_result = subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(patch)],
                                  cwd=scratch / "source", text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    patch_log.write_text(patch_result.stdout)
    if patch_result.returncode:
        raise SystemExit(f"transport patch failed to apply:\n{patch_result.stdout}")
    boundary_patch_log = None
    if boundary_patch is not None:
        boundary_patch_log = scratch / "boundary_patch.log"
        boundary_result = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(boundary_patch)],
            cwd=scratch / "source", text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        boundary_patch_log.write_text(boundary_result.stdout)
        if boundary_result.returncode:
            raise SystemExit(f"boundary refresh patch failed:\n{boundary_result.stdout}")
    solve_tile_guard_patch_log = None
    if solve_tile_guard_patch is not None:
        solve_tile_guard_patch_log = scratch / "solve_tile_guard_patch.log"
        tile_guard_result = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(solve_tile_guard_patch)],
            cwd=scratch / "source", text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        solve_tile_guard_patch_log.write_text(tile_guard_result.stdout)
        if tile_guard_result.returncode:
            raise SystemExit("solve tile guard patch failed after boundary refresh:\n" +
                             tile_guard_result.stdout)

    module_em_base = source_dir / "module_em.F"
    module_em_composite = compile_dir / "module_em_pr85.F"
    module_source = module_em_base.read_text()
    module_end = "END MODULE module_em"
    if module_source.upper().count(module_end.upper()) != 1:
        raise SystemExit("retained module_em source must have one END MODULE module_em")
    fragment = update_fragment.read_text().strip()
    module_source = kernel.read_text().strip() + "\n\n" + module_source
    module_source, inserted = re.subn(
        r"(?im)^\s*END MODULE module_em\s*$",
        lambda match: fragment + "\n\n" + match.group(0), module_source, count=1)
    if inserted != 1:
        raise SystemExit("failed to insert the grouped-update procedure into module_em")
    module_em_composite.write_text(module_source)

    compiled = []
    # The shared kernel module precedes module_em in one source/object, and
    # solve_em calls the contained grouped update after deferring its RK calls.
    compile_members = list(ORDER)
    if part2_source is not None:
        compile_members.append("module_first_rk_step_part2.o")
    if fog_patch is not None:
        compile_members.append("module_first_rk_step_part1.o")
    for member in compile_members:
        if member == "module_em.o":
            source = module_em_composite
        elif member == "solve_em.o":
            source = source_dir / "solve_em.F"
        elif member == "module_first_rk_step_part2.o":
            source = part2_source
        else:
            source = source_dir / "module_first_rk_step_part1.F"
        obj = compile_dir / member
        argv = list(base_argv)
        if "-O2" not in argv:
            raise SystemExit("retained PR83 recipe does not expose the expected optimization flag")
        argv[argv.index("-O2")] = "-O0"
        argv[-3:-3] = list(WRF_DYN_CPPFLAGS)
        argv[-3:] = [str(source), "-o", str(obj)]
        module_include = "-I" + str(KIM_DYN.parent)
        module_include_at = argv.index(module_include)
        argv[module_include_at:module_include_at] = [
                 "-module", str(compile_dir), "-I" + str(compile_dir)]
        generated = preprocess_dir / (member.removesuffix(".o") + ".f90")
        preprocess_log = scratch / (member.removesuffix(".o") + ".preprocess.log")
        log = scratch / (member.removesuffix(".o") + ".compile.log")
        preprocess_argv, argv = compile_preprocessed(
            argv, source, obj, compile_dir, generated, preprocess_log, log)
        compiled.append({
            "member": member,
            "source_path": str(source),
            "source_sha256": sha256(source),
            "generated_source_path": str(generated),
            "generated_source_sha256": sha256(generated),
            "preprocess_argv": preprocess_argv,
            "preprocess_log_sha256": sha256(preprocess_log),
            "preprocessor_defines": list(WRF_DYN_CPPFLAGS),
            "source_components": {
                "base_module_em_source": str(module_em_base),
                "base_module_em_source_sha256": sha256(module_em_base),
                "transport_kernel": str(kernel),
                "transport_kernel_sha256": sha256(kernel),
                "native_update_fragment": str(update_fragment),
                "native_update_fragment_sha256": sha256(update_fragment),
                "preprocessing_log_path": str(PR61_DYN_BUILD_LOG),
                "preprocessing_log_sha256": PR61_DYN_BUILD_LOG_SHA256,
            } if member == "module_em.o" else ({
                "base_solve_em_source": str(BASE_SOURCES[member][0]),
                "base_solve_em_source_sha256": BASE_SOURCES[member][1],
                "solve_patch": str(patch),
                "solve_patch_sha256": sha256(patch),
                "boundary_patch": str(boundary_patch) if boundary_patch else None,
                "boundary_patch_sha256": sha256(boundary_patch) if boundary_patch else None,
                "boundary_patch_log_sha256": sha256(boundary_patch_log)
                if boundary_patch_log else None,
                "solve_tile_guard_patch": str(solve_tile_guard_patch)
                if solve_tile_guard_patch else None,
                "solve_tile_guard_patch_sha256": sha256(solve_tile_guard_patch)
                if solve_tile_guard_patch else None,
                "solve_tile_guard_patch_log_sha256": sha256(solve_tile_guard_patch_log)
                if solve_tile_guard_patch_log else None,
            } if member == "solve_em.o" else ({
                "base_part2_source": str(PART2_SOURCE),
                "base_part2_source_sha256": PART2_SOURCE_SHA256,
                "source_attribution_patch": str(source_attribution_patch),
                "source_attribution_patch_sha256": sha256(source_attribution_patch),
                "source_attribution_patch_log_sha256": sha256(source_attribution_patch_log),
                "ksas_source_patch": str(ksas_source_patch) if ksas_source_patch else None,
                "ksas_source_patch_sha256": sha256(ksas_source_patch)
                if ksas_source_patch else None,
                "ksas_source_patch_log_sha256": sha256(ksas_source_patch_log)
                if ksas_source_patch_log else None,
            } if member == "module_first_rk_step_part2.o" else {
                "base_part1_source": str(PART1_SOURCE),
                "base_part1_source_sha256": PART1_SOURCE_SHA256,
                "fog_patch": str(fog_patch),
                "fog_patch_sha256": sha256(fog_patch),
                "fog_patch_log_sha256": sha256(pbl_patch_logs["fog"]),
                "preprocessing_log_path": str(PR61_DYN_BUILD_LOG),
                "preprocessing_log_sha256": PR61_DYN_BUILD_LOG_SHA256,
                "preprocessor_defines": list(WRF_DYN_CPPFLAGS),
            })),
            "object_path": str(obj),
            "object_sha256": sha256(obj),
            "compile_argv": argv,
            "preprocess_argv": preprocess_argv,
            "preprocess_log_sha256": sha256(preprocess_log),
            "preprocessor_defines": list(WRF_DYN_CPPFLAGS),
            "compile_log_sha256": sha256(log),
        })

    kdm6_row = None
    if kdm6_source is not None:
        parent_kdm6_argv = list(parent_receipt["production_compile_argv"])
        parent_source_text = str(PR84_KDM6_SOURCE)
        parent_object_text = str(PR84_KDM6_SOURCE.with_suffix(".o"))
        if (parent_kdm6_argv.count(parent_source_text) != 1 or
                parent_kdm6_argv.count(parent_object_text) != 1 or
                parent_kdm6_argv.count("-c") != 1 or
                parent_kdm6_argv.count("-o") != 1 or
                parent_kdm6_argv[0] != str(compiler)):
            raise SystemExit("retained PR84 KDM6 compile recipe has unexpected source/object bindings")
        kdm6_object = compile_dir / "module_mp_kdm6.o"
        kdm6_compile_dir = scratch / "kdm6_compile"
        kdm6_compile_dir.mkdir()
        generated = preprocess_dir / "module_mp_kdm6.f90"
        preprocess_log = scratch / "module_mp_kdm6.preprocess.log"
        compile_log = scratch / "module_mp_kdm6.compile.log"
        preprocess_argv = list(parent_kdm6_argv)
        preprocess_argv.remove("-c")
        object_index = preprocess_argv.index("-o")
        del preprocess_argv[object_index:object_index + 2]
        preprocess_argv[preprocess_argv.index(parent_source_text)] = str(kdm6_source)
        preprocess_argv.append("-EP")
        preprocessed = subprocess.run(
            ["bash", "-lc", "source " + shlex.quote(str(PROFILE)) + "; exec " +
             " ".join(shlex.quote(arg) for arg in preprocess_argv)],
            cwd=kdm6_compile_dir, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        preprocess_log.write_text(preprocessed.stdout)
        if preprocessed.returncode:
            raise SystemExit("KDM6 preprocessing failed:\n" + preprocessed.stdout)
        generated.write_text(preprocessed.stdout)
        kdm6_compile_argv = list(parent_kdm6_argv)
        kdm6_compile_argv.remove("-fpp")
        kdm6_compile_argv[kdm6_compile_argv.index(parent_source_text)] = str(generated)
        kdm6_compile_argv[kdm6_compile_argv.index(parent_object_text)] = str(kdm6_object)
        run(kdm6_compile_argv, kdm6_compile_dir, compile_log)
        kdm6_row = {
            "member": "module_mp_kdm6.o",
            "source_path": str(PR84_KDM6_SOURCE),
            "source_sha256": sha256(PR84_KDM6_SOURCE),
            "patched_source_path": str(kdm6_source),
            "patched_source_sha256": sha256(kdm6_source),
            "generated_source_path": str(generated),
            "generated_source_sha256": sha256(generated),
            "object_path": str(kdm6_object),
            "object_sha256": sha256(kdm6_object),
            "compile_argv": kdm6_compile_argv,
            "compile_log_sha256": sha256(compile_log),
            "preprocess_argv": preprocess_argv,
            "preprocess_log_sha256": sha256(preprocess_log),
            "preprocessor_defines": [arg for arg in preprocess_argv if arg.startswith("-D")],
            "source_receipt_path": str(PR84_BUILD_RECEIPT),
            "source_receipt_sha256": sha256(PR84_BUILD_RECEIPT),
            "source_module_object_sha256": PR84_KDM6_MEMBER_SHA256,
            "compile_recipe_source_path": str(PR84_BUILD_RECEIPT),
            "compile_recipe_source_sha256": sha256(PR84_BUILD_RECEIPT),
            "patches": {
                "kdm6_sedimentation": {
                    "path": str(kdm6_sedimentation_patch),
                    "sha256": sha256(kdm6_sedimentation_patch),
                    "patch_log_sha256": sha256(kdm6_patch_log),
                }
            },
            "compile_recipe_source": "PR84 production_compile_argv",
            "compile_recipe_source_sha256": sha256(PR84_BUILD_RECEIPT),
        }
        compiled.append(kdm6_row)

    pbl_rows = []
    for (member, original, expected, patched_source, obj, argv, log, generated,
         preprocess_argv, preprocess_log, patch_names) in (
            ("module_bl_shinhong.o", PR74_SHINHONG_SOURCE,
             PR74_SHINHONG_SOURCE_SHA256, shinhong_source, shinhong_object,
             shinhong_compile_argv, shinhong_compile_log, shinhong_generated,
             shinhong_preprocess_argv, shinhong_preprocess_log, ("pbl_packet",)),
            ("module_bl_fogdes.o", PR61_FOG_SOURCE,
             PR61_FOG_SOURCE_SHA256, fog_source, fog_object,
             fog_compile_argv, fog_compile_log, fog_generated,
             fog_preprocess_argv, fog_preprocess_log, ("fog",)),
            ("module_pbl_driver.o", PR74_PBL_SOURCE,
             PR74_PBL_SOURCE_SHA256, pbl_capture_source, pbl_capture_object,
             pbl_capture_compile_argv, pbl_capture_log, pbl_capture_generated,
             pbl_capture_preprocess_argv, pbl_capture_preprocess_log,
             ("fog", "pbl_capture"))):
        if obj is None:
            continue
        patch_paths = {"fog": fog_patch,
                       "pbl_packet": pbl_packet_patch,
                       "pbl_capture": pbl_capture_patch}
        patch_provenance = {
            name: {"path": str(patch_paths[name]),
                   "sha256": sha256(patch_paths[name]),
                   "patch_log_sha256": sha256(pbl_patch_logs[name])}
            for name in patch_names
            if patch_paths[name] is not None and name in pbl_patch_logs
        }
        pbl_rows.append({
            "member": member,
            "source_path": str(original),
            "source_sha256": expected,
            "patched_source_path": str(patched_source),
            "patched_source_sha256": sha256(patched_source),
            "generated_source_path": str(generated),
            "generated_source_sha256": sha256(generated),
            "object_path": str(obj),
            "object_sha256": sha256(obj),
            "compile_argv": argv,
            "compile_log_sha256": sha256(log),
            "preprocess_argv": preprocess_argv,
            "preprocess_log_sha256": sha256(preprocess_log),
            "preprocessor_defines": [arg for arg in preprocess_argv if arg.startswith("-D")],
            "source_receipt_path": str(PR74_SOURCE_RECEIPT),
            "source_receipt_sha256": sha256(PR74_SOURCE_RECEIPT),
            "source_module_object_sha256": (
                PR74_PBL_OBJECT_SHA256 if member == "module_pbl_driver.o" else None),
            "patches": patch_provenance,
        })
    compiled.extend(pbl_rows)

    replacements = {
        "schema": "pr85_replacement_objects_v1",
        "replacements": [{
            "member": row["member"], "object_path": row["object_path"],
            "object_sha256": row["object_sha256"], "source_path": row["source_path"],
            "source_sha256": row["source_sha256"],
        } for row in compiled],
    }
    replacement_path = scratch / "pr85_transport_replacements.json"
    replacement_path.write_text(json.dumps(replacements, indent=2) + "\n")

    # Keep the PR84 archive order and replace only members compiled above.
    # The stage observer remains a standalone link object.
    candidate_archive = link_dir / "libwrflib_pr85.a"
    shutil.copy2(PR84_ARCHIVE, candidate_archive)
    archive_replacements = list(compile_members)
    if pbl_capture_object is not None:
        archive_replacements.append("module_pbl_driver.o")
    if shinhong_object is not None:
        archive_replacements.append("module_bl_shinhong.o")
    if fog_object is not None:
        archive_replacements.append("module_bl_fogdes.o")
    if kdm6_row is not None:
        archive_replacements.append("module_mp_kdm6.o")
    for member in archive_replacements:
        subprocess.run(["ar", "r", str(candidate_archive), str(compile_dir / member)],
                       cwd=link_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    parent_rows = archive_member_hashes(PR84_ARCHIVE)
    candidate_rows = archive_member_hashes(candidate_archive)
    if [name for name, _ in parent_rows] != [name for name, _ in candidate_rows]:
        raise SystemExit("candidate archive member order differs from PR84")
    changed_members = [name for (name, before), (_, after) in zip(parent_rows, candidate_rows)
                       if before != after]
    if sorted(changed_members) != sorted(archive_replacements):
        raise SystemExit(f"candidate archive changed unexpected members: {changed_members}")

    for name in ("wrf.o", "module_wrf_top.o"):
        source_object = PR84_LINK_MAIN / name
        if not source_object.is_file():
            raise SystemExit(f"retained PR84 link object is missing: {source_object}")
        shutil.copy2(source_object, link_dir / name)

    observer_object = compile_dir / "pr85_joint_stage_observer.o"
    observer_argv = list(base_argv)
    if "-O2" not in observer_argv:
        raise SystemExit("retained PR83 recipe does not expose the expected optimization flag")
    observer_argv[observer_argv.index("-O2")] = "-O0"
    observer_argv[-3:] = [str(observer_source), "-o", str(observer_object)]
    log = scratch / "pr85_joint_stage_observer.compile.log"
    run(observer_argv, compile_dir, log)
    observer_object_sha256 = sha256(observer_object)

    candidate_executable = scratch / "wrf_pr85.exe"
    archive_arg = next(path for path, digest in parent_receipt["production_link_dependencies_sha256"].items()
                       if digest == sha256(PR84_ARCHIVE))
    parent_cwd = Path(archive_arg).parent
    replacements = {
        parent_link_argv[parent_link_argv.index("-o") + 1]: str(candidate_executable),
        archive_arg: str(candidate_archive),
        str(parent_cwd / "wrf.o"): str(link_dir / "wrf.o"),
        str(parent_cwd / "module_wrf_top.o"): str(link_dir / "module_wrf_top.o"),
    }
    link_argv = [replacements.get(arg, arg) for arg in parent_link_argv]
    archive_slot = link_argv.index(str(candidate_archive)) + 1
    link_argv.insert(archive_slot, str(observer_object))
    link_log = scratch / "link.log"
    run(link_argv, link_dir, link_log)

    link_inputs = {}
    for old_path, expected_digest in parent_receipt["production_link_dependencies_sha256"].items():
        path = Path(old_path)
        if old_path in parent_link_argv and path.is_file():
            if sha256(path) != expected_digest:
                raise SystemExit(f"pinned PR84 link input changed: {path}")
            link_inputs[old_path] = expected_digest
    for arg in link_argv:
        path = Path(arg)
        if path.is_absolute() and path.is_file() and path.suffix in {".o", ".a"}:
            link_inputs[str(path)] = sha256(path)

    provenance = []
    for row in compiled:
        member = row["member"]
        base_member = next(digest for name, digest in parent_rows if name == member)
        provenance.append({
            **row,
            "baseline_archive_path": str(PR84_ARCHIVE),
            "baseline_archive_sha256": sha256(PR84_ARCHIVE),
            "baseline_member_sha256": base_member,
        })

    output = {
        "schema": "pr85_joint_moment_native_build_v1",
        "status": "PASS_SCOPED_BUILD",
        "scratch": str(scratch),
        "model_run": False,
        "builder_path": str(Path(__file__).resolve()),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "compiler_profile_path": str(PROFILE),
        "compiler_profile_sha256": sha256(PROFILE),
        "compiler_path": str(compiler),
        "compiler_sha256": sha256(compiler),
        "retained_pr83_compile_receipt": str(PR83_RECEIPT),
        "retained_pr83_compile_receipt_sha256": sha256(PR83_RECEIPT),
        "retained_pr84_archive": str(PR84_ARCHIVE),
        "retained_pr84_archive_sha256": sha256(PR84_ARCHIVE),
        "parent_executable_path": str(PR84_EXE),
        "parent_executable_sha256": sha256(PR84_EXE),
        "parent_archive_path": str(PR84_ARCHIVE),
        "parent_archive_sha256": sha256(PR84_ARCHIVE),
        "candidate_executable_path": str(candidate_executable),
        "candidate_executable_sha256": sha256(candidate_executable),
        "candidate_archive_path": str(candidate_archive),
        "candidate_archive_sha256": sha256(candidate_archive),
        "replaced_members": changed_members,
        "compiled_member_provenance": provenance,
        "ordered_parent_members": [list(row) for row in parent_rows],
        "ordered_candidate_members": [list(row) for row in candidate_rows],
        "observer_source_path": str(observer_source),
        "observer_source_sha256": sha256(observer_source),
        "observer_object_path": str(observer_object),
        "observer_object_sha256": observer_object_sha256,
        "observer_compile_argv": observer_argv,
        "observer_compile_log_sha256": sha256(log),
        "link_argv": link_argv,
        "link_argv_nul_sha256": argv_digest(link_argv),
        "link_cwd": str(link_dir),
        "link_log_sha256": sha256(link_log),
        "link_inputs_sha256": link_inputs,
        "compiler_version": version(compiler),
        "retained_kim_sources": {
            member: {"path": str(path), "sha256": digest}
            for member, (path, digest) in BASE_SOURCES.items()},
        "retained_pr84_members": BASE_OBJECTS,
        "solve_patch_path": str(patch),
        "solve_patch_sha256": sha256(patch),
        "boundary_patch_path": str(boundary_patch) if boundary_patch else None,
        "boundary_patch_sha256": sha256(boundary_patch) if boundary_patch else None,
        "boundary_patch_log_sha256": sha256(boundary_patch_log)
        if boundary_patch_log else None,
        "solve_tile_guard_patch_path": str(solve_tile_guard_patch)
        if solve_tile_guard_patch else None,
        "solve_tile_guard_patch_sha256": sha256(solve_tile_guard_patch)
        if solve_tile_guard_patch else None,
        "solve_tile_guard_patch_log_sha256": sha256(solve_tile_guard_patch_log)
        if solve_tile_guard_patch_log else None,
        "kernel_path": str(kernel),
        "kernel_sha256": sha256(kernel),
        "native_update_fragment_path": str(update_fragment),
        "native_update_fragment_sha256": sha256(update_fragment),
        "pbl_capture_patch_path": str(pbl_capture_patch) if pbl_capture_patch else None,
        "pbl_capture_patch_sha256": sha256(pbl_capture_patch) if pbl_capture_patch else None,
        "pbl_capture_source_path": str(pbl_capture_source) if pbl_capture_source else None,
        "pbl_capture_source_sha256": sha256(pbl_capture_source) if pbl_capture_source else None,
        "pbl_capture_source_receipt_path": str(PR74_SOURCE_RECEIPT) if pbl_capture_object else None,
        "pbl_capture_source_receipt_sha256": sha256(PR74_SOURCE_RECEIPT) if pbl_capture_object else None,
        "source_attribution_patch_path": str(source_attribution_patch)
        if source_attribution_patch else None,
        "source_attribution_patch_sha256": sha256(source_attribution_patch)
        if source_attribution_patch else None,
        "source_attribution_source_path": str(part2_source) if part2_source else None,
        "source_attribution_source_sha256": sha256(part2_source) if part2_source else None,
        "source_attribution_patch_log_sha256": sha256(source_attribution_patch_log)
        if source_attribution_patch_log else None,
        "ksas_source_patch_path": str(ksas_source_patch) if ksas_source_patch else None,
        "ksas_source_patch_sha256": sha256(ksas_source_patch) if ksas_source_patch else None,
        "ksas_source_patch_log_sha256": sha256(ksas_source_patch_log)
        if ksas_source_patch_log else None,
        "fog_patch_path": str(fog_patch) if fog_patch else None,
        "fog_patch_sha256": sha256(fog_patch) if fog_patch else None,
        "pbl_packet_patch_path": str(pbl_packet_patch) if pbl_packet_patch else None,
        "pbl_packet_patch_sha256": sha256(pbl_packet_patch) if pbl_packet_patch else None,
        "kdm6_sedimentation_patch_path": str(kdm6_sedimentation_patch)
        if kdm6_sedimentation_patch else None,
        "kdm6_sedimentation_patch_sha256": sha256(kdm6_sedimentation_patch)
        if kdm6_sedimentation_patch else None,
        "kdm6_sedimentation_patch_log_sha256": sha256(kdm6_patch_log)
        if kdm6_patch_log else None,
        "patch_log_sha256": sha256(patch_log),
        "compiled_objects": provenance,
        "supplemental_replacements": [],
        "replacement_manifest_path": str(replacement_path),
        "replacement_manifest_sha256": sha256(replacement_path),
    }
    receipt_path = scratch / "pr85_native_transport_build.json"
    receipt_path.write_text(json.dumps(output, indent=2) + "\n")
    print(f"PR85_TRANSPORT_OBJECTS_ROOT {scratch}")
    print(f"PR85_TRANSPORT_OBJECTS_RECEIPT {receipt_path}")
    print(f"PR85_TRANSPORT_REPLACEMENT_MANIFEST {replacement_path}")
    print(f"PR85_NATIVE_EXE {candidate_executable}")


if __name__ == "__main__":
    main()
