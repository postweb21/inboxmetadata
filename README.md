# Inbox Workflow Metadata — Simulation & Detection Code

This repository contains the simulation, detection, and evaluation code supporting:

> Jaren O, Lukela JR. **Using Message-Level Metadata to Characterize Electronic Health Record Inbox Workflow.** *JAMIA Open* (submitted).

The study is a simulation-based feasibility analysis asking whether EHR inbox workflow
patterns ("phenotypes" P1–P8) can be detected from message-level **metadata alone**
(timestamps, sender/recipient roles, message types, routing events) — without reading
message content. All data used in the manuscript are synthetic. **No real patient data,
PHI, or production EHR data are used anywhere in this repository.**

## Pipeline overview

```
inbox_sim.py  →  messages.csv, events.csv, visits.csv, coverage.csv, ground_truth.csv
                              │
                              ▼
                   blind_detector.py   (metadata-only; never reads ground_truth.csv)
                              │
                              ▼
                   evaluate_detector.py  (ground truth used only here, only for planted
                                           phenotypes P1/P4/P7/P8)
```

The detector is "blind" by design: it is given only the files an analyst would actually
have access to in a live EHR (`messages.csv`, `events.csv`, `visits.csv`, `coverage.csv`)
and never sees `ground_truth.csv` or the generator's internal configuration. Ground truth
is used solely downstream, by `evaluate_detector.py`, to score the planted phenotypes.

## Repository contents

```
gen/
  inbox_sim.py                    generator — simulates a synthetic primary care practice's
                                   inbox metadata, with workflow patterns planted at known rates
  validate_generator.py           generator self-check used during development
  calibration_check.py            calibration benchmark across repeated runs
  audit_generator_integrity.py    integrity audit (planted-label consistency checks)
  README.md                       generator usage, parameters, event types, known simplifications
  P3_REVISION_REPORT.md           record of the P3 definition revision (v1.0, 2026-09-24)
  integrity_audit_v1/report.md    20-seed integrity audit: 13,776 checks, 0 failures
  generator_validation_v1/report.md   calibration benchmark report (includes a noted
                                       limitation around top-5%-concentration calibration)

det5/
  blind_detector.py               metadata-only detector (v0.5 — includes the P5 fix, see below)
  evaluate_detector.py            evaluator — ground truth used only for P1/P4/P7/P8
  run_evaluation_suite.py         runs detector + evaluator and summarizes results
  README.md                       detector/evaluator design, blinding boundary, phenotype definitions
  METHODS_REVISION.md             manuscript-ready description of the evaluation framework
  P5_FIX_NOTES.md                 P5 denominator bug and fix (see Version history)
  EVALUATOR_REPORT.md             scope and limitations of the evaluation (see note below)
```

## Reproducing the manuscript's results

```bash
pip install numpy pandas fhir.resources

# 1. Generate the dataset used in the manuscript
python gen/inbox_sim.py --out run1 --seed 20260924 --weeks 8 --providers 3

# 2. Run the blind detector on the generated metadata
python det5/blind_detector.py run1 --out predictions

# 3. Score the planted phenotypes and summarize descriptive/rate phenotypes
python det5/evaluate_detector.py run1 predictions
```

This exact seed/weeks/providers combination reproduces the dataset reported in the
manuscript (10,557 messages; 9,931 threads; 1,917 visits across 3 providers over 8
weeks) and all reported phenotype statistics (P1–P8), including the P5 forwarding rate
(564 eligible, 400 forwarded, 70.9%) and the P6 messaging-to-visit breakdown (1,571
patients with a thread, a visit, or both; 343 with a thread; 1,427 with a visit; 199
with both; median 1.0 threads/visit, IQR 0.5–1.0).

## Phenotypes (P1–P8)

| # | Phenotype | Type |
|---|-----------|------|
| P1 | Low-value terminal replies | Planted |
| P2 | Unread courtesy copies | Definition-derived |
| P3 | Extended visit-free threads | Emergent/descriptive |
| P4 | Misrouted results | Planted |
| P5 | Staff→provider forwarding rate | Rate estimation |
| P6 | Messaging-to-visit ratio | Descriptive |
| P7 | Staff↔provider round trips | Planted |
| P8 | Nonclinical messages reaching provider | Planted |

Full definitions are in `det5/README.md` and `det5/METHODS_REVISION.md`.

## Version history / known issues

- **v0.3 → v0.5, P5 denominator fix.** The original P5 eligibility filter
  (`recipient_role=='pool' AND portal_category not in NONCLIN`) incorrectly computed
  98.7% (770/770) forwarded rather than the correct 70.9% (400/564). The fix restricts
  the eligible cohort to `sender_role=='patient' & recipient_role=='pool' &
  msg_type=='patient_medical_advice_request'`, with clinical/nonclinical retained only
  as a stratification variable. See `det5/P5_FIX_NOTES.md` for the full root-cause
  explanation. This fix has been independently re-verified against freshly regenerated
  data (not just the author's bundled output).
- **P3 definition revision (v1.0, 2026-09-24).** P3 now requires no intervening office
  visit in the 14-day window following a candidate thread. See
  `gen/P3_REVISION_REPORT.md`.
- **Generator calibration.** The 20-seed integrity audit found 0 failures across 13,776
  planted-label checks. A separate calibration benchmark (`generator_validation_v1/report.md`)
  flagged a top-5%-message-concentration diagnostic as miscalibrated relative to the
  target distribution; this diagnostic is explicitly not a pass/fail target and does not
  affect the planted-phenotype ground truth.
- **Evaluation scope.** `det5/EVALUATOR_REPORT.md` documents that full held-out
  validation across many seeds was not run as part of this evaluator package; results
  reported in the manuscript are from the frozen 10k-message example run (seed
  20260924) plus independent re-generation and re-scoring from the same seed.

## Patient generation

Patients are generated internally using a lognormal messaging-propensity model; Synthea
is not currently integrated into the pipeline. See `gen/README.md`, "Known
simplifications."

## Data availability

All data are synthetic and generated by `gen/inbox_sim.py`; no patient data are included
in or required by this repository. The exact dataset used in the manuscript can be
regenerated with the seed/parameters given above.

## License

[Add a license, e.g. MIT or Apache-2.0, before publishing the repo.]

## Citation

If you use this code, please cite the manuscript above. A citable archived version of
this exact code is available via Zenodo: [DOI to be added once the Zenodo release is
created].
