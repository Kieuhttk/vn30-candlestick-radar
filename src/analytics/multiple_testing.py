"""Benjamini–Yekutieli cho họ kiểm định nhiều mẫu hình × kỳ nắm giữ."""
import numpy as np


def fdr_by(values, n_tests=None):
    values=np.asarray(values,dtype=float)
    result=np.full(len(values),np.nan);valid=np.flatnonzero(np.isfinite(values))
    if not len(valid):return result
    order=valid[np.argsort(values[valid])];n=len(order) if n_tests is None else int(n_tests)
    if n<len(valid):raise ValueError("n_tests nhỏ hơn số kiểm định hợp lệ")
    if ((values[valid]<0)|(values[valid]>1)).any():raise ValueError("p-value ngoài [0,1]")
    adjusted=values[order]*n*sum(1/i for i in range(1,n+1))/np.arange(1,len(order)+1)
    result[order]=np.minimum(1,np.minimum.accumulate(adjusted[::-1])[::-1])
    return result
