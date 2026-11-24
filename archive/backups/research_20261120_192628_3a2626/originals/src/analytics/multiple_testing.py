"""Benjamini–Yekutieli cho họ kiểm định nhiều mẫu hình × kỳ nắm giữ."""
import numpy as np


def fdr_by(values):
    values=np.asarray(values,dtype=float)
    result=np.full(len(values),np.nan);valid=np.flatnonzero(np.isfinite(values))
    if not len(valid):return result
    order=valid[np.argsort(values[valid])];n=len(order)
    adjusted=values[order]*n*sum(1/i for i in range(1,n+1))/np.arange(1,n+1)
    result[order]=np.minimum(1,np.minimum.accumulate(adjusted[::-1])[::-1])
    return result
