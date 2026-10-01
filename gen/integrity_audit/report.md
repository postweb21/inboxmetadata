# Generator integrity audit

Runs: 20 independent one-month simulations (seeds 1-20).

The audit tests planted labels against the generated event history, using the manuscript operational definitions where they are mechanically testable. It does not test the future detector.

## Summary

| Pattern | Check | Pass | Total | Rate |
|---|---|---:|---:|---:|
| P1_thank_you | accessed_and_completed | 172 | 172 | 100.0% |
| P1_thank_you | is_reply_to_prior_outbound | 172 | 172 | 100.0% |
| P1_thank_you | message_exists | 172 | 172 | 100.0% |
| P1_thank_you | patient_originated_portal_message | 172 | 172 | 100.0% |
| P1_thank_you | thread_ending | 172 | 172 | 100.0% |
| P2_unread_cc | is_cc | 2992 | 2992 | 100.0% |
| P2_unread_cc | message_exists | 2992 | 2992 | 100.0% |
| P2_unread_cc | no_access_event | 2992 | 2992 | 100.0% |
| P3_extended_thread | four_or_more_message_exchanges | 156 | 156 | 100.0% |
| P3_extended_thread | no_visit_between | 136 | 156 | 87.2% |
| P3_extended_thread | spans_at_least_3_days | 156 | 156 | 100.0% |
| P3_extended_thread | thread_exists | 156 | 156 | 100.0% |
| P3_extended_thread | three_or_more_patient_incoming | 156 | 156 | 100.0% |
| P4_result_misrouted | is_result | 576 | 576 | 100.0% |
| P4_result_misrouted | message_exists | 576 | 576 | 100.0% |
| P4_result_misrouted | recipient_not_covering | 576 | 576 | 100.0% |
| P4_result_misrouted | recipient_not_ordering | 576 | 576 | 100.0% |
| P7_pingpong | at_least_two_provider_to_staff_forwards | 220 | 220 | 100.0% |
| P7_pingpong | at_least_two_staff_to_provider_forwards | 220 | 220 | 100.0% |
| P7_pingpong | message_exists | 220 | 220 | 100.0% |
| P7_pingpong | two_or_more_round_trips | 220 | 220 | 100.0% |
| P8_nonclinical_misrouted | message_exists | 201 | 201 | 100.0% |
| P8_nonclinical_misrouted | nonclinical_category | 201 | 201 | 100.0% |
| P8_nonclinical_misrouted | reaches_provider | 201 | 201 | 100.0% |

Total atomic checks: 14403; failures: 20.

## Interpretation

All audited P1, P2, P4, P7, and P8 structural invariants passed. P3 also passed the thread-size and >=3-day-span checks in all 156 planted instances. The important exception was the manuscript requirement of “no visit in between”: 20 of 156 planted P3 threads (12.8%) had an intervening office visit. The generator currently plants the extended thread without checking or suppressing visits, so those labels do not fully satisfy the manuscript operational definition. This should be corrected before freezing v1.0.

## Scope caveats

P1 “needs no action” is semantic ground truth created by the generator; metadata can verify that it is a short, terminal patient reply and that it is accessed/completed, but cannot independently prove message content. P2 is audited before adding future missing-access noise; with nonzero missing-access noise, ordinary read CCs can become detector false positives by design.
