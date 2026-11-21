# CloudLake AI architecture

CloudLake AI models a synthetic commerce business. The core processing path is local and offline. The application reads committed lake snapshots and operational metadata. AWS is a separately configured deployment target.

```mermaid
flowchart LR
  Sources["Commerce feeds and FX fixture"] --> Landing --> Bronze["Bronze Parquet"]
  Bronze --> Spark["PySpark validation"]
  Spark --> Quarantine
  Spark --> Silver["Silver Parquet"]
  Silver --> Gold["Gold Parquet and analytical models"]
  Gold --> DuckDB --> FastAPI --> React
  Spark --> Metadata["SQLAlchemy operational store"]
  Metadata --> FastAPI
```

## Ingestion and publication

```mermaid
flowchart LR
  Discover["Discover batches"] --> Parse["Parse registered feeds"]
  Parse --> Hash["Fingerprint records and source files"]
  Hash --> Stage["Write immutable Bronze batches"]
  Stage --> Validate["Validate merged state"]
  Validate --> Gate{"Critical thresholds met?"}
  Gate -->|Yes| Commit["Commit snapshot and checkpoints together"]
  Gate -->|No| Retain["Retain previous publication and surface quarantine"]
```

The metadata store acts as the publication authority. Files under a run ID are immutable. A completed transaction selects the visible run and records its source manifest. Retried inputs use content digests. Incremental discovery hashes inputs and skips staging unchanged content. Changed inputs trigger a full analytical rebuild from the Bronze journal to preserve cross-dataset consistency. Watermarks describe observed event time. File discovery accepts late data even when it precedes the watermark.

```mermaid
flowchart LR
  Raw["Bronze · source payload and ingestion metadata"] --> Typed["Silver · typed, normalized and deduplicated records"]
  Typed --> Star["Gold · facts, dimensions and marts"]
  Typed --> Q["Quarantine · original payload and rule IDs"]
```

## Execution environments

```mermaid
flowchart LR
  Browser --> Vite --> API["FastAPI on loopback"]
  API --> SQLite
  API --> DuckDB
  API --> Runner["Controlled CLI subprocess"]
  Runner --> JVM["Spark local JVM"]
  JVM --> Files["Local Parquet snapshots"]
  DuckDB --> Files
```

SQLite is the verified local metadata store and the Compose default. The optional infrastructure profile defines PostgreSQL and MinIO, with PostgreSQL selected through the database URL. The DAG definitions target Airflow on Linux or WSL and invoke the pipeline in a distinct process. Docker Engine, PostgreSQL, MinIO and Airflow execution remain unverified. An Iceberg catalog can be enabled independently of the default Parquet snapshot workflow.

```mermaid
flowchart LR
  Events["EventBridge / S3 events"] --> Queue["SQS buffering and DLQ"]
  Queue --> Lambda["Lambda event validation"]
  Lambda --> Glue["AWS Glue Spark"]
  Glue --> Lake["Encrypted S3 lake"]
  Glue --> Catalog["Glue Data Catalog"]
  Catalog --> Athena["Athena bounded workgroup"]
  Lake --> Athena
  Lambda --> CloudWatch
  Glue --> CloudWatch
```

The AWS diagram describes the prepared target configuration. Terraform validation passed locally. Live AWS deployment remains unverified. The local API and control plane are designed for trusted single-user sessions.

## Orchestration and metadata

```mermaid
flowchart LR
  Trigger["CLI / API / scheduled Airflow"] --> Discover --> Ingest --> Transform --> Gate
  Gate -->|pass| Publish --> Summary
  Gate -->|block| Incident --> Summary
```

```mermaid
erDiagram
  PIPELINE_RUN ||--o{ TASK_RUN : logs
  PIPELINE_RUN ||--o{ QUALITY_RESULT : evaluates
  PIPELINE_RUN ||--o{ SOURCE_MANIFEST : commits
  PIPELINE_RUN ||--o{ ALERT : raises
```

The API is versioned under `/api/v1`. It exposes typed run initiation, fixed analytical queries, paginated operational listings, bounded dataset previews, evidence-grounded assistant responses and report downloads. `/health` checks process liveness. `/ready` checks the operational store.

The React shell provides Overview, Data Sources, Lakehouse Explorer, Pipeline Manager, Data Quality, Data Lineage, Business Analytics, AI Operations Assistant, Alerts & Monitoring, Cloud Infrastructure, Reports and Settings.

The executive report reads revenue and source counts for the current publication. Its quality table also covers blocked runs referenced by recent run history or the included alerts. Alert rows identify the associated run and its status. Each quality total counts individual rule evaluations, which can exceed the number of quarantined rows.

## Analytical lineage

```mermaid
flowchart LR
  Orders --> Sales["Validated sales lines"]
  Items --> Sales
  Products --> Sales
  Customers --> Sales
  Rates --> Sales
  Sales --> Fact["fact_sales"]
  Fact --> Daily["daily_sales"]
  Fact --> Product["product_profitability"]
  Daily --> Executive["Executive analytics and reports"]
  Product --> Executive
  Clickstream --> Funnel["Conversion funnel"]
```
