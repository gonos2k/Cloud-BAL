from __future__ import annotations

import csv
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PARENT = Path("/var/tmp/b1-two-hour-probe-20261103/build")
PINS = {
    "BASE": "b3a7f22c5929eab80784b2b2963e34798811b16c0f9a433601b16498f52aae02",
    "FIX": "bd4e0a021f770daf0fbbdedfa3f07b964638edac5b3fb1b1f97dbe4826b72e90",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates() -> list[tuple[int, int]]:
    path = REPO / "docs/evidence/cp02_state_path_20261104/cohorts/point_corners.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    cells = sorted({(int(row["wrf_i_1based"]), int(row["wrf_j_1based"])) for row in rows})
    if len(rows) != 32 or len(cells) != 32:
        raise ValueError(f"expected eight cohorts/32 distinct corners; got {len(rows)}/{len(cells)}")
    return cells


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def trace_helper(cells: list[tuple[int, int]]) -> str:
    tests = "\n".join(
        f"      if (trace_i == {i} .and. trace_j == {j}) found = .true."
        for i, j in cells
    )
    return f"""   logical function cloud_bal_trace_cell(trace_i, trace_j) result(found)
      implicit none
      integer, intent(in) :: trace_i, trace_j
      found = .false.
{tests}
   end function cloud_bal_trace_cell

   subroutine cloud_bal_state_open(unit, stage, stage_id, rank, call_id, timestep, &
                                   ilo, ihi, jlo, jhi, klo, khi, nfields, nrecords)
      implicit none
      integer, intent(out) :: unit
      character(len=*), intent(in) :: stage
      integer, intent(in) :: stage_id, rank, call_id, timestep
      integer, intent(in) :: ilo, ihi, jlo, jhi, klo, khi, nfields, nrecords
      character(len=16) :: rank_text
      character(len=96) :: filename
      write(rank_text,'(i0)') rank
      filename = 'state_'//trim(stage)//'_rank'//trim(rank_text)//'.bin'
      open(newunit=unit,file=trim(filename),status='unknown',position='append', &
           access='stream',form='unformatted',action='write')
      write(unit) 'CBSP0001', stage_id, rank, call_id, timestep, &
                  ilo, ihi, jlo, jhi, klo, khi, 1, 1, 1, nfields, nrecords
   end subroutine cloud_bal_state_open

   subroutine cloud_bal_state_row(unit, values)
      implicit none
      integer, intent(in) :: unit
      real, intent(in) :: values(:)
      write(unit) values
   end subroutine cloud_bal_state_row

   subroutine cloud_bal_state_keyed_row(unit, i, j, k, values)
      implicit none
      integer, intent(in) :: unit, i, j, k
      real, intent(in) :: values(:)
      write(unit) i, j, k, values
   end subroutine cloud_bal_state_keyed_row
"""


def extend(source: str, cells: list[tuple[int, int]]) -> str:
    begin = source.index("   logical function cloud_bal_trace_cell(")
    end_marker = "   end function cloud_bal_trace_cell"
    end = source.index(end_marker, begin) + len(end_marker)
    source = source[:begin] + trace_helper(cells).rstrip() + source[end:]

    source = once(source,
        "   integer                            :: cloud_bal_trace_unit\n",
        "   integer                            :: cloud_bal_trace_unit\n"
        "   integer                            :: cloud_bal_state_unit, cloud_bal_call_unit\n"
        "   integer                            :: cloud_bal_state_i\n"
        "   integer                            :: cloud_bal_state_j, cloud_bal_state_k\n"
        "   integer                            :: cloud_bal_state_records\n"
        "   real, dimension(16)                 :: cloud_bal_state_values\n",
        "KDM6 declarations")
    source = once(source,
        "   integer                            :: diagnostic_trace_active\n",
        "   integer                            :: diagnostic_trace_active\n"
        "   integer                            :: cloud_bal_pre_unit, cloud_bal_process_unit\n"
        "   integer                            :: cloud_bal_state_i, cloud_bal_state_k\n"
        "   real, dimension(15)                 :: cloud_bal_state_values\n",
        "KDM62D declarations")

    # Record actual KDM6 core bounds and the host-facing state before conversions.
    selected_entry = """   cloud_bal_trace_file = 'kdm6_trace_rank'//trim(cloud_bal_trace_rank_text)//'.bits'

   if (itimestep >= 1 .and. itimestep <= 360) then
     open(newunit=cloud_bal_call_unit, &
          file='state_calls_rank'//trim(cloud_bal_trace_rank_text)//'.txt', &
          status='unknown',position='append',action='write')
     write(cloud_bal_call_unit,'(21(i0,1x))') itimestep, cloud_bal_trace_rank, &
          cloud_bal_trace_call_id, ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
          its,ite,jts,jte,kts,kte
     close(cloud_bal_call_unit)
   endif

   if (itimestep >= 1 .and. itimestep <= 360) then
     cloud_bal_state_records = 0
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
         if (cloud_bal_trace_cell(cloud_bal_state_i,cloud_bal_state_j)) &
           cloud_bal_state_records = cloud_bal_state_records + kte-kts+1
       enddo
     enddo
     call cloud_bal_state_open(cloud_bal_state_unit,'selected_entry',6,cloud_bal_trace_rank, &
          cloud_bal_trace_call_id,itimestep,max(its,ids),min(ite,ide-1), &
          max(jts,jds),min(jte,jde-1),kts,kte,14,cloud_bal_state_records)
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
           if (cloud_bal_trace_cell(cloud_bal_state_i,cloud_bal_state_j)) then
             cloud_bal_state_values(1:14) = (/ th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               q(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qi(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qs(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nn(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               ni(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               bg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               den(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j)* &
                 pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)
             call cloud_bal_state_keyed_row(cloud_bal_state_unit,cloud_bal_state_i, &
                  cloud_bal_state_j,cloud_bal_state_k,cloud_bal_state_values(1:14))
           endif
         enddo
       enddo
     enddo
     close(cloud_bal_state_unit)
   endif

   if (itimestep == 1) then
     call cloud_bal_state_open(cloud_bal_state_unit,'entry',1,cloud_bal_trace_rank, &
          cloud_bal_trace_call_id,itimestep,max(its,ids),min(ite,ide-1), &
          max(jts,jds),min(jte,jde-1),kts,kte,14, &
          max(0,min(ite,ide-1)-max(its,ids)+1)* &
          max(0,min(jte,jde-1)-max(jts,jds)+1)*(kte-kts+1))
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
           cloud_bal_state_values(1:14) = (/ th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             q(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qi(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qs(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nn(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             ni(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             bg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             den(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j)* &
               pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)
           call cloud_bal_state_row(cloud_bal_state_unit,cloud_bal_state_values(1:14))
         enddo
       enddo
     enddo
     close(cloud_bal_state_unit)
   endif

   do j = jts,jte
"""
    anchor = "   cloud_bal_trace_file = 'kdm6_trace_rank'//trim(cloud_bal_trace_rank_text)//'.bits'\n\n   do j = jts,jte\n"
    source = once(source, anchor, selected_entry, "KDM6 selected ENTRY dump")

    pre = """   do loop = 1,loops

     if (diagnostic_itimestep == 1 .and. loop == 1) then
       call cloud_bal_state_open(cloud_bal_pre_unit,'pre_update',2,diagnostic_rank, &
            diagnostic_call_id,diagnostic_itimestep,its,ite,lat,lat,kts,kte,15, &
            (ite-its+1)*(kte-kts+1))
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = its,ite
           cloud_bal_state_values(1:15) = (/ q(cloud_bal_state_i,cloud_bal_state_k), &
             t(cloud_bal_state_i,cloud_bal_state_k), den(cloud_bal_state_i,cloud_bal_state_k), &
             qci(cloud_bal_state_i,cloud_bal_state_k,1), qci(cloud_bal_state_i,cloud_bal_state_k,2), &
             qrs(cloud_bal_state_i,cloud_bal_state_k,1), qrs(cloud_bal_state_i,cloud_bal_state_k,2), &
             qrs(cloud_bal_state_i,cloud_bal_state_k,3), nci(cloud_bal_state_i,cloud_bal_state_k,1), &
             nci(cloud_bal_state_i,cloud_bal_state_k,2), nci(cloud_bal_state_i,cloud_bal_state_k,3), &
             nrs(cloud_bal_state_i,cloud_bal_state_k,1), nrs(cloud_bal_state_i,cloud_bal_state_k,2), &
             nrs(cloud_bal_state_i,cloud_bal_state_k,3), brs(cloud_bal_state_i,cloud_bal_state_k) /)
           call cloud_bal_state_row(cloud_bal_pre_unit,cloud_bal_state_values(1:15))
         enddo
       enddo
       close(cloud_bal_pre_unit)
     endif

     do i = its,ite
"""
    source = once(source,
        "   do loop = 1,loops\n\n\n\n     do i = its,ite\n", pre,
        "first PRE_UPDATE block")

    process_open = """   do loop = 1,loops

     if (diagnostic_itimestep == 1 .and. loop == 1) then
       call cloud_bal_state_open(cloud_bal_process_unit,'post_process',3,diagnostic_rank, &
            diagnostic_call_id,diagnostic_itimestep,its,ite,lat,lat,kts,kte,15, &
            (ite-its+1)*(kte-kts+1))
     endif

"""
    source = once(source,
        "   do loop = 1,loops\n", process_open,
        "POST_PROCESS block open")

    process_row = """          if (diagnostic_itimestep == 1 .and. loop == 1) then
            cloud_bal_state_values(1:15) = (/ q(i,k), t(i,k), den(i,k), qci(i,k,1), qci(i,k,2), &
              qrs(i,k,1), qrs(i,k,2), qrs(i,k,3), nci(i,k,1), nci(i,k,2), nci(i,k,3), &
              nrs(i,k,1), nrs(i,k,2), nrs(i,k,3), brs(i,k) /)
            call cloud_bal_state_row(cloud_bal_process_unit,cloud_bal_state_values(1:15))
          endif
"""
    source = once(source,
        "          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n"
        "            write(diagnostic_trace_unit,*) 'POST_STEP', diagnostic_rank, diagnostic_call_id, &\n",
        process_row +
        "          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n"
        "            write(diagnostic_trace_unit,*) 'POST_STEP', diagnostic_rank, diagnostic_call_id, &\n",
        "POST_PROCESS per-cell row")

    close_anchor = "   end subroutine kdm62d\n"
    close_block = """   if (diagnostic_itimestep == 1 .and. loops >= 1) close(cloud_bal_process_unit)

   end subroutine kdm62d
"""
    source = once(source, close_anchor, close_block, "POST_PROCESS close")

    post = """     if (itimestep == 1) then
       call cloud_bal_state_open(cloud_bal_state_unit,'kdm62d_return',4,cloud_bal_trace_rank, &
            cloud_bal_trace_call_id,itimestep,its,ite,j,j,kts,kte,15, &
            (ite-its+1)*(kte-kts+1))
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = its,ite
           cloud_bal_state_values(1:15) = (/ q(cloud_bal_state_i,cloud_bal_state_k,j), &
             t(cloud_bal_state_i,cloud_bal_state_k), den(cloud_bal_state_i,cloud_bal_state_k,j), &
             qci(cloud_bal_state_i,cloud_bal_state_k,1), qci(cloud_bal_state_i,cloud_bal_state_k,2), &
             qrs(cloud_bal_state_i,cloud_bal_state_k,1), qrs(cloud_bal_state_i,cloud_bal_state_k,2), &
             qrs(cloud_bal_state_i,cloud_bal_state_k,3), nci(cloud_bal_state_i,cloud_bal_state_k,1), &
             nci(cloud_bal_state_i,cloud_bal_state_k,2), nci(cloud_bal_state_i,cloud_bal_state_k,3), &
             nrs(cloud_bal_state_i,cloud_bal_state_k,1), nrs(cloud_bal_state_i,cloud_bal_state_k,2), &
             nrs(cloud_bal_state_i,cloud_bal_state_k,3), brs(cloud_bal_state_i,cloud_bal_state_k) /)
           call cloud_bal_state_row(cloud_bal_state_unit,cloud_bal_state_values(1:15))
         enddo
       enddo
       close(cloud_bal_state_unit)
     endif

     do k = kts,kte
       do i = its,ite
         th(i,k,j) = t(i,k)/pii(i,k,j)
"""
    post_anchor = "     do k = kts,kte\n       do i = its,ite\n         th(i,k,j) = t(i,k)/pii(i,k,j)"
    source = once(source, post_anchor, post, "POST_STEP capture")

    ret = """   if (itimestep >= 1 .and. itimestep <= 360) then
     cloud_bal_state_records = 0
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
         if (cloud_bal_trace_cell(cloud_bal_state_i,cloud_bal_state_j)) &
           cloud_bal_state_records = cloud_bal_state_records + kte-kts+1
       enddo
     enddo
     call cloud_bal_state_open(cloud_bal_state_unit,'selected_return',7,cloud_bal_trace_rank, &
          cloud_bal_trace_call_id,itimestep,max(its,ids),min(ite,ide-1), &
          max(jts,jds),min(jte,jde-1),kts,kte,14,cloud_bal_state_records)
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
           if (cloud_bal_trace_cell(cloud_bal_state_i,cloud_bal_state_j)) then
             cloud_bal_state_values(1:14) = (/ th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               q(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qi(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qs(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               qg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nn(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               ni(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               nr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               bg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               den(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
               th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j)* &
                 pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)
             call cloud_bal_state_keyed_row(cloud_bal_state_unit,cloud_bal_state_i, &
                  cloud_bal_state_j,cloud_bal_state_k,cloud_bal_state_values(1:14))
           endif
         enddo
       enddo
     enddo
     close(cloud_bal_state_unit)
   endif

   if (itimestep == 1) then
     call cloud_bal_state_open(cloud_bal_state_unit,'wrapper_return',5,cloud_bal_trace_rank, &
          cloud_bal_trace_call_id,itimestep,max(its,ids),min(ite,ide-1), &
          max(jts,jds),min(jte,jde-1),kts,kte,14, &
          max(0,min(ite,ide-1)-max(its,ids)+1)* &
          max(0,min(jte,jde-1)-max(jts,jds)+1)*(kte-kts+1))
     do cloud_bal_state_j = max(jts,jds),min(jte,jde-1)
       do cloud_bal_state_k = kts,kte
         do cloud_bal_state_i = max(its,ids),min(ite,ide-1)
           cloud_bal_state_values(1:14) = (/ th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             q(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qi(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qs(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             qg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nn(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nc(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             ni(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             nr(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             bg(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             den(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &
             th(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j)* &
               pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)
           call cloud_bal_state_row(cloud_bal_state_unit,cloud_bal_state_values(1:14))
         enddo
       enddo
     enddo
     close(cloud_bal_state_unit)
   endif

   end subroutine kdm6
"""
    source = once(source, "   end subroutine kdm6\n", ret, "public KDM6 return dump")
    return source


def main() -> None:
    cells = coordinates()
    output = HERE / "patched"
    output.mkdir(exist_ok=True)
    patch: list[str] = []
    arms: dict[str, dict[str, str]] = {}
    for arm in ("BASE", "FIX"):
        path = PARENT / arm / "module_mp_kdm6.f90"
        if digest(path) != PINS[arm]:
            raise SystemExit(f"parent {arm} module hash mismatch")
        old = path.read_text(encoding="utf-8")
        new = extend(old, cells)
        target = output / f"module_mp_kdm6_{arm}.f90"
        target.write_text(new, encoding="utf-8")
        arms[arm] = {"input_sha256": digest(path), "output_sha256": digest(target)}
        patch.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{arm}/module_mp_kdm6.f90", tofile=f"b/{arm}/module_mp_kdm6.f90"))
    patch_path = HERE / "state_path_extension.patch"
    patch_path.write_text("".join(patch), encoding="utf-8")
    receipt = {
        "status": "SOURCE_PATCH_GENERATED_REVIEWED",
        "parent_patch_sha256": "94f109e624aa0b3b25689db20b1ac1acb4122920288d3765499147ed385fea3e",
        "cohorts": 8,
        "selected_corners": len(cells),
        "coordinate_file_sha256": digest(REPO / "docs/evidence/cp02_state_path_20261104/cohorts/point_corners.csv"),
        "binary_format": "CBSP0001, Intel -convert big_endian unformatted stream; global blocks use implicit j/k/i bounds and selected blocks use explicit i/j/k keys",
        "generator_sha256": digest(Path(__file__)),
        "schema_sha256": digest(HERE / "state_schema.json"),
        "plan_sha256": digest(HERE / "diagnostic_plan.md"),
        "arms": arms,
        "extension_patch_sha256": digest(patch_path),
    }
    (HERE / "patch_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
