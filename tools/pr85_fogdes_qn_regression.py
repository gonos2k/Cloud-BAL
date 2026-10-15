#!/usr/bin/env python3
"""Compile the patched FogDES Q/N source-form routine with pinned Intel ifx."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
PATCH = ROOT / "patches/pr85_fogdes_qn_stokes.patch"
FIXTURE = ROOT / "tests/fixtures/pr85_fogdes_qn_stokes_source.F90"
PATCH_SHA256 = "bc7bb6241218919a7ec51c4f9e30b2d732e6db64b0e5c1d2dc8ea687516c0789"
FIXTURE_SHA256 = "a886f80ac31477d41c9e8d7fef1fc084a5553af2bb03957b929685eee4592ed5"
FOGDES_BASE_SHA256 = "94d6b4ed3f82c6d7ca9b14107ee07af8ace058dd65f7e07ab5fa0ab8ea1b0ed7"
PBL_BASE_SHA256 = "342378285d929d06aa88b3c47b27c906bac05e560244162e4f946481ea4bd322"
PBL_CALLER_BASE_SHA256 = "b3d0c70397edd6a20162c55cbd988fe21e4c8aee484fb3b1da72760487e95d63"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patched_helper() -> str:
    lines = PATCH.read_text().splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("+  SUBROUTINE fogdes_qn_stokes_flux("))
    added = []
    for line in lines[start:]:
        if not line.startswith("+"):
            raise SystemExit("FogDES source patch helper is interrupted by a context line")
        added.append(line[1:])
        if line.startswith("+  END SUBROUTINE fogdes_qn_stokes_flux"):
            break
    else:
        raise SystemExit("FogDES source patch helper has no end statement")
    return "\n".join(added) + "\n"


def fixture_helper() -> str:
    source = FIXTURE.read_text()
    start = source.index("  SUBROUTINE fogdes_qn_stokes_flux(")
    end = source.index("  END SUBROUTINE fogdes_qn_stokes_flux", start)
    end += len("  END SUBROUTINE fogdes_qn_stokes_flux")
    return source[start:end] + "\n"


def verify_applied_driver_hook(scratch: Path, required: bool) -> dict:
    """Apply the patch to pinned PR74 sources and verify its real call routing."""
    sources = {
        "phys/module_bl_fogdes.F": (Path("/var/tmp/pr85_fogdes_work/base/module_bl_fogdes.F"),
                                    FOGDES_BASE_SHA256),
        "phys/module_pbl_driver.F": (Path("/var/tmp/pr74_shinhong_qni_driver.GvfcGi/O0/compile/module_pbl_driver.F"),
                                     PBL_BASE_SHA256),
        "dyn_em/module_first_rk_step_part1.F": (Path("/var/tmp/pr85_fogdes_work/base/module_first_rk_step_part1.F"),
                                                 PBL_CALLER_BASE_SHA256),
    }
    missing = []
    for source, expected_hash in sources.values():
        if not source.is_file():
            missing.append(str(source))
        elif sha(source) != expected_hash:
            raise SystemExit(f"pinned driver source mismatch: {source}")
    if missing:
        if required:
            raise SystemExit("pinned driver sources unavailable: " + ", ".join(missing))
        return {"status": "NOT_RUN_EXTERNAL_BASE_UNAVAILABLE", "missing_paths": missing}
    for relative, (source, expected_hash) in sources.items():
        destination = scratch / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    applied = subprocess.run(
        ["patch", "--fuzz=0", "-p1", "-i", str(PATCH)], cwd=scratch,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if applied.returncode:
        raise SystemExit("FogDES patch failed on pinned driver sources:\n" + applied.stdout)
    driver = (scratch / "phys/module_pbl_driver.F").read_text()
    caller = (scratch / "dyn_em/module_first_rk_step_part1.F").read_text()
    fog_start = driver.index("! KDM6 uses a conditional paired-Q/N research closure")
    fog_end = driver.index("!JOE-END", fog_start)
    fog_branch = driver[fog_start:fog_end]
    required = {
        "typed mp_physics dummy": "INTEGER,    INTENT(IN   )    ::     mp_physics" in driver,
        "MP37 paired FogDES call": "CALL bl_fogdes_qn(" in fog_branch,
        "non-MP37 legacy FogDES path": bool(re.search(
            r"ELSE\s+CALL bl_fogdes\(vdfg,qc_curr", fog_branch, re.IGNORECASE)),
        "paired FogDES ground ledgers": "ground_q_sink=fogdes_ground_q_sink" in fog_branch and
                                        "ground_n_sink=fogdes_ground_n_sink" in fog_branch,
        "MP37-only packet flag at Shinhong call":
            ",PR85_PACKET_ENABLED=(mp_physics .EQ. 37)" in driver,
        "BLDT/STEPBL cadence guard": "PR85 KDM6 Shinhong packet gate requires BLDT=0" in driver and
                                      "PR85 KDM6 Shinhong packet gate requires BLDT=0 or STEPBL=1" in driver,
        "caller passes the required physics argument": "MP_PHYSICS=config_flags%mp_physics" in caller,
    }
    missing = [label for label, present in required.items() if not present]
    if missing:
        raise SystemExit("applied PBL driver routing is incomplete: " + ", ".join(missing))
    return {"status": "PASS_PINNED_SOURCE_PATCH_APPLICATION"}


def run(argv: list[str], cwd: Path, log: Path) -> str:
    command = " ".join(shlex.quote(arg) for arg in argv)
    result = subprocess.run(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {command}"],
        cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(f"command failed ({result.returncode}): {command}\n{result.stdout}")
    return result.stdout


def verify_patch_driver_hook() -> None:
    """Keep the driver dispatch in the regression even without private sources."""
    driver_diff = PATCH.read_text().split("--- a/phys/module_pbl_driver.F", 1)[1]
    driver_diff = driver_diff.split("--- a/dyn_em/", 1)[0]
    added_or_context = "\n".join(line[1:] for line in driver_diff.splitlines()
                                 if line.startswith(("+", " ")) and not line.startswith("+++"))
    for required in ("IF (mp_physics .EQ. 37)", "CALL bl_fogdes_qn(",
                     "ground_q_sink=fogdes_ground_q_sink", "ground_n_sink=fogdes_ground_n_sink",
                     "CALL bl_fogdes(vdfg,qc_curr", "::     mp_physics",
                     "PR85_PACKET_ENABLED=(mp_physics .EQ. 37)"):
        if required not in added_or_context:
            raise SystemExit("FogDES driver overlay is missing: " + required)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pinned-driver", action="store_true",
                        help="fail unless the retained native driver sources are available")
    args = parser.parse_args()
    if sha(PATCH) != PATCH_SHA256:
        raise SystemExit("FogDES source patch SHA mismatch")
    if sha(FIXTURE) != FIXTURE_SHA256:
        raise SystemExit("FogDES source-form fixture SHA mismatch")
    if patched_helper() != fixture_helper():
        raise SystemExit("FogDES fixture helper differs from the added actual-source routine")
    removed = [line[1:] for line in PATCH.read_text().splitlines()
               if line.startswith("-") and not line.startswith("---")]
    if any("SUBROUTINE bl_fogdes(" in line for line in removed):
        raise SystemExit("FogDES patch changes the legacy bl_fogdes interface")
    if "SUBROUTINE bl_fogdes_qn(" not in PATCH.read_text():
        raise SystemExit("FogDES patch does not provide its separate paired-Q/N entry point")
    scratch = Path(tempfile.mkdtemp(prefix="pr85_fogdes_qn_", dir="/var/tmp"))
    verify_patch_driver_hook()
    driver_validation = verify_applied_driver_hook(scratch / "pinned_source", args.require_pinned_driver)
    source = scratch / "source.F90"
    source.write_bytes(FIXTURE.read_bytes())
    ifx = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""],
        text=True,
    ).strip()
    results: dict[str, dict[str, object]] = {}
    for label, flags_name in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                              ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        build = scratch / label
        build.mkdir()
        exe = build / "pr85_fogdes_qn.exe"
        argv = [ifx, *(["-check", "all"] if label == "O0" else []),
                str(source), "-o", str(exe)]
        flag_words = subprocess.check_output(
            ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf '%s\\n' \"${{{flags_name}[@]}}\""],
            text=True,
        ).splitlines()
        argv = [ifx, *flag_words, str(source), "-o", str(exe)]
        run(argv, build, build / "compile.log")
        output = run([str(exe)], build, build / "run.log")
        if "PR85 source-form FogDES paired Stokes cases PASS" not in output:
            raise SystemExit(f"FogDES paired Stokes fixture failed at {label}: {output}")
        budget = build / "pr85_fogdes_budget.raw"
        if not budget.is_file():
            raise SystemExit(f"FogDES fixture did not write its process budget at {label}")
        budget_text = budget.read_text()
        if "PR85_FOGDES_BUDGET_META" not in budget_text or \
                "PR85_FOGDES_BUDGET_UNITS local_rho_dry_times_dz" not in budget_text or \
                "PR85_FOGDES_BUDGET" not in budget_text:
            raise SystemExit(f"FogDES process budget is missing metadata or rows at {label}")
        results[label] = {
            "compile_argv": argv,
            "executable_sha256": sha(exe),
            "budget_path": str(budget),
            "budget_sha256": sha(budget),
            "budget_rows": sum(line.startswith("PR85_FOGDES_BUDGET ") for line in budget_text.splitlines()),
            "stdout": output,
        }
    print(json.dumps({
        "schema": "pr85_fogdes_qn_stokes_source_form_o0_o2_v2",
        "scratch": str(scratch),
        "runtime_model_call": False,
        "driver_source_validation": driver_validation,
        "research_closure": "conditional MP37/F_QNC only; generalized-gamma alpha=3, Stokes Q/N moments",
        "pbl_interface_extension": "required mp_physics dummy and paired dispatch edits checked; actual source-application status is driver_source_validation",
        "legacy_bl_fogdes_interface_unchanged": True,
        "patch_path": str(PATCH),
        "patch_sha256": sha(PATCH),
        "pinned_base_sources": {
            "module_bl_fogdes.F": FOGDES_BASE_SHA256,
            "module_pbl_driver.F": PBL_BASE_SHA256,
            "module_first_rk_step_part1.F": PBL_CALLER_BASE_SHA256,
        },
        "fixture_path": str(FIXTURE),
        "fixture_sha256": sha(FIXTURE),
        "compiler_profile": str(PROFILE),
        "compiler_profile_sha256": sha(PROFILE),
        "ifx": ifx,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
