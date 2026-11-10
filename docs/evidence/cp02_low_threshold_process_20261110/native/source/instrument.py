#!/usr/bin/env python3
"""Insert CP05 diagnostics into the three pinned B1 sources without editing physics."""
import argparse
import csv
import difflib
import hashlib
import json
import re
from pathlib import Path

WORK = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
HERE = Path(__file__).resolve().parent
BASE = Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/build_FIX/module_mp_kdm6.f90')
CP05 = HERE.parents[2] / 'cp02_protected_process_20261106/native/source/module_mp_kdm6_FIX.f90'
PARENTS = {
    'FIX': (BASE, '0b468be19f7dd66ad2f6e65a53b42f10391a4565831a96c80dddddf21934cf79'),
    'CONSERVATIVE': (WORK / 'scratch/b1_sedimentation_conservation_20261109/Cloud-BAL/docs/evidence/cp02_sedimentation_conservation_20261109/native/source/module_mp_kdm6_FIX.f90', 'ad255ae8b505af6b4ceebd177a54948d8bfff7fcd2c9f6d45c90122be0b57786'),
    'ICE_FIXED': (WORK / 'scratch/b1_ice_velocity_20261109/Cloud-BAL/docs/evidence/cp02_first_ice_velocity_20261109/native/source/module_mp_kdm6_FIX_new.f90', 'c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2'),
}
CP05_SHA = '1957f36c39d0e4bcbf16c238b90edde2a01285a03d7e1e65dd8de737c199d67c'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'expected one anchor, found {text.count(old)}: {old[:100]!r}')
    return text.replace(old, new, 1)


def selector(text, cells):
    predicates = '\n'.join(f'      if (trace_i == {i} .and. trace_j == {j}) found = .true.' for i, j in cells)
    text, n = re.subn(r'(?<=      found = .false.\n).*?(?=   end function cloud_bal_trace_cell)', predicates + '\n', text, flags=re.S)
    if n != 1:
        raise ValueError('selector anchor changed')
    text = text.replace('<= 360', '<= 180').replace('<= 900', '<= 1080').replace('min(chunk_first + 2, 900)', 'min(chunk_first + 2, 1080)').replace('min(diagnostic_chunk_first + 2, 900)', 'min(diagnostic_chunk_first + 2, 1080)')
    return text


def conservative_records(text, sediment_pre, sediment_post):
    # The same frame has REAL32 CP05 phases and explicitly tagged REAL64 phases.
    anchor = '   end subroutine cloud_bal_cp04_record\n'
    rec64 = '''\n   subroutine cloud_bal_cp04_record64(unit,phase,i,k,loop,loops,substep,mstep,values)
      implicit none
      integer, intent(in) :: unit,phase,i,k,loop,loops,substep,mstep
      real(kind=8), intent(in) :: values(:)
      write(unit) phase,i,k,loop,loops,substep,mstep,size(values),values
   end subroutine cloud_bal_cp04_record64
'''
    text = once(text, anchor, anchor + rec64)
    # Conservative post records contain states and cumulative fall only; no falk reads.
    sediment_post = sediment_post.replace(', falk(i,k,1), falk(i,k,2), &\n                     falk(i,k,3), falkn(i,k,1), falkb(i,k) /))', ' /))')
    rain_start = '      do n = 1, mstepmax\n        ! A boundary transfer is computed once from the pre-substep donor.\n'
    text = once(text, rain_start, rain_start + sediment_pre)
    rain_post = '        do k = kts, kte\n          do i = its, ite\n          qrs_tmp(i,k,1) = qrs(i,k,1)\n'
    text = once(text, rain_post, sediment_post + rain_post)
    rain_face = '''        do k = kte, kts, -1
          do i = its, ite
            if (n <= mstep(i)) then
              falk(i,k,1) = real(sed_mass(i,k,1) / &
'''
    rain_flux = '''              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
                call cloud_bal_cp04_record64(diagnostic_process_unit,18,i,k,loop,loops,n,mstep(i),(/ &
                  sed_mass(i,k,1), sed_mass(i,k+1,1), sed_mass(i,k,2), sed_mass(i,k+1,2), &
                  sed_mass(i,k,3), sed_mass(i,k+1,3), sed_number(i,k,1), sed_number(i,k+1,1), &
                  sed_volume(i,k), sed_volume(i,k+1) /))
'''
    text = once(text, rain_face, rain_face.replace('              falk(i,k,1)', rain_flux + '              falk(i,k,1)'))
    ice_face = '''        do k = kte, kts, -1
          do i = its, ite
            if (n <= mstep_i(i)) then
              falk(i,k,4) = real(sed_mass(i,k,4) / (real(dtcld,8)*real(delz(i,k),8)))
'''
    ice_pre = '''              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) then
                call cloud_bal_cp04_record(diagnostic_process_unit,20,i,k,loop,loops,n,mstep_i(i),(/ &
                  p(i,k), q(i,k), t(i,k), qci(i,k,2), nci(i,k,2), dend(i,k), delz(i,k), &
                  dtcld, fall(i,k,4), falln(i,k,2) /))
                call cloud_bal_cp04_record64(diagnostic_process_unit,22,i,k,loop,loops,n,mstep_i(i),(/ &
                  sed_mass(i,k,4), sed_mass(i,k+1,4), sed_number(i,k,2), sed_number(i,k+1,2) /))
              endif
'''
    text = once(text, ice_face, ice_face.replace('              falk(i,k,4)', ice_pre + '              falk(i,k,4)'))
    ice_end = '''              nci(i,k,2) = real((real(delz(i,k),8)*real(nci(i,k,2),8) &
                   - sed_number(i,k,2) + sed_number(i,k+1,2)) / real(delz(i,k),8))
'''
    ice_post = '''              if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
                call cloud_bal_cp04_record(diagnostic_process_unit,21,i,k,loop,loops,n,mstep_i(i),(/ &
                  p(i,k), q(i,k), t(i,k), qci(i,k,2), nci(i,k,2), dend(i,k), delz(i,k), &
                  dtcld, fall(i,k,4), falln(i,k,2) /))
'''
    return once(text, ice_end, ice_end + ice_post)


def legacy_ice_records(text):
    pre = """           if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
             call cloud_bal_cp04_record(diagnostic_process_unit,20,i,k,loop,loops,n,mstep_i(i),(/ &
               p(i,k), q(i,k), t(i,k), qci(i,k,2), nci(i,k,2), dend(i,k), delz(i,k), &
               dtcld, fall(i,k,4), falln(i,k,2) /))
"""
    flux = """           if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
             call cloud_bal_cp04_record(diagnostic_process_unit,23,i,k,loop,loops,n,mstep_i(i),(/ &
               falk(i,k,4), falkn(i,k,2) /))
"""
    post = pre.replace('process_unit,20,', 'process_unit,21,')
    start = text.index('      do n = 1, mstepmax_i\n')
    end = text.index('      do k = kte, kts, -1\n        do i = its, ite\n          supcol', start)
    ice = text[start:end]
    assignment = 'falk(i,k,4) = dend(i,k)*qci(i,k,2)*work1(i,k,4)/mstep_i(i)'
    number = 'falkn(i,k,2) = nci(i,k,2)*workn(i,k,2)/mstep_i(i)'
    if ice.count(assignment) != 2 or ice.count(number) != 2:
        raise ValueError('legacy ice source changed')
    ice = re.sub(r'^([ ]*)' + re.escape(assignment) + r'$', lambda m: pre + m.group(0), ice, flags=re.M)
    ice = ice.replace(number + '\n', number + '\n' + flux)
    for line in ('nci(i,k,2) = max(nci(i,k,2)-falkn(i,k,2)*dtcld,0.)',
                 'qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)'):
        ice = once(ice, line + '\n', line + '\n' + post)
    return text[:start] + ice + text[end:]


def generate(parent, cells, conservative):
    original = BASE.read_text().splitlines(keepends=True)
    template = selector(CP05.read_text(), cells).splitlines(keepends=True)
    source = parent.read_text().splitlines(keepends=True)
    variant_ops = difflib.SequenceMatcher(None, original, source, autojunk=False).get_opcodes()
    mapping = {x: y for tag, a, b, c, d in variant_ops if tag == 'equal' for x, y in zip(range(a, b), range(c, d))}
    insertions = {}
    sediment = {}
    for tag, a, b, c, d in difflib.SequenceMatcher(None, original, template, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        if tag != 'insert':
            raise ValueError(f'CP05 changed physics lines at {a}: {tag}')
        if conservative and a in (1044, 1102):
            sediment[a] = ''.join(template[c:d])
            continue
        left, right = mapping.get(a - 1), mapping.get(a)
        if left is None or right != left + 1:
            raise ValueError(f'cannot place insertion at original line {a}')
        insertions.setdefault(right, []).extend(template[c:d])
    out = ''.join(line for i in range(len(source) + 1) for line in insertions.get(i, []) + (source[i:i+1] if i < len(source) else []))
    if conservative:
        out = conservative_records(out, sediment[1044], sediment[1102])
    else:
        out = legacy_ice_records(out)
    operations = difflib.SequenceMatcher(None, source, out.splitlines(keepends=True), autojunk=False).get_opcodes()
    if any(tag not in ('equal', 'insert') for tag, *_ in operations):
        raise ValueError('generated source changed or deleted parent lines')
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('selector', type=Path, help='CSV with wrf_i_1based and wrf_j_1based')
    args = parser.parse_args()
    rows = list(csv.DictReader(args.selector.open(newline='')))
    cells = sorted({(int(r['wrf_i_1based']), int(r['wrf_j_1based'])) for r in rows})
    if len(cells) != len(rows) or not cells:
        raise ValueError('selector must contain unique native columns')
    if sha(CP05) != CP05_SHA:
        raise ValueError('CP05 template hash changed')
    receipt = {'selector_sha256': sha(args.selector), 'columns': len(cells), 'template_sha256': sha(CP05), 'arms': {}}
    for arm, (parent, expected) in PARENTS.items():
        if sha(parent) != expected:
            raise ValueError(f'{arm} parent hash changed')
        output = HERE / f'module_mp_kdm6_{arm}.f90'
        output.write_text(generate(parent, cells, arm != 'FIX'))
        receipt['arms'][arm] = {'parent_sha256': expected, 'source_sha256': sha(output)}
    (HERE / 'source_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
