#!/usr/bin/env python3
"""Generate a selected-cell CP04 diagnostic from the frozen CP03 source."""
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
BASE = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/native/source/module_mp_kdm6_FIX.f90'
COHORT = EVIDENCE / 'cohorts/results/unique_global_corners.csv'
BASE_SHA = '605b2d6895229f287dd6dc675b84dea0596f7a247a18bf80e3615635defb0295'
COHORT_SHA = 'c2ba19be993cd82dfeac0ff1b3a02659d6c137b733903e563da91f4024aa65b9'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    5: ('PROCESS_RATES', [f'{n}(i,k)' for n in RATE_NAMES] + ['delta2','delta3']),
    6: ('PRE_UPDATE', STATE + ['work2(i,k)','dtcld']),
    7: ('LATENT_INPUT', ['work2(i,k)','xlwork2','cpm(i,k)','dtcld','xl(i,k)','xlf']),
    8: ('POST_UPDATE', STATE), 9: ('SED_PRE', SED_PRE), 10: ('SED_POST', SED_POST),
    11: ('FINAL_COND_PRE', COND), 12: ('FINAL_COND_POST', COND),
    13: ('SURFACE_PRE', SURFACE), 14: ('SURFACE_POST', SURFACE),
    15: ('PREVP_RAW', ['prevp(i,k)','qrs(i,k,1)','satdt','dtcld']),
    16: ('PREVP_QR_CAP', ['prevp(i,k)']), 17: ('PREVP_SAT_CAP', ['prevp(i,k)']),
}
LABEL_IDS = {name: number for number, (name, _) in PHASES.items()}
LABEL_IDS['POST_STEP'] = 8
CP03_IDS = {1: 9, 2: 10, 3: 13, 4: 14, 5: 11, 6: 12}


def once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected one exact anchor, got {text.count(old)}')
    return text.replace(old, new, 1)


def record_call(phase, indent):
    _, fields = PHASES[phase]
    loop, loops = ('0','0') if phase in (1,2) else ('loop','loops')
    k = 'kts' if phase in (13,14) else 'k'
    sub, mstep = ('n','mstep(i)') if phase in (9,10) else ('0','0')
    lines = [indent + 'if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &',
             indent + f'  call cloud_bal_cp04_record(diagnostic_process_unit,{phase},i,{k}, &',
             indent + f'       {loop},{loops},{sub},{mstep},(/ &']
    for start in range(0, len(fields), 3):
        part = fields[start:start+3]
        last = start + 3 >= len(fields)
        lines.append(indent + '       ' + ', '.join(part) + (' /))' if last else ', &'))
    return '\n'.join(lines) + '\n'


def replace_writes(text):
    lines = text.splitlines(keepends=True)
    result, hits = [], {}
    i = 0
    while i < len(lines):
        if (i + 1 < len(lines) and 'if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &' in lines[i]
            and ('write(diagnostic_trace_unit,*)' in lines[i+1] or 'write(diagnostic_process_unit,*)' in lines[i+1])):
            start = i
            i += 1
            statement = lines[i]
            while statement.rstrip().endswith('&'):
                i += 1
                statement += lines[i]
            i += 1
            m = re.search(r"write\(diagnostic_(?:trace|process)_unit,\*\)\s*'([^']+)'", statement)
            if not m:
                raise ValueError('unrecognized diagnostic write')
            label = m.group(1)
            hits[label] = hits.get(label, 0) + 1
            if label == 'PREVP_FORMULA':
                continue  # superseded by RAW and actual caps; avoid lossy REAL64 n0r conversion
            if label == 'CP03':
                phase_match = re.search(r"'CP03',\s*(\d+)", statement)
                phase = CP03_IDS[int(phase_match.group(1))]
            else:
                phase = LABEL_IDS[label]
            result.append(record_call(phase, re.match(r'\s*', lines[start]).group(0)))
        else:
            result.append(lines[i])
            i += 1
    expected = {'ENTRY_RAW':1,'ENTRY_CLAMPED':1,'SATURATION':1,'SATDT':1,
                'PROCESS_RATES':2,'PRE_UPDATE':2,'LATENT_INPUT':2,'POST_STEP':1,
                'PREVP_FORMULA':1,'PREVP_RAW':1,'PREVP_QR_CAP':1,'PREVP_SAT_CAP':2,'CP03':6}
    if hits != expected:
        raise ValueError(f'diagnostic statement inventory changed: {hits}')
    return ''.join(result)


def generate():
    if sha(BASE) != BASE_SHA or sha(COHORT) != COHORT_SHA:
        raise ValueError('source or cohort pin differs')
    rows = list(csv.DictReader(COHORT.open()))
    cells = [(int(row['wrf_i_1based']), int(row['wrf_j_1based'])) for row in rows]
    if len(cells) != 123 or len(set(cells)) != 123:
        raise ValueError('expected 123 unique final cohort cells')
    text = BASE.read_text().replace('<= 540', '<= 360')
    tests = '\n'.join(f'      if (trace_i == {i} .and. trace_j == {j}) found = .true.' for i,j in cells)
    text, n = re.subn(r'(?<=      found = .false.\n).*?(?=   end function cloud_bal_trace_cell)', tests+'\n', text, flags=re.S)
    if n != 1:
        raise ValueError('trace predicate anchor differs')
    helper = '''   subroutine cloud_bal_cp04_record(unit,phase,i,k,loop,loops,substep,mstep,values)
      implicit none
      integer, intent(in) :: unit,phase,i,k,loop,loops,substep,mstep
      real, intent(in) :: values(:)
      write(unit) phase,i,k,loop,loops,substep,mstep,size(values),values
   end subroutine cloud_bal_cp04_record

'''
    text = once(text, '   subroutine cloud_bal_state_open(', helper + '   subroutine cloud_bal_state_open(', 'binary helper')
    for stage in ('selected_entry','selected_return'):
        start = text.index("call cloud_bal_state_open(cloud_bal_state_unit,'" + stage + "'")
        end = text.index('     close(cloud_bal_state_unit)', start)
        block = text[start:end].replace('kts,kte,14,cloud_bal_state_records)', 'kts,kte,16,cloud_bal_state_records)').replace('cloud_bal_state_values(1:14)', 'cloud_bal_state_values(1:16)')
        needle = 'pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)'
        if block.count(needle) != 1:
            raise ValueError(f'{stage}: selected field anchor differs')
        block = block.replace(needle, 'pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &\n               p(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j), &\n               pii(cloud_bal_state_i,cloud_bal_state_k,cloud_bal_state_j) /)')
        text = text[:start] + block + text[end:]
    start = text.index('     if (itimestep >= 1 .and. itimestep <= 360) then\n       do i = its,ite\n         if (cloud_bal_trace_cell(i,j)) then')
    end = text.index('     if (itimestep == 1) then', start)
    replacement = '''     if (itimestep >= 1 .and. itimestep <= 360) then
       do i = its,ite
         if (cloud_bal_trace_cell(i,j)) then
           cloud_bal_trace_file = 'surface_cp04_rank'//trim(cloud_bal_trace_rank_text)//'.bin'
           open(newunit=cloud_bal_trace_unit,file=trim(cloud_bal_trace_file), &
                status='unknown',position='append',access='stream', &
                form='unformatted',action='write')
           write(cloud_bal_trace_unit) 'C4SR0001', cloud_bal_trace_rank, &
                cloud_bal_trace_call_id,itimestep,j,i,rainncv(i,j),rain(i,j),sr(i,j)
           close(cloud_bal_trace_unit)
         endif
       enddo
     endif

'''
    text = text[:start] + replacement + text[end:]
    open_old = '''     diagnostic_trace_file = 'kdm6_trace_rank'//trim(diagnostic_rank_text)//'.bits'
     open(newunit=diagnostic_trace_unit,file=trim(diagnostic_trace_file), &
          status='unknown',position='append',action='write')
     diagnostic_trace_file = 'cp03_rank'//trim(diagnostic_rank_text)//'.bits'
     open(newunit=diagnostic_process_unit,file=trim(diagnostic_trace_file), &
          status='unknown',position='append',action='write')'''
    open_new = '''     diagnostic_trace_file = 'cp04_rank'//trim(diagnostic_rank_text)//'.bin'
     open(newunit=diagnostic_process_unit,file=trim(diagnostic_trace_file), &
          status='unknown',position='append',access='stream', &
          form='unformatted',action='write')
     write(diagnostic_process_unit) 'C4FR0001',diagnostic_rank,diagnostic_call_id, &
          diagnostic_itimestep,lat,its,ite,kts,kte, &
          qmin,t0c,rv,cpv,cliq,psat,ep2,xlv0,xls,cice'''
    text = once(text, open_old, open_new, 'inner frame open')
    close_old = '''   if (diagnostic_trace_active == 1) then
     close(diagnostic_trace_unit)
     close(diagnostic_process_unit)
   endif'''
    close_new = '''   if (diagnostic_trace_active == 1) then
     write(diagnostic_process_unit) -1
     close(diagnostic_process_unit)
   endif'''
    text = once(text, close_old, close_new, 'inner frame end')
    text = replace_writes(text)
    if 'write(diagnostic_trace_unit,*)' in text or "'CP03'" in text:
        raise ValueError('legacy ASCII diagnostic remains')
    schema = {'format':'CP04 framed Fortran stream, big-endian int32 and IEEE REAL32 (ifx -convert big_endian)',
              'frame_magic':'C4FR0001','frame_header_int32':['rank','call_id','itimestep','j','its','ite','kts','kte'],
              'frame_constants_real32':['qmin','t0c','rv','cpv','cliq','psat','ep2','xlv0','xls','cice'],
              'record_header_int32':['phase','i','k','loop','loops','substep','mstep','nfields'],
              'record_payload':'nfields REAL32 values in the exact field order below; signed zero preserved',
              'frame_end_int32':-1,
              'phases':{str(n):{'name':name,'fields':fields} for n,(name,fields) in PHASES.items()},
              'surface_return':{'file':'surface_cp04_rankN.bin','record_magic':'C4SR0001','key_int32':['rank','call_id','itimestep','j','i'],'fields_real32':['rainncv(i,j)','rain(i,j)','sr(i,j)']},
              'wrapper_selected':{'format':'CBSP0001 keyed stage 6 entry / 7 return',
                                  'fields':['TH','QV','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG','DEN','TK=TH*PII','P','PII']},
              'field_units':{'p':'Pa','t':'K','q/qci/qrs':'kg kg-1 model mixing-ratio basis','den/dend':'kg m-3 driver density','nci/nrs':'m-3 internal number','mass_process_rates':'kg kg-1 s-1','number_process_rates':'m-3 s-1','dtcld':'s','rain/rainncv':'mm'},
              'semantics':['Actual 1..360 timestep, per selected core and each 39 levels; ENTRY phases use loop=loops=0; later phases carry actual loop/loops.',
                           'SED only rain/snow/graupel actual n<=mstep; SED_PRE never reads falk; ice sedimentation is separate and not decomposed.',
                           'SATDT captures the liquid-water calculation at its actual later source location; an ice SATDT calculation later in the source is separate. It is not inferred from prior SATURATION.',
                           'Rates are recorded after source limiting immediately before respective cold/warm update; delta2 and delta3 reflect actual branch state.',
                           'FINAL_COND captures freshly recomputed qs_water at pcond source update; LATENT captures actual cpm/xl/xlf.',
                           'Surface pre/post and PREVP caps are conditional; absence is missing, never synthesized zero.',
                           'PII and P are captured at wrapper entry/return; intercall difference is total non-KDM6 change, not pure transport.',
                           'First-step all-domain CBSP stages 1..5 retained for parity against earlier uninstrumented-physics quick probes.']}
    return text, schema


def main():
    text, schema = generate()
    source = EVIDENCE / 'native/source/module_mp_kdm6_FIX.f90'
    schema_path = EVIDENCE / 'native/schema/cp04_schema.json'
    if source.exists() or schema_path.exists():
        raise FileExistsError('refusing to overwrite prior generated source/schema')
    source.write_text(text)
    schema_path.write_text(json.dumps(schema, indent=2)+'\n')
    print('source', sha(source), 'schema', sha(schema_path))


if __name__ == '__main__':
    main()
