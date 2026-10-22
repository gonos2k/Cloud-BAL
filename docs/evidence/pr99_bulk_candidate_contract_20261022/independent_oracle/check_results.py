#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path('/var/tmp/pr99_bulk_oracle_finalv2_20261022')
cases=json.loads((p/'cases.json').read_text())['cases']
lines=Path(sys.argv[1]).read_text().splitlines()
actual={int(a): b.upper()=='T' for a,b in (line.split() for line in lines if line.strip())}
if set(actual)!=set(range(1,len(cases)+1)): raise SystemExit(f'output ids differ: {sorted(actual)}')
false_accept=[]; fatal=False; valid_rejections=[]; accepted=0
for ix,c in enumerate(cases,1):
    got=actual[ix]; accepted+=got
    if got and not c['oracle_valid']: false_accept.append(c['name'])
    if c['name'].startswith('actual_fatal'): fatal=got
    if c['oracle_valid'] and not got: valid_rejections.append(c['name'])
if false_accept: raise SystemExit('FALSE ACCEPT: '+', '.join(false_accept))
if not fatal: raise SystemExit('actual fatal typed input was rejected')
print(json.dumps({'cases':len(cases),'accepted':accepted,'rejected':len(cases)-accepted,'false_accepts':false_accept,'actual_fatal_accepted':fatal,'conservative_valid_rejections':valid_rejections,'conservative_valid_rejection_count':len(valid_rejections)},indent=2))
