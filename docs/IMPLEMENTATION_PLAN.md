# Implementation plan

Phases are ordered by dependency. Each phase closes with execution evidence and limitations in PROJECT_STATUS.md. Local pipeline verification takes priority over optional hosting integrations.

| Phase | Definition of done |
| --- | --- |
| 0 · Audit and design | Inventory workspace and tools, define service boundaries, data contracts and local/cloud verification boundaries |
| 1 · Foundation | Migrate metadata store and verify API, shell, readiness and tooling |
| 2 · Generator | Reproduce seeded data, validate relationships and export CSV/JSON with separately labeled defects |
| 3 · Bronze | Read supported formats, write metadata-rich Parquet, persist manifests and exercise duplicate/retry behavior |
| 4 · Silver | Execute PySpark rules and joins, inspect quarantine and demonstrate critical publication blocking |
| 5 · Gold | Reconcile financial aggregates, run bounded analytical queries and verify Iceberg capabilities individually |
| 6 · Orchestration | Verify shared CLI runner and Airflow DAG imports, document scheduler execution status |
| 7 · Observability | Inspect durable runs, tasks, quality, alerts, checkpoints and lineage from actual runs |
| 8 · AWS | Author reviewable IaC and jobs, validate locally where possible, document deployment steps |
| 9 · Assistant | Test supported and unsupported questions against real database and lakehouse evidence |
| 10 · Frontend | Exercise all routes, data loads, actions, filters and reports in a browser and build |
| 11 · Hardening | Exercise upload, path, query and concurrency boundaries and interrupted publication behavior |
| 12 · Evaluation | Save reproducible raw measurements and per-experiment results with environment and limitations |
| 13 · QA | Run backend, pipeline, frontend and infrastructure checks and report unavailable checks |
| 14 · Documentation | Verify setup, contracts, case study, glossary, architecture and troubleshooting |
| 15 · CI/CD | Check locked builds and static workflows with no automatic deployment |
| 16 · Demo | Run seeded demo and capture authentic screenshots and report exports |
| 17 · Audit | Verify local demo, inspect publication contents and produce hashes and release summary |

Core run flow: seed sources, ingest Bronze, validate Silver, evaluate gates, publish Gold, serve analytics, exercise incremental input, query the assistant and generate a report.
