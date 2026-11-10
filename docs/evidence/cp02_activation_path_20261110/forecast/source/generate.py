#!/usr/bin/env python3
"""Gate only the last per-loop aerosol-number floor in the pinned MP10 parent."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PARENT=ROOT/'docs/evidence/cp02_pulse_path_20261110/forecast/source/MP10.f90'
EXPECTED='4604dc031d618a6feeb43a72a7cfabc656abf7f3e4eb591b0c7724f7e490f586'
OLD='            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)\n'
NEW='''            if (loop == loops) then
              nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
            else
              nci(i,k,3) = min(nci(i,k,3),2.e10)
            endif
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if sha(PARENT)!=EXPECTED:raise ValueError('MP10 parent differs')
    source=PARENT.read_text()
    if source.count('nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)')!=2 or source.count(OLD)!=1:raise ValueError('floor anchors differ')
    location=source.index(OLD)
    if not source.index('   do loop = 1,loops\n')<location<source.index('   end subroutine kdm62d'):raise ValueError('floor is outside inner loop')
    target=HERE/'MP10_NN_END.f90';target.write_text(source.replace(OLD,NEW,1))
    output={'status':'PASS','parent_sha256':sha(PARENT),'candidate_sha256':sha(target),'generator_sha256':sha(Path(__file__)),'change':'gate only last inner-loop NN lower bound until loop==loops; upper bound remains each loop','outer_entry_floor_unchanged':True,'parent_floor_occurrences':2,'changed_last_occurrence':True}
    (HERE/'source_receipt.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
if __name__=='__main__':main()
