"""Repeated-seed validation harness for inbox_sim.py.

Runs the generator in memory across many independent seeds and summarizes whether
sampled outputs recover configured generator targets. This validates the generator;
it is NOT the metadata-only detector and is allowed to inspect ground truth.

Usage:
  python validate_generator.py --runs 100 --out generator_validation
"""
from __future__ import annotations
import argparse, copy, csv, json, math, os
from collections import Counter
import numpy as np
from inbox_sim import CONFIG, Sim


def mean_ci(x):
    a=np.asarray(x,dtype=float)
    return float(a.mean()), float(np.quantile(a,.025)), float(np.quantile(a,.975)), float(a.std(ddof=1)) if len(a)>1 else 0.0

def truth_rows(sim, pattern=None, planted=None, lookalike=None):
    rows=sim.truth
    if pattern is not None: rows=[r for r in rows if r.get('pattern')==pattern]
    if planted is not None: rows=[r for r in rows if int(r.get('planted',0))==planted]
    if lookalike is not None: rows=[r for r in rows if int(r.get('lookalike',0))==lookalike]
    return rows

def one_run(cfg):
    sim=Sim(cfg); sim.run()
    weekdays=sum(1 for i in range(cfg['weeks']*7) if (sim.start+__import__('datetime').timedelta(days=i)).weekday()<5)
    nprov=cfg['n_providers']
    # Initial thread messages, matching calibration_check intent.
    first={}
    for m in sorted(sim.messages,key=lambda z:z.created): first.setdefault(m.thread_id,m)
    wk=[m for m in first.values() if m.created.weekday()<5 and m.msg_type!='reply_to_patient']
    type_map={'patient_medical_advice_request':'portal_message'}
    volume={t:sum(type_map.get(m.msg_type,m.msg_type)==t for m in wk)/(nprov*weekdays) for t in cfg['daily_volume']}
    # Provider inbox arrivals: CREATED/FORWARDED targeting provider on weekdays.
    prov_arr=sum(e.event_type in ('CREATED','FORWARDED') and e.target_role=='provider' and e.ts.weekday()<5 for e in sim.events)/(nprov*weekdays)
    # Handling paths. PATH rows are generated for staff-routed messages; restrict to first message ids.
    first_ids={m.message_id for m in first.values()}
    paths=[r for r in truth_rows(sim,'PATH') if r['id'] in first_ids]
    notes=[str(r.get('note','')).replace('+extra_cycle','') for r in paths]
    pc=Counter(notes); denom=max(len(paths),1)
    path_share={k:pc[k]/denom for k in ['nonclinical_staff_reply','nonclinical_no_reply','provider_direct','provider_instructs_staff','provider_instructs_staff_then_provider']}
    # Planted patterns and denominators, mirroring calibration_check.py.
    sender_patient=sum(m.sender_role=='patient' for m in sim.messages)
    cc=sum(m.msg_type=='cc_message' for m in sim.messages)
    clinical_portal=len({m.thread_id for m in sim.messages if m.msg_type=='patient_medical_advice_request' and m.category in ('medical_question','medication_question','results_question')})
    results=sum(m.msg_type=='result' for m in sim.messages)
    allpaths=truth_rows(sim,'PATH')
    clin_paths=sum(not str(r.get('note','')).startswith('nonclinical') for r in allpaths)
    nonclin_paths=sum(str(r.get('note','')).startswith('nonclinical') for r in allpaths)
    den={'P1_thank_you':sender_patient,'P2_unread_cc':cc,'P3_extended_thread':clinical_portal,'P4_result_misrouted':results,'P7_pingpong':clin_paths,'P8_nonclinical_misrouted':nonclin_paths}
    plant={p:len(truth_rows(sim,p,planted=1))/max(d,1) for p,d in den.items()}
    # Patient concentration over entire panel.
    counts=Counter(m.patient for m in sim.messages if m.sender_role=='patient' and m.patient)
    panel=nprov*cfg['panel_size']; vals=sorted(counts.values(),reverse=True)+[0]*max(panel-len(counts),0)
    k=max(1,int(.05*panel)); top5=sum(vals[:k])/max(sum(vals),1)
    return {'volume':volume,'provider_arrivals':prov_arr,'paths':path_share,'planted':plant,'top5':top5,'n_messages':len(sim.messages),'n_events':len(sim.events)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--runs',type=int,default=100); ap.add_argument('--seed-start',type=int,default=1); ap.add_argument('--out',default='generator_validation'); ap.add_argument('--weeks',type=int); ap.add_argument('--providers',type=int); ap.add_argument('--config'); a=ap.parse_args()
    cfg=copy.deepcopy(CONFIG)
    if a.config:
        over=json.load(open(a.config))
        for k,v in over.items():
            if isinstance(v,dict) and isinstance(cfg.get(k),dict): cfg[k].update(v)
            else: cfg[k]=v
    if a.weeks is not None: cfg['weeks']=a.weeks
    if a.providers is not None: cfg['n_providers']=a.providers
    os.makedirs(a.out,exist_ok=True)
    rows=[]
    for i in range(a.runs):
        c=copy.deepcopy(cfg); c['seed']=a.seed_start+i
        r=one_run(c); r['seed']=c['seed']; rows.append(r)
        if (i+1)%10==0 or i==a.runs-1: print(f'{i+1}/{a.runs}')
    expected_paths={
      'nonclinical_staff_reply':cfg['p_nonclinical']*cfg['p_staff_reply_nonclinical'],
      'nonclinical_no_reply':cfg['p_nonclinical']*(1-cfg['p_staff_reply_nonclinical']),
      'provider_direct':(1-cfg['p_nonclinical'])*cfg['p_provider_direct'],
      'provider_instructs_staff':(1-cfg['p_nonclinical'])*(1-cfg['p_provider_direct'])*(1-cfg['p_provider_followup']),
      'provider_instructs_staff_then_provider':(1-cfg['p_nonclinical'])*(1-cfg['p_provider_direct'])*cfg['p_provider_followup']}
    expected_planted={'P1_thank_you':cfg['planted']['p1_thank_you'],'P2_unread_cc':cfg['planted']['p2_unread_cc'],'P3_extended_thread':cfg['planted']['p3_extended_thread'],'P4_result_misrouted':cfg['planted']['p4_result_misrouted'],'P7_pingpong':cfg['planted']['p7_pingpong_extra'],'P8_nonclinical_misrouted':cfg['planted']['p8_nonclinical_misrouted']}
    summary=[]
    def add(group,metric,target,vals):
        m,lo,hi,sd=mean_ci(vals); summary.append({'group':group,'metric':metric,'target':target,'mean':m,'p2.5':lo,'p97.5':hi,'sd':sd,'bias':m-target,'relative_bias':(m-target)/target if target else ''})
    for t,target in cfg['daily_volume'].items(): add('daily_volume',t,target,[r['volume'][t] for r in rows])
    add('benchmark','provider_inbox_arrivals',76.9,[r['provider_arrivals'] for r in rows])
    for k,target in expected_paths.items(): add('handling_path',k,target,[r['paths'][k] for r in rows])
    for k,target in expected_planted.items(): add('planted_rate',k,target,[r['planted'][k] for r in rows])
    add('benchmark','top5_patient_message_share',.528,[r['top5'] for r in rows])
    with open(os.path.join(a.out,'summary.csv'),'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=summary[0].keys()); w.writeheader(); w.writerows(summary)
    # compact markdown report
    lines=['# Generator repeated-seed validation','',f'Runs: {a.runs}; seeds {a.seed_start}-{a.seed_start+a.runs-1}; providers: {cfg["n_providers"]}; weeks/run: {cfg["weeks"]}.','', 'Intervals below are empirical 2.5th-97.5th percentiles across independent simulation runs, not confidence intervals for real-world parameters.','']
    for group in ['daily_volume','handling_path','planted_rate','benchmark']:
        lines += [f'## {group.replace("_"," ").title()}','', '| Metric | Target | Mean | 95% simulation interval | Bias |','|---|---:|---:|---:|---:|']
        for s in summary:
            if s['group']!=group: continue
            pct=group in ('handling_path','planted_rate') or s['metric']=='top5_patient_message_share'
            fmt=(lambda x:f'{x:.1%}') if pct else (lambda x:f'{x:.2f}')
            lines.append(f"| {s['metric']} | {fmt(s['target'])} | {fmt(s['mean'])} | {fmt(s['p2.5'])}–{fmt(s['p97.5'])} | {fmt(s['bias'])} |")
        lines.append('')
    lines += ['## Interpretation','', '- A generator target is behaving as intended when the repeated-run mean is close to the configured target; individual one-month runs may vary substantially for uncommon paths.', '- The Holmgren top-5% patient concentration benchmark is expected to be distorted in short simulations because most panel patients send no message during a four-week window. It is shown as a diagnostic benchmark, not a pass/fail generator target.', '- This harness reads planted ground truth and therefore must remain separate from the future metadata-only detector.','']
    open(os.path.join(a.out,'report.md'),'w').write('\n'.join(lines))
    json.dump({k:v for k,v in cfg.items() if k!='salt'},open(os.path.join(a.out,'config.json'),'w'),indent=2)
    print('Wrote',a.out)
if __name__=='__main__': main()
