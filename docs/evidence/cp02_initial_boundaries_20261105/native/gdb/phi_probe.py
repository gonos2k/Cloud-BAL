"""Observe the original executable's pressure reconstruction and P write interval."""
import hashlib,json,os,struct
from pathlib import Path
import gdb

EXE_SHA='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
P_QV=0x3eea3a0
PARAM_FIRST_SCALAR=2
TARGETS={'p20183':(5,144,142,4),'p17051':(3,140,120,38)}
SYMBOLS={'calc':(0x213b1b0,43),'phi':(0x21557c0,46),'vspow':(0x22eaf30,4),
         'prep':(0x2190470,45),'kdm':(0x25df680,77)}
CALLSITES={0x13eb579:'solve_em_RK',0x13ffdd4:'solve_em_postphysics'}
target=os.environ['CP05_TARGET'];rank=int(os.environ['PMI_RANK'])
if target not in TARGETS or rank!=TARGETS[target][0]:raise RuntimeError('wrong target owner')
_,I,J,K=TARGETS[target]
with Path(gdb.current_progspace().filename).open('rb') as f:
    if hashlib.file_digest(f,'sha256').hexdigest()!=EXE_SHA:raise RuntimeError('wrong executable')
out=Path(os.environ['CP05_OUTPUT'])
if not out.is_dir():raise RuntimeError('missing output directory')
stream=(out/f'phi_rank{rank}.jsonl').open('x',buffering=1)
seq=0;kdm_entered=0;kdm_completed=0;active_phi=None;gap=None;last_phi=None
pending=[]


def emit(event,**values):
    global seq
    seq+=1
    stream.write(json.dumps({'event':event,'sequence':seq,'rank':rank,'target':target,
      'i':I,'j':J,'k':K,'kdm_entered':kdm_entered,'kdm_completed':kdm_completed,**values},sort_keys=True)+'\n')


def read(address,size):
    if not address:raise RuntimeError('null pointer')
    return bytes(gdb.selected_inferior().read_memory(address,size))


def pointers(n):
    frame=gdb.selected_frame(); regs=[int(frame.read_register(r)) for r in ('rdi','rsi','rdx','rcx','r8','r9')]
    if n<=6:return regs[:n]
    stack=int(frame.read_register('rsp'))
    return regs+list(struct.unpack('<'+str(n-6)+'Q',read(stack+8,(n-6)*8)))


def integer(address):return struct.unpack('<i',read(address,4))[0]
def word(address):return read(address,4).hex()
def arg(a,n,off=0):return a[n-1]+off


def bounds(a,start):
    names=('ids','ide','jds','jde','kds','kde','ims','ime','jms','jme','kms','kme','its','ite','jts','jte','kts','kte')
    d=dict(zip(names,[integer(a[i-1]) for i in range(start,start+18)]))
    if not (d['ims']<=d['its']<=d['ite']<=d['ime'] and d['jms']<=d['jts']<=d['jte']<=d['jme'] and d['kms']<=d['kts']<=d['kte']<=d['kme']):raise RuntimeError('invalid bounds')
    return d


def owns(d):return d['its']<=I<=min(d['ite'],d['ide']-1) and d['jts']<=J<=min(d['jte'],d['jde']-1) and d['kts']<=K<=min(d['kte'],d['kde']-1)
def o3(d,i=I,k=K,j=J):return 4*((j-d['jms'])*(d['kme']-d['kms']+1)*(d['ime']-d['ims']+1)+(k-d['kms'])*(d['ime']-d['ims']+1)+(i-d['ims']))
def o2(d):return 4*((J-d['jms'])*(d['ime']-d['ims']+1)+(I-d['ims']))
def o1(d,k=K):return 4*(k-d['kms'])


def snapshot(a,d,fields):
    offsets={'scalar':0,'3d':o3(d),'3d_next':o3(d,k=K+1),'2d':o2(d),'1d':o1(d),'1d_next':o1(d,K+1)}
    return {name:word(arg(a,n,offsets[shape])) for name,n,shape in fields}


def caller_pc():return struct.unpack('<Q',read(int(gdb.selected_frame().read_register('rsp')),8))[0]


class GapWatch(gdb.Breakpoint):
    def __init__(self,address):
        super().__init__(f'*(unsigned int*)0x{address:x}',type=gdb.BP_WATCHPOINT,wp_class=gdb.WP_WRITE,internal=True)
        self.address_watched=address;self.initial=word(address);self.last=self.initial;self.hits=0
    def stop(self):
        self.hits+=1;pc=int(gdb.selected_frame().read_register('pc'));now=word(self.address_watched)
        emit('gap_watch_after',target_address=hex(self.address_watched),pre_word=self.last,post_word=now,
             reported_pc=hex(pc),pc_symbol=gdb.execute(f'info symbol 0x{pc:x}',to_string=True).strip(),
             instruction_bytes=gdb.execute(f'x/48bx 0x{max(pc-32,0):x}',to_string=True),
             registers=gdb.execute('info all-registers',to_string=True),
             pc_semantics='post-store watch stop; exact writer needs preinstruction replay')
        self.last=now
        return False


class Return(gdb.FinishBreakpoint):
    def __init__(self,kind,args,d,fields,meta=None):
        super().__init__(gdb.newest_frame(),internal=True)
        self.kind=kind;self.args=args;self.d=d;self.fields=fields;self.meta=meta or {}
    def stop(self):
        global active_phi,last_phi,gap,kdm_completed
        values=snapshot(self.args,self.d,self.fields)
        if self.kind=='calc_last':
            if gap is not None:raise RuntimeError('previous pressure gap not closed')
            last_phi=None
            address=arg(self.args,2,o3(self.d));gap=GapWatch(address)
            emit('gap_start',target_address=hex(address),p_word=values['p'],**self.meta)
            if gap.initial!=values['p']:raise RuntimeError('watch initial mismatch')
        elif self.kind=='phi':
            if active_phi is None:raise RuntimeError('phi context missing')
            last_phi={'p_base':arg(self.args,16),'p_word':values['p'],'caller_pc':self.meta['caller_pc']}
            active_phi=None;vspow_break.enabled=False
        elif self.kind=='kdm':
            kdm_completed+=1
            if kdm_completed!=self.meta['timestep']:raise RuntimeError('unexpected completed call')
        emit('function_return',function=self.kind,fields=values,**self.meta)
        return False


class VspowReturn(gdb.FinishBreakpoint):
    def __init__(self,args,off,meta):
        super().__init__(gdb.newest_frame(),internal=True);self.args=args;self.off=off;self.meta=meta
    def stop(self):
        emit('vspow_return',output_word=word(arg(self.args,1,self.off)),**self.meta)
        return False


class Entry(gdb.Breakpoint):
    def __init__(self,kind):super().__init__(f'*0x{SYMBOLS[kind][0]:x}',internal=True);self.kind=kind
    def stop(self):
        global kdm_entered,active_phi,gap,last_phi
        kind=self.kind;a=pointers(SYMBOLS[kind][1]);pc=caller_pc()
        if kind=='vspow':
            if active_phi is None:raise RuntimeError('vspow enabled without phi context')
            d=active_phi['bounds'];expected=active_phi['p_base']+o3(d,i=d['its'])
            if a[0]!=expected:return False
            index=I-d['its'];n=integer(a[3])
            if not 0<=index<n:raise RuntimeError('target outside vspow row')
            off=index*4
            if a[0]+off != active_phi['p_base']+o3(d):raise RuntimeError('vspow target address differs')
            meta={'caller_pc':hex(pc),'row_pointer':hex(a[0]),'lane_index':index,'row_length':n,'output_address':hex(a[0]+off)}
            emit('vspow_entry',input_word=word(arg(a,2,off)),exponent_word=word(arg(a,3,off)),**meta)
            pending.append(VspowReturn(a,off,meta));return False
        start={'calc':26,'phi':29,'prep':28,'kdm':60}[kind];d=bounds(a,start)
        if not owns(d):return False
        if kind=='calc':
            iteration=integer(a[24])
            if iteration!=4:return False
            meta={'acoustic_iteration':iteration,'caller_pc':hex(pc),'p_base':hex(a[1]),'bounds':d}
            emit('function_entry',function='calc_last',fields={},**meta)
            pending.append(Return('calc_last',a,d,[('p',2,'3d'),('al',1,'3d')],meta))
        elif kind=='phi':
            if active_phi is not None or K+1>d['kme']:raise RuntimeError('invalid nested phi or k+1')
            raw=integer(a[26]);hypso=integer(a[2]);nmoist=integer(a[1]);qv_index=integer(P_QV);theta=integer(a[27])
            emit('phi_guard',caller_pc=hex(pc),caller_class=CALLSITES.get(pc,'other_unclassified'),
                 non_hydrostatic=raw,non_hydrostatic_raw_word=word(a[26]),non_hydrostatic_branch_bit=raw&1,
                 hypsometric_opt=hypso,n_moist=nmoist,runtime_p_qv=qv_index,param_first_scalar=PARAM_FIRST_SCALAR,use_theta_m=theta,
                 k_plus_one=K+1,kme=d['kme'])
            if not raw & 1 or hypso not in (1,2) or nmoist<PARAM_FIRST_SCALAR or not 1<=qv_index<=nmoist:raise RuntimeError('unsupported phi branch or moisture index')
            offset=(qv_index-1)*(d['ime']-d['ims']+1)*(d['kme']-d['kms']+1)*(d['jme']-d['jms']+1)*4
            qv_base=a[0]+offset
            fields=[('alb',5,'3d'),('mu',6,'2d'),('muts',7,'2d'),('c1',8,'1d'),('c2',9,'1d'),('c3h',10,'1d'),('c4h',11,'1d'),('c3f',12,'1d'),('c3f_next',12,'1d_next'),('c4f',13,'1d'),('c4f_next',13,'1d_next'),('ph',14,'3d'),('ph_next',14,'3d_next'),('phb',15,'3d'),('phb_next',15,'3d_next'),('pb',17,'3d'),('t',18,'3d'),('p0',19,'scalar'),('t0',20,'scalar'),('ptop',21,'scalar'),('znu',22,'1d'),('znw',23,'1d'),('dnw',24,'1d'),('rdnw',25,'1d'),('rdn',26,'1d')]
            values=snapshot(a,d,fields);values['qv']=word(qv_base+o3(d))
            meta={'caller_pc':hex(pc),'caller_class':CALLSITES.get(pc,'other_unclassified'),'p_base':hex(a[15]),'al_base':hex(a[3]),'moist_base':hex(a[0]),'qv_base':hex(qv_base),'n_moist':nmoist,'runtime_p_qv':qv_index,'param_first_scalar':PARAM_FIRST_SCALAR,'hypsometric_opt':hypso,'use_theta_m':theta,'non_hydrostatic':raw,'non_hydrostatic_raw_word':word(a[26]),'non_hydrostatic_branch_bit':raw&1,'bounds':d}
            if gap is not None and gap.address_watched!=a[15]+o3(d):raise RuntimeError('gap/phi pointer differs')
            active_phi={'bounds':d,'p_base':a[15]};vspow_break.enabled=True
            emit('function_entry',function=kind,fields=values,**meta)
            pending.append(Return(kind,a,d,[('al',4,'3d'),('p',16,'3d'),('ph',14,'3d'),('ph_next',14,'3d_next')],meta))
        elif kind=='prep':
            if gap is None:raise RuntimeError('prep reached without last-calc gap watch')
            if gap.address_watched!=a[6]+o3(d):raise RuntimeError('gap/prep P pointer differs')
            p=word(gap.address_watched)
            if p!=gap.last:raise RuntimeError('gap watch continuity differs')
            emit('gap_end',target_address=hex(gap.address_watched),initial_word=gap.initial,final_word=p,watch_events=gap.hits,
                 last_phi_p_word=last_phi['p_word'] if last_phi and last_phi['p_base']==a[6] else None,
                 last_phi_matches_prep=bool(last_phi and last_phi['p_base']==a[6] and last_phi['p_word']==p))
            gap.delete();gap=None
            fields=[('t_new',1,'3d'),('t0',3,'scalar'),('al',5,'3d'),('alb',6,'3d'),('p',7,'3d'),('p0',9,'scalar'),('pb',10,'3d'),('qv',21,'3d'),('qc',23,'3d')]
            meta={'caller_pc':hex(pc),'p_in_base':hex(a[6]),'th_out_base':hex(a[12]),'pii_out_base':hex(a[13]),'pf_out_base':hex(a[14]),'qv_base':hex(a[20]),'bounds':d}
            emit('function_entry',function=kind,fields=snapshot(a,d,fields),**meta)
            pending.append(Return(kind,a,d,[('rho',4,'3d'),('th',13,'3d'),('pii',14,'3d'),('pf',15,'3d')],meta))
        else:
            step=integer(a[52]);kdm_entered+=1
            if step!=kdm_entered or step>4 or kdm_completed!=step-1:raise RuntimeError('KDM call order differs')
            fields=[(name,n,'3d') for name,n in [('th',1),('qv',2),('qc',3),('qr',4),('qi',5),('qs',6),('qg',7),('nn',8),('nc',9),('ni',10),('nr',11),('bg',12),('den',14),('pii',15),('p',16)]]
            meta={'timestep':step,'caller_pc':hex(pc),'th_base':hex(a[0]),'qv_base':hex(a[1]),'pii_base':hex(a[14]),'p_base':hex(a[15]),'bounds':d}
            emit('function_entry',function=kind,fields=snapshot(a,d,fields),**meta)
            pending.append(Return(kind,a,d,fields,meta))
            if step==4:
                for bp in breaks:bp.enabled=False
        return False


gdb.execute('set pagination off');gdb.execute('set confirm off');gdb.execute('set debuginfod enabled off')
gdb.execute('set disable-randomization off');gdb.execute('set startup-with-shell off');gdb.execute('set language c')
breaks=[Entry(kind) for kind in ('calc','phi','prep','kdm')]
vspow_break=Entry('vspow');vspow_break.enabled=False
