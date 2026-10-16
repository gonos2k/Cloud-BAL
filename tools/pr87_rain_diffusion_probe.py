"""Instrument the selected QR/QNR RK1 diffusion call for one cell.

The generated source keeps the production diffusion call and tendency intact.
It prints the R32 inputs and accumulator immediately before and after that call
so an external replay can evaluate the same stencil in R64.
"""

from __future__ import annotations

import hashlib

_V16_MODULE_EM_SHA256 = "7052f067b3c84cb247b8245ce8979064c63577dd7aaa851cc6db191aff095f51"
_IMPORT_ANCHOR = (
    "  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &\n"
)
_CALL_MARKER = "         IF (.not. mix2_off)"
_CELL_GUARD = (
    "rk_step == 1 .AND. (im == P_QR .OR. im == P_QNR) .AND. &\n"
    "               110 >= its .AND. 110 <= ite .AND. 5 >= jts .AND. 5 <= jte .AND. &\n"
    "               18 >= kts .AND. 18 <= kte .AND. 110 > ims .AND. 111 < ime .AND. &\n"
    "               5 > jms .AND. 6 < jme"
)


def _call_span(source: str, start: int) -> tuple[int, int, str]:
    """Return the complete horizontal_diffusion CALL statement."""
    marker = "CALL horizontal_diffusion"
    call_start = source.find(marker, start)
    if call_start < 0:
        raise ValueError("missing horizontal_diffusion call after mix2_off guard")
    open_paren = source.find("(", call_start + len(marker))
    if open_paren < 0:
        raise ValueError("missing horizontal_diffusion argument list")
    depth = 0
    quote: str | None = None
    index = open_paren
    while index < len(source):
        char = source[index]
        if quote:
            if char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"":
            quote = char
        elif char == "!":
            newline = source.find("\n", index)
            if newline < 0:
                raise ValueError("unterminated comment in horizontal_diffusion call")
            index = newline
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return call_start, index + 1, source[call_start:index + 1]
        index += 1
    raise ValueError("unterminated horizontal_diffusion call")


def _write_record(tag: str, tendency: str) -> str:
    values = [
        "dt_step, khdq,",
        f"{tendency}, scalar(110,18,5,im),",
        "scalar(109,18,5,im), scalar(111,18,5,im),",
        "scalar(110,18,4,im), scalar(110,18,6,im),",
        "mut(110,5), mut(109,5), mut(111,5),",
        "mut(110,4), mut(110,6), c1h(18), c2h(18),",
        "xkmhd(110,18,5), xkmhd(109,18,5), xkmhd(111,18,5),",
        "xkmhd(110,18,4), xkmhd(110,18,6),",
        "msfux(109,5), msfux(110,5), msfux(111,5),",
        "msfuy(109,5), msfuy(110,5), msfuy(111,5),",
        "msfvx_inv(110,5), msfvx_inv(110,6),",
        "msfvy(110,5), msfvy(110,6), msftx(110,5),",
        "msfty(110,5), rdx, rdy",
    ]
    value_lines = " &\n".join(f"                {line}" for line in values)
    return (
        f"           WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &\n"
        f"                '{tag}', rk_step, im, 110, 5, 18, moist_step, mix2_off, &\n"
        f"{value_lines}\n"
    )


def _instrument_source(source: str) -> str:
    """Apply the trace transform to module_em source with the known call shape."""
    if source.count(_IMPORT_ANCHOR) != 1:
        raise ValueError("expected one module_state_description import anchor")
    source = source.replace(
        _IMPORT_ANCHOR,
        _IMPORT_ANCHOR.replace("p_qr,", "p_qr, p_qnr,"),
        1,
    )

    if source.count(_CALL_MARKER) != 1:
        raise ValueError("expected one mix2_off horizontal diffusion guard")
    guard_start = source.index(_CALL_MARKER)
    call_start, call_end, call = _call_span(source, guard_start)
    if "'m'" not in call or "scalar_tends(ims,kms,jms,im)" not in call:
        raise ValueError("diffusion call no longer matches rk_scalar_tend scalar path")
    block_start = guard_start
    block_end = call_end
    block = (
        "         IF (.not. mix2_off) THEN\n"
        f"           IF ({_CELL_GUARD}) THEN\n"
        f"{_write_record('PR87_RAIN_DIFFUSION_PRE', 'scalar_tends(110,18,5,im)')}"
        "           END IF\n"
        f"           {call}\n"
        f"           IF ({_CELL_GUARD}) THEN\n"
        f"{_write_record('PR87_RAIN_DIFFUSION_POST', 'scalar_tends(110,18,5,im)')}"
        "           END IF\n"
        "         END IF"
    )
    return source[:block_start] + block + source[block_end:]


def add_rain_diffusion_probe(source: str) -> str:
    """Transform only the hash-pinned V16 module_em source."""
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if source_sha256 != _V16_MODULE_EM_SHA256:
        raise ValueError("rain diffusion probe requires the hash-pinned V16 module_em source")
    return _instrument_source(source)
