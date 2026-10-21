from pathlib import Path
import sys
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from pr97_t1_rounding import read_columns

BOUNDS = {'its':2, 'ite':3, 'jts':7, 'jte':7}


def row(i, *, counts=(0,1,0,0,0,1), error=-2.0):
    values = [error, 0.0, abs(error), -3.0, 3.0, 0.0, -3.0, 0.0, 0.0,
              abs(error), abs(error)]
    if counts[5] == 0:
        values = [0.0]*11
    return ' '.join(map(str, ['LIQCOL',i,7,*counts,*values]))+'\n'


def test_complete_compact_columns_preserve_zero_events_and_error_sign(tmp_path):
    p = tmp_path/'columns.raw'
    p.write_text(row(2)+row(3,counts=(0,0,0,0,0,0),error=0.0))
    counts, values = read_columns(p, BOUNDS)
    assert counts[:,:,5].sum()==1
    assert values[0,0,0]==-2.0
    assert np.count_nonzero(counts[:,:,5])==1


@pytest.mark.parametrize('text,reason', [
    (row(2), 'missing'), (row(2)+row(2), 'duplicate'),
    (row(2)+row(4), 'outside'),
    (row(2)+row(3).replace('-2.0','nan'), 'finite'),
    (row(2)+row(3,counts=(0,1,0,0,0,2)), 'counts')])
def test_rejects_incomplete_or_invalid_compact_account(tmp_path,text,reason):
    p = tmp_path/'columns.raw'
    p.write_text(text)
    with pytest.raises(ValueError,match=reason):
        read_columns(p,BOUNDS)
