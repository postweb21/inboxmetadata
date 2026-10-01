"""
inbox_sim.py - Synthetic EHR inbox metadata generator (primary care).

Generates a message-level event log for a simulated primary care practice,
with workflow patterns planted at known rates and a separate ground-truth file.

Outputs (in --out):
  messages.csv        one row per inbox message (metadata only, no content)
  events.csv          one row per event (created, accessed, forwarded, replied, ...)
  visits.csv          completed visits (for thread/visit patterns)
  coverage.csv        provider absence/coverage records
  ground_truth.csv    planted pattern labels  -> NEVER read by the analysis pipeline
  fhir/*.ndjson       FHIR R4 resources (Patient, Practitioner, Communication,
                      Task, AuditEvent, Encounter)
  run_config.json     exact configuration and seed used

All identifiers are pseudonymous and salted-hashed on output.
Parameter sources are noted in CONFIG comments:
  [pub]    published value (see paper Table S1)
  [expert] expert-informed assumption (paper Table S2)
  [fill]   assumption used to fill the remainder of published total volume
  [model]  modeling choice
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, time

import numpy as np

# ----------------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------------
CONFIG = {
    "seed": 42,
    "salt": "change-me-per-release",
    "start_date": "2026-01-05",          # a Monday
    "weeks": 4,
    "n_providers": 3,                    # [model] >=2 needed for results-routing pattern
    "panel_size": 1800,                  # [model] patients per provider
    "staff": {"rn": 2, "ma": 2, "fd": 2},  # [model] staff users per pool

    # Patient messaging propensity: lognormal sigma chosen so the top 5% of
    # patients hold 52.8% of expected messages [pub: Holmgren 2026].
    # Top-q share for lognormal = 1 - Phi(z_{1-q} - sigma) -> sigma ~= 1.715
    "patient_propensity_sigma": 1.715,

    # Daily volumes per provider per weekday (Poisson means)
    "daily_volume": {
        "portal_message": 3.2,    # [pub] 16/week, Holmgren 2025
        "patient_call": 4.8,      # [pub] 24/week, Holmgren 2025
        "result": 15.5,           # [pub] Murphy 2016
        "rx_renewal": 5.0,        # [expert]
        "referral_notice": 2.0,   # [expert]
        "prior_auth": 1.0,        # [expert]
        "staff_message": 7.0,     # [fill]
        "cc_message": 10.0,       # [fill]
        "order_to_sign": 10.0,    # [fill]
        "system_notice": 18.0,    # [fill] fills total toward Murphy 2016 (76.9/day)
    },
    # Weekend multipliers [model]
    "weekend_factor": {"portal_message": 0.4, "result": 0.2, "system_notice": 0.5},

    "visits_per_day": 16,         # [model] ~Akbar 2021 encounter counts

    # Handling tree for staff-routed messages (portal messages, patient calls)
    "p_nonclinical": 0.35,             # [expert] billing/scheduling/cancellation
    "p_staff_reply_nonclinical": 0.80, # [pub] Tang 2026 scheduling threads 80.2%
    "p_provider_direct": 0.32,         # [expert] of forwarded clinical messages
    "p_provider_followup": 0.10,       # [expert] of provider-instructed messages
    "p_triage_before_forward": 0.0,    # [expert] 0 = all forwards are direct
                                       #  (user setting); raise to create 5a vs 5b

    # Baseline behaviors [model]
    "p_patient_followup": 0.15,        # patient writes again after a reply
    "p_cc_late_read": 0.05,            # look-alike: CC read after >14 days
    "coverage_days_per_provider": 1,   # look-alike: results to covering provider

    # Planted patterns (rates) - vary these in the scenario grid
    "planted": {
        "p1_thank_you": 0.04,        # share of patient messages that are thank-yous
        "p2_unread_cc": 0.25,        # share of CCs never accessed
        "p3_extended_thread": 0.05,  # share of clinical portal threads extended
        "p4_result_misrouted": 0.03, # share of results to non-ordering provider
        "p7_pingpong_extra": 0.03,   # share of clinical staff-routed msgs with extra cycle
        "p8_nonclinical_misrouted": 0.05,  # share of nonclinical msgs sent to provider
    },

    # Dwell times: (median minutes, lognormal sigma) [model]
    "dwell": {
        "fd_pickup": (60, 1.0), "rn_pickup": (90, 1.0), "ma_pickup": (90, 1.0),
        "staff_direct_forward": (3, 0.6), "staff_triage_forward": (12, 0.6),
        "provider_pickup": (240, 1.2), "provider_act": (3, 0.7),
        "provider_phone": (10, 0.5), "staff_reply": (8, 0.7),
        "provider_followup": (1440, 0.6), "patient_followup": (720, 1.0),
        "result_pickup": (300, 1.1), "info_pickup": (600, 1.2),
        "cc_pickup": (1440, 1.5), "staff_msg_pickup": (240, 1.1),
        "order_pickup": (480, 1.1), "quick_done": (1, 0.5),
    },

    # Work windows [model]
    "staff_hours": (8, 17),        # weekdays only
    "provider_hours": (7, 21),     # any day

    # Noise
    "noise": {
        "missing_access_rate": 0.0,   # drop share of ACCESSED events
        "timestamp_jitter_min": 2.0,  # +/- minutes
        "category_mislabel_rate": 0.0,
    },
}

PORTAL_CATEGORIES_NONCLIN = ["appointment_request", "billing_question", "cancellation"]
PORTAL_CATEGORIES_CLIN = ["medical_question", "medication_question", "results_question"]


# ----------------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------------
@dataclass
class Message:
    message_id: str
    thread_id: str
    patient: str | None
    msg_type: str
    category: str
    sender: str
    sender_role: str
    recipient: str
    recipient_role: str
    relationship: str            # primary | cc | pool
    created: datetime
    length: int
    ordering_provider: str | None = None
    in_response_to: str | None = None


@dataclass
class Event:
    event_id: str
    message_id: str
    thread_id: str
    patient: str | None
    event_type: str
    actor: str
    actor_role: str
    target: str | None
    target_role: str | None
    ts: datetime
    encounter_id: str | None = None


class Sim:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg["seed"])
        self.messages: list[Message] = []
        self.events: list[Event] = []
        self.visits: list[dict] = []
        self.coverage: list[dict] = []
        self.truth: list[dict] = []
        self.encounters: list[dict] = []
        self._ids = {}
        self.start = datetime.fromisoformat(cfg["start_date"])
        self.end = self.start + timedelta(weeks=cfg["weeks"])
        self._setup_people()

    # ---- ids ---------------------------------------------------------------
    def nid(self, prefix: str) -> str:
        self._ids[prefix] = self._ids.get(prefix, 0) + 1
        return f"{prefix}{self._ids[prefix]:07d}"

    # ---- people ------------------------------------------------------------
    def _setup_people(self):
        c = self.cfg
        self.providers = [f"PRV{i+1:03d}" for i in range(c["n_providers"])]
        self.staff = {role: [f"{role.upper()}{i+1:03d}" for i in range(n)]
                      for role, n in c["staff"].items()}
        self.pools = {"rn": "POOL_RN", "ma": "POOL_MA", "fd": "POOL_FD"}
        self.panels = {}
        self.propensity = {}
        sigma = c["patient_propensity_sigma"]
        for p in self.providers:
            pats = [f"PAT{p[3:]}{j+1:05d}" for j in range(c["panel_size"])]
            w = self.rng.lognormal(0, sigma, size=len(pats))
            self.panels[p] = pats
            self.propensity[p] = w / w.sum()
        self.pcp_of = {pt: p for p, pats in self.panels.items() for pt in pats}
        # coverage: each provider absent some weekdays, covered by the next provider
        days = self._weekdays()
        for i, p in enumerate(self.providers):
            k = min(c["coverage_days_per_provider"], len(days))
            chosen = self.rng.choice(len(days), size=k, replace=False)
            cover = self.providers[(i + 1) % len(self.providers)]
            for d in sorted(chosen):
                self.coverage.append({"provider": p, "date": days[d].isoformat(),
                                      "covering_provider": cover})
        self.absent = {(r["provider"], r["date"]): r["covering_provider"] for r in self.coverage}

    def _weekdays(self) -> list[date]:
        out, d = [], self.start.date()
        while d < self.end.date():
            if d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
        return out

    # ---- random helpers ------------------------------------------------------
    def dwell(self, key: str) -> timedelta:
        med, sig = self.cfg["dwell"][key]
        return timedelta(minutes=float(self.rng.lognormal(math.log(med), sig)))

    def in_window(self, t: datetime, role: str) -> datetime:
        """Push t into the actor's working window."""
        if role in ("patient", "system"):
            return t
        if role == "provider":
            h0, h1 = self.cfg["provider_hours"]
            weekdays_only = False
        else:
            h0, h1 = self.cfg["staff_hours"]
            weekdays_only = True
        for _ in range(10):
            if weekdays_only and t.weekday() >= 5:
                t = datetime.combine(t.date() + timedelta(days=7 - t.weekday()), time(h0)) \
                    + timedelta(minutes=float(self.rng.uniform(0, 45)))
                continue
            if t.hour < h0:
                t = datetime.combine(t.date(), time(h0)) + timedelta(minutes=float(self.rng.uniform(0, 45)))
                continue
            if t.hour >= h1:
                t = datetime.combine(t.date() + timedelta(days=1), time(h0)) \
                    + timedelta(minutes=float(self.rng.uniform(0, 45)))
                continue
            return t
        return t

    def after(self, t: datetime, key: str, role: str) -> datetime:
        return self.in_window(t + self.dwell(key), role)

    def pick_staff(self, role: str) -> str:
        return str(self.rng.choice(self.staff[role]))

    def pick_patient(self, provider: str) -> str:
        pats = self.panels[provider]
        return pats[int(self.rng.choice(len(pats), p=self.propensity[provider]))]

    def arrival(self, d: date, kind: str) -> datetime:
        if kind == "patient":      # portal: mostly daytime/evening
            h = float(np.clip(self.rng.normal(14, 4), 0, 23.99))
        elif kind == "call":
            h = float(self.rng.uniform(8, 17))
        elif kind == "lab":
            h = float(np.clip(self.rng.normal(12, 4), 5, 22))
        elif kind == "office":
            h = float(self.rng.uniform(8, 17.5))
        else:
            h = float(self.rng.uniform(0, 24))
        return datetime.combine(d, time(0)) + timedelta(hours=h)

    # ---- recording ------------------------------------------------------------
    def new_message(self, **kw) -> Message:
        m = Message(message_id=self.nid("MSG"), **kw)
        self.messages.append(m)
        self.event(m, "CREATED", m.sender, m.sender_role, m.recipient, m.recipient_role, m.created)
        return m

    def event(self, m: Message, etype, actor, actor_role, target, target_role, ts, enc=None):
        self.events.append(Event(self.nid("EVT"), m.message_id, m.thread_id, m.patient, etype,
                                 actor, actor_role, target, target_role, ts, enc))

    def label(self, level, id_, pattern, planted=True, lookalike=False, note=""):
        self.truth.append({"level": level, "id": id_, "pattern": pattern,
                           "planted": int(planted), "lookalike": int(lookalike), "note": note})

    def patient_reply_msg(self, thread_id, patient, sender, sender_role, t, parent, provider):
        """An outbound message to the patient (staff or provider reply)."""
        m = self.new_message(thread_id=thread_id, patient=patient, msg_type="reply_to_patient",
                             category="reply", sender=sender, sender_role=sender_role,
                             recipient=patient, recipient_role="patient", relationship="primary",
                             created=t, length=int(self.rng.integers(80, 900)),
                             ordering_provider=None, in_response_to=parent.message_id)
        return m

    # ------------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------------
    def run(self):
        c = self.cfg

        # Generate the complete visit schedule first. This lets Pattern 3 be
        # planted only in intervals without an intervening office visit, rather
        # than deleting or rescheduling visits after a message thread exists.
        d = self.start.date()
        while d < self.end.date():
            if d.weekday() < 5:
                for p in self.providers:
                    self._visits(d, p)
            d += timedelta(days=1)

        # Generate inbox traffic against that fixed visit schedule.
        d = self.start.date()
        while d < self.end.date():
            weekday = d.weekday() < 5
            for p in self.providers:
                for kind, mean in c["daily_volume"].items():
                    if not weekday:
                        mean = mean * c["weekend_factor"].get(kind, 0.0)
                    for _ in range(int(self.rng.poisson(mean))):
                        getattr(self, f"_gen_{kind}")(d, p)
            d += timedelta(days=1)
        self._apply_noise()
        self.messages.sort(key=lambda m: m.created)
        self.events.sort(key=lambda e: e.ts)

    def _visits(self, d, p):
        pats = self.panels[p]
        w = np.sqrt(self.propensity[p]); w = w / w.sum()
        for _ in range(int(self.rng.poisson(self.cfg["visits_per_day"]))):
            pt = pats[int(self.rng.choice(len(pats), p=w))]
            t = datetime.combine(d, time(8)) + timedelta(minutes=float(self.rng.uniform(0, 540)))
            self.visits.append({"visit_id": self.nid("VIS"), "patient": pt, "provider": p,
                                "start": t, "type": "office"})

    # ---- staff-routed: portal messages and patient calls --------------------
    def _gen_portal_message(self, d, p):
        pt = self.pick_patient(p)
        t = self.arrival(d, "patient")
        self._staff_routed(pt, p, t, channel="portal", thread_id=self.nid("THR"))

    def _gen_patient_call(self, d, p):
        pt = self.pick_patient(p)
        t = self.arrival(d, "call")
        self._staff_routed(pt, p, t, channel="call", thread_id=self.nid("THR"))

    def _staff_routed(self, pt, p, t, channel, thread_id, category=None, extended=False,
                      exchange_no=1):
        c, pl = self.cfg, self.cfg["planted"]
        nonclin = category in PORTAL_CATEGORIES_NONCLIN if category else \
            self.rng.random() < c["p_nonclinical"]
        if category is None:
            category = str(self.rng.choice(PORTAL_CATEGORIES_NONCLIN if nonclin
                                           else PORTAL_CATEGORIES_CLIN))
        pool_role = "fd" if nonclin else "rn"
        pool = self.pools[pool_role]
        msg_type = "patient_medical_advice_request" if channel == "portal" else "patient_call"
        sender, sender_role = (pt, "patient") if channel == "portal" else \
            (self.pick_staff("fd"), "fd")   # calls are documented by front desk
        m = self.new_message(thread_id=thread_id, patient=pt, msg_type=msg_type, category=category,
                             sender=sender, sender_role=sender_role, recipient=pool,
                             recipient_role="pool", relationship="pool", created=t,
                             length=int(self.rng.lognormal(math.log(250), 0.7)))
        staff = self.pick_staff(pool_role)
        ta = self.after(t, f"{pool_role}_pickup", "staff")
        self.event(m, "ACCESSED", staff, pool_role, None, None, ta)

        if nonclin:
            if self.rng.random() < pl["p8_nonclinical_misrouted"]:
                self.label("message", m.message_id, "P8_nonclinical_misrouted")
                tf = self.after(ta, "staff_direct_forward", "staff")
                self.event(m, "FORWARDED", staff, pool_role, p, "provider", tf)
                tp = self.after(tf, "provider_pickup", "provider")
                self.event(m, "ACCESSED", p, "provider", None, None, tp)
                tb = self.after(tp, "provider_act", "provider")
                self.event(m, "FORWARDED", p, "provider", pool, "pool", tb)
                ta = self.after(tb, "fd_pickup", "staff")
                self.event(m, "ACCESSED", staff, pool_role, None, None, ta)
            tr = self.after(ta, "staff_reply", "staff")
            if self.rng.random() < c["p_staff_reply_nonclinical"]:
                last = self._outbound(m, staff, pool_role, tr, channel, p)
            else:
                last = None
            self.event(m, "COMPLETED", staff, pool_role, None, None, tr)
            path = "nonclinical_staff_reply" if last else "nonclinical_no_reply"
            self._maybe_thank_you(m, last, p)
            self.label("message", m.message_id, "PATH", planted=False, note=path)
            return

        # clinical: forward to provider
        triage = self.rng.random() < c["p_triage_before_forward"]
        if triage:
            tc = self.after(ta, "quick_done", "staff")
            self.event(m, "CHART_ACCESS", staff, pool_role, None, None, tc)
            tf = self.after(tc, "staff_triage_forward", "staff")
        else:
            tf = self.after(ta, "staff_direct_forward", "staff")
        self.event(m, "FORWARDED", staff, pool_role, p, "provider", tf)
        self.label("message", m.message_id, "P5_forward_type", planted=False,
                   note="triaged" if triage else "direct")
        self.event(m, "COMPLETED", staff, pool_role, None, None, tf)

        # P7 is drawn only within the provider-instructs branch, scaled so the
        # planted share of ALL clinical staff-routed messages equals p7.
        direct = self.rng.random() < c["p_provider_direct"]
        p7_cond = min(1.0, pl["p7_pingpong_extra"] / max(1e-9, 1 - c["p_provider_direct"]))
        extra_cycle = (not direct) and self.rng.random() < p7_cond
        tp = self.after(tf, "provider_pickup", "provider")
        self.event(m, "ACCESSED", p, "provider", None, None, tp)
        last_out = None
        if direct:
            tr = self.after(tp, "provider_act", "provider")
            last_out = self._outbound(m, p, "provider", tr, channel, p)
            self.event(m, "COMPLETED", p, "provider", None, None, tr)
            path = "provider_direct"
        else:
            # provider instructs staff
            ti = self.after(tp, "provider_act", "provider")
            self.event(m, "FORWARDED", p, "provider", pool, "pool", ti)
            self.event(m, "COMPLETED", p, "provider", None, None, ti)
            staff2 = self.pick_staff(pool_role)
            ts = self.after(ti, "rn_pickup", "staff")
            self.event(m, "ACCESSED", staff2, pool_role, None, None, ts)
            if extra_cycle:
                # staff sends it back with a question -> provider -> staff again
                self.label("message", m.message_id, "P7_pingpong")
                tq = self.after(ts, "staff_direct_forward", "staff")
                self.event(m, "FORWARDED", staff2, pool_role, p, "provider", tq)
                tp2 = self.after(tq, "provider_pickup", "provider")
                self.event(m, "ACCESSED", p, "provider", None, None, tp2)
                ti2 = self.after(tp2, "provider_act", "provider")
                self.event(m, "FORWARDED", p, "provider", pool, "pool", ti2)
                ts = self.after(ti2, "rn_pickup", "staff")
                self.event(m, "ACCESSED", staff2, pool_role, None, None, ts)
            tr = self.after(ts, "staff_reply", "staff")
            last_out = self._outbound(m, staff2, pool_role, tr, channel, p)
            self.event(m, "COMPLETED", staff2, pool_role, None, None, tr)
            path = "provider_instructs_staff"
            if self.rng.random() < c["p_provider_followup"]:
                tfu = self.after(tr, "provider_followup", "provider")
                last_out = self._outbound(m, p, "provider", tfu, channel, p)
                path = "provider_instructs_staff_then_provider"
                self.label("message", m.message_id, "P7_pingpong", planted=False,
                           note="baseline provider follow-up after staff reply")
        if extra_cycle:
            path += "+extra_cycle"
        self.label("message", m.message_id, "PATH", planted=False, note=path)

        # thread continuation (portal only)
        if channel == "portal":
            if exchange_no == 1 and not extended and self.rng.random() < self.cfg["planted"]["p3_extended_thread"]:
                # P3 represents prolonged asynchronous management without an
                # intervening office visit. Visits are generated first, so only
                # plant P3 when the patient's upcoming 14-day interval is visit-free.
                # Fourteen days is deliberately conservative relative to the >=3-day
                # thread definition and avoids modifying the visit schedule.
                window_end = t + timedelta(days=14)
                has_intervening_visit = any(
                    v["patient"] == pt and t <= v["start"] <= window_end
                    for v in self.visits
                )
                if not has_intervening_visit:
                    extended = True
                    self.label("thread", thread_id, "P3_extended_thread")
            if extended and exchange_no < 3:
                tn = last_out.created + timedelta(hours=float(self.rng.uniform(36, 48)))
                self._staff_routed(pt, p, tn, "portal", thread_id, category, True, exchange_no + 1)
                return
            if not extended and exchange_no == 1 and self.rng.random() < c["p_patient_followup"]:
                tn = last_out.created + self.dwell("patient_followup")
                self._staff_routed(pt, p, tn, "portal", thread_id, category, False, exchange_no + 1)
                return
        self._maybe_thank_you(m, last_out, p)

    def _outbound(self, m, actor, role, t, channel, p):
        """Reply to patient: portal message or phone encounter."""
        if channel == "portal":
            out = self.patient_reply_msg(m.thread_id, m.patient, actor, role, t, m, p)
            self.event(m, "REPLIED", actor, role, m.patient, "patient", t)
            return out
        enc = self.nid("ENC")
        self.encounters.append({"encounter_id": enc, "patient": m.patient, "actor": actor,
                                "actor_role": role, "start": t, "type": "telephone",
                                "thread_id": m.thread_id})
        self.event(m, "PHONE_CONTACT", actor, role, m.patient, "patient", t, enc)
        return Message(message_id=enc, thread_id=m.thread_id, patient=m.patient,
                       msg_type="phone", category="phone", sender=actor, sender_role=role,
                       recipient=m.patient, recipient_role="patient", relationship="primary",
                       created=t, length=0)

    def _maybe_thank_you(self, m, last_out, p):
        """Pattern 1: thread-ending thank-you after a portal reply."""
        if last_out is None or last_out.msg_type != "reply_to_patient":
            return
        # convert target share of patient messages into a per-reply probability (~approx.)
        prob = self.cfg["planted"]["p1_thank_you"] / max(1e-9, 1 - self.cfg["planted"]["p1_thank_you"]) * 1.1
        if self.rng.random() >= min(prob, 0.9):
            return
        t = last_out.created + timedelta(minutes=float(self.rng.lognormal(math.log(90), 1.0)))
        to_provider = last_out.sender_role == "provider"
        rcpt, rrole, rel = (p, "provider", "primary") if to_provider else (self.pools["rn"], "pool", "pool")
        ty = self.new_message(thread_id=m.thread_id, patient=m.patient,
                              msg_type="patient_medical_advice_request", category=m.category,
                              sender=m.patient, sender_role="patient", recipient=rcpt,
                              recipient_role=rrole, relationship=rel, created=t,
                              length=int(self.rng.integers(5, 40)),
                              in_response_to=last_out.message_id)
        actor, arole = (p, "provider") if to_provider else (self.pick_staff("rn"), "rn")
        tk = "provider_pickup" if to_provider else "rn_pickup"
        ta = self.after(t, tk, "provider" if to_provider else "staff")
        self.event(ty, "ACCESSED", actor, arole, None, None, ta)
        self.event(ty, "COMPLETED", actor, arole, None, None, ta + self.dwell("quick_done"))
        self.label("message", ty.message_id, "P1_thank_you")

    # ---- direct-to-provider types ---------------------------------------------
    def _direct(self, d, p, msg_type, arrival_kind, pickup, act="quick_done",
                sender=None, sender_role="system", relationship="primary", patient=True,
                category="n/a", ordering=None, recipient=None):
        pt = self.pick_patient(p) if patient else None
        t = self.arrival(d, arrival_kind)
        rcpt = recipient or p
        m = self.new_message(thread_id=self.nid("THR"), patient=pt, msg_type=msg_type,
                             category=category, sender=sender or "SYSTEM", sender_role=sender_role,
                             recipient=rcpt, recipient_role="provider", relationship=relationship,
                             created=t, length=int(self.rng.lognormal(math.log(300), 0.8)),
                             ordering_provider=ordering)
        return m, t

    def _work(self, m, t, actor, pickup, act="quick_done"):
        ta = self.after(t, pickup, "provider")
        self.event(m, "ACCESSED", actor, "provider", None, None, ta)
        tc = self.after(ta, act, "provider")
        self.event(m, "COMPLETED", actor, "provider", None, None, tc)
        return tc

    def _gen_result(self, d, p):
        c = self.cfg
        m, t = self._direct(d, p, "result", "lab", "result_pickup", ordering=p)
        recipient = p
        key = (p, t.date().isoformat())
        if key in self.absent:
            recipient = self.absent[key]
            self.label("message", m.message_id, "P4_result_misrouted", planted=False,
                       lookalike=True, note="covering provider during absence")
        elif len(self.providers) > 1 and self.rng.random() < c["planted"]["p4_result_misrouted"]:
            others = [x for x in self.providers if x != p]
            recipient = str(self.rng.choice(others))
            self.label("message", m.message_id, "P4_result_misrouted")
        m.recipient = recipient
        self.events[-1].target = recipient  # fix CREATED target
        self._work(m, t, recipient, "result_pickup")

    def _gen_rx_renewal(self, d, p):
        m, t = self._direct(d, p, "rx_renewal", "office", "provider_pickup",
                            sender="PHARMACY", sender_role="external")
        self._work(m, t, p, "provider_pickup")

    def _gen_referral_notice(self, d, p):
        m, t = self._direct(d, p, "referral_notice", "office", "info_pickup")
        self._work(m, t, p, "info_pickup")

    def _gen_prior_auth(self, d, p):
        m, t = self._direct(d, p, "prior_auth", "office", "info_pickup",
                            sender="PAYER", sender_role="external")
        self._work(m, t, p, "info_pickup", act="provider_act")

    def _gen_staff_message(self, d, p):
        role = str(self.rng.choice(["rn", "ma", "fd"]))
        s = self.pick_staff(role)
        m, t = self._direct(d, p, "staff_message", "office", "staff_msg_pickup",
                            sender=s, sender_role=role)
        tc = self._work(m, t, p, "staff_msg_pickup", act="provider_act")
        self.event(m, "FORWARDED", p, "provider", self.pools[role], "pool", tc)

    def _gen_order_to_sign(self, d, p):
        m, t = self._direct(d, p, "order_to_sign", "office", "order_pickup")
        self._work(m, t, p, "order_pickup")

    def _gen_system_notice(self, d, p):
        m, t = self._direct(d, p, "system_notice", "other", "info_pickup", patient=True)
        self._work(m, t, p, "info_pickup")

    def _gen_cc_message(self, d, p):
        other = [x for x in self.providers if x != p] or [p]
        author = str(self.rng.choice(other + ["EXTERNAL_CLINICIAN"]))
        m, t = self._direct(d, p, "cc_message", "office", "cc_pickup", sender=author,
                            sender_role="provider" if author.startswith("PRV") else "external",
                            relationship="cc")
        if self.rng.random() < self.cfg["planted"]["p2_unread_cc"]:
            self.label("message", m.message_id, "P2_unread_cc")
            return  # never accessed
        if self.rng.random() < self.cfg["p_cc_late_read"]:
            ta = self.in_window(t + timedelta(days=float(self.rng.uniform(15, 25))), "provider")
            self.label("message", m.message_id, "P2_unread_cc", planted=False, lookalike=True,
                       note="read after >14 days")
            self.event(m, "ACCESSED", p, "provider", None, None, ta)
            self.event(m, "COMPLETED", p, "provider", None, None, ta + self.dwell("quick_done"))
            return
        self._work(m, t, p, "cc_pickup")

    # ---- noise ------------------------------------------------------------------
    def _apply_noise(self):
        n = self.cfg["noise"]
        if n["missing_access_rate"] > 0:
            keep = [e for e in self.events if not (e.event_type == "ACCESSED"
                    and self.rng.random() < n["missing_access_rate"])]
            self.events = keep
        j = n["timestamp_jitter_min"]
        if j > 0:
            last = {}
            for e in self.events:          # generation order is chronological per message
                if e.event_type != "CREATED":
                    e.ts = e.ts + timedelta(minutes=float(self.rng.uniform(-j, j)))
                if e.message_id in last and e.ts < last[e.message_id]:
                    e.ts = last[e.message_id] + timedelta(seconds=1)
                last[e.message_id] = e.ts
        if n["category_mislabel_rate"] > 0:
            for m in self.messages:
                if m.category in PORTAL_CATEGORIES_CLIN + PORTAL_CATEGORIES_NONCLIN and \
                        self.rng.random() < n["category_mislabel_rate"]:
                    m.category = str(self.rng.choice(PORTAL_CATEGORIES_CLIN + PORTAL_CATEGORIES_NONCLIN))

    # ------------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------------
    def h(self, x):
        if x is None or x in ("SYSTEM", "PHARMACY", "PAYER", "EXTERNAL_CLINICIAN") or x.startswith("POOL_"):
            return x
        return hashlib.sha256((self.cfg["salt"] + x).encode()).hexdigest()[:16]

    def write(self, out):
        os.makedirs(out, exist_ok=True)
        H = self.h
        ts = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S")
        with open(f"{out}/messages.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["message_id", "thread_id", "patient_hash", "msg_type", "portal_category",
                        "sender_hash", "sender_role", "recipient_hash", "recipient_role",
                        "relationship", "created", "length_chars", "ordering_provider_hash",
                        "in_response_to"])
            for m in self.messages:
                w.writerow([m.message_id, m.thread_id, H(m.patient), m.msg_type, m.category,
                            H(m.sender), m.sender_role, H(m.recipient), m.recipient_role,
                            m.relationship, ts(m.created), m.length, H(m.ordering_provider),
                            m.in_response_to or ""])
        with open(f"{out}/events.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["event_id", "message_id", "thread_id", "patient_hash", "event_type",
                        "actor_hash", "actor_role", "target_hash", "target_role", "timestamp",
                        "encounter_id"])
            for e in self.events:
                w.writerow([e.event_id, e.message_id, e.thread_id, H(e.patient), e.event_type,
                            H(e.actor), e.actor_role, H(e.target), e.target_role or "",
                            ts(e.ts), e.encounter_id or ""])
        with open(f"{out}/visits.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["visit_id", "patient_hash", "provider_hash", "start", "type"])
            for v in self.visits:
                w.writerow([v["visit_id"], H(v["patient"]), H(v["provider"]), ts(v["start"]), v["type"]])
        with open(f"{out}/coverage.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["provider_hash", "date", "covering_provider_hash"])
            for r in self.coverage:
                w.writerow([H(r["provider"]), r["date"], H(r["covering_provider"])])
        with open(f"{out}/ground_truth.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["level", "id", "pattern", "planted", "lookalike", "note"], lineterminator="\n")
            w.writeheader()
            w.writerows(self.truth)
        with open(f"{out}/run_config.json", "w") as f:
            cfg = copy.deepcopy(self.cfg)
            cfg["salt"] = "<redacted>"
            json.dump(cfg, f, indent=2, default=str)
        self.write_fhir(f"{out}/fhir")

    def write_fhir(self, out):
        os.makedirs(out, exist_ok=True)
        H = self.h
        iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S") + "-08:00"
        ref = lambda kind, x: {"reference": f"{kind}/{H(x)}"} if x else None

        def actor_ref(x, role):
            if role == "patient":
                return ref("Patient", x)
            if role == "provider":
                return ref("Practitioner", x)
            if role == "pool":
                return {"reference": f"Group/{x}"}
            if role in ("rn", "ma", "fd"):
                return ref("Practitioner", x)
            return {"display": x}

        files = {k: open(f"{out}/{k}.ndjson", "w") for k in
                 ["Patient", "Practitioner", "Communication", "Task", "AuditEvent", "Encounter"]}
        pats = {m.patient for m in self.messages if m.patient} | {v["patient"] for v in self.visits}
        for pt in sorted(pats):
            files["Patient"].write(json.dumps({"resourceType": "Patient", "id": H(pt),
                                               "active": True}) + "\n")
        people = self.providers + [s for v in self.staff.values() for s in v]
        for x in people:
            files["Practitioner"].write(json.dumps({"resourceType": "Practitioner", "id": H(x),
                                                    "active": True}) + "\n")
        for m in self.messages:
            com = {"resourceType": "Communication", "id": m.message_id, "status": "completed",
                   "category": [{"coding": [{"system": "urn:helsesoft:inbox-type", "code": m.msg_type}]}],
                   "sent": iso(m.created),
                   "sender": actor_ref(m.sender, m.sender_role),
                   "recipient": [actor_ref(m.recipient, m.recipient_role)],
                   "identifier": [{"system": "urn:helsesoft:thread", "value": m.thread_id}],
                   "extension": [{"url": "urn:helsesoft:portal-category", "valueString": m.category},
                                 {"url": "urn:helsesoft:relationship", "valueString": m.relationship},
                                 {"url": "urn:helsesoft:length-chars", "valueInteger": m.length}]}
            if m.patient:
                com["subject"] = ref("Patient", m.patient)
            if m.in_response_to:
                com["inResponseTo"] = [{"reference": f"Communication/{m.in_response_to}"}]
            com = {k: v for k, v in com.items() if v is not None}
            files["Communication"].write(json.dumps(com) + "\n")
        # Tasks: one per inbox assignment (CREATED to non-patient recipient, and each FORWARDED)
        open_task = {}
        for e in self.events:
            if e.event_type in ("CREATED", "FORWARDED") and e.target_role not in ("patient", None):
                tid = self.nid("TSK")
                task = {"resourceType": "Task", "id": tid, "status": "requested", "intent": "order",
                        "focus": {"reference": f"Communication/{e.message_id}"},
                        "owner": actor_ref(e.target, e.target_role),
                        "requester": actor_ref(e.actor, e.actor_role),
                        "authoredOn": iso(e.ts),
                        "code": {"coding": [{"system": "urn:helsesoft:task-type",
                                             "code": "forward" if e.event_type == "FORWARDED" else "inbox"}]}}
                if e.message_id in open_task:
                    task["partOf"] = [{"reference": f"Task/{open_task[e.message_id]['id']}"}]
                open_task.setdefault(e.message_id + "_list", []).append(task)
                open_task[e.message_id] = task
            elif e.event_type == "COMPLETED" and e.message_id in open_task:
                t = open_task[e.message_id]
                t["status"] = "completed"
                t["executionPeriod"] = {"start": t["authoredOn"], "end": iso(e.ts)}
            elif e.event_type == "ACCESSED":
                ae = {"resourceType": "AuditEvent", "id": e.event_id,
                      "type": {"system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
                               "code": "rest"},
                      "action": "R", "recorded": iso(e.ts),
                      "agent": [{"who": actor_ref(e.actor, e.actor_role), "requestor": True}],
                      "source": {"observer": {"display": "inbox-sim"}},
                      "entity": [{"what": {"reference": f"Communication/{e.message_id}"}}]}
                files["AuditEvent"].write(json.dumps(ae) + "\n")
        for k, v in open_task.items():
            if k.endswith("_list"):
                for t in v:
                    files["Task"].write(json.dumps(t) + "\n")
        for v in self.visits:
            files["Encounter"].write(json.dumps({
                "resourceType": "Encounter", "id": v["visit_id"], "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
                "subject": ref("Patient", v["patient"]),
                "participant": [{"individual": ref("Practitioner", v["provider"])}],
                "period": {"start": iso(v["start"])}}) + "\n")
        for enc in self.encounters:
            files["Encounter"].write(json.dumps({
                "resourceType": "Encounter", "id": enc["encounter_id"], "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "VR"},
                "subject": ref("Patient", enc["patient"]),
                "participant": [{"individual": actor_ref(enc["actor"], enc["actor_role"])}],
                "period": {"start": iso(enc["start"])},
                "identifier": [{"system": "urn:helsesoft:thread", "value": enc["thread_id"]}]}) + "\n")
        for fh in files.values():
            fh.close()


def main():
    ap = argparse.ArgumentParser(description="Synthetic EHR inbox metadata generator")
    ap.add_argument("--out", default="sim_output")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--weeks", type=int)
    ap.add_argument("--providers", type=int)
    ap.add_argument("--config", help="JSON file overriding CONFIG keys")
    a = ap.parse_args()
    cfg = copy.deepcopy(CONFIG)
    if a.config:
        with open(a.config) as f:
            over = json.load(f)
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    if a.seed is not None: cfg["seed"] = a.seed
    if a.weeks is not None: cfg["weeks"] = a.weeks
    if a.providers is not None: cfg["n_providers"] = a.providers
    sim = Sim(cfg)
    sim.run()
    sim.write(a.out)
    print(f"messages={len(sim.messages)} events={len(sim.events)} visits={len(sim.visits)} "
          f"truth_rows={len(sim.truth)} -> {a.out}")


if __name__ == "__main__":
    main()
