"""Bootstrap vòng tròn trên LỊCH đầy đủ; giữ ngày không tín hiệu trong khối."""
import numpy as np
import pandas as pd


def block_test(series, calendar=None, block_size=20, resamples=1000, seed=2026, one_sided=False):
    series=series.groupby(level=0).mean().sort_index()
    if calendar is not None:series=series.reindex(pd.DatetimeIndex(calendar))
    values=series.to_numpy(dtype=float,copy=True);values[np.abs(values)<1e-12]=0
    finite=np.isfinite(values);estimate=float(values[finite].mean()) if finite.any() else np.nan
    if finite.sum()<20:return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=int(finite.sum()))
    if block_size<1 or resamples<99:raise ValueError('block_size >=1 và resamples >=99')
    n=len(values);length=min(block_size,n);rng=np.random.default_rng(seed)
    collected=[]
    for offset in range(0,resamples,128):
        batch=min(128,resamples-offset)
        starts=rng.integers(0,n,size=(batch,int(np.ceil(n/length))))
        indices=((starts[:,:,None]+np.arange(length))%n).reshape(batch,-1)[:,:n]
        samples=values[indices];counts=np.isfinite(samples).sum(axis=1)
        collected.append(np.divide(np.nansum(samples,axis=1),counts,out=np.full(batch,np.nan),where=counts>0))
    means=np.concatenate(collected)
    means=means[np.isfinite(means)]
    if len(means)<resamples*.8:return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=int(finite.sum()))
    low,high=np.quantile(means,[.025,.975]);centered=means-estimate
    extreme=centered>=estimate if one_sided else np.abs(centered)>=abs(estimate)
    return dict(mean=estimate,low=float(low),high=float(high),p=(1+int(extreme.sum()))/(len(means)+1),n_dates=int(finite.sum()))


def _block_tables(values,length):
    """Tổng và số hữu hạn cho từng khối vòng tròn; tránh dựng B×N×S."""
    values=np.asarray(values,dtype=float)
    if values.ndim==1:values=values[:,None]
    n=len(values);length=min(int(length),n)
    extended=np.concatenate([values,values[:length-1]],axis=0) if length>1 else values
    sums=np.vstack([np.zeros((1,values.shape[1])),np.cumsum(np.where(np.isfinite(extended),extended,0.),axis=0)])
    counts=np.vstack([np.zeros((1,values.shape[1])),np.cumsum(np.isfinite(extended),axis=0)])
    return sums[length:]-sums[:-length],counts[length:]-counts[:-length]


def _draw_totals(tables,last_tables,starts,n,length):
    sums,counts=tables;blocks=n//length;remainder=n%length
    shape=(len(starts),sums.shape[1])
    total=sums[starts[:,:blocks]].sum(axis=1) if blocks else np.zeros(shape)
    count=counts[starts[:,:blocks]].sum(axis=1) if blocks else np.zeros(shape)
    if remainder:
        total+=last_tables[0][starts[:,-1]];count+=last_tables[1][starts[:,-1]]
    return total,count


def _bootstrap_result(estimate,draws,resamples,one_sided=True,**extra):
    draws=np.asarray(draws);draws=draws[np.isfinite(draws)]
    base=dict(mean=float(estimate),low=np.nan,high=np.nan,p=np.nan,
              effective_resamples=len(draws),**extra)
    if len(draws)<resamples*.8:return base
    draws=np.where(np.abs(draws)<1e-12,0.,draws)
    estimate=0. if abs(estimate)<1e-12 else estimate
    low,high=np.quantile(draws,[.025,.975]);centered=draws-estimate
    extreme=centered>=estimate if one_sided else np.abs(centered)>=abs(estimate)
    base.update(mean=float(estimate),low=float(low),high=float(high),p=(1+int(extreme.sum()))/(len(draws)+1))
    return base


def two_sample_block_test(test_returns,train_controls,test_calendar=None,train_calendar=None,
                          direction=1,block_size=20,resamples=1000,seed=2026):
    """Chênh test–nền train, bootstrap riêng hai lịch và chung mọi mã trong mỗi lịch.

    Test lấy trọng số đều theo ngày tín hiệu. Trọng số mã thay đổi cùng mẫu test;
    mỗi lần bootstrap tính lại nền từ TRAIN, không fit bằng test.
    Dùng bootstrap-t với phương sai ảnh hưởng theo khối để xử lý độ lệch/sai số thay đổi.
    """
    if direction not in (-1,1):raise ValueError('direction phải là +1 hoặc -1')
    if block_size<1 or resamples<99:raise ValueError('block_size >=1 và resamples >=99')
    if test_returns.index.has_duplicates or train_controls.index.has_duplicates:
        raise ValueError('Lịch không được trùng ngày')
    test=test_returns.sort_index().copy();train=train_controls.reindex(columns=test.columns).sort_index().copy()
    if test_calendar is not None:test=test.reindex(pd.DatetimeIndex(test_calendar))
    if train_calendar is not None:train=train.reindex(pd.DatetimeIndex(train_calendar))
    if len(train) and len(test) and train.index.max()>=test.index.min():
        raise ValueError('Lịch train và test phải tách theo thời gian')
    train_values=train.to_numpy(dtype=float,copy=True);test_values=test.to_numpy(dtype=float,copy=True)
    train_values[~np.isfinite(train_values)]=np.nan;test_values[~np.isfinite(test_values)]=np.nan
    train_mean=np.divide(np.nansum(train_values,axis=0),np.isfinite(train_values).sum(axis=0),
                         out=np.full(train.shape[1],np.nan),where=np.isfinite(train_values).sum(axis=0)>0)
    test_values[:,~np.isfinite(train_mean)]=np.nan
    counts=np.isfinite(test_values).sum(axis=1)
    daily=np.divide(np.nansum(test_values,axis=1),counts,out=np.full(len(test),np.nan),where=counts>0)
    weights=np.divide(np.isfinite(test_values).astype(float),counts[:,None],out=np.zeros_like(test_values),where=counts[:,None]>0)
    n_dates=int((counts>0).sum());n_train=int(np.isfinite(train_values).any(axis=1).sum())
    labels=int(np.isfinite(test_values).sum())
    estimate=direction*(np.nanmean(daily)-np.nansum(weights.sum(axis=0)/max(n_dates,1)*train_mean)) if n_dates else np.nan
    if n_dates<20 or n_train<20 or labels<30:
        return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=n_dates,n_train_dates=n_train,effective_resamples=0)
    test_data=np.column_stack([daily,weights]);nt=len(train);nv=len(test)
    lt=min(block_size,nt);lv=min(block_size,nv)
    # Ít khối làm bootstrap-t không ổn định (thấy trong mô phỏng h=20).
    # Đây là chốt bảo thủ, không phải bảo đảm mọi p-value đã được hiệu chuẩn.
    if nt//lt<10 or nv//lv<10:
        return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=n_dates,n_train_dates=n_train,effective_resamples=0,std_error=np.nan)
    train_frequency=np.isfinite(train_values).sum(axis=0)/nt
    average_weight=weights.sum(axis=0)/n_dates
    scale=np.divide(average_weight,train_frequency,out=np.zeros_like(average_weight),where=train_frequency>0)
    residual=np.where(np.isfinite(train_values),train_values-np.nan_to_num(train_mean),0.)
    train_influence=-direction*np.sum(residual*scale,axis=1)
    centered=direction*(np.nan_to_num(daily)-weights@np.nan_to_num(train_mean))-estimate
    test_influence=np.where(counts>0,centered/(n_dates/nv),0.)
    train_variance=np.mean(_block_tables(train_influence,lt)[0]**2)/(lt*nt)
    test_variance=np.mean(_block_tables(test_influence,lv)[0]**2)/(lv*nv)
    standard_error=float(np.sqrt(max(0.,train_variance+test_variance)))
    if standard_error<1e-14:
        point=0. if abs(estimate)<1e-12 else float(estimate)
        return dict(mean=point,low=point,high=point,p=1/(resamples+1) if point>0 else 1.,
                    n_dates=n_dates,n_train_dates=n_train,effective_resamples=resamples,std_error=standard_error)
    tt=_block_tables(train_values,lt);tr=_block_tables(train_values,nt%lt) if nt%lt else None
    vt=_block_tables(test_data,lv);vr=_block_tables(test_data,nv%lv) if nv%lv else None
    rng=np.random.default_rng(seed);collected=[]
    for start in range(0,resamples,128):
        batch=min(128,resamples-start)
        a=rng.integers(0,nt,size=(batch,int(np.ceil(nt/lt))))
        b=rng.integers(0,nv,size=(batch,int(np.ceil(nv/lv))))
        ts,tc=_draw_totals(tt,tr,a,nt,lt);vs,vc=_draw_totals(vt,vr,b,nv,lv)
        means=np.divide(ts,tc,out=np.full_like(ts,np.nan),where=tc>0)
        days=vc[:,0]
        missing=((vs[:,1:]>1e-12)&~np.isfinite(means)).any(axis=1)
        numerator=vs[:,0]-np.nansum(vs[:,1:]*means,axis=1)
        draws=direction*np.divide(numerator,days,out=np.full(batch,np.nan),where=(days>0)&~missing)
        weight=np.divide(vs[:,1:],days[:,None],out=np.zeros_like(ts),where=days[:,None]>0)
        scale=np.divide(weight,tc/nt,out=np.zeros_like(ts),where=tc>0)
        train_blocks=tt[0][a[:,:nt//lt]]-np.nan_to_num(means)[:,None,:]*tt[1][a[:,:nt//lt]]
        train_scores=-direction*np.sum(train_blocks*scale[:,None,:],axis=2)
        test_blocks=vt[0][b[:,:nv//lv]]
        test_counts=vt[1][b[:,:nv//lv],0]
        test_scores=direction*(test_blocks[:,:,0]-np.sum(test_blocks[:,:,1:]*np.nan_to_num(means)[:,None,:],axis=2))-draws[:,None]*test_counts
        test_scores=np.divide(test_scores,(days/nv)[:,None],out=np.full_like(test_scores,np.nan),where=days[:,None]>0)
        variance=np.var(train_scores,axis=1,ddof=1)/(lt*nt)+np.var(test_scores,axis=1,ddof=1)/(lv*nv)
        se=np.sqrt(np.maximum(variance,0.))
        collected.append(np.divide(draws-estimate,se,out=np.full(batch,np.nan),where=(se>1e-14)&~missing))
    statistics=np.concatenate(collected);statistics=statistics[np.isfinite(statistics)]
    result=dict(mean=float(estimate),low=np.nan,high=np.nan,p=np.nan,n_dates=n_dates,
                n_train_dates=n_train,effective_resamples=len(statistics),std_error=standard_error)
    if len(statistics)>=resamples*.8:
        qlow,qhigh=np.quantile(statistics,[.025,.975])
        result.update(low=float(estimate-qhigh*standard_error),high=float(estimate-qlow*standard_error),
                      p=(1+int((statistics>=estimate/standard_error).sum()))/(len(statistics)+1))
    return result


def ratio_block_test(numerators,denominators,calendar=None,block_size=20,resamples=1000,seed=2026):
    """Bootstrap tổng sai số / tổng số nhãn; giữ nguyên trọng số theo NHÃN."""
    if block_size<1 or resamples<99:raise ValueError('block_size >=1 và resamples >=99')
    joined=pd.concat([numerators.rename('numerator'),denominators.rename('denominator')],axis=1).sort_index()
    if calendar is not None:joined=joined.reindex(pd.DatetimeIndex(calendar))
    joined=joined.fillna(0.)
    if (joined.denominator<0).any():raise ValueError('Số nhãn không thể âm')
    total=float(joined.denominator.sum());dates=int(joined.denominator.gt(0).sum())
    estimate=float(joined.numerator.sum()/total) if total else np.nan
    if total<30 or dates<20:
        return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=dates,effective_resamples=0)
    values=joined.to_numpy(dtype=float);n=len(values);length=min(block_size,n)
    if n//length<10:
        return dict(mean=estimate,low=np.nan,high=np.nan,p=np.nan,n_dates=dates,effective_resamples=0)
    tables=_block_tables(values,length);last=_block_tables(values,n%length) if n%length else None
    rng=np.random.default_rng(seed);collected=[]
    for offset in range(0,resamples,128):
        batch=min(128,resamples-offset);starts=rng.integers(0,n,size=(batch,int(np.ceil(n/length))))
        totals,_=_draw_totals(tables,last,starts,n,length)
        collected.append(np.divide(totals[:,0],totals[:,1],out=np.full(batch,np.nan),where=totals[:,1]>0))
    return _bootstrap_result(estimate,np.concatenate(collected),resamples,n_dates=dates)
