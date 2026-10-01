# Pattern 3 revision and freeze candidate

Date: 2026-09-24

## Design decision

Pattern 3 is modeled as a prolonged inbox exchange occurring without an intervening completed office visit. This supports the study's intended interpretation of some extended inbox traffic as asynchronous care occurring when an in-person visit does not intervene, while not treating metadata alone as evidence that limited appointment access caused the thread.

## Generator change

1. The complete office-visit schedule is generated before inbox traffic.
2. A candidate P3 thread can be planted only if the patient has no office visit in the following 14 days.
3. Existing visits are not removed, moved, or suppressed.
4. Extended-thread patient follow-ups are spaced 36-48 hours apart, ensuring the planted thread satisfies the >=3-day duration criterion.

## Integrity audit

20 independent one-month simulations (seeds 1-20) produced 13,776 atomic checks with 0 failures. There were 100 planted P3 threads. All 100 satisfied every P3 integrity invariant, including no intervening visit and a duration of at least 3 days.

## Calibration consequence

The configured 5% P3 planting probability is conditional on eligibility (a visit-free interval). In the 20-run validation, planted P3 threads represented 3.6% of all clinical portal threads. The manuscript should therefore describe P3 prevalence as eligibility-conditioned, or choose a separate overall target and calibrate the conditional probability accordingly.
