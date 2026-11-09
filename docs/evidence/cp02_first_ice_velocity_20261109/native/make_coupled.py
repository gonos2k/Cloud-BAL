#!/usr/bin/env python3
from pathlib import Path
import sys
import re
s=Path(sys.argv[1]).read_text()
assert 'double precision, dimension(its:ite,kts:kte,4) :: work1' in s.lower()
assert re.search(r'double precision, dimension\(its:ite,kts:kte,2\)\s*:: workn', s, re.I)
start=s.index('      ! The final warm-loop slope call restores ice velocities')
end=s.index('      do n = 1, mstepmax_i',start)
boundary=s[s.index('      do k = kte, kts, -1',start):end]
a=s.index('        ! Ice mass and number use',end)
b=s.index('        do k = kts, kte\n          do i = its, ite\n            qrs_tmp',a)
ice=s[a:b]
a=s.index('       do k = kte, kts, -1',b)
b=s.index('      enddo',s.index('       enddo',a)+len('       enddo'))+len('      enddo')
endnorm=s[a:b]
assert boundary.count('/delz(i,k)')==2 and endnorm.count('/delz(i,k)')==2
out=Path(__file__).with_name('coupled.F90.in').read_text()
for key,value in [('BOUNDARY',boundary),('ICE',ice),('ENDNORM',endnorm)]: out=out.replace('@'+key+'@',value)
Path(sys.argv[2]).write_text(out)

# Preserve the actual declarations and slope routine; unrelated model procedures
# and WRF imports are excluded from this isolated column executable.
header=s[:s.index("    contains")].replace("   use module_mp_radar\n", "").replace("   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG\n", "")
a=s.lower().index("      subroutine slope_kdm6(")
b=s.lower().index("  end subroutine slope_kdm6",a)+len("  END subroutine slope_kdm6")
Path(sys.argv[3]).write_text(header+"\n contains\n"+s[a:b]+"\nend module module_mp_kdm6\n")
