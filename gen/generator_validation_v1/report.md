# Generator repeated-seed validation

Runs: 20; seeds 1-20; providers: 3; weeks/run: 4.

Intervals below are empirical 2.5th-97.5th percentiles across independent simulation runs, not confidence intervals for real-world parameters.

## Daily Volume

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| portal_message | 3.20 | 3.06 | 2.62–3.50 | -0.14 |
| patient_call | 4.80 | 4.74 | 4.29–5.14 | -0.06 |
| result | 15.50 | 15.31 | 14.60–16.05 | -0.19 |
| rx_renewal | 5.00 | 4.93 | 4.52–5.44 | -0.07 |
| referral_notice | 2.00 | 1.97 | 1.71–2.38 | -0.03 |
| prior_auth | 1.00 | 1.01 | 0.81–1.18 | 0.01 |
| staff_message | 7.00 | 7.00 | 6.40–7.47 | 0.00 |
| cc_message | 10.00 | 10.01 | 9.16–10.89 | 0.01 |
| order_to_sign | 10.00 | 10.00 | 9.32–10.63 | -0.00 |
| system_notice | 18.00 | 18.16 | 17.42–18.98 | 0.16 |

## Handling Path

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| nonclinical_staff_reply | 28.0% | 28.3% | 25.1%–30.7% | 0.3% |
| nonclinical_no_reply | 7.0% | 7.1% | 5.6%–8.3% | 0.1% |
| provider_direct | 20.8% | 20.7% | 18.4%–23.1% | -0.1% |
| provider_instructs_staff | 39.8% | 39.5% | 36.3%–43.1% | -0.3% |
| provider_instructs_staff_then_provider | 4.4% | 4.4% | 3.4%–5.8% | 0.0% |

## Planted Rate

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| P1_thank_you | 4.0% | 3.7% | 1.1%–6.4% | -0.3% |
| P2_unread_cc | 25.0% | 24.3% | 21.8%–27.0% | -0.7% |
| P3_extended_thread | 5.0% | 3.6% | 1.4%–5.9% | -1.4% |
| P4_result_misrouted | 3.0% | 2.8% | 1.8%–3.5% | -0.2% |
| P7_pingpong | 3.0% | 3.0% | 1.4%–4.6% | -0.0% |
| P8_nonclinical_misrouted | 5.0% | 5.0% | 2.1%–7.8% | 0.0% |

## Benchmark

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| provider_inbox_arrivals | 76.90 | 74.61 | 72.40–76.44 | -2.29 |
| top5_patient_message_share | 52.8% | 100.0% | 100.0%–100.0% | 47.2% |

## Interpretation

- A generator target is behaving as intended when the repeated-run mean is close to the configured target; individual one-month runs may vary substantially for uncommon paths.
- The Holmgren top-5% patient concentration benchmark is expected to be distorted in short simulations because most panel patients send no message during a four-week window. It is shown as a diagnostic benchmark, not a pass/fail generator target.
- This harness reads planted ground truth and therefore must remain separate from the future metadata-only detector.
