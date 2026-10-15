#!/usr/bin/env python3
"""Pinned-Intel source-form regression for coupled KDM6 cold-process admission."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pr85_kdm6_cold_process_source.F90"
SOURCE_CONTRACT = ROOT / "tests/fixtures/pr85_kdm6_cold_warm_source_contract.json"
PATCH = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
PROCEDURES = (
    "kdm6_rain_process_fraction",
    "kdm6_rain_process_state_valid",
)


def _procedure(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(rf"\s*subroutine\s+{name}\s*\(", line, re.I)),
        None,
    )
    assert start is not None, f"missing {name} procedure"
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(rf"\s*end\s+subroutine\s+{name}\s*$", lines[i], re.I)
        ),
        None,
    )
    assert end is not None, f"missing end of {name} procedure"
    return "\n".join(lines[start : end + 1])


def _patch_source(path: Path) -> str:
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", " ")):
            lines.append(line[1:])
    return "\n".join(lines)


def _check_procedure_contract(fixture_text: str, patch: Path) -> str | None:
    contract = json.loads(SOURCE_CONTRACT.read_text())
    patch_sha = hashlib.sha256(patch.read_bytes()).hexdigest()
    assert patch_sha == contract["patch_sha256"], "source-contract patch identity mismatch"
    constant = re.sub(r"\s+", "", contract["inactive_ice_limit_declaration"]).lower()
    assert constant in re.sub(r"\s+", "", fixture_text).lower(), (
        "cold fixture does not bind the native inactive-ice limit constant"
    )
    for name in PROCEDURES:
        fixture_body = _procedure(fixture_text, name)
        body_sha = hashlib.sha256(fixture_body.encode()).hexdigest()
        assert body_sha == contract["procedure_sha256"][name], (
            f"fixture {name} differs from verified patch-derived procedure contract"
        )
    source_path = os.environ.get("PR85_KDM6_APPLIED_SOURCE")
    if source_path:
        applied = Path(source_path)
        assert applied.is_file(), f"PR85_KDM6_APPLIED_SOURCE is not a file: {applied}"
        applied_text = applied.read_text()
        for name in PROCEDURES:
            assert _procedure(fixture_text, name) == _procedure(applied_text, name), (
                f"fixture {name} differs byte-for-byte from optional applied source {applied}"
            )
        return hashlib.sha256(applied.read_bytes()).hexdigest()
    return None


def _check_composite_transaction_source(source_text: str) -> None:
    uncommented = re.sub(r"!.*$", "", source_text, flags=re.MULTILINE)
    compact = re.sub(r"[\s&]+", "", uncommented).lower()
    expected_rates = (
        "pracw", "piacw", "pmulcs", "pmulcg", "pmulrs", "pmulrg", "prevp",
        "psdep", "pidep", "pinud", "psaut", "psaci", "nccol", "nracw",
        "niacw", "ninud", "nmulcs", "nmulcg", "nmulrs", "nmulrg", "nsaci",
        "nsaut", "nrcol", "praut", "nraut", "paacw", "naacw", "pracs",
        "praci", "piacr", "psacr", "pgacr", "pgdep", "pgaci", "pgaut",
        "pgacs", "nraci", "niacr", "nsacr", "ngacr", "ngaci",
    )
    start = compact.index("rain_composite_rate_base=[")
    end = compact.index("]", start)
    rate_map = compact[start:end]
    actual_rates = tuple(re.findall(r"([a-z0-9_]+)\(i,k\)", rate_map))
    assert actual_rates == expected_rates, (
        "composite retry rate snapshot changed or omits a native transaction rate"
    )

    loop_start = compact.index("dorain_composite_retry=0,24")
    loop_end = compact.index("enddo", loop_start)
    trial = compact[loop_start:loop_end]
    assert "rain_composite_gamma=1.0" in compact[:loop_start]
    assert "rain_composite_gamma=0.5*rain_composite_gamma" in trial
    assert "rain_composite_gamma=0.0" in trial
    assert "callkdm6_rain_process_state_valid(rain_q_after,rain_n_after" in trial
    assert "rain_composite_valid=rain_stored_state_feasible" in trial
    assert "if(rain_composite_valid)exit" in trial
    for index, rate in enumerate(expected_rates, start=1):
        assignment = f"{rate}(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma"
        assert assignment in trial, f"composite retry does not rescale snapshot slot {index} ({rate})"
        assert f"{rate}(i,k)=" in trial

    native_ni = (
        "rain_n_after(2)=nci(i,k,2)+(-nraci(i,k)-nsaci(i,k)-ngaci(i,k)-niacr(i,k)"
        "+ninud(i,k)+nmulcs(i,k)+nmulcg(i,k)+nmulrs(i,k)+nmulrg(i,k)"
        "-nsaut(i,k))*dtcld"
    )
    native_qi = (
        "rain_q_after(2)=qci(i,k,2)-(psaut(i,k)+praci(i,k)+psaci(i,k)+pgaci(i,k)"
        "-pinud(i,k)-pidep(i,k)-piacw(i,k)-pmulcs(i,k)-pmulcg(i,k)"
        "-pmulrs(i,k)-pmulrg(i,k))*dtcld"
    )
    assert native_ni in trial, "composite candidate no longer uses native-order NI equation"
    assert native_qi in trial, "composite candidate no longer uses native-order QI equation"

    for conversion in (
        "biacr(i,k)=piacr(i,k)*(1.-delta3)/denr",
        "braci(i,k)=praci(i,k)*(1.-delta3)/deni",
        "bsacr(i,k)=psacr(i,k)*(1.-delta2)/denr",
        "bracs(i,k)=pracs(i,k)*(1.-delta2)/dens",
        "baacw(i,k)=paacw(i,k)/denr",
        "bgaci(i,k)=pgaci(i,k)/deni",
        "bgacr(i,k)=pgacr(i,k)/denr",
        "callkdm6_mass_volume_rate(pgdep(i,k),rhox(i,k),rain_pgdep_bg_rate",
    ):
        assert conversion in trial, f"retry does not recompute derived volume rate: {conversion}"

    pending_transfer = (
        "if(rain_full_evap_pending(i,k).and.rain_q_after(3).eq.0.0)then"
        "rain_n_ccn_transfer=rain_n_after(3)"
    )
    assert pending_transfer in trial, "pending rain cleanup must transfer number only at exact zero mass"
    commit = compact.index("q(i,k)=rain_qv_after", loop_end)
    assert commit > loop_end
    assert compact.index("qci(i,k,1)=rain_q_after(1)", commit) > commit


def _check_cold_ledger_source(source_text: str) -> None:
    uncommented = re.sub(r"!.*$", "", source_text, flags=re.MULTILINE)
    compact = re.sub(r"[\s&]+", "", uncommented).lower()
    assert "write(pr85_cold_unit,'(a,8i8,1x,l1,1p,*(1x,e24.16))'" in compact
    assert "'#pr85_kdm6_coldfields:i,lat,k,loop,ngsearchstatus,autsearchstatus,gsearchstatus,compositeretry,storednoop;'" in compact
    assert "thendtcld,rhodry,compositegamma,scaledrates(41)real32,alphang,alphaaut,alphag;" in compact
    assert "'pr85_kdm6_cold',i,lat,k,loop,rain_ng_search_status," in compact
    assert "rain_aut_search_status,rain_process_search_status,rain_composite_retry," in compact
    assert "rain_composite_stored_noop,dtcld,dry_carrier_density(i,k),rain_composite_gamma," in compact
    assert "rain_composite_rate_base*rain_composite_gamma," in compact
    assert "rain_ng_alpha,rain_aut_alpha,rain_process_alpha," in compact

    noop_start = compact.index("rain_composite_stored_noop=(")
    noop_end = compact.index("!commit", noop_start) if "!commit" in compact[noop_start:] else compact.index("q(i,k)=rain_qv_after", noop_start)
    noop = compact[noop_start:noop_end]
    clauses = (
        "(rain_ng_alpha.gt.0.0.and.(any(rain_ng_q_process.ne.0.0).or.any(rain_ng_n_process.ne.0.0).or.rain_ng_bg_process.ne.0.0.or.rain_ng_t_process.ne.0.0.or.rain_ng_qv_process.ne.0.0))",
        "(rain_aut_alpha.gt.0.0.and.(any(rain_aut_q_process.ne.0.0).or.any(rain_aut_n_process.ne.0.0)))",
        "(rain_g_alpha.gt.0.0.and.(any(rain_q_process_request.ne.0.0).or.any(rain_n_process_request.ne.0.0).or.rain_bg_process_request.ne.0.0.or.rain_t_process_request.ne.0.0.or.rain_g_qv_process.ne.0.0))",
    )
    for clause in clauses:
        assert clause in noop, f"stored-noop predicate lost same-group alpha/request binding: {clause}"
    assert "all(rain_composite_rate_base*rain_composite_gamma.eq.0.0)" in noop
    assert "rain_ng_alpha.gt.0.0.or.rain_aut_alpha.gt.0.0" not in noop, (
        "stored-noop must not combine an active alpha from one group with a request from another"
    )


def _check_transient_ice_source(source_text: str) -> None:
    uncommented = re.sub(r"!.*$", "", source_text, flags=re.MULTILINE)
    compact = re.sub(r"[\s&]+", "", uncommented).lower()

    # The optional limit is strict by default and bounded by the native
    # greatest REAL32 value below the source's 1.e-14 inactive-ice cutoff.
    assert "real,intent(in),optional::ice_transient_mass_limit" in compact
    assert "ice_transient_limit=0.0d0" in compact
    assert "ice_transient_mass_limit.gt.pr85_ice_native_inactive_max" in compact
    assert "pr85_ice_native_inactive_max=nearest(1.e-14,-1.0)" in compact
    assert "calladd_breakpoint(q0(2),dq(2),ice_transient_limit)" in compact
    assert "if(q(2).gt.ice_transient_limit)then" in compact
    validator_start = compact.index("subroutinekdm6_rain_process_state_valid")
    # A source patch contains changed/context hunk lines, not the untouched
    # tail of the full routine. Inspect the included validator hunk through
    # its final available context rather than requiring an artificial END.
    validator = compact[validator_start:]
    bounds_start = validator.index("rain_min=real(density")
    cone_checks = validator[bounds_start:]
    cloud_start = cone_checks.index("if(q(1).eq.0.0)then")
    ice_start = cone_checks.index("if(q(2).eq.0.0)then", cloud_start)
    rain_start = cone_checks.index("if(q(3).eq.0.0)then", ice_start)
    nonnegative_start = cone_checks.index("if(q(4).lt.0.0.or.q(5).lt.0.0)", rain_start)
    cloud_branch = cone_checks[cloud_start:ice_start]
    ice_branch = cone_checks[ice_start:rain_start]
    rain_branch = cone_checks[rain_start:nonnegative_start]
    assert "ice_min*q(2)" in ice_branch and "ice_max*q(2)" in ice_branch
    assert "ice_transient_limit" in ice_branch
    assert "cloud_min*q(1)" in cloud_branch and "cloud_max*q(1)" in cloud_branch
    assert "rain_min*q(3)" in rain_branch and "rain_max*q(3)" in rain_branch
    assert "ice_transient_limit" not in cloud_branch and "ice_transient_limit" not in rain_branch

    # Only the three cold reaction groups and their fixed/candidate checks opt in.
    assert compact.count("ice_transient_mass_limit=pr85_ice_native_inactive_max") == 8
    for fragment in (
        "rain_ng_search_status,rain_qv_before,rain_ng_qv_process,ice_transient_mass_limit=pr85_ice_native_inactive_max",
        "rain_aut_search_status,rain_qv_stage,0.0,ice_transient_mass_limit=pr85_ice_native_inactive_max",
        "rain_process_search_status,rain_qv_stage,rain_g_qv_process,ice_transient_mass_limit=pr85_ice_native_inactive_max",
        "rain_stored_state_feasible,rain_full_evap_pending(i,k),ice_transient_mass_limit=pr85_ice_native_inactive_max",
    ):
        assert fragment in compact, f"cold transient opt-in is missing: {fragment}"

    # Final cutoff code is unchanged baseline context and therefore is not
    # present in the focused patch. Its write layout is checked only when a
    # caller supplies a complete applied KDM6 source below.

def test_pr85_kdm6_cold_process() -> None:
    fixture_text = FIXTURE.read_text()
    patch = PATCH
    assert patch.is_file(), f"missing KDM6 source patch: {patch}"
    applied_sha = _check_procedure_contract(fixture_text, patch)
    production_text = Path(os.environ["PR85_KDM6_APPLIED_SOURCE"]).read_text() if applied_sha else _patch_source(patch)

    _check_composite_transaction_source(production_text)
    _check_cold_ledger_source(production_text)
    _check_transient_ice_source(production_text)
    compact = re.sub(r"\s+", "", production_text).lower()
    for contract in (
        "rain_ng_q_process(1)=-(pracw(i,k)+piacw(i,k)+pmulcs(i,k)+pmulcg(i,k))*dtcld",
        "rain_aut_q_process(1)=-praut(i,k)*dtcld",
        "rain_g_q_process(1)=-2.*paacw(i,k)*dtcld",
        "rain_g_q_process(5)=(pgdep(i,k)+pgaut(i,k)+pgaci(i,k)+pgacs(i,k)",
        "rain_ng_qv_process=-(prevp(i,k)+psdep(i,k)+pidep(i,k)+pinud(i,k))*dtcld",
        "rain_g_qv_process=-pgdep(i,k)*dtcld",
        "rain_g_bg_process=(rain_pgdep_bg_rate+rain_pgaci_bg_rate",
        "rain_ng_t_process=(xls*(psdep(i,k)+pidep(i,k)+pinud(i,k))",
        "rain_g_t_process=(xls*pgdep(i,k)+xlf*(2.*paacw(i,k)",
        "rain_pracs_bg_rate*(1.-delta2)",
        "rain_piacr_bg_rate*(1.-delta3)",
        "rain_praci_bg_rate*(1.-delta3)",
        "rain_psacr_bg_rate*(1.-delta2)",
        ):
        assert contract in compact, f"cold-process source is missing {contract}"

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_cold_process_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        fixture_copy = build / "fixture.F90"
        fixture_copy.write_bytes(FIXTURE.read_bytes())
        command = [
            "bash",
            "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/test.exe" && '
            '"$4/test.exe"',
            "pr85-kdm6-cold-process-test",
            str(ROOT),
            optimization,
            "fixture.F90",
            str(build),
        ]
        result = subprocess.run(
            command,
            cwd=build,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR85 KDM6 cold process cases PASS" in result.stdout
        if optimization == "O2":
            assert "#10182" not in result.stdout, result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("fixture_sha256=" + hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
    if applied_sha:
        source_path = os.environ["PR85_KDM6_APPLIED_SOURCE"]
        source_after = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
        assert source_after == applied_sha, "applied source changed during cold test run"
        print("applied_source_sha256=" + applied_sha)


if __name__ == "__main__":
    test_pr85_kdm6_cold_process()
    print("PR85 KDM6 cold-process test PASS")
