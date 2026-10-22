#!/usr/bin/env python3
"""Replay one captured candidate through the pinned C1 store and group predicates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pr99_group_failure_capture as capture


SOURCE = Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F")
SOURCE_SHA256 = "f88708844994a30540fc458aeede7e0eda4503a04a341caf714050e52f8c18af"
PROFILE = Path(__file__).resolve().parents[1] / "tests/intel_toolchain.sh"
PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def r32(bits: str) -> str:
    return f"transfer(int(z'{bits}',int32),0.0_real32)"


def r64(bits: str) -> str:
    return f"transfer(int(z'{bits}',int64),0.0_real64)"


def profile_metadata(flag_set: str) -> tuple[str, list[str], str, str]:
    shell = (
        'source "$1"; if [[ $2 == FREE ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
        'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi; '
        'printf "FC=%s\\n" "$CLOUD_BAL_FC"; printf "FLAG=%s\\n" "${flags[@]}"'
    )
    result = subprocess.run(["bash", "-c", shell, "pr99-profile", str(PROFILE), flag_set],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"could not read pinned profile: {result.stdout}")
    compiler = next(row[3:] for row in result.stdout.splitlines() if row.startswith("FC="))
    flags = [row[5:] for row in result.stdout.splitlines() if row.startswith("FLAG=")]
    version = subprocess.run([compiler, "--version"], text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=False).stdout.splitlines()[0]
    return compiler, flags, version, sha256(Path(compiler))


def generate_driver(event: dict) -> str:
    h = event["hex"]
    q_expected, n_expected = h["HEX64_CANDIDATE"]
    old, new, density, dt = h["HEX32_CARRIERS_DT"]
    qb, nb = h["HEX32_BASE"]
    qs, ns = h["HEX64_SOURCE_RATE"]
    qt, nt = h["HEX64_TRANSPORT_RATE"]
    min_mass, max_mass = h["HEX64_MASS_BOUNDS"]
    vol_min, vol_max = h["HEX64_NUMBER_BOUNDS"]
    inactive_limit = h["HEX64_INACTIVE_MASS_LIMIT"][0]
    pair = event["pair"]
    if pair not in {1, 2, 3, 4}:
        raise ValueError(f"unsupported pair index {pair}")
    options = event["options"]
    if options["OPT_source_first_fallback"] != (event["attempt"] == "SOURCE_FIRST"):
        raise ValueError("attempt label and source-first option disagree")
    expected_flags = {
        "OPT_joint_constrained_storage": True,
        "OPT_joint_quantum_absence": True,
        "OPT_normal_q_adjustment": True,
    }
    if any(options[name] != value for name, value in expected_flags.items()):
        raise ValueError("captured storage options do not match the C1 constrained-store contract")
    if pair == 2:
        if not options["OPT_inactive_mass_pair"] or not options["OPT_inactive_q_quantum_pair"]:
            raise ValueError("pair 2 requires the recorded inactive-mass options")
        if inactive_limit == "0000000000000000":
            raise ValueError("pair 2 requires a positive recorded inactive-mass cutoff")
    elif options["OPT_inactive_mass_pair"] or options["OPT_inactive_q_quantum_pair"]:
        raise ValueError("inactive-mass options are only valid for pair 2")
    has_volume = pair in {1, 3}
    if not options["OPT_number_pair_bounds"]:
        raise ValueError("C1 capture must record the supplied number-pair bounds array")
    if options["OPT_strict_mass_pair"] != (pair == 4):
        raise ValueError("recorded strict-mass option does not match pair contract")
    if not options["OPT_bulk_volume_quantum_storage"]:
        raise ValueError("C1 capture must record the supplied bulk-volume storage option")

    optional_args = ["allow_normal_q_adjustment=.true.",
                     "allow_joint_quantum_absence=.true.",
                     f"strict_mass_ratio={'.true.' if pair == 4 else '.false.'}"]
    if has_volume:
        optional_args.append(f"volume_number_bounds=[{r64(vol_min)},{r64(vol_max)}]")
    if pair == 2:
        optional_args.extend((f"inactive_mass_limit={r64(inactive_limit)}",
                              "allow_inactive_q_quantum_adjustment=.true."))
    if pair == 4:
        optional_args.append("allow_bulk_volume_quantum_storage=.true.")
    optional_args.append("failure_stage=stage")
    optional_lines = ", &\n      ".join(optional_args)
    return f"""program scalar_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_moment_store, pr99_replay_group_predicates
  implicit none
  real(real64) :: qbase,nbase,qsrc,nsrc,qtr,ntr,dt64,qcalc,ncalc
  real(real64) :: minmass,maxmass
  real(real32) :: oldc,newc,density,storedq,storedn,groupq,groupn
  integer, parameter :: pair={pair}
  integer :: adjustment,stage
  integer :: replay_predicate
  logical :: valid,pair_valid,volume_valid
  oldc={r32(old)}
  newc={r32(new)}
  density={r32(density)}
  qbase=real({r32(qb)},real64); nbase=real({r32(nb)},real64)
  dt64=real({r32(dt)},real64)
  qsrc={r64(qs)}
  nsrc={r64(ns)}
  qtr={r64(qt)}
  ntr={r64(nt)}
  minmass={r64(min_mass)}; maxmass={r64(max_mass)}
  qcalc=(real(oldc,real64)*qbase+dt64*(qsrc+qtr))/real(newc,real64)
  ncalc=(real(oldc,real64)*nbase+dt64*(nsrc+ntr))/real(newc,real64)
  write(*,'(A,2(1X,Z16.16))') 'RECOMPUTED_CANDIDATE',transfer(qcalc,0_int64),transfer(ncalc,0_int64)
  call joint_moment_store(qcalc,ncalc,density,minmass,maxmass,.true.,storedq,storedn, &
      adjustment,valid, &
      {optional_lines})
  write(*,'(A,1X,I0,2(1X,Z8.8),1X,I0,1X,L1)') 'STORE_RESULT',stage, &
      transfer(storedq,0_int32),transfer(storedn,0_int32),adjustment,valid
  groupq=storedq; groupn=storedn
  if (.not.valid) then
    groupq=-1.0_real32; groupn=-1.0_real32
  end if
  write(*,'(A,2(1X,Z8.8))') 'GROUP_INPUT',transfer(groupq,0_int32),transfer(groupn,0_int32)
  call pr99_replay_group_predicates(groupq,groupn,density,minmass,maxmass, &
      {r64(inactive_limit)},pair==2,pair==4, &
      [{r64(vol_min)},{r64(vol_max)}],pair==1 .or. pair==3, &
      pair_valid,volume_valid,replay_predicate)
  write(*,'(A,1X,I0,1X,L1,1X,L1)') 'GROUP_RESULT',replay_predicate,pair_valid,volume_valid
end program scalar_replay
"""


def instrumented_core(source: str) -> str:
    """Expose the frozen module's private grouped predicates to this replay driver."""
    end = "end module cloud_bal_joint_transport"
    if source.count(end) != 1:
        raise ValueError("receipt-pinned C1 core module boundary is ambiguous")
    public = "  public :: joint_moment_is_valid, joint_moment_is_valid64, joint_moment_store, joint_qnb_update"
    if source.count(public) != 1:
        raise ValueError("receipt-pinned C1 core public interface is ambiguous")
    source = source.replace(public, public + ", pr99_replay_group_predicates", 1)
    wrapper = """
  subroutine pr99_replay_group_predicates(q,n,dry_density,minimum_ratio,maximum_ratio, &
      inactive_mass_limit,has_inactive,strict_mass,volume_bounds,has_volume,pair_valid,volume_valid,predicate)
    real(real32), intent(in) :: q,n,dry_density
    real(real64), intent(in) :: minimum_ratio,maximum_ratio,inactive_mass_limit,volume_bounds(2)
    logical, intent(in) :: has_inactive,strict_mass,has_volume
    logical, intent(out) :: pair_valid,volume_valid
    integer, intent(out) :: predicate
    if (has_inactive) then
      pair_valid=joint_moment_is_valid(q,n,dry_density,minimum_ratio,maximum_ratio,inactive_mass_limit)
    else
      pair_valid=joint_moment_is_valid(q,n,dry_density,minimum_ratio,maximum_ratio)
    end if
    if (strict_mass) pair_valid=strict_mass_ratio_valid64( &
        real(q,real64),real(n,real64),minimum_ratio,maximum_ratio)
    volume_valid=.true.
    if (has_volume) volume_valid=volume_number_stored_contract_valid(q,n,dry_density,volume_bounds)
    predicate=0
    if (.not.pair_valid) then
      predicate=1
    else if (.not.volume_valid) then
      predicate=2
    end if
  end subroutine pr99_replay_group_predicates

"""
    return source.replace(end, wrapper + end, 1)


def run_one(event: dict, source: str, flag_set: str, raw_sha: str) -> dict:
    compiler, flags, version, compiler_sha = profile_metadata(flag_set)
    with tempfile.TemporaryDirectory(prefix=f"pr99-scalar-{flag_set.lower()}-", dir="/var/tmp") as tmp:
        work = Path(tmp)
        core = instrumented_core(source)
        module_end = core.index("end module cloud_bal_joint_transport") + len(
            "end module cloud_bal_joint_transport")
        (work / "core.f90").write_text(core[:module_end] + "\n")
        core_sha = hashlib.sha256((work / "core.f90").read_bytes()).hexdigest()
        (work / "driver.f90").write_text(generate_driver(event))
        exe = work / "scalar_replay.exe"
        compile_argv = [compiler, *flags, "-free", "core.f90", "driver.f90", "-module",
                        str(work), "-o", str(exe)]
        build = subprocess.run(compile_argv, cwd=work, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)
        result = build
        run_argv = ["bash", "-c", 'source "$1" && exec "$2"',
                    "pr99-scalar-runtime", str(PROFILE), str(exe)]
        if build.returncode == 0:
            result = subprocess.run(run_argv, cwd=work, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError(json.dumps({"optimization": flag_set, "compiler": compiler,
                                           "compiler_version": version,
                                           "compiler_sha256": compiler_sha,
                                           "profile_sha256": PROFILE_SHA256,
                                           "compile_argv": compile_argv,
                                           "build_stdout": build.stdout,
                                           "run_stdout": result.stdout,
                                           "driver_sha256": hashlib.sha256(
                                               (work / "driver.f90").read_bytes()).hexdigest()},
                                          indent=2))
        lines = [line.split() for line in result.stdout.splitlines()
                 if line.startswith(("RECOMPUTED_CANDIDATE", "STORE_RESULT", "GROUP_INPUT", "GROUP_RESULT"))]
        if (len(lines) != 4 or len(lines[0]) != 3 or len(lines[1]) != 6
                or len(lines[2]) != 3 or len(lines[3]) != 4):
            raise RuntimeError(f"unexpected scalar replay output:\n{result.stdout}")
        candidate_hex = [x.upper() for x in lines[0][1:]]
        store = lines[1]
        group_input = lines[2]
        group = lines[3]
        result_row = {"optimization": flag_set, "candidate_hex": candidate_hex,
                      "store_failure_stage": int(store[1]),
                      "store_output_hex": [x.upper() for x in store[2:4]],
                      "group_predicate_input_hex": [x.upper() for x in group_input[1:]],
                      "adjustment": int(store[4]), "valid": store[5].upper() in {"T", ".TRUE."},
                      "replayed_group_predicate": int(group[1]),
                      "replayed_pair_valid": group[2].upper() in {"T", ".TRUE."},
                      "replayed_volume_valid": group[3].upper() in {"T", ".TRUE."},
                      "captured_store_succeeded": event["store_succeeded"],
                      "executable_sha256": sha256(exe), "raw_capture_sha256": raw_sha,
                      "compiler": compiler, "compiler_version": version,
                      "compiler_sha256": compiler_sha, "profile_sha256": PROFILE_SHA256,
                      "profile_flags": flags, "compile_argv": compile_argv,
                      "run_argv": run_argv, "build_stdout": build.stdout,
                      "run_stdout": result.stdout,
                      "driver_sha256": hashlib.sha256((work / "driver.f90").read_bytes()).hexdigest(),
                      "instrumented_core_sha256": core_sha,
                      "replay_adapter": "visibility-only wrapper calls frozen private grouped predicates"}
        expected = event["hex"]["HEX64_CANDIDATE"]
        if candidate_hex != expected:
            raise ValueError("recomputed candidate differs from captured exact bits: "
                             f"{candidate_hex} != {expected}\n{json.dumps(result_row, indent=2)}")
        if result_row["store_failure_stage"] != event["store_failure_stage"]:
            raise ValueError("replayed store failure stage differs from captured event\n" +
                             json.dumps(result_row, indent=2))
        if result_row["group_predicate_input_hex"] != event["hex"]["HEX32_STORED"]:
            raise ValueError("replayed grouped-predicate input bits differ from captured event\n" +
                             json.dumps(result_row, indent=2))
        if result_row["valid"] != event["store_succeeded"]:
            raise ValueError("replayed store validity differs from captured event boolean\n" +
                             json.dumps(result_row, indent=2))
        if result_row["replayed_group_predicate"] != event["group_predicate"]:
            raise ValueError("replayed first grouped predicate differs from captured event\n" +
                             json.dumps(result_row, indent=2))
        result_row["group_predicate_reached"] = True
        result_row["group_predicate_input"] = (
            "stored REAL32 values" if result_row["valid"] else
            "(-1,-1) REAL32 sentinel installed by form_candidate after store failure")
        return result_row


def replay(path: Path, event_index: int = 0) -> dict:
    raw_sha = sha256(path)
    parsed = capture.parse_capture(path)
    if event_index < 0 or event_index >= parsed["event_count"]:
        raise ValueError(f"event index {event_index} outside capture count {parsed['event_count']}")
    if not SOURCE.is_file() or sha256(SOURCE) != SOURCE_SHA256:
        raise ValueError("receipt-pinned original C1 source is unavailable or has changed")
    source = SOURCE.read_text()
    event = parsed["events"][event_index]
    return {"schema": "pr99_group_failure_scalar_replay_v2", "raw_capture_sha256": raw_sha,
            "capture_event_count": parsed["event_count"], "selected_event_index": event_index,
            "c1_source_sha256": SOURCE_SHA256,
            "replay_adapter_sha256": hashlib.sha256(instrumented_core(source).encode()).hexdigest(),
            "event_key": list(event["key"]),
            "captured_store_failure_stage": event["store_failure_stage"],
            "captured_group_predicate": event["group_predicate"],
            "captured_post_graupel_mixture_feasible": event["post_graupel_mixture_feasible"],
            "captured_group_predicate_input_hex": event["hex"]["HEX32_STORED"],
            "runs": [run_one(event, source, level, raw_sha) for level in ("FREE", "REPRO")],
            "interpretation": "scalar local replay only; no forecast causality claim"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--event-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(args.capture, args.event_index)
    except Exception as error:
        failure_path = args.output.with_suffix(args.output.suffix + ".failure.log")
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(str(error) + "\n")
        raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
