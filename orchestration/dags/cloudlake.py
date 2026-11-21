import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Param, dag, task

ROOT = Path(__file__).resolve().parents[2]


def on_failure(context):
    logging.error("CloudLake Airflow failure in %s, attempt %s",
                  context["task_instance"].task_id, context["task_instance"].try_number)


def command(*arguments):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    python = os.environ.get("CLOUDLAKE_PIPELINE_PYTHON", sys.executable)
    subprocess.run([python, "-m", "data_engineering.cli", *arguments],
                   cwd=ROOT, env=env, check=True, timeout=1800)


def workspace_home():
    return ROOT / os.environ.get("CLOUDLAKE_HOME", ".runtime")


DEFAULT = {
    "start_date": datetime(2025, 1, 1, tzinfo=UTC), "catchup": False, "max_active_runs": 1,
    "tags": ["cloudlake"],
    "default_args": {"retries": 1, "retry_delay": timedelta(minutes=5),
                     "execution_timeout": timedelta(minutes=35), "on_failure_callback": on_failure},
}


@task
def discover():
    path = workspace_home() / "landing"
    if not any(path.glob("*/*.*")):
        raise FileNotFoundError("No source batches in the configured landing directory")


@task
def process(mode):
    command("run", "--mode", mode, "--trigger", "airflow")


@task
def inspect_quality():
    command("monitor")


@dag(dag_id="cloudlake_batch", schedule="0 2 * * *", **DEFAULT)
def batch():
    discover() >> process("batch") >> inspect_quality()


@dag(dag_id="cloudlake_incremental", schedule="15 */4 * * *", **DEFAULT)
def incremental():
    discover() >> process("incremental")


@dag(dag_id="cloudlake_quality", schedule="30 */6 * * *", **DEFAULT)
def quality():
    inspect_quality()


@dag(dag_id="cloudlake_maintenance", schedule="0 1 * * 0", **DEFAULT)
def maintenance():
    @task
    def inventory():
        home = workspace_home()
        candidates = list(home.rglob("*.tmp"))
        sizes = sum(path.stat().st_size for path in home.rglob("*.parquet"))
        logging.info("Parquet bytes=%s, temporary file review candidates=%s", sizes, len(candidates))

    inventory()


@dag(dag_id="cloudlake_backfill", schedule=None, params={
    "start": Param("2024-01-01", type="string", format="date"),
    "end": Param("2024-01-31", type="string", format="date"),
}, **DEFAULT)
def backfill():
    @task
    def locate_window(params=None):
        first, last = (datetime.strptime(params[key], "%Y-%m-%d").date() for key in ("start", "end"))
        if not 0 <= (last - first).days <= 366:
            raise ValueError("Backfill range must contain at most 367 calendar dates")
        folder = workspace_home() / "backfill" / f"{first}_{last}"
        if not any(folder.glob("*/*.*")):
            raise FileNotFoundError(f"Place reviewed window-specific source files under {folder}")
        return str(folder)

    @task
    def process_window(folder):
        command("run", "--landing", folder, "--mode", "backfill", "--trigger", "airflow")

    process_window(locate_window())


batch()
incremental()
quality()
maintenance()
backfill()
