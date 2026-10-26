"""Add diagnostic-only producer records at the retained C14 failure support."""
from __future__ import annotations

import hashlib
from pathlib import Path


C14_SHA256 = "6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1"
TARGETS = ((127, 5, 22), (170, 42, 23), (171, 43, 23), (163, 44, 20),
           (158, 47, 20), (232, 203, 20), (203, 213, 21), (11, 216, 21),
           (2, 218, 13), (22, 228, 21), (41, 229, 14), (43, 239, 19))


def _validate_selection(timestep: int, rk: int,
                       cells: tuple[tuple[int, int, int], ...] | None
                       ) -> tuple[tuple[int, int, int], ...]:
    if not isinstance(timestep, int) or isinstance(timestep, bool) or timestep < 1:
        raise ValueError("timestep must be a positive integer")
    if not isinstance(rk, int) or isinstance(rk, bool) or rk not in (1, 2, 3):
        raise ValueError("RK stage must be 1, 2, or 3")
    selected = TARGETS if cells is None else cells
    if not selected:
        raise ValueError("at least one producer cell is required")
    normalized = []
    for cell in selected:
        if (not isinstance(cell, (tuple, list)) or len(cell) != 3 or
                any(not isinstance(value, int) or
                    isinstance(value, bool) or value < 1 for value in cell)):
            raise ValueError("producer cells must be positive (i, j, k) triples")
        normalized.append(tuple(cell))
    if len(set(normalized)) != len(normalized):
        raise ValueError("producer cells must be unique")
    return tuple(normalized)


def transform_producer(source: str, *, timestep: int = 15, rk: int | None = None,
                       cells: tuple[tuple[int, int, int], ...] | None = None) -> str:
    """Keep physics unchanged; record the original diffusion inputs and outputs."""
    selected_cells = _validate_selection(timestep, 1 if rk is None else rk, cells)
    declarations = "   LOGICAL :: pr87_diff_specified, pr87_capture_rain_diffusion\n"
    anchor = "           IF (PRESENT(all_pair_diffusion_tendency32).AND.pr87_diff_channel<=4) THEN\n"
    if source.count(declarations) != 1 or source.count(anchor) != 1:
        raise ValueError("ambiguous retained diffusion producer")
    # RESHAPE uses column order: each coordinate is one complete (i,j,k) column.
    source = source.replace(declarations, declarations +
                            "   INTEGER :: pr92_u,pr92_target,pr92_i,pr92_j,pr92_k,pr92_dx,pr92_dy\n" +
                            _target_declaration(selected_cells), 1)
    rk_guard = "" if rk is None else f".AND.rk_step=={rk}"
    record = f"""           ! Coordinate selection controls diagnostic I/O only, never a physical update.
           IF (pr87_diff_channel>=7.AND.PRESENT(all_pair_diffusion_identity)) THEN
             IF (all_pair_diffusion_identity(1)=={timestep}{rk_guard}) THEN
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


def retarget_producer(source: str, *, timestep: int, rk: int,
                      cells: tuple[tuple[int, int, int], ...]) -> str:
    """Retarget one generated legacy capture block without changing physics."""
    selected_cells = _validate_selection(timestep, rk, cells)
    old_declaration = _target_declaration(TARGETS)
    new_declaration = _target_declaration(selected_cells)
    old_guard = "             IF (all_pair_diffusion_identity(1)==15) THEN\n"
    new_guard = (f"             IF (all_pair_diffusion_identity(1)=={timestep}.AND."
                 f"rk_step=={rk}) THEN\n")
    if source.count(old_declaration) != 1 or source.count(old_guard) != 1:
        raise ValueError("expected one complete legacy producer capture block")
    if source.count("PR92_PRODUCER_END") != 1:
        raise ValueError("expected one producer capture routine")
    return source.replace(old_declaration, new_declaration, 1).replace(old_guard, new_guard, 1)


def _target_declaration(cells: tuple[tuple[int, int, int], ...]) -> str:
    coords = ", &\n       ".join(",".join(map(str, cell)) for cell in cells)
    return (f"   INTEGER,PARAMETER :: pr92_targets(3,{len(cells)})=RESHAPE([ &\n"
            f"       {coords}], [3,{len(cells)}])\n")


def require_c14(path: Path) -> str:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != C14_SHA256:
        raise ValueError("producer input is not the retained C14 module")
    return data.decode()
