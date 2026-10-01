"""
calibration_check.py - Verify a simulation run against its target parameters.

This checks the GENERATOR (it reads ground_truth.csv for path and pattern labels).
It is not the analysis pipeline, which must never read ground_truth.csv.

Usage: python calibration_check.py <run_dir> [--validate-fhir N]
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--validate-fhir", type=int, default=300,
                    help="resources per type to validate (0 = skip, -1 = all)")
    a = ap.parse_args()
    d = a.run_dir
    cfg = json.load(open(f"{d}/run_config.json"))
    msgs = pd.read_csv(f"{d}/messages.csv", parse_dates=["created"])
    ev = pd.read_csv(f"{d}/events.csv", parse_dates=["timestamp"])
    gt = pd.read_csv(f"{d}/ground_truth.csv")
    n_prov = cfg["n_providers"]
    days = pd.date_range(cfg["start_date"], periods=cfg["weeks"] * 7, freq="D")
    n_weekdays = int((days.weekday < 5).sum())
    out = []
    p = out.append

    # 1. Volume by type per provider per weekday (initial messages only)
    initial = msgs[msgs.in_response_to.isna() & (msgs.msg_type != "reply_to_patient")]
    initial = initial.assign(weekday=initial.created.dt.weekday < 5)
    first_in_thread = initial.sort_values("created").drop_duplicates("thread_id")
    wk = first_in_thread[first_in_thread.weekday]
    targets = cfg["daily_volume"]
    type_map = {"patient_medical_advice_request": "portal_message"}
    wk_types = wk.msg_type.map(lambda t: type_map.get(t, t))
    p("## 1. New inbox items per provider per weekday\n")
    p("| Type | Target | Simulated |\n| --- | --- | --- |")
    tot_t = tot_s = 0
    for t, target in targets.items():
        sim = (wk_types == t).sum() / (n_prov * n_weekdays)
        tot_t += target; tot_s += sim
        p(f"| {t} | {target:.1f} | {sim:.1f} |")
    p(f"| **total new items** | **{tot_t:.1f}** | **{tot_s:.1f}** |")

    # Provider-facing notifications: items arriving in a provider inbox (created to or forwarded to)
    prov_in = ev[((ev.event_type == "CREATED") | (ev.event_type == "FORWARDED")) & (ev.target_role == "provider")]
    prov_in = prov_in[prov_in.timestamp.dt.weekday < 5]
    p(f"\nProvider-inbox arrivals (new + forwarded) per provider per weekday: "
      f"**{len(prov_in) / (n_prov * n_weekdays):.1f}** (Murphy 2016: 76.9)\n")

    # 2. Handling paths for staff-routed messages
    paths_all = gt[gt.pattern == "PATH"]
    staff_routed_ids = set(paths_all.id)
    first_ids = set(msgs.sort_values("created").drop_duplicates("thread_id").message_id)
    paths = paths_all[paths_all.id.isin(first_ids)]   # initial message of each thread
    pr = paths.note.str.replace(r"\+extra_cycle", "", regex=True).value_counts(normalize=True)
    expected = {
        "nonclinical_staff_reply": cfg["p_nonclinical"] * cfg["p_staff_reply_nonclinical"],
        "nonclinical_no_reply": cfg["p_nonclinical"] * (1 - cfg["p_staff_reply_nonclinical"]),
        "provider_direct": (1 - cfg["p_nonclinical"]) * cfg["p_provider_direct"],
        "provider_instructs_staff": (1 - cfg["p_nonclinical"]) * (1 - cfg["p_provider_direct"]) * (1 - cfg["p_provider_followup"]),
        "provider_instructs_staff_then_provider": (1 - cfg["p_nonclinical"]) * (1 - cfg["p_provider_direct"]) * cfg["p_provider_followup"],
    }
    p("## 2. Handling paths, staff-routed messages\n")
    p(f"n = {len(paths)} new staff-routed threads (portal + calls); {len(paths_all) - len(paths)} follow-up messages excluded.\n")
    p("| Path | Target | Simulated |\n| --- | --- | --- |")
    for k, v in expected.items():
        p(f"| {k} | {v:.1%} | {pr.get(k, 0):.1%} |")
    p("\nPath shares are sampled; expect a few points of variation in a 1-month, 3-provider run.\n")

    # 3. Comparison with Tang et al.
    sr_ev = ev[ev.message_id.isin(staff_routed_ids)]
    contacted = sr_ev[sr_ev.event_type.isin(["REPLIED", "PHONE_CONTACT"])]
    prov_contact = contacted[contacted.actor_role == "provider"].message_id.nunique() / len(paths_all)
    any_contact = contacted.message_id.nunique() / len(paths_all)
    p("## 3. Comparison with Tang et al. 2026\n")
    p("| Measure | Simulated | Tang et al. |\n| --- | --- | --- |")
    p(f"| Provider personally contacts patient | {prov_contact:.1%} | 32.0% (written replies) |")
    p(f"| Any care team response | {any_contact:.1%} | 77.5% (written replies) |")

    # 4. Planted patterns
    planted = gt[(gt.planted == 1) & (gt.pattern.str.startswith("P"))]
    look = gt[gt.lookalike == 1]
    denoms = {
        "P1_thank_you": ("patient-sent messages", (msgs.sender_role == "patient").sum()),
        "P2_unread_cc": ("CC messages", (msgs.msg_type == "cc_message").sum()),
        "P3_extended_thread": ("clinical portal threads",
                               msgs[(msgs.msg_type == "patient_medical_advice_request") &
                                    msgs.portal_category.isin(["medical_question", "medication_question", "results_question"])].thread_id.nunique()),
        "P4_result_misrouted": ("results", (msgs.msg_type == "result").sum()),
        "P7_pingpong": ("clinical staff-routed messages",
                        paths_all[~paths_all.note.str.startswith("nonclinical")].shape[0]),
        "P8_nonclinical_misrouted": ("nonclinical staff-routed messages",
                                     paths_all[paths_all.note.str.startswith("nonclinical")].shape[0]),
    }
    cfg_rate = {"P1_thank_you": cfg["planted"]["p1_thank_you"], "P2_unread_cc": cfg["planted"]["p2_unread_cc"],
                "P3_extended_thread": cfg["planted"]["p3_extended_thread"],
                "P4_result_misrouted": cfg["planted"]["p4_result_misrouted"],
                "P7_pingpong": cfg["planted"]["p7_pingpong_extra"],
                "P8_nonclinical_misrouted": cfg["planted"]["p8_nonclinical_misrouted"]}
    p("## 4. Planted patterns\n")
    p("| Pattern | Denominator | Planted n | Planted rate | Config rate | Look-alikes / baseline |\n| --- | --- | --- | --- | --- | --- |")
    for pat, (dname, dn) in denoms.items():
        n = (planted.pattern == pat).sum()
        other = gt[(gt.pattern == pat) & (gt.planted == 0)].shape[0]
        p(f"| {pat} | {dname} ({dn}) | {n} | {n / max(dn, 1):.1%} | {cfg_rate[pat]:.1%} | {other} |")
    p("\nP7 baseline = provider follow-up after a staff reply (expected 4.4% of staff-routed).")

    # 5. Patient concentration
    pm = msgs[msgs.sender_role == "patient"]
    counts = pm.patient_hash.value_counts()
    panel_total = n_prov * cfg["panel_size"]
    full = np.concatenate([counts.values, np.zeros(panel_total - len(counts))])
    full = np.sort(full)[::-1]
    top5 = full[: int(0.05 * panel_total)].sum() / full.sum()
    p("\n## 5. Concentration of patient messages\n")
    p(f"Top 5% of panel patients sent **{top5:.1%}** of patient messages "
      f"(Holmgren 2026: 52.8% over a longer window). Short runs overstate this because "
      f"few patients message in {cfg['weeks']} weeks.")

    # 6. Turnaround
    comp = ev[ev.event_type == "COMPLETED"].groupby("message_id").timestamp.max()
    created = msgs.set_index("message_id").created
    ta = (comp - created.reindex(comp.index)).dt.total_seconds() / 3600
    sr_ta = ta[ta.index.isin(staff_routed_ids)]
    p("\n## 6. Time to completion (hours)\n")
    p(f"All completed items: median {ta.median():.1f} h, 90th pct {ta.quantile(.9):.1f} h. "
      f"Staff-routed messages: median {sr_ta.median():.1f} h, 90th pct {sr_ta.quantile(.9):.1f} h.")

    # 7. FHIR validation
    if a.validate_fhir != 0:
        from fhir.resources.R4B import get_fhir_model_class
        p("\n## 7. FHIR validation (fhir.resources R4B models)\n")
        p("| Resource | Checked | Errors |\n| --- | --- | --- |")
        for rt in ["Patient", "Practitioner", "Communication", "Task", "AuditEvent", "Encounter"]:
            cls = get_fhir_model_class(rt)
            n = err = 0
            first_err = None
            with open(f"{d}/fhir/{rt}.ndjson") as f:
                for line in f:
                    if a.validate_fhir > 0 and n >= a.validate_fhir:
                        break
                    n += 1
                    try:
                        cls.model_validate(json.loads(line)) if hasattr(cls, "model_validate") else cls.parse_raw(line)
                    except Exception as e:  # noqa
                        err += 1
                        first_err = first_err or str(e)[:300]
            p(f"| {rt} | {n} | {err} |")
            if first_err:
                p(f"\n    first error: {first_err}\n")

    text = "\n".join(out)
    open(f"{d}/calibration_report.md", "w").write("# Calibration report\n\n" + text + "\n")
    print(text)


if __name__ == "__main__":
    main()
