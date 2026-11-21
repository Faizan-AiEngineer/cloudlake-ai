# Benchmark methodology

The seed is 42. Dataset size, software versions, platform and logical CPU count are recorded under [results](../results/). Timing uses monotonic elapsed time. Reconciliation uses independently calculated cent-rounded ex-tax line revenue. CSV and JSON inputs and Parquet storage contain the same logical orders for the storage test.

Run a fresh benchmark from the repository root.

```powershell
python -m pip install -r backend/requirements.txt -r backend/requirements-spark.txt -r backend/requirements-infra.txt
python -m evaluation.scripts.benchmark --work .runtime/benchmark-fresh --output .runtime/benchmark-results-fresh
python -m evaluation.scripts.scale_probe --profile standard --work .runtime/standard-fresh --output .runtime/standard-fresh.csv
python -m evaluation.scripts.reliability_probe --home .runtime/benchmark-fresh/main --output .runtime/gate-probe-fresh.json
```

Pass unique workspace and output paths when repeating runs. The recorded main run reused the initial verified demo snapshot and used a separate strict challenge workspace. The first Spark context invocation and subsequent invocations can have different startup and caching costs. For a runtime comparison, repeat cases after warm-up in a randomized order and report the distribution. Source parsing, staging, validation and Gold timings are separately available in the raw CSV.

Labeled defect classification is at the business-record ID grain. A secondary rule violation can result from a different injected defect or a downstream broken reference. The independently simulated timing series excludes real pipeline outcomes. Unchanged-source manifest behavior and strict gate outcomes are recorded. An interrupted-Spark-process recovery experiment was not run in this set.
