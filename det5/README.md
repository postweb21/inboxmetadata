# Blind Inbox Workflow Detector v0.2

This package implements the metadata-only analysis pipeline for the inbox workflow simulation study. The detector never reads `ground_truth.csv` or generator configuration.

## Revised evaluation framework

- **P1, P4, P7, P8 — planted detection tasks.** Evaluate sensitivity, PPV, and F1 against hidden planted ground truth.
- **P2 — definition-derived phenotype.** A courtesy-copy message is positive when it has no access event within 14 days. Messages without 14 days of observable follow-up are right-censored and not classified. A later access after day 14 does not negate the positive classification.
- **P3 — emergent/descriptive phenotype.** An extended thread is defined as at least 4 patient/outbound exchanges spanning at least 3 days with no intervening office visit. It is counted from observable metadata and is not evaluated against planted P3 labels. Future generator versions need not deliberately plant P3; realistic continuation/timing probabilities may generate it naturally.
- **P5a/P5b — rate estimation.** Estimate forwarded-after-triage and forwarded-without-processing rates.
- **P6 — descriptive.** Report per-patient messaging-to-visit ratio.

This separation prevents naturally occurring rule-concordant P2/P3 cases from being incorrectly scored as false positives merely because they were not deliberately planted.

## Files

- `blind_detector.py` — blinded metadata-only detector.
- `evaluate_detector.py` — separate post-prediction evaluator. Ground truth is visible only here and is used only for planted detection tasks.
- `METHODS_REVISION.md` — manuscript-ready description of the revised framework.

## Blinding boundary

Detector inputs: `messages.csv`, `events.csv`, `visits.csv`, `coverage.csv`.

Forbidden detector inputs: `ground_truth.csv`, `run_config.json`, generator source/configuration.
