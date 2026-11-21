# Technology decisions

## Workspace audit

The workspace was empty and had no Git repository. Windows build 26100 has Python 3.13.2, Temurin Java 17.0.17 and Git 2.56.1. Node 20.20.2 and npm 10.8.2 are installed in the local Programs directory outside PATH. Approximately 4.06 GB was free on drive C. CIM returned an access error for memory inventory. Docker and Terraform were absent from PATH. The command sandbox failed to resolve the npm registry during the initial audit.

## Runtime choices

- Use the preinstalled PySpark 4.0.1 and Java 17 for local validation. Keep shared job expressions within the Spark 3.5/4.x surface where practical. AWS Glue 5.1 targets Spark 3.5.6 and Python 3.11 with the corresponding Iceberg integration. [Glue release notes](https://docs.aws.amazon.com/glue/latest/dg/release-notes.html)
- Use one Spark local worker and small shuffle partitions for the initial Windows workflow. Keep UI and database startup independent of the JVM.
- SQLite and a filesystem lake are the lightweight defaults. PostgreSQL and MinIO belong to the optional container profile. Use Alembic for transactional metadata schema changes.
- Serve typed, read-only analytics from DuckDB with a closed set of queries. Airflow remains an optional Linux runtime; Windows uses the same processing entry point through the CLI. [Airflow prerequisites](https://airflow.apache.org/docs/apache-airflow/3.1.7/installation/prerequisites.html)
- Frontend targets React, TypeScript and Vite on Node 20.19+ or 22.12+. Exact package versions are committed with the versioned dependency files. [Vite runtime requirements](https://vite.dev/guide/)
- Use explicit Iceberg format version 2 for Athena interoperability. [AWS Glue Iceberg migration notes](https://docs.aws.amazon.com/glue/latest/dg/migrating-version-60.html)

The Windows host reported four logical processors and 7.90 GiB RAM during the final audit. The security review moved Vite to 6.4.6 and Vitest to 4.1.12. PyPI advisories prompted updates to FastAPI's compatible Starlette version, PyArrow and pytest. The original benchmark files retain the versions used in their recorded runs.
