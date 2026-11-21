# CloudLake AI technical case study

A commerce team needs consistent revenue definitions, reproducible analytics and a traceable explanation when ingestion fails. CloudLake AI models that job with deterministic synthetic data and a single-user operational console. The data is suitable for demonstrating engineering and quality checks without private customer records.

The pipeline puts append-oriented file provenance in Bronze, use-case-independent normalized records in Silver and facts, dimensions and marts in Gold. A manifest hashes source bytes. Incremental mode stages unseen files, checks the merged history and publishes after the quality gate. Late data is advisory and still participates in the rebuild. The publication pointer changes in the same database transaction as the manifests, so failed work cannot make an intermediate Gold result current.

Spark executes type coercion, domain checks and referential joins. Arrow writes partitioned local Parquet with bounded transfer buffers. DuckDB supplies parameterized sales queries. FastAPI returns observability, previews, reports and a deterministic operations assistant. The AWS design separates queue and trigger handling from Spark processing, uses Iceberg format v2 for Athena and keeps the real deployment boundary explicit.

Raw timings, financial reconciliation and defect tests are described in [benchmarks](BENCHMARKS.md). Source and result sizes should be interpreted for the recorded hardware and run counts. Main tradeoffs include a local single-job limit, a full analytical rebuild when incremental data changes, illustrative currency rates, dataset-specific rules and a deliberate trusted loopback boundary.

Next engineering steps are incremental partition publication with replay semantics, expanded cloud analytical parity, multi-tenant controls and a measured cloud trial after approval.
