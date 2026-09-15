"""Extract the real BALCON conversion, NONLIN call, and rollback for a unit fixture.

This intentionally excludes continuity/relaxation and is not a full BALCON test.
"""
from pathlib import Path
import sys


def between(text, start, end):
    assert text.count(start) == 1, start
    return text.split(start, 1)[1].split(end, 1)[0]


source = Path(sys.argv[1]).read_text()
conversion = between(source, "c convert input observed fields to perturbations \n", "      call frict(")
call = "      call nonlin(" + between(source, "      call nonlin(", "c *** Compute new phi")
rollback = " 900  if(bal_status.ne.1)then" + between(
    source, " 900  if(bal_status.ne.1)then", "      if(allocated(aaa))"
)
assert "nonlin_status" in call and "goto 900" in call

prefix = """      subroutine caller_fragment(to,uo,vo,omo,t,u,v,om,
     &                           tb,ub,vb,omb,dp,nu,nv,bal_status)
      implicit none
      integer,parameter :: nx=4,ny=4,nz=4
      integer i,j,k,bal_status,nonlin_status
      real*4 to(nx,ny,nz),uo(nx,ny,nz),vo(nx,ny,nz),omo(nx,ny,nz)
      real*4 t(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz),om(nx,ny,nz)
      real*4 tb(nx,ny,nz),ub(nx,ny,nz),vb(nx,ny,nz),omb(nx,ny,nz)
      real*4 nu(nx,ny,nz),nv(nx,ny,nz),dp(nz),dx(nx,ny),dy(nx,ny)
      real*4 torig(nx,ny,nz),uorig(nx,ny,nz),vorig(nx,ny,nz)
      real*4 omorig(nx,ny,nz),tworkorig(nx,ny,nz),uworkorig(nx,ny,nz)
      real*4 vworkorig(nx,ny,nz),omworkorig(nx,ny,nz),dt,bnd,rod
      torig=to
      uorig=uo
      vorig=vo
      omorig=omo
      tworkorig=t
      uworkorig=u
      vworkorig=v
      omworkorig=om
      dx=1.
      dy=1.
      dt=1.
      rod=1.
      bnd=1.e-30
      bal_status=0
"""
Path(sys.argv[2]).write_text(prefix + conversion + call + "      bal_status=1\n" + rollback + "      end\n")
