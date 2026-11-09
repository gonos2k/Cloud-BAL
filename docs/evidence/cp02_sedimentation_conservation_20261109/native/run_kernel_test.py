#!/usr/bin/env python3
"""Extract the sedimentation statements from the candidate source into a test driver."""
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
baseline = len(sys.argv) > 3 and sys.argv[3] == '--baseline'
a = source.index('        k = kte\n', source.index('      do n = 1, mstepmax\n')) if baseline else source.index('        ! A boundary transfer is computed once')
b = source.index('        do k = kts, kte\n          do i = its, ite\n          qrs_tmp', a)
warm = source[a:b]
a = source.index('        k = kte\n', source.index('      do n = 1, mstepmax_i\n')) if baseline else source.index('        ! Ice mass and number use')
b = source.index('        do k = kts, kte\n          do i = its, ite\n            qrs_tmp', a)
ice = source[a:b]
template = Path(__file__).with_name('kernel_driver.F90.in').read_text()
if baseline:
    template = template.replace(' do c=1,7', ' do c=7,7')
Path(sys.argv[2]).write_text(template.replace('@WARM@',warm).replace('@ICE@',ice))
