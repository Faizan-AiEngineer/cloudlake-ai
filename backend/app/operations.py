import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.database import Alert, Manifest, Quality, Run, Task, published_run, serialize
from backend.app.lakehouse import inspect_parquet, lineage, partitions, snapshot, source_inventory
from data_engineering.gold import MODELS, sales_summary
from data_engineering.ingest import FORMATS, now, parse
from data_engineering.schema import FEEDS

router = APIRouter(prefix="/api/v1")
RunId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
PAGE_SIZE = Annotated[int, Query(ge=1, le=100)]
OFFSET = Annotated[int, Query(ge=0, le=100_000)]
UPLOAD_LIMIT = 10 * 1024 * 1024
LAUNCH_LOCK = Lock()
ROOT = Path(__file__).resolve().parents[2]


class RunRequest(BaseModel):
    mode: Literal["batch", "incremental"] = "batch"
    generate: bool = False
    profile: Literal["tiny", "demo"] = "demo"


class AlertUpdate(BaseModel):
    status: Literal["acknowledged", "resolved"]


def database(request):
    return request.app.state.database


def listing(session, stmt, limit, offset):
    count = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return {"items": [serialize(row) for row in session.scalars(stmt.limit(limit).offset(offset))],
            "total": count, "limit": limit, "offset": offset}


@router.get("/overview")
def overview(request: Request):
    db = database(request)
    with db.transaction() as session:
        count, processed = session.execute(select(func.count(Run.id), func.coalesce(func.sum(Run.processed), 0))).one()
        successful = session.scalar(select(func.count(Run.id)).where(Run.status == "successful"))
        alerts = session.scalar(select(func.count(Alert.id)).where(Alert.status != "resolved"))
        sources = session.scalar(select(func.count(func.distinct(Manifest.dataset))))
        recent = list(session.scalars(select(Run).order_by(Run.started_at.desc()).limit(30)))
        publication = session.get(Run, key) if (key := published_run(session)) else None
        durations = [
            {"run_id": run.id, "date": run.started_at, "status": run.status, "seconds": run.duration,
             "processed": run.processed, "quality": (1 - run.rejected / run.processed) if run.processed else None}
            for run in reversed(recent)
        ]
        bronze_bytes = sum((db.settings.home / key).stat().st_size for key in session.scalars(select(Manifest.key)))
        return {
            "processed": processed, "runs": count, "success_rate": successful / count if count else None,
            "active_sources": sources, "active_alerts": alerts, "published_run": publication.id if publication else None,
            "latest_publication": publication.finished_at if publication else None,
            "quality": 1 - publication.rejected / publication.processed
            if publication and publication.processed else None,
            "storage": {
                "bronze": bronze_bytes,
                "silver": sum(item["bytes"] for item in publication.details.get("silver", {}).values()) if publication else 0,
                "gold": sum(item["bytes"] for item in publication.details.get("gold", {}).values()) if publication else 0,
            },
            "history": durations,
        }


@router.get("/sources")
def sources(request: Request):
    return source_inventory(database(request))


@router.post("/sources/{dataset}/upload", status_code=201)
async def upload(
    request: Request, dataset: str,
    filename: Annotated[str, Query(min_length=3, max_length=100)],
):
    if dataset not in FEEDS:
        raise HTTPException(404, "Dataset is not registered")
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{2,99}", filename):
        raise HTTPException(422, "Use a simple CSV, JSON or Parquet filename")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > UPLOAD_LIMIT:
            raise HTTPException(413, "Upload limit is 10 MiB")
        body.extend(chunk)
    try:
        if not parse(body, suffix):
            raise ValueError("Empty file")
    except (ValueError, UnicodeError, OSError) as error:
        raise HTTPException(422, "File does not contain readable flat records") from error
    folder = database(request).settings.home / "landing" / dataset
    if folder.is_symlink():
        raise HTTPException(409, "Dataset path is a symbolic link")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}-{filename}"
    path = folder / name
    temp = path.with_suffix(".upload")
    try:
        temp.write_bytes(body)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return {"dataset": dataset, "file": name, "bytes": len(body)}


@router.get("/lakehouse")
def lakehouse(request: Request):
    return {"bronze": list(FEEDS), "silver": list(FEEDS), "gold": list(MODELS),
            "quarantine": ["rejected_records"], "published": snapshot(database(request)) is not None}


@router.get("/lakehouse/{zone}/{dataset}")
def preview(
    request: Request, zone: Literal["bronze", "silver", "gold", "quarantine"], dataset: str,
    limit: PAGE_SIZE = 25, run_id: RunId | None = None,
):
    db = database(request)
    path = snapshot(db)
    if zone in {"bronze", "silver"} and dataset not in FEEDS or zone == "gold" and dataset not in MODELS:
        raise HTTPException(404, "Dataset is not registered in this zone")
    if zone == "quarantine" and dataset != "rejected_records":
        raise HTTPException(404, "Dataset is not registered in this zone")
    if zone == "bronze":
        files = partitions(db, dataset)
    elif zone == "quarantine":
        if run_id:
            with db.transaction() as session:
                if session.get(Run, run_id) is None:
                    raise HTTPException(404, "Run not found")
            path = db.settings.home / "snapshots" / run_id
        files = [path / "quarantine.parquet"] if path else []
    else:
        files = [path / zone / f"{dataset}.parquet"] if path else []
    result = inspect_parquet(files, limit)
    result["partitions"] = [file.name for file in files if file.is_file()]
    return result


@router.get("/runs")
def list_runs(
    request: Request, limit: PAGE_SIZE = 25, offset: OFFSET = 0,
    status: Literal["pending", "running", "successful", "failed", "blocked"] | None = None,
):
    stmt = select(Run).order_by(Run.started_at.desc(), Run.id.desc())
    if status:
        stmt = stmt.where(Run.status == status)
    with database(request).transaction() as session:
        return listing(session, stmt, limit, offset)


@router.get("/runs/{run_id}")
def run_details(request: Request, run_id: RunId):
    with database(request).transaction() as session:
        run = session.get(Run, run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        tasks = session.scalars(select(Task).where(Task.run_id == run_id).order_by(Task.id)).all()
        return {"run": serialize(run), "tasks": [serialize(item) for item in tasks]}


def launch_worker(db, run_id, options):
    env = dict(os.environ, CLOUDLAKE_HOME=str(db.settings.home), CLOUDLAKE_DATABASE_URL=db.settings.database_url,
               CLOUDLAKE_QUALITY_THRESHOLD=str(db.settings.quality_threshold), CLOUDLAKE_SPARK_MASTER=db.settings.spark_master)
    logfile = db.settings.home / "logs" / f"{run_id}.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)
    error = "Worker exited before recording a result."
    try:
        with logfile.open("wb") as stream:
            if options.generate:
                subprocess.run([sys.executable, "-m", "data_engineering.cli", "generate", "--profile",
                                options.profile], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                               timeout=120, check=True)
            subprocess.run([sys.executable, "-m", "data_engineering.cli", "run", "--mode", options.mode,
                            "--run-id", run_id, "--trigger", "api"], cwd=ROOT, env=env, stdout=stream,
                           stderr=subprocess.STDOUT, timeout=1800, check=False)
    except subprocess.TimeoutExpired:
        error = "Pipeline worker exceeded its execution timeout."
    except (subprocess.CalledProcessError, OSError):
        error = "Worker setup failed. Review the execution log."
    finally:
        with db.transaction() as session:
            run = session.get(Run, run_id)
            if run and run.status in {"pending", "running"}:
                run.status, run.error, run.finished_at = "failed", error, now()
                from data_engineering.pipeline import open_alert

                open_alert(session, run_id, "pipeline_failure", "CRITICAL", error)
                for task in session.scalars(select(Task).where(Task.run_id == run_id, Task.status == "running")):
                    task.status, task.message, task.finished_at = "failed", error, run.finished_at


@router.post("/runs", status_code=202)
def start_run(request: Request, options: RunRequest):
    db = database(request)
    run_id = uuid4().hex
    with LAUNCH_LOCK:
        with db.transaction() as session:
            active = session.scalar(select(Run.id).where(Run.status.in_(["pending", "running"])).limit(1))
            if active:
                raise HTTPException(409, "A workspace run is already pending or running")
            session.add(Run(id=run_id, mode=options.mode, status="pending", trigger="api", started_at=now()))
        Thread(target=launch_worker, args=(db, run_id, options), daemon=True).start()
    return {"run_id": run_id, "status": "pending"}


@router.get("/runs/{run_id}/logs")
def run_logs(request: Request, run_id: RunId):
    path = database(request).settings.home / "logs" / f"{run_id}.log"
    if not path.is_file():
        return {"log": "", "available": False}
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 24_000))
        return {"log": stream.read(24_000).decode("utf-8", errors="replace"), "available": True}


@router.get("/quality")
def quality(request: Request, limit: PAGE_SIZE = 80, offset: OFFSET = 0,
            run_id: RunId | None = None, dataset: Annotated[str | None, Query(max_length=40)] = None):
    with database(request).transaction() as session:
        stmt = select(Quality).order_by(Quality.evaluated_at.desc(), Quality.dataset, Quality.rule_id)
        if run_id:
            stmt = stmt.where(Quality.run_id == run_id)
        if dataset:
            stmt = stmt.where(Quality.dataset == dataset)
        return listing(session, stmt, limit, offset)


@router.get("/alerts")
def alerts(request: Request, limit: PAGE_SIZE = 50, offset: OFFSET = 0,
           status: Literal["open", "acknowledged", "resolved"] | None = None,
           severity: Literal["CRITICAL", "WARNING", "INFO"] | None = None):
    with database(request).transaction() as session:
        stmt = select(Alert).order_by(Alert.id.desc())
        if status:
            stmt = stmt.where(Alert.status == status)
        if severity:
            stmt = stmt.where(Alert.severity == severity)
        return listing(session, stmt, limit, offset)


@router.patch("/alerts/{alert_id}")
def update_alert(request: Request, alert_id: int, options: AlertUpdate):
    with database(request).transaction() as session:
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(404, "Alert not found")
        if alert.status == "resolved" and options.status != "resolved":
            raise HTTPException(409, "Resolved alerts cannot be acknowledged")
        alert.status = options.status
        return serialize(alert)


@router.get("/lineage")
def get_lineage(request: Request):
    return lineage(snapshot(database(request)) is not None)


@router.get("/iceberg/snapshots")
def iceberg_history(request: Request):
    home = database(request).settings.home
    if not (home / "iceberg" / "catalog.db").is_file():
        return {"available": False, "snapshots": []}
    try:
        from pyiceberg.exceptions import NoSuchTableError

        from data_engineering.iceberg import iceberg_catalog
    except ImportError:
        return {"available": False, "snapshots": []}
    try:
        table = iceberg_catalog(home).load_table("commerce.daily_sales")
    except NoSuchTableError:
        return {"available": False, "snapshots": []}
    return {
        "available": True, "table": "commerce.daily_sales",
        "schema_id": table.schema().schema_id,
        "snapshots": [
            {"snapshot_id": str(item.snapshot_id), "committed_at": datetime.fromtimestamp(item.timestamp_ms / 1000, UTC),
             "operation": str(item.summary.operation.value) if item.summary else None}
            for item in table.snapshots()[-100:]
        ],
    }


@router.get("/analytics")
def analytics(request: Request, start: date | None = None, end: date | None = None,
              country: Annotated[str | None, Query(max_length=60)] = None,
              region: Annotated[str | None, Query(max_length=60)] = None,
              category: Annotated[str | None, Query(max_length=60)] = None,
              segment: Annotated[str | None, Query(max_length=60)] = None,
              channel: Annotated[str | None, Query(max_length=60)] = None):
    if start and end and end < start:
        raise HTTPException(422, "End date must be on or after the start date")
    directory = snapshot(database(request))
    if directory is None:
        return {"available": False}
    filters = dict(start=start, end=end, country=country, region=region, category=category,
                   segment=segment, channel=channel)
    return {"available": True, **sales_summary(directory / "gold", filters)}


@router.get("/monitoring")
def monitoring(request: Request):
    threshold = datetime.now(UTC) - timedelta(hours=36)
    feeds = source_inventory(database(request))
    return {"stale_hours": 36, "datasets": [{
        "name": item["dataset"], "status": "missing" if not item["updated_at"] else (
            "stale" if datetime.fromisoformat(item["updated_at"]) < threshold else "healthy"
        ), "ingested_at": item["updated_at"], "event_watermark": item["event_watermark"],
    } for item in feeds]}
