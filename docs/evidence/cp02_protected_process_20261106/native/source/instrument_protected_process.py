#!/usr/bin/env python3
"""Build the paired, selected-column CP04 diagnostic without changing physics."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / "docs/evidence/cp02_protected_process_20261106"
CP04_BASE = ROOT / "docs/evidence/cp02_thermo_cloud_path_20261105/native/source/module_mp_kdm6_FIX.f90"
ARCHIVES = {
    "OLD": Path("/var/tmp/firsthour-runtime-plan-20261030/experiment/build_BASE/module_mp_kdm6.f90"),
    "FIX": Path("/var/tmp/firsthour-runtime-plan-20261030/experiment/build_FIX/module_mp_kdm6.f90"),
}
ARCHIVE_SHA = {
    "OLD": "c4a7d1e90ea27608ba7efb652cfb79dee2e30db769e076ad1a2e7a7e63d5e52b",
    "FIX": "0b468be19f7dd66ad2f6e65a53b42f10391a4565831a96c80dddddf21934cf79",
}
PROFILE = ROOT / "tests/intel_toolchain.sh"
PROFILE_SHA = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
CP03_TEMPLATE_SHA = "605b2d6895229f287dd6dc675b84dea0596f7a247a18bf80e3615635defb0295"
CP04_TEMPLATE_SHA = "93e7575701655cd5fead8c40d316e6292f29c0ef7c9594380ee8a55d2dbcf0f5"
CP04_INSTRUMENTER = ROOT / "docs/evidence/cp02_thermo_cloud_path_20261105/native/source/instrument_cp04.py"
CP04_INSTRUMENTER_SHA = "8465eb90296660ab93e1b50f5d697c8191b8eada6b96299b50738c3b8e118175"
COHORT = EVIDENCE / "cohorts/unique_global_corners.csv"
COHORT_RECEIPT = EVIDENCE / "cohorts/receipt.json"
COHORT_SHA = "62b365cb0cc57b7b6006d8f6f760021f7424b94d7b381b507aeed093a9664b58"
POINTS = EVIDENCE / "cohorts/point_corners.csv"
POINTS_SHA = "12a000e1dab5963f7327cce49a44e988940b8e1c208049dd7f5285f126e85ea9"
ROLES = EVIDENCE / "cohorts/role_membership.csv"
ROLES_SHA = "54cbe13a13a7494fdaf10159919c480f90dfad26dcdcf8337735828d05132cb6"
COHORT_RECEIPT_SHA = "cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826"
WINDOWS = ((1, 360), (721, 900))
CHUNK_STEPS = 3

STATE = ['p(i,k)', 'q(i,k)', 't(i,k)', 'den(i,k)', 'qci(i,k,1)', 'qci(i,k,2)',
         'qrs(i,k,1)', 'qrs(i,k,2)', 'qrs(i,k,3)', 'nci(i,k,1)', 'nci(i,k,2)',
         'nci(i,k,3)', 'nrs(i,k,1)', 'nrs(i,k,2)', 'nrs(i,k,3)', 'brs(i,k)']
RATE_NAMES = ['praut','pracw','prevp','piacr','pgacr','psacr','pmulrs','pmulrg',
              'pseml','pgeml','psevp','pgevp','psdep','pgdep','pinud','pidep',
              'paacw','piacw','pmulcs','pmulcg','psaut','pgaut','praci','psaci',
              'pgaci','pgacs','pracs','nraut','nccol','nracw','naacw','niacw',
              'nrcol','nraci','nsacr','ngacr','nseml','ngeml','niacr']
SED_PRE = ['p(i,k)','q(i,k)','t(i,k)','qci(i,k,1)','qci(i,k,2)',
           'qrs(i,k,1)','qrs(i,k,2)','qrs(i,k,3)','nrs(i,k,1)',
           'den(i,k)','dend(i,k)','delz(i,k)','dtcld','brs(i,k)',
           'nci(i,k,1)','nci(i,k,2)','nci(i,k,3)','fall(i,k,1)',
           'fall(i,k,2)','fall(i,k,3)','falln(i,k,1)','fallb(i,k)']
SED_POST = SED_PRE + ['falk(i,k,1)','falk(i,k,2)','falk(i,k,3)','falkn(i,k,1)','falkb(i,k)']
COND = ['p(i,k)','q(i,k)','t(i,k)','qs(i,k,1)','qci(i,k,1)','qci(i,k,2)',
        'nci(i,k,1)','nci(i,k,2)','nci(i,k,3)','pcond(i,k)','dtcld','xl(i,k)','cpm(i,k)']
SURFACE = ['fall(i,kts,1)','fall(i,kts,2)','fall(i,kts,3)','fall(i,kts,4)',
           'fallsum','fallsum_qsi','fallsum_qg','delz(i,kts)','denr','dtcld','rain(i)','rainncv(i)']
PHASES = {
    1: ('ENTRY_RAW', STATE), 2: ('ENTRY_CLAMPED', STATE),
    3: ('SATURATION', ['p(i,k)','q(i,k)','t(i,k)','den(i,k)','qs(i,k,1)',
                       'qs(i,k,2)','rh(i,k,1)','rh(i,k,2)','sw(i,k)','dtcld']),
    4: ('SATDT', ['p(i,k)','q(i,k)','t(i,k)','den(i,k)','qs(i,k,1)','rh(i,k,1)','satdt','dtcld']),
    5: ('PROCESS_RATES', [f'{name}(i,k)' for name in RATE_NAMES] + ['delta2','delta3']),
    6: ('PRE_UPDATE', STATE + ['work2(i,k)','dtcld']),
    7: ('LATENT_INPUT', ['work2(i,k)','xlwork2','cpm(i,k)','dtcld','xl(i,k)','xlf']),
    8: ('POST_UPDATE', STATE), 9: ('SED_PRE', SED_PRE), 10: ('SED_POST', SED_POST),
    11: ('FINAL_COND_PRE', COND), 12: ('FINAL_COND_POST', COND),
    13: ('SURFACE_PRE', SURFACE), 14: ('SURFACE_POST', SURFACE),
    15: ('PREVP_RAW', ['prevp(i,k)','qrs(i,k,1)','satdt','dtcld']),
    16: ('PREVP_QR_CAP', ['prevp(i,k)']), 17: ('PREVP_SAT_CAP', ['prevp(i,k)']),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label}: expected one exact anchor, got {text.count(old)}")
    return text.replace(old, new, 1)


def read_selector() -> tuple[list[dict], dict, str]:
    if (sha(COHORT) != COHORT_SHA or sha(POINTS) != POINTS_SHA or
            sha(ROLES) != ROLES_SHA or sha(COHORT_RECEIPT) != COHORT_RECEIPT_SHA):
        raise ValueError("final cohort pin changed; update the plan and generator pin before regeneration")
    receipt = json.loads(COHORT_RECEIPT.read_text())
    rows = list(csv.DictReader(COHORT.open(newline="")))
    cells = {(int(row["wrf_i_1based"]), int(row["wrf_j_1based"])) for row in rows}
    if len(cells) != len(rows):
        raise ValueError("cohort selector contains duplicate native columns")
    expected = receipt.get("unique_native_global_corners")
    if expected is not None and expected != len(cells):
        raise ValueError("cohort receipt count differs from selector")
    return rows, receipt, sha(COHORT_RECEIPT)



def apply_cp04(text: str, arm: str, rows: list[dict]) -> str:
    if sha(CP04_BASE) != CP04_TEMPLATE_SHA or sha(CP04_INSTRUMENTER) != CP04_INSTRUMENTER_SHA:
        raise ValueError("pinned CP04 source/template changed")

    predicates = "\n".join(
        f"      if (trace_i == {int(row['wrf_i_1based'])} .and. trace_j == {int(row['wrf_j_1based'])}) found = .true."
        for row in rows
    )
    text, count = re.subn(r"(?<=      found = .false.\n).*?(?=   end function cloud_bal_trace_cell)",
                          predicates + "\n", text, flags=re.S)
    if count != 1:
        raise ValueError("CP04 native-selector function anchor differs")

    if arm == "OLD":
        old_lines = ARCHIVES["OLD"].read_text().splitlines()
        fix_lines = ARCHIVES["FIX"].read_text().splitlines()
        edits = [(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in
                 __import__("difflib").SequenceMatcher(a=old_lines, b=fix_lines, autojunk=False).get_opcodes()
                 if tag != "equal"]
        if len(edits) != 1:
            raise ValueError("expected the single pinned OLD/FIX source-line difference")
        oi1, oi2, fi1, fi2 = edits[0]
        if oi2 - oi1 != 1 or fi2 - fi1 != 1:
            raise ValueError("OLD/FIX source difference is not one line")
        old_line, fix_line = old_lines[oi1], fix_lines[fi1]
        if text.count(fix_line) != 1:
            raise ValueError("CP04 source does not contain the unique FIX source line")
        text = text.replace(fix_line, old_line, 1)

    # Preserve a complete 1..900 call inventory, selected process only in the
    # two frozen windows, and a compact surface boundary record through step 900.
    call_gate = "if (itimestep >= 1 .and. itimestep <= 360) then"
    if text.count(call_gate) != 4:
        raise ValueError(f"unexpected CP04 timestep gate count: {text.count(call_gate)}")
    text = text.replace(call_gate, "if (itimestep >= 1 .and. itimestep <= 900) then", 1)
    window_gate = "if ((itimestep >= 1 .and. itimestep <= 360) .or. &\n" \
                  "       (itimestep >= 721 .and. itimestep <= 900)) then"
    text = text.replace(call_gate, window_gate, 1)
    text = text.replace(call_gate, "if (itimestep >= 1 .and. itimestep <= 900) then", 1)
    text = text.replace(call_gate, window_gate, 1)
    detail_gate = "if (diagnostic_itimestep >= 1 .and. diagnostic_itimestep <= 360) then"
    text = once(text, detail_gate,
        "if ((diagnostic_itimestep >= 1 .and. diagnostic_itimestep <= 360) .or. &\n" +
        "       (diagnostic_itimestep >= 721 .and. diagnostic_itimestep <= 900)) then",
        "process timestep windows")

    state_open = """      character(len=16) :: rank_text
      character(len=96) :: filename
      write(rank_text,'(i0)') rank
      filename = 'state_'//trim(stage)//'_rank'//trim(rank_text)//'.bin'"""
    state_chunk = """      character(len=16) :: rank_text
      character(len=32) :: chunk_text
      character(len=96) :: filename
      integer :: chunk_first, chunk_last
      write(rank_text,'(i0)') rank
      if (stage == 'selected_entry' .or. stage == 'selected_return') then
        chunk_first = ((timestep - 1) / 3) * 3 + 1
        chunk_last = min(chunk_first + 2, 900)
        write(chunk_text,'(i6.6,"-",i6.6)') chunk_first, chunk_last
        filename = 'state_'//trim(stage)//'_t'//trim(chunk_text)//'_rank'//trim(rank_text)//'.bin'
      else
        filename = 'state_'//trim(stage)//'_rank'//trim(rank_text)//'.bin'
      endif"""
    text = once(text, state_open, state_chunk, "chunked selected-state filename")

    declaration = "integer                            :: diagnostic_trace_unit, diagnostic_process_unit, diagnostic_i"
    text = once(text, declaration,
        declaration + "\n   integer                            :: diagnostic_chunk_first, diagnostic_chunk_last\n" +
        "   character(len=32)                 :: diagnostic_chunk_text",
        "process chunk declarations")
    process_open = """     write(diagnostic_rank_text,'(i0)') diagnostic_rank
     diagnostic_trace_file = 'cp04_rank'//trim(diagnostic_rank_text)//'.bin'
     open(newunit=diagnostic_process_unit,file=trim(diagnostic_trace_file), &"""
    process_chunk = """     write(diagnostic_rank_text,'(i0)') diagnostic_rank
     diagnostic_chunk_first = ((diagnostic_itimestep - 1) / 3) * 3 + 1
     diagnostic_chunk_last = min(diagnostic_chunk_first + 2, 900)
     write(diagnostic_chunk_text,'(i6.6,"-",i6.6)') diagnostic_chunk_first, diagnostic_chunk_last
     diagnostic_trace_file = 'cp04_t'//trim(diagnostic_chunk_text)//'_rank'//trim(diagnostic_rank_text)//'.bin'
     open(newunit=diagnostic_process_unit,file=trim(diagnostic_trace_file), &"""
    text = once(text, process_open, process_chunk, "chunked process filename")
    if "write(diagnostic_process_unit) -1" not in text:
        raise ValueError("missing CP04 frame terminator")
    if ("if (itimestep >= 1 .and. itimestep <= 360) then" in text or
            "if (diagnostic_itimestep >= 1 .and. diagnostic_itimestep <= 360) then" in text):
        raise ValueError("stale timestep gate remains")
    return text

def schema(cohort_rows: list[dict], cohort_receipt: dict, receipt_sha: str) -> dict:
    return {
        "format": "CP04 framed Fortran stream, big-endian int32 and IEEE REAL32",
        "frame_magic": "C4FR0001",
        "frame_header_int32": ["rank", "call_id", "itimestep", "j", "its", "ite", "kts", "kte"],
        "frame_constants_real32": ["qmin", "t0c", "rv", "cpv", "cliq", "psat", "ep2", "xlv0", "xls", "cice"],
        "record_header_int32": ["phase", "i", "k", "loop", "loops", "substep", "mstep", "nfields"],
        "record_payload": "nfields REAL32 values in exact phase field order; signed zero preserved",
        "frame_end_int32": -1,
        "phase_window_steps": [1, 360, 721, 900],
        "surface_return_steps": [1, 900],
        "chunk_steps": CHUNK_STEPS,
        "cohort": {"points": cohort_receipt["point_count_deduplicated"],
                    "point_corner_rows": cohort_receipt["point_corner_rows"],
                    "columns": cohort_receipt["unique_native_global_corners"],
                    "unique_global_columns_sha256": COHORT_SHA, "point_corners_sha256": POINTS_SHA,
                    "role_membership_sha256": ROLES_SHA, "receipt_sha256": receipt_sha},
        "phases": {str(n): {"name": name, "fields": fields} for n, (name, fields) in PHASES.items()},
        "surface_return": {"record_magic": "C4SR0001", "key_int32": ["rank", "call_id", "itimestep", "j", "i"],
                           "fields_real32": ["rainncv(i,j)", "rain(i,j)", "sr(i,j)"],
                           "steps": "1..900; rain is checked against cumulative RAINNC; rainncv is retained as per-call non-convective increment; RAINC is separate convective history"},
        "wrapper_selected": {"format": "CBSP0001 keyed stage 6 entry / 7 return", "fields":
            ["TH", "QV", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DEN",
             "TK=TH*PII", "P", "PII"]},
        "field_units": {"p": "Pa", "t": "K", "q/qci/qrs": "kg kg-1 model mixing-ratio basis",
                        "den/dend": "kg m-3 driver density", "nci/nrs": "m-3 internal number",
                        "mass_process_rates": "kg kg-1 s-1", "number_process_rates": "m-3 s-1",
                        "dtcld": "s", "rain/rainncv": "mm"},
        "semantics": [
            "Actual selected process timesteps are 1..360 and 721..900; 361..720 is missing by design.",
            "Selected wrapper entry/return and all process phases preserve actual timestep, rank, call, loop, and substep.",
            "Call inventory is recorded for steps 1..900; compact surface return is recorded at every selected cell and step.",
            "Phase 5 rates are source values after their source limiters, not event counts.",
            "Sedimentation phases 9/10 cover actual rain/snow/graupel substeps; phase 9 does not read falk.",
            "Final condensation phases 11/12 are emitted for every selected cell and level; the pcond source update itself remains source-limited.",
            "Surface phase 13/14 rows are conditional and paired; absence is not synthesized zero.",
            "Wrapper differences between KDM6 calls are total non-KDM6 net, not pure transport.",
            "No extrapolation or ledger term crosses the uncaptured step interval 361..720.",
        ],
    }


def main() -> None:
    rows, cohort_receipt, receipt_sha = read_selector()
    if sha(PROFILE) != PROFILE_SHA:
        raise ValueError("pinned Intel toolchain profile changed")
    plan_path = EVIDENCE / "native/plans/capture_plan.md"
    freeze_path = EVIDENCE / "native/plans/plan_freeze.json"
    if not plan_path.is_file() or not freeze_path.is_file():
        raise ValueError("frozen native capture plan is missing")
    frozen_plan = json.loads(freeze_path.read_text())
    if frozen_plan.get("plan_sha256") != sha(plan_path):
        raise ValueError("capture plan differs from its freeze receipt")
    outputs = []
    for arm in ("OLD", "FIX"):
        if sha(ARCHIVES[arm]) != ARCHIVE_SHA[arm]:
            raise ValueError(f"{arm}: archived source changed")
        candidate = apply_cp04(CP04_BASE.read_text(), arm, rows)
        source_path = EVIDENCE / f"native/source/module_mp_kdm6_{arm}.f90"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(candidate)
        # The generated source is required to retain every original physics line
        # in order; only diagnostic insertions are allowed.
        import difflib
        original_lines = ARCHIVES[arm].read_text().splitlines()
        generated_lines = candidate.splitlines()
        operations = difflib.SequenceMatcher(a=original_lines, b=generated_lines, autojunk=False).get_opcodes()
        if any(tag not in ("equal", "insert") for tag, *_ in operations):
            raise ValueError(f"{arm}: generated source replaced or deleted original lines")
        outputs.append({"arm": arm, "source": str(source_path), "sha256": sha(source_path),
                        "original_source_sha256": ARCHIVE_SHA[arm],
                        "line_bijection": {tag: sum(1 for op in operations if op[0] == tag)
                                           for tag in ("equal", "insert", "replace", "delete")}})
    schema_path = EVIDENCE / "native/schema/cp05_schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema(rows, cohort_receipt, receipt_sha), indent=2) + "\n")
    receipt = {"status": "SOURCE_GENERATED_AWAITING_INDEPENDENT_REVIEW", "arms": outputs,
               "generator_sha256": sha(Path(__file__)), "plan_sha256": sha(plan_path),
               "plan_freeze_sha256": sha(freeze_path),
               "cohort_sha256": COHORT_SHA, "cohort_receipt_sha256": receipt_sha,
               "toolchain_profile_sha256": PROFILE_SHA, "cp03_template_source_sha256": CP03_TEMPLATE_SHA,
               "cp04_template_source_sha256": CP04_TEMPLATE_SHA,
               "cp04_instrumenter_sha256": CP04_INSTRUMENTER_SHA, "schema_sha256": sha(schema_path),
               "windows": WINDOWS, "chunk_steps": CHUNK_STEPS}
    receipt_path = EVIDENCE / "native/source/source_generation_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
