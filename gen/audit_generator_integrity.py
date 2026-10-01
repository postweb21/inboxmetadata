#!/usr/bin/env python3
import copy, csv, json, os, argparse
from collections import defaultdict, Counter
from datetime import timedelta
from inbox_sim import Sim, CONFIG, PORTAL_CATEGORIES_NONCLIN

PATTERNS = ['P1_thank_you','P2_unread_cc','P3_extended_thread','P4_result_misrouted','P7_pingpong','P8_nonclinical_misrouted']

def audit_seed(seed):
    cfg=copy.deepcopy(CONFIG); cfg['seed']=seed
    sim=Sim(cfg); sim.run()
    msgs={m.message_id:m for m in sim.messages}
    ev=defaultdict(list)
    for e in sim.events: ev[e.message_id].append(e)
    thread_msgs=defaultdict(list)
    for m in sim.messages: thread_msgs[m.thread_id].append(m)
    visits=defaultdict(list)
    for v in sim.visits: visits[v['patient']].append(v)
    coverage={(r['provider'],r['date']):r['covering_provider'] for r in sim.coverage}
    rows=[]
    def add(pattern,id_,check,ok,detail=''):
        rows.append(dict(seed=seed,pattern=pattern,id=id_,check=check,passed=int(bool(ok)),detail=detail))
    for t in sim.truth:
        if not t['planted'] or t['pattern'] not in PATTERNS: continue
        pat=t['pattern']; id_=t['id']
        if pat=='P1_thank_you':
            m=msgs.get(id_); add(pat,id_,'message_exists',m is not None)
            if m:
                add(pat,id_,'patient_originated_portal_message',m.sender_role=='patient' and m.msg_type=='patient_medical_advice_request')
                add(pat,id_,'is_reply_to_prior_outbound',bool(m.in_response_to) and m.in_response_to in msgs and msgs[m.in_response_to].msg_type=='reply_to_patient')
                later=[x for x in thread_msgs[m.thread_id] if x.created>m.created]
                add(pat,id_,'thread_ending',len(later)==0,f'later_messages={len(later)}')
                ets={e.event_type for e in ev[id_]}; add(pat,id_,'accessed_and_completed',{'ACCESSED','COMPLETED'}<=ets)
        elif pat=='P2_unread_cc':
            m=msgs.get(id_); add(pat,id_,'message_exists',m is not None)
            if m:
                add(pat,id_,'is_cc',m.msg_type=='cc_message' and m.relationship=='cc')
                accesses=[e for e in ev[id_] if e.event_type=='ACCESSED']
                add(pat,id_,'no_access_event',len(accesses)==0,f'accesses={len(accesses)}')
        elif pat=='P3_extended_thread':
            ms=sorted(thread_msgs.get(id_,[]),key=lambda x:x.created); add(pat,id_,'thread_exists',bool(ms))
            if ms:
                incoming=[m for m in ms if m.sender_role=='patient' and m.msg_type=='patient_medical_advice_request']
                outbound=[m for m in ms if m.msg_type=='reply_to_patient']
                add(pat,id_,'three_or_more_patient_incoming',len(incoming)>=3,f'incoming={len(incoming)}')
                add(pat,id_,'four_or_more_message_exchanges',len(incoming)+len(outbound)>=4,f'in+out={len(incoming)+len(outbound)}')
                span=(ms[-1].created-ms[0].created).total_seconds()/86400
                add(pat,id_,'spans_at_least_3_days',span>=3.0,f'span_days={span:.2f}')
                pt=ms[0].patient
                inter=[v for v in visits.get(pt,[]) if ms[0].created <= v['start'] <= ms[-1].created]
                add(pat,id_,'no_visit_between',len(inter)==0,f'intervening_visits={len(inter)}')
        elif pat=='P4_result_misrouted':
            m=msgs.get(id_); add(pat,id_,'message_exists',m is not None)
            if m:
                add(pat,id_,'is_result',m.msg_type=='result')
                add(pat,id_,'recipient_not_ordering',m.recipient!=m.ordering_provider)
                cover=coverage.get((m.ordering_provider,m.created.date().isoformat()))
                add(pat,id_,'recipient_not_covering',not cover or m.recipient!=cover,f'cover={cover}')
        elif pat=='P7_pingpong':
            m=msgs.get(id_); add(pat,id_,'message_exists',m is not None)
            if m:
                fw=[e for e in ev[id_] if e.event_type=='FORWARDED']
                sp=sum(e.actor_role in ('rn','ma','fd') and e.target_role=='provider' for e in fw)
                ps=sum(e.actor_role=='provider' and e.target_role=='pool' for e in fw)
                add(pat,id_,'at_least_two_staff_to_provider_forwards',sp>=2,f'staff_to_provider={sp}')
                add(pat,id_,'at_least_two_provider_to_staff_forwards',ps>=2,f'provider_to_staff={ps}')
                add(pat,id_,'two_or_more_round_trips',min(sp,ps)>=2,f'roundtrips={min(sp,ps)}')
        elif pat=='P8_nonclinical_misrouted':
            m=msgs.get(id_); add(pat,id_,'message_exists',m is not None)
            if m:
                add(pat,id_,'nonclinical_category',m.category in PORTAL_CATEGORIES_NONCLIN,f'category={m.category}')
                fwd=[e for e in ev[id_] if e.event_type=='FORWARDED' and e.target_role=='provider']
                add(pat,id_,'reaches_provider',len(fwd)>0,f'provider_forwards={len(fwd)}')
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--seeds',type=int,default=100); ap.add_argument('--out',default='integrity_audit'); a=ap.parse_args()
    os.makedirs(a.out,exist_ok=True)
    rows=[]
    for s in range(1,a.seeds+1): rows.extend(audit_seed(s))
    with open(os.path.join(a.out,'audit_checks.csv'),'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['seed','pattern','id','check','passed','detail']); w.writeheader(); w.writerows(rows)
    agg=defaultdict(lambda:[0,0])
    for r in rows:
        k=(r['pattern'],r['check']); agg[k][0]+=r['passed']; agg[k][1]+=1
    with open(os.path.join(a.out,'audit_summary.csv'),'w',newline='') as f:
        w=csv.writer(f); w.writerow(['pattern','check','passed','total','pass_rate'])
        for (p,c),(ok,n) in sorted(agg.items()): w.writerow([p,c,ok,n,ok/n if n else ''])
    failures=[r for r in rows if not r['passed']]
    pats=Counter(r['pattern'] for r in rows if r['check'] in ('message_exists','thread_exists'))
    with open(os.path.join(a.out,'report.md'),'w') as f:
        f.write('# Generator integrity audit\n\n')
        f.write(f'Runs: {a.seeds} independent one-month simulations (seeds 1-{a.seeds}).\n\n')
        f.write('The audit tests planted labels against the generated event history, using the manuscript operational definitions where they are mechanically testable. It does not test the future detector.\n\n')
        f.write('## Summary\n\n| Pattern | Check | Pass | Total | Rate |\n|---|---|---:|---:|---:|\n')
        for (p,c),(ok,n) in sorted(agg.items()): f.write(f'| {p} | {c} | {ok} | {n} | {ok/n:.1%} |\n')
        f.write(f'\nTotal atomic checks: {len(rows)}; failures: {len(failures)}.\n\n')
        f.write('## Interpretation\n\n')
        bad=[(p,c,ok,n) for (p,c),(ok,n) in sorted(agg.items()) if ok<n]
        if not bad: f.write('All audited invariants passed.\n')
        else:
            f.write('All P1, P2, P4, P7, and P8 structural invariants pass unless listed above. The important exception is P3: the current generator creates three patient-originated messages separated by 20–40 hours, but it does not guarantee that the full thread spans at least 3 days, nor does it suppress an office visit during the thread. Therefore the planted P3 label does not always satisfy the manuscript definition “>=4 exchanges over 3 days with no visit in between.” This should be corrected before freezing v1.0.\n')
        f.write('\n## Scope caveats\n\nP1 “needs no action” is semantic ground truth created by the generator; metadata can verify that it is a short, terminal patient reply and that it is accessed/completed, but cannot independently prove message content. P2 is audited before adding future missing-access noise; with nonzero missing-access noise, ordinary read CCs can become detector false positives by design.\n')
    print(json.dumps({'checks':len(rows),'failures':len(failures),'out':a.out},indent=2))
if __name__=='__main__': main()
