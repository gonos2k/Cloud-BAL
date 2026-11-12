"""Convert the captured binary32 words to the Intel big-endian stream."""
import gzip,json,sys
from pathlib import Path
CAP=Path(__file__).resolve().parent.parent/'native/capturedsmallrecords/rank3.jsonl.gz'
three='th qv qc qr qi qs qg nn nc ni nr bg diag_rhog den pii p delz refl_10cm re_cloud re_ice re_snow'.split()
two='xland rain rainncv snow snowncv sr graupel graupelncv'.split()
constants='delt g cpd cpv ccn0 rd rv t0c ep1 ep2 qmin xls xlv0 xlf0 den0 denr scale_h qnn_land_mult qnn_sea_mult ncmin_land ncmin_sea cliq cice psat'.split()
def main():
 rows={}
 with gzip.open(CAP,'rt') as f:
  for line in f:
   x=json.loads(line)
   if x['event']=='entry':rows[tuple(x['cell'])]=x
 assert len(rows)==116*39
 one=rows[(118,72,1)]
 def word(rec,key): return bytes.fromhex(rec['fields'][key]['hex_le'])[::-1]
 with Path(sys.argv[1]).open('wb') as f:
  for name in three:
   for k in range(1,40):
    for i in range(118,234):f.write(word(rows[(i,72,k)],name))
  for name in two:
   for i in range(118,234):f.write(word(rows[(i,72,1)],name))
  for name in constants:f.write(word(one,name))
 print('input words',len(three)*116*39+len(two)*116+len(constants))

if __name__ == '__main__':
 main()
