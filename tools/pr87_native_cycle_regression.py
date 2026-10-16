#!/usr/bin/env python3
"""Compile the native zero-out and FogDES routines in a pinned O0/O2 cycle test."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
FOGDES_SOURCE = Path("/var/tmp/pr85_native_joint_candidate_20261015v17/source/phys/module_bl_fogdes.F")
FOGDES_SHA256 = "aee27ecc6f259e94dfbb7cc8dad2ebd8cd97432d31363e268d1fedffa84bcc7d"
ZERO_OUT_SOURCE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys/module_microphysics_zero_out.F")
ZERO_OUT_SHA256 = "a57268701b424b07a604ce93f733314183a29bfb39e7e6283f92f8668808fa4f"
REGISTRY_SOURCE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/KIM-rdps_kfarms_port/KIM_RDPS_MODL_V2026.2/Registry/Registry.EM_COMMON")
REGISTRY_SHA256 = "4c8174711ed7ce50d4e04c3849254a77cbc963161aa42d6326ace4cf1fe0c700"
CYCLE_EVIDENCE = ROOT / "docs/evidence/pr87_state_cycle_20261016/post_kdm6_cycle.json"
EXPECTED_QC = 8.469214662909508e-09
EXPECTED_NC = 2021875.875


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_subroutine(source: str, name: str) -> str:
    start = re.search(rf"^\s*SUBROUTINE\s+{re.escape(name)}\s*\(", source,
                      flags=re.IGNORECASE | re.MULTILINE)
    if not start:
        raise ValueError(f"missing source subroutine {name}")
    end = re.search(rf"^\s*END\s+SUBROUTINE\s+{re.escape(name)}\b", source[start.start():],
                    flags=re.IGNORECASE | re.MULTILINE)
    if not end:
        raise ValueError(f"missing source terminator for {name}")
    return source[start.start():start.start() + end.end()].strip()


def cycle_values() -> tuple[float, float]:
    data = json.loads(CYCLE_EVIDENCE.read_text(encoding="utf-8"))
    if data.get("schema") != "pr87_post_kdm6_zero_out_cycle_v1":
        raise ValueError("unexpected saved-cycle evidence schema")
    off = data["arms"]["OFF"]["candidate_cells"]
    coupled = data["arms"]["COUPLED"]["candidate_cells"]
    if not off or off != coupled:
        raise ValueError("OFF/COUPLED candidate cells are missing or differ")
    cell = off[0]
    if cell["POST_KDM6_QC"] != EXPECTED_QC or cell["POST_KDM6_QNC"] != EXPECTED_NC:
        raise ValueError("saved-cycle candidate does not match the pinned regression values")
    if cell["POST_KDM6_QC"] >= data["arms"]["OFF"]["threshold"]:
        raise ValueError("saved-cycle QC is not below the host cutoff")
    return float(cell["POST_KDM6_QC"]), float(cell["POST_KDM6_QNC"])


def source_text(qc_value: float, nc_value: float, zero_outa: str,
                fogdes: str) -> str:
    qc_literal = f"{qc_value:.17e}"
    nc_literal = f"{nc_value:.17e}"
    return f"""MODULE module_model_constants
  REAL, PARAMETER :: g=9.81, rhowater=1000.0
END MODULE module_model_constants

MODULE module_state_description
  INTEGER, PARAMETER :: PARAM_FIRST_SCALAR=1, P_QV=1, P_QC=2, P_QI=3
  INTEGER, PARAMETER :: P_QR=4, P_QG=5, P_QS=6
END MODULE module_state_description

MODULE module_configure
  TYPE grid_config_rec_type
    INTEGER :: mp_zero_out=0, mp_zero_out_all=0
    REAL :: mp_zero_out_thresh=0.0
  END TYPE grid_config_rec_type
END MODULE module_configure

MODULE module_wrf_error
CONTAINS
  SUBROUTINE wrf_debug(level,message)
    INTEGER, INTENT(IN) :: level
    CHARACTER(*), INTENT(IN) :: message
  END SUBROUTINE wrf_debug
END MODULE module_wrf_error

MODULE module_zero_out_source
CONTAINS
{zero_outa}
END MODULE module_zero_out_source

MODULE module_fogdes_source
  USE module_model_constants
CONTAINS
{fogdes}
END MODULE module_fogdes_source

PROGRAM pr87_native_cycle_regression
  USE module_state_description
  USE module_configure
  USE module_zero_out_source
  USE module_fogdes_source
  IMPLICIT NONE
  CHARACTER(32) :: mode
  TYPE(grid_config_rec_type) :: config_flags
  REAL :: moist(1:1,1:3,1:1,6), scalar(1:1,1:3,1:1,2)
  REAL :: qv(1:1,1:3,1:1), temp(1:1,1:3,1:1), rho(1:1,1:3,1:1)
  REAL :: dz(1:1,1:3,1:1), dq(1:1,1:3,1:1), dn(1:1,1:3,1:1)
  REAL :: vdfg(1:1,1:1), ground_q(1:1,1:1), ground_n(1:1,1:1)
  REAL :: qc_before, nc_before, qs_before

  CALL get_command_argument(1,mode)
  config_flags%mp_zero_out=2
  config_flags%mp_zero_out_all=0
  config_flags%mp_zero_out_thresh=1.0e-8
  moist=0.0
  scalar=0.0
  qv=0.01
  temp=260.0
  rho=1.2
  dz=100.0
  dq=0.0
  dn=0.0
  vdfg=0.0
  moist(1,2,1,P_QV)=-1.0e-6
  moist(1,2,1,P_QC)={qc_literal}
  moist(1,2,1,P_QI)=5.0e-9
  moist(1,2,1,P_QR)=6.0e-9
  moist(1,2,1,P_QG)=7.0e-9
  moist(1,2,1,P_QS)=5.0e-9
  scalar(1,2,1,1)={nc_literal}
  scalar(1,2,1,2)=5.0e-9
  qv(1,2,1)=moist(1,2,1,P_QV)
  qc_before=moist(1,2,1,P_QC)
  nc_before=scalar(1,2,1,1)
  qs_before=moist(1,2,1,P_QS)

  IF (TRIM(mode)=='generic') THEN
    CALL microphysics_zero_outa(moist,6,config_flags,1,2,1,2,1,4, &
         1,1,1,1,1,3,1,1,1,1,1,3)
    IF (moist(1,2,1,P_QC)/=0.0 .OR. moist(1,2,1,P_QI)/=0.0 .OR. &
        moist(1,2,1,P_QR)/=0.0 .OR. moist(1,2,1,P_QG)/=0.0 .OR. &
        moist(1,2,1,P_QS)/=0.0 .OR. &
        moist(1,2,1,P_QV)/=0.0 .OR. scalar(1,2,1,1)/=nc_before) &
      ERROR STOP 'generic host cutoff did not match expected field policy'
    qv(1,2,1)=moist(1,2,1,P_QV)
    WRITE(*,'(a,4(1x,es24.16))') 'PR87_GENERIC_STATE',moist(1,2,1,P_QC), &
         qv(1,2,1),moist(1,2,1,P_QS),scalar(1,2,1,1)
  ELSE IF (TRIM(mode)=='preserved') THEN
    CALL microphysics_zero_outa(moist,6,config_flags,1,2,1,2,1,4, &
         1,1,1,1,1,3,1,1,1,1,1,3,preserve_paired_moisture=.TRUE.)
    IF (moist(1,2,1,P_QC)/=qc_before .OR. moist(1,2,1,P_QI)/=5.0e-9 .OR. &
        moist(1,2,1,P_QR)/=6.0e-9 .OR. moist(1,2,1,P_QG)/=7.0e-9 .OR. &
        scalar(1,2,1,1)/=nc_before .OR. moist(1,2,1,P_QS)/=0.0 .OR. &
        moist(1,2,1,P_QV)/=0.0) &
      ERROR STOP 'paired-only preservation changed the wrong moisture fields'
    config_flags%mp_zero_out_all=1
    CALL microphysics_zero_outa(scalar,2,config_flags,1,2,1,2,1,4, &
         1,1,1,1,1,3,1,1,1,1,1,3)
    IF (scalar(1,2,1,1)/=nc_before .OR. scalar(1,2,1,2)/=0.0) &
      ERROR STOP 'scalar cleanup behavior changed when optional arg is omitted'
    qv(1,2,1)=moist(1,2,1,P_QV)
    WRITE(*,'(a,4(1x,es24.16))') 'PR87_PRESERVED_STATE',moist(1,2,1,P_QC), &
         moist(1,2,1,P_QV),moist(1,2,1,P_QS),scalar(1,2,1,1)
  ELSE IF (TRIM(mode)/='before') THEN
    ERROR STOP 'unknown regression mode'
  ENDIF

  CALL fogdes_qn_stokes_flux(vdfg,moist(:,:,:,P_QC),scalar(:,:,:,1),qv,temp, &
       20.0,1.0,rho,dz,dq,dn,ground_q,ground_n,1,1,1,1,1,3,4,1,1,1,1,1,3)
  IF (TRIM(mode)=='generic') ERROR STOP 'generic cutoff unexpectedly reached FogDES'
  WRITE(*,'(a,1x,a)') 'PR87_FOGDES_ACCEPTED',TRIM(mode)
END PROGRAM pr87_native_cycle_regression

SUBROUTINE wrf_error_fatal(message)
  CHARACTER(*), INTENT(IN) :: message
  WRITE(*,'(a,1x,a)') 'PR87_EXPECTED_FOGDES_FATAL',TRIM(message)
  ERROR STOP 87
END SUBROUTINE wrf_error_fatal
"""


def run(argv: list[str], cwd: Path, log: Path) -> subprocess.CompletedProcess[str]:
    command = " ".join(shlex.quote(arg) for arg in argv)
    result = subprocess.run(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {command}"],
        cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    log.write_text(result.stdout, encoding="utf-8")
    return result


def profile_value(name: str) -> list[str]:
    if name not in ("CLOUD_BAL_FREE_FLAGS", "CLOUD_BAL_REPRO_FLAGS"):
        raise ValueError("unsupported pinned profile flags")
    output = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf '%s\\n' \"${{{name}[@]}}\""],
        text=True,
    )
    return output.splitlines()


def run_regression() -> dict:
    for path, expected in ((FOGDES_SOURCE, FOGDES_SHA256),
                           (ZERO_OUT_SOURCE, ZERO_OUT_SHA256),
                           (REGISTRY_SOURCE, REGISTRY_SHA256)):
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"pinned source unavailable or changed: {path}")
    registry = REGISTRY_SOURCE.read_text(encoding="utf-8")
    if not re.search(r"rconfig\s+integer\s+mp_zero_out_all\s+namelist,physics\s+1\s+0\b", registry):
        raise ValueError("pinned mp_zero_out_all default changed")
    if not re.search(r"rconfig\s+real\s+mp_zero_out_thresh\s+namelist,physics\s+1\s+1\.e-8\b", registry):
        raise ValueError("pinned mp_zero_out_thresh default changed")

    fogdes_text = FOGDES_SOURCE.read_text(encoding="utf-8")
    fogdes = extract_subroutine(fogdes_text, "fogdes_qn_stokes_flux")
    fixture_text = (ROOT / "tests/fixtures/pr85_fogdes_qn_stokes_source.F90").read_text(encoding="utf-8")
    if fogdes != extract_subroutine(fixture_text, "fogdes_qn_stokes_flux"):
        raise ValueError("FogDES helper differs from the existing source-form fixture")
    zero_out_source = ZERO_OUT_SOURCE.read_text(encoding="utf-8")
    zero_out_module = re.sub(r"\nEND MODULE module_microphysics_zero_out\s*$", "\n", zero_out_source,
                             flags=re.IGNORECASE)
    from pr87_prepare_native_cycle import zero_out_overlay
    zero_out = extract_subroutine(zero_out_overlay(zero_out_module), "microphysics_zero_outa")
    overlaid_module = zero_out_overlay(zero_out_module)
    zero_outb = extract_subroutine(zero_out_source, "microphysics_zero_outb")
    if extract_subroutine(overlaid_module, "microphysics_zero_outb") != zero_outb:
        raise ValueError("paired cleanup overlay changed boundary nonnegativity routine")
    qc_value, nc_value = cycle_values()
    generated_source = source_text(qc_value, nc_value, zero_out, fogdes)
    scratch = Path(tempfile.mkdtemp(prefix="pr87_native_cycle_", dir="/var/tmp"))
    source = scratch / "pr87_native_cycle.F90"
    source.write_text(generated_source, encoding="utf-8")
    ifx = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""],
        text=True,
    ).strip()
    results = {}
    for label, flag_name in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                             ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        build = scratch / label
        build.mkdir()
        exe = build / "pr87_native_cycle.exe"
        compile_argv = [ifx, *profile_value(flag_name), str(source), "-o", str(exe)]
        compiled = run(compile_argv, build, build / "compile.log")
        if compiled.returncode:
            raise RuntimeError(f"{label} compile failed:\n{compiled.stdout}")
        modes = {}
        for mode in ("before", "generic", "preserved"):
            work = build / mode
            work.mkdir()
            result = run([str(exe), mode], work, work / "run.log")
            if mode == "generic":
                if result.returncode == 0 or "PR87_EXPECTED_FOGDES_FATAL" not in result.stdout or \
                        "requires both cloud moments" not in result.stdout:
                    raise RuntimeError(f"{label} generic cutoff did not expose the unpaired-state fatal:\n{result.stdout}")
            elif result.returncode or f"PR87_FOGDES_ACCEPTED {mode}" not in result.stdout:
                raise RuntimeError(f"{label} {mode} paired FogDES call failed:\n{result.stdout}")
            modes[mode] = {"returncode": result.returncode, "stdout": result.stdout}
        results[label] = {
            "compile_argv": compile_argv,
            "executable_sha256": sha256(exe),
            "modes": modes,
        }
    return {
        "schema": "pr87_native_zero_out_fogdes_cycle_o0_o2_v1",
        "scratch": str(scratch),
        "runtime_model_call": False,
        "selected_POST_KDM6_cell": {"QC": qc_value, "QNC": nc_value},
        "source_identity": {
            "fogdes_source": str(FOGDES_SOURCE), "fogdes_sha256": FOGDES_SHA256,
            "zero_out_source": str(ZERO_OUT_SOURCE), "zero_out_sha256": ZERO_OUT_SHA256,
            "registry_source": str(REGISTRY_SOURCE), "registry_sha256": REGISTRY_SHA256,
            "overlay_generator": str(ROOT / "tools/pr87_prepare_native_cycle.py"),
            "overlay_generator_sha256": sha256(ROOT / "tools/pr87_prepare_native_cycle.py"),
            "cycle_evidence": str(CYCLE_EVIDENCE), "cycle_evidence_sha256": sha256(CYCLE_EVIDENCE),
            "fixture_helper_matches_pinned_fogdes_helper": True,
        },
        "compiler_profile": str(PROFILE), "ifx": ifx,
        "source_mechanism": {
            "host_cutoff": "Actual microphysics_zero_outa source with mp_zero_out=2 and pinned 1.e-8 threshold; mp_zero_out_all=0 leaves QNC scalar unprocessed.",
            "preserved_case": "Applies the generator's optional paired-only species-loop skip to QC/QI/QR/QG; QV is still clamped and QS is still thresholded, then the same saved positive QC/QNC pair reaches the actual FogDES helper.",
            "other_channel_probe": "With mp_zero_out_all=1, scalar cleanup called without the optional argument still thresholds a non-QNC scalar while preserving the positive QNC value.",
            "boundary_policy": "The overlay leaves microphysics_zero_outb byte-for-byte unchanged, retaining its boundary nonnegativity clamp.",
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_regression()
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
