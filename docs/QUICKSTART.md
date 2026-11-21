# Quickstart

## Local Python and Node

Use the Windows commands in the [README](../README.md). On Linux, run `python3 -m venv .venv`, activate with `source .venv/bin/activate`, install both backend requirements files and run the same Python modules. Launch `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` and `npm --prefix frontend run dev` in separate terminal sessions.

Run `python -m data_engineering.cli generate --profile tiny --format csv` for a small CSV dataset or add `--challenge` to write labeled defects separately. Profiles are approximate total-row targets. `--count orders=100` overrides a supported count. Use the same dimensional sizing and seed across incremental batches. Reuse a distinct workspace if generating a different seed.

Set `CLOUDLAKE_HOME` to isolate an experiment. Environment variables and the optional `.env` come from [.env.example](../.env.example). `python -m data_engineering.cli migrate` runs the committed Alembic revision. `python -m data_engineering.cli stream --batches 3 --interval 5` simulates arrivals through recurring local micro-batches.

## Docker Compose

- Run `docker compose up --build` from the project root. Generate and process data with `docker compose exec api python -m data_engineering.cli generate --profile demo` and `docker compose exec api python -m data_engineering.cli run`.
- To use PostgreSQL, set `CLOUDLAKE_POSTGRES_PASSWORD` and `CLOUDLAKE_COMPOSE_DB_URL=postgresql+psycopg://cloudlake:<encoded-password>@postgres:5432/cloudlake`. Start PostgreSQL with `docker compose --profile infrastructure up -d postgres` before starting the API.
- To start MinIO, configure `CLOUDLAKE_MINIO_USER` and `CLOUDLAKE_MINIO_PASSWORD` and run `docker compose --profile infrastructure up -d minio`. The Python `S3Source` adapter accepts an S3-compatible boto3 client. Configure bucket and endpoint explicitly in the caller.
- Stop containers with `docker compose down`. The default named volumes retain data.

## Airflow and Iceberg

Install Airflow in its own Linux or WSL virtual environment with the version-matched official constraints. Set `AIRFLOW__CORE__DAGS_FOLDER` to the absolute `orchestration/dags` folder. Set `CLOUDLAKE_PIPELINE_PYTHON` to the absolute Python executable in the CloudLake application environment so pipeline subprocesses use the project's pinned SQLAlchemy and Spark dependencies. Configure `CLOUDLAKE_HOME` explicitly and share the same landing path, metadata database and lake volume across workers. See [Airflow constraints and installation](https://airflow.apache.org/docs/apache-airflow/3.1.7/installation/installing-from-pypi.html).

Install `backend/requirements-infra.txt` for the optional local Iceberg catalog. Run `python -m data_engineering.cli iceberg` after publishing to register daily sales in a separate format-v2 table. Run it following another publication to append snapshot history using a table overwrite commit. See [status](../PROJECT_STATUS.md) for the verified capabilities.

## Browser verification

Install `backend/requirements-qa.txt` and run `python -m playwright install chromium`. With a published demo and ports 8000 and 5173 available, run `npm --prefix frontend run build` followed by `python -m scripts.verify_demo --screens .runtime/demo-shots --exports .runtime/demo-exports --trigger`. The verification script owns its temporary backend and frontend servers. Pass `--chrome` and `--node` with explicit executables if needed. Use an unchanged landing directory for the no-op trigger check.
