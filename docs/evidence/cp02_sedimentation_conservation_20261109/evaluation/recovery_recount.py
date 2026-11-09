#!/usr/bin/env python3
"""Recount 15 frozen recovery conditions for B1 and the candidate."""
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE/'results'
CANDIDATE = 'CONSERVATIVE_SEDIMENTATION'
B1 = 'IMPROVED_BG_FIXED'


def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    path = RESULTS/'categorical_scores.csv'; receipt = json.loads((RESULTS/'receipt.json').read_text())
    if receipt['outputs']['categorical_scores.csv'] != digest(path): raise ValueError('score input identity differs')
    with path.open(newline='') as f:
        scores = {(int(r['lead_hour']),float(r['threshold_mm']),r['case']):r for r in csv.DictReader(f)}
    def exact(r):
        h,m,f = (int(r[k]) for k in ('hit','miss','false_alarm'))
        return Fraction(h,h+m+f)
    rows = []
    for lead in range(2,7):
        for threshold in (.1,.5,1.):
            original,b1,candidate = (scores[lead,threshold,case] for case in ('ORIGINAL',B1,CANDIDATE))
            b1_pass=exact(b1)>=exact(original); candidate_pass=exact(candidate)>=exact(original)
            rows.append({'lead_hour':lead,'threshold_mm':threshold,
                         'original_hit':original['hit'],'original_miss':original['miss'],'original_false_alarm':original['false_alarm'],
                         'b1_hit':b1['hit'],'b1_miss':b1['miss'],'b1_false_alarm':b1['false_alarm'],
                         'candidate_hit':candidate['hit'],'candidate_miss':candidate['miss'],'candidate_false_alarm':candidate['false_alarm'],
                         'b1_recovered':b1_pass,'candidate_recovered':candidate_pass,
                         'newly_recovered':candidate_pass and not b1_pass,
                         'lost_recovery':b1_pass and not candidate_pass})
    target=HERE/'recovery_condition_recount.csv'
    with target.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    summary={'b1_recovered':sum(r['b1_recovered'] for r in rows),
             'candidate_recovered':sum(r['candidate_recovered'] for r in rows),
             'newly_recovered':sum(r['newly_recovered'] for r in rows),
             'lost_recovery':sum(r['lost_recovery'] for r in rows),
             'total':len(rows),'method':'exact H/(H+M+F) versus ORIGINAL per lead/threshold',
             'scorer_sha256':digest(Path(__file__)), 'input_sha256':digest(path),'output_sha256':digest(target)}
    (HERE/'recovery_condition_recount.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__': main()
