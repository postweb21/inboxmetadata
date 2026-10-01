# Evaluator v0.3 report

## Purpose
The evaluator is intentionally separate from the blind detector. It may read `ground_truth.csv` and `run_config.json`; the detector may not. The evaluator implements the revised phenotype framework.

## What is evaluated
- P1, P4, P7, P8: classification against planted hidden ground truth (sensitivity, PPV, F1).
- P2: independently reconstructs the 14-day unread-CC definition from raw metadata and checks detector agreement; right-censored CCs are excluded.
- P3: independently reconstructs the extended-thread definition from raw metadata and checks that the detector reproduces it. This is a definition-reconstruction check, not a claim that P3 is a planted abnormality.
- P5: independently identifies the complete patient-originated portal-message cohort delivered to staff pools and staff-to-provider forwards, then compares detector and reference forwarding rates. Dwell time and chart activity are not used to infer triage quality.
- P6: produces a descriptive summary of threads-per-visit output.

## Smoke test
The full 20-seed run was intentionally not completed in this interactive pass because generation of each full one-month FHIR dataset is computationally expensive. Three completed independent seeds were used as a software smoke test. Across these runs, P1, P2, P3, P4, P7, and P8 showed exact detector/reference agreement (sensitivity/PPV/F1 = 1.0 where defined). P5 also showed exact set and rate agreement, with zero absolute rate error. These results validate evaluator plumbing and definition consistency; they are not yet the study's held-out performance results.

## Next use
Before manuscript Results are generated, choose development and held-out seed sets, freeze detector thresholds, and run the suite on those prespecified sets. Aggregate performance should then be reported across held-out runs with simulation intervals.
