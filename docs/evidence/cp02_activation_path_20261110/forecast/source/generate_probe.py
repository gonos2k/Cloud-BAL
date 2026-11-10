#!/usr/bin/env python3
"""Insert trace-only writes around the entry and inner NN bounds for one native cell."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'MP10_NN_END.f90'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    identity=json.loads((HERE/'source_receipt.json').read_text())
    if sha(SOURCE)!=identity['candidate_sha256']:raise ValueError('candidate source changed')
    text=SOURCE.read_text()
    outer='\n       nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)\n'
    inner='''            if (loop == loops) then
              nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
            else
              nci(i,k,3) = min(nci(i,k,3),2.e10)
            endif
'''
    if text.count(outer)!=1 or text.count(inner)!=1:raise ValueError('probe anchor differs')
    def record(label, inside):
        info='loop,loops,transfer(dtcld,0),' if inside else ''
        return f"       if (lat == 86 .and. i == 156 .and. k == 14) &\n         write(*,*) 'NN_END_TRACE {label}', {info}transfer(nci(i,k,3),0)\n"
    text=text.replace(outer,'\n'+record('ENTRY_PRE',False)+outer.lstrip('\n')+record('ENTRY_POST',False),1)
    text=text.replace(inner,record('LOOP_PRE',True)+inner+record('LOOP_POST',True),1)
    target=HERE/'MP10_NN_END_PROBE.f90';target.write_text(text)
    receipt={'status':'PASS','candidate_source_sha256':sha(SOURCE),'diagnostic_source_sha256':sha(target),'generator_sha256':sha(Path(__file__)),'cell_ijk':[156,86,14],'added_only':'four guarded WRITE records around original and modified bounds; no physical variable modified'}
    (HERE/'probe_source_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
