from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np

source=Path('/var/tmp/b1-two-hour-probe-20261103/compare_histories.py')
spec=importlib.util.spec_from_file_location('compare_histories_under_review',source)
module=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

# Numeric scalar attributes must serialize without a dtype-view exception.
scalar_i=module.value_signature(np.asarray(3,dtype=np.int32))
scalar_f=module.value_signature(np.asarray(1.25,dtype=np.float32))
assert scalar_i[0]=='numeric' and scalar_i[2]==() and scalar_i[3]==np.asarray(3,dtype=np.int32).tobytes()
assert scalar_f[0]=='numeric' and scalar_f[2]==() and scalar_f[3]==np.asarray(1.25,dtype=np.float32).tobytes()
assert scalar_i!=module.value_signature(np.asarray(4,dtype=np.int32))
assert scalar_f!=module.value_signature(np.asarray(1.5,dtype=np.float32))

# Same dtype/shape with one changed numeric payload must remain distinguishable.
a=np.asarray([1.0,2.0],dtype=np.float32)
b=np.asarray([1.0,2.5],dtype=np.float32)
assert module.value_signature(a)!=module.value_signature(b)
# The new serialization is byte-identical to the prior view method for arrays.
assert module.value_signature(a)[3]==a.view(np.uint8).tobytes()
print('PASS scalar int/float attributes, changed payload, and array byte parity')
