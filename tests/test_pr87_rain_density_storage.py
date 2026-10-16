from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_rain_density_storage import (  # noqa: E402
    V19_SOLVE_SHA256,
    extend_rain_density_storage,
)


ROOT = Path(__file__).resolve().parents[1]
V19_SOLVE = ROOT / "docs/evidence/pr87_two_step_v19_20261016/solve_em.F.gz"
WRAPPER = ROOT / "tools/pr87_rain_density_store.f90"
INTEL_PROFILE = ROOT / "tests/intel_toolchain.sh"


def test_density_repair_is_inserted_at_completed_rk_stage() -> None:
    source = gzip.decompress(V19_SOLVE.read_bytes()).decode()
    assert hashlib.sha256(source.encode()).hexdigest() == V19_SOLVE_SHA256

    result = extend_rain_density_storage(source)
    call = "CALL pr87_rain_density_store(grid%itimestep,rk_step, &"
    assert result.count(call) == 1
    hook = result.index(call)
    call_end = result.index("\n         IF (.NOT.pr87_rain_density_valid)", hook)
    call_block = result[hook:call_end]
    assert "ims,ime,kms,kme,jms,jme, &\n" in call_block
    assert (
        "max(ids+1,grid%i_start(ij)),min(ide-2,grid%i_end(ij)), &\n"
        "              max(jds+1,grid%j_start(ij)),min(jde-2,grid%j_end(ij)), &\n"
        "              k_start,min(k_end,kde-1),grid%al,grid%alb, &\n"
    ) in call_block
    wrapper = WRAPPER.read_text()
    assert (
        "subroutine pr87_rain_density_store(itimestep,rk_step,ims,ime,kms,kme,jms,jme, &\n"
        "     its,ite,jts,jte,kts,kte,"
    ) in wrapper
    observer = result.index("CALL pr85_joint_stage_dump('RK_STAGE_END'")
    first_calc = result.index("CALL calc_p_rho_phi(")
    second_calc = result.index("CALL calc_p_rho_phi(", first_calc + 1)
    rk_end = result.index("END DO Runge_Kutta_loop")
    assert first_calc < hook < observer < rk_end < second_calc

    assert "moist(ims,kms,jms,P_QR),scalar(ims,kms,jms,P_QNR)" in result
    assert "max(ids+1,grid%i_start(ij)),min(ide-2,grid%i_end(ij))" in result
    assert "max(jds+1,grid%j_start(ij)),min(jde-2,grid%j_end(ij))" in result
    assert "k_start,min(k_end,kde-1)" in result
    assert "12566.37109375,3.0,961.0,35000.0" in result


def test_generator_rejects_nonfrozen_solve_source() -> None:
    source = gzip.decompress(V19_SOLVE.read_bytes()).decode()
    with pytest.raises(ValueError, match="preimage differs"):
        extend_rain_density_storage(source + "\n")


def test_prepare_cli_requires_rain_diffusion_precision(tmp_path: Path) -> None:
    script = ROOT / "tools/pr87_prepare_native_cycle.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output",
            str(tmp_path / "candidate"),
            "--rain-density-storage",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "updated-density rain storage requires the selected precision overlay" in result.stderr


def test_rain_density_wrapper_with_pinned_intel_o0_o2() -> None:
    kernel = ROOT / "src/common/cloud_bal_joint_transport.f90"
    public_store = ROOT / "tools/pr87_rain_public_store.f90"
    observer = ROOT / "tools/pr85_joint_stage_observer.f90"
    fixture = ROOT / "tests/test_pr87_rain_density_storage.f90"
    source_paths = [kernel, public_store, observer, WRAPPER, fixture, INTEL_PROFILE]
    scratch = Path(tempfile.mkdtemp(prefix="pr87_rain_density_wrapper_", dir="/var/tmp"))
    receipt = {
        "schema": "pr87_rain_density_wrapper_ifx_v1",
        "sources": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "runs": {},
    }

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash",
            "-c",
            'set -euo pipefail; source "$1/tests/intel_toolchain.sh"; '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi; '
            'printf "IFX_VERSION="; "$CLOUD_BAL_FC" --version | sed -n "1p"; '
            'printf "IFX_SHA256="; sha256sum "$CLOUD_BAL_FC" | cut -d" " -f1; '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$5" -I "$5" '
            '"$3" "$4" "$6" "$7" "$8" -o "$5/test.exe"; '
            '"$5/test.exe"',
            "pr87-rain-density-wrapper-test",
            str(ROOT),
            profile,
            str(kernel),
            str(public_store),
            str(build),
            str(observer),
            str(WRAPPER),
            str(fixture),
        ]
        result = subprocess.run(
            command,
            cwd=build,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path = build / "run.log"
        log_path.write_text(result.stdout)
        assert result.returncode == 0, result.stdout
        pass_marker = "PASS rain-density tile transaction, Q-only commit, and rejection rollback"
        assert pass_marker in result.stdout, result.stdout
        compiler_version = "IFX_VERSION=ifx (IFX) 2026.0.0 20260331"
        compiler_sha = "IFX_SHA256=909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"
        assert compiler_version in result.stdout, result.stdout
        assert compiler_sha in result.stdout, result.stdout
        receipt["runs"][profile] = {
            "returncode": result.returncode,
            "pass_marker": pass_marker,
            "compiler_version": compiler_version.removeprefix("IFX_VERSION="),
            "compiler_sha256": compiler_sha.removeprefix("IFX_SHA256="),
            "log": str(log_path),
            "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        }

    receipt_path = scratch / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PR87 rain-density wrapper O0/O2 PASS: {receipt_path}")

