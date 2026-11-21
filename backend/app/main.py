import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.assistant import router as assistant_router
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.operations import router
from backend.app.reports import router as reports_router
from backend.app.request_limits import RequestLimits

logger = logging.getLogger("uvicorn.error")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.load()
    db = Database(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.migrate()
        yield
        db.engine.dispose()

    app = FastAPI(title="CloudLake AI", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.include_router(assistant_router)
    app.include_router(reports_router)
    app.state.database = db
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.origin],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"])
    app.add_middleware(RequestLimits, origin=config.origin)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        correlation_id = uuid4().hex
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Request failed [%s]", correlation_id)
            response = JSONResponse(
                {"detail": "Internal server error", "correlation_id": correlation_id},
                status_code=500,
            )
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(json.dumps({
            "event": "request", "method": request.method, "status": response.status_code,
            "correlation_id": correlation_id, "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }))
        return response

    def database_available():
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    @app.get("/health")
    def health():
        return {"status": "up"}

    @app.get("/ready")
    def ready():
        healthy = database_available()
        return JSONResponse({"ready": healthy}, status_code=200 if healthy else 503)

    @app.get("/api/v1/system/status")
    def status():
        return {
            "mode": "local",
            "api": "up",
            "metadata": {"engine": db.engine.dialect.name, "available": database_available()},
            "aws_deployed": False,
        }

    @app.get("/api/v1/system/configuration")
    def configuration():
        return {
            "mode": "local",
            "quality_threshold": config.quality_threshold,
            "spark_master": config.spark_master,
            "assistant_provider": "offline",
        }

    return app


app = create_app()
