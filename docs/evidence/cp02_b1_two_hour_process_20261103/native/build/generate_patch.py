from __future__ import annotations
import difflib, hashlib, json
from pathlib import Path

ROOT = Path('/var/tmp/b1-two-hour-probe-20261103')
SOURCE_ROOT = Path('/var/tmp/firsthour-runtime-plan-20261030/experiment')
EXPECTED = {
    'BASE': 'c4a7d1e90ea27608ba7efb652cfb79dee2e30db769e076ad1a2e7a7e63d5e52b',
    'FIX': '0b468be19f7dd66ad2f6e65a53b42f10391a4565831a96c80dddddf21934cf79',
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def patch_arm(arm: str, coordinates: list[dict]) -> tuple[str, str]:
    src = SOURCE_ROOT / f'build_{arm}' / 'module_mp_kdm6.f90'
    original = src.read_text()
    assert sha(src) == EXPECTED[arm], f'{arm} source pin mismatch'
    assert original.count('    contains\n') == 1
    original = original.replace(
        '    contains\n',
        '    integer, save :: cloud_bal_trace_next_call = 0\n\n    contains\n', 1)
    helper_lines = [
        '   logical function cloud_bal_trace_cell(trace_i, trace_j) result(found)',
        '      implicit none',
        '      integer, intent(in) :: trace_i, trace_j',
        '      found = .false.',
    ]
    for c in coordinates:
        helper_lines.append(f'      if (trace_i == {c["i"]} .and. trace_j == {c["j"]}) found = .true.')
    helper_lines += ['   end function cloud_bal_trace_cell', '', '']
    original = original.replace('    subroutine kdm6(th, q, qc, qr, qi, qs, qg,', '\n'.join(helper_lines) + '    subroutine kdm6(th, q, qc, qr, qi, qs, qg,', 1)
    original = original.replace(
        '   integer                            :: i,j,k\n',
        '   integer                            :: i,j,k\n'
        '   integer                            :: cloud_bal_trace_rank, cloud_bal_trace_call_id\n'
        '   integer                            :: cloud_bal_trace_unit\n'
        '   character(len=16)                  :: cloud_bal_trace_rank_text\n'
        '   character(len=64)                  :: cloud_bal_trace_file\n', 1)
    original = original.replace(
        '   do j = jts,jte\n',
        '   call wrf_get_myproc(cloud_bal_trace_rank)\n'
        '   cloud_bal_trace_next_call = cloud_bal_trace_next_call + 1\n'
        '   cloud_bal_trace_call_id = cloud_bal_trace_next_call\n'
        '   write(cloud_bal_trace_rank_text,\'(i0)\') cloud_bal_trace_rank\n'
        '   cloud_bal_trace_file = \'kdm6_trace_rank\'//trim(cloud_bal_trace_rank_text)//\'.bits\'\n\n'
        '   do j = jts,jte\n', 1)
    call_end = '                ,graupel(ims,j),graupelncv(ims,j)          &\n                )'
    assert original.count(call_end) == 1
    original = original.replace(call_end,
        '                ,graupel(ims,j),graupelncv(ims,j)          &\n'
        '                ,itimestep, cloud_bal_trace_call_id, cloud_bal_trace_rank &\n'
        '                )', 1)
    original = original.replace(
        '     do k = kts,kte\n       do i = its,ite\n         th(i,k,j) = t(i,k)/pii(i,k,j)',
        '     if (itimestep >= 1 .and. itimestep <= 360) then\n'
        '       do i = its,ite\n'
        '         if (cloud_bal_trace_cell(i,j)) then\n'
        '           open(newunit=cloud_bal_trace_unit,file=trim(cloud_bal_trace_file), &\n'
        '                status=\'unknown\',position=\'append\',action=\'write\')\n'
        '           write(cloud_bal_trace_unit,*) \'SURFACE_RETURN\', cloud_bal_trace_rank, &\n'
        '             cloud_bal_trace_call_id, itimestep, j, i, transfer(rainncv(i,j),0), &\n'
        '             transfer(rain(i,j),0), transfer(sr(i,j),0)\n'
        '           if (present(snow)) then\n'
        '             write(cloud_bal_trace_unit,*) \'SNOW_RETURN\', cloud_bal_trace_rank, &\n'
        '               cloud_bal_trace_call_id, itimestep, j, i, transfer(snow(i,j),0)\n'
        '           endif\n'
        '           if (present(graupel)) then\n'
        '             write(cloud_bal_trace_unit,*) \'GRAUPEL_RETURN\', cloud_bal_trace_rank, &\n'
        '               cloud_bal_trace_call_id, itimestep, j, i, transfer(graupel(i,j),0)\n'
        '           endif\n'
        '           close(cloud_bal_trace_unit)\n'
        '         endif\n'
        '       enddo\n'
        '     endif\n\n'
        '     do k = kts,kte\n       do i = its,ite\n         th(i,k,j) = t(i,k)/pii(i,k,j)', 1)
    kdm62d_at = original.index('   subroutine kdm62D(')
    prefix, suffix = original[:kdm62d_at], original[kdm62d_at:]
    sig = '                   ,graupel,graupelncv                            &\n                    )'
    assert suffix.count(sig) == 1
    suffix = suffix.replace(sig,
        '                   ,graupel,graupelncv                            &\n'
        '                   ,diagnostic_itimestep, diagnostic_call_id, diagnostic_rank &\n'
        '                    )', 1)
    lat_decl = '   integer                                , intent(in   ) :: lat\n'
    assert suffix.count(lat_decl) == 1
    suffix = suffix.replace(lat_decl,
        lat_decl +
        '   integer, intent(in) :: diagnostic_itimestep, diagnostic_call_id, diagnostic_rank\n', 1)
    original = prefix + suffix
    decl_marker = '   integer                            :: kte_in\n'
    assert original.count(decl_marker) == 1
    original = original.replace(decl_marker,
        '   integer                            :: kte_in\n'
        '   integer                            :: diagnostic_trace_unit, diagnostic_i\n'
        '   integer                            :: diagnostic_trace_active\n'
        '   character(len=16)                  :: diagnostic_rank_text\n'
        '   character(len=64)                  :: diagnostic_trace_file\n', 1)
    insert_at = '   do k = kts, kte\n     do i = its, ite\n       qci(i,k,1) = max(qci(i,k,1),0.0)'
    assert original.count(insert_at) == 1
    preamble = (
        '   diagnostic_trace_active = 0\n'
        '   if (diagnostic_itimestep >= 1 .and. diagnostic_itimestep <= 360) then\n'
        '     do diagnostic_i = its, ite\n'
        '       if (cloud_bal_trace_cell(diagnostic_i,lat)) diagnostic_trace_active = 1\n'
        '     enddo\n'
        '   endif\n'
        '   if (diagnostic_trace_active == 1) then\n'
        '     write(diagnostic_rank_text,\'(i0)\') diagnostic_rank\n'
        '     diagnostic_trace_file = \'kdm6_trace_rank\'//trim(diagnostic_rank_text)//\'.bits\'\n'
        '     open(newunit=diagnostic_trace_unit,file=trim(diagnostic_trace_file), &\n'
        '          status=\'unknown\',position=\'append\',action=\'write\')\n'
        '   endif\n\n'
    )
    raw = (
        '       if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '         write(diagnostic_trace_unit,*) \'ENTRY_RAW\', diagnostic_rank, diagnostic_call_id, &\n'
        '           diagnostic_itimestep, 0, lat, i, k, transfer(q(i,k),0), transfer(t(i,k),0), &\n'
        '           transfer(den(i,k),0), transfer(qci(i,k,1),0), transfer(qci(i,k,2),0), &\n'
        '           transfer(qrs(i,k,1),0), transfer(qrs(i,k,2),0), transfer(qrs(i,k,3),0), &\n'
        '           transfer(nci(i,k,1),0), transfer(nci(i,k,2),0), transfer(nci(i,k,3),0), &\n'
        '           transfer(nrs(i,k,1),0), transfer(nrs(i,k,2),0), transfer(nrs(i,k,3),0), &\n'
        '           transfer(brs(i,k),0)\n'
    )
    original = original.replace(insert_at, preamble + insert_at, 1)
    original = original.replace(
        '       qci(i,k,1) = max(qci(i,k,1),0.0)',
        raw + '       qci(i,k,1) = max(qci(i,k,1),0.0)', 1)
    # Post-clamp state in the same initial loop, after the last entry clamp.
    original = original.replace(
        '       brs(i,k) = max(brs(i,k),0.0)\n',
        '       brs(i,k) = max(brs(i,k),0.0)\n'
        '       if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '         write(diagnostic_trace_unit,*) \'ENTRY_CLAMPED\', diagnostic_rank, diagnostic_call_id, &\n'
        '           diagnostic_itimestep, 0, lat, i, k, transfer(q(i,k),0), transfer(t(i,k),0), &\n'
        '           transfer(den(i,k),0), transfer(qci(i,k,1),0), transfer(qci(i,k,2),0), &\n'
        '           transfer(qrs(i,k,1),0), transfer(qrs(i,k,2),0), transfer(qrs(i,k,3),0), &\n'
        '           transfer(nci(i,k,1),0), transfer(nci(i,k,2),0), transfer(nci(i,k,3),0), &\n'
        '           transfer(nrs(i,k,1),0), transfer(nrs(i,k,2),0), transfer(nrs(i,k,3),0), &\n'
        '           transfer(brs(i,k),0)\n', 1)
    original = original.replace(
        '         rh(i,k,2) = max(q(i,k)/qs(i,k,2),qmin)\n',
        '         rh(i,k,2) = max(q(i,k)/qs(i,k,2),qmin)\n'
        '         if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '           write(diagnostic_trace_unit,*) \'SATURATION\', diagnostic_rank, diagnostic_call_id, &\n'
        '             diagnostic_itimestep, loop, lat, i, k, transfer(q(i,k),0), transfer(t(i,k),0), &\n'
        '             transfer(den(i,k),0), transfer(qs(i,k,1),0), transfer(qs(i,k,2),0), &\n'
        '             transfer(rh(i,k,1),0), transfer(rh(i,k,2),0), transfer(sw(i,k),0)\n', 1)
    original = original.replace(
        '          satdt = supsat/dtcld\n',
        '          satdt = supsat/dtcld\n'
        '          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '            write(diagnostic_trace_unit,*) \'SATDT\', diagnostic_rank, diagnostic_call_id, &\n'
        '              diagnostic_itimestep, loop, lat, i, k, transfer(dtcld,0), transfer(satdt,0), &\n'
        '              transfer(q(i,k),0), transfer(qs(i,k,1),0), transfer(rh(i,k,1),0)\n', 1)
    original = original.replace(
        '            prevp(i,k) = fac_evap*prevp(i,k) \n',
        '            if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '              write(diagnostic_trace_unit,*) \'PREVP_FORMULA\', diagnostic_rank, diagnostic_call_id, &\n'
        '                diagnostic_itimestep, loop, lat, i, k, transfer(prevp(i,k),0), &\n'
        '                transfer(nrs(i,k,1),0), &\n'
        '                transfer(qrs(i,k,1),0), transfer(den(i,k),0), transfer(rh(i,k,1),0), &\n'
        '                transfer(n0r(i,k),0_8), transfer(fac_evap,0)\n'
        '            prevp(i,k) = fac_evap*prevp(i,k) \n'
        '            if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '              write(diagnostic_trace_unit,*) \'PREVP_RAW\', diagnostic_rank, diagnostic_call_id, &\n'
        '                diagnostic_itimestep, loop, lat, i, k, transfer(prevp(i,k),0), &\n'
        '                transfer(qrs(i,k,1),0), transfer(satdt,0), transfer(dtcld,0)\n', 1)
    original = original.replace(
        '              prevp(i,k) = max(prevp(i,k),-(qrs(i,k,1))/dtcld)\n',
        '              prevp(i,k) = max(prevp(i,k),-(qrs(i,k,1))/dtcld)\n'
        '              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '                write(diagnostic_trace_unit,*) \'PREVP_QR_CAP\', diagnostic_rank, diagnostic_call_id, &\n'
        '                  diagnostic_itimestep, loop, lat, i, k, transfer(prevp(i,k),0)\n', 1)
    original = original.replace(
        '              prevp(i,k) = max(prevp(i,k),(satdt)/2)\n',
        '              prevp(i,k) = max(prevp(i,k),(satdt)/2)\n'
        '              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '                write(diagnostic_trace_unit,*) \'PREVP_SAT_CAP\', diagnostic_rank, diagnostic_call_id, &\n'
        '                  diagnostic_itimestep, loop, lat, i, k, transfer(prevp(i,k),0)\n', 1)
    original = original.replace(
        '              prevp(i,k) = min(prevp(i,k),(satdt)/2)\n',
        '              prevp(i,k) = min(prevp(i,k),(satdt)/2)\n'
        '              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '                write(diagnostic_trace_unit,*) \'PREVP_SAT_CAP\', diagnostic_rank, diagnostic_call_id, &\n'
        '                  diagnostic_itimestep, loop, lat, i, k, transfer(prevp(i,k),0)\n', 1)
    # Capture final rates immediately before each cloud-water/rainwater state update.
    pre_update_write = (
        '          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '            write(diagnostic_trace_unit,*) \'PRE_UPDATE\', diagnostic_rank, diagnostic_call_id, &\n'
        '              diagnostic_itimestep, loop, lat, i, k, transfer(q(i,k),0), transfer(t(i,k),0), &\n'
        '              transfer(den(i,k),0), transfer(qci(i,k,1),0), transfer(qci(i,k,2),0), &\n'
        '              transfer(qrs(i,k,1),0), transfer(qrs(i,k,2),0), transfer(qrs(i,k,3),0), &\n'
        '              transfer(nci(i,k,1),0), transfer(nci(i,k,2),0), transfer(nci(i,k,3),0), &\n'
        '              transfer(nrs(i,k,1),0), transfer(nrs(i,k,2),0), transfer(nrs(i,k,3),0), &\n'
        '              transfer(brs(i,k),0), transfer(work2(i,k),0), transfer(dtcld,0)\n'
    )
    rate_write = (
        '          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '            write(diagnostic_trace_unit,*) \'PROCESS_RATES\', diagnostic_rank, diagnostic_call_id, &\n'
        '              diagnostic_itimestep, loop, lat, i, k, transfer(praut(i,k),0), transfer(pracw(i,k),0), &\n'
        '              transfer(prevp(i,k),0), transfer(piacr(i,k),0), transfer(pgacr(i,k),0), &\n'
        '              transfer(psacr(i,k),0), transfer(pmulrs(i,k),0), transfer(pmulrg(i,k),0), &\n'
        '              transfer(pseml(i,k),0), transfer(pgeml(i,k),0), transfer(psevp(i,k),0), &\n'
        '              transfer(pgevp(i,k),0), transfer(psdep(i,k),0), transfer(pgdep(i,k),0), &\n'
        '              transfer(pinud(i,k),0), transfer(pidep(i,k),0)\n'
    )
    import re
    original, rate_count = re.subn(r'(?m)^\s*q\(i,k\) = q\(i,k\)\+work2\(i,k\)\*dtcld[^\n]*$', lambda m: rate_write + pre_update_write + m.group(0), original)
    assert rate_count == 2, rate_count
    latent_write = (
        '            if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '              write(diagnostic_trace_unit,*) \'LATENT_INPUT\', diagnostic_rank, diagnostic_call_id, &\n'
        '                diagnostic_itimestep, loop, lat, i, k, transfer(work2(i,k),0), &\n'
        '                transfer(xlwork2,0), transfer(cpm(i,k),0), transfer(dtcld,0), &\n'
        '                transfer(xl(i,k),0), transfer(xlf,0)\n'
    )
    import re
    original, latent_count = re.subn(r'(?m)^(\s*)t\(i,k\) = t\(i,k\)-xlwork2/cpm\(i,k\)\*dtcld\s*$', lambda m: latent_write + m.group(0), original)
    assert latent_count == 2, latent_count
    # Append final state after the cold/warm branch; this marker is unique at main loop close.
    close_marker = '          endif\n        enddo\n      enddo\n\n     do k = kts,kte\n'
    assert original.count(close_marker) == 1
    original = original.replace(close_marker,
        '          endif\n'
        '          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &\n'
        '            write(diagnostic_trace_unit,*) \'POST_STEP\', diagnostic_rank, diagnostic_call_id, &\n'
        '              diagnostic_itimestep, loop, lat, i, k, transfer(q(i,k),0), transfer(t(i,k),0), &\n'
        '              transfer(den(i,k),0), transfer(qci(i,k,1),0), transfer(qci(i,k,2),0), &\n'
        '              transfer(qrs(i,k,1),0), transfer(qrs(i,k,2),0), transfer(qrs(i,k,3),0), &\n'
        '              transfer(nci(i,k,1),0), transfer(nci(i,k,2),0), transfer(nci(i,k,3),0), &\n'
        '              transfer(nrs(i,k,1),0), transfer(nrs(i,k,2),0), transfer(nrs(i,k,3),0), &\n'
        '              transfer(brs(i,k),0)\n'
        '        enddo\n      enddo\n\n     do k = kts,kte\n', 1)
    end_marker = '   end subroutine kdm62d\n'
    assert original.count(end_marker) == 1
    original = original.replace(end_marker,
        '   if (diagnostic_trace_active == 1) close(diagnostic_trace_unit)\n\n' + end_marker, 1)
    assert original.count("'PREVP_FORMULA'") == 1, 'missing raw formula assignment capture'
    formula_event = original.split("write(diagnostic_trace_unit,*) 'PREVP_FORMULA'",1)[1].split('prevp(i,k) = fac_evap*prevp(i,k)',1)[0]
    assert 'transfer(prevp(i,k),0)' in formula_event, 'missing exact binary32 formula result'
    assert original.count("'PREVP_RAW'") == 1, 'missing post-fac/pre-cap capture'
    assert original.count('transfer(n0r(i,k),0_8)') == 1, 'missing raw int64 n0r capture'
    assert original.count("'LATENT_INPUT'") == 2, 'missing source-ordered latent inputs'
    assert original.count("'PRE_UPDATE'") == 2, 'missing pre-update state capture'
    assert original.count("'PREVP_QR_CAP'") == 1
    assert original.count("'PREVP_SAT_CAP'") == 2
    return src.read_text(), original

cells = json.loads((ROOT/'cells.json').read_text())['coordinates']
assert len(cells) == 16 and len({(c['j'],c['i']) for c in cells}) == 16
out = ROOT/'patched'
out.mkdir(exist_ok=True)
diffs=[]
for arm in ('BASE','FIX'):
    old,new=patch_arm(arm,cells)
    dst=out/f'module_mp_kdm6_{arm}.f90'
    dst.write_text(new)
    diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=f'archived/{arm}/module_mp_kdm6.f90',tofile=f'diagnostic/{arm}/module_mp_kdm6.f90'))
patch_text = ''.join(diffs)
assert all(not line.startswith('-') or line.startswith('---') for line in patch_text.splitlines()), 'physical source line removed or rewritten'
(ROOT/'candidate.patch').write_text(patch_text)
print(json.dumps({'BASE_input_sha256':EXPECTED['BASE'],'FIX_input_sha256':EXPECTED['FIX'],'BASE_instrumented_sha256':sha(out/'module_mp_kdm6_BASE.f90'),'FIX_instrumented_sha256':sha(out/'module_mp_kdm6_FIX.f90'),'patch_sha256':sha(ROOT/'candidate.patch'),'selected_cells':len(cells)},indent=2))
