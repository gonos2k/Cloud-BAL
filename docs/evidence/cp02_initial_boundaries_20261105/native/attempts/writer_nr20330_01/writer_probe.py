"""Read-only GDB function boundary and hardware-store discovery for original WRF."""
import hashlib
import json
import os
import struct
from pathlib import Path
import gdb

EXE_SHA='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
P_QNR_SYMBOL=0x3eea2b8
FUNCTIONS={'rk':(0x219f900,40),'pressure':(0x213b1b0,43),
           'prep':(0x2190470,45),'kdm':(0x25df680,77)}
TARGETS={'nr20330':(5,141,142,2),'nr20330max':(5,141,143,11),'p20183':(5,144,142,4),'p17051':(3,140,120,38)}
case=os.environ['CP05_TARGET'];rank=int(os.environ['PMI_RANK'])
if case not in TARGETS or rank!=TARGETS[case][0]:raise RuntimeError('wrong target or rank')
_,I,J,K=TARGETS[case]
output=Path(os.environ['CP05_OUTPUT'])
with Path(gdb.current_progspace().filename).open('rb') as f:
    if hashlib.file_digest(f,'sha256').hexdigest()!=EXE_SHA:raise RuntimeError('wrong executable')
if not output.is_dir():raise RuntimeError('missing output directory')
path=output/f'writer_rank{rank}.jsonl'
stream=path.open('x',buffering=1)
sequence=0
kdm_count=0
rk_qnr_pointers=set()
calc_pointers=set()
prep_pointer_tuples=[]
pm1_initialized=set()
rk_old_initialized=set()
return_breakpoints=[]


def emit(kind,**values):
    global sequence
    sequence+=1
    stream.write(json.dumps({'event':kind,'sequence':sequence,'rank':rank,'target':case,
                             'i':I,'j':J,'k':K,**values},sort_keys=True)+'\n')


def pointers(n):
    frame=gdb.selected_frame()
    regs=[int(frame.read_register(r)) for r in ('rdi','rsi','rdx','rcx','r8','r9')]
    stack=int(frame.read_register('rsp'))
    return regs+list(struct.unpack('<'+str(n-6)+'Q',bytes(gdb.selected_inferior().read_memory(stack+8,(n-6)*8))))


def bytes_at(address,size):
    if not address:raise RuntimeError('null pointer')
    return bytes(gdb.selected_inferior().read_memory(address,size))


def integer(pointer):return struct.unpack('<i',bytes_at(pointer,4))[0]


def word(pointer):return bytes_at(pointer,4).hex()


def bounds(args,start):
    names=('ids','ide','jds','jde','kds','kde','ims','ime','jms','jme','kms','kme','its','ite','jts','jte','kts','kte')
    d=dict(zip(names,[integer(args[i-1]) for i in range(start,start+18)]))
    if not (d['ims']<=d['its']<=d['ite']<=d['ime'] and d['jms']<=d['jts']<=d['jte']<=d['jme'] and d['kms']<=d['kts']<=d['kte']<=d['kme']):
        raise RuntimeError('invalid bounds')
    return d


def owns(d):return (d['its']<=I<=min(d['ite'],d['ide']-1) and d['jts']<=J<=min(d['jte'],d['jde']-1) and d['kts']<=K<=min(d['kte'],d['kde']-1))


def offset3(d,k=K):
    ni=d['ime']-d['ims']+1;nk=d['kme']-d['kms']+1
    return 4*((J-d['jms'])*nk*ni+(k-d['kms'])*ni+(I-d['ims']))


def offset2(d):return 4*((J-d['jms'])*(d['ime']-d['ims']+1)+(I-d['ims']))


def offset1(d):return 4*(K-d['kms'])


def address(args,n,offset=0):return args[n-1]+offset


def snap(args,d,fields):
    offsets={'scalar':0,'3d':offset3(d),'3d_kplus':offset3(d,K+1),'2d':offset2(d),'1d':offset1(d)}
    return {name:word(address(args,n,offsets[shape])) for name,n,shape in fields}


def frame_registers():
    return gdb.execute('info all-registers',to_string=True)


class Watch(gdb.Breakpoint):
    def __init__(self,address,owner,metadata,initial_defined=True):
        super().__init__(f'*(unsigned int*)0x{address:x}',type=gdb.BP_WATCHPOINT,wp_class=gdb.WP_WRITE,internal=True)
        self.watched_address=address;self.owner_name=owner;self.event_metadata=metadata;self.initial_defined=initial_defined
        self.last=word(address) if initial_defined else None
        self.count=0

    def stop(self):
        self.count+=1
        frame=gdb.selected_frame();pc=int(frame.read_register('pc'))
        current=word(self.watched_address)
        emit('watch_after',owner=self.owner_name,watch_address=hex(self.watched_address),
             pre_word=self.last,post_word=current,reported_pc=hex(pc),
             pc_symbol=gdb.execute(f'info symbol 0x{pc:x}',to_string=True).strip(),
             instruction_bytes_around_pc=gdb.execute(f'x/48bx 0x{max(0,pc-32):x}',to_string=True),
             registers=frame_registers(),pc_semantics='stopped after write; pre_word absent means opaque pre-call output',**self.event_metadata)
        self.last=current
        return False


class OnReturn(gdb.FinishBreakpoint):
    def __init__(self,kind,args,d,fields,watch=None,metadata=None):
        super().__init__(gdb.newest_frame(),internal=True)
        self.kind=kind;self.args=args;self.d=d;self.fields=fields;self.watch=watch;self.metadata=metadata or {}

    def stop(self):
        if self.watch is not None:
            count=self.watch.count;self.watch.delete()
        else:count=None
        if self.kind=='pressure' and self.metadata['acoustic_iteration']==0:
            pm1_initialized.add(address(self.args,8,offset3(self.d)))
        if self.kind=='rk' and self.metadata['rk_step']==1:
            rk_old_initialized.add(address(self.args,3,offset3(self.d)))
        emit('function_return',function=self.kind,fields=snap(self.args,self.d,self.fields),watch_events=count,**self.metadata)
        return False


class OnEntry(gdb.Breakpoint):
    def __init__(self,kind):
        super().__init__(f'*0x{FUNCTIONS[kind][0]:x}',internal=True)
        self.kind=kind

    def stop(self):
        global kdm_count
        kind=self.kind;args=pointers(FUNCTIONS[kind][1])
        if kind=='rk':
            if not case.startswith('nr20330') or integer(args[0]) != integer(P_QNR_SYMBOL):return False
            d=bounds(args,23)
            if not owns(d):return False
            if integer(args[1]) != integer(args[0]):raise RuntimeError('QNR scalar slice bounds differ')
            rk=integer(args[17]);ptr=address(args,4);rk_qnr_pointers.add(ptr)
            if rk <= 0:raise RuntimeError('invalid RK stage')
            fields=[('scalar_current',4,'3d'),('scalar_tendency',5,'3d'),('advection_tendency',8,'3d'),('msfty',12,'2d'),('c1',13,'1d'),('c2',14,'1d'),('mu_old',15,'2d'),('mu_new',16,'2d'),('mu_base',17,'2d'),('dt',19,'scalar')]
            old_target=address(args,3,offset3(d))
            if rk>1:
                if old_target not in rk_old_initialized:raise RuntimeError('scalar_old not initialized by witnessed RK1')
                fields.append(('scalar_old',3,'3d'))
            target=ptr+offset3(d);metadata={'candidate_timestep':kdm_count+1,'rk_step':rk,'spec_zone':integer(args[19]),'qnr_species_index':integer(args[0]),'scs':integer(args[0]),'sce':integer(args[1]),'runtime_p_qnr':integer(P_QNR_SYMBOL),'qnr_base_pointer':hex(ptr),'target_pointer':hex(target),'bounds':d}
            emit('function_entry',function=kind,fields=snap(args,d,fields),**metadata)
            watch=Watch(target,'rk_update_scalar',metadata,True)
            return_breakpoints.append(OnReturn(kind,args,d,[('scalar_old',3,'3d'),('scalar_current',4,'3d')],watch,metadata))
        elif kind=='pressure':
            if case.startswith('nr20330'):return False
            d=bounds(args,26)
            if not owns(d):return False
            iteration=integer(args[24]);ptr=address(args,2);calc_pointers.add(ptr)
            if iteration < 0:raise RuntimeError('invalid acoustic iteration')
            if integer(args[23]) != 1 or K+1 > d['kme']:
                raise RuntimeError('pressure producer requires nonhydrostatic branch and valid k+1')
            fields=[('ph_k',3,'3d'),('ph_kplus1',3,'3d_kplus'),('alt',4,'3d'),('t2',5,'3d'),('t_save',6,'3d'),('c2a',7,'3d'),('mu',9,'2d'),('mut',10,'2d'),('c1h',11,'1d'),('c2h',12,'1d'),('t0',20,'scalar'),('rdnw',21,'1d'),('smdiv',23,'scalar')]
            if iteration>0:
                if address(args,8,offset3(d)) not in pm1_initialized:raise RuntimeError('pm1 not initialized by witnessed step zero')
                fields.append(('pm1',8,'3d'))
            target=ptr+offset3(d);metadata={'candidate_timestep':kdm_count+1,'acoustic_iteration':iteration,'non_hydrostatic':integer(args[23]),'p_base_pointer':hex(ptr),'target_pointer':hex(target),'bounds':d}
            emit('function_entry',function=kind,fields=snap(args,d,fields),**metadata)
            watch=Watch(target,'calc_p_rho',metadata,False)
            return_breakpoints.append(OnReturn(kind,args,d,[('al',1,'3d'),('p',2,'3d'),('pm1',8,'3d')],watch,metadata))
        elif kind=='prep':
            if case.startswith('nr20330'):return False
            d=bounds(args,28)
            if not owns(d):return False
            inputs=[('t_new',1,'3d'),('t0',3,'scalar'),('al',5,'3d'),('alb',6,'3d'),('p',7,'3d'),('p0',9,'scalar'),('pb',10,'3d'),('qv',21,'3d'),('qc',23,'3d')]
            pt=(address(args,7),address(args,13),address(args,14),address(args,15));prep_pointer_tuples.append(pt)
            metadata={'candidate_timestep':kdm_count+1,'p_in_pointer':hex(pt[0]),'th_out_pointer':hex(pt[1]),'pii_out_pointer':hex(pt[2]),'pf_out_pointer':hex(pt[3]),'bounds':d}
            emit('function_entry',function=kind,fields=snap(args,d,inputs),**metadata)
            return_breakpoints.append(OnReturn(kind,args,d,[('rho',4,'3d'),('th',13,'3d'),('pii',14,'3d'),('pf',15,'3d')],metadata=metadata))
        else:
            step=integer(args[52]);d=bounds(args,60)
            if not owns(d):return False
            kdm_count+=1
            if step!=kdm_count or step>4:raise RuntimeError('unexpected target KDM call sequence')
            fields=[(name,n,'3d') for name,n in [('th',1),('qv',2),('qc',3),('qr',4),('qi',5),('qs',6),('qg',7),('nn',8),('nc',9),('ni',10),('nr',11),('bg',12),('den',14),('pii',15),('p',16)]]
            metadata={'timestep':step,'bounds':d,'nr_base_pointer':hex(address(args,11)),'th_base_pointer':hex(address(args,1)),'pii_base_pointer':hex(address(args,15)),'p_base_pointer':hex(address(args,16)),
                      'nr_matches_rk':address(args,11) in rk_qnr_pointers if case.startswith('nr20330') else None,
                      'prep_binding_matches':any(pt[0] in calc_pointers and pt[1:]==(address(args,1),address(args,15),address(args,16)) for pt in prep_pointer_tuples) if not case.startswith('nr20330') else None}
            if case.startswith('nr20330') and not metadata['nr_matches_rk']:raise RuntimeError('QNR pointer does not bind KDM')
            if not case.startswith('nr20330') and not metadata['prep_binding_matches']:raise RuntimeError('pressure/prep pointers do not bind KDM')
            emit('function_entry',function=kind,fields=snap(args,d,fields),**metadata)
            return_breakpoints.append(OnReturn(kind,args,d,fields,metadata=metadata))
            rk_qnr_pointers.clear();calc_pointers.clear();prep_pointer_tuples.clear();pm1_initialized.clear();rk_old_initialized.clear()
            if kdm_count==4:
                for bp in breaks:bp.enabled=False
        return False


gdb.execute('set pagination off');gdb.execute('set confirm off')
gdb.execute('set debuginfod enabled off');gdb.execute('set disable-randomization off')
gdb.execute('set startup-with-shell off')
breaks=[OnEntry(kind) for kind in FUNCTIONS]
