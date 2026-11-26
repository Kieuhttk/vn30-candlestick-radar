"""MDE xấp xỉ từ SE/CI đã có, không phải observed power và không sửa kết quả chính."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from scipy.stats import norm
from _support import parent_report,output_folder,csv,finish,utf8
from analytics.multiple_testing import fdr_by


def thresholds(m=280,alpha=.05,resamples=39999):
    harmonic=sum(1/k for k in range(1,m+1));rank=np.arange(1,m+1)
    return pd.DataFrame({'rank':rank,'family':m,'alpha':alpha,
        'by_raw_critical':alpha*rank/(m*harmonic),'bootstrap_floor':1/(resamples+1)})


def analyze(table,m=280,alpha=.05,power=.8,resamples=39999,effects=(.25,.5,1.,2.)):
    critical=thresholds(m,alpha,resamples);rows=[];plans=[];zpower=norm.ppf(power)
    for row in table.to_dict('records'):
        if row['bias']=='neutral':continue
        for baseline in ['all','trend']:
            lo=row.get(baseline+'_low',np.nan);hi=row.get(baseline+'_high',np.nan)
            se_ci=(hi-lo)/(2*norm.ppf(.975)) if np.isfinite([lo,hi]).all() else np.nan
            saved=row.get(baseline+'_std_error',np.nan)
            common=dict(pattern=row['Mẫu hình'],horizon=row['Số phiên'],fee_bps=row['fee_bps'],baseline=baseline,
                raw_p=row.get(baseline+'_p'),se_saved=saved,se_ci_width=se_ci,
                ci_asymmetry=(hi+lo-2*row.get(baseline+'_mean',np.nan)))
            for label,se in [('ci_width',se_ci),('saved_se',saved)]:
                common['mde80_unadjusted_'+label+'_pct']=100*(norm.ppf(1-alpha)+zpower)*se
                common['mde80_by_rank1_'+label+'_pct']=100*(norm.ppf(1-critical.by_raw_critical.iloc[0])+zpower)*se
            common['status']='approximation_available' if np.isfinite(se_ci) and se_ci>0 else 'no_valid_interval'
            rows.append(common)
            if np.isfinite(se_ci) and se_ci>0:
                for effect in effects:
                    for family_label,a in [('unadjusted',alpha),('BY_rank1_isolated',critical.by_raw_critical.iloc[0])]:
                        plans.append(dict(pattern=common['pattern'],horizon=common['horizon'],fee_bps=common['fee_bps'],
                            baseline=baseline,effect_pct=effect,criterion=family_label,
                            normal_approx_power=float(norm.sf(norm.ppf(1-a)-effect/100/se_ci))))
    return pd.DataFrame(rows),pd.DataFrame(plans),critical


def family_diagnostics(table):
    rows=[]
    for fee,g in table.groupby('fee_bps'):
        for baseline in ['all','trend']:
            values=g.loc[g.bias.ne('neutral'),baseline+'_p'].dropna().to_numpy()
            if not len(values):continue
            for family in [len(values),70]:
                adjusted=fdr_by(values,n_tests=family)
                rows.append(dict(fee_bps=fee,baseline=baseline,finite_tests=len(values),diagnostic_family=family,
                    minimum_raw_p=values.min(),minimum_BY_q=adjusted.min(),n_q_below_05=int((adjusted<.05).sum()),
                    interpretation='diagnostic only; not a replacement for locked family 280'))
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',default='report/oos_verified');p.add_argument('--out',default='report/supplement_20261124/power')
    a=p.parse_args();source,m=parent_report(a.study);out=output_folder(a.out,source)
    table=pd.read_csv(source/'q2_oos_summary.csv')
    details,power,critical=analyze(table,m['planned_directional_family'],resamples=m['resamples'])
    csv(out,'mde_by_comparison.csv',details);csv(out,'hypothetical_power.csv',power);csv(out,'BY_rank_thresholds.csv',critical)
    csv(out,'family_diagnostics.csv',family_diagnostics(table))
    columns=[c for c in details if c.startswith('mde80')]
    grouped=details.groupby('horizon')[columns].median().reset_index()
    csv(out,'mde_median_by_horizon.csv',grouped)
    finish(out,'planning_MDE_normal_approximation',source,dict(alpha=.05,target_power=.8,
        family=m['planned_directional_family'],resamples=m['resamples'],
        cautions=['CI is bootstrap-t and can be asymmetric; width-to-SE is approximate',
        'BY rank-one threshold is sufficient for an isolated signal, not necessary at higher ranks',
        'No observed-effect post-hoc power; hypothetical effect sizes only','No MDE when the interval is unavailable']),__file__)
    print(grouped.to_string(index=False));print('Saved:',out)


if __name__=='__main__':utf8();main()
