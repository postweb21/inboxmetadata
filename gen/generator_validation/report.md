# Generator repeated-seed validation

Runs: 100; seeds 1-100; providers: 3; weeks/run: 4.

Intervals below are empirical 2.5th-97.5th percentiles across independent simulation runs, not confidence intervals for real-world parameters.

## Daily Volume

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| portal_message | 3.20 | 3.20 | 2.82–3.63 | -0.00 |
| patient_call | 4.80 | 4.76 | 4.28–5.23 | -0.04 |
| result | 15.50 | 15.48 | 14.48–16.55 | -0.02 |
| rx_renewal | 5.00 | 5.01 | 4.52–5.48 | 0.01 |
| referral_notice | 2.00 | 2.00 | 1.63–2.37 | 0.00 |
| prior_auth | 1.00 | 1.01 | 0.77–1.23 | 0.01 |
| staff_message | 7.00 | 6.99 | 6.35–7.62 | -0.01 |
| cc_message | 10.00 | 10.02 | 9.23–10.88 | 0.02 |
| order_to_sign | 10.00 | 10.02 | 9.37–10.62 | 0.02 |
| system_notice | 18.00 | 17.97 | 16.92–18.96 | -0.03 |

## Handling Path

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| nonclinical_staff_reply | 28.0% | 28.1% | 24.5%–31.7% | 0.1% |
| nonclinical_no_reply | 7.0% | 6.8% | 4.9%–8.8% | -0.2% |
| provider_direct | 20.8% | 20.8% | 17.6%–24.4% | 0.0% |
| provider_instructs_staff | 39.8% | 39.9% | 35.6%–43.6% | 0.1% |
| provider_instructs_staff_then_provider | 4.4% | 4.4% | 2.8%–6.5% | 0.0% |

## Planted Rate

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| P1_thank_you | 4.0% | 3.6% | 1.9%–5.9% | -0.4% |
| P2_unread_cc | 25.0% | 25.0% | 22.0%–28.1% | -0.0% |
| P3_extended_thread | 5.0% | 4.9% | 2.3%–8.1% | -0.1% |
| P4_result_misrouted | 3.0% | 2.8% | 2.1%–4.1% | -0.2% |
| P7_pingpong | 3.0% | 3.1% | 1.6%–5.1% | 0.1% |
| P8_nonclinical_misrouted | 5.0% | 5.4% | 2.5%–8.1% | 0.4% |

## Benchmark

| Metric | Target | Mean | 95% simulation interval | Bias |
|---|---:|---:|---:|---:|
| provider_inbox_arrivals | 76.90 | 74.97 | 73.20–77.23 | -1.93 |
| top5_patient_message_share | 52.8% | 100.0% | 100.0%–100.0% | 47.2% |

## Interpretation

- A generator target is behaving as intended when the repeated-run mean is close to the configured target; individual one-month runs may vary substantially for uncommon paths.
- The Holmgren top-5% patient concentration benchmark is expected to be distorted in short simulations because most panel patients send no message during a four-week window. It is shown as a diagnostic benchmark, not a pass/fail generator target.
- This harness reads planted ground truth and therefore must remain separate from the future metadata-only detector.
