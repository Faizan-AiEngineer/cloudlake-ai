# CloudLake AI delivery report

CloudLake AI was built in the original `CloudLake Ai` workspace and audited in a staging copy for the sibling `CloudLake-AI-Clean` publication folder. The 128 original payload files were used as the verified copy baseline. The Windows application uses PySpark, Arrow/Parquet, DuckDB, SQLite/Alembic, FastAPI, and React/TypeScript. The optional local Iceberg SQL catalog mirrors the daily sales model.

## Final audit findings

The old report's quality totals were correct for publication `0b1e554258b8412197647aa0103f03e3`. Its two alerts were linked to blocked candidate `b0434e335a2c4abaae41c34cab9a3a43`, and the export omitted that link. All three executive exports now identify both quality scopes and the associated run on each alert.

| Run scope | Rule evaluations | Failed rule evaluations | Blocked rules | Quarantined rows |
| --- | ---: | ---: | ---: | ---: |
| Published snapshot | 92,192 | 0 | 0 | 0 |
| Blocked candidate | 109,680 | 3,027 | 10 | 1,356 |

Pipeline reports now expose blocked runs before the first successful publication. Executive source counts follow the same publication as the sales figures. XLSX columns fit run identifiers and wrap long messages. [Sample PDF](sample-cloudlake-report.pdf) · [CSV](sample-cloudlake-report.csv) · [Excel](sample-cloudlake-report.xlsx)

## Project inventory

| Item | Count |
| --- | ---: |
| Source and configuration files counted by code/config extension | 60 |
| Python and TypeScript source files | 37 Python and 9 TypeScript |
| Backend application modules | 8 |
| React components including route components and the error boundary | 19 |
| Console routes | 12 |
| API endpoints excluding documentation and OpenAPI | 23 |
| Airflow DAG definitions | 5 |
| Data quality rule types | 8 across 9 feeds |
| DuckDB Gold tables and marts | 23 |
| Automated tests | 13 Python definitions and 3 Vitest checks, plus the live browser script |

Artifact hashes and publication paths are listed in the [SHA-256 manifest](../PUBLICATION_MANIFEST.json). Counts exclude dependencies, application data, caches, images and build output.

The clean folder contains 130 payload files plus the manifest. The release scan checked source and documentation, PDF text, XLSX XML and embedded PNG metadata for likely credentials and machine-specific paths. It found no matching credential material. The clean copy excludes runtime databases, local environment files, virtual environments, dependencies, provider binaries, build directories, caches and editor metadata. The public owner name and GitHub handle remain visible. The owner-supplied commit email is reserved for local Git configuration.

## Files changed in the clean copy

| Purpose | Paths |
| --- | --- |
| Report correction and regression test | `backend/app/reports.py`, `backend/tests/test_boundaries.py` |
| Regenerated reports | `docs/sample-cloudlake-report.pdf`, `docs/sample-cloudlake-report.csv`, `docs/sample-cloudlake-report.xlsx`, `docs/screenshots/10-generated-report.png` |
| Documentation | `README.md`, `PROJECT_STATUS.md`, `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/BENCHMARKS.md`, `docs/FINAL_DELIVERY.md` |
| New checklist and rerun evidence | `docs/PUBLICATION_CHECKLIST.md`, `evaluation/results/final_audit_recheck.json` |
| Publication controls | `.gitignore`, `scripts/publication_manifest.py`, `PUBLICATION_MANIFEST.json` |

## Execution and validation

| Check | Result |
| --- | --- |
| Pytest | 12 passed, 1 skipped. The skipped Airflow import check requires Airflow |
| Ruff and Python compilation | Passed |
| TypeScript, Vite production build and Vitest | Passed; 3 Vitest tests |
| Browser and API | All 12 routes loaded in Chrome with actual data. Tested mobile navigation, Bronze/Silver/Gold previews, quarantine, filtered analytics, assistant answers, a report download and an API-triggered unchanged-input run |
| Report exports | All six report types passed PDF, CSV and XLSX checks. The executive exports matched stored run-level counts and alert links. The API returned the expected validation and missing-resource errors |
| Financial independently calculated totals | Demo, changed incremental, replay, German filter and standard runs reconciled |
| Reliability | Duplicate-input no-op, task metadata, strict gate, preservation of existing publication, 669 late-record flags and interrupted-status recovery test passed |
| Iceberg | Created the format-v2 table, recorded two publications, read earlier and later snapshots, and evolved the schema additively |
| Terraform | Formatting and local provider schema validation passed |
| Docker Compose | Standalone Compose 2.40.3 parsed and validated the configuration; Docker Engine execution and container image builds remain unverified |
| Dependency checks | Prior remediation checks reported zero npm advisories and reviewed Python release metadata. The final audit installed the locked frontend dependencies offline and ran the pinned Python suite |
| GitHub Actions | Workflow prepared; GitHub-hosted execution remains unverified |

The baseline and standard runs were measured on Windows 11 with four logical processors and Temurin Java 17, Python 3.13, PySpark 4.0.1 and DuckDB 1.5.6. Host memory measured during the subsequent audit was 7.90 GiB. The original run dependency and timing records are retained.

## Benchmarks

| Run or check | Measurement |
| --- | --- |
| Demo batch | 10,594 evaluated, 0 rejected, 69.49 s and 152.5 rows/s |
| Standard batch | 105,683 evaluated, 0 rejected, 203.53 s and 519.3 rows/s |
| Changed incremental | 930 new rows staged, 11,524 evaluated, 102.93 s |
| Replay over the same journal | 11,524 evaluated in 29.10 s. Revenue matched incremental at USD 1,360,238.67 |
| Unchanged incremental | 0.18 s with zero rows evaluated and the published snapshot retained |
| Quality challenge | 87 of 1,048 records quarantined. Seven directly scored injected categories detected |
| Anomaly detection | Median/MAD F1 1.000 and Isolation Forest F1 0.816 on a 100-point held-out synthetic series |
| Analytical queries | Six runs reconciled in 0.101–0.181 s. Germany filter total was USD 244,808.46 |
| Storage | Equivalent orders occupied 118,081 B CSV, 287,923 B JSON and 19,618 B compressed Parquet |
| Offline assistant | Four supported answer/evidence checks passed. Two unsupported prompts were rejected |

[Raw results](../evaluation/results/) · [Benchmark report](../evaluation/reports/BENCHMARK_REPORT.md) · [Reproduction](../evaluation/reports/methodology.md)

The final audit independently recalculated USD 1,360,238.67 from the stored seeded inputs and matched both historical Gold snapshots. A separate Tiny rerun reconciled changed incremental and batch replay revenue at USD 219,473.92 across 1,958 evaluated rows. The unchanged rerun kept the publication pointer, and the strict challenge blocked publication and quarantined 87 rows. Changed incremental inputs rebuild Silver and Gold snapshots. [Audit rerun measurements and environment](../evaluation/results/final_audit_recheck.json)

## AWS readiness

| Service | Evidence |
| --- | --- |
| S3 | Infrastructure configuration validated; S3-compatible source adapter mock-tested |
| AWS Glue Spark | Infrastructure configuration validated; shared validation executed locally on Spark. Managed Glue execution remains unverified |
| Glue Data Catalog | Infrastructure configuration validated; local Iceberg SQL catalog verified separately |
| Athena | Workgroup configuration validated and sample SQL prepared; live Athena execution remains unverified |
| AWS Lambda | Infrastructure configuration validated; trigger event handling and capacity retry mock-tested |
| EventBridge and SQS | Infrastructure configuration validated for landing events, optional schedule, buffering and dead-letter queue; live delivery remains unverified |
| CloudWatch | Infrastructure configuration validated for logs, metrics configuration and queue alarm; live telemetry remains unverified |
| IAM | Scoped roles and policy configuration validated syntactically; runtime permissions remain unverified |

No AWS infrastructure was deployed and no credentialed AWS plan was run. The AWS job currently publishes two Gold models and performs full rebuilds.

## Reproduce the demonstration

From the workspace directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-spark.txt -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
.\.venv\Scripts\python.exe -m data_engineering.cli generate --profile demo
.\.venv\Scripts\python.exe -m data_engineering.cli run
.\.venv\Scripts\python.exe -m data_engineering.cli generate --profile demo --batch 1
.\.venv\Scripts\python.exe -m data_engineering.cli run --mode incremental
```

Start the API and dashboard in separate terminals.

```powershell
.\scripts\start-local.ps1 api
.\scripts\start-local.ps1 web
```

Open the dashboard or API documentation. Press Ctrl+C in both terminals to stop. The initialization commands create the local runtime data from the seeded generator. [Dashboard](http://127.0.0.1:5173) · [API documentation](http://127.0.0.1:8000/docs)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend data_engineering aws orchestration evaluation/scripts scripts
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-infra.txt
.\.venv\Scripts\python.exe -m evaluation.scripts.benchmark --work .runtime/bench-next --output .runtime/bench-next-results
```

See [Quickstart](QUICKSTART.md) for Docker, Iceberg, Airflow, live browser testing and Windows troubleshooting.

## Portfolio and remaining work

The recommended GitHub name is `cloudlake-ai`. Use this description: “Reproducible PySpark commerce lakehouse with Bronze, Silver and Gold layers, data-quality gates, DuckDB analytics, an operations console and AWS infrastructure as code.”

Suggested initial commit: `Build CloudLake AI commerce lakehouse and operations console`.

[Portfolio text, topics and interview material](PORTFOLIO_MATERIALS.md) · [Ten demo screenshots](screenshots/) · [Sample PDF](sample-cloudlake-report.pdf) · [CSV](sample-cloudlake-report.csv) · [XLSX](sample-cloudlake-report.xlsx) · [Phase records](../PROJECT_STATUS.md)

The clean folder is ready for GitHub review. Repository initialization, commits, hosted publication and licensing remain pending owner authorization. [Final publication checklist](PUBLICATION_CHECKLIST.md)

Changed incremental inputs rebuild the complete local Silver and Gold snapshots. Larger profiles, Airflow execution, PostgreSQL, MinIO, live AWS, container runtime and GitHub-hosted execution remain unverified. The optional external assistant providers were left out. The local console assumes a trusted user and requires additional hardening for shared or public access. Licensing and GitHub publication remain subject to owner approval.
