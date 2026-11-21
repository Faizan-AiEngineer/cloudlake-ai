# API reference

Swagger UI is served at `/docs` and OpenAPI at `/openapi.json`. JSON responses use `X-Correlation-ID`. Routes are local single-user endpoints.

| Method and path | Contract |
| --- | --- |
| GET `/health`, `/ready` | Liveness and a real metadata connection check |
| GET `/api/v1/system/status`, `/system/configuration` | Local service status and safe configuration fields |
| GET `/api/v1/overview`, `/monitoring` | Usage, run history, storage and ingestion freshness |
| GET `/api/v1/sources` | Feed schemas, committed files and event watermarks |
| POST `/api/v1/sources/{dataset}/upload?filename=...` | Raw CSV, JSON or Parquet bytes up to 10 MiB |
| GET `/api/v1/lakehouse` | Registered zones and datasets |
| GET `/api/v1/lakehouse/{zone}/{dataset}` | Preview, row count, size and schema; `limit` 1–100; optional quarantine run ID |
| GET `/api/v1/runs` | Paginated run records; optional status filter |
| POST `/api/v1/runs` | Accepts `{"mode":"batch","generate":true,"profile":"demo"}`; returns 202 and run ID |
| GET `/api/v1/runs/{run_id}`, `/runs/{run_id}/logs` | Run, task timeline and bounded API worker log |
| GET `/api/v1/quality` | Evaluations by dataset or run ID; bounded pagination |
| GET `/api/v1/alerts` | Severity/status filters and bounded pagination |
| PATCH `/api/v1/alerts/{id}` | Set status to `acknowledged` or `resolved` |
| GET `/api/v1/lineage` | Declared graph nodes and edges |
| GET `/api/v1/iceberg/snapshots` | Snapshot history for the optional local daily sales Iceberg table |
| GET `/api/v1/analytics` | Sales KPIs and charts with start, end, country, region, category, segment and channel |
| GET `/api/v1/assistant/status` | Offline provider availability |
| POST `/api/v1/assistant/ask` | Question, answer, evidence links, confidence and support flag |
| GET `/api/v1/reports/{kind}/{format}` | Executive, pipeline, quality, business, infrastructure or incident report; PDF, CSV or XLSX |

The API returns a 409 when required publications are absent or the workspace job slot is busy. Fixed filter values are parameterized. Report data comes from the workspace at request time. The record preview uses a table allowlist and row limits.

Executive, business and quality reports require a published snapshot. Pipeline reports can show blocked runs before the first publication. The executive quality summary identifies each run and distinguishes the published snapshot from blocked candidates in the recent history or included alerts. Executive and incident alerts include the recorded run ID and its status when a run is associated with the alert.
