from __future__ import annotations

import gzip
import hashlib
import re
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/evidence/pr87_two_step_v42_20261016/module_mp_kdm6.F.gz"
TRANSFORM = runpy.run_path(str(ROOT / "tools/pr87_graupel_failure_context.py"))
SOURCE_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"


def _source() -> str:
    return gzip.decompress(ARCHIVE.read_bytes()).decode()


def _strip_instrumentation(transformed: str) -> str:
    source = re.sub(
        r"\n   call pr87_report_graupel_consumer\(\d+,pr87_model_timestep,lat, &\n"
        r"        its,ite,kts,kte,qrs_tmp,brs,progb_status\)\n",
        "",
        transformed,
    )
    reporter_start = source.index("\n   subroutine pr87_report_graupel_consumer(")
    reporter_end = source.index(
        "   end subroutine pr87_report_graupel_consumer\n", reporter_start
    ) + len("   end subroutine pr87_report_graupel_consumer\n")
    source = source[:reporter_start] + source[reporter_end:]
    capture = (
        "   if (itimestep == 3) then\n"
        "     call kdm6_trace_dump(1,itimestep,ids,ide,jds,jde,kds,kde, &\n"
        "          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &\n"
        "          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &\n"
        "          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)\n"
        "   endif\n"
    )
    source = source.replace(capture, "", 1)
    return source.replace(
        "       if (itimestep == 3) path='kdm6_third_call_pre.raw'\n", "", 1
    )


def test_transform_instruments_only_seven_native_prog_b_calls() -> None:
    original = _source()
    assert hashlib.sha256(original.encode()).hexdigest() == SOURCE_SHA256
    transformed = TRANSFORM["add_failure_context"](original)

    assert original.count(TRANSFORM["CALL_START"]) == 7
    assert original.count(TRANSFORM["CALL_END"]) == 8
    assert transformed.count("call pr87_report_graupel_consumer(") == 7
    for site in range(1, 8):
        assert transformed.count(
            f"call pr87_report_graupel_consumer({site},pr87_model_timestep,lat, &"
        ) == 1

    # The eighth end-line match belongs to a different routine's ProgB signature.
    assert _strip_instrumentation(transformed) == original
