# Benchmark report

The local baseline generated nine feed types and evaluated 10,594 records. DuckDB recognized USD 1,215,013.42, which matched a separate Python Decimal calculation. Adding 930 records increased recognized revenue to USD 1,360,238.67, and the batch replay reproduced it. Filtered German sales also reconciled to USD 244,808.46.

The strict challenge blocked Gold. Each of the seven directly scored injected rule categories was detected. Referential integrity produced 14 additional flags because the deliberately malformed product also invalidated dependent inventory records. The incorrect-total classifier flagged an additional line whose injected negative quantity also broke arithmetic. These are counted as false positives against the direct-injection labels. The ground truth does not classify dependent errors. Lateness and the isolated synthetic payment anomaly were excluded from quarantine scoring.

The held-out timing series used 120 independent calibration samples and 100 labeled evaluation samples. Median/MAD detected all 20 shifts without flagging the 80 clean points on this series. Isolation Forest detected all 20 and flagged nine clean samples. These are outcomes for the seeded distribution and thresholds.

Parquet was approximately 6.0 times smaller than CSV and 14.7 times smaller than JSON for equivalent orders. The single measured read per format includes parser startup and should not be generalized. DuckDB timings use fresh connections sharing the operating-system cache. Cold disk-cache behavior was not controlled.

The fixed offline question set tested four supported questions for response content and evidence and two unsupported questions for rejection. These checks cover the published set only.

[Recorded environment](../results/environment.json) · [Batch measurements](../results/batch_performance.csv) · [Incremental measurements](../results/incremental_performance.csv) · [Monthly revenue chart](../results/observed_revenue.svg)

[Batch throughput chart](figures/batch-throughput.svg) · [Storage efficiency chart](figures/storage-efficiency.svg)
