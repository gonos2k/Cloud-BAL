from pathlib import Path
import json,hashlib,csv,re
base=Path('docs/evidence/cp02_state_path_20261104/native/patched/module_mp_kdm6_FIX.f90')
out=Path('docs/evidence/cp02_rain_number_process_20261104/native')
s=base.read_text().replace('<= 360','<= 540')

cohort=Path('docs/evidence/cp02_rain_number_process_20261104/newcohorts/unique_global_corners.csv')
assert hashlib.sha256(cohort.read_bytes()).hexdigest()=='169adba4177e9efcd11d54603a4ce451593c24927b6f8e0a93a2d16480eeddc3'
rows=list(csv.DictReader(cohort.open())); assert len(rows)==36
expr='\n'.join(f"      if (trace_i == {int(x['wrf_i_1based'])} .and. trace_j == {int(x['wrf_j_1based'])}) found = .true." for x in rows)
s,n=re.subn(r'(?<=      found = .false.\n).*?(?=   end function cloud_bal_trace_cell)',expr+'\n',s,flags=re.S);assert n==1

s=s.replace('integer                            :: diagnostic_trace_unit, diagnostic_i','integer                            :: diagnostic_trace_unit, diagnostic_process_unit, diagnostic_i')
needle="     open(newunit=diagnostic_trace_unit,file=trim(diagnostic_trace_file), &\n          status='unknown',position='append',action='write')"
assert s.count(needle)==1
s=s.replace(needle,needle+"\n     diagnostic_trace_file = 'cp03_rank'//trim(diagnostic_rank_text)//'.bits'\n     open(newunit=diagnostic_process_unit,file=trim(diagnostic_trace_file), &\n          status='unknown',position='append',action='write')")
s=s.replace('if (diagnostic_trace_active == 1) close(diagnostic_trace_unit)','if (diagnostic_trace_active == 1) then\n     close(diagnostic_trace_unit)\n     close(diagnostic_process_unit)\n   endif')
pre=['q(i,k)','t(i,k)','qci(i,k,1)','qci(i,k,2)','qrs(i,k,1)','qrs(i,k,2)','qrs(i,k,3)','nrs(i,k,1)','den(i,k)','dend(i,k)','delz(i,k)','dtcld','brs(i,k)','nci(i,k,1)','nci(i,k,2)','nci(i,k,3)','fall(i,k,1)','fall(i,k,2)','fall(i,k,3)','falln(i,k,1)','fallb(i,k)']
post=pre+['falk(i,k,1)','falk(i,k,2)','falk(i,k,3)','falkn(i,k,1)','falkb(i,k)']
surface=['fall(i,kts,1)','fall(i,kts,2)','fall(i,kts,3)','fall(i,kts,4)','fallsum','fallsum_qsi','fallsum_qg','delz(i,kts)','denr','dtcld','rain(i)','rainncv(i)']
cond=['q(i,k)','t(i,k)','qci(i,k,1)','qci(i,k,2)','nci(i,k,1)','nci(i,k,2)','nci(i,k,3)','pcond(i,k)','dtcld','xl(i,k)','cpm(i,k)']
def rec(phase, vals, kval='k', sub='0', step='0', indent='          '):
  lines=[indent+'if (diagnostic_trace_active == 1 .and. cloud_bal_trace_cell(i,lat)) &',indent+"  write(diagnostic_process_unit,*) 'CP03', "+str(phase)+', diagnostic_rank, diagnostic_call_id, &',indent+'    diagnostic_itimestep, loop, loops, i, lat, '+kval+', '+sub+', '+step+', '+str(len(vals))+', &']
  for j in range(0,len(vals),3):
    lines.append(indent+'    '+', '.join('transfer('+x+',0)' for x in vals[j:j+3])+(', &' if j+3<len(vals) else ''))
  return '\n'.join(lines)+'\n'
def loop(phase,vals): return '        do k = kts, kte\n          do i = its, ite\n            if (n <= mstep(i)) then\n'+rec(phase,vals,sub='n',step='mstep(i)',indent='              ')+'            endif\n          enddo\n        enddo\n'
a='      do n = 1, mstepmax\n'; assert s.count(a)==1;s=s.replace(a,a+loop(1,pre))
a='        do k = kts, kte\n          do i = its, ite\n          qrs_tmp(i,k,1) = qrs(i,k,1)';assert s.count(a)==1;s=s.replace(a,loop(2,post)+a)
a='        if(fallsum.gt.0.) then\n          rainncv(i) =';assert s.count(a)==1;s=s.replace(a,'        if(fallsum.gt.0.) then\n'+rec(3,surface,kval='kts',indent='          ')+'          rainncv(i) =')
a='          rain(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rain(i)\n';assert s.count(a)==1;s=s.replace(a,a+rec(4,surface,kval='kts',indent='          '))
a='          if(pcond(i,k).eq.-qci(i,k,1)/dtcld) then';assert s.count(a)==1;s=s.replace(a,rec(5,cond)+a)
a='          t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld\n';assert s.count(a)==1;s=s.replace(a,a+rec(6,cond))
(out/'source/module_mp_kdm6_FIX.f90').write_text(s)
schema={'format':'Fortran list-directed ASCII; logical CP03 records may span physical lines; real values encoded via transfer(real,0) signed int32 bits', 'key':['marker','phase','rank','call_id','itimestep','loop','loops','i','j','k','substep','mstep','nfields'], 'phases':{str(i):{'name':n,'fields':v} for i,n,v in [(1,'SED_PRE',pre),(2,'SED_POST',post),(3,'SURFACE_PRE',surface),(4,'SURFACE_POST',surface),(5,'FINAL_COND_PRE',cond),(6,'FINAL_COND_POST',cond)]},'notes':['SED records cover actual rain/snow/graupel sedimentation substeps only, n <= mstep; all values taken before or after the entire substep, before slopes are recalculated. falk values are not read in PRE.','Surface phases occur only where fallsum > 0 and use kts; absent records do not imply zero.','Final condensation phases surround only the pcond conditional and updates, after pcond is computed.','State and legacy trace streams remain separate.']}
p=out/'schema/cp03_schema.json';p.write_text(json.dumps(schema,indent=2)+'\n');print(hashlib.sha256(p.read_bytes()).hexdigest())
