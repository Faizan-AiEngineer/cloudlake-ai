# Benchmarks

Raw measurements are in [evaluation/results](../evaluation/results/). See the [report](../evaluation/reports/BENCHMARK_REPORT.md) for interpretation and the [methodology](../evaluation/reports/methodology.md) for reproduction.

| Experiment | Observed result |
| --- | --- |
| Demo batch | 10,594 evaluated rows, zero rejected, 69.49 seconds, 152.5 rows/s |
| Standard batch | 105,683 evaluated rows, zero rejected, 203.53 seconds, 519.3 rows/s with reconciled revenue |
| Changed incremental input | 930 new rows staged, 11,524 rows evaluated, 102.93 seconds |
| Full replay over the same journal | 11,524 rows evaluated in 29.10 seconds, with the same USD 1,360,238.67 revenue |
| Unchanged incremental input | 0 rows evaluated, 0.18 seconds (raw timing 0.1820735 seconds), publication pointer retained |
| Strict quality challenge | 1,048 input rows, 87 quarantined, critical gate blocked |
| Analytical queries | Six executions reconciled to independent USD totals. Range 0.101–0.181 seconds |
| Storage | 1,428 logical order rows. CSV 118,081 B, JSON 287,923 B, Zstandard Parquet 19,618 B |
| Anomaly evaluation | Median/MAD F1 1.000 and Isolation Forest F1 0.816 on the fixed labeled series |
| Offline assistant | Four supported sample questions met their content/evidence assertion and two unsupported prompts were rejected |

The incremental run and full replay used different JVM warm-up states. The timing comparison does not establish a speedup. Source staging overhead fell when few or no files changed. Reconciliation establishes equivalent analytical output for the measured synthetic input.

A separate strict-gate follow-up verified that a blocked candidate left the prior Gold publication visible. The earlier successful incremental run flagged 669 records before their feed watermark. Changed incremental input stages only new content and rebuilds the Silver and Gold snapshots from the journal. [Strict-gate follow-up](../evaluation/results/reliability_followup.json)

The final audit matched the four headline measurements to the original CSV rows and independently recalculated USD 1,360,238.67 from the seeded order lines and FX rates. Both existing Gold snapshots produced the same revenue. The original measurement files remain part of the publication. [Batch](../evaluation/results/batch_performance.csv) · [Standard](../evaluation/results/scale_performance.csv) · [Incremental and replay](../evaluation/results/incremental_performance.csv) · [Revenue checks](../evaluation/results/query_performance.csv)

The isolated Tiny audit rerun measured 1,958 rows in both the changed incremental and replay runs. They reconciled to USD 219,473.92. The rerun preserves full measured durations and its own environment separately from the original results. [Audit rerun](../evaluation/results/final_audit_recheck.json)
