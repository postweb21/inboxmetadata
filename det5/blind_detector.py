#!/usr/bin/env python3
"""Metadata-only detector for synthetic inbox workflow study.
Never reads ground_truth.csv or run_config.json.
"""
import argparse, os
import pandas as pd
NONCLIN={"appointment_request","billing_question","cancellation"}
STAFF={'rn','ma','fd'}

def load(run):
    m=pd.read_csv(os.path.join(run,'messages.csv'),dtype=str).fillna('')
    e=pd.read_csv(os.path.join(run,'events.csv'),dtype=str).fillna('')
    v=pd.read_csv(os.path.join(run,'visits.csv'),dtype=str).fillna('')
    c=pd.read_csv(os.path.join(run,'coverage.csv'),dtype=str).fillna('')
    m['created']=pd.to_datetime(m.created); m['length_chars']=pd.to_numeric(m.length_chars,errors='coerce')
    e['timestamp']=pd.to_datetime(e.timestamp); v['start']=pd.to_datetime(v.start)
    return m,e,v,c

def detect(run,out,cc_days=14,p1_max_chars=40):
    m,e,v,c=load(run); rows=[]
    end=max(m.created.max(),e.timestamp.max() if len(e) else m.created.max())
    ev_by_mid={k:g.sort_values('timestamp') for k,g in e.groupby('message_id')}
    thread_last=m.groupby('thread_id').created.max().to_dict(); msg_index=m.set_index('message_id')
    # P1
    for _,x in m.iterrows():
        if x.sender_role!='patient' or x.length_chars>p1_max_chars or not x.in_response_to: continue
        if x.created!=thread_last.get(x.thread_id): continue
        parent=msg_index.loc[x.in_response_to] if x.in_response_to in msg_index.index else None
        if parent is None or parent.msg_type!='reply_to_patient': continue
        ev=ev_by_mid.get(x.message_id,pd.DataFrame()); types=set(ev.event_type) if len(ev) else set()
        if 'ACCESSED' in types and 'COMPLETED' in types and not(types & {'REPLIED','FORWARDED','PHONE_CONTACT'}):
            rows.append(('message',x.message_id,'P1_low_value_terminal','short terminal patient reply after care-team response'))
    # P2
    for _,x in m[m.relationship.eq('cc')].iterrows():
        if end < x.created+pd.Timedelta(days=cc_days): continue
        ev=ev_by_mid.get(x.message_id,pd.DataFrame()); acc=ev[ev.event_type.eq('ACCESSED')] if len(ev) else ev
        timely=len(acc) and acc.timestamp.min()<=x.created+pd.Timedelta(days=cc_days)
        if not timely: rows.append(('message',x.message_id,'P2_unread_cc',f'no access within {cc_days} days'))
    # P3
    for tid,g in m.groupby('thread_id'):
        g=g.sort_values('created'); relevant=g[g.sender_role.eq('patient')|g.msg_type.eq('reply_to_patient')]
        if len(relevant)<4: continue
        span=(relevant.created.max()-relevant.created.min()).total_seconds()/86400
        if span<3: continue
        ph=g.patient_hash.iloc[0]; vv=v[v.patient_hash.eq(ph)]
        between=vv[(vv.start>=relevant.created.min())&(vv.start<=relevant.created.max())]
        if len(between)==0: rows.append(('thread',tid,'P3_extended_thread',f'{len(relevant)} exchanges over {span:.1f} days; no intervening visit'))
    # P4
    cov={(r.provider_hash,r.date):r.covering_provider_hash for _,r in c.iterrows()}
    for _,x in m[m.msg_type.eq('result')].iterrows():
        if not x.ordering_provider_hash: continue
        cover=cov.get((x.ordering_provider_hash,x.created.date().isoformat()),'')
        if x.recipient_hash not in {x.ordering_provider_hash,cover}:
            rows.append(('message',x.message_id,'P4_result_nonordering','recipient neither ordering nor documented covering provider'))
    # P5: initial patient-originated portal/call messages delivered to a staff pool.
    # IMPORTANT: retain both clinical and nonclinical messages in the denominator.
    # The clinical/nonclinical split is descriptive and must not define eligibility.
        p5_detail=[]
    eligible=m[(m.sender_role.eq('patient')) & (m.recipient_role.eq('pool')) & (m.msg_type.eq('patient_medical_advice_request'))]
    for _,x in eligible.iterrows():
        ev=ev_by_mid.get(x.message_id,pd.DataFrame())
        if not len(ev): continue
        sf=ev[(ev.event_type.eq('FORWARDED'))&ev.actor_role.isin(STAFF)&ev.target_role.eq('provider')]
        if not len(sf): continue
        ft=sf.timestamp.min(); pre=ev[ev.timestamp<=ft]
        chart=((pre.event_type=='CHART_ACCESS')).any()
        acc=pre[(pre.event_type=='ACCESSED')&pre.actor_role.isin(STAFF)]
        dwell=(ft-acc.timestamp.min()).total_seconds()/60 if len(acc) else None
        rows.append(('message',x.message_id,'P5_staff_to_provider_forward','initial patient message to staff pool subsequently forwarded to provider'))
        stratum='nonclinical' if x.portal_category in NONCLIN else 'clinical'
        p5_detail.append([x.message_id,stratum,x.portal_category,dwell,bool(chart)])
    # P7
    for mid,ev in e[e.event_type.eq('FORWARDED')].groupby('message_id'):
        sp=((ev.actor_role.isin(STAFF))&ev.target_role.eq('provider')).sum(); ps=(ev.actor_role.eq('provider')&ev.target_role.eq('pool')).sum()
        if sp>=2 and ps>=2: rows.append(('message',mid,'P7_pingpong',f'{sp} staff→provider and {ps} provider→pool forwards'))
    # P8
    for _,x in m[m.portal_category.isin(NONCLIN)].iterrows():
        ev=ev_by_mid.get(x.message_id,pd.DataFrame())
        if len(ev) and ((ev.event_type.eq('FORWARDED'))&ev.target_role.eq('provider')).any():
            rows.append(('message',x.message_id,'P8_nonclinical_misrouted','nonclinical category forwarded to provider'))
    pred=pd.DataFrame(rows,columns=['level','id','pattern','detector_note']).drop_duplicates(['level','id','pattern'])
    os.makedirs(out,exist_ok=True); pred.to_csv(os.path.join(out,'predictions.csv'),index=False)
    pd.DataFrame(p5_detail,columns=['message_id','clinical_stratum','portal_category','staff_dwell_minutes','chart_activity_before_forward']).to_csv(os.path.join(out,'p5_forwarding_detail.csv'),index=False)
    threads=m[m.sender_role.eq('patient')].groupby('patient_hash').thread_id.nunique().rename('message_threads')
    visits=v.groupby('patient_hash').visit_id.nunique().rename('completed_visits')
    p6=pd.concat([threads,visits],axis=1).fillna(0); p6['threads_per_visit']=p6.message_threads/p6.completed_visits.replace(0,pd.NA)
    p6.reset_index().to_csv(os.path.join(out,'p6_messaging_visit_ratio.csv'),index=False)
    summary=pred.groupby('pattern').size().rename('flagged').reset_index(); summary.to_csv(os.path.join(out,'summary.csv'),index=False)
    return pred,summary
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('--out',default='detector_output'); a=ap.parse_args(); p,s=detect(a.run,a.out); print(s.to_string(index=False))
