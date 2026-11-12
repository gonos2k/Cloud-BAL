from pathlib import Path
import hashlib,sys
s=Path(sys.argv[1]).read_text()
assert hashlib.sha256(s.encode()).hexdigest()=='f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
a=s.index('      found = .false.');b=s.index('   end function cloud_bal_trace_cell',a)
s=s[:a]+'''      found = trace_j == 72 .and. (trace_i == 192 .or. trace_i == 201)
'''+s[b:]
needle='if (diagnostic_itimestep >= 361 .and. diagnostic_itimestep <= 540) then'
assert s.count(needle)==1
s=s.replace(needle,'if (diagnostic_itimestep == 1) then')
Path(sys.argv[2]).write_text(s)
