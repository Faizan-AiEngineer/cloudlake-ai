# Portfolio materials

## GitHub

**Repository name** · `cloudlake-ai`

**Description** · Reproducible PySpark commerce lakehouse with Bronze, Silver and Gold layers, data-quality gates, DuckDB analytics, an operations console and AWS infrastructure as code.

**Topics** · `data-engineering`, `pyspark`, `data-lakehouse`, `duckdb`, `apache-iceberg`, `fastapi`, `react`, `airflow`, `terraform`, `aws-glue`, `data-quality`, `observability`

**Suggested initial commit** · `Build CloudLake AI commerce lakehouse and operations console`

## LinkedIn announcement draft

I built CloudLake AI to practice the parts of data engineering that start after the first ETL succeeds: quality gates, checkpoints, reconciliation, reruns and visibility into failures. A seeded synthetic commerce dataset moves through Bronze, Silver and Gold using PySpark, Parquet and DuckDB. I tested a full run, a changed incremental input and an unchanged-input no-op. I also reconciled revenue independently from transaction records. The React console exposes run history, quality results, analytics, evidence-grounded answers and actual exports. The project includes validated Terraform for an AWS data plane. Cloud deployment is still unverified.

**LinkedIn project description** · Local Spark and DuckDB commerce lakehouse with deterministic inputs, quality gates, analytical marts, operational dashboards and AWS infrastructure configuration.

## CV bullets

- Built a medallion data pipeline for nine synthetic feeds using PySpark, Apache Parquet and DuckDB, with typed Silver validation, quarantine and Gold models for commerce analytics.
- Implemented content-addressed ingestion, recoverable publication and an explicit quality gate, then reconciled batch, incremental and replay outputs against independent financial calculations.
- Developed a FastAPI and React operations console for pipeline runs, data quality, lineage and PDF/CSV/XLSX reports, with Terraform configuration for an AWS Glue and Athena data plane.

## Demonstration scripts

**Two minutes** · Open Overview and show the latest real publication and dataset health. In Pipeline Manager, select the full run and read the task sequence. Compare Bronze orders and Silver orders in Lakehouse Explorer. Open Data Quality and explain one rule and what blocks publication. Open Business Analytics, apply a country filter and compare revenue totals. Ask the assistant about the latest observed revenue months and follow its evidence link. Download the executive report.

**Five minutes** · Begin with the business grain and nine source contracts. Trace one order line through Bronze provenance, Silver typed validation and the Gold sales fact. Show how content identity and event watermarks serve different purposes. Explain the pointer/manifest transaction, demonstrate the incremental and no-op runs and discuss why changed inputs rebuild Gold. Describe quality-driven quarantine and the independent revenue check. Explain what stays local, which AWS services are configured and which live-cloud checks remain.

## Interview questions

| Question | Project-grounded answer |
| --- | --- |
| What business problem does it model? | Consistent commerce metrics and visible failure diagnosis across data ingestion and serving. |
| Why three storage layers? | Preserve source provenance, establish normalized records and support analytical serving at distinct grains. |
| How is generation reproducible? | Fixed pseudo-random seeds, historical start date, explicit batch IDs and configuration. |
| How does Bronze retain provenance? | Each record includes dataset, source name, run ID, timestamp, schema version and payload hash. |
| What does the manifest identify? | Immutable dataset and source-content digest pairs committed by successful runs. |
| What happens with no new input? | Incremental mode records a successful no-op without moving the publication pointer. |
| How do you handle late data? | Compare new arrival timestamps with prior watermarks and flag them as advisory. Valid rows still enter the rebuilt state. |
| Where does Spark execute? | The local Spark JVM handles casts, windows and joins. Arrow writes bounded output chunks. |
| How are invalid records reviewed? | Quarantine retains original fields and check IDs. The API lets users inspect a run’s rejected rows. |
| What triggers blocking? | A critical rule fails at a proportion above the configured per-dataset threshold. |
| How do you guarantee local publication semantics? | Place outputs under an immutable run ID and commit its pointer with its source manifests in the metadata store. |
| Why DuckDB? | A local engine can query Parquet and compute aggregates with small infrastructure overhead. |
| How was revenue reconciled? | A separate Python Decimal calculation derived ex-tax completed-order line revenue and rounded each converted line. |
| How is a refund represented? | A returned order has zero recognized revenue and a separate positive ex-tax refund amount. |
| What limits Spark scalability here? | One local worker, file-bounded ingest and whole-snapshot rebuilds when a delta arrives. |
| Which anomalies were measured? | Timing outliers on a held-out, labeled synthetic series using median/MAD and Isolation Forest. |
| Why use offline rule-based assistance? | Supported intents can be tied deterministically to published facts and run IDs with an explicit unsupported response. |
| Why use Iceberg separately from local Parquet? | It demonstrates table metadata and history while keeping the default local runtime simple. |
| How does AWS event handling work? | EventBridge routes landing events or schedules through SQS. Lambda validates metadata and triggers Glue. |
| What would you verify before production? | Live IAM permissions, retry semantics, IAM-scoped access, snapshot consistency, cost, throughput and multi-user security. |
