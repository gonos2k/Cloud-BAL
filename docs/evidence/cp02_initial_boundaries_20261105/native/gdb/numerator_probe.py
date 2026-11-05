"""Read-only bounded SIMD numerator/lane probe inside target phi call seven."""
import hashlib,importlib.util,json,os,struct
from pathlib import Path
import gdb

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_phi_probe',HERE/'phi_probe.py')
phi=importlib.util.module_from_spec(spec);spec.loader.exec_module(phi)
if phi.target!='p20183' or phi.rank!=5:raise RuntimeError('numerator probe requires p20183 rank 5')
ARM=os.environ['CP05_ARM']
EXPECTED={'B1':{'ph':'7de0a842','ph_next':'5ef20143','phb':'4c280546','phb_next':'39751446'},
          'DM065':{'ph':'7ce0a842','ph_next':'5ef20143','phb':'4c280546','phb_next':'39751446'}}
if ARM not in EXPECTED:raise RuntimeError('invalid arm')
stream=(phi.out/'numerator_rank5.jsonl').open('x',buffering=1)
seq=0;phi_calls=0;context=None;read_watch=None;prepoint=None;steps=[];active=False


def emit(event,**data):
    global seq
    seq+=1;stream.write(json.dumps({'event':event,'sequence':seq,'arm':ARM,'target':'p20183','i':phi.I,'j':phi.J,'k':phi.K,**data},sort_keys=True)+'\n')


def reg(name):return int(gdb.selected_frame().read_register(name))
def rawreg(name):return bytes(gdb.selected_frame().read_register(name).bytes).hex()
def qword(address):return struct.unpack('<Q',phi.read(address,8))[0]


def vector_operand_bases(rbx,r13):
    return [qword(rbx+0x280),qword(rbx+0x200),qword(rbx+0x2a0),r13]


class ReadWatch(gdb.Breakpoint):
    def __init__(self,address):
        super().__init__(f'*(unsigned int*)0x{address:x}',type=gdb.BP_WATCHPOINT,wp_class=gdb.WP_READ,internal=True)
        self.read_address=address
    def stop(self):
        global prepoint
        pc=reg('pc');emit('read_watch_after',reported_pc=hex(pc),watched_address=hex(self.read_address),
                          semantics='hardware read-watch stop; PC is after the access')
        self.enabled=False
        prepoint.enabled=True
        return False


class Prepoint(gdb.Breakpoint):
    def __init__(self):
        super().__init__('*0x2156f80',internal=True);self.enabled=False;self.skipped=0
    def stop(self):
        global active
        if context is None:raise RuntimeError('missing phi7 context')
        vector_base=reg('r12')+4*reg('r15');delta=context['al_address']-vector_base
        if not 0<=delta<16 or delta%4:
            self.skipped+=1
            if self.skipped>500:raise RuntimeError('target vector not reached within bound')
            return False
        lane=delta//4;rbx=reg('rbx');r15=reg('r15');r13=reg('r13')
        bases=vector_operand_bases(rbx,r13)
        addresses=[base+4*r15+4*lane for base in bases]
        if set(addresses)!=set(context['operand_addresses'].values()):
            raise RuntimeError('candidate vector operands do not map exact PH/PHB addresses')
        mapped={name:addresses.index(address) for name,address in context['operand_addresses'].items()}
        emit('vector_prepoint',pc='0x2156f80',skipped_vectors=self.skipped,al_vector_address=hex(vector_base),al_target_address=hex(context['al_address']),
             lane=lane,operand_slot_mapping=mapped,operand_addresses={k:hex(v) for k,v in context['operand_addresses'].items()},
             operand_words=context['operand_words'],alb_word=context['alb_word'],registers={n:hex(reg(n)) for n in ('rax','rbx','r12','r13','r15')})
        context['lane']=lane;active=True;self.enabled=False;steps[0].enabled=True
        return False


class Step(gdb.Breakpoint):
    def __init__(self,index,address,opcode):
        super().__init__(f'*0x{address:x}',internal=True);self.enabled=False
        self.step_index=index;self.address_pc=address;self.expected_opcode=bytes.fromhex(opcode)
    def stop(self):
        global active
        if not active or context is None or reg('pc')!=self.address_pc:raise RuntimeError('unexpected numerator stop')
        if phi.read(self.address_pc,len(self.expected_opcode))!=self.expected_opcode:raise RuntimeError('instruction bytes differ')
        event={'pc':hex(self.address_pc),'opcode':self.expected_opcode.hex(),'lane':context['lane'],
               'xmm0':rawreg('xmm0'),'xmm2':rawreg('xmm2'),'xmm3':rawreg('xmm3'),'xmm1':rawreg('xmm1'),
               'r12':hex(reg('r12')),'r15':hex(reg('r15'))}
        if self.address_pc in (0x2157072,0x2157077):
            vector=reg('r12')+4*reg('r15')
            if vector+4*context['lane']!=context['al_address']:raise RuntimeError('AL target store address differs')
            event['al_vector_address']=hex(vector);event['al_target_address']=hex(context['al_address'])
            if self.address_pc==0x2157077:event['stored_al_word']=phi.word(context['al_address'])
        emit('instruction_stop',**event)
        self.enabled=False
        if self.step_index+1<len(steps):steps[self.step_index+1].enabled=True
        else:active=False
        return False


class PhiReturn(gdb.FinishBreakpoint):
    def __init__(self):super().__init__(gdb.newest_frame(),internal=True)
    def stop(self):
        if read_watch is not None and read_watch.enabled:read_watch.enabled=False
        if prepoint.enabled:prepoint.enabled=False
        if active or any(b.enabled for b in steps):raise RuntimeError('numerator instruction sequence incomplete')
        emit('phi7_return',captured=bool(context and 'lane' in context))
        return False


class PhiEntry(gdb.Breakpoint):
    def __init__(self):super().__init__('*0x21557c0',internal=True)
    def stop(self):
        global phi_calls,context,read_watch
        a=phi.pointers(46);d=phi.bounds(a,29)
        if not phi.owns(d):return False
        phi_calls+=1
        if phi_calls!=7:return False
        pc=phi.caller_pc()
        if pc!=0x13eb579 or phi.kdm_completed!=1 or phi.integer(a[2])!=2 or phi.integer(a[27])!=1 or (phi.integer(a[26])&1)!=1:
            raise RuntimeError('phi7 caller/branch/timing differs')
        addresses={'ph':phi.arg(a,14,phi.o3(d)),'ph_next':phi.arg(a,14,phi.o3(d,k=phi.K+1)),
                   'phb':phi.arg(a,15,phi.o3(d)),'phb_next':phi.arg(a,15,phi.o3(d,k=phi.K+1))}
        words={name:phi.word(addr) for name,addr in addresses.items()}
        if words!=EXPECTED[ARM]:raise RuntimeError('phi7 input words differ from frozen baseline')
        if phi.K-1<d['kms']:raise RuntimeError('earlier interface outside allocation')
        neighbor_address=phi.arg(a,14,phi.o3(d,k=phi.K-1))
        context={'operand_addresses':addresses,'operand_words':words,'al_address':phi.arg(a,4,phi.o3(d)),
                 'al_base':a[3],'ph_base':a[13],'phb_base':a[14],'neighbor_address':neighbor_address,
                 'alb_word':phi.word(phi.arg(a,5,phi.o3(d)))}
        emit('phi7_entry',caller_pc=hex(pc),kdm_completed=phi.kdm_completed,
             hypsometric_opt=phi.integer(a[2]),use_theta_m=phi.integer(a[27]),
             non_hydrostatic=phi.integer(a[26]),non_hydrostatic_raw_word=phi.word(a[26]),bounds=d,operand_words=words,
             al_address=hex(context['al_address']),al_base=hex(context['al_base']),
             ph_base=hex(context['ph_base']),phb_base=hex(context['phb_base']),
             neighbor_watch_address=hex(neighbor_address))
        read_watch=ReadWatch(neighbor_address);phi.pending.append(PhiReturn())
        self.enabled=False
        return False


prepoint=Prepoint()
steps=[Step(i,int(pc,16),opcode) for i,(pc,opcode) in enumerate([
 ('0x2156fe7','0f5cd3'),('0x2156fea','488b83a0020000'),('0x2156ff6','0f58da'),
 ('0x2156ff9','430f1054bd00'),('0x2156fff','0f5cda'),('0x2157002','0f5ed8'),
 ('0x2157005','0f295b30'),('0x2157067','0f5ec8'),('0x215706a','430f1004be'),
 ('0x215706f','0f5cc8'),('0x2157072','430f110cbc'),('0x2157077','4983c704')])]
phi7=PhiEntry()
