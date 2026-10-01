#!/usr/bin/env python3
"""Independent evaluator for the inbox metadata detector.
May read ground_truth.csv and run_config.json. Detector must not.
"""
import argparse, json, os
import numpy as np
import pandas as pd
MAP={'P1_low_value_terminal':'P1_thank_you','P4_result_nonordering':'P4_result_misrouted','P7_pingpong':'P7_pingpong','P8_nonclinical_misrouted':'P8_nonclinical_misrouted'}
NONCLIN={"appointment_request","billing_question","cancellation"}; STAFF={'rn','ma','fd'}

def load(run,predfile):
    m=pd.read_csv(os.path.join(run,'messages.csv'),dtype=str).fillna(''); e=pd.read_csv(os.path.join(run,'events.csv'),dtype=str).fillna(''); v=pd.read_csv(os.path.join(run,'visits.csv'),dtype=str).fillna('')
    gt=pd.read_csv(os.path.join(run,'ground_truth.csv'),dtype=str).fillna(''); pr=pd.read_csv(predfile,dtype=str).fillna('')
    m['created']=pd.to_datetime(m.created); e['timestamp']=pd.to_datetime(e.timestamp); v['start']=pd.to_datetime(v.start)
    return m,e,v,gt,pr

def metrics(pred,pos):
    tp=len(pred&pos); fp=len(pred-pos); fn=len(pos-pred); sens=tp/(tp+fn) if tp+fn else np.nan; ppv=tp/(tp+fp) if tp+fp else np.nan; f1=2*sens*ppv/(sens+ppv) if sens+ppv else np.nan
    return tp,fp,fn,sens,ppv,f1

def reference_p2(m,e,days=14):
    end=max(m.created.max(),e.timestamp.max() if len(e) else m.created.max()); out=set(); evaluable=0
    ev={k:g for k,g in e.groupby('message_id')}
    for _,x in m[m.relationship.eq('cc')].iterrows():
        if end<x.created+pd.Timedelta(days=days): continue
        evaluable+=1; z=ev.get(x.message_id,pd.DataFrame()); acc=z[z.event_type.eq('ACCESSED')] if len(z) else z
        if not(len(acc) and acc.timestamp.min()<=x.created+pd.Timedelta(days=days)): out.add(x.message_id)
    return out,evaluable

def reference_p3(m,v):
    out=set()
    for tid,g in m.groupby('thread_id'):
        r=g[g.sender_role.eq('patient')|g.msg_type.eq('reply_to_patient')].sort_values('created')
        if len(r)<4: continue
        if (r.created.max()-r.created.min()).total_seconds()/86400<3: continue
        vv=v[v.patient_hash.eq(g.patient_hash.iloc[0])]
        if not len(vv[(vv.start>=r.created.min())&(vv.start<=r.created.max())]): out.add(tid)
    return out

def reference_p5(m,e):
    # Denominator: all patient-originated portal messages delivered to a staff pool (the dataset's staff-routed patient-message cohort).
    # Do NOT pre-exclude nonclinical portal categories; that split is part of what P5 measures.
    mask=(m.sender_role.eq('patient')) & (m.recipient_role.eq('pool')) & (m.msg_type.eq('patient_medical_advice_request'))
    eligible=set(m.loc[mask,'message_id'])
    z=e[(e.event_type.eq('FORWARDED')) & e.actor_role.isin(STAFF) & e.target_role.eq('provider')]
    forwarded=set(z.message_id) & eligible
    clinical=set(m.loc[mask & (~m.portal_category.isin(NONCLIN)),'message_id'])
    nonclinical=set(m.loc[mask & m.portal_category.isin(NONCLIN),'message_id'])
    return eligible,forwarded,clinical,nonclinical

def main(run,predfile,out):
    m,e,v,gt,pr=load(run,predfile); os.makedirs(out,exist_ok=True)
    rows=[]
    for dp,gp in MAP.items():
        pred=set(pr.loc[pr.pattern.eq(dp),'id']); z=gt[gt.pattern.eq(gp)]; pos=set(z.loc[z.planted.isin(['1','true','True']),'id'])
        met=metrics(pred,pos); rows.append([dp,'planted_detection',*met,len(pos),len(pred)])
    p2,evaluable=reference_p2(m,e); p2pred=set(pr.loc[pr.pattern.eq('P2_unread_cc'),'id']); met=metrics(p2pred,p2)
    rows.append(['P2_unread_cc','definition_derived_validation',*met,len(p2),len(p2pred)])
    p3=reference_p3(m,v); p3pred=set(pr.loc[pr.pattern.eq('P3_extended_thread'),'id']); met=metrics(p3pred,p3)
    rows.append(['P3_extended_thread','definition_reconstruction_check',*met,len(p3),len(p3pred)])
    cols=['pattern','evaluation_mode','TP','FP','FN','sensitivity','PPV','F1','reference_positives','flagged']
    score=pd.DataFrame(rows,columns=cols); score.to_csv(os.path.join(out,'pattern_evaluation.csv'),index=False)
    elig,fwd,clinical,nonclinical=reference_p5(m,e); p5pred=set(pr.loc[pr.pattern.eq('P5_staff_to_provider_forward'),'id']); met=metrics(p5pred,fwd)
    config={}
    cp=os.path.join(run,'run_config.json')
    if os.path.exists(cp):
        with open(cp) as f: config=json.load(f)
    generating_rate=config.get('p_nonclinical'); generating_forward_rate=(1-generating_rate) if generating_rate is not None else np.nan
    # Config p_nonclinical is the routing split among staff-routed portal messages, not necessarily the exact denominator below; report separately.
    p5=pd.DataFrame([{
        'eligible_initial_patient_staff_pool_messages':len(elig),'reference_forwarded':len(fwd),'detector_forwarded':len(p5pred),
        'eligible_clinical':len(clinical),'clinical_forwarded':len(fwd & clinical),'clinical_forwarding_rate':len(fwd & clinical)/len(clinical) if clinical else np.nan,
        'eligible_nonclinical':len(nonclinical),'nonclinical_forwarded':len(fwd & nonclinical),'nonclinical_forwarding_rate':len(fwd & nonclinical)/len(nonclinical) if nonclinical else np.nan,
        'reference_forwarding_rate':len(fwd)/len(elig) if elig else np.nan,'detector_forwarding_rate':len(p5pred)/len(elig) if elig else np.nan,
        'absolute_rate_error':abs(len(p5pred)-len(fwd))/len(elig) if elig else np.nan,
        'set_sensitivity':met[3],'set_PPV':met[4],'set_F1':met[5],
        'config_implied_clinical_share_note':generating_forward_rate
    }]); p5.to_csv(os.path.join(out,'p5_rate_evaluation.csv'),index=False)
    p6file=os.path.join(os.path.dirname(predfile),'p6_messaging_visit_ratio.csv'); p6sum=[]
    if os.path.exists(p6file):
        p6=pd.read_csv(p6file); vals=pd.to_numeric(p6.threads_per_visit,errors='coerce').dropna(); p6sum=[{'patients':len(p6),'patients_with_defined_ratio':len(vals),'median_threads_per_visit':vals.median() if len(vals) else np.nan,'p25':vals.quantile(.25) if len(vals) else np.nan,'p75':vals.quantile(.75) if len(vals) else np.nan}]
    pd.DataFrame(p6sum).to_csv(os.path.join(out,'p6_descriptive_summary.csv'),index=False)
    meta=pd.DataFrame([{'p2_evaluable_cc':evaluable,'p2_reference_positive':len(p2),'p3_reference_positive':len(p3)}]); meta.to_csv(os.path.join(out,'descriptive_reference_counts.csv'),index=False)
    print(score.to_string(index=False)); print('\nP5 rate evaluation:\n'+p5.to_string(index=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('predictions'); ap.add_argument('--out',default='evaluation'); a=ap.parse_args(); main(a.run,a.predictions,a.out)
