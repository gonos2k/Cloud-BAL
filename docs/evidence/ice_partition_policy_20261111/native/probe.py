"""Read-only GDB ABI capture of first-step selected cells; no inferior writes."""
import gdb,hashlib,json,os,struct
from pathlib import Path
R=int(os.environ['PMI_RANK']); O=Path(os.environ['ICE_OUT']); O.mkdir(exist_ok=True)
with Path(gdb.current_progspace().filename).open('rb') as f:
 if hashlib.file_digest(f,'sha256').hexdigest()!='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f': raise RuntimeError('bad exe')
S=O.joinpath(f'rank{R}.jsonl').open('x',buffering=1)
CELLS=[(212,84,20),(199,111,22),(219,236,17),(209,94,17),(192,72,26)]
SYMS={'QI':0x3eea388,'QS':0x3eea370,'NI':0x3eea2e0}
NAMES=('ids','ide','jds','jde','kds','kde','ims','ime','jms','jme','kms','kme','its','ite','jts','jte','kts','kte')
def mem(a,n):return bytes(gdb.selected_inferior().read_memory(a,n))
def integer(a):return struct.unpack('<i',mem(a,4))[0]
def args(n):
 f=gdb.selected_frame(); r=[int(f.read_register(x)) for x in ('rdi','rsi','rdx','rcx','r8','r9')]; sp=int(f.read_register('rsp'))
 return r+list(struct.unpack('<'+str(n-6)+'Q',mem(sp+8,(n-6)*8)))
def dims(a,start):return dict(zip(NAMES,[integer(a[i-1]) for i in range(start,start+18)]))
def owns(d,c):
 i,j,k=c
 return d['its']<=i<=min(d['ite'],d['ide']-1) and d['jts']<=j<=min(d['jte'],d['jde']-1) and d['kts']<=k<=min(d['kte'],d['kde']-1)
def offset(d,c,kind):
 i,j,k=c; ni=d['ime']-d['ims']+1; nk=d['kme']-d['kms']+1
 return {'3d':4*((j-d['jms'])*nk*ni+(k-d['kms'])*ni+i-d['ims']),'2d':4*((j-d['jms'])*ni+i-d['ims']),'1d':4*(k-d['kms']),'scalar':0}[kind]
def values(a,d,c,fields):
 out={}
 for name,n,typ in fields:
  addr=a[n-1]+offset(d,c,typ); raw=mem(addr,4); out[name]={'hex_le':raw.hex(),'value':struct.unpack('<f',raw)[0],'pointer':hex(addr)}
 return out
def emit(**kw): S.write(json.dumps({'rank':R,**kw},sort_keys=True)+'\n')
finished=[]; count=0
class Return(gdb.FinishBreakpoint):
 def __init__(self,kind,a,d,c,fields,extra):
  super().__init__(gdb.newest_frame(),internal=True);self.kind=kind;self.a=a;self.d=d;self.c=c;self.fields=fields;self.extra=extra
 def stop(self):
  emit(event='return',kind=self.kind,cell=self.c,fields=values(self.a,self.d,self.c,self.fields),**self.extra);return False
class Entry(gdb.Breakpoint):
 def __init__(self,kind,addr,n,start):
  super().__init__('*'+hex(addr),internal=True);self.kind=kind;self.n=n;self.start=start
 def stop(self):
  global count
  if count:return False
  a=args(self.n);d=dims(a,self.start); cells=[c for c in CELLS if owns(d,c)]
  if not cells:return False
  if self.kind=='prep':
   fields=[('t_new',1,'3d'),('al',5,'3d'),('alb',6,'3d'),('p',7,'3d'),('pb',10,'3d'),('qv',21,'3d'),('qc',23,'3d')]
   ret=[('rho',4,'3d'),('th',13,'3d'),('pii',14,'3d'),('p_full',15,'3d')]
   extra={'bounds':d,'bases':{x:hex(a[n-1]) for x,n,_ in fields+ret}}
   for c in cells:
    emit(event='entry',kind=self.kind,cell=c,fields=values(a,d,c,fields),**extra)
    finished.append(Return(self.kind,a,d,c,ret,extra))
   return False
  if self.kind=='kdm':
   step=integer(a[52]);
   if step!=1:return False
   fields=[(x,n,'3d') for x,n in [('th',1),('qv',2),('qc',3),('qr',4),('qi',5),('qs',6),('qg',7),('ni',10),('den',14),('pii',15),('p',16)]]
   extra={'step':step,'bounds':d,'bases':{x:hex(a[n-1]) for x,n,_ in fields}}
   for c in cells:
    emit(event='entry',kind=self.kind,cell=c,fields=values(a,d,c,fields),**extra)
    finished.append(Return(self.kind,a,d,c,fields,extra))
   count=1;return False
  idx=integer(a[0]); mapping={x:integer(v) for x,v in SYMS.items()}
  if self.kind=='tend':
   moist=bool(integer(a[29])&1); matches=[x for x in mapping if mapping[x]==idx and ((x!='NI')==moist)];rk=integer(a[4])
   if not matches:return False
   fields=[('current',23,'3d'),('tendency',24,'3d'),('advect',25,'3d'),('mut',14,'2d'),('mub',15,'2d'),('mu_old',16,'2d'),('c1h',17,'1d'),('c2h',18,'1d'),('dt',6,'scalar')]; ret=[('tendency',24,'3d'),('advect',25,'3d'),('h_tendency',26,'3d'),('z_tendency',27,'3d')]
  else:
   matches=[x for x in mapping if mapping[x]==idx];rk=integer(a[17]);moist=None
   if not matches:return False
   fields=[('current',4,'3d'),('tendency',5,'3d'),('advect',8,'3d'),('msfty',12,'2d'),('c1',13,'1d'),('c2',14,'1d'),('mu_old',15,'2d'),('mu_new',16,'2d'),('mu_base',17,'2d'),('dt',19,'scalar')];ret=[('current',4,'3d'),('old',3,'3d')]
  extra={'rk_step':rk,'species_index':idx,'runtime_species':mapping,'species_candidates':matches,'moist_flag':moist,'bounds':d,'current_base':hex(a[(23 if self.kind=='tend' else 4)-1])}
  for c in cells:
   emit(event='entry',kind=self.kind,cell=c,fields=values(a,d,c,fields),**extra)
   finished.append(Return(self.kind,a,d,c,ret,extra))
  return False
gdb.execute('set pagination off');gdb.execute('set confirm off');gdb.execute('set debuginfod enabled off');gdb.execute('set disable-randomization off');gdb.execute('set startup-with-shell off');gdb.execute('set language c')
breaks=[Entry('tend',0x219dcc0,71,54),Entry('update',0x219f900,40,23),Entry('prep',0x2190470,45,28),Entry('kdm',0x25df680,77,60)]
