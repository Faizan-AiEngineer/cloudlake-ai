import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from backend.app.database import Alert, Database, Quality, Run, State, Task
from data_engineering.gold import build
from data_engineering.ingest import Filesystem, exchange_rates, get_history, now, stage

logger = logging.getLogger(__name__)


@contextmanager
def exclusive(home):
    home.mkdir(parents=True, exist_ok=True)
    with (home / "pipeline.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("A pipeline already holds the workspace lease") from error
        yield


def open_alert(session, run_id, kind, severity, message):
    active = session.scalar(select(Alert).where(Alert.kind == kind, Alert.status != "resolved"))
    if active:
        active.run_id = run_id
        active.message = message
    else:
        session.add(Alert(run_id=run_id, kind=kind, severity=severity, message=message,
                          status="open", created_at=now()))


def recover_interrupted(db):
    message = "Worker exited before recording a result. Review the run and retry from the retained inputs."
    with exclusive(db.settings.home), db.transaction() as session:
        runs = list(session.scalars(select(Run).where(Run.status.in_(["running", "pending"]))))
        for run in runs:
            run.status, run.finished_at, run.error = "failed", now(), message
            open_alert(session, run.id, "pipeline_failure", "CRITICAL", message)
            tasks = session.scalars(select(Task).where(Task.run_id == run.id, Task.status == "running"))
            for task in tasks:
                task.status, task.finished_at, task.message = "failed", run.finished_at, message
        return len(runs)


@contextmanager
def task(db, run_id, name):
    with db.transaction() as session:
        row = Task(run_id=run_id, name=name, status="running", started_at=now())
        session.add(row)
        session.flush()
        task_id = row.id
    started = time.perf_counter()
    message = {}
    try:
        yield message
    except Exception as error:
        with db.transaction() as session:
            row = session.get(Task, task_id)
            row.status, row.message = "failed", str(error)[:1200]
            row.finished_at, row.seconds = now(), time.perf_counter() - started
        raise
    else:
        with db.transaction() as session:
            row = session.get(Task, task_id)
            row.status = message.get("status", "successful")
            row.message = message.get("message")
            row.finished_at, row.seconds = now(), time.perf_counter() - started


def watermarks(batches):
    values = {}
    for batch in batches:
        if batch.watermark:
            values[batch.dataset] = max(values.get(batch.dataset, ""), batch.watermark)
    return values


def run_pipeline(db: Database, landing: Path, mode="batch", trigger="cli", run_id=None, online_rates=False):
    home = db.settings.home
    run_id = run_id or uuid4().hex
    started = time.perf_counter()
    with db.transaction() as session:
        run = session.get(Run, run_id)
        if run:
            if run.status != "pending":
                raise ValueError("Run already started")
            run.status, run.started_at = "running", now()
        else:
            session.add(Run(id=run_id, mode=mode, trigger=trigger, status="running", started_at=now()))

    try:
        with exclusive(home):
            _process(db, landing, mode, run_id, online_rates)
    except Exception as error:
        logger.exception("Pipeline %s failed", run_id)
        with db.transaction() as session:
            run = session.get(Run, run_id)
            run.status = "failed"
            run.error = str(error)[:1200] or type(error).__name__
            open_alert(session, run_id, "pipeline_failure", "CRITICAL", "Review the failed pipeline task.")
    finally:
        with db.transaction() as session:
            run = session.get(Run, run_id)
            run.finished_at, run.duration = now(), time.perf_counter() - started
            status = run.status
    return {"run_id": run_id, "status": status}


def _process(db, landing, mode, run_id, online_rates):
    home = db.settings.home
    with db.transaction() as session:
        history = get_history(session)
    with task(db, run_id, "discover_sources") as report:
        sources = list(landing.sources() if hasattr(landing, "sources") else Filesystem(landing).sources())
        if not sources and not history:
            raise ValueError("No registered source files. Generate or upload data first.")
        if online_rates or not any(source.dataset == "rates" for source in sources):
            sources.append(exchange_rates(online_rates))
        report["message"] = f"{len(sources)} source files discovered"
    with task(db, run_id, "stage_bronze") as report:
        staged = stage(sources, home, run_id, history)
        report["message"] = f"{len(staged)} new files, {sum(batch.rows for batch in staged)} rows"
    if mode == "incremental" and not staged:
        with db.transaction() as session:
            row = session.get(Run, run_id)
            row.status, row.details = "successful", {"noop": True, "watermarks": watermarks(history)}
        return
    snapshots = home / "snapshots" / run_id
    with task(db, run_id, "validate_silver") as report:
        from data_engineering.silver import transform
        from data_engineering.spark_runtime import spark_session

        with spark_session(db.settings.spark_master) as spark:
            silver = transform(
                spark, history + staged, home, snapshots / "silver", run_id,
                watermarks(history), db.settings.quality_threshold,
            )
        report["message"] = f"{silver.rejected} records quarantined"
        with db.transaction() as session:
            session.add_all(Quality(**record) for record in silver.quality)
            row = session.get(Run, run_id)
            row.processed, row.rejected = sum(item["input"] for item in silver.datasets.values()), silver.rejected
            row.details = {"silver": silver.datasets, "new_rows": sum(batch.rows for batch in staged)}
            drift = [record["dataset"] for record in silver.quality if record["rule_id"] == "schema" and record["failed"]]
            if drift:
                open_alert(session, run_id, "schema_drift", "WARNING", "Schema changed in " + ", ".join(drift) + ".")
    with task(db, run_id, "quality_gate") as report:
        if silver.blocked:
            report["status"] = "blocked"
            report["message"] = "One or more critical rules exceeded the configured threshold"
            with db.transaction() as session:
                session.get(Run, run_id).status = "blocked"
                open_alert(session, run_id, "quality_gate", "CRITICAL", report["message"])
            return
    with task(db, run_id, "build_gold") as report:
        models = build(snapshots / "silver", snapshots / "gold")
        report["message"] = f"{len(models)} analytical tables written"
    with task(db, run_id, "publish") as report:
        byte_count = sum(path.stat().st_size for path in snapshots.rglob("*.parquet"))
        with db.transaction() as session:
            row = session.get(Run, run_id)
            row.status, row.bytes_written = "successful", byte_count
            row.details = {**row.details, "gold": models, "watermarks": watermarks(history + staged)}
            session.merge(State(key="published_run", value=run_id))
            session.add_all(batch.manifest() for batch in staged)
            if silver.rejected:
                open_alert(session, run_id, "quarantine", "WARNING", f"{silver.rejected} records quarantined.")
        report["message"] = f"{byte_count} snapshot bytes published"
