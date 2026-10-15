#!/usr/bin/env python3
"""Compile the exact native grouped updater and shared operator in a small fixture."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
FRAGMENT = ROOT / "tools/pr85_native_joint_update.f90"
MOCK = ROOT / "tests/pr85_state_description_stub.f90"
JOINT_OPERATOR = ROOT / "src/common/cloud_bal_joint_transport.f90"
OBSERVER = ROOT / "tools/pr85_joint_stage_observer.f90"
DRIVER = ROOT / "tests/test_pr85_native_air_operator.f90"


def compile_and_run() -> None:
    scratch_root = Path(os.environ.get("CLOUD_BAL_TEST_SCRATCH_ROOT", "/var/tmp"))
    scratch_root.mkdir(parents=True, exist_ok=True)
    fragment = FRAGMENT.read_text()
    source = "MODULE native_joint_adapter\n  USE module_state_description, ONLY: P_QV\n  IMPLICIT NONE\nCONTAINS\n" + fragment + "\nEND MODULE native_joint_adapter\n"
    with tempfile.TemporaryDirectory(prefix="pr85_native_air_", dir=scratch_root) as tmp:
        work = Path(tmp)
        adapter = work / "native_joint_adapter.f90"
        adapter.write_text(source)
        executable = work / "test_pr85_native_air_operator"
        compile_argv = [
            "$CLOUD_BAL_FC", "${CLOUD_BAL_FREE_FLAGS[@]}",
            "-module", shlex.quote(str(work)), "-I", shlex.quote(str(work)),
            shlex.quote(str(MOCK)),
            shlex.quote(str(JOINT_OPERATOR)),
            shlex.quote(str(adapter)), shlex.quote(str(OBSERVER)), shlex.quote(str(DRIVER)),
            "-o", shlex.quote(str(executable)),
        ]
        command = "source " + shlex.quote(str(PROFILE)) + " && " + " ".join(compile_argv)
        built = subprocess.run(["bash", "-lc", command], cwd=work, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if built.returncode:
            raise SystemExit(f"native grouped updater compile failed:\n{built.stdout}")
        run_command = "source " + shlex.quote(str(PROFILE)) + " && exec " + shlex.quote(str(executable))
        result = subprocess.run(["bash", "-lc", run_command], cwd=work, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"native grouped updater fixture failed:\n{result.stdout}")
        if "PR85_NATIVE_AIR_OPERATOR_PASS" not in result.stdout:
            raise SystemExit(f"native grouped updater omitted its pass marker:\n{result.stdout}")
        state_path = work / "pr85_joint_moment_stages.raw"
        state_bytes = state_path.read_bytes()
        if state_bytes[:8] != b"PR85QND2":
            raise SystemExit("native observer did not emit the dry-density PR85QND2 format")
        recorded_density = struct.unpack("=f", state_bytes[100:104])[0]
        if recorded_density != 2.0:
            raise SystemExit(f"observer did not write 1/(AL+ALB): {recorded_density}")
        for mode, marker in (("invalid-density", "PR85 invalid AL+ALB dry density"),
                             ("invalid-observer", "PR85 invalid AL+ALB stage density")):
            invalid_command = "source " + shlex.quote(str(PROFILE)) + " && " + \
                shlex.quote(str(executable)) + " " + mode
            invalid = subprocess.run(["bash", "-lc", invalid_command], cwd=work, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if invalid.returncode == 0 or marker not in invalid.stdout:
                raise SystemExit(f"invalid AL+ALB did not fail closed in {mode}:\n"
                                 f"{invalid.stdout}")
        print("PR85_NATIVE_AIR_OPERATOR_PASS "
              f"updater_sha256={hashlib.sha256(FRAGMENT.read_bytes()).hexdigest()} "
              f"operator_sha256={hashlib.sha256(JOINT_OPERATOR.read_bytes()).hexdigest()}")
        print(result.stdout.strip())


if __name__ == "__main__":
    compile_and_run()
