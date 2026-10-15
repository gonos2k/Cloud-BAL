#!/usr/bin/env python3
"""Pinned-Intel regression for atomic PR85 subthreshold snowmelt pairing."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_pr85_kdm6_subthreshold_melt() -> None:
    patch = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
    helper = ROOT / "tools/pr85_kdm6_subthreshold_melt.F90"
    fixture = ROOT / "tests/fixtures/pr85_kdm6_subthreshold_melt.F90"
    patch_lines = patch.read_text().splitlines()
    additions = "\n".join(
        line[1:] for line in patch_lines if line.startswith("+") and not line.startswith("+++")
    )
    helper_lines = helper.read_text().splitlines()
    assert any(
        additions.splitlines()[index : index + len(helper_lines)] == helper_lines
        for index in range(len(additions.splitlines()) - len(helper_lines) + 1)
    ), "the combined KDM6 patch must append the exact tested melt helper"
    for source_contract in (
        "if (qrs(i,k,2).gt.qcrmin) then",
        "sfac = (rslope(i,k,2))*n0so(i,k)*n0sfac(i,k)/qrs(i,k,2)",
        "nrs(i,k,1) = nrs(i,k,1) - sfac*psmlt(i,k)",
        "call pr85_kdm6_subthreshold_melt",
        "if (pr85_melt_accepted .and. pr85_melt_route.ne.0) then",
        "pr85_melt_qs_candidate=DBLE(qrs(i,k,2))+DBLE(psmlt(i,k))",
        "pr85_melt_t_candidate=DBLE(pr85_melt_t_before)+",
        "cpm(i,k).le.0.0",
        "pr85_melt_qs_after.ge.pr85_melt_q_before",
        "qrs(i,k,2) = pr85_melt_qs_after",
        "t(i,k) = pr85_melt_t_after",
        "pr85_melt_mass_residual = pr85_melt_mass_actual-pr85_melt_mass_request",
        "error stop 'PR85 positive snowmelt has no supported liquid pair'",
        "file='pr85_kdm6_melt_budget.raw'",
        "file='pr85_ice_transition_branch.raw'",
        "'PR85_ICE_TRANSITION_LOOP',loop,lat,its,ite,kts,kte,dtcld",
        "executedQI",
        "'PR85_ICE_TRANSITION',i,lat,k,loop,dtcld",
    ):
        assert source_contract in additions, f"missing source contract: {source_contract}"
    assert additions.index("pr85_melt_qs_candidate=DBLE(qrs(i,k,2))") < additions.index(
        "qci(i,k,1) = pr85_melt_qc_after"
    ), "snow and temperature preflight must precede the six-state commit"
    assert additions.index("file='pr85_kdm6_melt_budget.raw'") < additions.index(
        "error stop 'PR85 positive snowmelt has no supported liquid pair'"
    ), "an unsupported positive melt must be ledgered before the fatal rejection"
    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_melt_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        argv = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free '
            '"$3" "$4" -o "$5/pr85_kdm6_subthreshold_melt.exe" && '
            '"$5/pr85_kdm6_subthreshold_melt.exe"',
            "pr85-kdm6-melt-test", str(ROOT), optimization, str(helper), str(fixture), str(build),
        ]
        result = subprocess.run(argv, cwd=build, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        if optimization == "O2":
            assert "warning #10182" not in result.stdout.lower(), result.stdout
        assert "PR85 KDM6 subthreshold melt cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("helper_sha256=" + hashlib.sha256(helper.read_bytes()).hexdigest())
    print("fixture_sha256=" + hashlib.sha256(fixture.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_subthreshold_melt()
    print("PR85 KDM6 subthreshold melt test PASS")
