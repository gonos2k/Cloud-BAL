"""Shared read-only snapshot diagnostic calculations."""
import hashlib
import numpy as np


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def stats(qi,qs,ni,selected,policy,analysis_total,analysis_den):
    finite=np.isfinite(qi)&np.isfinite(qs)&np.isfinite(ni)
    nonnegative=finite&(qi>=0)&(qs>=0)&(ni>=0)
    q=qi.astype(np.float64);s=qs.astype(np.float64);n=ni.astype(np.float64)
    positive=nonnegative&(q>0)&(n>0);mean=np.zeros_like(q)
    np.divide(q,n,out=mean,where=positive)
    inmean=positive&(mean>=policy['lower'][1])&(mean<=policy['upper'][1])
    total=q+s
    paired=(nonnegative&((q==0)&(n==0)|((q>0)&(n>0))))
    support=paired&(total>0)&((q==0)|inmean)
    fraction=np.zeros_like(q);np.divide(q,total,out=fraction,where=total>0)
    outqi=(fraction*analysis_total).astype(np.float32); outni=np.zeros_like(q)
    np.divide(outqi.astype(np.float64),mean,out=outni,where=positive)
    with np.errstate(over='ignore',under='ignore',invalid='ignore'):
        outni32=outni.astype(np.float32); volume=np.multiply(outni32,analysis_den,dtype=np.float32)
    return {'selected':int(selected.sum()),'nonfinite':int((selected&~finite).sum()),'negative':int((selected&finite&~nonnegative).sum()),'ice_zero_ni_positive':int((selected&nonnegative&(q==0)&(n>0)).sum()),'ice_positive_ni_zero':int((selected&nonnegative&(q>0)&(n==0)).sum()),'solid_total_zero':int((selected&nonnegative&(total==0)).sum()),'positive_pair_inside_mean_bounds':int((selected&inmean).sum()),'positive_pair_outside_mean_bounds':int((selected&positive&~inmean).sum()),'background_pair_and_mass_support_diagnostic':int((selected&support).sum()),'computed_rounded_ni_density_above_cap':int((selected&support&(volume>policy['number_cap'][1])).sum()),'nonfinite_candidate_volume':int((selected&support&~np.isfinite(volume)).sum())}


