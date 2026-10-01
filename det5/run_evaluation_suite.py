#!/usr/bin/env python3
"""Run frozen generator -> blind detector -> evaluator over multiple seeds and aggregate results."""
import argparse, os, subprocess, sys
from pathlib import Path
import pandas as pd

def ci(s):
    s=pd.to_numeric(s,errors='coerce').dropna()
    return (s.mean(),s.quantile(.025),s.quantile(.975)) if len(s) else (float('nan'),)*3

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--generator',required=True); ap.add_argument('--seeds',type=int,default=20); ap.add_argument('--weeks',type=int,default=4); ap.add_argument('--out',default='evaluation_suite'); a=ap.parse_args()
    root=Path(a.out); root.mkdir(parents=True,exist_ok=True); here=Path(__file__).resolve().parent; allscores=[]; allp5=[]
    for seed in range(1,a.seeds+1):
        rd=root/f'seed_{seed:03d}'; run=rd/'run'; det=rd/'detector'; ev=rd/'evaluation'; rd.mkdir(exist_ok=True)
        subprocess.run([sys.executable,a.generator,'--out',str(run),'--seed',str(seed),'--weeks',str(a.weeks)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable,str(here/'blind_detector.py'),str(run),'--out',str(det)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable,str(here/'evaluate_detector.py'),str(run),str(det/'predictions.csv'),'--out',str(ev)],check=True,stdout=subprocess.DEVNULL)
        s=pd.read_csv(ev/'pattern_evaluation.csv'); s['seed']=seed; allscores.append(s); p=pd.read_csv(ev/'p5_rate_evaluation.csv'); p['seed']=seed; allp5.append(p)
    scores=pd.concat(allscores,ignore_index=True); scores.to_csv(root/'all_pattern_evaluations.csv',index=False); p5=pd.concat(allp5,ignore_index=True); p5.to_csv(root/'all_p5_evaluations.csv',index=False)
    rows=[]
    for pat,g in scores.groupby('pattern'):
        r={'pattern':pat,'evaluation_mode':g.evaluation_mode.iloc[0]}
        for col in ['sensitivity','PPV','F1','reference_positives','flagged']:
            mean,lo,hi=ci(g[col]); r[col+'_mean']=mean; r[col+'_p2_5']=lo; r[col+'_p97_5']=hi
        rows.append(r)
    summary=pd.DataFrame(rows); summary.to_csv(root/'aggregate_pattern_summary.csv',index=False)
    p5sum=[]
    for col in ['reference_forwarding_rate','detector_forwarding_rate','absolute_rate_error','set_sensitivity','set_PPV','set_F1']:
        mean,lo,hi=ci(p5[col]); p5sum.append({'metric':col,'mean':mean,'p2_5':lo,'p97_5':hi})
    pd.DataFrame(p5sum).to_csv(root/'aggregate_p5_summary.csv',index=False)
    print(summary.to_string(index=False)); print('\nP5\n'+pd.DataFrame(p5sum).to_string(index=False))
if __name__=='__main__': main()
