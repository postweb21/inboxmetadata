# P5 denominator correction

P5 now uses the dataset's complete staff-routed patient portal cohort as the denominator:

- `sender_role == 'patient'`
- `recipient_role == 'pool'`
- `msg_type == 'patient_medical_advice_request'`

No `portal_category` values are excluded. Clinical/nonclinical category is retained only for stratified reporting.

In this synthetic dataset, `patient_call` records are created by front-desk (`fd`) actors and are not part of this patient-originated staff-pool cohort. An earlier attempted fix also required `in_response_to == ''`; that incorrectly removed 11 eligible portal records and produced 553 rather than 564 eligible messages.

A P5 positive is an eligible message with a subsequent `FORWARDED` event from a staff actor (`rn`, `ma`, or `fd`) to a provider.

Verified on the frozen 10k example dataset (seed 20260924):
- Eligible: 564
- Forwarded: 400 (70.9%)
- Clinical: 399; forwarded 389 (97.5%)
- Nonclinical: 165; forwarded 11 (6.7%)
