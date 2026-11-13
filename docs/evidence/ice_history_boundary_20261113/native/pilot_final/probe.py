"""GDB read-only capture; exact executable and runtime pointer checks required."""
import gdb,hashlib,json,os,struct
from pathlib import Path
expected='3a286f6691fa94c2dccf55b14e4cbf609b8c9540c2caf83556969932ca9854ea'
with open(gdb.current_progspace().filename,'rb') as f:
 if hashlib.file_digest(f,'sha256').hexdigest()!=expected:raise RuntimeError('wrong executable')
out=Path('../rank3_capture.jsonl').open('x',buffering=1)
cells=[(138,72,17),(205,102,17),(193,97,18),(153,115,22),(167,73,31),(205,79,20),(172,124,21),(190,103,23),(173,79,29)]
names=('ids','ide','jds','jde','kds','kde','ims','ime','jms','jme','kms','kme','its','ite','jts','jte','kts','kte')
active={};keepers=[]; target_step=int(os.environ['TARGET_STEP'])
def mem(a,n):return bytes(gdb.selected_inferior().read_memory(a,n))
def integer(a):return struct.unpack('<i',mem(a,4))[0]
def args(n):
 f=gdb.selected_frame();r=[int(f.read_register(x)) for x in ('rdi','rsi','rdx','rcx','r8','r9')];sp=int(f.read_register('rsp'));return r+list(struct.unpack('<'+str(n-6)+'Q',mem(sp+8,(n-6)*8)))
def bounds(a,start):return dict(zip(names,[integer(a[i-1]) for i in range(start,start+18)]))
def offset(d,c):
 i,j,k=c;nx=d['ime']-d['ims']+1;nz=d['kme']-d['kms']+1
 return 4*((j-d['jms'])*nz*nx+(k-d['kms'])*nx+i-d['ims'])
def snapshot(qi,ni,d):
 rows=[]
 for c in cells:
  i,j,k=c
  if not (d['its']<=i<=min(d['ite'],d['ide']-1) and d['jts']<=j<=min(d['jte'],d['jde']-1) and d['kts']<=k<=min(d['kte'],d['kde']-1)):continue
  a=mem(qi+offset(d,c),4);b=mem(ni+offset(d,c),4)
  rows.append({'cell':c,'qi':struct.unpack('<f',a)[0],'ni':struct.unpack('<f',b)[0],'qi_le':a.hex(),'ni_le':b.hex()})
 return rows
def emit(event,**v):out.write(json.dumps({'event':event,**v},sort_keys=True)+'\n')
class Finish(gdb.FinishBreakpoint):
 def __init__(self,event,qi,ni,d):
  super().__init__(gdb.newest_frame(),internal=True);self.event=event;self.qi=qi;self.ni=ni;self.d=d
 def stop(self):
  emit(self.event,qi_base=hex(self.qi),ni_base=hex(self.ni),bounds=self.d,rows=snapshot(self.qi,self.ni,self.d));return False
class Kdm(gdb.Breakpoint):
 def stop(self):
  a=args(77);step=integer(a[52])
  if active and step!=target_step:
   emit('target_scope_closed',next_step=step);active.clear()
  if step!=target_step:return False
  d=bounds(a,60);qi=a[4];ni=a[9];rows=snapshot(qi,ni,d)
  if not rows:return False
  if active:raise RuntimeError('multiple matching final KDM calls')
  active.update(qi=qi,ni=ni,bounds=d,step=step)
  emit('kdm_entry',step=step,qi_base=hex(qi),ni_base=hex(ni),bounds=d,rows=rows)
  keepers.append(Finish('kdm_return',qi,ni,d));return False
class Zero(gdb.Breakpoint):
 def __init__(self,kind,symbol):super().__init__(symbol,internal=True);self.kind=kind
 def stop(self):
  if not active:return False
  a=args(21);d=bounds(a,4);caller=struct.unpack('<Q',mem(int(gdb.selected_frame().read_register('rsp')),8))[0];rawcfg=mem(a[2]+0xe64,12);qi_idx=integer(int(gdb.parse_and_eval('&module_state_description_mp_p_qi_')));ni_idx=integer(int(gdb.parse_and_eval('&module_state_description_mp_p_qni_')))
  volume=(d['ime']-d['ims']+1)*(d['kme']-d['kms']+1)*(d['jme']-d['jms']+1)
  qi=a[0]+4*(qi_idx-1)*volume
  if qi!=active['qi'] or any(d[x]!=active['bounds'][x] for x in ('ims','ime','jms','jme','kms','kme')):
   emit('nonmatching_zero_call',kind=self.kind,caller_return=hex(caller),computed_qi=hex(qi),kdm_qi=hex(active['qi']),bounds=d,qi_index=qi_idx,ni_index=ni_idx);return False
  emit(self.kind+'_entry',step=active['step'],qi_index=qi_idx,ni_index=ni_idx,caller_return=hex(caller),config_raw_le=rawcfg.hex(),mode=integer(a[2]+0xe64),all_raw=integer(a[2]+0xe68),threshold=struct.unpack('<f',mem(a[2]+0xe6c,4))[0],qi_base=hex(qi),ni_base=hex(active['ni']),bounds=d,rows=snapshot(qi,active['ni'],d))
  keepers.append(Finish(self.kind+'_return',qi,active['ni'],d));return False
gdb.execute('set pagination off');gdb.execute('set confirm off');gdb.execute('set debuginfod enabled off');gdb.execute('set disable-randomization off');gdb.execute('set startup-with-shell off');gdb.execute('set language c')
keepers.extend([Kdm('*0x2283ac0',internal=True),Zero('zero_b','*0x20ca2d0'),Zero('zero_a','*0x20c9550')])
