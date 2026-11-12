"""Compare every active wrapper output word to the captured native return."""
import gzip,json,sys
from pathlib import Path
from input import three,two,constants,CAP
p=Path(sys.argv[1]); blob=p.read_bytes(); rows={}
with gzip.open(CAP,'rt') as f:
 for line in f:
  d=json.loads(line)
  if d['event']=='return': rows[tuple(d['cell'])]=d
pos=0; result={}
for name in three:
 total=0; examples=[]
 for k in range(1,40):
  for i in range(118,234):
   word=blob[pos:pos+4][::-1].hex();pos+=4; expected=rows[i,72,k]['fields'][name]['hex_le']
   if word != expected:
    total+=1
    if len(examples)<3:examples.append({'i':i,'k':k,'replay_hex_le':word,'native_hex_le':expected})
 result[name]={'mismatches':total,'examples':examples}
for name in two:
 total=0; examples=[]
 for i in range(118,234):
  word=blob[pos:pos+4][::-1].hex();pos+=4;expected=rows[i,72,1]['fields'][name]['hex_le']
  if word!=expected:
   total+=1
   if len(examples)<3:examples.append({'i':i,'replay_hex_le':word,'native_hex_le':expected})
 result[name]={'mismatches':total,'examples':examples}
assert pos+4*len(constants)==len(blob)
match=all(x['mismatches']==0 for x in result.values())
print(json.dumps({'terminal':str(p),'native_word_match':match,'fields':result},indent=2))
if not match: sys.exit(1)
