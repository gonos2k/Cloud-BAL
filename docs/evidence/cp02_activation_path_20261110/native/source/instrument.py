#!/usr/bin/env python3
"""Insert paired diagnostic records into the frozen PR157 forecast sources."""
import argparse, csv, difflib, hashlib, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NATIVE = Path(__file__).resolve().parents[1]
PRIOR = ROOT / 'cp02_low_threshold_process_20261110/native/source/instrument.py'
FORECAST = ROOT / 'cp02_pulse_path_20261110/forecast/source'
spec = importlib.util.spec_from_file_location('prior_instrument', PRIOR)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s, a, b):
    if s.count(a) != 1: raise ValueError(f'anchor occurs {s.count(a)} times: {a[:100]!r}')
    return s.replace(a, b, 1)

original_selector = prior.selector
def select(text, cells):
    text = original_selector(text, cells)
    for name in ('itimestep', 'diagnostic_itimestep'):
        old = f'({name} >= 1 .and. {name} <= 180) .or. &\n       ({name} >= 721 .and. {name} <= 1080)'
        new = f'{name} >= 361 .and. {name} <= 540'
        if text.count(old) != (2 if name == 'itimestep' else 1): raise ValueError(f'window anchor differs: {name}: {text.count(old)}')
        text = text.replace(old, new)
    text = text.replace('<= 1080', '<= 540').replace('+ 2, 540)', '+ 2, 540)')
    return text

prior.selector = select
# Preserve the original function for selector composition.

STATE = 'p(i,k), q(i,k), t(i,k), den(i,k), delz(i,k), dtcld, &\n               qci(i,k,1), qci(i,k,2), qrs(i,k,1), qrs(i,k,2), qrs(i,k,3), &\n               nci(i,k,1), nci(i,k,2), nci(i,k,3), nrs(i,k,1), nrs(i,k,2), nrs(i,k,3), brs(i,k)'
SURFACE = 'rain(i), rainncv(i)'

def state(phase):
    return f'''     do k = kts, kte
       do i = its, ite
         if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
           call cloud_bal_cp04_record(diagnostic_process_unit,{phase},i,k,loop,loops,0,0,(/ &
               {STATE} /))
       enddo
     enddo
'''

def surface(phase, loop, loops):
    extra = '' if phase == 40 else f'''         call cloud_bal_cp04_record(diagnostic_surface_unit,{phase+10},i,kts,{loop},{loops},0,0,(/ tstepsnow(i), tstepgraup(i) /))
'''
    return f'''     do i = its, ite
       if (diagnostic_surface_active == 1 .and. cloud_bal_trace_cell(i,lat)) then
         call cloud_bal_cp04_record(diagnostic_surface_unit,{phase},i,kts,{loop},{loops},0,0,(/ {SURFACE} /))
         if (present(snow) .and. present(snowncv)) &
           call cloud_bal_cp04_record(diagnostic_surface_unit,{phase+20},i,kts,{loop},{loops},0,0,(/ snow(i), snowncv(i) /))
         if (present(graupel) .and. present(graupelncv)) &
           call cloud_bal_cp04_record(diagnostic_surface_unit,{phase+30},i,kts,{loop},{loops},0,0,(/ graupel(i), graupelncv(i) /))
{extra}       endif
     enddo
'''

def add_records(s):
    s = once(s, '   integer                            :: diagnostic_trace_active\n',
             '   integer                            :: diagnostic_trace_active\n   integer                            :: diagnostic_surface_active, diagnostic_surface_unit\n')
    anchor = '   diagnostic_trace_active = 0\n'
    start = '''   diagnostic_surface_active = 0
   if (diagnostic_itimestep >= 1 .and. diagnostic_itimestep <= 540) then
     do diagnostic_i = its, ite
       if (cloud_bal_trace_cell(diagnostic_i,lat)) diagnostic_surface_active = 1
     enddo
   endif
   if (diagnostic_surface_active == 1) then
     write(diagnostic_rank_text,'(i0)') diagnostic_rank
     diagnostic_chunk_first = ((diagnostic_itimestep - 1) / 3) * 3 + 1
     diagnostic_chunk_last = min(diagnostic_chunk_first + 2, 540)
     write(diagnostic_chunk_text,'(i6.6,"-",i6.6)') diagnostic_chunk_first, diagnostic_chunk_last
     diagnostic_trace_file = 'surface_t'//trim(diagnostic_chunk_text)//'_rank'//trim(diagnostic_rank_text)//'.bin'
     open(newunit=diagnostic_surface_unit,file=trim(diagnostic_trace_file), &
          status='unknown',position='append',access='stream',form='unformatted',action='write')
     write(diagnostic_surface_unit) 'C4FR0001',diagnostic_rank,diagnostic_call_id, &
          diagnostic_itimestep,lat,its,ite,kts,kte, &
          qmin,t0c,rv,cpv,cliq,psat,ep2,xlv0,xls,cice
   endif
'''
    s = once(s, anchor, start + anchor)
    anchor = '   do i = its,ite\n     rainncv(i) = 0.\n'
    s = once(s, anchor, surface(40, '0', '0') + anchor)
    anchor = '   loops = max(nint(delt/dtcldcr),1)\n'
    s = once(s, anchor, surface(41, '0', '0') + anchor)
    anchor = '   do loop = 1,loops\n'
    s = once(s, anchor, anchor + surface(42, 'loop', 'loops') + state(30))
    anchor = '           if(qci(i,k,1).le.qmin)then\n'
    pre = '''           if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
             call cloud_bal_cp04_record(diagnostic_process_unit,32,i,k,loop,loops,0,0,(/ &
               ''' + STATE + ''' /))
'''
    s = once(s, anchor, pre + anchor)
    anchor = '          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then\n'
    mid = pre.replace('process_unit,32,', 'process_unit,33,')
    pos = s.index(pre + '           if(qci(i,k,1).le.qmin)then\n')
    s = s[:pos] + once(s[pos:], anchor, mid + anchor)
    update = '          rainncv(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rainncv(i)\n'
    executed = '''          if (diagnostic_surface_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
            call cloud_bal_cp04_record(diagnostic_surface_unit,46,i,kts,loop,loops,0,0,(/ &
              fall(i,kts,1), fall(i,kts,2), fall(i,kts,3), fall(i,kts,4), &
              fallsum, fallsum_qsi, fallsum_qg, delz(i,kts), denr, dtcld, rain(i), rainncv(i) /))
'''
    s = once(s, update, executed + update)
    update = '          rain(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rain(i)\n'
    s = once(s, update, update + executed.replace('surface_unit,46,', 'surface_unit,47,'))
    anchor = '''        enddo
      enddo 
   enddo                  

   if (diagnostic_trace_active == 1) then
'''
    s = once(s, anchor, '''        enddo
      enddo 
''' + state(34) + surface(43, 'loop', 'loops') + '''   enddo                  

   if (diagnostic_surface_active == 1) then
     write(diagnostic_surface_unit) -1
     close(diagnostic_surface_unit)
   endif

   if (diagnostic_trace_active == 1) then
''')
    fields = 'sw(i,k), nci(i,k,1), nci(i,k,3), q(i,k), qci(i,k,1), t(i,k), &\n               den(i,k), xl(i,k), cpm(i,k), dtcld, pi, denr'
    def activation_record(phase):
        return f"""          if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &
            call cloud_bal_cp04_record(diagnostic_process_unit,{phase},i,k,loop,loops,0,0,(/ &
               {fields} /))
"""
    anchor = '           if(sw(i,k).gt.0.) then\n'
    s = once(s, anchor, activation_record(35) + anchor)
    anchor = '          tr=ttp/t(i,k)\n'
    pos = s.index(activation_record(35))
    if s[pos:].count(anchor) < 1: raise ValueError('post activation anchor missing')
    s = s[:pos] + s[pos:].replace(anchor, activation_record(36) + anchor, 1)
    return s

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('selector', type=Path); args = ap.parse_args()
    rows = list(csv.DictReader(args.selector.open(newline='')))
    cells = sorted({(int(r['i_fortran']), int(r['j_fortran'])) for r in rows})
    if len(cells) != len(rows) or not cells: raise ValueError('selector must contain unique native columns')
    receipt = {'selector_sha256':sha(args.selector), 'columns':len(cells), 'arms':{}}
    for arm in ('CONTROL','MP10'):
        parent = FORECAST / f'{arm}.f90'
        out = add_records(prior.generate(parent, cells, True))
        ops = difflib.SequenceMatcher(None, parent.read_text().splitlines(keepends=True), out.splitlines(keepends=True), autojunk=False).get_opcodes()
        if any(op[0] not in ('equal','insert') for op in ops): raise ValueError(f'{arm} changed parent physics')
        target = NATIVE / 'source' / f'{arm}.f90'; target.write_text(out)
        receipt['arms'][arm] = {'parent_sha256':sha(parent), 'source_sha256':sha(target), 'insertion_only':True}
    (NATIVE/'source/source_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
if __name__ == '__main__': main()
