#!/usr/bin/env python3
"""Check the Fortran replay stream with a manufactured four-node time history."""
import argparse
from pathlib import Path
import subprocess
import tempfile

import numpy as np


def check_driver(executable):
    nn,nz,nt,ne = 4,3,2,5
    lat = np.deg2rad([38.,38.,38.01,38.01])
    lon = np.deg2rad([126.,126.01,126.,126.01])
    pressure = np.array([95000.,90000.,5000.])
    triangles = np.array([[1,2,4],[1,4,3]],dtype="<i4")
    edges = np.array([[1,2],[2,4],[1,4],[3,4],[1,3]],dtype="<i4")
    incidence = np.array([[1,2,-3],[3,-4,-5]],dtype="<i4")
    parameters = [np.deg2rad(38.),np.deg2rad(126.),6371200.,0.,np.deg2rad(126.)]
    counts = [2*nn,3*nn,3*ne,3*ne,3*ne,nt,nt,nt,nt,3*nt,nt,nt]
    for invalid in (False,True):
        for top_coefficient in (0.,1.):
            ps = np.broadcast_to(np.array([99880.,100000.,100120.])[:,None],(3,nn)).copy()
            height = np.broadcast_to([500.,1000.,20000.],(3,nn,nz)).copy()
            if invalid:
                height[:,0,0] = -1.
            # A quadratic top history: Simpson mean is (1+0+1)/6 = 1/3.
            omega = np.broadcast_to((1/30+top_coefficient*np.array([1.,0.,1.]))[:,None],(3,nn))
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with (root/"input.bin").open("wb") as stream:
                    stream.write(np.array([nn,nz,nt,ne],dtype="<i4").tobytes())
                    stream.write(np.array([0,3600,7200],dtype="<i8").tobytes())
                    for value in (parameters,lat,lon,np.zeros(nn),pressure,ps,height,
                                  np.zeros((3,nn,nz)),np.zeros((3,nn,nz)),
                                  np.zeros((3,nn)),np.zeros((3,nn)),omega):
                        stream.write(np.asarray(value,dtype="<f8").tobytes())
                    for value in (triangles,edges,incidence):
                        stream.write(value.tobytes())
                subprocess.run([str(executable),str(root/"input.bin"),str(root/"output.bin")],check=True)
                with (root/"output.bin").open("rb") as stream:
                    raw = np.fromfile(stream,dtype="<f8",count=sum(counts))
                    mapped = np.fromfile(stream,dtype="<i4",count=3*nn).reshape(3,nn)
                    domain = np.fromfile(stream,dtype="<f8",count=2)
                    unknown = np.fromfile(stream,dtype="<i4",count=2)
                    assert not stream.read(1)
                xy,p10,covered,lower,missing,area,surface,rate,bound,top,known,residual = np.split(raw,np.cumsum(counts)[:-1])
                expected = -top_coefficient*area/3
                np.testing.assert_allclose(known,expected,rtol=1e-13,atol=1e-8)
                np.testing.assert_allclose(surface,area/30,rtol=1e-13)
                np.testing.assert_allclose(domain[0],expected.sum(),rtol=1e-13,atol=1e-8)
                assert np.isnan(residual).all() and np.isnan(domain[1])
                assert np.array_equal(unknown,[4,1])
                assert np.all(mapped[:,0] == (0 if invalid else 1))
                assert np.all(mapped[:,1:] == 1)
    print("Fortran lower-transport stream: 4 manufactured cases passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable",type=Path)
    check_driver(parser.parse_args().executable.resolve())
