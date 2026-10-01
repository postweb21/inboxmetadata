# Generator integrity audit

Runs: 20 independent one-month simulations (seeds 1-20).

The audit tests planted labels against the generated event history, using the manuscript operational definitions where they are mechanically testable. It does not test the future detector.

## Summary

| Pattern | Check | Pass | Total | Rate |
|---|---|---:|---:|---:|
| P1_thank_you | accessed_and_completed | 188 | 188 | 100.0% |
| P1_thank_you | is_reply_to_prior_outbound | 188 | 188 | 100.0% |
| P1_thank_you | message_exists | 188 | 188 | 100.0% |
| P1_thank_you | patient_originated_portal_message | 188 | 188 | 100.0% |
| P1_thank_you | thread_ending | 188 | 188 | 100.0% |
| P2_unread_cc | is_cc | 2919 | 2919 | 100.0% |
| P2_unread_cc | message_exists | 2919 | 2919 | 100.0% |
| P2_unread_cc | no_access_event | 2919 | 2919 | 100.0% |
| P3_extended_thread | four_or_more_message_exchanges | 100 | 100 | 100.0% |
| P3_extended_thread | no_visit_between | 100 | 100 | 100.0% |
| P3_extended_thread | spans_at_least_3_days | 100 | 100 | 100.0% |
| P3_extended_thread | thread_exists | 100 | 100 | 100.0% |
| P3_extended_thread | three_or_more_patient_incoming | 100 | 100 | 100.0% |
| P4_result_misrouted | is_result | 551 | 551 | 100.0% |
| P4_result_misrouted | message_exists | 551 | 551 | 100.0% |
| P4_result_misrouted | recipient_not_covering | 551 | 551 | 100.0% |
| P4_result_misrouted | recipient_not_ordering | 551 | 551 | 100.0% |
| P7_pingpong | at_least_two_provider_to_staff_forwards | 211 | 211 | 100.0% |
| P7_pingpong | at_least_two_staff_to_provider_forwards | 211 | 211 | 100.0% |
| P7_pingpong | message_exists | 211 | 211 | 100.0% |
| P7_pingpong | two_or_more_round_trips | 211 | 211 | 100.0% |
| P8_nonclinical_misrouted | message_exists | 177 | 177 | 100.0% |
| P8_nonclinical_misrouted | nonclinical_category | 177 | 177 | 100.0% |
| P8_nonclinical_misrouted | reaches_provider | 177 | 177 | 100.0% |

Total atomic checks: 13776; failures: 0.

## Interpretation

All audited invariants passed.

## Scope caveats

P1 “needs no action” is semantic ground truth created by the generator; metadata can verify that it is a short, terminal patient reply and that it is accessed/completed, but cannot independently prove message content. P2 is audited before adding future missing-access noise; with nonzero missing-access noise, ordinary read CCs can become detector false positives by design.
