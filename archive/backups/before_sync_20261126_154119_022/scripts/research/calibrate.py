"""DỮ LIỆU MÔ PHỎNG: random walk, kiểm tra null và positive control +3%."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
import argparse,json,hashlib,platform
import numpy as np
import pandas as pd
from analytics.radar import build_radar
from analytics.study import q2_tables
from analytics.setup_probability import wilson_interval


def random_walk(seed,days=650,symbols=6):
    rng=np.random.default_rng(seed);index=pd.bdate_range('2020-01-01',periods=days);frames={}
    for i in range(symbols):
        gap=rng.normal(0,.004,days);intraday=rng.normal(0,.012,days)
        close=100*np.exp(np.cumsum(gap+intraday));prior=np.r_[100,close[:-1]];opening=prior*np.exp(gap)
        spread=np.abs(rng.normal(.004,.002,days))
        frames[f'SIM{i}']=pd.DataFrame(dict(open=opening,high=np.maximum(opening,close)*(1+spread),low=np.minimum(opening,close)/(1+spread),close=close,volume=rng.lognormal(10,.2,days)),index=index)
    return frames


def inject(frames,events,effect=.03):
    output={}
    for symbol,f in frames.items():
        flags=np.zeros(len(f));index=f.index
        for day in events.loc[(events.symbol==symbol)&(events.name=='bullish_engulfing'),'date']:
            pos=index.get_loc(day)+1
            if pos<len(f):flags[pos]=1
        factor=(1+effect)**np.cumsum(flags);before=factor/(1+effect)**flags
        g=f.copy();g['open']=f.open*before;g['close']=f.close*factor
        g['high']=np.maximum(f.high*before,g[['open','close']].max(axis=1));g['low']=np.minimum(f.low*before,g[['open','close']].min(axis=1))
        output[symbol]=g
    return output



def oos_repetition(trial,days,symbols,horizons,resamples,seed_start=10000):
    from analytics.study import make_oos_protocol,training_fingerprint
    from analytics.event_study import fit_event_baselines
    from analytics.multiple_testing import fdr_by
    targets={'bullish_engulfing','bearish_engulfing'}
    frames=random_walk(seed_start+trial,days,symbols)
    asof=next(iter(frames.values())).index[-1]
    protocol,calendar=make_oos_protocol(frames,asof,horizons=horizons,fees=(20,))
    cut=pd.Timestamp(protocol['train_end']);start=pd.Timestamp(protocol['test_start'])
    null=build_radar(frames,asof,market_days=calendar)
    frozen_hash=training_fingerprint(frames,None,cut)
    keys={(symbol,name,h) for symbol in frames for name in targets for h in horizons}
    model=fit_event_baselines(frames,cut,horizons=horizons,fee_bps=20,market_days=calendar,keys=keys)
    future_signals=null.events[null.events.date>=start]
    rows=[];family=len(targets)*len(horizons)*2
    for arm,data in [('random_walk_null',frames),('injected_3pct',inject(frames,future_signals))]:
        if training_fingerprint(data,None,cut)!=frozen_hash:raise AssertionError('Positive control đã sửa train')
        radar=null if arm=='random_walk_null' else build_radar(data,asof,market_days=calendar)
        events=radar.events[(radar.events.date>=start)&radar.events.name.isin(targets)]
        table,_,_=q2_tables(data,events,asof,horizons=horizons,fees=(20,),resamples=resamples,
                           baselines=model,market_days=calendar,evaluation_start=start)
        table=table[table['Mẫu hình'].isin(['Bao trùm tăng','Bao trùm giảm'])].copy()
        q=fdr_by(np.column_stack([table.all_p,table.trend_p]).reshape(-1),n_tests=family).reshape(-1,2)
        for position,r in enumerate(table.itertuples(index=False,name=None)):
            item=table.iloc[position]
            for j,label in enumerate(('all','trend')):
                rows.append(dict(trial=trial,seed=seed_start+trial,arm=arm,pattern=item['Mẫu hình'],
                    horizon=int(item['Số phiên']),baseline=label,p=item[label+'_p'],q=q[position,j],
                    n=int(item['Đủ dữ liệu']),family=family))
    return rows


def run_oos_calibration(args,out):
    horizons=tuple(int(x) for x in args.horizons.split(','))
    if not horizons or any(h<1 for h in horizons) or len(set(horizons))!=len(horizons):raise ValueError('Kỳ hạn không hợp lệ')
    days=args.days or 1300;symbols=args.symbols or 12;rows=[]
    # Chụp mã NGAY TRƯỚC chạy, không lấy hash từ file có thể vừa sửa khi đang chạy.
    sources=[Path(__file__)]+list((ROOT/'src/analytics').glob('*.py'))+list((ROOT/'src/finance').glob('*.py'))
    source_bytes={str(p.relative_to(ROOT)):p.read_bytes() for p in sources}
    for name,data in source_bytes.items():
        dest=out/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    source_hashes={name:hashlib.sha256(data).hexdigest() for name,data in source_bytes.items()}
    for trial in range(args.repetitions):
        rows.extend(oos_repetition(trial,days,symbols,horizons,args.resamples,args.seed_start))
        pd.DataFrame(rows).to_csv(out/'replications.csv',index=False,encoding='utf-8-sig')
        print(f'Mô phỏng OOS {trial+1}/{args.repetitions}',flush=True)
    result=pd.DataFrame(rows);summary=[]
    for keys,g in result.groupby(['arm','pattern','horizon','baseline']):
        for metric in ('p','q'):
            values=g[metric].dropna();k=int(values.lt(.05).sum());low,high=wilson_interval(k,len(values))
            summary.append(dict(zip(['arm','pattern','horizon','baseline'],keys),metric=metric,
                valid=len(values),rejected=k,rate=k/len(values) if len(values) else np.nan,ci_low=low,ci_high=high))
    pd.DataFrame(summary).to_csv(out/'calibration_summary.csv',index=False,encoding='utf-8-sig')
    family=[]
    for arm,g in result.groupby('arm'):
        flags=g.groupby('trial').q.agg(lambda s:bool(s.lt(.05).any()))
        valid=g.groupby('trial').q.agg(lambda s:bool(s.notna().any()))
        flags=flags[valid];k=int(flags.sum());low,high=wilson_interval(k,len(flags))
        family.append(dict(arm=arm,valid=len(flags),any_rejection=k,rate=k/len(flags) if len(flags) else np.nan,ci_low=low,ci_high=high))
    pd.DataFrame(family).to_csv(out/'family_summary.csv',index=False,encoding='utf-8-sig')
    design=dict(simulated=True,mode='chronological_holdout_two_sample_studentized_bootstrap',seed_start=args.seed_start,
        repetitions=args.repetitions,resamples=args.resamples,days=days,symbols=symbols,
        targets=['bullish_engulfing','bearish_engulfing'],horizons=horizons,fees_bps=[20],
        family=2*len(horizons)*2,train_fraction=.7,block_rule='max(20,5*h)',
        min_calendar_blocks=10,python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
        positive_control='inject +3% after ORIGINAL bullish engulfing signals in TEST only; unchanged TRAIN; rerun detection',
        caveats=['end-to-end on two prespecified patterns, not all 19 patterns or market validity',
                 'replications with insufficient observations excluded and denominators reported',
                 'BY rejection rate need not equal 5%; Monte Carlo uncertainty remains',
                 'positive control is artificial, not a tradable strategy'],
        source_hashes=source_hashes)
    (out/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
    print(pd.DataFrame(family).to_string(index=False))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repetitions',type=int,default=100);ap.add_argument('--resamples',type=int,default=3999);ap.add_argument('--out');ap.add_argument('--oos',action='store_true');ap.add_argument('--days',type=int);ap.add_argument('--symbols',type=int);ap.add_argument('--horizons',default='1,3,5,10,20')
    ap.add_argument('--seed-start',type=int,default=10000)
    args=ap.parse_args();out=Path(args.out or ('report/calibration_oos' if args.oos else 'report/calibration'));out=out if out.is_absolute() else ROOT/out;out.mkdir(parents=True,exist_ok=True)
    if (out/'replications.csv').exists():ap.error('Thư mục đã có mô phỏng; chọn --out mới để giữ nguyên bằng chứng cũ')
    if args.repetitions < 1 or args.resamples < 99:ap.error('--repetitions >= 1 và --resamples >= 99')
    if args.oos:
        run_oos_calibration(args,out);return
    rows=[]
    for trial in range(args.repetitions):
        frames=random_walk(10000+trial);asof=next(iter(frames.values())).index[-1];base=build_radar(frames,asof)
        for arm,data in [('random_walk_null',frames),('injected_3pct',inject(frames,base.events))]:
            radar=base if arm=='random_walk_null' else build_radar(data,asof)
            table,_,family=q2_tables(data,radar.events,asof,horizons=(1,),fees=(20,),resamples=args.resamples)
            target=table[table['Mẫu hình']=='Bao trùm tăng'].iloc[0]
            rows.append(dict(trial=trial,seed=10000+trial,arm=arm,p=target.all_p,p_trend=target.trend_p,q=target.all_q_fixed,q_trend=target.trend_q_fixed,n=target['Đủ dữ liệu'],family=family,
                             any_q=bool(((table.all_q_fixed<.05)|(table.trend_q_fixed<.05)).any())))
        if (trial+1)%10==0:print('Mô phỏng',trial+1,'/',args.repetitions,flush=True)
        pd.DataFrame(rows).to_csv(out/'replications.csv',index=False,encoding='utf-8-sig')
    result=pd.DataFrame(rows);summary=[]
    for arm,g in result.groupby('arm'):
        for col in ['p','p_trend','q','q_trend']:
            values=g[col].dropna();count=int((values<.05).sum());low,high=wilson_interval(count,len(values))
            summary.append(dict(arm=arm,metric=col,valid=len(values),rejected=count,rate=count/len(values) if len(values) else None,ci_low=low,ci_high=high))
    pd.DataFrame(summary).to_csv(out/'calibration_summary.csv',index=False,encoding='utf-8-sig')
    sources=[Path(__file__)]+list((ROOT/'src/analytics').glob('*.py'))+list((ROOT/'src/finance').glob('*.py'))
    (out/'design.json').write_text(json.dumps(dict(simulated=True,seed_start=10000,repetitions=args.repetitions,resamples=args.resamples,days=650,symbols=6,block_size=20,
        python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},primary='bullish_engulfing, h=1, 20 bps',
        null='independent Gaussian log random walk with independent overnight and intraday innovations',
        control='inject +3% into next-day close after ORIGINAL null engulfing labels; propagate price level, then rerun detection and study',
        caveats=['positive control not realistic market or online strategy','h=1 calibration does not validate h=3/5/10/20','raw p nominal .05; BY conservative, not expected to reject exactly .05','small Monte Carlo sample has broad uncertainty']),ensure_ascii=False,indent=2),encoding='utf-8')
    print(pd.DataFrame(summary).to_string(index=False))


if __name__=='__main__':
    # CLI tiếng Việt dùng UTF-8 cả khi stdout/stderr bị chuyển vào pipe trên Windows.
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
