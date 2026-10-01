# Inbox metadata simulator (feasibility study)

Synthetic EHR inbox metadata for a simulated primary care practice, with workflow
patterns planted at known rates. Metadata only - no message content.

## Run
    pip install numpy pandas fhir.resources
    python inbox_sim.py --out run1                 # defaults: 3 providers, 4 weeks, seed 42
    python inbox_sim.py --out run2 --weeks 26 --providers 8 --seed 7
    python inbox_sim.py --out run3 --config overrides.json   # e.g. {"noise": {"missing_access_rate": 0.05}}
    python calibration_check.py run1               # writes run1/calibration_report.md

## Outputs
- messages.csv, events.csv, visits.csv, coverage.csv - the "extract" an analyst would receive
- fhir/*.ndjson - same data as FHIR resources (Patient, Practitioner, Communication, Task, AuditEvent, Encounter)
- ground_truth.csv - planted labels and handling paths. The analysis pipeline must never read it.
- run_config.json - exact parameters (salt redacted)

## Parameters
All in CONFIG at the top of inbox_sim.py, tagged [pub], [expert], [fill], or [model].
Planted rates live under CONFIG["planted"]; noise under CONFIG["noise"].

## Event types (events.csv)
CREATED, ACCESSED, FORWARDED, REPLIED, PHONE_CONTACT, CHART_ACCESS, COMPLETED

## Known simplifications
- Patients are generated internally (lognormal messaging propensity); Synthea not yet integrated.
- FHIR validated with fhir.resources R4B models (equivalent to R4 for these resources).
- Work windows are simple (staff weekdays 8-17, providers 7-21 daily).

## v1.0 P3 integrity revision (2026-09-24)

Pattern 3 now represents prolonged asynchronous management **without an intervening office visit**. The simulator first generates the complete office-visit schedule, then generates inbox traffic. A candidate P3 thread is planted only when the patient has no office visit in the subsequent 14-day window; the visit schedule is never deleted or rescheduled to make a thread qualify. P3 follow-up spacing is 36–48 hours so planted threads reliably span at least 3 days.

Because the 5% P3 probability is applied only to visit-free eligible clinical portal threads, the observed share among *all* clinical portal threads is lower (3.6% in the 20-run post-fix validation). This is intentional and should be described as an eligibility-conditioned planting rate rather than a 5% overall prevalence.

Post-fix integrity audit: 20 independent one-month simulations, 13,776 atomic checks, 0 failures. All 100 planted P3 threads met all audited criteria: >=3 patient incoming messages, >=4 patient/outbound message exchanges, >=3-day span, and no intervening office visit.
