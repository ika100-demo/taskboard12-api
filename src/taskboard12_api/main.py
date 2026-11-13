"""FastAPI entry point for taskboard12-api."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks import PostgresTaskStore, StorageUnavailableError
from .tasks import router as tasks_router
from .tracing import configure_tracing, tracing_enabled

logger = structlog.get_logger(__name__)

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()


class HealthResponse(BaseModel):
    status: str


def create_app(database_url: str | None = None) -> FastAPI:
    """Build the application with its own Postgres task store.

    ``database_url`` falls back to the ``DATABASE_URL`` environment variable,
    read when the app is built. No connection is made here.
    """
    url = database_url if database_url is not None else os.environ.get("DATABASE_URL")
    if url is None:
        logger.warning("database_url_missing")
    store = PostgresTaskStore(url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            await store.ensure_schema()
        except StorageUnavailableError:
            logger.warning("task_schema_deferred")
        yield

    app = FastAPI(title="taskboard12-api", version=__version__, lifespan=lifespan)
    app.add_middleware(MetricsMiddleware)
    if tracing_enabled():
        FastAPIInstrumentor.instrument_app(app)
    app.state.task_store = store

    @app.exception_handler(StorageUnavailableError)
    async def storage_unavailable_handler(
        _request: Request, _exc: StorageUnavailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Task storage is unavailable"})

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Liveness probe — returns 200 as long as the process is responding."""
        return HealthResponse(status="ok")

    @app.get("/ready", response_model=HealthResponse)
    async def ready() -> HealthResponse | JSONResponse:
        """Readiness probe — 200 when the database answers, else 503."""
        if await store.ping():
            return HealthResponse(status="ready")
        return JSONResponse(status_code=503, content={"status": "unavailable"})

    @app.get("/ping")
    def ping() -> dict[str, str]:
        """Simple ping endpoint."""
        return {"pong": "taskboard12-api"}

    @app.get("/metrics")
    def metrics() -> Response:
        """Prometheus scrape endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(tasks_router)
    return app


app = create_app()
