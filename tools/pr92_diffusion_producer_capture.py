"""Add diagnostic-only producer records at the retained C14 failure support."""
from __future__ import annotations

import hashlib
from pathlib import Path


C14_SHA256 = "6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1"
TARGETS = ((127, 5, 22), (170, 42, 23), (171, 43, 23), (163, 44, 20),
           (158, 47, 20), (232, 203, 20), (203, 213, 21), (11, 216, 21),
           (2, 218, 13), (22, 228, 21), (41, 229, 14), (43, 239, 19))


def transform_producer(source: str) -> str:
    """Keep physics unchanged; record the original diffusion inputs and outputs."""
    declarations = "   LOGICAL :: pr87_diff_specified, pr87_capture_rain_diffusion\n"
    anchor = "           IF (PRESENT(all_pair_diffusion_tendency32).AND.pr87_diff_channel<=4) THEN\n"
    if source.count(declarations) != 1 or source.count(anchor) != 1:
        raise ValueError("ambiguous retained diffusion producer")
    # RESHAPE uses column order: each coordinate is one complete (i,j,k) column.
    coords = ", &\n       ".join(",".join(map(str, t)) for t in TARGETS)
    source = source.replace(declarations, declarations + f"""   INTEGER :: pr92_u,pr92_target,pr92_i,pr92_j,pr92_k,pr92_dx,pr92_dy
   INTEGER,PARAMETER :: pr92_targets(3,12)=RESHAPE([ &
       {coords}], [3,12])
""", 1)
    record = """           ! Coordinate selection controls diagnostic I/O only, never a physical update.
           IF (pr87_diff_channel>=7.AND.PRESENT(all_pair_diffusion_identity)) THEN
             IF (all_pair_diffusion_identity(1)==15) THEN
               OPEN(NEWUNIT=pr92_u,FILE='pr92_diffusion_producer.raw', &
                    STATUS='UNKNOWN',POSITION='APPEND')
               DO pr92_target=1,SIZE(pr92_targets,2)
                 pr92_i=pr92_targets(1,pr92_target)
                 pr92_j=pr92_targets(2,pr92_target)
                 pr92_k=pr92_targets(3,pr92_target)
                 IF (pr92_i<pr87_diff_i_start.OR.pr92_i>pr87_diff_i_end.OR. &
                     pr92_j<pr87_diff_j_start.OR.pr92_j>pr87_diff_j_end.OR. &
                     pr92_k<kts.OR.pr92_k>pr87_diff_k_end) CYCLE
                 WRITE(pr92_u,'(A,7(1X,I0))') 'PR92_PRODUCER', &
                   all_pair_diffusion_identity(1),rk_step,pr87_diff_channel,im,pr92_i,pr92_j,pr92_k
                 WRITE(pr92_u,'(A,8(1X,I0))') 'PR92_PRODUCER_BOUNDS',all_pair_diffusion_identity
                 WRITE(pr92_u,'(A,2(1X,Z8.8),1X,Z16.16)') 'PR92_TENDENCY', &
                   TRANSFER(pr87_rain_tendency_before(pr92_i,pr92_k,pr92_j),0_4), &
                   TRANSFER(scalar_tends(pr92_i,pr92_k,pr92_j,im),0_4), &
                   TRANSFER(pr87_rain_diffusion_increment(pr92_i,pr92_k,pr92_j),0_8)
                 WRITE(pr92_u,'(A,4(1X,Z8.8))') 'PR92_PRODUCER_SCALE', &
                   TRANSFER(c1h(pr92_k),0_4),TRANSFER(c2h(pr92_k),0_4), &
                   TRANSFER(rdx,0_4),TRANSFER(rdy,0_4)
                 DO pr92_dy=-1,1
                   WRITE(pr92_u,'(A,1X,I0,9(1X,Z8.8))') 'PR92_PRODUCER_STENCIL',pr92_dy, &
                     (TRANSFER(scalar(pr92_i+pr92_dx,pr92_k,pr92_j+pr92_dy,im),0_4),pr92_dx=-1,1), &
                     (TRANSFER(xkmhd(pr92_i+pr92_dx,pr92_k,pr92_j+pr92_dy),0_4),pr92_dx=-1,1), &
                     (TRANSFER(mut(pr92_i+pr92_dx,pr92_j+pr92_dy),0_4),pr92_dx=-1,1)
                 END DO
                 WRITE(pr92_u,'(A,10(1X,Z8.8))') 'PR92_PRODUCER_METRICS', &
                   TRANSFER(msfux(pr92_i,pr92_j),0_4),TRANSFER(msfux(pr92_i+1,pr92_j),0_4), &
                   TRANSFER(msfuy(pr92_i,pr92_j),0_4),TRANSFER(msfuy(pr92_i+1,pr92_j),0_4), &
                   TRANSFER(msfvx_inv(pr92_i,pr92_j),0_4),TRANSFER(msfvx_inv(pr92_i,pr92_j+1),0_4), &
                   TRANSFER(msfvy(pr92_i,pr92_j),0_4),TRANSFER(msfvy(pr92_i,pr92_j+1),0_4), &
                   TRANSFER(msftx(pr92_i,pr92_j),0_4),TRANSFER(msfty(pr92_i,pr92_j),0_4)
                 WRITE(pr92_u,'(A)') 'PR92_PRODUCER_END'
               END DO
               CLOSE(pr92_u)
             END IF
           END IF
"""
    return source.replace(anchor, record + anchor, 1)


def require_c14(path: Path) -> str:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != C14_SHA256:
        raise ValueError("producer input is not the retained C14 module")
    return data.decode()
