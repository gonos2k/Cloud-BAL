#!/usr/bin/env python3
"""Pinned Intel regression for the REAL64 PR87 horizontal m-diffusion helper."""
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
HELPER = ROOT / "tools/pr87_horizontal_diffusion64.f90"
TEST = ROOT / "tests/test_pr87_horizontal_diffusion64.f90"
UPSTREAM = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/"
    "KIM_RDPS_MODL_V2026.2/dyn_em/module_big_step_utilities_em.F"
)
UPSTREAM_FILE_SHA256 = "27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c"
UPSTREAM_PROCEDURE_SHA256 = "cbcc347345a6449b9e5666407c5ef8c6a0db73a9a397d0e306ad14a085783ac3"
HELPER_SHA256 = "0a8b2865fff3d7ad6592e0d1bc1d3f7b51970de13ac9ea128066b7cba655bfe3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_procedure(text: str) -> str:
    start = re.search(r"^SUBROUTINE\s+horizontal_diffusion\s*\(", text,
                      re.IGNORECASE | re.MULTILINE)
    if not start:
        raise RuntimeError("pinned upstream horizontal_diffusion procedure was not found")
    tail = text[start.start():]
    end = re.search(r"^END SUBROUTINE horizontal_diffusion\b", tail,
                    re.IGNORECASE | re.MULTILINE)
    if not end:
        raise RuntimeError("pinned upstream horizontal_diffusion terminator was not found")
    return tail[:end.end()]


def assert_upstream_mapping() -> dict[str, str]:
    if sha256(UPSTREAM) != UPSTREAM_FILE_SHA256:
        raise RuntimeError("upstream module_big_step_utilities_em.F hash changed")
    procedure = extract_procedure(UPSTREAM.read_text(encoding="utf-8"))
    procedure_sha = hashlib.sha256(procedure.encode()).hexdigest()
    if procedure_sha != UPSTREAM_PROCEDURE_SHA256:
        raise RuntimeError("upstream horizontal_diffusion procedure hash changed")
    normalized = re.sub(r"\s+|&", "", procedure).lower()
    required = (
        "elseif(name.eq.'w')then",  # The target `m` implementation is the default ELSE branch.
        "mkrdxm=(msfux(i,j)/msfuy(i,j))*0.5*(xkmhd(i,k,j)+xkmhd(i-1,k,j))*",
        "0.5*((c1(k)*mut(i,j)+c2(k))+(c1(k)*mut(i-1,j)+c2(k)))*rdx",
        "mkrdym=(msfvy(i,j)*msfvx_inv(i,j))*0.5*(xkmhd(i,k,j)+xkmhd(i,k,j-1))*",
        "0.5*((c1(k)*mut(i,j)+c2(k))+(c1(k)*mut(i,j-1)+c2(k)))*rdy",
        "mrdx=msftx(i,j)*msfty(i,j)*rdx",
        "mrdy=msftx(i,j)*msfty(i,j)*rdy",
        "mrdx*(mkrdxp*(field(i+1,k,j)-field(i,k,j))-mkrdxm*(field(i,k,j)-field(i-1,k,j)))",
        "mrdy*(mkrdyp*(field(i,k,j+1)-field(i,k,j))-mkrdym*(field(i,k,j)-field(i,k,j-1)))",
    )
    missing = [fragment for fragment in required if fragment not in normalized]
    if missing:
        raise RuntimeError(f"upstream m-stencil mapping assertions failed: {missing}")
    return {"upstream_file_sha256": UPSTREAM_FILE_SHA256,
            "upstream_procedure_sha256": procedure_sha}


def profile(name: str) -> tuple[str, list[str]]:
    if name not in ("CLOUD_BAL_FREE_FLAGS", "CLOUD_BAL_REPRO_FLAGS"):
        raise ValueError(f"unsupported compiler profile: {name}")
    source = f"source {shlex.quote(str(PROFILE))}; printf '%s\\n' \"${{{name}[@]}}\""
    flags = subprocess.check_output(["bash", "-lc", source], text=True).splitlines()
    compiler = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""],
        text=True,
    ).strip()
    return compiler, flags


def run(command: list[str], cwd: Path, logfile: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    logfile.write_text(result.stdout, encoding="utf-8")
    return result


def execute(receipt_path: Path) -> dict[str, object]:
    if receipt_path.exists():
        raise FileExistsError(f"refusing to overwrite receipt: {receipt_path}")
    upstream = assert_upstream_mapping()
    if HELPER_SHA256 == "PENDING" or sha256(HELPER) != HELPER_SHA256:
        raise RuntimeError("helper hash is not frozen in this runner")
    scratch = Path(tempfile.mkdtemp(prefix="pr87_horizontal_diffusion64_", dir="/var/tmp"))
    results: dict[str, object] = {}
    for level, flag_name in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                             ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        compiler, flags = profile(flag_name)
        work = scratch / level
        work.mkdir()
        executable = work / "test_pr87_horizontal_diffusion64.exe"
        compile_log = work / "compile.log"
        compiled = run([compiler, *flags, str(HELPER), str(TEST), "-o", str(executable)],
                       work, compile_log)
        if compiled.returncode:
            raise RuntimeError(f"{level} pinned Intel compile failed:\n{compiled.stdout}")
        run_log = work / "run.log"
        runtime = f"source {shlex.quote(str(PROFILE))}; {shlex.quote(str(executable))}"
        tested = run(["bash", "-lc", runtime], work, run_log)
        if tested.returncode or "PR87_DIFFUSION64_PASS" not in tested.stdout:
            raise RuntimeError(f"{level} helper regression failed:\n{tested.stdout}")
        results[level] = {
            "compiler": compiler,
            "compiler_sha256": sha256(Path(compiler)),
            "flags": flags,
            "compile_log": str(compile_log),
            "compile_log_sha256": sha256(compile_log),
            "executable": str(executable),
            "executable_sha256": sha256(executable),
            "run_log": str(run_log),
            "run_log_sha256": sha256(run_log),
            "stdout": tested.stdout.strip(),
            "status": "PASS",
        }
    return {
        "schema": "pr87_horizontal_diffusion64_ifx_o0_o2_v1",
        "status": "PASS_O0_O2",
        "helper": str(HELPER),
        "helper_sha256": sha256(HELPER),
        "test_source": str(TEST),
        "test_source_sha256": sha256(TEST),
        "mapping": upstream,
        "tests": ["zero_field", "constant_field", "nonuniform_face_coefficients",
                  "active_bounds_zeroed", "closed_area_weighted_face_cancellation",
                  "exact_dyadic_shared_QN_mixing", "R32_crosses_strict_lower_bound_R64_passes"],
        "fresh_scratch": str(scratch),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    evidence = execute(args.receipt)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(f"PASS_O0_O2: {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
